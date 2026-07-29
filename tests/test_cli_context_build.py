"""CLI tests for transport-neutral agent context packets."""

import json
from pathlib import Path

from typer.testing import CliRunner

from contextforge.cli.main import app

runner = CliRunner(env={"NO_COLOR": "1"})


def test_context_build_returns_selected_content_and_traceability(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "payments.py").write_text(
        "def authorize_payment(amount: int) -> bool:\n    return amount > 0\n",
        encoding="utf-8",
    )
    (source / "unrelated.py").write_text("COLOR = 'blue'\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--format",
            "json",
            "context",
            "build",
            "Explain authorize_payment in src/payments.py",
            "--max-items",
            "4",
            "--max-bytes",
            "4096",
        ],
    )

    assert result.exit_code == 0, result.stderr
    data = json.loads(result.stdout)["data"]
    packet = data["packet"]
    assert packet["packet_version"] == "contextforge-agent-context-v1"
    assert packet["budget"] == {"max_bytes": 4096, "max_items": 4}
    assert packet["estimated_context_tokens"] > 0
    assert packet["project_fingerprint"].startswith("project_sha256_")
    assert packet["items"]
    selected = packet["items"][0]
    assert selected["path"] == "src/payments.py"
    assert "authorize_payment" in selected["content"]
    assert selected["evidence"]
    assert selected["source_reference"]
    assert result.stderr == ""


def test_context_build_reuses_index_until_project_content_changes(tmp_path: Path) -> None:
    source = tmp_path / "module.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    command = [
        "--project",
        str(tmp_path),
        "--format",
        "json",
        "context",
        "build",
        "Explain VALUE in module.py",
    ]

    first = runner.invoke(app, command)
    pointer_path = tmp_path / ".contextforge" / "state" / "indexes" / "latest.json"
    first_index_id = json.loads(pointer_path.read_text(encoding="utf-8"))["artifact_id"]
    second = runner.invoke(app, command)
    second_index_id = json.loads(pointer_path.read_text(encoding="utf-8"))["artifact_id"]

    source.write_text("VALUE = 2\n", encoding="utf-8")
    changed = runner.invoke(app, command)
    changed_index_id = json.loads(pointer_path.read_text(encoding="utf-8"))["artifact_id"]

    assert first.exit_code == 0, first.stderr
    assert second.exit_code == 0, second.stderr
    assert changed.exit_code == 0, changed.stderr
    assert second_index_id == first_index_id
    assert changed_index_id != first_index_id
    changed_packet = json.loads(changed.stdout)["data"]["packet"]
    assert "VALUE = 2" in changed_packet["items"][0]["content"]


def test_context_build_enforces_agent_budget_bounds(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "context",
            "build",
            "Explain the project",
            "--max-items",
            "101",
        ],
    )

    assert result.exit_code == 2
    assert "100" in result.stderr


def test_context_build_rejects_blank_task(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["--project", str(tmp_path), "context", "build", "   "],
    )

    assert result.exit_code == 2
    assert "must not be empty" in result.stderr
