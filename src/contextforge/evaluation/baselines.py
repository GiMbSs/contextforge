"""Deterministic baseline strategies for effectiveness comparison."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from contextforge.domain import ArtifactId, ArtifactPath, TaskId
from contextforge.domain.tasks import TaskSpecification
from contextforge.evaluation.models import MetricResult, StrategyResult, StrategySelection
from contextforge.evaluation.ports import EvaluationStrategyRequest
from contextforge.retrieval import (
    CandidateOutcome,
    ExplicitReferenceStrategy,
    LexicalSearchStrategy,
    TaskQueryNormalizer,
)

LEXICAL_BASELINE_ID = "baseline-lexical"
EXPLICIT_BASELINE_ID = "baseline-explicit"
ALL_FILES_BASELINE_ID = "baseline-all-files"


@dataclass(frozen=True, slots=True)
class BaselineMetricDelta:
    """One signed quality delta from a named baseline."""

    case_id: str
    metric_name: str
    primary_strategy_id: str
    baseline_strategy_id: str
    primary_value: float
    baseline_value: float
    delta: float

    def __post_init__(self) -> None:
        values = (self.primary_value, self.baseline_value, self.delta)
        if any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in values):
            raise ValueError("Metric delta values must be finite numbers")
        if self.delta != self.primary_value - self.baseline_value:
            raise ValueError("delta must equal primary_value minus baseline_value")


def calculate_baseline_deltas(
    primary: tuple[MetricResult, ...],
    baselines: tuple[MetricResult, ...],
) -> tuple[BaselineMetricDelta, ...]:
    """Compare primary metrics with every matching baseline metric."""
    primary_values: dict[tuple[str, str], MetricResult] = {}
    for metric in primary:
        key = (metric.case_id, metric.metric_name)
        if key in primary_values:
            raise ValueError("Primary metrics must be unique by case and metric name")
        primary_values[key] = metric

    deltas: list[BaselineMetricDelta] = []
    baseline_keys: set[tuple[str, str, str]] = set()
    for metric in baselines:
        key = (metric.case_id, metric.metric_name)
        identity = (metric.case_id, metric.strategy_id, metric.metric_name)
        if identity in baseline_keys:
            raise ValueError("Baseline metrics must be unique by case, strategy, and metric")
        baseline_keys.add(identity)
        primary_metric = primary_values.get(key)
        if primary_metric is None:
            raise ValueError("Every baseline metric must have a matching primary metric")
        deltas.append(
            BaselineMetricDelta(
                case_id=metric.case_id,
                metric_name=metric.metric_name,
                primary_strategy_id=primary_metric.strategy_id,
                baseline_strategy_id=metric.strategy_id,
                primary_value=primary_metric.value,
                baseline_value=metric.value,
                delta=primary_metric.value - metric.value,
            )
        )
    return tuple(
        sorted(
            deltas,
            key=lambda item: (
                item.case_id,
                item.baseline_strategy_id,
                item.metric_name,
            ),
        )
    )


def _task(request: EvaluationStrategyRequest) -> TaskSpecification:
    case = request.case
    digest = hashlib.sha256(f"{case.case_id}\0{case.fixture_fingerprint}".encode()).hexdigest()[:32]
    return TaskSpecification(
        TaskId(f"task_{digest}"),
        case.task_text,
        case.task_kind,
        case.requested_output,
    )


def _path_by_artifact(request: EvaluationStrategyRequest) -> dict[ArtifactId, ArtifactPath]:
    return {
        artifact.artifact_id: artifact.path
        for artifact in request.project_index.indexed_artifacts
        if artifact.path is not None
    }


def _apply_budget(
    request: EvaluationStrategyRequest,
    ranked: tuple[tuple[ArtifactPath, float | None], ...],
    strategy_id: str,
) -> StrategyResult:
    estimates = {item.path: item for item in request.artifact_estimates}
    budget = request.case.context_budget
    selected: list[StrategySelection] = []
    used_bytes = 0
    used_characters = 0
    used_tokens = 0

    for path, score in ranked:
        estimate = estimates[path]
        next_artifacts = len(selected) + 1
        exceeds = (
            (
                budget.max_estimated_tokens is not None
                and used_tokens + estimate.estimated_tokens > budget.max_estimated_tokens
            )
            or (
                budget.max_characters is not None
                and used_characters + estimate.character_count > budget.max_characters
            )
            or (
                budget.max_bytes is not None and used_bytes + estimate.byte_count > budget.max_bytes
            )
            or (budget.max_artifacts is not None and next_artifacts > budget.max_artifacts)
            or (budget.max_items is not None and next_artifacts > budget.max_items)
            or (budget.max_item_bytes is not None and estimate.byte_count > budget.max_item_bytes)
        )
        if exceeds:
            continue
        selected.append(StrategySelection(path, next_artifacts, score))
        used_bytes += estimate.byte_count
        used_characters += estimate.character_count
        used_tokens += estimate.estimated_tokens
    return StrategyResult(request.case.case_id, strategy_id, tuple(selected), 0.0)


def _deduplicate_ranked(
    ranked: tuple[tuple[ArtifactPath, float | None], ...],
) -> tuple[tuple[ArtifactPath, float | None], ...]:
    result: list[tuple[ArtifactPath, float | None]] = []
    seen: set[ArtifactPath] = set()
    for item in ranked:
        if item[0] not in seen:
            seen.add(item[0])
            result.append(item)
    return tuple(result)


@dataclass(frozen=True, slots=True)
class LexicalOnlyBaseline:
    """Rank artifact paths using only task-text lexical matches."""

    strategy_id: str = LEXICAL_BASELINE_ID

    def evaluate(self, request: EvaluationStrategyRequest) -> StrategyResult:
        if not isinstance(request, EvaluationStrategyRequest):
            raise TypeError("request must be an EvaluationStrategyRequest")
        query = TaskQueryNormalizer().normalize(_task(request))
        result = LexicalSearchStrategy().search(query, request.project_index)
        paths = _path_by_artifact(request)
        ranked = _deduplicate_ranked(
            tuple(
                (paths[candidate.artifact_id], candidate.rationale.score)
                for candidate in result.candidates
                if candidate.artifact_id in paths and candidate.rationale is not None
            )
        )
        return _apply_budget(request, ranked, self.strategy_id)


@dataclass(frozen=True, slots=True)
class ExplicitOnlyBaseline:
    """Select only artifact paths named directly by path, filename, or symbol."""

    strategy_id: str = EXPLICIT_BASELINE_ID

    def evaluate(self, request: EvaluationStrategyRequest) -> StrategyResult:
        if not isinstance(request, EvaluationStrategyRequest):
            raise TypeError("request must be an EvaluationStrategyRequest")
        query = TaskQueryNormalizer().normalize(_task(request))
        result = ExplicitReferenceStrategy().resolve(query, request.project_index)
        paths = _path_by_artifact(request)
        ranked = _deduplicate_ranked(
            tuple(
                (
                    paths[candidate.artifact_id],
                    candidate.rationale.score if candidate.rationale is not None else None,
                )
                for candidate in result.candidates
                if candidate.outcome is CandidateOutcome.SELECTED and candidate.artifact_id in paths
            )
        )
        return _apply_budget(request, ranked, self.strategy_id)


@dataclass(frozen=True, slots=True)
class BudgetedAllFilesBaseline:
    """Select every indexed artifact in path order until the common budget is full."""

    strategy_id: str = ALL_FILES_BASELINE_ID

    def evaluate(self, request: EvaluationStrategyRequest) -> StrategyResult:
        if not isinstance(request, EvaluationStrategyRequest):
            raise TypeError("request must be an EvaluationStrategyRequest")
        ranked = tuple((item.path, None) for item in request.artifact_estimates)
        return _apply_budget(request, ranked, self.strategy_id)
