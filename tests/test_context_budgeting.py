"""Tests for CF-014 increment I038 hard context budgeting."""

from __future__ import annotations

from contextforge.retrieval import (
    BudgetUsage,
    CandidateBudgetEstimate,
    CandidateEligibility,
    CandidateOutcome,
    CandidateScore,
    CandidateType,
    ContextBudget,
    ContextBudgetPlanner,
    ContextBudgetReservation,
    RetrievalCandidate,
    RetrievalEvidence,
    ScoreComponent,
    ScoreContribution,
)


def candidate(
    identifier: str,
    size: int,
    *,
    tokens: int,
    eligibility: CandidateEligibility = CandidateEligibility.ELIGIBLE,
    candidate_type: CandidateType = CandidateType.FULL_ARTIFACT,
) -> RetrievalCandidate:
    return RetrievalCandidate(
        identifier,
        candidate_type,
        identifier,
        f"content:{identifier}",
        (RetrievalEvidence("test", "test", "match", 1.0),),
        eligibility,
        CandidateOutcome.SELECTED
        if eligibility is CandidateEligibility.ELIGIBLE
        else CandidateOutcome.EXCLUDED,
        size,
        tokens,
    )


def score(identifier: str, value: float, rank: int) -> CandidateScore:
    return CandidateScore(
        identifier,
        tuple(ScoreContribution(component, 0.0, 1.0, 0.0, 0) for component in ScoreComponent),
        value,
        value,
        rank,
    )


def test_selects_highest_value_candidates_within_all_size_limits() -> None:
    high = candidate("candidate_high", 40, tokens=10)
    low = candidate("candidate_low", 40, tokens=10)

    result = ContextBudgetPlanner().select(
        (low, high),
        (score("candidate_high", 1.0, 1), score("candidate_low", 0.5, 2)),
        ContextBudget(max_bytes=50, max_characters=50, max_estimated_tokens=15),
        estimates=(
            CandidateBudgetEstimate("candidate_high", 30),
            CandidateBudgetEstimate("candidate_low", 30),
        ),
    )

    assert result.selected_candidate_ids == ("candidate_high",)
    assert result.candidates[0].outcome is CandidateOutcome.EXCLUDED
    assert result.candidates[1].outcome is CandidateOutcome.SELECTED
    assert result.usage == BudgetUsage(10, 30, 40, 1, 0, 0)


def test_reservation_reduces_available_capacity() -> None:
    item = candidate("candidate_item", 40, tokens=10)

    result = ContextBudgetPlanner().select(
        (item,),
        (score(item.candidate_id, 1.0, 1),),
        ContextBudget(max_bytes=50, max_characters=50, max_estimated_tokens=15),
        ContextBudgetReservation(estimated_tokens=6, characters=11, bytes=11),
        (CandidateBudgetEstimate(item.candidate_id, 40),),
    )

    assert result.selected_candidate_ids == ()
    assert result.candidates[0].outcome is CandidateOutcome.EXCLUDED


def test_reservation_overflow_is_reported_even_without_candidates() -> None:
    result = ContextBudgetPlanner().select(
        (),
        (),
        ContextBudget(max_bytes=10),
        ContextBudgetReservation(bytes=11),
    )

    assert [str(item.code) for item in result.diagnostics] == ["RETRIEVAL_BUDGET_EXCEEDED"]


def test_mandatory_candidate_is_considered_before_higher_scored_optional() -> None:
    mandatory = candidate("candidate_mandatory", 40, tokens=10)
    optional = candidate("candidate_optional", 40, tokens=10)

    result = ContextBudgetPlanner().select(
        (optional, mandatory),
        (score(optional.candidate_id, 1.0, 1), score(mandatory.candidate_id, 0.2, 2)),
        ContextBudget(max_bytes=40),
        mandatory_candidate_ids=(mandatory.candidate_id,),
    )

    assert result.selected_candidate_ids == (mandatory.candidate_id,)


def test_mandatory_overflow_is_reported_without_exceeding_budget() -> None:
    mandatory = candidate("candidate_mandatory", 60, tokens=10)

    result = ContextBudgetPlanner().select(
        (mandatory,),
        (score(mandatory.candidate_id, 1.0, 1),),
        ContextBudget(max_bytes=50),
        mandatory_candidate_ids=(mandatory.candidate_id,),
    )

    assert result.usage.bytes == 0
    assert result.mandatory_overflow
    assert [str(item.code) for item in result.diagnostics] == ["RETRIEVAL_BUDGET_EXCEEDED"]


def test_item_artifact_excerpt_and_individual_limits_are_strict() -> None:
    first = candidate(
        "candidate_first",
        10,
        tokens=1,
        candidate_type=CandidateType.SOURCE_EXCERPT,
    )
    second = candidate(
        "candidate_second",
        20,
        tokens=1,
        candidate_type=CandidateType.SOURCE_EXCERPT,
    )

    result = ContextBudgetPlanner().select(
        (first, second),
        (score(first.candidate_id, 1.0, 1), score(second.candidate_id, 0.5, 2)),
        ContextBudget(max_items=1, max_excerpts=1, max_item_bytes=15),
    )

    assert result.selected_candidate_ids == (first.candidate_id,)
    assert result.usage.items == 1
    assert result.usage.excerpts == 1


def test_ineligible_and_deferred_candidates_are_never_selected() -> None:
    prohibited = candidate(
        "candidate_prohibited",
        1,
        tokens=1,
        eligibility=CandidateEligibility.PROHIBITED,
    )
    deferred = candidate("candidate_deferred", 1, tokens=1)
    deferred = RetrievalCandidate(
        deferred.candidate_id,
        deferred.candidate_type,
        deferred.source_reference,
        deferred.content_reference,
        deferred.evidence,
        deferred.eligibility,
        CandidateOutcome.DEFERRED,
        deferred.estimated_bytes,
        deferred.estimated_tokens,
    )

    result = ContextBudgetPlanner().select(
        (prohibited, deferred),
        (score(prohibited.candidate_id, 1.0, 1), score(deferred.candidate_id, 0.9, 2)),
        ContextBudget(max_items=2),
    )

    assert result.selected_candidate_ids == ()
