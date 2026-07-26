"""Tests for CF-014 increment I039 dependency closure policy."""

from __future__ import annotations

from contextforge.diagnostics import DiagnosticCollection
from contextforge.indexer import RelationshipKind
from contextforge.retrieval import (
    CandidateBudgetEstimate,
    CandidateEligibility,
    CandidateOutcome,
    CandidateType,
    ContextBudget,
    DependencyClosureConfig,
    DependencyClosurePolicy,
    DependencyTraversalPath,
    DependencyTraversalResult,
    DependencyTraversalStep,
    RetrievalCandidate,
    RetrievalEvidence,
)


def candidate(
    identifier: str,
    *,
    eligibility: CandidateEligibility = CandidateEligibility.ELIGIBLE,
    size: int = 10,
) -> RetrievalCandidate:
    return RetrievalCandidate(
        identifier,
        CandidateType.SYMBOL_DEFINITION,
        identifier,
        f"symbol:{identifier}",
        (RetrievalEvidence("test", "test", "match", 1.0),),
        eligibility,
        CandidateOutcome.SELECTED
        if eligibility is CandidateEligibility.ELIGIBLE
        else CandidateOutcome.EXCLUDED,
        size,
        2,
    )


def traversal(
    primary: RetrievalCandidate,
    support: RetrievalCandidate,
    kind: RelationshipKind = RelationshipKind.IMPLEMENTS,
) -> DependencyTraversalResult:
    step = DependencyTraversalStep(
        "relationship_support",
        kind,
        primary.candidate_id,
        support.candidate_id,
        0.9,
    )
    path = DependencyTraversalPath(
        primary.candidate_id,
        support.candidate_id,
        (step,),
        0.9,
    )
    return DependencyTraversalResult(
        (support,),
        (path,),
        DiagnosticCollection(),
    )


def test_closure_adds_interface_with_explicit_required_by_rationale() -> None:
    primary = candidate("candidate_implementation")
    support = candidate("candidate_interface")

    result = DependencyClosurePolicy().apply(
        (primary,),
        traversal(primary, support),
        ContextBudget(max_bytes=100),
    )

    assert result.budget_result.selected_candidate_ids == (
        primary.candidate_id,
        support.candidate_id,
    )
    assert result.additions[0].primary_candidate_id == primary.candidate_id
    added = result.budget_result.candidates[1]
    assert "required_by=candidate_implementation" in added.evidence[-1].detail
    assert not result.incomplete


def test_configuration_relationship_can_enter_closure() -> None:
    primary = candidate("candidate_module")
    support = candidate("candidate_configuration")

    result = DependencyClosurePolicy().apply(
        (primary,),
        traversal(primary, support, RelationshipKind.CONFIGURES),
        ContextBudget(max_bytes=100),
    )

    assert result.additions[0].supporting_candidate_id == support.candidate_id


def test_security_ineligible_support_is_not_added_and_marks_incomplete() -> None:
    primary = candidate("candidate_primary")
    support = candidate(
        "candidate_sensitive",
        eligibility=CandidateEligibility.PROHIBITED,
    )

    result = DependencyClosurePolicy().apply(
        (primary,),
        traversal(primary, support),
        ContextBudget(max_bytes=100),
    )

    assert result.additions == ()
    assert result.incomplete
    assert "RETRIEVAL_INSUFFICIENT_CONTEXT" in {str(item.code) for item in result.diagnostics}


def test_required_support_budget_overflow_marks_context_incomplete() -> None:
    primary = candidate("candidate_primary", size=10)
    support = candidate("candidate_support", size=20)

    result = DependencyClosurePolicy().apply(
        (primary,),
        traversal(primary, support),
        ContextBudget(max_bytes=15),
    )

    assert result.budget_result.selected_candidate_ids == (primary.candidate_id,)
    assert result.incomplete
    assert "RETRIEVAL_BUDGET_EXCEEDED" in {str(item.code) for item in result.diagnostics}


def test_closure_additions_are_bounded_and_deterministic() -> None:
    primary = candidate("candidate_primary")
    first = candidate("candidate_a")
    second = candidate("candidate_b")
    first_result = traversal(primary, first)
    second_result = traversal(primary, second)
    combined = DependencyTraversalResult(
        (*first_result.candidates, *second_result.candidates),
        (*first_result.paths, *second_result.paths),
        DiagnosticCollection(),
    )
    policy = DependencyClosurePolicy(DependencyClosureConfig(max_additions=1))

    one = policy.apply((primary,), combined, ContextBudget(max_bytes=100))
    two = policy.apply((primary,), combined, ContextBudget(max_bytes=100))

    assert one == two
    assert len(one.additions) == 1
    assert one.incomplete


def test_character_estimates_are_forwarded_to_budget_planner() -> None:
    primary = candidate("candidate_primary")
    support = candidate("candidate_support")

    result = DependencyClosurePolicy().apply(
        (primary,),
        traversal(primary, support),
        ContextBudget(max_characters=15),
        estimates=(
            CandidateBudgetEstimate(primary.candidate_id, 10),
            CandidateBudgetEstimate(support.candidate_id, 10),
        ),
    )

    assert result.incomplete
    assert result.budget_result.usage.characters == 10
