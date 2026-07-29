from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from contextforge.adapters.filesystem import (
    FilesystemIndexStorage,
    FilesystemInventoryStorage,
    LocalProjectScanner,
    ProjectStateStorageError,
)
from contextforge.application import (
    BuildProjectIndex,
    ProjectIndexBuild,
    ProjectScan,
    ScanProject,
)
from contextforge.configuration import ScannerConfig
from contextforge.domain import new_project_id
from contextforge.indexer import DeterministicProjectIndexer
from contextforge.project import ProjectRoot, ProjectRootSource
from contextforge.scanner import ProjectArtifact


@dataclass(slots=True)
class _ProjectSource:
    root: Path

    def read(self, artifact: ProjectArtifact) -> bytes:
        return self.root.joinpath(*artifact.path.parts).read_bytes()


def _root(path: Path) -> ProjectRoot:
    return ProjectRoot(path, ProjectRootSource.EXPLICIT)


def test_inventory_storage_round_trips_and_supports_incremental_scan(
    tmp_path: Path,
) -> None:
    (tmp_path / "module.py").write_text("def answer():\n    return 42\n", encoding="utf-8")
    root = _root(tmp_path)
    project_id = new_project_id()
    storage = FilesystemInventoryStorage(root)
    scanner = ProjectScan(
        LocalProjectScanner(),
        storage,
        ScannerConfig(exclude_patterns=(".contextforge/",)),
    )

    first = scanner.execute(ScanProject(project_id, root))
    restored = storage.load(first.inventory_id)
    second = scanner.execute(ScanProject(project_id, root))

    assert restored == first
    assert storage.load_latest(project_id) == second
    assert second.statistics.artifacts_reused == len(second.artifacts)


def test_index_storage_round_trips_and_supports_incremental_indexing(
    tmp_path: Path,
) -> None:
    (tmp_path / "module.py").write_text("def answer():\n    return 42\n", encoding="utf-8")
    root = _root(tmp_path)
    project_id = new_project_id()
    inventories = FilesystemInventoryStorage(root)
    indexes = FilesystemIndexStorage(root)
    scan = ProjectScan(
        LocalProjectScanner(),
        inventories,
        ScannerConfig(exclude_patterns=(".contextforge/",)),
    )
    index = ProjectIndexBuild(
        DeterministicProjectIndexer(_ProjectSource(tmp_path)),
        inventories,
        indexes,
    )

    first_inventory = scan.execute(ScanProject(project_id, root))
    first = index.execute(BuildProjectIndex(project_id, first_inventory.inventory_id))
    second_inventory = scan.execute(ScanProject(project_id, root))
    second = index.execute(BuildProjectIndex(project_id, second_inventory.inventory_id))

    restored = indexes.load(project_id)
    assert restored is not None
    assert restored.semantically_equivalent_to(second)
    assert first.index_id != second.index_id
    assert second.measurements.artifacts_reused == len(second.indexed_artifacts)


def test_corrupt_latest_inventory_fails_closed(tmp_path: Path) -> None:
    root = _root(tmp_path)
    project_id = new_project_id()
    latest = tmp_path / ".contextforge" / "state" / "inventories" / "latest.json"
    latest.parent.mkdir(parents=True)
    latest.write_text("{", encoding="utf-8")

    with pytest.raises(ProjectStateStorageError, match="Invalid latest"):
        FilesystemInventoryStorage(root).load_latest(project_id)
