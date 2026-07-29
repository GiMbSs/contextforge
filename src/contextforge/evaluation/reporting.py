"""Stable machine and human-readable effectiveness evaluation reports."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass

from contextforge.evaluation.baselines import BaselineMetricDelta, calculate_baseline_deltas
from contextforge.evaluation.models import MetricResult
from contextforge.evaluation.runner import (
    CaseRunRecord,
    CaseRunStatus,
    EvaluationExecutionResult,
)

EVALUATION_RESULT_SCHEMA = "contextforge.evaluation-result"
EVALUATION_RESULT_SCHEMA_VERSION = "1"
_ABSOLUTE_PATH = re.compile(r"(?<![\w.])(?:[A-Za-z]:[\\/]|/)[^\s;,\])}]+")
_SECRET = re.compile(
    r"(?i)\b(api[_-]?key|authorization|bearer|password|secret|token)"
    r"(\s*[:=]\s*|\s+)[^\s;,]+"
)


def sanitize_report_text(value: str) -> str:
    """Redact likely secrets and absolute local paths from report text."""
    if not isinstance(value, str):
        raise TypeError("value must be a string")
    without_secrets = _SECRET.sub(r"\1\2<redacted>", value)
    return _ABSOLUTE_PATH.sub("<local-path>", without_secrets)


@dataclass(frozen=True, slots=True)
class AggregateMetric:
    """Mean metric value for one strategy across successful cases."""

    strategy_id: str
    metric_name: str
    case_count: int
    mean: float

    def to_dict(self) -> dict[str, object]:
        return {
            "case_count": self.case_count,
            "mean": self.mean,
            "metric_name": self.metric_name,
            "strategy_id": self.strategy_id,
        }


def aggregate_metrics(metrics: tuple[MetricResult, ...]) -> tuple[AggregateMetric, ...]:
    """Aggregate metrics by strategy and metric name in canonical order."""
    grouped: dict[tuple[str, str], list[float]] = {}
    for metric in metrics:
        grouped.setdefault((metric.strategy_id, metric.metric_name), []).append(metric.value)
    return tuple(
        AggregateMetric(strategy_id, metric_name, len(values), math.fsum(values) / len(values))
        for (strategy_id, metric_name), values in sorted(grouped.items())
    )


def _deltas(result: EvaluationExecutionResult) -> tuple[BaselineMetricDelta, ...]:
    metrics = result.run.metric_results
    primary = tuple(metric for metric in metrics if metric.strategy_id == "contextforge")
    baselines = tuple(metric for metric in metrics if metric.strategy_id.startswith("baseline-"))
    primary_keys = {(metric.case_id, metric.metric_name) for metric in primary}
    comparable = tuple(
        metric for metric in baselines if (metric.case_id, metric.metric_name) in primary_keys
    )
    return calculate_baseline_deltas(primary, comparable)


def _case_dict(record: CaseRunRecord) -> dict[str, object]:
    return {
        "case_id": record.case_id,
        "error_message": (
            sanitize_report_text(record.error_message) if record.error_message is not None else None
        ),
        "error_type": record.error_type,
        "status": record.status.value,
    }


def evaluation_result_document(result: EvaluationExecutionResult) -> dict[str, object]:
    """Build the versioned, path-safe evaluation result document."""
    deltas = _deltas(result)
    metadata = result.metadata
    return {
        "aggregates": [item.to_dict() for item in aggregate_metrics(result.run.metric_results)],
        "baseline_deltas": [
            {
                "baseline_strategy_id": item.baseline_strategy_id,
                "baseline_value": item.baseline_value,
                "case_id": item.case_id,
                "delta": item.delta,
                "metric_name": item.metric_name,
                "primary_strategy_id": item.primary_strategy_id,
                "primary_value": item.primary_value,
            }
            for item in deltas
        ],
        "cases": [_case_dict(record) for record in result.cases],
        "metadata": {
            "configuration_fingerprint": metadata.configuration_fingerprint,
            "offline": metadata.offline,
            "runner_version": metadata.runner_version,
            "selected_case_ids": list(metadata.selected_case_ids),
            "selected_tags": list(metadata.selected_tags),
            "source_revision": metadata.source_revision,
        },
        "run": result.run.to_dict(),
        "schema": EVALUATION_RESULT_SCHEMA,
        "schema_version": EVALUATION_RESULT_SCHEMA_VERSION,
    }


def render_evaluation_json(result: EvaluationExecutionResult) -> str:
    """Serialize a stable machine-readable result document."""
    return json.dumps(
        evaluation_result_document(result),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def render_evaluation_markdown(result: EvaluationExecutionResult) -> str:
    """Render a concise comparison report with failures and regressions."""
    aggregates = aggregate_metrics(result.run.metric_results)
    deltas = _deltas(result)
    failures = tuple(record for record in result.cases if record.status is CaseRunStatus.FAILED)
    regressions = tuple(item for item in deltas if item.delta < 0)
    lines = [
        "# ContextForge evaluation",
        "",
        f"- Run: `{result.run.run_id}`",
        f"- Suite: `{result.run.suite_id}`",
        f"- Cases: {len(result.cases)} ({len(failures)} failed)",
        f"- Offline: {'yes' if result.metadata.offline else 'no'}",
        "",
        "## Failures",
        "",
    ]
    if failures:
        lines.extend(
            f"- `{record.case_id}` — {record.error_type}: "
            f"{sanitize_report_text(record.error_message or 'Case execution failed')}"
            for record in failures
        )
    else:
        lines.append("No case failures.")
    lines.extend(
        [
            "",
            "## Aggregate metrics",
            "",
            "| Strategy | Metric | Cases | Mean |",
            "|---|---|---:|---:|",
        ]
    )
    lines.extend(
        f"| `{item.strategy_id}` | `{item.metric_name}` | {item.case_count} | {item.mean:.6f} |"
        for item in aggregates
    )
    if not aggregates:
        lines.append("| — | — | 0 | — |")
    lines.extend(
        [
            "",
            "## Baseline deltas",
            "",
            "| Case | Baseline | Metric | Delta |",
            "|---|---|---|---:|",
        ]
    )
    lines.extend(
        f"| `{item.case_id}` | `{item.baseline_strategy_id}` | "
        f"`{item.metric_name}` | {item.delta:+.6f} |"
        for item in deltas
    )
    if not deltas:
        lines.append("| — | — | — | — |")
    lines.extend(["", "## Regressions", ""])
    if regressions:
        lines.extend(
            f"- `{item.case_id}` / `{item.metric_name}` vs "
            f"`{item.baseline_strategy_id}`: {item.delta:+.6f}"
            for item in regressions
        )
    else:
        lines.append("No baseline regressions.")
    return "\n".join(lines) + "\n"
