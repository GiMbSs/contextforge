"""CLI tests for persisted context inspection."""

import json
from pathlib import Path

from typer.testing import CliRunner

from contextforge.cli.main import app

runner = CliRunner()


def _run_analysis(project: Path) -> dict[str, object]:
    result = runner.invoke(
        app,
        [
            "--project",
            str(project),
            "--format",
            "json",
            "run",
            "--analysis-only",
            "Explain this project.",
        ],
    )
    assert result.exit_code == 0
    return json.loads(result.stdout)


def test_context_show_and_list_use_persisted_run_result(tmp_path: Path) -> None:
    _run_analysis(tmp_path)
    persisted = tmp_path / ".contextforge" / "executions" / "latest-context.json"
    assert persisted.is_file()

    show = runner.invoke(
        app,
        ["--project", str(tmp_path), "--format", "json", "context", "show"],
    )
    listing = runner.invoke(
        app,
        ["--project", str(tmp_path), "--format", "json", "context", "list"],
    )

    assert show.exit_code == 0
    assert (
        json.loads(show.stdout)["bundle_id"]
        == json.loads(persisted.read_text(encoding="utf-8"))["bundle_id"]
    )
    assert json.loads(listing.stdout)["items"] == []


def test_context_export_writes_explicit_destination_without_rerun(tmp_path: Path) -> None:
    _run_analysis(tmp_path)
    export_path = tmp_path / "exports" / "context.json"
    export_path.parent.mkdir()

    result = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--format",
            "json",
            "context",
            "export",
            "--output",
            str(export_path),
        ],
    )

    assert result.exit_code == 0
    exported = json.loads(export_path.read_text(encoding="utf-8"))
    assert exported["bundle_id"].startswith("context_bundle_")
    assert json.loads(result.stdout)["destination"] == str(export_path)


def test_context_inspection_fails_when_no_persisted_result_exists(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["--project", str(tmp_path), "--format", "json", "context", "show"],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {"status": "failed"}
    assert "CLI_CONTEXT_NOT_FOUND" in result.stderr


def test_context_explain_reports_missing_item_from_persisted_bundle(tmp_path: Path) -> None:
    _run_analysis(tmp_path)

    result = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--format",
            "json",
            "context",
            "explain",
            "missing.py",
        ],
    )

    assert result.exit_code == 1
    assert "CLI_CONTEXT_ITEM_NOT_FOUND" in result.stderr
