"""Tests for CF-014 increment I016 Project Scanner contracts."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from pathlib import Path

import pytest

from contextforge.configuration import ScannerConfig
from contextforge.domain import (
    ArtifactPath,
    ProjectId,
    new_artifact_id,
    new_inventory_id,
    new_project_id,
)
from contextforge.domain.fingerprints import (
    FingerprintOrdering,
    fingerprint_project,
)
from contextforge.project import ProjectRoot, ProjectRootSource
from contextforge.scanner import (
    ArtifactAvailability,
    ArtifactClassification,
    ArtifactKind,
    ProjectArtifact,
    ProjectInventory,
    ProjectScanner,
    ScanRequest,
    ScanStatistics,
)


def make_artifact(
    project_id: ProjectId,
    path: str = "src/main.py",
) -> ProjectArtifact:
    return ProjectArtifact(
        artifact_id=new_artifact_id(),
        project_id=project_id,
        path=ArtifactPath(path),
        kind=ArtifactKind.SOURCE,
        classifications=(ArtifactClassification.SOURCE,),
        metadata=(("size_bytes", 42), ("language", "python")),
    )


def make_inventory(
    project_id: ProjectId,
    artifacts: tuple[ProjectArtifact, ...] = (),
) -> ProjectInventory:
    return ProjectInventory(
        inventory_id=new_inventory_id(),
        project_id=project_id,
        project_fingerprint=fingerprint_project(
            ("project-state",),
            ordering=FingerprintOrdering.ORDERED,
        ),
        artifacts=artifacts,
        statistics=ScanStatistics(
            artifacts_discovered=len(artifacts),
            artifacts_included=len(artifacts),
            total_bytes=42 * len(artifacts),
        ),
        discovered_at=datetime(2026, 7, 25, 12, 0, tzinfo=UTC),
        scanner_version="contextforge-scanner-v1",
    )


class FakeScanner:
    """Scanner test double that performs no filesystem access."""

    def scan(self, request: ScanRequest) -> ProjectInventory:
        artifact = make_artifact(request.project_id)
        return make_inventory(request.project_id, (artifact,))


def test_fake_scanner_produces_valid_inventory_without_disk_access() -> None:
    project_id = new_project_id()
    request = ScanRequest(
        project_id=project_id,
        project_root=ProjectRoot(
            Path.cwd() / "nonexistent-virtual-project",
            ProjectRootSource.EXPLICIT,
        ),
        configuration=ScannerConfig(),
    )
    scanner: ProjectScanner = FakeScanner()

    inventory = scanner.scan(request)

    assert inventory.project_id == project_id
    assert tuple(artifact.path.value for artifact in inventory.artifacts) == ("src/main.py",)


def test_artifact_classifications_are_exactly_normative_i016_values() -> None:
    assert tuple(ArtifactClassification) == (
        ArtifactClassification.SOURCE,
        ArtifactClassification.TEST,
        ArtifactClassification.CONFIGURATION,
        ArtifactClassification.DOCUMENTATION,
        ArtifactClassification.GENERATED,
        ArtifactClassification.BINARY,
        ArtifactClassification.SENSITIVE,
        ArtifactClassification.UNKNOWN,
    )


def test_artifact_kinds_match_domain_model() -> None:
    assert {kind.value for kind in ArtifactKind} == {
        "source",
        "test",
        "configuration",
        "documentation",
        "manifest",
        "build",
        "directory",
        "generated",
        "binary",
        "unknown",
    }


def test_inventory_orders_artifacts_by_canonical_path() -> None:
    project_id = new_project_id()
    artifacts = (
        make_artifact(project_id, "tests/test_main.py"),
        make_artifact(project_id, "src/main.py"),
    )

    inventory = make_inventory(project_id, artifacts)

    assert tuple(str(artifact.path) for artifact in inventory.artifacts) == (
        "src/main.py",
        "tests/test_main.py",
    )


def test_inventory_rejects_artifact_from_another_project() -> None:
    with pytest.raises(ValueError, match="belong"):
        make_inventory(new_project_id(), (make_artifact(new_project_id()),))


def test_inventory_rejects_duplicate_artifact_path() -> None:
    project_id = new_project_id()
    artifacts = (
        make_artifact(project_id),
        make_artifact(project_id),
    )

    with pytest.raises(ValueError, match="paths must be unique"):
        make_inventory(project_id, artifacts)


def test_inventory_rejects_duplicate_artifact_identifier() -> None:
    project_id = new_project_id()
    first = make_artifact(project_id)
    duplicate = ProjectArtifact(
        artifact_id=first.artifact_id,
        project_id=project_id,
        path=ArtifactPath("src/other.py"),
        kind=ArtifactKind.SOURCE,
        classifications=(ArtifactClassification.SOURCE,),
    )

    with pytest.raises(ValueError, match="identifiers must be unique"):
        make_inventory(project_id, (first, duplicate))


def test_artifact_supports_multiple_deterministic_classifications() -> None:
    artifact = ProjectArtifact(
        artifact_id=new_artifact_id(),
        project_id=new_project_id(),
        path=ArtifactPath("generated/secret.txt"),
        kind=ArtifactKind.GENERATED,
        classifications=(
            ArtifactClassification.SENSITIVE,
            ArtifactClassification.GENERATED,
        ),
        availability=ArtifactAvailability.EXCLUDED,
    )

    assert artifact.classifications == (
        ArtifactClassification.GENERATED,
        ArtifactClassification.SENSITIVE,
    )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ScanStatistics(directories_visited=-1),
        lambda: ScanStatistics(total_bytes=-1),
        lambda: ScanStatistics(duration_seconds=-1),
    ],
)
def test_scan_statistics_reject_negative_measurements(
    factory: Callable[[], ScanStatistics],
) -> None:
    with pytest.raises(ValueError, match="negative"):
        factory()


def test_inventory_requires_timezone_aware_discovery_timestamp() -> None:
    project_id = new_project_id()

    with pytest.raises(ValueError, match="timezone-aware"):
        ProjectInventory(
            inventory_id=new_inventory_id(),
            project_id=project_id,
            project_fingerprint=fingerprint_project(
                ("state",),
                ordering=FingerprintOrdering.ORDERED,
            ),
            artifacts=(),
            statistics=ScanStatistics(),
            discovered_at=datetime(2026, 7, 25),
            scanner_version="v1",
        )


def test_inventory_and_artifacts_are_immutable() -> None:
    project_id = new_project_id()
    artifact = make_artifact(project_id)
    inventory = make_inventory(project_id, (artifact,))

    with pytest.raises(FrozenInstanceError):
        artifact.path = ArtifactPath("other.py")  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        inventory.artifacts = ()  # type: ignore[misc]


def test_project_artifact_does_not_store_file_content() -> None:
    assert "content" not in ProjectArtifact.__dataclass_fields__
