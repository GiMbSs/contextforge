"""Deterministic project root resolution."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from contextforge.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticCollection,
    DiagnosticLocation,
    DiagnosticSeverity,
)

_METADATA_DIRECTORY = ".contextforge"


class ProjectRootSource(StrEnum):
    """Reason a project root was selected."""

    EXPLICIT = "explicit"
    METADATA_PARENT = "metadata_parent"
    WORKING_DIRECTORY = "working_directory"


@dataclass(frozen=True, slots=True)
class ProjectRoot:
    """One normalized absolute authorized project root."""

    path: Path
    source: ProjectRootSource

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path):
            raise TypeError("path must be a Path")
        if not self.path.is_absolute():
            raise ValueError("Project root must be absolute")
        if not isinstance(self.source, ProjectRootSource):
            raise TypeError("source must be a ProjectRootSource")

    def __str__(self) -> str:
        return str(self.path)


@dataclass(frozen=True, slots=True)
class ProjectRootResolution:
    """Outcome of resolving an authorized project root."""

    root: ProjectRoot | None
    diagnostics: DiagnosticCollection = field(default_factory=DiagnosticCollection)

    @property
    def succeeded(self) -> bool:
        """Whether a project root was resolved without errors."""
        return self.root is not None and not any(
            diagnostic.severity in (DiagnosticSeverity.ERROR, DiagnosticSeverity.CRITICAL)
            for diagnostic in self.diagnostics
        )


def _failure(reference: Path, message: str) -> ProjectRootResolution:
    diagnostic = Diagnostic(
        code=DiagnosticCode("CLI_PROJECT_NOT_FOUND"),
        severity=DiagnosticSeverity.ERROR,
        message=message,
        capability="project_resolution",
        location=DiagnosticLocation(str(reference)),
        guidance="Provide a valid project directory with --project.",
    )
    return ProjectRootResolution(None, DiagnosticCollection((diagnostic,)))


def _resolved_directory(path: Path) -> Path | None:
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if not resolved.is_dir() or not os.access(resolved, os.R_OK):
        return None
    try:
        stable = resolved.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    return resolved if stable == resolved else None


def _metadata_parent(working_directory: Path) -> Path | None:
    for candidate in (working_directory, *working_directory.parents):
        metadata = candidate / _METADATA_DIRECTORY
        try:
            if metadata.is_dir():
                return candidate
        except OSError:
            continue
    return None


def resolve_project_root(
    *,
    explicit_project: str | Path | None = None,
    working_directory: str | Path | None = None,
) -> ProjectRootResolution:
    """Resolve a project root using the approved deterministic precedence."""
    cwd_input = Path.cwd() if working_directory is None else Path(working_directory)

    if explicit_project is not None:
        explicit_input = Path(explicit_project)
        candidate = explicit_input if explicit_input.is_absolute() else cwd_input / explicit_input
        resolved = _resolved_directory(candidate)
        if resolved is None:
            return _failure(candidate, "Explicit project root is invalid or unreadable.")
        return ProjectRootResolution(ProjectRoot(resolved, ProjectRootSource.EXPLICIT))

    resolved_cwd = _resolved_directory(cwd_input)
    if resolved_cwd is None:
        return _failure(cwd_input, "Project root could not be resolved.")

    metadata_parent = _metadata_parent(resolved_cwd)
    if metadata_parent is not None:
        return ProjectRootResolution(
            ProjectRoot(metadata_parent, ProjectRootSource.METADATA_PARENT)
        )

    return ProjectRootResolution(ProjectRoot(resolved_cwd, ProjectRootSource.WORKING_DIRECTORY))
