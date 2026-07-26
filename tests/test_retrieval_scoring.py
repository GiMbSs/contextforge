"""Tests for CF-014 increment I036 inspectable scoring."""

from __future__ import annotations

import pytest

from contextforge.retrieval import (
    CandidateEligibility,
    CandidateOutcome,
    CandidateType,
    RetrievalCandidate,
    RetrievalEvidence,
    RetrievalScoringConfig,
    RetrievalScoringModel,
    ScoreComponent,
)


def candidate(
    identifier: str,
    *evidence: RetrievalEvidence,
    candidate_type: CandidateType = CandidateType.SOURCE_EXCERPT,
    eligibility: CandidateEligibility = CandidateEligibility.ELIGIBLE,
) -> RetrievalCandidate:
    return RetrievalCandidate(
        identifier,
        candidate_type,
        identifier,
        f"content:{identifier}",
        evidence,
        eligibility,
        CandidateOutcome.EXCLUDED,
        10,
    )


def evidence(kind: str, detail: str, weight: float) -> RetrievalEvidence:
    return RetrievalEvidence(kind, "test", detail, weight)


def test_score_exposes_every_canonical_component() -> None:
    result = RetrievalScoringModel().score(
        (
            candidate(
                "candidate_a",
                evidence("explicit-path-reference", "a.py", 1.0),
                evidence("lexical-text-match", "cache", 0.5),
            ),
        )
    )

    score = result.scores[0]
    assert tuple(item.component for item in score.components) == tuple(ScoreComponent)
    assert score.raw_score > 0
    assert score.normalized_score == 1.0


def test_independent_components_outscore_one_weak_signal() -> None:
    strong = candidate(
        "candidate_strong",
        evidence("lexical-text-match", "cache", 0.6),
        evidence("structural-definition", "Service", 0.6),
    )
    weak = candidate(
        "candidate_weak",
        evidence("lexical-text-match", "cache", 0.7),
    )

    result = RetrievalScoringModel().score((weak, strong))

    assert result.scores[0].candidate_id == "candidate_strong"


def test_duplicate_equivalent_evidence_does_not_inflate_score() -> None:
    item = evidence("lexical-text-match", "cache", 0.7)
    single = candidate("candidate_single", item)
    duplicate = candidate("candidate_duplicate", item, item)

    result = RetrievalScoringModel().score((single, duplicate))
    scores = {score.candidate_id: score.raw_score for score in result.scores}

    assert scores["candidate_single"] == scores["candidate_duplicate"]


def test_security_penalty_is_visible_and_subtracted() -> None:
    prohibited = candidate(
        "candidate_prohibited",
        evidence("lexical-text-match", "secret", 1.0),
        eligibility=CandidateEligibility.PROHIBITED,
    )

    score = RetrievalScoringModel().score((prohibited,)).scores[0]
    penalty = next(
        item for item in score.components if item.component is ScoreComponent.SENSITIVITY_PENALTY
    )

    assert penalty.value == 1.0
    assert penalty.weighted_value < 0


def test_equal_scores_use_candidate_identifier_as_stable_tie_breaker() -> None:
    first = candidate("candidate_b", evidence("lexical-text-match", "same", 0.5))
    second = candidate("candidate_a", evidence("lexical-text-match", "same", 0.5))

    result = RetrievalScoringModel().score((first, second))

    assert [score.candidate_id for score in result.scores] == [
        "candidate_a",
        "candidate_b",
    ]


def test_weight_configuration_requires_all_unique_non_negative_components() -> None:
    with pytest.raises(ValueError, match="every ScoreComponent"):
        RetrievalScoringConfig(())
    with pytest.raises(ValueError, match="finite non-negative"):
        RetrievalScoringConfig(
            tuple(
                (component, -1.0 if component is ScoreComponent.PATH_MATCH else 1.0)
                for component in ScoreComponent
            )
        )
