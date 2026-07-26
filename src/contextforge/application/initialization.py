"""Project initialization use case and filesystem-neutral port."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from contextforge.application.messages import InitializeProject
from contextforge.diagnostics import (
    DiagnosticCollection,
    DiagnosticSeverity,
)
from contextforge.project import ProjectRoot


@dataclass(frozen=True, slots=True)
class ProjectInitializationResult:
    """Observable outcome of initializing project metadata."""

    metadata_directory: Path
    configuration_file: Path | None
    metadata_created: bool = False
    configuration_created: bool = False
    diagnostics: DiagnosticCollection = field(default_factory=DiagnosticCollection)

    def __post_init__(self) -> None:
        if not isinstance(self.metadata_directory, Path):
            raise TypeError("metadata_directory must be a Path")
        if self.configuration_file is not None and not isinstance(self.configuration_file, Path):
            raise TypeError("configuration_file must be a Path when provided")
        if type(self.metadata_created) is not bool:
            raise TypeError("metadata_created must be a boolean")
        if type(self.configuration_created) is not bool:
            raise TypeError("configuration_created must be a boolean")
        if not isinstance(self.diagnostics, DiagnosticCollection):
            raise TypeError("diagnostics must be a DiagnosticCollection")

    @property
    def succeeded(self) -> bool:
        """Whether initialization completed without an error diagnostic."""
        return not any(
            item.severity in (DiagnosticSeverity.ERROR, DiagnosticSeverity.CRITICAL)
            for item in self.diagnostics
        )


class ProjectInitializationPort(Protocol):
    """Filesystem boundary required by project initialization."""

    def initialize(
        self,
        project_root: ProjectRoot,
        *,
        create_config: bool,
    ) -> ProjectInitializationResult:
        """Create project metadata without overwriting existing files."""
        ...


class ProjectInitialization:
    """Coordinate the project initialization command through an injected port."""

    def __init__(self, port: ProjectInitializationPort) -> None:
        self._port = port

    def execute(self, command: InitializeProject) -> ProjectInitializationResult:
        """Initialize only the authorized metadata location."""
        if not isinstance(command, InitializeProject):
            raise TypeError("command must be an InitializeProject")
        return self._port.initialize(
            command.project_root,
            create_config=command.create_config,
        )
