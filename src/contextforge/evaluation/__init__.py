"""Public contracts for deterministic ContextForge evaluations."""

from contextforge.evaluation.baselines import (
    ALL_FILES_BASELINE_ID,
    EXPLICIT_BASELINE_ID,
    LEXICAL_BASELINE_ID,
    BaselineMetricDelta,
    BudgetedAllFilesBaseline,
    ExplicitOnlyBaseline,
    LexicalOnlyBaseline,
    calculate_baseline_deltas,
)
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
from contextforge.evaluation.ports import (
    ArtifactBudgetEstimate,
    EvaluationStrategy,
    EvaluationStrategyRequest,
)

__all__ = [
    "ALL_FILES_BASELINE_ID",
    "EXPLICIT_BASELINE_ID",
    "LEXICAL_BASELINE_ID",
    "ArtifactBudgetEstimate",
    "BaselineMetricDelta",
    "BudgetedAllFilesBaseline",
    "ContextEfficiencyResult",
    "EvaluationCase",
    "EvaluationRunResult",
    "EvaluationStrategy",
    "EvaluationStrategyRequest",
    "EvaluationSuite",
    "ExplicitOnlyBaseline",
    "LexicalOnlyBaseline",
    "MetricResult",
    "RelevanceJudgment",
    "RelevanceLevel",
    "StrategyResult",
    "StrategySelection",
    "artifact_recall",
    "calculate_baseline_deltas",
    "complete_evidence_rate",
    "evaluate_context_efficiency",
    "evaluate_retrieval_metrics",
    "has_complete_evidence",
    "normalized_discounted_cumulative_gain",
    "precision_over_judged",
    "recall_at_k",
    "reciprocal_rank",
]
