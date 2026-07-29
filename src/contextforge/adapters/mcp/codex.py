"""Codex CLI registration for the local ContextForge MCP server."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import anyio
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

from contextforge.adapters.mcp.server import CONTEXT_TOOL_NAME
from contextforge.adapters.project_commands import LocalProjectCommandGateway, resolve_cli_project

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


@dataclass(frozen=True, slots=True)
class DiagnosticCheck:
    """One stable installation or bridge health check."""

    name: str
    status: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"message": self.message, "name": self.name, "status": self.status}


@dataclass(frozen=True, slots=True)
class CodexBridgeDiagnostics:
    """Complete diagnostic report for the Codex MCP bridge."""

    checks: tuple[DiagnosticCheck, ...]
    project_root: str

    @property
    def succeeded(self) -> bool:
        return all(check.status == "passed" for check in self.checks)

    def to_dict(self) -> dict[str, object]:
        return {
            "checks": [check.to_dict() for check in self.checks],
            "project_root": self.project_root,
            "status": "ready" if self.succeeded else "failed",
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


def _project_source_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    excluded = {
        ".contextforge",
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "venv",
    }
    for candidate in sorted(root.rglob("*")):
        relative = candidate.relative_to(root)
        if (
            any(part in excluded for part in relative.parts)
            or candidate.is_symlink()
            or not candidate.is_file()
        ):
            continue
        digest.update(relative.as_posix().encode())
        digest.update(b"\0")
        digest.update(candidate.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


async def _exercise_stdio_server(root: Path, task: str) -> tuple[bool, str]:
    command = contextforge_server_command()
    parameters = StdioServerParameters(
        command=command[0],
        args=list(command[1:]),
        cwd=root,
    )
    before = _project_source_fingerprint(root)
    try:
        with anyio.fail_after(30):
            async with Client(stdio_client(parameters), mode="legacy") as client:
                tools = await client.list_tools()
                names = {tool.name for tool in tools.tools}
                if CONTEXT_TOOL_NAME not in names:
                    return False, f"MCP server did not list {CONTEXT_TOOL_NAME}"
                result = await client.call_tool(
                    CONTEXT_TOOL_NAME,
                    {
                        "task": task,
                        "project_root": str(root),
                        "max_items": 5,
                        "max_bytes": 16_384,
                    },
                )
                if result.is_error:
                    return False, "MCP sample context request returned an error"
                packet = result.structured_content
                if not isinstance(packet, dict) or not packet.get("items"):
                    return False, "MCP sample context request returned no context items"
    except Exception as error:
        return False, f"MCP stdio smoke test failed: {type(error).__name__}: {error}"
    after = _project_source_fingerprint(root)
    if after != before:
        return False, "MCP smoke test modified project source files"
    return True, "Server started, listed its context tool, and completed a read-only request."


def diagnose_codex_bridge(
    project_root: Path,
    *,
    runner: CommandRunner | None = None,
    codex_executable: str | None = None,
    task: str = "Explain the ContextForge MCP integration",
) -> CodexBridgeDiagnostics:
    """Verify installation, project readiness, registration, and stdio behavior."""
    checks: list[DiagnosticCheck] = []
    selected_runner = runner or SubprocessCommandRunner()
    launcher_check = selected_runner.run((sys.executable, "-m", "contextforge", "--version"))
    checks.append(
        DiagnosticCheck(
            "contextforge_executable",
            "passed" if launcher_check.returncode == 0 else "failed",
            (
                launcher_check.stdout.strip()
                if launcher_check.returncode == 0
                else "Current Python environment cannot launch ContextForge."
            ),
        )
    )

    root, failure = resolve_cli_project(project_root)
    if failure is not None or root is None:
        checks.append(
            DiagnosticCheck(
                "project",
                "failed",
                "Project root could not be resolved.",
            )
        )
        return CodexBridgeDiagnostics(tuple(checks), str(project_root))

    project_status = LocalProjectCommandGateway().status(root)
    initialized = project_status.data.get("initialized") is True
    checks.append(
        DiagnosticCheck(
            "project",
            "passed" if initialized else "failed",
            "Project is initialized." if initialized else "Run 'contextforge init' first.",
        )
    )

    selected_codex = codex_executable or shutil.which("codex")
    if selected_codex is None:
        checks.append(
            DiagnosticCheck("codex_registration", "failed", "Codex CLI was not found on PATH.")
        )
    else:
        inspected = selected_runner.run((selected_codex, "mcp", "get", CODEX_SERVER_NAME, "--json"))
        try:
            configured = (
                _configured_command(json.loads(inspected.stdout))
                if inspected.returncode == 0
                else None
            )
        except json.JSONDecodeError:
            configured = None
        registration_ready = configured == contextforge_server_command()
        checks.append(
            DiagnosticCheck(
                "codex_registration",
                "passed" if registration_ready else "failed",
                (
                    "Codex has the expected ContextForge stdio registration."
                    if registration_ready
                    else "Run 'contextforge mcp install-codex'."
                ),
            )
        )

    smoke_ok, smoke_message = anyio.run(_exercise_stdio_server, root.path, task)
    checks.append(
        DiagnosticCheck(
            "mcp_stdio_smoke",
            "passed" if smoke_ok else "failed",
            smoke_message,
        )
    )
    return CodexBridgeDiagnostics(tuple(checks), str(root.path))


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
