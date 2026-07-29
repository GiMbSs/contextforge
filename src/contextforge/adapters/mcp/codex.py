"""Codex CLI registration for the local ContextForge MCP server."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

CODEX_SERVER_NAME = "contextforge"


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Captured result from an external command."""

    returncode: int
    stdout: str = ""
    stderr: str = ""


class CommandRunner(Protocol):
    """Boundary for deterministic Codex CLI tests."""

    def run(self, command: Sequence[str]) -> CommandResult:
        """Run one command without raising for a non-zero exit status."""
        ...


@dataclass(frozen=True, slots=True)
class SubprocessCommandRunner:
    """Execute commands through the host operating system."""

    def run(self, command: Sequence[str]) -> CommandResult:
        completed = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            check=False,
        )
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)


@dataclass(frozen=True, slots=True)
class CodexRegistration:
    """Result of inspecting or registering the ContextForge MCP server."""

    status: str
    codex_executable: str
    server_command: tuple[str, ...]
    registration_command: tuple[str, ...]
    message: str

    def to_dict(self) -> dict[str, object]:
        return {
            "codex_executable": self.codex_executable,
            "command": list(self.registration_command),
            "message": self.message,
            "server_command": list(self.server_command),
            "server_name": CODEX_SERVER_NAME,
            "status": self.status,
        }


def contextforge_server_command() -> tuple[str, ...]:
    """Return a launcher tied to the current ContextForge Python environment."""
    return (sys.executable, "-m", "contextforge", "mcp", "serve")


def _configured_command(payload: object) -> tuple[str, ...] | None:
    if not isinstance(payload, dict):
        return None
    transport = payload.get("transport")
    if not isinstance(transport, dict) or transport.get("type") != "stdio":
        return None
    command = transport.get("command")
    args = transport.get("args", [])
    if not isinstance(command, str) or not isinstance(args, list):
        return None
    if not all(isinstance(argument, str) for argument in args):
        return None
    return (command, *args)


def register_codex_server(
    *,
    runner: CommandRunner | None = None,
    codex_executable: str | None = None,
    dry_run: bool = False,
) -> CodexRegistration:
    """Register the local stdio server without replacing unrelated configuration."""
    selected_codex = codex_executable or shutil.which("codex")
    if selected_codex is None:
        raise RuntimeError(
            "CF_CODEX_NOT_FOUND: codex executable was not found on PATH; "
            "install Codex CLI before registering the MCP server"
        )
    selected_runner = runner or SubprocessCommandRunner()
    server_command = contextforge_server_command()
    registration_command = (
        selected_codex,
        "mcp",
        "add",
        CODEX_SERVER_NAME,
        "--",
        *server_command,
    )
    if dry_run:
        return CodexRegistration(
            "planned",
            selected_codex,
            server_command,
            registration_command,
            "Codex configuration was not modified.",
        )

    inspected = selected_runner.run((selected_codex, "mcp", "get", CODEX_SERVER_NAME, "--json"))
    if inspected.returncode == 0:
        try:
            configured = _configured_command(json.loads(inspected.stdout))
        except json.JSONDecodeError as error:
            raise RuntimeError(
                "CF_CODEX_CONFIG_INVALID: Codex returned invalid JSON for the existing server"
            ) from error
        if configured == server_command:
            return CodexRegistration(
                "already_configured",
                selected_codex,
                server_command,
                registration_command,
                "The ContextForge MCP server is already registered with this environment.",
            )
        raise RuntimeError(
            "CF_CODEX_CONFIG_CONFLICT: an MCP server named 'contextforge' is already "
            "registered with a different command; remove it explicitly before retrying"
        )

    registered = selected_runner.run(registration_command)
    if registered.returncode != 0:
        details = registered.stderr.strip() or registered.stdout.strip() or "unknown error"
        raise RuntimeError(f"CF_CODEX_REGISTRATION_FAILED: {details}")
    return CodexRegistration(
        "registered",
        selected_codex,
        server_command,
        registration_command,
        "The ContextForge MCP server was registered in Codex.",
    )


def render_shell_command(command: Sequence[str]) -> str:
    """Render a display-only command for the current host shell."""
    if sys.platform == "win32":
        return subprocess.list2cmdline(list(command))
    return _quote_posix(command)


def _quote_posix(command: Sequence[str]) -> str:
    import shlex

    return shlex.join(command)


def executable_path() -> Path:
    """Expose the current interpreter path for installation diagnostics."""
    return Path(sys.executable)
