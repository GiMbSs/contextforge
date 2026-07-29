"""Operational diagnostics for the Codex-to-ContextForge MCP bridge."""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from typer.testing import CliRunner

from contextforge.adapters.mcp.codex import CommandResult, contextforge_server_command
from contextforge.cli.main import app


@dataclass
class StubRunner:
    results: list[CommandResult]
    commands: list[tuple[str, ...]] = field(default_factory=list)

    def run(self, command: Sequence[str]) -> CommandResult:
        self.commands.append(tuple(command))
        return self.results.pop(0)


def _configured_server_result() -> CommandResult:
    command = contextforge_server_command()
    return CommandResult(
        0,
        stdout=json.dumps(
            {
                "transport": {
                    "type": "stdio",
                    "command": command[0],
                    "args": list(command[1:]),
                }
            }
        ),
    )


def test_doctor_exercises_real_stdio_server_without_changing_source(
    tmp_path: Path,
) -> None:
    from contextforge.adapters.mcp.codex import diagnose_codex_bridge

    (tmp_path / "service.py").write_text(
        "def healthcheck() -> str:\n    return 'ready'\n",
        encoding="utf-8",
    )
    CliRunner().invoke(app, ["init", str(tmp_path)])
    original = (tmp_path / "service.py").read_bytes()
    runner = StubRunner(
        [
            CommandResult(0, stdout="contextforge 0.1.1"),
            _configured_server_result(),
        ]
    )

    report = diagnose_codex_bridge(
        tmp_path,
        runner=runner,
        codex_executable="codex",
        task="Explain healthcheck in service.py",
    )

    assert report.succeeded is True
    assert {check.name for check in report.checks} == {
        "contextforge_executable",
        "project",
        "codex_registration",
        "mcp_stdio_smoke",
    }
    assert (tmp_path / "service.py").read_bytes() == original
    assert runner.commands[0] == (sys.executable, "-m", "contextforge", "--version")


def test_doctor_reports_uninitialized_project_and_missing_registration(
    tmp_path: Path,
) -> None:
    from contextforge.adapters.mcp.codex import diagnose_codex_bridge

    (tmp_path / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    runner = StubRunner(
        [
            CommandResult(0, stdout="contextforge 0.1.1"),
            CommandResult(1, stderr="server not found"),
        ]
    )

    report = diagnose_codex_bridge(
        tmp_path,
        runner=runner,
        codex_executable="codex",
        task="Explain module.py",
    )

    checks = {check.name: check for check in report.checks}
    assert report.succeeded is False
    assert checks["project"].status == "failed"
    assert checks["codex_registration"].status == "failed"
    assert checks["mcp_stdio_smoke"].status == "passed"


def test_doctor_cli_emits_json_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from contextforge.adapters.mcp.codex import CodexBridgeDiagnostics, DiagnosticCheck

    report = CodexBridgeDiagnostics(
        (DiagnosticCheck("mcp_stdio_smoke", "passed", "ok"),),
        str(tmp_path),
    )
    monkeypatch.setattr("contextforge.cli.main.diagnose_codex_bridge", lambda _: report)

    result = CliRunner().invoke(
        app,
        ["--project", str(tmp_path), "--format", "json", "mcp", "doctor"],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "ready"
