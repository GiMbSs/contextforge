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
    (tmp_path / "main.py").write_text("def main(): pass\n", encoding="utf-8")
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
    assert payload["task_id"].startswith("task_")
    assert task not in result.stdout
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


def test_run_rejects_empty_task_input(tmp_path: Path) -> None:
    empty = runner.invoke(
        app,
        ["--project", str(tmp_path), "run", "--analysis-only", "--stdin"],
        input=" \n",
        color=False,
    )
    assert empty.exit_code == 2
    assert "must not be empty" in empty.stderr


def test_run_without_analysis_only_generates_reviewable_patch(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "example.py").write_text("value = 1\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--format",
            "json",
            "run",
            "Add a generated module.",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)["data"]
    assert payload["mode"] == "patch_proposal"
    assert payload["status"] == "awaiting_approval"
    assert payload["change_count"] == 1
    proposal_id = payload["proposal_id"]
    assert (tmp_path / ".contextforge" / "proposals" / f"{proposal_id}.json").is_file()


def test_run_analysis_produces_non_empty_context(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    src = project / "db.py"
    src.write_text("def connect(): pass\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "--project",
            str(project),
            "--format",
            "json",
            "run",
            "--analysis-only",
            "Explain the database module.",
        ],
    )

    assert result.exit_code == 0
    context_path = project / ".contextforge" / "executions" / "latest-context.json"
    assert context_path.is_file()
    context = json.loads(context_path.read_text(encoding="utf-8"))
    assert context["statistics"]["item_count"] > 0
