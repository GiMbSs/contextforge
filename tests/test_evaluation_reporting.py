"""Tests for CF-015-E007 stable JSON and Markdown reporting."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from contextforge.adapters.evaluation import (
    FilesystemEvaluationReportWriter,
    FilesystemEvaluationSuiteLoader,
)
from contextforge.evaluation import (
    CaseEvaluationOutput,
    EvaluationCase,
    EvaluationRunner,
    MetricResult,
    StrategyResult,
    render_evaluation_json,
    render_evaluation_markdown,
)

FIXED_TIME = datetime(2026, 2, 3, 4, 5, tzinfo=UTC)
FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "evaluation"


@dataclass
class _ReportExecutor:
    def execute(self, case: EvaluationCase) -> CaseEvaluationOutput:
        if case.case_id == "dependency-closure":
            raise RuntimeError(r"C:\Users\me\fixture.py token=super-secret")
        return CaseEvaluationOutput(
            (
                StrategyResult(case.case_id, "contextforge", (), 0.0),
                StrategyResult(case.case_id, "baseline-lexical", (), 0.0),
            ),
            (
                MetricResult(case.case_id, "contextforge", "ndcg", 0.25),
                MetricResult(case.case_id, "baseline-lexical", "ndcg", 0.75),
            ),
        )


def _result():
    suite = FilesystemEvaluationSuiteLoader(FIXTURE_ROOT).load(Path("suites/core.json"))
    return EvaluationRunner(_ReportExecutor(), clock=lambda: FIXED_TIME).run(
        suite,
        case_ids=("budget-pressure", "dependency-closure"),
    )


def test_json_is_stable_versioned_and_redacts_paths_and_secrets() -> None:
    first = render_evaluation_json(_result())
    second = render_evaluation_json(_result())
    document = json.loads(first)

    assert first == second
    assert document["schema"] == "contextforge.evaluation-result"
    assert document["schema_version"] == "1"
    assert document["aggregates"][0]["mean"] == 0.75
    assert document["baseline_deltas"][0]["delta"] == -0.5
    assert "C:\\Users" not in first
    assert "super-secret" not in first
    assert "<local-path>" in first
    assert "<redacted>" in first


def test_markdown_shows_failures_regressions_deltas_and_aggregates() -> None:
    markdown = render_evaluation_markdown(_result())

    assert "## Failures" in markdown
    assert "`dependency-closure`" in markdown
    assert "## Aggregate metrics" in markdown
    assert "## Baseline deltas" in markdown
    assert "## Regressions" in markdown
    assert "-0.500000" in markdown
    assert "super-secret" not in markdown


def test_filesystem_writer_confines_atomic_report_outputs(tmp_path: Path) -> None:
    paths = FilesystemEvaluationReportWriter(tmp_path).write(_result(), "core-run")

    assert paths.json_path.read_text(encoding="utf-8").endswith("\n")
    assert paths.markdown_path.read_text(encoding="utf-8").startswith("# ContextForge evaluation\n")
    assert not tuple(tmp_path.glob("*.tmp"))
    with pytest.raises(ValueError, match="filename stem"):
        FilesystemEvaluationReportWriter(tmp_path).write(_result(), "../escape")
