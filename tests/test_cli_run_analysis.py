"""CLI tests for analysis-only task input modes."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from contextforge.cli.main import app

runner = CliRunner(env={"NO_COLOR": "1"})


@pytest.mark.parametrize("mode", ["argument", "stdin", "file"])
def test_run_analysis_accepts_each_exact_task_source(tmp_path: Path, mode: str) -> None:
    task = "Explain this project."
    arguments = [
        "--project",
        str(tmp_path),
        "--format",
        "json",
        "run",
        "--analysis-only",
    ]
    input_text = None
    if mode == "argument":
        arguments.append(task)
    elif mode == "stdin":
        arguments.append("--stdin")
        input_text = task
    else:
        task_file = tmp_path / "task.md"
        task_file.write_text(task, encoding="utf-8")
        arguments.extend(("--task-file", str(task_file)))

    result = runner.invoke(app, arguments, input=input_text)

    assert result.exit_code == 0
    envelope = json.loads(result.stdout)
    assert envelope["schema_version"] == "1.0"
    payload = envelope["data"]
    assert payload["mode"] == "analysis_only"
    assert payload["task"] == task
    assert payload["summary"] == "Deterministic mock analysis."
    assert result.stderr == ""


@pytest.mark.parametrize(
    "task_arguments",
    [
        (),
        ("task", "--stdin"),
        ("task", "--task-file", "task.md"),
    ],
)
def test_run_requires_exactly_one_task_source(
    tmp_path: Path,
    task_arguments: tuple[str, ...],
) -> None:
    (tmp_path / "task.md").write_text("file task", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "run",
            "--analysis-only",
            *task_arguments,
        ],
        input="stdin task",
    )

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "exactly one" in result.stderr


def test_run_rejects_empty_and_non_analysis_execution(tmp_path: Path) -> None:
    empty = runner.invoke(
        app,
        ["--project", str(tmp_path), "run", "--analysis-only", "--stdin"],
        input=" \n",
    )
    patch_mode = runner.invoke(
        app,
        ["--project", str(tmp_path), "run", "change a file"],
    )

    assert empty.exit_code == 2
    assert "must not be empty" in empty.stderr
    assert patch_mode.exit_code == 2
    assert "--analysis-only is required" in patch_mode.stderr
