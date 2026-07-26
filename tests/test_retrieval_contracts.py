"""Tests for CF-014 increment I030 Context Retriever contracts."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from contextforge.diagnostics import DiagnosticCollection
from contextforge.domain import (
    new_index_id,
    new_inventory_id,
    new_project_id,
    new_retrieval_id,
    new_task_id,
)
from contextforge.domain.fingerprints import FingerprintOrdering, fingerprint_project
from contextforge.domain.tasks import RequestedOutput, TaskKind, TaskSpecification
from contextforge.indexer import ProjectIndex
from contextforge.retrieval import (
    CandidateEligibility,
    CandidateOutcome,
    CandidateType,
    ContextBudget,
    ContextRetriever,
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

NOW = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)


def make_task() -> TaskSpecification:
    return TaskSpecification(
        new_task_id(),
        "Explain main.py and keep the context small.",
        TaskKind.EXPLAIN,
        RequestedOutput.ANALYSIS,
    )


def make_index() -> ProjectIndex:
    project_fingerprint = fingerprint_project(
        ("state",),
        ordering=FingerprintOrdering.ORDERED,
    )
    return ProjectIndex(
        new_index_id(),
        new_project_id(),
        new_inventory_id(),
        project_fingerprint,
        "1",
        "indexer-v1",
        (),
        NOW,
    )


def evidence(detail: str) -> RetrievalEvidence:
    return RetrievalEvidence("contract-test", "fake-retriever", detail, 1.0)


def rationale(
    candidate_id: str,
    decision: SelectionDecision,
    reason: SelectionReason,
) -> SelectionRationale:
    return SelectionRationale(
        candidate_id,
        decision,
        reason,
        (evidence(reason.value),),
    )


class FakeRetriever:
    """Contract double with selected, excluded, deferred, and truncated output."""

    def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        selected_rationale = rationale(
            "candidate_selected",
            SelectionDecision.SELECTED,
            SelectionReason.EXACT_PATH_MATCH,
        )
        excluded_rationale = rationale(
            "candidate_excluded",
            SelectionDecision.EXCLUDED,
            SelectionReason.CONTEXT_BUDGET_EXCEEDED,
        )
        deferred_rationale = rationale(
            "candidate_deferred",
            SelectionDecision.DEFERRED,
            SelectionReason.DEFERRED_AMBIGUITY,
        )
        truncated_rationale = rationale(
            "candidate_truncated",
            SelectionDecision.SELECTED,
            SelectionReason.REQUIRED_CONTEXT,
        )
        candidates = (
            RetrievalCandidate(
                "candidate_selected",
                CandidateType.FULL_ARTIFACT,
                "main.py",
                "artifact:main.py",
                selected_rationale.evidence,
                CandidateEligibility.ELIGIBLE,
                CandidateOutcome.SELECTED,
                100,
                25,
                rationale=selected_rationale,
            ),
            RetrievalCandidate(
                "candidate_excluded",
                CandidateType.DOCUMENTATION_SECTION,
                "README.md",
                "search:readme",
                excluded_rationale.evidence,
                CandidateEligibility.ELIGIBLE,
                CandidateOutcome.EXCLUDED,
                400,
                100,
                rationale=excluded_rationale,
            ),
            RetrievalCandidate(
                "candidate_deferred",
                CandidateType.SYMBOL_DEFINITION,
                "ambiguous:run",
                "symbol:run",
                deferred_rationale.evidence,
                CandidateEligibility.ELIGIBLE,
                CandidateOutcome.DEFERRED,
                80,
                20,
                rationale=deferred_rationale,
            ),
            RetrievalCandidate(
                "candidate_truncated",
                CandidateType.SOURCE_EXCERPT,
                "large.py",
                "search:large",
                truncated_rationale.evidence,
                CandidateEligibility.ELIGIBLE,
                CandidateOutcome.TRUNCATED,
                800,
                200,
                rationale=truncated_rationale,
            ),
        )
        selected_items = (
            SelectedContextItem(
                "context_item_selected",
                "candidate_selected",
                None,
                "artifact:main.py",
                CandidateType.FULL_ARTIFACT,
                selected_rationale,
                estimated_tokens=25,
            ),
            SelectedContextItem(
                "context_item_truncated",
                "candidate_truncated",
                None,
                "search:large:partial",
                CandidateType.SOURCE_EXCERPT,
                truncated_rationale,
                estimated_tokens=50,
                is_truncated=True,
            ),
        )
        return RetrievalResult(
            new_retrieval_id(),
            request.task.task_id,
            request.project_index.index_id,
            request.project_index.project_fingerprint,
            ("fake-retrieval-v1",),
            candidates,
            selected_items,
            (
                selected_rationale,
                excluded_rationale,
                deferred_rationale,
                truncated_rationale,
            ),
            request.budget,
            DiagnosticCollection(),
            RetrievalStatistics(
                candidates_generated=4,
                candidates_evaluated=4,
                artifacts_selected=1,
                excerpts_selected=1,
                candidates_budget_excluded=1,
                estimated_selected_tokens=75,
            ),
            RetrievalStatus.COMPLETE_WITH_WARNINGS,
            NOW,
        )


def test_fake_retriever_represents_every_required_candidate_disposition() -> None:
    request = RetrievalRequest(
        make_task(),
        make_index(),
        ContextBudget(max_estimated_tokens=100, max_artifacts=2),
    )
    retriever: ContextRetriever = FakeRetriever()

    result = retriever.retrieve(request)

    assert {candidate.outcome for candidate in result.candidates} == {
        CandidateOutcome.SELECTED,
        CandidateOutcome.EXCLUDED,
        CandidateOutcome.DEFERRED,
        CandidateOutcome.TRUNCATED,
    }
    assert len(result.selected_items) == 2
    assert result.selected_items[1].is_truncated
    assert all(candidate.rationale is not None for candidate in result.candidates)


def test_retrieval_contracts_are_immutable() -> None:
    result = FakeRetriever().retrieve(
        RetrievalRequest(make_task(), make_index(), ContextBudget(max_bytes=1_000))
    )

    with pytest.raises(FrozenInstanceError):
        result.status = RetrievalStatus.FAILED  # type: ignore[misc]


def test_result_rejects_selected_item_without_selected_candidate() -> None:
    request = RetrievalRequest(make_task(), make_index(), ContextBudget(max_bytes=1_000))
    valid = FakeRetriever().retrieve(request)

    with pytest.raises(ValueError, match="Selected items"):
        RetrievalResult(
            valid.retrieval_id,
            valid.task_id,
            valid.index_id,
            valid.project_fingerprint,
            valid.strategy_versions,
            valid.candidates,
            (),
            valid.rationales,
            valid.applied_budget,
            valid.diagnostics,
            valid.statistics,
            valid.status,
            valid.created_at,
        )


def test_budget_rejects_zero_or_negative_limits() -> None:
    with pytest.raises(ValueError, match="positive"):
        ContextBudget(max_bytes=0)
    with pytest.raises(ValueError, match="positive"):
        ContextBudget(max_estimated_tokens=-1)
