"""Tests for CF-014 increment I020 complete Project Inventory construction."""

from pathlib import Path

from contextforge.adapters.filesystem import LocalProjectScanner
from contextforge.configuration import ScannerConfig
from contextforge.domain import new_project_id
from contextforge.project import ProjectRoot, ProjectRootSource
from contextforge.scanner import (
    ArtifactAvailability,
    ArtifactClassification,
    ArtifactKind,
    DiscoveryStatus,
    ProjectScanner,
    ScanRequest,
)


def make_request(root: Path, configuration: ScannerConfig | None = None) -> ScanRequest:
    return ScanRequest(
        project_id=new_project_id(),
        project_root=ProjectRoot(root.resolve(), ProjectRootSource.EXPLICIT),
        configuration=configuration or ScannerConfig(),
    )


def create_fixture_repository(root: Path) -> None:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "web").mkdir()
    (root / ".git").mkdir()
    (root / "src" / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (root / "tests" / "test_main.py").write_text(
        "def test_main(): pass\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text("# Fixture\n", encoding="utf-8")
    (root / ".env").write_text("TOKEN=not-exposed\n", encoding="utf-8")
    (root / "poetry.lock").write_text("[[package]]\n", encoding="utf-8")
    (root / "web" / "app.min.js").write_text("let value=1;", encoding="utf-8")
    (root / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (root / ".git" / "config").write_text("[core]\n", encoding="utf-8")


def test_complete_scanner_builds_all_inventory_fields(tmp_path: Path) -> None:
    create_fixture_repository(tmp_path)
    request = make_request(tmp_path)
    scanner: ProjectScanner = LocalProjectScanner()

    inventory = scanner.scan(request)

    assert inventory.status is DiscoveryStatus.COMPLETE
    assert inventory.project_id == request.project_id
    assert inventory.scanner_version == "contextforge-scanner-v1"
    assert inventory.project_fingerprint.value.startswith("project_sha256_")
    assert inventory.applied_exclusion_rules
    assert inventory.statistics.artifacts_included == len(inventory.artifacts)
    assert tuple(artifact.path.value for artifact in inventory.artifacts) == tuple(
        sorted(artifact.path.value for artifact in inventory.artifacts)
    )
    assert all(".git" not in artifact.path.parts for artifact in inventory.artifacts)


def test_repeated_fixture_scan_is_semantically_identical(tmp_path: Path) -> None:
    create_fixture_repository(tmp_path)
    request = make_request(tmp_path)
    scanner = LocalProjectScanner()

    first = scanner.scan(request)
    second = scanner.scan(request)

    assert first.inventory_id != second.inventory_id
    assert first.project_fingerprint == second.project_fingerprint
    assert tuple(item.artifact_id for item in first.artifacts) == tuple(
        item.artifact_id for item in second.artifacts
    )
    assert first.semantically_equivalent_to(second)


def test_inventory_contains_classifications_and_content_metadata(
    tmp_path: Path,
) -> None:
    create_fixture_repository(tmp_path)

    inventory = LocalProjectScanner().scan(make_request(tmp_path))
    artifacts = {artifact.path.value: artifact for artifact in inventory.artifacts}

    source = artifacts["src/main.py"]
    assert source.kind is ArtifactKind.SOURCE
    assert source.classifications == (ArtifactClassification.SOURCE,)
    assert dict(source.metadata)["detected_language"] == "python"
    assert dict(source.metadata)["encoding"] == "utf-8"
    assert dict(source.metadata)["size_bytes"] > 0

    test = artifacts["tests/test_main.py"]
    assert test.kind is ArtifactKind.TEST
    assert ArtifactClassification.TEST in test.classifications

    secret = artifacts[".env"]
    assert ArtifactClassification.SENSITIVE in secret.classifications
    assert "not-exposed" not in repr(secret)

    assert artifacts["poetry.lock"].kind is ArtifactKind.MANIFEST
    assert artifacts["web/app.min.js"].kind is ArtifactKind.GENERATED
    assert artifacts["logo.png"].kind is ArtifactKind.BINARY


def test_relevant_project_state_changes_fingerprint(tmp_path: Path) -> None:
    create_fixture_repository(tmp_path)
    request = make_request(tmp_path)
    scanner = LocalProjectScanner()
    before = scanner.scan(request)

    (tmp_path / "src" / "added.py").write_text("value = 1\n", encoding="utf-8")
    after = scanner.scan(request)

    assert before.project_fingerprint != after.project_fingerprint
    assert not before.semantically_equivalent_to(after)


def test_scanner_configuration_changes_fingerprint(tmp_path: Path) -> None:
    create_fixture_repository(tmp_path)
    project_id = new_project_id()
    root = ProjectRoot(tmp_path.resolve(), ProjectRootSource.EXPLICIT)
    default = LocalProjectScanner().scan(ScanRequest(project_id, root, ScannerConfig()))
    without_defaults = LocalProjectScanner().scan(
        ScanRequest(
            project_id,
            root,
            ScannerConfig(use_default_exclusions=False),
        )
    )

    assert default.project_fingerprint != without_defaults.project_fingerprint
    assert ".git/config" not in {item.path.value for item in default.artifacts}
    assert ".git/config" in {item.path.value for item in without_defaults.artifacts}


def test_oversized_file_is_retained_as_skipped_with_warning(
    tmp_path: Path,
) -> None:
    (tmp_path / "large.py").write_bytes(b"x" * 32)
    request = make_request(
        tmp_path,
        ScannerConfig(
            max_file_size_bytes=16,
            use_default_exclusions=False,
        ),
    )

    inventory = LocalProjectScanner().scan(request)

    assert inventory.status is DiscoveryStatus.COMPLETE_WITH_WARNINGS
    assert inventory.artifacts[0].availability is ArtifactAvailability.SKIPPED
    assert "SCAN_FILE_TOO_LARGE" in {str(diagnostic.code) for diagnostic in inventory.diagnostics}


def test_invalid_root_produces_failed_inventory(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    request = ScanRequest(
        new_project_id(),
        ProjectRoot(missing.absolute(), ProjectRootSource.EXPLICIT),
        ScannerConfig(use_default_exclusions=False),
    )

    inventory = LocalProjectScanner().scan(request)

    assert inventory.status is DiscoveryStatus.FAILED
    assert inventory.artifacts == ()
    assert "SCAN_ROOT_NOT_FOUND" in {str(diagnostic.code) for diagnostic in inventory.diagnostics}
