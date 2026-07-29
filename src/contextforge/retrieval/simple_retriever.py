"""Minimal deterministic context retriever for analysis-only tasks."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from contextforge.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticCollection,
    DiagnosticSeverity,
)
from contextforge.domain import ArtifactId, RetrievalId, new_retrieval_id
from contextforge.indexer import (
    IndexedArtifact,
    ProjectIndex,
    RelationshipKind,
    RelationshipResolution,
    SearchUnit,
    SourceLocation,
    Symbol,
)
from contextforge.retrieval.models import (
    CandidateEligibility,
    CandidateOutcome,
    CandidateType,
    ContextBudget,
    RetrievalCandidate,
    RetrievalEvidence,
    RetrievalRequest,
    RetrievalResult,
    RetrievalStatistics,
    RetrievalStatus,
    SelectedContextItem,
    SelectionDecision,
    SelectionRationale,
    SelectionReason,
)
from contextforge.retrieval.query import TaskQueryNormalizer

SIMPLE_RETRIEVER_VERSION = "simple-retriever-v4"

_SEMANTIC_ALIASES: dict[str, tuple[str, ...]] = {
    "composed": ("configuration", "settings"),
    "constructed": ("configuration", "settings"),
    "salutation": ("greeting",),
}
_CURRENT_BEHAVIOR_TERMS = frozenset({"active", "current", "production", "runtime"})
_HISTORICAL_MARKERS = frozenset({"archive", "deprecated", "historical", "legacy"})
_BROAD_CONTEXT_TERMS = frozenset({"codebase", "project", "repository"})


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def _diagnostic(code: str, message: str) -> Diagnostic:
    return Diagnostic(
        DiagnosticCode(code),
        DiagnosticSeverity.WARNING,
        message,
        "simple-context-retriever",
    )


def _unique_hits(keywords: tuple[str, ...], text: str) -> tuple[str, ...]:
    normalized = _normalize(text)
    return tuple(keyword for keyword in keywords if keyword in normalized)


def _expand_keywords(keywords: tuple[str, ...]) -> tuple[str, ...]:
    expanded: list[str] = []
    seen: set[str] = set()
    for keyword in keywords:
        for candidate in (keyword, *_SEMANTIC_ALIASES.get(keyword, ())):
            if candidate not in seen:
                seen.add(candidate)
                expanded.append(candidate)
    return tuple(expanded)


def _estimate_tokens(character_count: int) -> int:
    if character_count == 0:
        return 0
    return max(1, (character_count * 11 + 39) // 40)


def _is_historical_distractor(
    keywords: tuple[str, ...],
    *candidate_text: str,
) -> bool:
    if not _CURRENT_BEHAVIOR_TERMS.intersection(keywords):
        return False
    normalized = " ".join(_normalize(value) for value in candidate_text)
    return any(marker in normalized for marker in _HISTORICAL_MARKERS)


@dataclass(frozen=True, slots=True)
class _ScoredCandidate:
    candidate_id: str
    candidate_type: CandidateType
    artifact_id: ArtifactId
    content_reference: str
    location: SourceLocation | None
    estimated_bytes: int
    estimated_characters: int
    score: int
    path_hits: tuple[str, ...]
    name_hits: tuple[str, ...]
    content_hits: tuple[str, ...]
    content_fingerprint: str | None = None
    historical_penalty: int = 0
    structural_hits: tuple[str, ...] = ()
    structural_boost: int = 0


class SimpleContextRetriever:
    """Select context by simple lexical overlap against a project index."""

    def __init__(self, normalizer: TaskQueryNormalizer | None = None) -> None:
        self._normalizer = normalizer if normalizer is not None else TaskQueryNormalizer()
        self._version = SIMPLE_RETRIEVER_VERSION

    def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        """Return a deterministic RetrievalResult for the request."""
        if not isinstance(request, RetrievalRequest):
            raise TypeError("request must be a RetrievalRequest")

        query = self._normalizer.normalize(request.task)
        composite_identifiers = tuple(
            token for token in query.normalized_text.split() if "_" in token or "." in token
        )
        keywords = _expand_keywords(
            tuple(
                term.normalized
                for term in query.terms
                if term.kind.value == "keyword" and len(term.normalized) >= 3
            )
            + composite_identifiers
        )
        specific_signals = tuple(
            dict.fromkeys(
                _normalize(value)
                for value in (
                    *query.explicit_paths,
                    *query.filenames,
                    *query.symbols,
                    *composite_identifiers,
                    *(keyword for keyword in keywords if "_" in keyword or "." in keyword),
                )
            )
        )

        artifact_by_id = {
            artifact.artifact_id: artifact for artifact in request.project_index.indexed_artifacts
        }
        units_by_artifact: dict[ArtifactId, list[SearchUnit]] = {
            artifact_id: [] for artifact_id in artifact_by_id
        }
        for unit in request.project_index.search_units:
            units_by_artifact.setdefault(unit.artifact_id, []).append(unit)

        candidates: list[_ScoredCandidate] = []
        candidates.extend(
            self._score_search_units(keywords, artifact_by_id, request.project_index.search_units)
        )
        candidates.extend(
            self._score_symbols(
                keywords, artifact_by_id, units_by_artifact, request.project_index.symbols
            )
        )
        candidates = self._boost_structural_dependencies(candidates, request.project_index)

        if not candidates:
            return self._empty_result(request)

        candidates.sort(key=lambda item: (-item.score, item.estimated_bytes, item.candidate_id))

        unique, duplicates = self._deduplicate_candidates(candidates)
        selected, excluded, exclusion_reasons = self._select_under_budget(unique, request.budget)
        excluded = [*duplicates, *excluded]
        exclusion_reasons.update(
            (candidate.candidate_id, SelectionReason.DUPLICATE_CONTENT) for candidate in duplicates
        )
        is_fallback = False

        if not selected and all(item.score == 0 for item in candidates):
            fallback = self._fallback_candidates(tuple(artifact_by_id.values()), units_by_artifact)
            selected, excluded, exclusion_reasons = self._select_under_budget(
                fallback, request.budget, require_positive_score=False
            )
            candidates = fallback
            is_fallback = True

        return self._build_result(
            request,
            candidates,
            selected,
            excluded,
            exclusion_reasons,
            is_fallback,
            specific_signals,
            bool(_BROAD_CONTEXT_TERMS.intersection(keywords)),
        )

    def _score_search_units(
        self,
        keywords: tuple[str, ...],
        artifact_by_id: dict[ArtifactId, IndexedArtifact],
        units: tuple[SearchUnit, ...],
    ) -> list[_ScoredCandidate]:
        scored: list[_ScoredCandidate] = []
        texts_by_artifact: dict[ArtifactId, list[str]] = {}
        for unit in units:
            texts_by_artifact.setdefault(unit.artifact_id, []).append(unit.text)
        historical_artifacts = {
            artifact_id
            for artifact_id, artifact in artifact_by_id.items()
            if _is_historical_distractor(
                keywords,
                str(artifact.path) if artifact.path is not None else "",
                *texts_by_artifact.get(artifact_id, ()),
            )
        }
        for unit in units:
            artifact = artifact_by_id.get(unit.artifact_id)
            if artifact is None:
                continue
            path = str(artifact.path) if artifact.path is not None else ""
            path_hits = _unique_hits(keywords, path)
            content_hits = _unique_hits(keywords, unit.text)
            raw_score = 3 * len(path_hits) + len(content_hits)
            historical_penalty = raw_score if unit.artifact_id in historical_artifacts else 0
            scored.append(
                _ScoredCandidate(
                    candidate_id=unit.search_unit_id,
                    candidate_type=CandidateType.SOURCE_EXCERPT,
                    artifact_id=unit.artifact_id,
                    content_reference=path,
                    location=unit.location,
                    estimated_bytes=len(unit.text.encode("utf-8")),
                    estimated_characters=len(unit.text),
                    score=raw_score - historical_penalty,
                    path_hits=path_hits,
                    name_hits=(),
                    content_hits=content_hits,
                    content_fingerprint=artifact.content_fingerprint,
                    historical_penalty=historical_penalty,
                )
            )
        return scored

    @staticmethod
    def _boost_structural_dependencies(
        candidates: list[_ScoredCandidate],
        project_index: ProjectIndex,
    ) -> list[_ScoredCandidate]:
        """Boost verified direct dependencies of the strongest lexical artifacts."""
        maximum = max((candidate.score for candidate in candidates), default=0)
        if maximum <= 0:
            return candidates
        seed_artifacts = {
            candidate.artifact_id
            for candidate in candidates
            if candidate.score == maximum and candidate.historical_penalty == 0
        }
        entity_artifacts: dict[str, ArtifactId] = {
            str(artifact.artifact_id): artifact.artifact_id
            for artifact in project_index.indexed_artifacts
        }
        entity_artifacts.update(
            (symbol.symbol_id, symbol.artifact_id) for symbol in project_index.symbols
        )
        allowed_kinds = {
            RelationshipKind.CALLS,
            RelationshipKind.CONFIGURES,
            RelationshipKind.DEPENDS_ON,
            RelationshipKind.IMPORTS,
            RelationshipKind.REFERENCES,
        }
        hits_by_artifact: dict[ArtifactId, list[str]] = {}
        for relationship in project_index.relationships:
            if (
                relationship.resolution is not RelationshipResolution.RESOLVED_INTERNAL
                or relationship.kind not in allowed_kinds
                or entity_artifacts.get(relationship.source_reference) not in seed_artifacts
            ):
                continue
            target_artifact = entity_artifacts.get(relationship.target_reference)
            if target_artifact is None or target_artifact in seed_artifacts:
                continue
            hits_by_artifact.setdefault(target_artifact, []).append(relationship.relationship_id)
        boosted: list[_ScoredCandidate] = []
        for candidate in candidates:
            hits = tuple(sorted(set(hits_by_artifact.get(candidate.artifact_id, ()))))
            if not hits or candidate.historical_penalty:
                boosted.append(candidate)
                continue
            boosted_score = min(
                candidate.score + 4 * len(hits),
                max(0, maximum - 1),
            )
            boosted.append(
                replace(
                    candidate,
                    score=boosted_score,
                    structural_hits=hits,
                    structural_boost=boosted_score - candidate.score,
                )
            )
        return boosted

    def _score_symbols(
        self,
        keywords: tuple[str, ...],
        artifact_by_id: dict[ArtifactId, IndexedArtifact],
        units_by_artifact: dict[ArtifactId, list[SearchUnit]],
        symbols: tuple[Symbol, ...],
    ) -> list[_ScoredCandidate]:
        scored: list[_ScoredCandidate] = []
        for symbol in symbols:
            artifact = artifact_by_id.get(symbol.artifact_id)
            if artifact is None:
                continue
            path = str(artifact.path) if artifact.path is not None else ""
            path_hits = _unique_hits(keywords, path)
            name_hits = _unique_hits(keywords, symbol.name)
            content_hits = _unique_hits(keywords, symbol.signature or "")
            # A symbol-name match is more specific than a path/content token match.
            # Keep it dominant so generic filenames cannot displace the definition
            # under a one-artifact budget.
            raw_score = 3 * len(path_hits) + 6 * len(name_hits) + len(content_hits)
            historical_penalty = (
                raw_score
                if _is_historical_distractor(
                    keywords,
                    path,
                    symbol.name,
                    symbol.signature or "",
                    *(unit.text for unit in units_by_artifact.get(symbol.artifact_id, ())),
                )
                else 0
            )
            estimated_bytes = self._estimate_artifact_bytes_from_units(
                units_by_artifact, symbol.artifact_id
            )
            scored.append(
                _ScoredCandidate(
                    candidate_id=symbol.symbol_id,
                    candidate_type=CandidateType.SYMBOL_DEFINITION,
                    artifact_id=symbol.artifact_id,
                    content_reference=path,
                    location=symbol.location,
                    estimated_bytes=estimated_bytes,
                    estimated_characters=len(symbol.signature or symbol.name),
                    score=raw_score - historical_penalty,
                    path_hits=path_hits,
                    name_hits=name_hits,
                    content_hits=content_hits,
                    content_fingerprint=artifact.content_fingerprint,
                    historical_penalty=historical_penalty,
                )
            )
        return scored

    def _fallback_candidates(
        self,
        artifacts: tuple[IndexedArtifact, ...],
        units_by_artifact: dict[ArtifactId, list[SearchUnit]],
    ) -> list[_ScoredCandidate]:
        candidates: list[_ScoredCandidate] = []
        for artifact in artifacts:
            path = str(artifact.path) if artifact.path is not None else ""
            estimated_bytes = self._estimate_artifact_bytes_from_units(
                units_by_artifact, artifact.artifact_id
            )
            candidates.append(
                _ScoredCandidate(
                    candidate_id=f"artifact-{artifact.artifact_id}",
                    candidate_type=CandidateType.FULL_ARTIFACT,
                    artifact_id=artifact.artifact_id,
                    content_reference=path,
                    location=None,
                    estimated_bytes=estimated_bytes,
                    estimated_characters=estimated_bytes,
                    score=0,
                    path_hits=(),
                    name_hits=(),
                    content_hits=(),
                    content_fingerprint=artifact.content_fingerprint,
                )
            )
        candidates.sort(key=lambda item: (item.estimated_bytes, item.candidate_id))
        return candidates

    def _select_under_budget(
        self,
        candidates: list[_ScoredCandidate],
        budget: ContextBudget,
        *,
        require_positive_score: bool = True,
    ) -> tuple[
        list[_ScoredCandidate],
        list[_ScoredCandidate],
        dict[str, SelectionReason],
    ]:
        selected: list[_ScoredCandidate] = []
        excluded: list[_ScoredCandidate] = []
        exclusion_reasons: dict[str, SelectionReason] = {}
        used_bytes = 0
        used_characters = 0
        used_tokens = 0
        selected_artifacts: set[ArtifactId] = set()
        selected_excerpts = 0
        for candidate in candidates:
            if require_positive_score and candidate.score <= 0:
                excluded.append(candidate)
                exclusion_reasons[candidate.candidate_id] = (
                    SelectionReason.BELOW_RELEVANCE_THRESHOLD
                )
                continue
            estimated_tokens = _estimate_tokens(candidate.estimated_characters)
            over_items = budget.max_items is not None and len(selected) >= budget.max_items
            over_bytes = (
                budget.max_bytes is not None
                and used_bytes + candidate.estimated_bytes > budget.max_bytes
            )
            over_characters = (
                budget.max_characters is not None
                and used_characters + candidate.estimated_characters > budget.max_characters
            )
            over_tokens = (
                budget.max_estimated_tokens is not None
                and used_tokens + estimated_tokens > budget.max_estimated_tokens
            )
            over_artifacts = (
                budget.max_artifacts is not None
                and candidate.artifact_id not in selected_artifacts
                and len(selected_artifacts) >= budget.max_artifacts
            )
            over_excerpts = (
                budget.max_excerpts is not None
                and candidate.candidate_type is CandidateType.SOURCE_EXCERPT
                and selected_excerpts >= budget.max_excerpts
            )
            over_item_bytes = (
                budget.max_item_bytes is not None
                and candidate.estimated_bytes > budget.max_item_bytes
            )
            if any(
                (
                    over_items,
                    over_bytes,
                    over_characters,
                    over_tokens,
                    over_artifacts,
                    over_excerpts,
                    over_item_bytes,
                )
            ):
                excluded.append(candidate)
                exclusion_reasons[candidate.candidate_id] = SelectionReason.CONTEXT_BUDGET_EXCEEDED
            else:
                selected.append(candidate)
                used_bytes += candidate.estimated_bytes
                used_characters += candidate.estimated_characters
                used_tokens += estimated_tokens
                selected_artifacts.add(candidate.artifact_id)
                if candidate.candidate_type is CandidateType.SOURCE_EXCERPT:
                    selected_excerpts += 1
        return selected, excluded, exclusion_reasons

    @staticmethod
    def _deduplicate_candidates(
        candidates: list[_ScoredCandidate],
    ) -> tuple[list[_ScoredCandidate], list[_ScoredCandidate]]:
        unique: list[_ScoredCandidate] = []
        duplicates: list[_ScoredCandidate] = []
        seen: set[tuple[object, ...]] = set()
        for candidate in candidates:
            location = candidate.location
            span = (
                (
                    candidate.artifact_id,
                    candidate.content_reference,
                    None,
                )
                if location is None
                else (
                    location.artifact_id,
                    location.start_line,
                    location.start_column,
                    location.end_line,
                    location.end_column,
                )
            )
            if span in seen:
                duplicates.append(candidate)
            else:
                seen.add(span)
                unique.append(candidate)
        return unique, duplicates

    def _build_result(
        self,
        request: RetrievalRequest,
        candidates: list[_ScoredCandidate],
        selected: list[_ScoredCandidate],
        excluded: list[_ScoredCandidate],
        exclusion_reasons: dict[str, SelectionReason],
        is_fallback: bool = False,
        specific_signals: tuple[str, ...] = (),
        broad_context_requested: bool = False,
    ) -> RetrievalResult:
        retrieval_id = new_retrieval_id()

        retrieval_candidates: list[RetrievalCandidate] = []
        selected_items: list[SelectedContextItem] = []
        rationales: list[SelectionRationale] = []
        artifacts_selected: set[ArtifactId] = set()
        excerpts = 0
        symbols = 0

        for rank, candidate in enumerate(selected, start=1):
            rationale = self._selected_rationale(candidate, rank)
            retrieval_candidate = self._to_retrieval_candidate(candidate, rationale)
            retrieval_candidates.append(retrieval_candidate)
            rationales.append(rationale)
            selected_items.append(self._to_selected_item(retrieval_id, candidate, rationale))
            artifacts_selected.add(candidate.artifact_id)
            if candidate.candidate_type is CandidateType.SOURCE_EXCERPT:
                excerpts += 1
            elif candidate.candidate_type is CandidateType.SYMBOL_DEFINITION:
                symbols += 1

        for candidate in excluded:
            rationale = self._excluded_rationale(
                candidate,
                reason=exclusion_reasons.get(candidate.candidate_id),
                is_fallback=is_fallback,
            )
            retrieval_candidates.append(self._to_retrieval_candidate(candidate, rationale))
            rationales.append(rationale)

        sufficient_evidence = bool(selected) and (not is_fallback or broad_context_requested)
        if sufficient_evidence and specific_signals:
            sufficient_evidence = any(
                signal
                in {
                    *candidate.path_hits,
                    *candidate.name_hits,
                    *candidate.content_hits,
                }
                for candidate in selected
                for signal in specific_signals
            )

        diagnostics: list[Diagnostic] = []
        if not selected:
            diagnostics.append(
                _diagnostic(
                    "RETRIEVAL_NO_RELEVANT_CONTEXT",
                    "Simple retriever produced no selected context items.",
                )
            )
        elif not sufficient_evidence:
            diagnostics.append(
                _diagnostic(
                    "RETRIEVAL_INSUFFICIENT_CONTEXT",
                    "Selected context does not resolve the task's specific references.",
                )
            )

        return RetrievalResult(
            retrieval_id=retrieval_id,
            task_id=request.task.task_id,
            index_id=request.project_index.index_id,
            project_fingerprint=request.project_index.project_fingerprint,
            strategy_versions=(self._version, TaskQueryNormalizer().version),
            candidates=tuple(retrieval_candidates),
            selected_items=tuple(selected_items),
            rationales=tuple(rationales),
            applied_budget=request.budget,
            diagnostics=DiagnosticCollection(tuple(diagnostics)),
            statistics=RetrievalStatistics(
                candidates_generated=len(candidates),
                candidates_evaluated=len(candidates),
                artifacts_selected=len(artifacts_selected),
                excerpts_selected=excerpts,
                symbols_selected=symbols,
                candidates_budget_excluded=sum(
                    1
                    for candidate in excluded
                    if exclusion_reasons.get(candidate.candidate_id)
                    is SelectionReason.CONTEXT_BUDGET_EXCEEDED
                ),
                duplicates_suppressed=sum(
                    reason is SelectionReason.DUPLICATE_CONTENT
                    for reason in exclusion_reasons.values()
                ),
                estimated_selected_tokens=sum(
                    item.estimated_tokens or 0 for item in selected_items
                ),
            ),
            status=(
                RetrievalStatus.COMPLETE if sufficient_evidence else RetrievalStatus.INCOMPLETE
            ),
            created_at=datetime.now(UTC),
        )

    def _to_retrieval_candidate(
        self,
        candidate: _ScoredCandidate,
        rationale: SelectionRationale,
    ) -> RetrievalCandidate:
        return RetrievalCandidate(
            candidate_id=candidate.candidate_id,
            candidate_type=candidate.candidate_type,
            source_reference=candidate.candidate_id,
            content_reference=candidate.content_reference,
            evidence=rationale.evidence,
            eligibility=CandidateEligibility.ELIGIBLE,
            outcome=CandidateOutcome.SELECTED
            if rationale.decision is SelectionDecision.SELECTED
            else CandidateOutcome.EXCLUDED,
            estimated_bytes=candidate.estimated_bytes,
            estimated_tokens=_estimate_tokens(candidate.estimated_characters),
            artifact_id=candidate.artifact_id,
            location=candidate.location,
            rationale=rationale,
        )

    def _to_selected_item(
        self,
        retrieval_id: RetrievalId,
        candidate: _ScoredCandidate,
        rationale: SelectionRationale,
    ) -> SelectedContextItem:
        return SelectedContextItem(
            context_item_id=f"simple-item-{candidate.candidate_id}",
            candidate_id=candidate.candidate_id,
            artifact_id=candidate.artifact_id,
            content_reference=candidate.content_reference,
            candidate_type=candidate.candidate_type,
            rationale=rationale,
            location=candidate.location,
            estimated_bytes=candidate.estimated_bytes,
            estimated_characters=candidate.estimated_characters,
            estimated_tokens=_estimate_tokens(candidate.estimated_characters),
            score_breakdown=self._score_breakdown(candidate),
            content_fingerprint=candidate.content_fingerprint,
            sensitivity_classification="standard",
        )

    def _selected_rationale(
        self,
        candidate: _ScoredCandidate,
        rank: int,
    ) -> SelectionRationale:
        primary_reason = (
            SelectionReason.LEXICAL_CONTENT_MATCH
            if candidate.score > 0
            else SelectionReason.REQUIRED_CONTEXT
        )
        return SelectionRationale(
            candidate_id=candidate.candidate_id,
            decision=SelectionDecision.SELECTED,
            primary_reason=primary_reason,
            evidence=(self._simple_evidence(candidate),),
            score=float(candidate.score),
            rank=rank,
            explanation="Selected by simple lexical relevance scoring.",
        )

    def _excluded_rationale(
        self,
        candidate: _ScoredCandidate,
        *,
        reason: SelectionReason | None = None,
        is_fallback: bool = False,
    ) -> SelectionRationale:
        primary_reason: SelectionReason
        if reason is SelectionReason.DUPLICATE_CONTENT:
            primary_reason = reason
            explanation = "Excluded because another candidate covers the same source span."
        elif reason is SelectionReason.CONTEXT_BUDGET_EXCEEDED or is_fallback:
            primary_reason = SelectionReason.CONTEXT_BUDGET_EXCEEDED
            explanation = "Excluded because the candidate does not fit within the Context Budget."
        else:
            primary_reason = SelectionReason.BELOW_RELEVANCE_THRESHOLD
            explanation = "Excluded because the candidate scored no lexical relevance."
        return SelectionRationale(
            candidate_id=candidate.candidate_id,
            decision=SelectionDecision.EXCLUDED,
            primary_reason=primary_reason,
            evidence=(self._simple_evidence(candidate),),
            score=float(candidate.score),
            explanation=explanation,
        )

    def _simple_evidence(self, candidate: _ScoredCandidate) -> RetrievalEvidence:
        detail = (
            f"score={candidate.score};"
            f"path_hits={','.join(candidate.path_hits) or 'none'};"
            f"name_hits={','.join(candidate.name_hits) or 'none'};"
            f"content_hits={','.join(candidate.content_hits) or 'none'};"
            f"historical_penalty={candidate.historical_penalty};"
            f"structural_hits={','.join(candidate.structural_hits) or 'none'};"
            f"structural_boost={candidate.structural_boost}"
        )
        return RetrievalEvidence(
            evidence_type="simple-lexical",
            source="retriever",
            detail=detail,
            weight=float(candidate.score),
        )

    def _score_breakdown(
        self,
        candidate: _ScoredCandidate,
    ) -> tuple[tuple[str, float], ...]:
        return (
            ("path", float(3 * len(candidate.path_hits))),
            ("name", float(6 * len(candidate.name_hits))),
            ("content", float(len(candidate.content_hits))),
            ("structural", float(candidate.structural_boost)),
            ("historical_penalty", float(-candidate.historical_penalty)),
        )

    @staticmethod
    def _estimate_artifact_bytes_from_units(
        units_by_artifact: dict[ArtifactId, list[SearchUnit]],
        artifact_id: ArtifactId,
    ) -> int:
        return sum(
            len(unit.text.encode("utf-8")) for unit in units_by_artifact.get(artifact_id, ())
        )

    def _empty_result(self, request: RetrievalRequest) -> RetrievalResult:
        return RetrievalResult(
            retrieval_id=new_retrieval_id(),
            task_id=request.task.task_id,
            index_id=request.project_index.index_id,
            project_fingerprint=request.project_index.project_fingerprint,
            strategy_versions=(self._version, TaskQueryNormalizer().version),
            candidates=(),
            selected_items=(),
            rationales=(),
            applied_budget=request.budget,
            diagnostics=DiagnosticCollection(
                (
                    _diagnostic(
                        "RETRIEVAL_NO_CANDIDATES",
                        "Project index contains no retrievable candidates.",
                    ),
                )
            ),
            statistics=RetrievalStatistics(),
            status=RetrievalStatus.INCOMPLETE,
            created_at=datetime.now(UTC),
        )
