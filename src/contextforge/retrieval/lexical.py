"""Deterministic lexical ranking over indexed search units."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from contextforge.indexer import ProjectIndex, SearchUnit, SearchUnitKind
from contextforge.retrieval.models import (
    CandidateEligibility,
    CandidateOutcome,
    CandidateType,
    RetrievalCandidate,
    RetrievalEvidence,
    SelectionDecision,
    SelectionRationale,
    SelectionReason,
)
from contextforge.retrieval.query import NormalizedTaskQuery

LEXICAL_SEARCH_STRATEGY_VERSION = "lexical-search-v1"
_TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)
_PHRASE_PATTERN = re.compile(r"`([^`\r\n]+)`|\"([^\"\r\n]+)\"|'([^'\r\n]+)'")
_TYPE_BY_UNIT_KIND = {
    SearchUnitKind.SYMBOL_DEFINITION: CandidateType.SYMBOL_DEFINITION,
    SearchUnitKind.CONFIGURATION_BLOCK: CandidateType.CONFIGURATION_BLOCK,
    SearchUnitKind.DOCUMENTATION_SECTION: CandidateType.DOCUMENTATION_SECTION,
    SearchUnitKind.MANIFEST_SECTION: CandidateType.MANIFEST_SECTION,
}


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(_normalize(match.group()) for match in _TOKEN_PATTERN.finditer(value))


@dataclass(frozen=True, slots=True)
class LexicalSearchResult:
    """Ranked lexical candidates and the strategy version that produced them."""

    candidates: tuple[RetrievalCandidate, ...]
    strategy_version: str = LEXICAL_SEARCH_STRATEGY_VERSION

    def __post_init__(self) -> None:
        candidates = tuple(self.candidates)
        if any(not isinstance(candidate, RetrievalCandidate) for candidate in candidates):
            raise TypeError("candidates must contain RetrievalCandidate values")
        ranks = tuple(
            candidate.rationale.rank for candidate in candidates if candidate.rationale is not None
        )
        if ranks != tuple(range(1, len(candidates) + 1)):
            raise ValueError("candidates must have contiguous ranks")
        if not self.strategy_version.strip():
            raise ValueError("strategy_version must not be empty")
        object.__setattr__(self, "candidates", candidates)


@dataclass(frozen=True, slots=True)
class _ScoredUnit:
    unit: SearchUnit
    score: float
    matched_terms: tuple[str, ...]
    exact_phrase: bool
    path_match: bool


@dataclass(frozen=True, slots=True)
class LexicalSearchStrategy:
    """Rank search units using stable, explainable textual relevance."""

    version: str = LEXICAL_SEARCH_STRATEGY_VERSION

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("version must not be empty")

    def search(
        self,
        query: NormalizedTaskQuery,
        project_index: ProjectIndex,
    ) -> LexicalSearchResult:
        """Return relevant search units ordered by deterministic score."""
        if not isinstance(query, NormalizedTaskQuery):
            raise TypeError("query must be a NormalizedTaskQuery")
        if not isinstance(project_index, ProjectIndex):
            raise TypeError("project_index must be a ProjectIndex")

        query_terms = tuple(
            dict.fromkeys(
                (
                    *query.keywords,
                    *(_normalize(value) for value in query.quoted_identifiers),
                    *(_normalize(value) for value in query.symbols),
                )
            )
        )
        if not query_terms:
            return LexicalSearchResult((), self.version)

        paths = {
            artifact.artifact_id: artifact.path.value
            for artifact in project_index.indexed_artifacts
            if artifact.path is not None
        }
        scored: list[_ScoredUnit] = []
        phrases = tuple(
            _normalize(next(value for value in match.groups() if value is not None))
            for match in _PHRASE_PATTERN.finditer(query.original_text)
        )
        for unit in project_index.search_units:
            text = _normalize(unit.text)
            text_tokens = _tokens(text)
            counts = {term: text_tokens.count(term) for term in query_terms}
            matched = tuple(term for term in query_terms if counts[term])
            path = _normalize(paths.get(unit.artifact_id, ""))
            path_match = any(term in path for term in query_terms)
            exact_phrase = any(phrase in text for phrase in phrases)
            if not matched and not path_match and not exact_phrase:
                continue
            overlap = len(matched) / len(query_terms)
            frequency = sum(counts.values()) / max(len(text_tokens), 1)
            score = round(
                overlap + min(frequency, 1.0) * 0.25 + exact_phrase * 0.25 + path_match * 0.15,
                8,
            )
            scored.append(_ScoredUnit(unit, score, matched, exact_phrase, path_match))

        scored.sort(key=lambda item: (-item.score, item.unit.search_unit_id))
        candidates = tuple(self._candidate(item, rank) for rank, item in enumerate(scored, start=1))
        return LexicalSearchResult(candidates, self.version)

    def _candidate(self, scored: _ScoredUnit, rank: int) -> RetrievalCandidate:
        unit = scored.unit
        digest = hashlib.sha256(unit.search_unit_id.encode()).hexdigest()[:20]
        candidate_id = f"lexical_{digest}"
        details = [f"matched_terms={','.join(scored.matched_terms)}"]
        if scored.exact_phrase:
            details.append("exact_phrase=true")
        if scored.path_match:
            details.append("path_match=true")
        evidence = RetrievalEvidence(
            "lexical-text-match",
            self.version,
            ";".join(details),
            scored.score,
        )
        rationale = SelectionRationale(
            candidate_id,
            SelectionDecision.SELECTED,
            SelectionReason.LEXICAL_CONTENT_MATCH,
            (evidence,),
            score=scored.score,
            rank=rank,
            explanation="Search unit ranked by deterministic lexical relevance.",
        )
        return RetrievalCandidate(
            candidate_id,
            _TYPE_BY_UNIT_KIND.get(unit.kind, CandidateType.SOURCE_EXCERPT),
            unit.search_unit_id,
            f"search-unit:{unit.search_unit_id}",
            (evidence,),
            CandidateEligibility.ELIGIBLE,
            CandidateOutcome.SELECTED,
            len(unit.text.encode()),
            artifact_id=unit.artifact_id,
            location=unit.location,
            rationale=rationale,
        )
