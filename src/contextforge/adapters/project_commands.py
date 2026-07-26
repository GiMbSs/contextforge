"""Thin CLI composition for foundational project commands."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

import typer

from contextforge.adapters.filesystem import (
    LocalProjectInitialization,
    LocalProjectScanner,
)
from contextforge.application import InitializeProject, ProjectInitialization
from contextforge.configuration import ScannerConfig
from contextforge.diagnostics import DiagnosticCollection
from contextforge.domain import ProjectId
from contextforge.indexer import DeterministicProjectIndexer, IndexRequest
from contextforge.project import ProjectRoot, resolve_project_root
from contextforge.scanner import DiscoveryStatus, ProjectArtifact, ProjectInventory, ScanRequest


class CliExitCode(IntEnum):
    """Stable process exit codes assigned by the CLI specification."""

    SUCCESS = 0
    GENERAL_FAILURE = 1
    PROJECT_RESOLUTION_FAILURE = 4
    SCAN_FAILURE = 5
    INDEX_FAILURE = 6
    PARTIAL_RESULT = 17


@dataclass(frozen=True, slots=True)
class CliCommandResult:
    """Presentation-neutral result returned by CLI command composition."""

    data: dict[str, object]
    exit_code: CliExitCode = CliExitCode.SUCCESS
    diagnostics: tuple[dict[str, object], ...] = ()


class ProjectCommandGateway(Protocol):
    """Operations consumed by the CLI without embedding domain decisions."""

    def initialize(self, root: ProjectRoot) -> CliCommandResult: ...

    def status(self, root: ProjectRoot) -> CliCommandResult: ...

    def scan(self, root: ProjectRoot) -> CliCommandResult: ...

    def index(self, root: ProjectRoot) -> CliCommandResult: ...


@dataclass(slots=True)
class _LocalSource:
    root: Path

    def read(self, artifact: ProjectArtifact) -> bytes:
        candidate = self.root.joinpath(*artifact.path.parts).resolve(strict=True)
        candidate.relative_to(self.root)
        return candidate.read_bytes()


@dataclass(slots=True)
class LocalProjectCommandGateway:
    """Default local composition of existing application and adapter services."""

    scanner: LocalProjectScanner = field(default_factory=LocalProjectScanner)
    scanner_configuration: ScannerConfig = field(default_factory=ScannerConfig)

    def initialize(self, root: ProjectRoot) -> CliCommandResult:
        result = ProjectInitialization(LocalProjectInitialization()).execute(
            InitializeProject(root, create_config=True)
        )
        return CliCommandResult(
            {
                "command": "init",
                "configuration_created": result.configuration_created,
                "configuration_file": (
                    str(result.configuration_file)
                    if result.configuration_file is not None
                    else None
                ),
                "metadata_created": result.metadata_created,
                "metadata_directory": str(result.metadata_directory),
                "project_root": str(root.path),
                "status": "initialized" if result.succeeded else "failed",
            },
            CliExitCode.SUCCESS if result.succeeded else CliExitCode.GENERAL_FAILURE,
            _diagnostics(result.diagnostics),
        )

    def status(self, root: ProjectRoot) -> CliCommandResult:
        metadata = root.path / ".contextforge"
        configuration = metadata / "config.toml"
        initialized = metadata.is_dir()
        return CliCommandResult(
            {
                "command": "status",
                "configuration_present": configuration.is_file(),
                "initialized": initialized,
                "project_id": str(_project_id(root)),
                "project_root": str(root.path),
                "status": "ready" if initialized else "uninitialized",
            }
        )

    def scan(self, root: ProjectRoot) -> CliCommandResult:
        inventory = self._scan(root)
        statistics = inventory.statistics
        failed = inventory.status is DiscoveryStatus.FAILED
        partial = inventory.status is DiscoveryStatus.INCOMPLETE
        return CliCommandResult(
            {
                "artifact_count": len(inventory.artifacts),
                "command": "scan",
                "directories": statistics.directories_visited,
                "duration_seconds": statistics.duration_seconds,
                "ignored": statistics.artifacts_excluded,
                "inventory_id": str(inventory.inventory_id),
                "project_fingerprint": str(inventory.project_fingerprint),
                "project_root": str(root.path),
                "status": inventory.status.value,
            },
            (
                CliExitCode.SCAN_FAILURE
                if failed
                else CliExitCode.PARTIAL_RESULT
                if partial
                else CliExitCode.SUCCESS
            ),
            _diagnostics(inventory.diagnostics),
        )

    def index(self, root: ProjectRoot) -> CliCommandResult:
        inventory = self._scan(root)
        project_index = DeterministicProjectIndexer(_LocalSource(root.path)).index(
            IndexRequest(inventory)
        )
        failed = project_index.status.value == "failed"
        return CliCommandResult(
            {
                "artifact_count": len(project_index.indexed_artifacts),
                "command": "index",
                "index_id": str(project_index.index_id),
                "project_fingerprint": str(project_index.project_fingerprint),
                "project_root": str(root.path),
                "relationships": len(project_index.relationships),
                "search_units": len(project_index.search_units),
                "status": project_index.status.value,
                "symbols": len(project_index.symbols),
            },
            CliExitCode.INDEX_FAILURE if failed else CliExitCode.SUCCESS,
            _diagnostics(project_index.diagnostics),
        )

    def _scan(self, root: ProjectRoot) -> ProjectInventory:
        return self.scanner.scan(ScanRequest(_project_id(root), root, self.scanner_configuration))


def _project_id(root: ProjectRoot) -> ProjectId:
    identity = uuid5(NAMESPACE_URL, root.path.as_uri())
    return ProjectId(f"project_{identity.hex}")


def _diagnostics(collection: DiagnosticCollection) -> tuple[dict[str, object], ...]:
    return tuple(item.to_dict() for item in collection)


def resolve_cli_project(
    project: Path | None,
    *,
    working_directory: Path | None = None,
) -> tuple[ProjectRoot | None, CliCommandResult | None]:
    """Resolve a CLI project and normalize resolution failures."""
    resolution = resolve_project_root(
        explicit_project=project,
        working_directory=working_directory,
    )
    if resolution.root is not None and resolution.succeeded:
        return resolution.root, None
    return None, CliCommandResult(
        {"status": "failed"},
        CliExitCode.PROJECT_RESOLUTION_FAILURE,
        _diagnostics(resolution.diagnostics),
    )


def render_result(result: CliCommandResult, *, output_format: str | None) -> None:
    """Render requested results to stdout and diagnostics to stderr."""
    if output_format == "json":
        typer.echo(json.dumps(result.data, ensure_ascii=False, sort_keys=True))
    else:
        for key, value in result.data.items():
            typer.echo(f"{key.replace('_', ' ').title()}: {value}")
    for diagnostic in result.diagnostics:
        typer.echo(
            f"{diagnostic['code']}: {diagnostic['message']}",
            err=True,
        )
