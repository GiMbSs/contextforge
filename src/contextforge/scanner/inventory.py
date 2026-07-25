"""Deterministic Project Inventory construction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid5

from contextforge.diagnostics import (
    DiagnosticCollection,
    DiagnosticSeverity,
)
from contextforge.domain import (
    ArtifactId,
    FingerprintOrdering,
    InventoryId,
    ProjectId,
    fingerprint_project,
    new_inventory_id,
)
from contextforge.scanner.classification import ClassificationResult
from contextforge.scanner.ignore import IgnorePolicy
from contextforge.scanner.models import (
    ArtifactAvailability,
    DiscoveryStatus,
    ProjectArtifact,
    ProjectInventory,
    ScanRequest,
    ScanStatistics,
)
from contextforge.scanner.traversal import TraversalEntry, TraversalResult

SCANNER_VERSION = "contextforge-scanner-v1"
_ARTIFACT_NAMESPACE = UUID("a9eecc26-1368-5da7-b50b-67fb9431f50d")


@dataclass(frozen=True, slots=True)
class ClassifiedEntry:
    """A traversal entry enriched with deterministic classification."""

    entry: TraversalEntry
    classification: ClassificationResult
    availability: ArtifactAvailability = ArtifactAvailability.INCLUDED

    def __post_init__(self) -> None:
        if not isinstance(self.entry, TraversalEntry):
            raise TypeError("entry must be a TraversalEntry")
        if not isinstance(self.classification, ClassificationResult):
            raise TypeError("classification must be a ClassificationResult")
        if not isinstance(self.availability, ArtifactAvailability):
            raise TypeError("availability must be an ArtifactAvailability")


def _artifact_id(project_id: ProjectId, path: str) -> ArtifactId:
    identity = uuid5(_ARTIFACT_NAMESPACE, f"{project_id}:{path}")
    return ArtifactId(f"artifact_{identity.hex}")


def _serialized_rules(policy: IgnorePolicy) -> tuple[str, ...]:
    return tuple(
        ":".join(
            (
                rule.source.value,
                rule.action.value,
                rule.base_path.value,
                rule.pattern,
                f"directory={str(rule.directory_only).lower()}",
                f"anchored={str(rule.anchored).lower()}",
            )
        )
        for rule in policy.rules
    )


def _artifact_components(artifact: ProjectArtifact) -> tuple[str, ...]:
    metadata = ",".join(f"{key}={value!r}" for key, value in artifact.metadata)
    classifications = ",".join(item.value for item in artifact.classifications)
    return (
        f"artifact.path={artifact.path.value}",
        f"artifact.kind={artifact.kind.value}",
        f"artifact.classifications={classifications}",
        f"artifact.availability={artifact.availability.value}",
        f"artifact.metadata={metadata}",
    )


@dataclass(frozen=True, slots=True)
class ProjectInventoryBuilder:
    """Build an immutable inventory from traversal and classification results."""

    scanner_version: str = SCANNER_VERSION

    def __post_init__(self) -> None:
        if not self.scanner_version.strip():
            raise ValueError("scanner_version must not be empty")

    def build(
        self,
        request: ScanRequest,
        traversal: TraversalResult,
        classified_entries: tuple[ClassifiedEntry, ...],
        ignore_policy: IgnorePolicy,
        diagnostics: DiagnosticCollection,
        *,
        classification_complete: bool = True,
        inventory_id: InventoryId | None = None,
        discovered_at: datetime | None = None,
    ) -> ProjectInventory:
        """Construct a deterministic semantic inventory snapshot."""
        if not isinstance(request, ScanRequest):
            raise TypeError("request must be a ScanRequest")
        if not isinstance(traversal, TraversalResult):
            raise TypeError("traversal must be a TraversalResult")
        if not isinstance(ignore_policy, IgnorePolicy):
            raise TypeError("ignore_policy must be an IgnorePolicy")
        if not isinstance(diagnostics, DiagnosticCollection):
            raise TypeError("diagnostics must be a DiagnosticCollection")

        classified = tuple(classified_entries)
        if any(not isinstance(item, ClassifiedEntry) for item in classified):
            raise TypeError("classified_entries must contain ClassifiedEntry values")
        traversal_paths = {entry.path for entry in traversal.entries}
        classified_paths = {item.entry.path for item in classified}
        if classified_paths != traversal_paths or len(classified) != len(traversal.entries):
            raise ValueError("Every Traversal entry must be classified exactly once")

        artifacts = tuple(
            ProjectArtifact(
                artifact_id=_artifact_id(
                    request.project_id,
                    item.entry.path.value,
                ),
                project_id=request.project_id,
                path=item.entry.path,
                kind=item.classification.kind,
                classifications=item.classification.classifications,
                availability=item.availability,
                metadata=tuple(
                    (key, value)
                    for key, value in (
                        ("classification_evidence", "|".join(item.classification.evidence)),
                        ("detected_language", item.classification.detected_language),
                        ("encoding", item.classification.encoding),
                        ("is_symlink", item.entry.is_symlink),
                        ("size_bytes", item.entry.size_bytes),
                    )
                    if value is not None and value != ""
                ),
            )
            for item in classified
        )
        artifacts = tuple(sorted(artifacts, key=lambda artifact: artifact.path.value))
        rules = _serialized_rules(ignore_policy)
        components: list[str] = [
            f"scanner_version={self.scanner_version}",
            f"project_id={request.project_id}",
            f"scanner_configuration={request.configuration!r}",
            *(f"ignore_rule={rule}" for rule in rules),
        ]
        for artifact in artifacts:
            components.extend(_artifact_components(artifact))
        project_fingerprint = fingerprint_project(
            tuple(components),
            ordering=FingerprintOrdering.ORDERED,
        )

        unsupported = sum(artifact.kind.value == "unknown" for artifact in artifacts)
        classification_unreadable = sum(
            artifact.availability is ArtifactAvailability.UNREADABLE for artifact in artifacts
        )
        statistics = ScanStatistics(
            directories_visited=traversal.statistics.directories_visited,
            artifacts_discovered=traversal.statistics.artifacts_discovered,
            artifacts_included=traversal.statistics.artifacts_included,
            artifacts_excluded=traversal.statistics.artifacts_excluded,
            unsupported_artifacts=unsupported,
            unreadable_paths=(traversal.statistics.unreadable_paths + classification_unreadable),
            total_bytes=traversal.statistics.total_bytes,
            duration_seconds=0.0,
        )
        has_errors = any(
            item.severity in (DiagnosticSeverity.ERROR, DiagnosticSeverity.CRITICAL)
            for item in diagnostics
        )
        has_warnings = any(item.severity is DiagnosticSeverity.WARNING for item in diagnostics)
        if has_errors and not artifacts:
            status = DiscoveryStatus.FAILED
        elif not traversal.is_complete or not classification_complete or has_errors:
            status = DiscoveryStatus.INCOMPLETE
        elif has_warnings:
            status = DiscoveryStatus.COMPLETE_WITH_WARNINGS
        else:
            status = DiscoveryStatus.COMPLETE

        return ProjectInventory(
            inventory_id=inventory_id or new_inventory_id(),
            project_id=request.project_id,
            project_fingerprint=project_fingerprint,
            artifacts=artifacts,
            statistics=statistics,
            discovered_at=discovered_at or datetime.now(UTC),
            scanner_version=self.scanner_version,
            applied_exclusion_rules=rules,
            diagnostics=diagnostics,
            status=status,
        )
