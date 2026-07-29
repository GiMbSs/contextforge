"""Table-driven tests for CF-015-E003 retrieval and ranking metrics."""

from __future__ import annotations

import math

import pytest

from contextforge.domain import ArtifactPath
from contextforge.domain.fingerprints import FingerprintOrdering, fingerprint_project
from contextforge.domain.tasks import RequestedOutput, TaskKind
from contextforge.evaluation import (
    EvaluationCase,
    RelevanceJudgment,
    RelevanceLevel,
    StrategyResult,
    StrategySelection,
    artifact_recall,
    complete_evidence_rate,
    evaluate_retrieval_metrics,
    has_complete_evidence,
    normalized_discounted_cumulative_gain,
    precision_over_judged,
    recall_at_k,
    reciprocal_rank,
)
from contextforge.retrieval import ContextBudget

REQUIRED = RelevanceJudgment(ArtifactPath("required.py"), RelevanceLevel.REQUIRED)
REQUIRED_TWO = RelevanceJudgment(ArtifactPath("required_two.py"), RelevanceLevel.REQUIRED)
SUPPORTING = RelevanceJudgment(ArtifactPath("supporting.py"), RelevanceLevel.SUPPORTING)
IRRELEVANT = RelevanceJudgment(ArtifactPath("irrelevant.py"), RelevanceLevel.IRRELEVANT)
JUDGMENTS = (REQUIRED, REQUIRED_TWO, SUPPORTING, IRRELEVANT)


def selections(*paths: str) -> tuple[StrategySelection, ...]:
    return tuple(
        StrategySelection(ArtifactPath(path), rank) for rank, path in enumerate(paths, start=1)
    )


@pytest.mark.parametrize(
    ("ranked", "level", "expected"),
    [
        (selections("required.py", "required_two.py"), RelevanceLevel.REQUIRED, 1.0),
        (selections("required.py"), RelevanceLevel.REQUIRED, 0.5),
        ((), RelevanceLevel.REQUIRED, 0.0),
        (selections("supporting.py"), RelevanceLevel.SUPPORTING, 1.0),
        ((), RelevanceLevel.IRRELEVANT, 0.0),
    ],
)
def test_artifact_recall_is_bounded_and_deterministic(
    ranked: tuple[StrategySelection, ...],
    level: RelevanceLevel,
    expected: float,
) -> None:
    assert artifact_recall(JUDGMENTS, ranked, level) == expected


def test_recall_of_an_empty_gold_level_is_vacuously_complete() -> None:
    assert artifact_recall((REQUIRED,), (), RelevanceLevel.SUPPORTING) == 1.0
    assert recall_at_k((SUPPORTING,), (), 1) == 1.0


@pytest.mark.parametrize(
    ("ranked", "expected"),
    [
        ((), 1.0),
        (selections("neutral.py"), 1.0),
        (selections("required.py", "neutral.py"), 1.0),
        (selections("required.py", "irrelevant.py"), 0.5),
        (selections("irrelevant.py"), 0.0),
    ],
)
def test_precision_ignores_unlabeled_artifacts(
    ranked: tuple[StrategySelection, ...],
    expected: float,
) -> None:
    assert precision_over_judged(JUDGMENTS, ranked) == expected


def test_recall_at_k_uses_only_the_ranked_prefix() -> None:
    ranked = selections("neutral.py", "required.py", "required_two.py")

    assert recall_at_k(JUDGMENTS, ranked, 1) == 0.0
    assert recall_at_k(JUDGMENTS, ranked, 2) == 0.5
    assert recall_at_k(JUDGMENTS, ranked, 3) == 1.0


@pytest.mark.parametrize(
    ("ranked", "expected"),
    [
        (selections("required.py"), 1.0),
        (selections("neutral.py", "required.py"), 0.5),
        (selections("neutral.py"), 0.0),
        ((), 0.0),
    ],
)
def test_reciprocal_rank_finds_the_first_required_artifact(
    ranked: tuple[StrategySelection, ...],
    expected: float,
) -> None:
    assert reciprocal_rank(JUDGMENTS, ranked) == expected


def test_reciprocal_rank_without_required_gold_is_zero() -> None:
    assert reciprocal_rank((SUPPORTING,), selections("supporting.py")) == 0.0


@pytest.mark.parametrize(
    ("ranked", "expected"),
    [
        (selections("required.py", "supporting.py"), 1.0),
        (selections("supporting.py", "required.py"), None),
        (selections("irrelevant.py"), 0.0),
        ((), 0.0),
    ],
)
def test_ndcg_uses_graded_relevance(
    ranked: tuple[StrategySelection, ...],
    expected: float | None,
) -> None:
    judgments = (REQUIRED, SUPPORTING, IRRELEVANT)
    actual = normalized_discounted_cumulative_gain(judgments, ranked)

    if expected is None:
        ideal = 3 / math.log2(2) + 1 / math.log2(3)
        reversed_order = 1 / math.log2(2) + 3 / math.log2(3)
        assert actual == pytest.approx(reversed_order / ideal)
    else:
        assert actual == expected


def test_ndcg_without_positive_gold_is_zero() -> None:
    assert normalized_discounted_cumulative_gain((IRRELEVANT,), ()) == 0.0


def test_complete_evidence_and_aggregate_rate_have_explicit_empty_semantics() -> None:
    complete = selections("required.py", "required_two.py")
    partial = selections("required.py")

    assert has_complete_evidence(JUDGMENTS, complete)
    assert not has_complete_evidence(JUDGMENTS, partial)
    assert complete_evidence_rate(((JUDGMENTS, complete), (JUDGMENTS, partial))) == 0.5
    assert complete_evidence_rate(()) == 1.0


def make_case() -> EvaluationCase:
    return EvaluationCase(
        "ranking",
        "fixture",
        fingerprint_project(("fixture",), ordering=FingerprintOrdering.ORDERED),
        "Find required files.",
        TaskKind.ANALYZE,
        RequestedOutput.ANALYSIS,
        JUDGMENTS,
        ContextBudget(max_artifacts=4),
    )


def test_evaluate_retrieval_metrics_returns_stable_named_results() -> None:
    case = make_case()
    result = StrategyResult(
        "ranking",
        "lexical",
        selections("required.py", "supporting.py", "irrelevant.py"),
        0.0,
    )

    metrics = evaluate_retrieval_metrics(case, result, recall_ks=(3, 1))

    assert tuple(metric.metric_name for metric in metrics) == (
        "required-artifact-recall",
        "supporting-artifact-recall",
        "judged-precision",
        "reciprocal-rank",
        "ndcg",
        "complete-evidence",
        "required-recall-at-1",
        "required-recall-at-3",
    )
    assert all(0.0 <= metric.value <= 1.0 for metric in metrics)


def test_metric_evaluation_rejects_mismatched_cases_and_invalid_k() -> None:
    case = make_case()
    other = StrategyResult("other", "lexical", (), 0.0)

    with pytest.raises(ValueError, match="belong"):
        evaluate_retrieval_metrics(case, other)
    with pytest.raises(ValueError, match="positive"):
        evaluate_retrieval_metrics(
            case,
            StrategyResult("ranking", "lexical", (), 0.0),
            recall_ks=(0,),
        )
