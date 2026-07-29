"""Deterministic orchestration for end-to-end effectiveness evaluations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from contextforge.evaluation.models import (
    EvaluationCase,
    EvaluationRunResult,
    EvaluationSuite,
    MetricResult,
    StrategyResult,
)

EVALUATION_RUNNER_VERSION = "evaluation-runner-v1"


class CaseRunStatus(StrEnum):
    """Terminal outcome for one independently evaluated case."""

    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class CaseEvaluationOutput:
    """Successful output produced by a case executor."""

    strategy_results: tuple[StrategyResult, ...]
    metric_results: tuple[MetricResult, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "strategy_results", tuple(self.strategy_results))
        object.__setattr__(self, "metric_results", tuple(self.metric_results))


class EvaluationCaseExecutor(Protocol):
    """Execute one case against its immutable fixture snapshot."""

    def execute(self, case: EvaluationCase) -> CaseEvaluationOutput:
        """Return all strategy and metric results for one case."""
        ...


@dataclass(frozen=True, slots=True)
class CaseRunRecord:
    """Stable success or failure information for one selected case."""

    case_id: str
    status: CaseRunStatus
    error_type: str | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("case_id must not be empty")
        if self.status is CaseRunStatus.COMPLETED:
            if self.error_type is not None or self.error_message is not None:
                raise ValueError("Completed cases must not contain error details")
        elif not self.error_type or not self.error_message:
            raise ValueError("Failed cases must contain error details")


@dataclass(frozen=True, slots=True)
class EvaluationRunMetadata:
    """Reproducibility metadata that does not depend on local absolute paths."""

    runner_version: str
    configuration_fingerprint: str
    source_revision: str | None
    offline: bool
    selected_case_ids: tuple[str, ...]
    selected_tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvaluationExecutionResult:
    """Run results together with case outcomes and reproducibility metadata."""

    run: EvaluationRunResult
    cases: tuple[CaseRunRecord, ...]
    metadata: EvaluationRunMetadata


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class EvaluationRunner:
    """Filter and execute cases independently with deterministic aggregation."""

    executor: EvaluationCaseExecutor
    configuration: tuple[tuple[str, str], ...] = ()
    source_revision: str | None = None
    offline: bool = True
    clock: Callable[[], datetime] = _utc_now

    def run(
        self,
        suite: EvaluationSuite,
        *,
        case_ids: tuple[str, ...] = (),
        tags: tuple[str, ...] = (),
    ) -> EvaluationExecutionResult:
        """Run selected cases; one case failure never aborts later cases."""
        if not isinstance(suite, EvaluationSuite):
            raise TypeError("suite must be an EvaluationSuite")
        normalized_ids = tuple(sorted(set(case_ids)))
        normalized_tags = tuple(sorted(set(tags)))
        available_ids = {case.case_id for case in suite.cases}
        unknown = set(normalized_ids) - available_ids
        if unknown:
            raise ValueError(f"Unknown evaluation case identifiers: {sorted(unknown)}")

        selected = tuple(
            case
            for case in suite.cases
            if (not normalized_ids or case.case_id in normalized_ids)
            and (not normalized_tags or set(normalized_tags) <= set(case.tags))
        )
        configuration_fingerprint = self._configuration_fingerprint(
            suite, selected, normalized_tags
        )
        strategy_results: list[StrategyResult] = []
        metric_results: list[MetricResult] = []
        records: list[CaseRunRecord] = []

        for case in selected:
            try:
                output = self.executor.execute(case)
                if any(item.case_id != case.case_id for item in output.strategy_results):
                    raise ValueError("Case executor returned a strategy result for another case")
                if any(item.case_id != case.case_id for item in output.metric_results):
                    raise ValueError("Case executor returned a metric result for another case")
                strategy_keys = tuple(
                    (item.case_id, item.strategy_id) for item in output.strategy_results
                )
                metric_keys = tuple(
                    (item.case_id, item.strategy_id, item.metric_name)
                    for item in output.metric_results
                )
                if len(set(strategy_keys)) != len(strategy_keys):
                    raise ValueError("Case executor returned duplicate strategy results")
                if len(set(metric_keys)) != len(metric_keys):
                    raise ValueError("Case executor returned duplicate metric results")
                strategy_results.extend(output.strategy_results)
                metric_results.extend(output.metric_results)
                records.append(CaseRunRecord(case.case_id, CaseRunStatus.COMPLETED))
            except Exception as error:
                records.append(
                    CaseRunRecord(
                        case.case_id,
                        CaseRunStatus.FAILED,
                        type(error).__name__,
                        str(error) or "Case execution failed",
                    )
                )

        created_at = self.clock()
        digest = hashlib.sha256(
            f"{suite.suite_id}\0{suite.suite_version}\0{configuration_fingerprint}".encode()
        ).hexdigest()[:24]
        run = EvaluationRunResult(
            run_id=f"run-{digest}",
            suite_id=suite.suite_id,
            strategy_results=tuple(strategy_results),
            metric_results=tuple(metric_results),
            created_at=created_at,
        )
        metadata = EvaluationRunMetadata(
            EVALUATION_RUNNER_VERSION,
            configuration_fingerprint,
            self.source_revision,
            self.offline,
            tuple(case.case_id for case in selected),
            normalized_tags,
        )
        return EvaluationExecutionResult(run, tuple(records), metadata)

    def _configuration_fingerprint(
        self,
        suite: EvaluationSuite,
        selected: tuple[EvaluationCase, ...],
        tags: tuple[str, ...],
    ) -> str:
        payload = {
            "cases": [case.case_id for case in selected],
            "configuration": sorted(self.configuration),
            "offline": self.offline,
            "runner_version": EVALUATION_RUNNER_VERSION,
            "source_revision": self.source_revision,
            "suite_id": suite.suite_id,
            "suite_version": suite.suite_version,
            "tags": list(tags),
        }
        serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        return f"sha256:{hashlib.sha256(serialized.encode()).hexdigest()}"
