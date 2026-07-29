"""Immutable, behavior-free contracts for effectiveness evaluation."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from contextforge.domain import ArtifactPath, ProjectFingerprint
from contextforge.domain.tasks import RequestedOutput, TaskKind
from contextforge.retrieval import ContextBudget

_IDENTIFIER = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*")


def _require_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase canonical identifier")


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _unique_sorted_text(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    normalized = tuple(values)
    for value in normalized:
        _require_text(value, field_name)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must not contain duplicates")
    return tuple(sorted(normalized))


def _format_datetime(value: datetime) -> str:
    if not isinstance(value, datetime):
        raise TypeError("created_at must be a datetime")
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("created_at must use UTC")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class RelevanceLevel(StrEnum):
    """Gold relevance assigned to one judged artifact."""

    REQUIRED = "required"
    SUPPORTING = "supporting"
    IRRELEVANT = "irrelevant"


@dataclass(frozen=True, slots=True)
class RelevanceJudgment:
    """One gold artifact judgment, optionally narrowed to named symbols."""

    path: ArtifactPath
    relevance: RelevanceLevel
    symbols: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.path, ArtifactPath):
            raise TypeError("path must be an ArtifactPath")
        if not isinstance(self.relevance, RelevanceLevel):
            raise TypeError("relevance must be a RelevanceLevel")
        object.__setattr__(self, "symbols", _unique_sorted_text(self.symbols, "symbols"))

    def to_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "relevance": self.relevance.value,
            "symbols": list(self.symbols),
        }


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    """A deterministic task and its versioned gold data."""

    case_id: str
    fixture_project_id: str
    fixture_fingerprint: ProjectFingerprint
    task_text: str
    task_kind: TaskKind
    requested_output: RequestedOutput
    judgments: tuple[RelevanceJudgment, ...]
    context_budget: ContextBudget
    tags: tuple[str, ...] = ()
    expected_evidence: tuple[str, ...] = ()
    expected_changed_paths: tuple[ArtifactPath, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier(self.case_id, "case_id")
        _require_identifier(self.fixture_project_id, "fixture_project_id")
        if not isinstance(self.fixture_fingerprint, ProjectFingerprint):
            raise TypeError("fixture_fingerprint must be a ProjectFingerprint")
        _require_text(self.task_text, "task_text")
        if not isinstance(self.task_kind, TaskKind):
            raise TypeError("task_kind must be a TaskKind")
        if not isinstance(self.requested_output, RequestedOutput):
            raise TypeError("requested_output must be a RequestedOutput")
        if not isinstance(self.context_budget, ContextBudget):
            raise TypeError("context_budget must be a ContextBudget")

        judgments = tuple(self.judgments)
        if any(not isinstance(item, RelevanceJudgment) for item in judgments):
            raise TypeError("judgments must contain RelevanceJudgment values")
        paths = tuple(item.path for item in judgments)
        if len(set(paths)) != len(paths):
            raise ValueError("An artifact path cannot have duplicate or contradictory judgments")

        changed_paths = tuple(self.expected_changed_paths)
        if any(not isinstance(path, ArtifactPath) for path in changed_paths):
            raise TypeError("expected_changed_paths must contain ArtifactPath values")
        if len(set(changed_paths)) != len(changed_paths):
            raise ValueError("expected_changed_paths must not contain duplicates")

        object.__setattr__(self, "judgments", tuple(sorted(judgments, key=lambda item: item.path)))
        object.__setattr__(self, "tags", _unique_sorted_text(self.tags, "tags"))
        object.__setattr__(
            self,
            "expected_evidence",
            _unique_sorted_text(self.expected_evidence, "expected_evidence"),
        )
        object.__setattr__(self, "expected_changed_paths", tuple(sorted(changed_paths)))

    def to_dict(self) -> dict[str, object]:
        budget = {
            name: getattr(self.context_budget, name)
            for name in self.context_budget.__dataclass_fields__
        }
        return {
            "case_id": self.case_id,
            "context_budget": budget,
            "expected_changed_paths": [str(path) for path in self.expected_changed_paths],
            "expected_evidence": list(self.expected_evidence),
            "fixture_fingerprint": str(self.fixture_fingerprint),
            "fixture_project_id": self.fixture_project_id,
            "judgments": [item.to_dict() for item in self.judgments],
            "requested_output": self.requested_output.value,
            "tags": list(self.tags),
            "task_kind": self.task_kind.value,
            "task_text": self.task_text,
        }


@dataclass(frozen=True, slots=True)
class EvaluationSuite:
    """A versioned collection of uniquely identified evaluation cases."""

    suite_id: str
    suite_version: str
    cases: tuple[EvaluationCase, ...]

    def __post_init__(self) -> None:
        _require_identifier(self.suite_id, "suite_id")
        _require_text(self.suite_version, "suite_version")
        cases = tuple(self.cases)
        if not cases:
            raise ValueError("Evaluation Suite must contain at least one case")
        if any(not isinstance(case, EvaluationCase) for case in cases):
            raise TypeError("cases must contain EvaluationCase values")
        if len({case.case_id for case in cases}) != len(cases):
            raise ValueError("Evaluation case identifiers must be unique")
        object.__setattr__(self, "cases", tuple(sorted(cases, key=lambda case: case.case_id)))

    def to_dict(self) -> dict[str, object]:
        return {
            "cases": [case.to_dict() for case in self.cases],
            "suite_id": self.suite_id,
            "suite_version": self.suite_version,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )


@dataclass(frozen=True, slots=True)
class StrategySelection:
    """One ranked artifact emitted by an evaluation strategy."""

    path: ArtifactPath
    rank: int
    score: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.path, ArtifactPath):
            raise TypeError("path must be an ArtifactPath")
        if type(self.rank) is not int:
            raise TypeError("rank must be an integer")
        if self.rank < 1:
            raise ValueError("rank must be positive")
        if self.score is not None and (
            not isinstance(self.score, (int, float)) or not math.isfinite(self.score)
        ):
            raise ValueError("score must be a finite number")

    def to_dict(self) -> dict[str, object]:
        return {"path": str(self.path), "rank": self.rank, "score": self.score}


@dataclass(frozen=True, slots=True)
class StrategyResult:
    """Ranked output and cost observations for one strategy and case."""

    case_id: str
    strategy_id: str
    selections: tuple[StrategySelection, ...]
    duration_ms: float

    def __post_init__(self) -> None:
        _require_identifier(self.case_id, "case_id")
        _require_identifier(self.strategy_id, "strategy_id")
        selections = tuple(self.selections)
        if any(not isinstance(item, StrategySelection) for item in selections):
            raise TypeError("selections must contain StrategySelection values")
        if len({item.path for item in selections}) != len(selections):
            raise ValueError("Strategy selections must contain unique paths")
        if tuple(item.rank for item in selections) != tuple(range(1, len(selections) + 1)):
            raise ValueError("Strategy selection ranks must be contiguous and ordered")
        if not isinstance(self.duration_ms, (int, float)) or not math.isfinite(self.duration_ms):
            raise ValueError("duration_ms must be a finite number")
        if self.duration_ms < 0:
            raise ValueError("duration_ms must not be negative")
        object.__setattr__(self, "selections", selections)

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "duration_ms": self.duration_ms,
            "selections": [item.to_dict() for item in self.selections],
            "strategy_id": self.strategy_id,
        }


@dataclass(frozen=True, slots=True)
class MetricResult:
    """One bounded deterministic score for one strategy and case."""

    case_id: str
    strategy_id: str
    metric_name: str
    value: float

    def __post_init__(self) -> None:
        _require_identifier(self.case_id, "case_id")
        _require_identifier(self.strategy_id, "strategy_id")
        _require_identifier(self.metric_name, "metric_name")
        if not isinstance(self.value, (int, float)) or not math.isfinite(self.value):
            raise ValueError("value must be a finite number")
        if not 0.0 <= self.value <= 1.0:
            raise ValueError("Metric value must be between zero and one")

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "metric_name": self.metric_name,
            "strategy_id": self.strategy_id,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class EvaluationRunResult:
    """Complete immutable output of an evaluation run."""

    run_id: str
    suite_id: str
    strategy_results: tuple[StrategyResult, ...]
    metric_results: tuple[MetricResult, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        _require_identifier(self.run_id, "run_id")
        _require_identifier(self.suite_id, "suite_id")
        strategy_results = tuple(self.strategy_results)
        metric_results = tuple(self.metric_results)
        if any(not isinstance(item, StrategyResult) for item in strategy_results):
            raise TypeError("strategy_results must contain StrategyResult values")
        if any(not isinstance(item, MetricResult) for item in metric_results):
            raise TypeError("metric_results must contain MetricResult values")
        strategy_keys = tuple((item.case_id, item.strategy_id) for item in strategy_results)
        metric_keys = tuple(
            (item.case_id, item.strategy_id, item.metric_name) for item in metric_results
        )
        if len(set(strategy_keys)) != len(strategy_keys):
            raise ValueError("Strategy results must be unique by case and strategy")
        if len(set(metric_keys)) != len(metric_keys):
            raise ValueError("Metric results must be unique by case, strategy, and metric")
        _format_datetime(self.created_at)
        object.__setattr__(
            self,
            "strategy_results",
            tuple(sorted(strategy_results, key=lambda item: (item.case_id, item.strategy_id))),
        )
        object.__setattr__(
            self,
            "metric_results",
            tuple(
                sorted(
                    metric_results,
                    key=lambda item: (item.case_id, item.strategy_id, item.metric_name),
                )
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "created_at": _format_datetime(self.created_at),
            "metric_results": [item.to_dict() for item in self.metric_results],
            "run_id": self.run_id,
            "strategy_results": [item.to_dict() for item in self.strategy_results],
            "suite_id": self.suite_id,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
