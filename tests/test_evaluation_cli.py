"""Tests for CF-015-E008 CLI and optional regression gate."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from contextforge.cli.main import app

runner = CliRunner(env={"NO_COLOR": "1"})
SUITE = Path(__file__).parent / "fixtures" / "evaluation" / "suites" / "core.json"


def test_evaluate_writes_reports_offline_without_gating_case_failures(
    tmp_path: Path,
) -> None:
    output = tmp_path / "reports" / "latest"

    result = runner.invoke(
        app,
        [
            "evaluate",
            str(SUITE),
            "--case",
            "direct-path",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    assert "1 cases, 1 failed" in result.stdout
    document = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
    assert document["metadata"]["offline"] is True
    assert output.with_suffix(".md").is_file()


def test_evaluate_threshold_failure_uses_stable_exit_code(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "evaluate",
            str(SUITE),
            "--case",
            "direct-path",
            "--output",
            str(tmp_path / "latest"),
            "--minimum",
            "not-measured=0.5",
        ],
    )

    assert result.exit_code == 20
    assert "Regression: not-measured=missing" in result.stderr


def test_evaluate_input_failure_uses_stable_exit_code(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "evaluate",
            str(tmp_path / "missing.json"),
            "--output",
            str(tmp_path / "latest"),
        ],
    )

    assert result.exit_code == 19
    assert "Evaluation failed" in result.stderr


def test_evaluate_rejects_duplicate_thresholds(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "evaluate",
            str(SUITE),
            "--output",
            str(tmp_path / "latest"),
            "--minimum",
            "ndcg=0.1",
            "--minimum",
            "ndcg=0.2",
        ],
    )

    assert result.exit_code == 19
    assert "threshold metric names must be unique" in result.stderr
