"""Optional aggregate regression thresholds for evaluation runs."""

from __future__ import annotations

import math
from dataclasses import dataclass

from contextforge.evaluation.reporting import aggregate_metrics
from contextforge.evaluation.runner import EvaluationExecutionResult


@dataclass(frozen=True, slots=True)
class MetricThreshold:
    """Minimum accepted primary-strategy aggregate for one metric."""

    metric_name: str
    minimum: float

    def __post_init__(self) -> None:
        if not isinstance(self.metric_name, str) or not self.metric_name.strip():
            raise ValueError("metric_name must be a non-empty string")
        if not isinstance(self.minimum, (int, float)) or not math.isfinite(self.minimum):
            raise ValueError("minimum must be a finite number")
        if not 0.0 <= self.minimum <= 1.0:
            raise ValueError("minimum must be between zero and one")


@dataclass(frozen=True, slots=True)
class RegressionGateFailure:
    """One missing or below-threshold aggregate metric."""

    metric_name: str
    minimum: float
    actual: float | None


@dataclass(frozen=True, slots=True)
class RegressionGateResult:
    """Deterministic outcome of applying requested thresholds."""

    failures: tuple[RegressionGateFailure, ...]

    @property
    def passed(self) -> bool:
        """Return whether every requested threshold passed."""
        return not self.failures


def evaluate_regression_gate(
    result: EvaluationExecutionResult,
    thresholds: tuple[MetricThreshold, ...],
    *,
    strategy_id: str = "contextforge",
) -> RegressionGateResult:
    """Fail when a primary aggregate is absent or below its threshold."""
    normalized = tuple(thresholds)
    names = tuple(item.metric_name for item in normalized)
    if len(set(names)) != len(names):
        raise ValueError("Threshold metric names must be unique")
    aggregates = {
        item.metric_name: item.mean
        for item in aggregate_metrics(result.run.metric_results)
        if item.strategy_id == strategy_id
    }
    failures = tuple(
        RegressionGateFailure(threshold.metric_name, threshold.minimum, actual)
        for threshold in sorted(normalized, key=lambda item: item.metric_name)
        if (actual := aggregates.get(threshold.metric_name)) is None or actual < threshold.minimum
    )
    return RegressionGateResult(failures)
