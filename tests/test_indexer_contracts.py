"""Tests for CF-014 increment I022 Project Indexer contracts."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from contextforge.domain import (
    ArtifactPath,
    IndexId,
    ProjectId,
    new_artifact_id,
    new_index_id,
    new_inventory_id,
    new_project_id,
)
from contextforge.domain.fingerprints import FingerprintOrdering, fingerprint_project
from contextforge.indexer import (
    IndexedArtifact,
    Indexer,
    IndexingState,
    IndexRequest,
    IndexStorage,
    ProjectIndex,
    Relationship,
    RelationshipKind,
    SearchUnit,
    SearchUnitKind,
    SourceLocation,
    Symbol,
    SymbolKind,
)
from contextforge.scanner import (
    ArtifactClassification,
    ArtifactKind,
    ProjectArtifact,
    ProjectInventory,
    ScanStatistics,
)

NOW = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)


def make_inventory() -> ProjectInventory:
    project_id = new_project_id()
    artifact = ProjectArtifact(
        new_artifact_id(),
        project_id,
        ArtifactPath("src/main.py"),
        ArtifactKind.SOURCE,
        (ArtifactClassification.SOURCE,),
    )
    return ProjectInventory(
        new_inventory_id(),
        project_id,
        fingerprint_project(("state",), ordering=FingerprintOrdering.ORDERED),
        (artifact,),
        ScanStatistics(artifacts_discovered=1, artifacts_included=1),
        NOW,
        "scanner-v1",
    )


def make_index(inventory: ProjectInventory) -> ProjectIndex:
    artifact = inventory.artifacts[0]
    location = SourceLocation(artifact.artifact_id, 1, 1, 1, 10)
    symbol = Symbol(
        "symbol_main",
        "main",
        SymbolKind.FUNCTION,
        artifact.artifact_id,
        location,
        qualified_name="main",
    )
    relationship = Relationship(
        "relationship_defines_main",
        str(artifact.artifact_id),
        symbol.symbol_id,
        RelationshipKind.DEFINES,
        "parser:function-definition",
        location,
    )
    search_unit = SearchUnit(
        "search_main",
        artifact.artifact_id,
        location,
        SearchUnitKind.SYMBOL_DEFINITION,
        "def main():",
        0,
        (symbol.symbol_id,),
    )
    indexed = IndexedArtifact(
        artifact.artifact_id,
        IndexingState.FULLY_INDEXED,
        "fake-python",
        "1",
        inventory.project_fingerprint,
        (symbol.symbol_id,),
        (relationship.relationship_id,),
        (search_unit.search_unit_id,),
    )
    return ProjectIndex(
        new_index_id(),
        inventory.project_id,
        inventory.inventory_id,
        inventory.project_fingerprint,
        "1",
        "fake-indexer-v1",
        (indexed,),
        NOW,
        (symbol,),
        (relationship,),
        (search_unit,),
    )


class FakeIndexer:
    """Contract double without parsing or content access."""

    def index(self, request: IndexRequest) -> ProjectIndex:
        return make_index(request.inventory)


class MemoryIndexStorage:
    """Persistence double without filesystem or database access."""

    def __init__(self) -> None:
        self._indexes: dict[ProjectId, ProjectIndex] = {}

    def load(self, project_id: ProjectId) -> ProjectIndex | None:
        return self._indexes.get(project_id)

    def save(self, project_index: ProjectIndex) -> None:
        self._indexes[project_index.project_id] = project_index

    def remove(self, index_id: IndexId) -> None:
        for project_id, project_index in tuple(self._indexes.items()):
            if project_index.index_id == index_id:
                del self._indexes[project_id]


def test_fake_indexer_can_produce_and_persist_valid_project_index() -> None:
    inventory = make_inventory()
    indexer: Indexer = FakeIndexer()
    storage: IndexStorage = MemoryIndexStorage()

    project_index = indexer.index(IndexRequest(inventory))
    storage.save(project_index)

    assert storage.load(inventory.project_id) == project_index
    assert project_index.source_inventory_id == inventory.inventory_id
    assert project_index.project_fingerprint == inventory.project_fingerprint


def test_index_entities_are_immutable_and_preserve_traceability() -> None:
    project_index = make_index(make_inventory())
    symbol = project_index.symbols[0]

    assert symbol.location.artifact_id == symbol.artifact_id
    with pytest.raises(FrozenInstanceError):
        symbol.name = "changed"  # type: ignore[misc]


def test_source_location_rejects_reversed_or_zero_based_positions() -> None:
    artifact_id = new_artifact_id()

    with pytest.raises(ValueError, match="one-based"):
        SourceLocation(artifact_id, 0, 1, 1, 1)
    with pytest.raises(ValueError, match="precede"):
        SourceLocation(artifact_id, 2, 1, 1, 1)


def test_project_index_rejects_duplicate_symbol_identifiers() -> None:
    inventory = make_inventory()
    valid = make_index(inventory)

    with pytest.raises(ValueError, match="Symbol identifiers"):
        ProjectIndex(
            valid.index_id,
            valid.project_id,
            valid.source_inventory_id,
            valid.project_fingerprint,
            valid.format_version,
            valid.indexer_version,
            valid.indexed_artifacts,
            valid.created_at,
            (valid.symbols[0], valid.symbols[0]),
        )


def test_project_index_rejects_unknown_artifact_references() -> None:
    inventory = make_inventory()
    valid = make_index(inventory)
    foreign_artifact_id = new_artifact_id()
    foreign_symbol = Symbol(
        "symbol_foreign",
        "foreign",
        SymbolKind.FUNCTION,
        foreign_artifact_id,
        SourceLocation(foreign_artifact_id, 1, 1, 1, 1),
    )

    with pytest.raises(ValueError, match="indexed artifact"):
        ProjectIndex(
            valid.index_id,
            valid.project_id,
            valid.source_inventory_id,
            valid.project_fingerprint,
            valid.format_version,
            valid.indexer_version,
            valid.indexed_artifacts,
            valid.created_at,
            (foreign_symbol,),
        )


def test_project_index_requires_timezone_aware_creation_timestamp() -> None:
    inventory = make_inventory()

    with pytest.raises(ValueError, match="timezone-aware"):
        ProjectIndex(
            new_index_id(),
            inventory.project_id,
            inventory.inventory_id,
            inventory.project_fingerprint,
            "1",
            "fake-indexer-v1",
            (),
            datetime(2026, 7, 25),
        )


def test_storage_double_can_remove_index() -> None:
    inventory = make_inventory()
    project_index = make_index(inventory)
    storage: IndexStorage = MemoryIndexStorage()
    storage.save(project_index)

    storage.remove(project_index.index_id)

    assert storage.load(inventory.project_id) is None
