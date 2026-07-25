"""Filesystem traversal contracts exposed to the Scanner Core."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from contextforge.configuration import ScannerConfig
from contextforge.diagnostics import DiagnosticCollection
from contextforge.domain import ArtifactPath
from contextforge.project import ProjectRoot
from contextforge.scanner.ignore import IgnorePolicy
from contextforge.scanner.models import ScanStatistics


class TraversalEntryType(StrEnum):
    """Filesystem entry kinds discovered without content inspection."""

    FILE = "file"
    DIRECTORY = "directory"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class TraversalEntry:
    """Project-relative metadata for one safely discovered entry."""

    path: ArtifactPath
    entry_type: TraversalEntryType
    size_bytes: int
    is_symlink: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.path, ArtifactPath):
            raise TypeError("path must be an ArtifactPath")
        if not isinstance(self.entry_type, TraversalEntryType):
            raise TypeError("entry_type must be a TraversalEntryType")
        if type(self.size_bytes) is not int:
            raise TypeError("size_bytes must be an integer")
        if self.size_bytes < 0:
            raise ValueError("size_bytes must not be negative")
        if type(self.is_symlink) is not bool:
            raise TypeError("is_symlink must be a boolean")


@dataclass(frozen=True, slots=True)
class TraversalResult:
    """Deterministic outcome of a bounded safe traversal."""

    entries: tuple[TraversalEntry, ...]
    statistics: ScanStatistics
    diagnostics: DiagnosticCollection = field(default_factory=DiagnosticCollection)
    is_complete: bool = True

    def __post_init__(self) -> None:
        entries = tuple(self.entries)
        if any(not isinstance(entry, TraversalEntry) for entry in entries):
            raise TypeError("entries must contain only TraversalEntry values")
        if len({entry.path for entry in entries}) != len(entries):
            raise ValueError("Traversal entry paths must be unique")
        if not isinstance(self.statistics, ScanStatistics):
            raise TypeError("statistics must be ScanStatistics")
        if not isinstance(self.diagnostics, DiagnosticCollection):
            raise TypeError("diagnostics must be a DiagnosticCollection")
        if type(self.is_complete) is not bool:
            raise TypeError("is_complete must be a boolean")
        object.__setattr__(
            self,
            "entries",
            tuple(sorted(entries, key=lambda entry: entry.path.value)),
        )


class ProjectTraversal(Protocol):
    """Port for safe project entry discovery."""

    def traverse(
        self,
        root: ProjectRoot,
        configuration: ScannerConfig,
        ignore_policy: IgnorePolicy,
    ) -> TraversalResult:
        """Discover eligible entry metadata beneath an authorized root."""
        ...
