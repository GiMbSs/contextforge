"""Scan and index orchestration through independently testable ports."""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from contextforge.application.messages import BuildProjectIndex, ScanProject
from contextforge.configuration import ScannerConfig
from contextforge.diagnostics import DiagnosticCollection
from contextforge.domain import InventoryId, ProjectId
from contextforge.indexer import (
    IncrementalIndexer,
    Indexer,
    IndexRequest,
    IndexStorage,
    ProjectIndex,
)
from contextforge.scanner import (
    IncrementalProjectScanner,
    ProjectInventory,
    ScanRequest,
)


class InventoryStorage(Protocol):
    """Persistence boundary for immutable project inventories."""

    def load(self, inventory_id: InventoryId) -> ProjectInventory | None:
        """Load an inventory by exact identity."""
        ...

    def load_latest(self, project_id: ProjectId) -> ProjectInventory | None:
        """Load the latest known inventory for incremental scanning."""
        ...

    def save(self, inventory: ProjectInventory) -> None:
        """Persist a fully constructed inventory."""
        ...


class InventoryNotFoundError(LookupError):
    """The requested inventory is unavailable to the application layer."""


def _merged_diagnostics(
    first: DiagnosticCollection,
    second: DiagnosticCollection,
) -> DiagnosticCollection:
    unique = {item.to_json(): item for item in (*first.diagnostics, *second.diagnostics)}
    return DiagnosticCollection(tuple(unique.values()))


class ProjectScan:
    """Coordinate scanning, compatible reuse, and inventory persistence."""

    def __init__(
        self,
        scanner: IncrementalProjectScanner,
        storage: InventoryStorage,
        configuration: ScannerConfig,
    ) -> None:
        if not isinstance(configuration, ScannerConfig):
            raise TypeError("configuration must be a ScannerConfig")
        self._scanner = scanner
        self._storage = storage
        self._configuration = configuration

    def execute(self, command: ScanProject) -> ProjectInventory:
        """Scan an authorized project and persist the resulting inventory."""
        if not isinstance(command, ScanProject):
            raise TypeError("command must be a ScanProject")
        request = ScanRequest(
            command.project_id,
            command.project_root,
            self._configuration,
        )
        previous = self._storage.load_latest(command.project_id)
        inventory = self._scanner.scan(request, previous)
        if inventory.project_id != command.project_id:
            raise ValueError("Scanner returned an inventory for another project")
        self._storage.save(inventory)
        return inventory


class ProjectIndexBuild:
    """Coordinate inventory lookup, incremental indexing, and persistence."""

    def __init__(
        self,
        indexer: Indexer,
        inventory_storage: InventoryStorage,
        index_storage: IndexStorage,
    ) -> None:
        self._indexer = indexer
        self._inventory_storage = inventory_storage
        self._index_storage = index_storage

    def execute(self, command: BuildProjectIndex) -> ProjectIndex:
        """Build and persist an index for the exact requested inventory."""
        if not isinstance(command, BuildProjectIndex):
            raise TypeError("command must be a BuildProjectIndex")
        inventory = self._inventory_storage.load(command.inventory_id)
        if inventory is None:
            raise InventoryNotFoundError(str(command.inventory_id))
        if inventory.project_id != command.project_id:
            raise ValueError("Inventory belongs to another project")

        request = IndexRequest(inventory)
        previous = self._index_storage.load(command.project_id)
        if previous is not None and isinstance(self._indexer, IncrementalIndexer):
            project_index = self._indexer.update(previous, request)
        else:
            project_index = self._indexer.index(request)
        if project_index.project_id != command.project_id:
            raise ValueError("Indexer returned an index for another project")
        if project_index.source_inventory_id != command.inventory_id:
            raise ValueError("Indexer returned an index for another inventory")

        diagnostics = _merged_diagnostics(inventory.diagnostics, project_index.diagnostics)
        if diagnostics != project_index.diagnostics:
            project_index = replace(project_index, diagnostics=diagnostics)
        self._index_storage.save(project_index)
        return project_index
