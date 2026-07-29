"""Public contracts for deterministic ContextForge evaluations."""

from contextforge.evaluation.context_metrics import (
    ContextEfficiencyResult,
    evaluate_context_efficiency,
)
from contextforge.evaluation.metrics import (
    artifact_recall,
    complete_evidence_rate,
    evaluate_retrieval_metrics,
    has_complete_evidence,
    normalized_discounted_cumulative_gain,
    precision_over_judged,
    recall_at_k,
    reciprocal_rank,
)
from contextforge.evaluation.models import (
    EvaluationCase,
    EvaluationRunResult,
    EvaluationSuite,
    MetricResult,
    RelevanceJudgment,
    RelevanceLevel,
    StrategyResult,
    StrategySelection,
)

__all__ = [
    "ContextEfficiencyResult",
    "EvaluationCase",
    "EvaluationRunResult",
    "EvaluationSuite",
    "MetricResult",
    "RelevanceJudgment",
    "RelevanceLevel",
    "StrategyResult",
    "StrategySelection",
    "artifact_recall",
    "complete_evidence_rate",
    "evaluate_context_efficiency",
    "evaluate_retrieval_metrics",
    "has_complete_evidence",
    "normalized_discounted_cumulative_gain",
    "precision_over_judged",
    "recall_at_k",
    "reciprocal_rank",
]
