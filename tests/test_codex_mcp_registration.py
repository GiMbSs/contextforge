"""Tests for idempotent Codex CLI MCP registration."""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest
from typer.testing import CliRunner

from contextforge.adapters.mcp.codex import (
    CODEX_SERVER_NAME,
    CommandResult,
    contextforge_server_command,
    register_codex_server,
)
from contextforge.cli.main import app


@dataclass
class StubRunner:
    results: list[CommandResult]
    commands: list[tuple[str, ...]] = field(default_factory=list)

    def run(self, command: Sequence[str]) -> CommandResult:
        self.commands.append(tuple(command))
        return self.results.pop(0)


def test_registration_uses_current_python_environment() -> None:
    runner = StubRunner(
        [
            CommandResult(1, stderr="server not found"),
            CommandResult(0, stdout="Added global MCP server"),
        ]
    )

    result = register_codex_server(runner=runner, codex_executable="/tools/codex")

    expected_server = (sys.executable, "-m", "contextforge", "mcp", "serve")
    assert result.status == "registered"
    assert result.server_command == expected_server
    assert runner.commands == [
        ("/tools/codex", "mcp", "get", CODEX_SERVER_NAME, "--json"),
        ("/tools/codex", "mcp", "add", CODEX_SERVER_NAME, "--", *expected_server),
    ]


def test_registration_is_idempotent_for_matching_server() -> None:
    server_command = contextforge_server_command()
    runner = StubRunner(
        [
            CommandResult(
                0,
                stdout=json.dumps(
                    {
                        "transport": {
                            "type": "stdio",
                            "command": server_command[0],
                            "args": list(server_command[1:]),
                        }
                    }
                ),
            )
        ]
    )

    result = register_codex_server(runner=runner, codex_executable="codex")

    assert result.status == "already_configured"
    assert len(runner.commands) == 1


def test_registration_refuses_to_replace_conflicting_server() -> None:
    runner = StubRunner(
        [
            CommandResult(
                0,
                stdout=json.dumps(
                    {
                        "transport": {
                            "type": "stdio",
                            "command": "other-contextforge",
                            "args": [],
                        }
                    }
                ),
            )
        ]
    )

    with pytest.raises(RuntimeError, match="CF_CODEX_CONFIG_CONFLICT"):
        register_codex_server(runner=runner, codex_executable="codex")

    assert len(runner.commands) == 1


def test_dry_run_prints_machine_readable_registration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("contextforge.adapters.mcp.codex.shutil.which", lambda _: "codex")
    result = CliRunner().invoke(
        app,
        ["--format", "json", "mcp", "install-codex", "--dry-run"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "planned"
    assert payload["server_name"] == "contextforge"
    assert payload["server_command"][-3:] == ["contextforge", "mcp", "serve"]
