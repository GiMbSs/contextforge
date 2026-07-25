"""Tests for CF-014 increment I021 incremental scanning."""

from __future__ import annotations

import os
from pathlib import Path

from contextforge.adapters.filesystem import LocalProjectScanner
from contextforge.configuration import ScannerConfig
from contextforge.domain import ArtifactFingerprint, new_project_id
from contextforge.project import ProjectRoot, ProjectRootSource
from contextforge.scanner import ProjectArtifact, ProjectInventory, ScanRequest


def make_request(
    root: Path,
    configuration: ScannerConfig | None = None,
) -> ScanRequest:
    return ScanRequest(
        new_project_id(),
        ProjectRoot(root.resolve(), ProjectRootSource.EXPLICIT),
        configuration or ScannerConfig(use_default_exclusions=False),
    )


def artifact_at(inventory: ProjectInventory, path: str) -> ProjectArtifact:
    return next(artifact for artifact in inventory.artifacts if artifact.path.value == path)


def test_unchanged_artifacts_are_reused_without_semantic_change(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("value = 1\n", encoding="utf-8")
    request = make_request(tmp_path)
    scanner = LocalProjectScanner()

    first = scanner.scan(request)
    second = scanner.scan(request, first)

    assert second.statistics.artifacts_reused == len(second.artifacts)
    assert first.project_fingerprint == second.project_fingerprint
    assert first.semantically_equivalent_to(second)
    assert all(
        isinstance(artifact.fingerprint, ArtifactFingerprint) for artifact in second.artifacts
    )


def test_modified_content_invalidates_only_affected_artifact(tmp_path: Path) -> None:
    changed = tmp_path / "changed.py"
    stable = tmp_path / "stable.py"
    changed.write_text("value = 1\n", encoding="utf-8")
    stable.write_text("stable = 1\n", encoding="utf-8")
    request = make_request(tmp_path)
    scanner = LocalProjectScanner()
    first = scanner.scan(request)

    changed.write_text("value = 2\n", encoding="utf-8")
    second = scanner.scan(request, first)

    assert (
        artifact_at(first, "changed.py").fingerprint
        != artifact_at(second, "changed.py").fingerprint
    )
    assert (
        artifact_at(first, "stable.py").fingerprint == artifact_at(second, "stable.py").fingerprint
    )
    assert first.project_fingerprint != second.project_fingerprint
    assert second.statistics.artifacts_reused == 1


def test_deleted_and_added_artifacts_update_inventory(tmp_path: Path) -> None:
    deleted = tmp_path / "deleted.py"
    deleted.write_text("deleted = True\n", encoding="utf-8")
    request = make_request(tmp_path)
    scanner = LocalProjectScanner()
    first = scanner.scan(request)

    deleted.unlink()
    (tmp_path / "added.py").write_text("added = True\n", encoding="utf-8")
    second = scanner.scan(request, first)
    paths = {artifact.path.value for artifact in second.artifacts}

    assert "deleted.py" not in paths
    assert "added.py" in paths
    assert first.project_fingerprint != second.project_fingerprint


def test_line_ending_change_invalidates_raw_content_fingerprint(
    tmp_path: Path,
) -> None:
    source = tmp_path / "main.py"
    source.write_bytes(b"first\nsecond\n")
    request = make_request(tmp_path)
    scanner = LocalProjectScanner()
    first = scanner.scan(request)

    source.write_bytes(b"first\r\nsecond\r\n")
    second = scanner.scan(request, first)

    before = artifact_at(first, "main.py")
    after = artifact_at(second, "main.py")
    assert (
        dict(before.metadata)["content_fingerprint"] != dict(after.metadata)["content_fingerprint"]
    )
    assert before.fingerprint != after.fingerprint
    assert second.statistics.artifacts_reused == 0


def test_timestamp_only_change_is_ignored_by_default(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text("value = 1\n", encoding="utf-8")
    request = make_request(tmp_path)
    scanner = LocalProjectScanner()
    first = scanner.scan(request)
    initial = source.stat()

    os.utime(
        source,
        ns=(initial.st_atime_ns, initial.st_mtime_ns + 2_000_000_000),
    )
    second = scanner.scan(request, first)

    assert artifact_at(first, "main.py").fingerprint == artifact_at(second, "main.py").fingerprint
    assert first.project_fingerprint == second.project_fingerprint
    assert second.statistics.artifacts_reused == 1


def test_timestamp_invalidation_can_be_enabled_explicitly(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text("value = 1\n", encoding="utf-8")
    request = make_request(
        tmp_path,
        ScannerConfig(
            use_default_exclusions=False,
            invalidate_on_timestamp_change=True,
        ),
    )
    scanner = LocalProjectScanner()
    first = scanner.scan(request)
    initial = source.stat()

    os.utime(
        source,
        ns=(initial.st_atime_ns, initial.st_mtime_ns + 2_000_000_000),
    )
    second = scanner.scan(request, first)

    assert artifact_at(first, "main.py").fingerprint != artifact_at(second, "main.py").fingerprint
    assert first.project_fingerprint != second.project_fingerprint
    assert second.statistics.artifacts_reused == 0


def test_rename_is_remove_plus_add_without_identity_guessing(tmp_path: Path) -> None:
    old_path = tmp_path / "old.py"
    old_path.write_text("value = 1\n", encoding="utf-8")
    request = make_request(tmp_path)
    scanner = LocalProjectScanner()
    first = scanner.scan(request)

    old_path.rename(tmp_path / "new.py")
    second = scanner.scan(request, first)
    old_artifact = artifact_at(first, "old.py")
    new_artifact = artifact_at(second, "new.py")

    assert old_artifact.artifact_id != new_artifact.artifact_id
    assert (
        dict(old_artifact.metadata)["content_fingerprint"]
        == dict(new_artifact.metadata)["content_fingerprint"]
    )
    assert second.statistics.artifacts_reused == 0
