"""Deterministic retrieval and ranking metrics for judged artifacts."""

from __future__ import annotations

import math

from contextforge.domain import ArtifactPath
from contextforge.evaluation.models import (
    EvaluationCase,
    MetricResult,
    RelevanceJudgment,
    RelevanceLevel,
    StrategyResult,
    StrategySelection,
)

type JudgedRanking = tuple[tuple[RelevanceJudgment, ...], tuple[StrategySelection, ...]]

_RELEVANCE_GAIN = {
    RelevanceLevel.REQUIRED: 2,
    RelevanceLevel.SUPPORTING: 1,
    RelevanceLevel.IRRELEVANT: 0,
}


def _paths_at_level(
    judgments: tuple[RelevanceJudgment, ...],
    level: RelevanceLevel,
) -> frozenset[ArtifactPath]:
    return frozenset(item.path for item in judgments if item.relevance is level)


def _selected_paths(selections: tuple[StrategySelection, ...]) -> tuple[ArtifactPath, ...]:
    return tuple(item.path for item in selections)


def artifact_recall(
    judgments: tuple[RelevanceJudgment, ...],
    selections: tuple[StrategySelection, ...],
    level: RelevanceLevel,
) -> float:
    """Return recall for one relevance level; an empty gold set has recall 1."""
    if not isinstance(level, RelevanceLevel):
        raise TypeError("level must be a RelevanceLevel")
    relevant = _paths_at_level(judgments, level)
    if not relevant:
        return 1.0
    return len(relevant.intersection(_selected_paths(selections))) / len(relevant)


def precision_over_judged(
    judgments: tuple[RelevanceJudgment, ...],
    selections: tuple[StrategySelection, ...],
) -> float:
    """Measure relevant selections among judged selections.

    Unlabeled artifacts are neutral and excluded from the denominator. If no
    selected artifact is judged, precision is 1 because no judged false
    positive was selected.
    """
    relevance_by_path = {item.path: item.relevance for item in judgments}
    selected_judgments = tuple(
        relevance_by_path[path] for path in _selected_paths(selections) if path in relevance_by_path
    )
    if not selected_judgments:
        return 1.0
    relevant_count = sum(level is not RelevanceLevel.IRRELEVANT for level in selected_judgments)
    return relevant_count / len(selected_judgments)


def recall_at_k(
    judgments: tuple[RelevanceJudgment, ...],
    selections: tuple[StrategySelection, ...],
    k: int,
) -> float:
    """Return required-artifact recall in the first K ranked selections."""
    if type(k) is not int:
        raise TypeError("k must be an integer")
    if k < 1:
        raise ValueError("k must be positive")
    return artifact_recall(judgments, selections[:k], RelevanceLevel.REQUIRED)


def reciprocal_rank(
    judgments: tuple[RelevanceJudgment, ...],
    selections: tuple[StrategySelection, ...],
) -> float:
    """Return reciprocal rank of the first required artifact.

    Cases without required artifacts, and rankings containing no required
    artifact, return zero because there is no successful first hit.
    """
    required = _paths_at_level(judgments, RelevanceLevel.REQUIRED)
    for rank, path in enumerate(_selected_paths(selections), start=1):
        if path in required:
            return 1.0 / rank
    return 0.0


def normalized_discounted_cumulative_gain(
    judgments: tuple[RelevanceJudgment, ...],
    selections: tuple[StrategySelection, ...],
    k: int | None = None,
) -> float:
    """Return graded NDCG using required=2, supporting=1, and other=0."""
    if k is not None:
        if type(k) is not int:
            raise TypeError("k must be an integer or None")
        if k < 1:
            raise ValueError("k must be positive")
    limit = len(selections) if k is None else k
    relevance_by_path = {item.path: _RELEVANCE_GAIN[item.relevance] for item in judgments}
    actual_gains = tuple(
        relevance_by_path.get(path, 0) for path in _selected_paths(selections)[:limit]
    )
    ideal_gains = tuple(
        sorted(
            (gain for gain in relevance_by_path.values() if gain > 0),
            reverse=True,
        )[:limit]
    )
    if not ideal_gains:
        return 0.0

    def discounted_gain(gains: tuple[int, ...]) -> float:
        return math.fsum(
            ((2.0**gain) - 1.0) / math.log2(rank + 1) for rank, gain in enumerate(gains, start=1)
        )

    return discounted_gain(actual_gains) / discounted_gain(ideal_gains)


def has_complete_evidence(
    judgments: tuple[RelevanceJudgment, ...],
    selections: tuple[StrategySelection, ...],
) -> bool:
    """Return whether every required artifact is present."""
    required = _paths_at_level(judgments, RelevanceLevel.REQUIRED)
    return required <= frozenset(_selected_paths(selections))


def complete_evidence_rate(results: tuple[JudgedRanking, ...]) -> float:
    """Return the fraction of rankings that contain every required artifact.

    An empty collection has rate 1, matching the vacuous semantics used for
    required-artifact recall.
    """
    if not results:
        return 1.0
    complete = sum(
        has_complete_evidence(judgments, selections) for judgments, selections in results
    )
    return complete / len(results)


def evaluate_retrieval_metrics(
    case: EvaluationCase,
    result: StrategyResult,
    *,
    recall_ks: tuple[int, ...] = (1, 3, 5),
) -> tuple[MetricResult, ...]:
    """Calculate the standard E003 metric set for one case and strategy."""
    if not isinstance(case, EvaluationCase):
        raise TypeError("case must be an EvaluationCase")
    if not isinstance(result, StrategyResult):
        raise TypeError("result must be a StrategyResult")
    if result.case_id != case.case_id:
        raise ValueError("Strategy result must belong to the evaluation case")
    normalized_ks = tuple(recall_ks)
    if any(type(k) is not int for k in normalized_ks):
        raise TypeError("recall_ks must contain integers")
    if any(k < 1 for k in normalized_ks):
        raise ValueError("recall_ks must contain positive values")
    if len(set(normalized_ks)) != len(normalized_ks):
        raise ValueError("recall_ks must not contain duplicates")

    values = [
        (
            "required-artifact-recall",
            artifact_recall(case.judgments, result.selections, RelevanceLevel.REQUIRED),
        ),
        (
            "supporting-artifact-recall",
            artifact_recall(case.judgments, result.selections, RelevanceLevel.SUPPORTING),
        ),
        ("judged-precision", precision_over_judged(case.judgments, result.selections)),
        ("reciprocal-rank", reciprocal_rank(case.judgments, result.selections)),
        ("ndcg", normalized_discounted_cumulative_gain(case.judgments, result.selections)),
        (
            "complete-evidence",
            float(has_complete_evidence(case.judgments, result.selections)),
        ),
        *(
            (f"required-recall-at-{k}", recall_at_k(case.judgments, result.selections, k))
            for k in sorted(normalized_ks)
        ),
    ]
    return tuple(
        MetricResult(case.case_id, result.strategy_id, metric_name, value)
        for metric_name, value in values
    )
