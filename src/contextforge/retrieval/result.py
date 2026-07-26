"""Assembly of complete, explainable Retrieval Results."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import datetime

from contextforge.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticCollection,
    DiagnosticSeverity,
)
from contextforge.domain import RetrievalId
from contextforge.retrieval.budgeting import (
    BudgetSelectionResult,
    CandidateBudgetEstimate,
)
from contextforge.retrieval.dependencies import DependencyTraversalPath
from contextforge.retrieval.eligibility import ArtifactEligibilityRecord
from contextforge.retrieval.models import (
    CandidateOutcome,
    CandidateType,
    RetrievalCandidate,
    RetrievalRequest,
    RetrievalResult,
    RetrievalStatistics,
    RetrievalStatus,
    SelectedContextItem,
    SelectionDecision,
    SelectionRationale,
    SelectionReason,
)
from contextforge.retrieval.scoring import RetrievalScoreResult

RETRIEVAL_RESULT_ASSEMBLER_VERSION = "retrieval-result-v1"


def _fallback_rationale(candidate: RetrievalCandidate) -> SelectionRationale:
    decision = {
        CandidateOutcome.SELECTED: SelectionDecision.SELECTED,
        CandidateOutcome.TRUNCATED: SelectionDecision.SELECTED,
        CandidateOutcome.EXCLUDED: SelectionDecision.EXCLUDED,
        CandidateOutcome.DEFERRED: SelectionDecision.DEFERRED,
    }[candidate.outcome]
    reason = {
        CandidateOutcome.SELECTED: SelectionReason.REQUIRED_CONTEXT,
        CandidateOutcome.TRUNCATED: SelectionReason.REQUIRED_CONTEXT,
        CandidateOutcome.EXCLUDED: SelectionReason.BELOW_RELEVANCE_THRESHOLD,
        CandidateOutcome.DEFERRED: SelectionReason.DEFERRED_AMBIGUITY,
    }[candidate.outcome]
    return SelectionRationale(
        candidate.candidate_id,
        decision,
        reason,
        candidate.evidence,
        explanation="Final retrieval disposition.",
    )


def _diagnostic(code: str, message: str) -> Diagnostic:
    return Diagnostic(
        DiagnosticCode(code),
        DiagnosticSeverity.WARNING,
        message,
        "context-retriever",
    )


@dataclass(frozen=True, slots=True)
class RetrievalResultAssembler:
    """Construct the final contract from already filtered and budgeted state."""

    version: str = RETRIEVAL_RESULT_ASSEMBLER_VERSION

    def assemble(
        self,
        request: RetrievalRequest,
        retrieval_id: RetrievalId,
        budget_result: BudgetSelectionResult,
        score_result: RetrievalScoreResult,
        created_at: datetime,
        *,
        strategy_versions: tuple[str, ...],
        estimates: tuple[CandidateBudgetEstimate, ...] = (),
        eligibility_records: tuple[ArtifactEligibilityRecord, ...] = (),
        dependency_paths: tuple[tuple[str, DependencyTraversalPath], ...] = (),
        diagnostic_collections: tuple[DiagnosticCollection, ...] = (),
        incomplete: bool = False,
    ) -> RetrievalResult:
        """Assemble selected items, statistics, diagnostics, and final status."""
        if not isinstance(request, RetrievalRequest):
            raise TypeError("request must be a RetrievalRequest")
        if not isinstance(retrieval_id, RetrievalId):
            raise TypeError("retrieval_id must be a RetrievalId")
        candidates = tuple(
            candidate
            if candidate.rationale is not None
            else replace(candidate, rationale=_fallback_rationale(candidate))
            for candidate in budget_result.candidates
        )
        candidate_ids = {candidate.candidate_id for candidate in candidates}
        scores = {score.candidate_id: score for score in score_result.scores}
        if set(scores) != candidate_ids:
            raise ValueError("score_result must cover every final candidate")
        budget_ranks = {
            candidate_id: rank
            for rank, candidate_id in enumerate(budget_result.selected_candidate_ids, start=1)
        }
        candidates = tuple(
            replace(
                candidate,
                rationale=replace(
                    candidate.rationale,
                    rank=budget_ranks[candidate.candidate_id],
                    score=scores[candidate.candidate_id].normalized_score,
                ),
            )
            if candidate.candidate_id in budget_ranks
            and candidate.rationale is not None
            and candidate.rationale.rank is None
            else candidate
            for candidate in candidates
        )
        characters = {estimate.candidate_id: estimate.characters for estimate in estimates}
        if not set(characters) <= candidate_ids:
            raise ValueError("estimates must reference final candidates")
        records = {record.artifact_id: record for record in eligibility_records}
        if len(records) != len(eligibility_records):
            raise ValueError("eligibility_records must not contain duplicates")
        paths = dict(dependency_paths)
        if len(paths) != len(dependency_paths):
            raise ValueError("dependency_paths must not contain duplicate candidates")
        if not set(paths) <= candidate_ids:
            raise ValueError("dependency_paths must reference final candidates")

        indexed = {
            artifact.artifact_id: artifact for artifact in request.project_index.indexed_artifacts
        }
        selected_items = []
        for candidate in candidates:
            if candidate.outcome not in (
                CandidateOutcome.SELECTED,
                CandidateOutcome.TRUNCATED,
            ):
                continue
            assert candidate.rationale is not None
            score = scores[candidate.candidate_id]
            record = (
                records.get(candidate.artifact_id) if candidate.artifact_id is not None else None
            )
            sensitivity = (
                "sensitive"
                if record is not None and record.sensitive
                else ("standard" if candidate.artifact_id is not None else "not_applicable")
            )
            path = paths.get(candidate.candidate_id)
            digest = hashlib.sha256(
                f"{retrieval_id}\0{candidate.candidate_id}".encode()
            ).hexdigest()[:20]
            indexed_artifact = (
                indexed.get(candidate.artifact_id) if candidate.artifact_id is not None else None
            )
            selected_items.append(
                SelectedContextItem(
                    f"context_item_{digest}",
                    candidate.candidate_id,
                    candidate.artifact_id,
                    candidate.content_reference,
                    candidate.candidate_type,
                    candidate.rationale,
                    candidate.location,
                    candidate.estimated_tokens,
                    indexed_artifact.content_fingerprint if indexed_artifact is not None else None,
                    candidate.outcome is CandidateOutcome.TRUNCATED,
                    candidate.estimated_bytes,
                    characters.get(candidate.candidate_id, candidate.estimated_bytes),
                    tuple(
                        (component.component.value, component.weighted_value)
                        for component in score.components
                    ),
                    sensitivity,
                    tuple(step.relationship_id for step in path.steps) if path is not None else (),
                )
            )

        diagnostics = list(budget_result.diagnostics)
        for collection in diagnostic_collections:
            diagnostics.extend(collection)
        no_selection = not selected_items
        if no_selection:
            diagnostics.append(
                _diagnostic(
                    "RETRIEVAL_NO_RELEVANT_CONTEXT",
                    "Retrieval produced no selected context items.",
                )
            )
        is_incomplete = incomplete or budget_result.mandatory_overflow or no_selection
        diagnostic_collection = DiagnosticCollection(tuple(diagnostics))
        status = (
            RetrievalStatus.INCOMPLETE
            if is_incomplete
            else (
                RetrievalStatus.COMPLETE_WITH_WARNINGS
                if len(diagnostic_collection)
                else RetrievalStatus.COMPLETE
            )
        )
        selected_candidates = {item.candidate_id: item for item in selected_items}
        selected_artifacts = {
            candidate.artifact_id
            for candidate in candidates
            if candidate.candidate_id in selected_candidates and candidate.artifact_id is not None
        }
        return RetrievalResult(
            retrieval_id,
            request.task.task_id,
            request.project_index.index_id,
            request.project_index.project_fingerprint,
            (*strategy_versions, self.version),
            candidates,
            tuple(selected_items),
            tuple(candidate.rationale for candidate in candidates if candidate.rationale),
            request.budget,
            diagnostic_collection,
            RetrievalStatistics(
                candidates_generated=len(candidates),
                candidates_evaluated=len(candidates),
                artifacts_selected=len(selected_artifacts),
                excerpts_selected=sum(
                    item.candidate_type is CandidateType.SOURCE_EXCERPT for item in selected_items
                ),
                symbols_selected=sum(
                    item.candidate_type is CandidateType.SYMBOL_DEFINITION
                    for item in selected_items
                ),
                relationships_traversed=sum(len(path.steps) for path in paths.values()),
                candidates_budget_excluded=sum(
                    candidate.rationale is not None
                    and candidate.rationale.primary_reason
                    is SelectionReason.CONTEXT_BUDGET_EXCEEDED
                    for candidate in candidates
                ),
                estimated_selected_tokens=sum(
                    item.estimated_tokens or 0 for item in selected_items
                ),
            ),
            status,
            created_at,
        )
