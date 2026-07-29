"""Optional aggregate regression thresholds for evaluation runs."""

from __future__ import annotations

import math
from dataclasses import dataclass

from contextforge.evaluation.reporting import aggregate_metrics
from contextforge.evaluation.runner import EvaluationExecutionResult


@dataclass(frozen=True, slots=True)
class MetricThreshold:
    """One inclusive aggregate bound for a primary-strategy metric."""

    metric_name: str
    minimum: float | None = None
    maximum: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.metric_name, str) or not self.metric_name.strip():
            raise ValueError("metric_name must be a non-empty string")
        if (self.minimum is None) == (self.maximum is None):
            raise ValueError("exactly one threshold bound must be provided")
        for field_name in ("minimum", "maximum"):
            value = getattr(self, field_name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{field_name} must be a finite number")
            if not math.isfinite(value):
                raise ValueError(f"{field_name} must be a finite number")
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{field_name} must be between zero and one")


@dataclass(frozen=True, slots=True)
class RegressionGateFailure:
    """One missing or out-of-bounds aggregate metric."""

    metric_name: str
    minimum: float | None
    maximum: float | None
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
    """Fail when a primary aggregate is absent or outside its inclusive bound."""
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
        RegressionGateFailure(
            threshold.metric_name,
            threshold.minimum,
            threshold.maximum,
            actual,
        )
        for threshold in sorted(normalized, key=lambda item: item.metric_name)
        if (actual := aggregates.get(threshold.metric_name)) is None
        or (threshold.minimum is not None and actual < threshold.minimum)
        or (threshold.maximum is not None and actual > threshold.maximum)
    )
    return RegressionGateResult(failures)
