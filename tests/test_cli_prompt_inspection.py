"""CLI tests for safe persisted prompt inspection."""

import json
from pathlib import Path

from typer.testing import CliRunner

from contextforge.cli.main import app

runner = CliRunner()


def _run_analysis(project: Path, task: str = "Explain this project.") -> dict[str, object]:
    result = runner.invoke(
        app,
        [
            "--project",
            str(project),
            "--format",
            "json",
            "run",
            "--analysis-only",
            task,
        ],
    )
    assert result.exit_code == 0
    return json.loads(result.stdout)


def test_prompt_preview_and_measure_use_persisted_inference_request(
    tmp_path: Path,
) -> None:
    run = _run_analysis(tmp_path)
    persisted = tmp_path / ".contextforge" / "executions" / "latest-prompt.json"
    assert persisted.is_file()

    preview = runner.invoke(
        app,
        ["--project", str(tmp_path), "--format", "json", "prompt", "preview"],
    )
    measure = runner.invoke(
        app,
        ["--project", str(tmp_path), "--format", "json", "prompt", "measure"],
    )

    assert preview.exit_code == 0
    preview_data = json.loads(preview.stdout)
    assert preview_data["request_id"] == run["request_id"]
    assert [section["section_id"] for section in preview_data["sections"]] == [
        "system-operating-rules",
        "task-specification",
        "context-usage-rules",
        "serialized-context-bundle",
        "output-response-contract",
    ]
    assert json.loads(measure.stdout)["measurements"]["estimated_tokens"] > 0


def test_prompt_export_writes_safe_explicit_destination(tmp_path: Path) -> None:
    secret = "never-display-this-value"
    _run_analysis(tmp_path, f"Explain configuration with api_key={secret}")
    export_path = tmp_path / "exports" / "prompt.json"
    export_path.parent.mkdir()

    result = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--format",
            "json",
            "prompt",
            "export",
            "--output",
            str(export_path),
        ],
    )

    assert result.exit_code == 0
    persisted_text = (tmp_path / ".contextforge" / "executions" / "latest-prompt.json").read_text(
        encoding="utf-8"
    )
    exported_text = export_path.read_text(encoding="utf-8")
    assert secret not in persisted_text
    assert secret not in exported_text
    assert "[REDACTED]" in exported_text
    assert json.loads(result.stdout)["destination"] == str(export_path)


def test_prompt_inspection_fails_without_persisted_request(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["--project", str(tmp_path), "--format", "json", "prompt", "preview"],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {"status": "failed"}
    assert "CLI_PROMPT_NOT_FOUND" in result.stderr
