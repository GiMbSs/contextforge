"""Tests for CF-014 increment I040 Retrieval Result assembly."""

from __future__ import annotations

from datetime import UTC, datetime

from contextforge.diagnostics import DiagnosticCollection
from contextforge.domain import (
    ArtifactPath,
    ProjectFingerprint,
    new_artifact_id,
    new_index_id,
    new_inventory_id,
    new_project_id,
    new_retrieval_id,
    new_task_id,
)
from contextforge.domain.tasks import RequestedOutput, TaskKind, TaskSpecification
from contextforge.indexer import (
    IndexedArtifact,
    IndexingState,
    ProjectIndex,
    RelationshipKind,
)
from contextforge.retrieval import (
    ArtifactEligibilityRecord,
    BudgetSelectionResult,
    BudgetUsage,
    CandidateBudgetEstimate,
    CandidateEligibility,
    CandidateOutcome,
    CandidateType,
    ContextBudget,
    ContextBudgetReservation,
    DependencyTraversalPath,
    DependencyTraversalStep,
    RetrievalCandidate,
    RetrievalEvidence,
    RetrievalRequest,
    RetrievalResultAssembler,
    RetrievalScoringModel,
    RetrievalStatus,
    SelectionDecision,
    SelectionRationale,
    SelectionReason,
)

FINGERPRINT = ProjectFingerprint("project_sha256_" + "6" * 64)
NOW = datetime(2026, 7, 26, tzinfo=UTC)


def setup() -> tuple[RetrievalRequest, RetrievalCandidate]:
    artifact_id = new_artifact_id()
    artifact = IndexedArtifact(
        artifact_id,
        IndexingState.FULLY_INDEXED,
        "test",
        "1",
        FINGERPRINT,
        content_fingerprint="sha256:" + "a" * 64,
        path=ArtifactPath("service.py"),
    )
    index = ProjectIndex(
        new_index_id(),
        new_project_id(),
        new_inventory_id(),
        FINGERPRINT,
        "1",
        "test",
        (artifact,),
        NOW,
    )
    task = TaskSpecification(
        new_task_id(),
        "Explain Service",
        TaskKind.EXPLAIN,
        RequestedOutput.ANALYSIS,
    )
    evidence = (RetrievalEvidence("explicit-symbol-reference", "test", "Service", 1.0),)
    rationale = SelectionRationale(
        "candidate_service",
        SelectionDecision.SELECTED,
        SelectionReason.EXACT_SYMBOL_MATCH,
        evidence,
        score=1.0,
        rank=1,
    )
    candidate = RetrievalCandidate(
        "candidate_service",
        CandidateType.SYMBOL_DEFINITION,
        "Service",
        "symbol:service",
        evidence,
        CandidateEligibility.ELIGIBLE,
        CandidateOutcome.SELECTED,
        40,
        10,
        artifact_id,
        rationale=rationale,
    )
    return RetrievalRequest(task, index, ContextBudget(max_bytes=100)), candidate


def budget_result(candidate: RetrievalCandidate) -> BudgetSelectionResult:
    return BudgetSelectionResult(
        (candidate,),
        (candidate.candidate_id,),
        BudgetUsage(10, 30, 40, 1, 1, 1),
        ContextBudgetReservation(),
        DiagnosticCollection(),
        False,
    )


def test_selected_item_contains_complete_explainability_gate() -> None:
    request, candidate = setup()
    score_result = RetrievalScoringModel().score((candidate,))
    step = DependencyTraversalStep(
        "relationship_service",
        RelationshipKind.IMPLEMENTS,
        "implementation",
        "service",
        0.9,
    )
    path = DependencyTraversalPath("implementation", "service", (step,), 0.9)

    result = RetrievalResultAssembler().assemble(
        request,
        new_retrieval_id(),
        budget_result(candidate),
        score_result,
        NOW,
        strategy_versions=("test-strategy-v1",),
        estimates=(CandidateBudgetEstimate(candidate.candidate_id, 30),),
        eligibility_records=(ArtifactEligibilityRecord(candidate.artifact_id, sensitive=True),),
        dependency_paths=((candidate.candidate_id, path),),
    )

    item = result.selected_items[0]
    assert item.rationale.rank == 1
    assert len(item.score_breakdown) == 9
    assert item.artifact_id == candidate.artifact_id
    assert item.rationale.evidence == candidate.evidence
    assert (item.estimated_bytes, item.estimated_characters, item.estimated_tokens) == (
        40,
        30,
        10,
    )
    assert item.sensitivity_classification == "sensitive"
    assert item.dependency_path == ("relationship_service",)
    assert result.status is RetrievalStatus.COMPLETE


def test_result_statistics_and_versions_are_deterministic() -> None:
    request, candidate = setup()
    score_result = RetrievalScoringModel().score((candidate,))
    retrieval_id = new_retrieval_id()
    assembler = RetrievalResultAssembler()

    first = assembler.assemble(
        request,
        retrieval_id,
        budget_result(candidate),
        score_result,
        NOW,
        strategy_versions=("z-v1", "a-v1"),
    )
    second = assembler.assemble(
        request,
        retrieval_id,
        budget_result(candidate),
        score_result,
        NOW,
        strategy_versions=("z-v1", "a-v1"),
    )

    assert first == second
    assert first.strategy_versions == ("a-v1", "retrieval-result-v1", "z-v1")
    assert first.statistics.candidates_generated == 1
    assert first.statistics.symbols_selected == 1


def test_no_selected_context_is_incomplete_and_diagnostic() -> None:
    request, candidate = setup()
    excluded = RetrievalCandidate(
        candidate.candidate_id,
        candidate.candidate_type,
        candidate.source_reference,
        candidate.content_reference,
        candidate.evidence,
        CandidateEligibility.ELIGIBLE,
        CandidateOutcome.EXCLUDED,
        candidate.estimated_bytes,
        candidate.estimated_tokens,
        candidate.artifact_id,
    )
    budget = BudgetSelectionResult(
        (excluded,),
        (),
        BudgetUsage(),
        ContextBudgetReservation(),
        DiagnosticCollection(),
        False,
    )

    result = RetrievalResultAssembler().assemble(
        request,
        new_retrieval_id(),
        budget,
        RetrievalScoringModel().score((excluded,)),
        NOW,
        strategy_versions=("test-v1",),
    )

    assert result.status is RetrievalStatus.INCOMPLETE
    assert [str(item.code) for item in result.diagnostics] == ["RETRIEVAL_NO_RELEVANT_CONTEXT"]
