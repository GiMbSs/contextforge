"""Immutable contracts produced and consumed by the Project Scanner."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from contextforge.configuration import ScannerConfig
from contextforge.diagnostics import DiagnosticCollection
from contextforge.domain import (
    ArtifactId,
    ArtifactPath,
    InventoryId,
    ProjectFingerprint,
    ProjectId,
)
from contextforge.project import ProjectRoot

type ArtifactMetadataValue = str | int | float | bool | None
type ArtifactMetadata = tuple[tuple[str, ArtifactMetadataValue], ...]


class ArtifactKind(StrEnum):
    """Canonical structural roles of project artifacts."""

    SOURCE = "source"
    TEST = "test"
    CONFIGURATION = "configuration"
    DOCUMENTATION = "documentation"
    MANIFEST = "manifest"
    BUILD = "build"
    DIRECTORY = "directory"
    GENERATED = "generated"
    BINARY = "binary"
    UNKNOWN = "unknown"


class ArtifactClassification(StrEnum):
    """Canonical I016 artifact processing classifications."""

    SOURCE = "source"
    TEST = "test"
    CONFIGURATION = "configuration"
    DOCUMENTATION = "documentation"
    GENERATED = "generated"
    BINARY = "binary"
    SENSITIVE = "sensitive"
    UNKNOWN = "unknown"


class ArtifactAvailability(StrEnum):
    """Discovery disposition retained by a Project Inventory."""

    INCLUDED = "included"
    EXCLUDED = "excluded"
    UNSUPPORTED = "unsupported"
    UNREADABLE = "unreadable"
    SKIPPED = "skipped"


def _normalize_metadata(metadata: ArtifactMetadata) -> ArtifactMetadata:
    normalized: list[tuple[str, ArtifactMetadataValue]] = []
    seen: set[str] = set()
    for key, value in metadata:
        normalized_key = key.strip()
        if not normalized_key:
            raise ValueError("Artifact metadata keys must not be empty")
        if normalized_key in seen:
            raise ValueError(f"Duplicate Artifact metadata key: {normalized_key}")
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise TypeError("Artifact metadata values must be scalar")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Artifact metadata values must be finite")
        seen.add(normalized_key)
        normalized.append((normalized_key, value))
    return tuple(sorted(normalized))


@dataclass(frozen=True, slots=True)
class ScanRequest:
    """Validated input required by a Project Scanner implementation."""

    project_id: ProjectId
    project_root: ProjectRoot
    configuration: ScannerConfig

    def __post_init__(self) -> None:
        if not isinstance(self.project_id, ProjectId):
            raise TypeError("project_id must be a ProjectId")
        if not isinstance(self.project_root, ProjectRoot):
            raise TypeError("project_root must be a ProjectRoot")
        if not isinstance(self.configuration, ScannerConfig):
            raise TypeError("configuration must be a ScannerConfig")


@dataclass(frozen=True, slots=True, eq=False)
class ProjectArtifact:
    """One immutable project-relative artifact description without content."""

    artifact_id: ArtifactId
    project_id: ProjectId
    path: ArtifactPath
    kind: ArtifactKind
    classifications: tuple[ArtifactClassification, ...]
    availability: ArtifactAvailability = ArtifactAvailability.INCLUDED
    metadata: ArtifactMetadata = ()

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_id, ArtifactId):
            raise TypeError("artifact_id must be an ArtifactId")
        if not isinstance(self.project_id, ProjectId):
            raise TypeError("project_id must be a ProjectId")
        if not isinstance(self.path, ArtifactPath):
            raise TypeError("path must be an ArtifactPath")
        if not isinstance(self.kind, ArtifactKind):
            raise TypeError("kind must be an ArtifactKind")
        classifications = tuple(self.classifications)
        if not classifications:
            raise ValueError("Artifact classifications must not be empty")
        if any(
            not isinstance(classification, ArtifactClassification)
            for classification in classifications
        ):
            raise TypeError("classifications must contain only ArtifactClassification values")
        if len(set(classifications)) != len(classifications):
            raise ValueError("Artifact classifications must not contain duplicates")
        if not isinstance(self.availability, ArtifactAvailability):
            raise TypeError("availability must be an ArtifactAvailability")
        object.__setattr__(
            self,
            "classifications",
            tuple(sorted(classifications, key=lambda item: item.value)),
        )
        object.__setattr__(self, "metadata", _normalize_metadata(tuple(self.metadata)))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ProjectArtifact):
            return NotImplemented
        return self.artifact_id == other.artifact_id

    def __hash__(self) -> int:
        return hash(self.artifact_id)


@dataclass(frozen=True, slots=True)
class ScanStatistics:
    """Discovery measurements that never alter scan decisions."""

    directories_visited: int = 0
    artifacts_discovered: int = 0
    artifacts_included: int = 0
    artifacts_excluded: int = 0
    unsupported_artifacts: int = 0
    unreadable_paths: int = 0
    total_bytes: int = 0
    duration_seconds: float = 0.0

    def __post_init__(self) -> None:
        counts = (
            self.directories_visited,
            self.artifacts_discovered,
            self.artifacts_included,
            self.artifacts_excluded,
            self.unsupported_artifacts,
            self.unreadable_paths,
            self.total_bytes,
        )
        if any(type(count) is not int for count in counts):
            raise TypeError("Scan statistic counts must be integers")
        if any(count < 0 for count in counts):
            raise ValueError("Scan statistics must not be negative")
        if not isinstance(self.duration_seconds, (int, float)):
            raise TypeError("duration_seconds must be numeric")
        if not math.isfinite(self.duration_seconds) or self.duration_seconds < 0:
            raise ValueError("duration_seconds must be finite and non-negative")


@dataclass(frozen=True, slots=True, eq=False)
class ProjectInventory:
    """Immutable deterministic result produced by a Project Scanner."""

    inventory_id: InventoryId
    project_id: ProjectId
    project_fingerprint: ProjectFingerprint
    artifacts: tuple[ProjectArtifact, ...]
    statistics: ScanStatistics
    discovered_at: datetime
    scanner_version: str
    applied_exclusion_rules: tuple[str, ...] = ()
    diagnostics: DiagnosticCollection = field(default_factory=DiagnosticCollection)

    def __post_init__(self) -> None:
        if not isinstance(self.inventory_id, InventoryId):
            raise TypeError("inventory_id must be an InventoryId")
        if not isinstance(self.project_id, ProjectId):
            raise TypeError("project_id must be a ProjectId")
        if not isinstance(self.project_fingerprint, ProjectFingerprint):
            raise TypeError("project_fingerprint must be a ProjectFingerprint")
        artifacts = tuple(self.artifacts)
        if any(not isinstance(artifact, ProjectArtifact) for artifact in artifacts):
            raise TypeError("artifacts must contain only ProjectArtifact values")
        if any(artifact.project_id != self.project_id for artifact in artifacts):
            raise ValueError("Every artifact must belong to the Inventory project")
        if len({artifact.artifact_id for artifact in artifacts}) != len(artifacts):
            raise ValueError("Artifact identifiers must be unique within an Inventory")
        if len({artifact.path for artifact in artifacts}) != len(artifacts):
            raise ValueError("Artifact paths must be unique within an Inventory")
        if not isinstance(self.statistics, ScanStatistics):
            raise TypeError("statistics must be ScanStatistics")
        if not isinstance(self.discovered_at, datetime):
            raise TypeError("discovered_at must be a datetime")
        if self.discovered_at.tzinfo is None or self.discovered_at.utcoffset() is None:
            raise ValueError("discovered_at must be timezone-aware")
        if not isinstance(self.scanner_version, str) or not self.scanner_version.strip():
            raise ValueError("scanner_version must not be empty")
        rules = tuple(self.applied_exclusion_rules)
        if any(not isinstance(rule, str) or not rule.strip() for rule in rules):
            raise ValueError("Applied exclusion rules must be non-empty strings")
        if not isinstance(self.diagnostics, DiagnosticCollection):
            raise TypeError("diagnostics must be a DiagnosticCollection")
        object.__setattr__(
            self,
            "artifacts",
            tuple(sorted(artifacts, key=lambda artifact: artifact.path.value)),
        )
        object.__setattr__(self, "applied_exclusion_rules", rules)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ProjectInventory):
            return NotImplemented
        return self.inventory_id == other.inventory_id

    def __hash__(self) -> int:
        return hash(self.inventory_id)
