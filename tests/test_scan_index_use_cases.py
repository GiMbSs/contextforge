"""Tests for application scan and index orchestration."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from contextforge.application import (
    BuildProjectIndex,
    InventoryNotFoundError,
    ProjectIndexBuild,
    ProjectScan,
    ScanProject,
)
from contextforge.configuration import ScannerConfig
from contextforge.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticCollection,
    DiagnosticSeverity,
)
from contextforge.domain import (
    FingerprintOrdering,
    IndexId,
    InventoryId,
    ProjectId,
    fingerprint_project,
    new_index_id,
    new_inventory_id,
    new_project_id,
)
from contextforge.indexer import (
    IndexMeasurements,
    IndexRequest,
    IndexStatus,
    ProjectIndex,
)
from contextforge.project import ProjectRoot, ProjectRootSource
from contextforge.scanner import (
    DiscoveryStatus,
    ProjectInventory,
    ScanRequest,
    ScanStatistics,
)


def _diagnostic(code: str) -> Diagnostic:
    return Diagnostic(
        DiagnosticCode(code),
        DiagnosticSeverity.WARNING,
        f"Diagnostic {code}",
        "test",
    )


def _inventory(
    project_id: ProjectId,
    *,
    inventory_id: InventoryId | None = None,
    diagnostics: DiagnosticCollection | None = None,
) -> ProjectInventory:
    return ProjectInventory(
        inventory_id or new_inventory_id(),
        project_id,
        fingerprint_project(("project",), ordering=FingerprintOrdering.ORDERED),
        (),
        ScanStatistics(),
        datetime.now(UTC),
        "scanner-v1",
        diagnostics=diagnostics or DiagnosticCollection(),
        status=DiscoveryStatus.COMPLETE_WITH_WARNINGS if diagnostics else DiscoveryStatus.COMPLETE,
    )


def _index(
    inventory: ProjectInventory,
    diagnostics: DiagnosticCollection | None = None,
) -> ProjectIndex:
    return ProjectIndex(
        new_index_id(),
        inventory.project_id,
        inventory.inventory_id,
        inventory.project_fingerprint,
        "1",
        "indexer-v1",
        (),
        datetime.now(UTC),
        diagnostics=diagnostics or DiagnosticCollection(),
        status=IndexStatus.COMPLETE_WITH_WARNINGS if diagnostics else IndexStatus.COMPLETE,
        measurements=IndexMeasurements(),
    )


class _InventoryStorage:
    def __init__(self, current: ProjectInventory | None = None) -> None:
        self.current = current
        self.saved: ProjectInventory | None = None

    def load(self, inventory_id: InventoryId) -> ProjectInventory | None:
        if self.current is not None and self.current.inventory_id == inventory_id:
            return self.current
        return None

    def load_latest(self, project_id: ProjectId) -> ProjectInventory | None:
        if self.current is not None and self.current.project_id == project_id:
            return self.current
        return None

    def save(self, inventory: ProjectInventory) -> None:
        self.saved = inventory
        self.current = inventory


class _IncrementalScanner:
    def __init__(self, result: ProjectInventory) -> None:
        self.result = result
        self.previous: ProjectInventory | None = None

    def scan(
        self,
        request: ScanRequest,
        previous_inventory: ProjectInventory | None = None,
    ) -> ProjectInventory:
        self.previous = previous_inventory
        return self.result


class _IndexStorage:
    def __init__(self, previous: ProjectIndex | None = None) -> None:
        self.previous = previous
        self.saved: ProjectIndex | None = None

    def load(self, project_id: ProjectId) -> ProjectIndex | None:
        return self.previous if self.previous and self.previous.project_id == project_id else None

    def save(self, project_index: ProjectIndex) -> None:
        self.saved = project_index

    def remove(self, index_id: IndexId) -> None:
        raise AssertionError("remove must not be called")


class _IncrementalIndexer:
    def __init__(self, result: ProjectIndex) -> None:
        self.result = result
        self.previous: ProjectIndex | None = None
        self.index_calls = 0

    def index(self, request: IndexRequest) -> ProjectIndex:
        self.index_calls += 1
        return self.result

    def update(
        self,
        previous_index: ProjectIndex,
        request: IndexRequest,
    ) -> ProjectIndex:
        self.previous = previous_index
        return self.result


def test_scan_reuses_latest_inventory_and_persists_result(tmp_path: Path) -> None:
    project_id = new_project_id()
    previous = _inventory(project_id)
    result = _inventory(project_id)
    scanner = _IncrementalScanner(result)
    storage = _InventoryStorage(previous)
    command = ScanProject(
        project_id,
        ProjectRoot(tmp_path.resolve(), ProjectRootSource.EXPLICIT),
    )

    returned = ProjectScan(scanner, storage, ScannerConfig()).execute(command)

    assert returned is result
    assert scanner.previous is previous
    assert storage.saved is result


def test_scan_can_preserve_equivalent_inventory_for_read_only_context(
    tmp_path: Path,
) -> None:
    project_id = new_project_id()
    previous = _inventory(project_id)
    equivalent = _inventory(project_id)
    scanner = _IncrementalScanner(equivalent)
    storage = _InventoryStorage(previous)
    command = ScanProject(
        project_id,
        ProjectRoot(tmp_path.resolve(), ProjectRootSource.EXPLICIT),
    )

    returned = ProjectScan(
        scanner,
        storage,
        ScannerConfig(),
        reuse_unchanged_inventory=True,
    ).execute(command)

    assert returned is previous
    assert storage.saved is None


def test_scan_does_not_reuse_inventory_when_diagnostics_change(tmp_path: Path) -> None:
    project_id = new_project_id()
    previous = _inventory(project_id)
    changed = _inventory(
        project_id,
        diagnostics=DiagnosticCollection((_diagnostic("SCAN_WARNING"),)),
    )
    scanner = _IncrementalScanner(changed)
    storage = _InventoryStorage(previous)
    command = ScanProject(
        project_id,
        ProjectRoot(tmp_path.resolve(), ProjectRootSource.EXPLICIT),
    )

    returned = ProjectScan(
        scanner,
        storage,
        ScannerConfig(),
        reuse_unchanged_inventory=True,
    ).execute(command)

    assert returned is changed
    assert storage.saved is changed


def test_index_reuses_prior_index_and_preserves_all_diagnostics() -> None:
    project_id = new_project_id()
    scan_diagnostic = _diagnostic("SCAN_WARNING")
    index_diagnostic = _diagnostic("INDEX_WARNING")
    inventory = _inventory(
        project_id,
        diagnostics=DiagnosticCollection((scan_diagnostic,)),
    )
    previous = _index(inventory)
    produced = _index(inventory, DiagnosticCollection((index_diagnostic,)))
    indexer = _IncrementalIndexer(produced)
    index_storage = _IndexStorage(previous)

    result = ProjectIndexBuild(
        indexer,
        _InventoryStorage(inventory),
        index_storage,
    ).execute(BuildProjectIndex(project_id, inventory.inventory_id))

    assert indexer.previous is previous
    assert indexer.index_calls == 0
    assert {str(item.code) for item in result.diagnostics} == {
        "SCAN_WARNING",
        "INDEX_WARNING",
    }
    assert index_storage.saved is result


def test_index_reports_missing_exact_inventory() -> None:
    project_id = new_project_id()
    inventory = _inventory(project_id)
    indexer = _IncrementalIndexer(_index(inventory))

    with pytest.raises(InventoryNotFoundError, match=str(inventory.inventory_id)):
        ProjectIndexBuild(indexer, _InventoryStorage(), _IndexStorage()).execute(
            BuildProjectIndex(project_id, inventory.inventory_id)
        )

    assert indexer.index_calls == 0
