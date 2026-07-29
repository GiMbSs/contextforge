"""Durable, versioned local storage for project inventories and indexes."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import fields
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from contextforge.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticCollection,
    DiagnosticLocation,
    DiagnosticSeverity,
)
from contextforge.domain import (
    ArtifactFingerprint,
    ArtifactId,
    ArtifactPath,
    IndexId,
    InventoryId,
    ProjectFingerprint,
    ProjectId,
)
from contextforge.indexer import (
    IndexedArtifact,
    IndexingState,
    IndexMeasurements,
    IndexStatus,
    ProjectIndex,
    Relationship,
    RelationshipKind,
    RelationshipResolution,
    SearchUnit,
    SearchUnitKind,
    SourceLocation,
    Symbol,
    SymbolKind,
)
from contextforge.project import ProjectRoot
from contextforge.scanner import (
    ArtifactAvailability,
    ArtifactClassification,
    ArtifactKind,
    DiscoveryStatus,
    ProjectArtifact,
    ProjectInventory,
    ScanStatistics,
)
from contextforge.shared import SerializationEnvelope

_SCHEMA_VERSION = "1.0"
_INVENTORY_SCHEMA = "contextforge.project_inventory"
_INDEX_SCHEMA = "contextforge.project_index"


class ProjectStateStorageError(RuntimeError):
    """A durable project-state record is malformed or cannot be persisted."""


def _object(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ProjectStateStorageError(f"{name} must be an object")
    return dict(value)


def _list(value: object, name: str) -> list[Any]:
    if not isinstance(value, (list, tuple)):
        raise ProjectStateStorageError(f"{name} must be an array")
    return list(value)


def _string(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ProjectStateStorageError(f"{name} must be a string")
    return value


def _optional_string(value: object, name: str) -> str | None:
    if value is None:
        return None
    return _string(value, name)


def _location_to_data(location: SourceLocation) -> dict[str, object]:
    return {
        "artifact_id": str(location.artifact_id),
        "end_column": location.end_column,
        "end_line": location.end_line,
        "start_column": location.start_column,
        "start_line": location.start_line,
    }


def _location_from_data(value: object) -> SourceLocation:
    item = _object(value, "source location")
    return SourceLocation(
        ArtifactId.from_string(_string(item["artifact_id"], "artifact_id")),
        cast(int, item["start_line"]),
        cast(int, item["start_column"]),
        cast(int, item["end_line"]),
        cast(int, item["end_column"]),
    )


def _diagnostics_to_data(collection: DiagnosticCollection) -> list[dict[str, object]]:
    return [diagnostic.to_dict() for diagnostic in collection]


def _diagnostics_from_data(value: object) -> DiagnosticCollection:
    diagnostics: list[Diagnostic] = []
    for raw in _list(value, "diagnostics"):
        item = _object(raw, "diagnostic")
        raw_location = item.get("location")
        location = None
        if raw_location is not None:
            location_data = _object(raw_location, "diagnostic location")
            location = DiagnosticLocation(
                _string(location_data["reference"], "reference"),
                cast(int | None, location_data.get("line")),
                cast(int | None, location_data.get("column")),
            )
        metadata = _object(item.get("metadata", {}), "diagnostic metadata")
        diagnostics.append(
            Diagnostic(
                DiagnosticCode(_string(item["code"], "diagnostic code")),
                DiagnosticSeverity(_string(item["severity"], "diagnostic severity")),
                _string(item["message"], "diagnostic message"),
                _string(item["capability"], "diagnostic capability"),
                location,
                _optional_string(item.get("guidance"), "diagnostic guidance"),
                _optional_string(item.get("technical_details"), "technical details"),
                tuple(sorted(metadata.items())),
            )
        )
    return DiagnosticCollection(tuple(diagnostics))


def _inventory_payload(inventory: ProjectInventory) -> dict[str, object]:
    return {
        "applied_exclusion_rules": list(inventory.applied_exclusion_rules),
        "artifacts": [
            {
                "artifact_id": str(artifact.artifact_id),
                "availability": artifact.availability.value,
                "classifications": [item.value for item in artifact.classifications],
                "fingerprint": (
                    str(artifact.fingerprint) if artifact.fingerprint is not None else None
                ),
                "kind": artifact.kind.value,
                "metadata": dict(artifact.metadata),
                "path": str(artifact.path),
                "project_id": str(artifact.project_id),
            }
            for artifact in inventory.artifacts
        ],
        "diagnostics": _diagnostics_to_data(inventory.diagnostics),
        "project_fingerprint": str(inventory.project_fingerprint),
        "project_id": str(inventory.project_id),
        "scanner_version": inventory.scanner_version,
        "statistics": {
            field.name: getattr(inventory.statistics, field.name)
            for field in fields(ScanStatistics)
        },
        "status": inventory.status.value,
    }


def _inventory_from_envelope(envelope: SerializationEnvelope) -> ProjectInventory:
    if envelope.schema_name != _INVENTORY_SCHEMA:
        raise ProjectStateStorageError("Record is not a project inventory")
    payload = _object(envelope.payload, "inventory payload")
    artifacts: list[ProjectArtifact] = []
    for raw in _list(payload["artifacts"], "artifacts"):
        item = _object(raw, "artifact")
        raw_fingerprint = item.get("fingerprint")
        artifacts.append(
            ProjectArtifact(
                ArtifactId.from_string(_string(item["artifact_id"], "artifact_id")),
                ProjectId.from_string(_string(item["project_id"], "project_id")),
                ArtifactPath.from_string(_string(item["path"], "artifact path")),
                ArtifactKind(_string(item["kind"], "artifact kind")),
                tuple(
                    ArtifactClassification(_string(value, "classification"))
                    for value in _list(item["classifications"], "classifications")
                ),
                ArtifactAvailability(_string(item["availability"], "availability")),
                tuple(sorted(_object(item.get("metadata", {}), "artifact metadata").items())),
                (
                    ArtifactFingerprint(_string(raw_fingerprint, "artifact fingerprint"))
                    if raw_fingerprint is not None
                    else None
                ),
            )
        )
    statistics_data = _object(payload["statistics"], "scan statistics")
    return ProjectInventory(
        InventoryId.from_string(envelope.artifact_id),
        ProjectId.from_string(_string(payload["project_id"], "project_id")),
        ProjectFingerprint(_string(payload["project_fingerprint"], "project fingerprint")),
        tuple(artifacts),
        ScanStatistics(**statistics_data),
        envelope.created_at,
        _string(payload["scanner_version"], "scanner_version"),
        tuple(
            _string(value, "exclusion rule")
            for value in _list(payload["applied_exclusion_rules"], "exclusion rules")
        ),
        _diagnostics_from_data(payload["diagnostics"]),
        DiscoveryStatus(_string(payload["status"], "discovery status")),
    )


def _index_payload(project_index: ProjectIndex) -> dict[str, object]:
    return {
        "configuration_fingerprint": project_index.configuration_fingerprint,
        "diagnostics": _diagnostics_to_data(project_index.diagnostics),
        "format_version": project_index.format_version,
        "indexed_artifacts": [
            {
                "artifact_id": str(item.artifact_id),
                "content_fingerprint": item.content_fingerprint,
                "path": str(item.path) if item.path is not None else None,
                "relationship_ids": list(item.relationship_ids),
                "search_unit_ids": list(item.search_unit_ids),
                "source_project_fingerprint": str(item.source_project_fingerprint),
                "state": item.state.value,
                "strategy": item.strategy,
                "strategy_version": item.strategy_version,
                "symbol_ids": list(item.symbol_ids),
            }
            for item in project_index.indexed_artifacts
        ],
        "indexer_version": project_index.indexer_version,
        "measurements": {
            field.name: getattr(project_index.measurements, field.name)
            for field in fields(IndexMeasurements)
        },
        "project_fingerprint": str(project_index.project_fingerprint),
        "project_id": str(project_index.project_id),
        "relationships": [
            {
                "evidence": item.evidence,
                "kind": item.kind.value,
                "location": (
                    _location_to_data(item.location) if item.location is not None else None
                ),
                "relationship_id": item.relationship_id,
                "resolution": item.resolution.value,
                "source_reference": item.source_reference,
                "target_reference": item.target_reference,
            }
            for item in project_index.relationships
        ],
        "search_units": [
            {
                "artifact_id": str(item.artifact_id),
                "content_fingerprint": item.content_fingerprint,
                "kind": item.kind.value,
                "language": item.language,
                "location": _location_to_data(item.location),
                "order": item.order,
                "search_unit_id": item.search_unit_id,
                "symbol_ids": list(item.symbol_ids),
                "text": item.text,
            }
            for item in project_index.search_units
        ],
        "source_inventory_id": str(project_index.source_inventory_id),
        "status": project_index.status.value,
        "strategy_versions": list(project_index.strategy_versions),
        "symbols": [
            {
                "artifact_id": str(item.artifact_id),
                "kind": item.kind.value,
                "language": item.language,
                "location": _location_to_data(item.location),
                "metadata": dict(item.metadata),
                "name": item.name,
                "parent_symbol_id": item.parent_symbol_id,
                "qualified_name": item.qualified_name,
                "signature": item.signature,
                "symbol_id": item.symbol_id,
            }
            for item in project_index.symbols
        ],
    }


def _index_from_envelope(envelope: SerializationEnvelope) -> ProjectIndex:
    if envelope.schema_name != _INDEX_SCHEMA:
        raise ProjectStateStorageError("Record is not a project index")
    payload = _object(envelope.payload, "index payload")
    indexed_artifacts = []
    for raw in _list(payload["indexed_artifacts"], "indexed artifacts"):
        item = _object(raw, "indexed artifact")
        path = item.get("path")
        indexed_artifacts.append(
            IndexedArtifact(
                ArtifactId.from_string(_string(item["artifact_id"], "artifact_id")),
                IndexingState(_string(item["state"], "indexing state")),
                _string(item["strategy"], "strategy"),
                _string(item["strategy_version"], "strategy version"),
                ProjectFingerprint(
                    _string(item["source_project_fingerprint"], "project fingerprint")
                ),
                tuple(map(str, _list(item["symbol_ids"], "symbol ids"))),
                tuple(map(str, _list(item["relationship_ids"], "relationship ids"))),
                tuple(map(str, _list(item["search_unit_ids"], "search unit ids"))),
                _optional_string(item.get("content_fingerprint"), "content fingerprint"),
                ArtifactPath.from_string(_string(path, "artifact path"))
                if path is not None
                else None,
            )
        )
    symbols = []
    for raw in _list(payload["symbols"], "symbols"):
        item = _object(raw, "symbol")
        symbols.append(
            Symbol(
                _string(item["symbol_id"], "symbol_id"),
                _string(item["name"], "symbol name"),
                SymbolKind(_string(item["kind"], "symbol kind")),
                ArtifactId.from_string(_string(item["artifact_id"], "artifact_id")),
                _location_from_data(item["location"]),
                _optional_string(item.get("qualified_name"), "qualified name"),
                _optional_string(item.get("signature"), "signature"),
                _optional_string(item.get("parent_symbol_id"), "parent symbol id"),
                _optional_string(item.get("language"), "language"),
                tuple(
                    (str(key), str(value))
                    for key, value in sorted(
                        _object(item.get("metadata", {}), "symbol metadata").items()
                    )
                ),
            )
        )
    relationships = []
    for raw in _list(payload["relationships"], "relationships"):
        item = _object(raw, "relationship")
        location = item.get("location")
        relationships.append(
            Relationship(
                _string(item["relationship_id"], "relationship_id"),
                _string(item["source_reference"], "source reference"),
                _string(item["target_reference"], "target reference"),
                RelationshipKind(_string(item["kind"], "relationship kind")),
                _string(item["evidence"], "relationship evidence"),
                _location_from_data(location) if location is not None else None,
                RelationshipResolution(_string(item["resolution"], "relationship resolution")),
            )
        )
    search_units = []
    for raw in _list(payload["search_units"], "search units"):
        item = _object(raw, "search unit")
        search_units.append(
            SearchUnit(
                _string(item["search_unit_id"], "search_unit_id"),
                ArtifactId.from_string(_string(item["artifact_id"], "artifact_id")),
                _location_from_data(item["location"]),
                SearchUnitKind(_string(item["kind"], "search unit kind")),
                _string(item["text"], "search unit text"),
                cast(int, item["order"]),
                tuple(map(str, _list(item["symbol_ids"], "symbol ids"))),
                _optional_string(item.get("content_fingerprint"), "content fingerprint"),
                _optional_string(item.get("language"), "language"),
            )
        )
    return ProjectIndex(
        IndexId.from_string(envelope.artifact_id),
        ProjectId.from_string(_string(payload["project_id"], "project_id")),
        InventoryId.from_string(_string(payload["source_inventory_id"], "source inventory id")),
        ProjectFingerprint(_string(payload["project_fingerprint"], "project fingerprint")),
        _string(payload["format_version"], "format version"),
        _string(payload["indexer_version"], "indexer version"),
        tuple(indexed_artifacts),
        envelope.created_at,
        tuple(symbols),
        tuple(relationships),
        tuple(search_units),
        _diagnostics_from_data(payload["diagnostics"]),
        IndexStatus(_string(payload["status"], "index status")),
        IndexMeasurements(**_object(payload["measurements"], "index measurements")),
        _optional_string(payload.get("configuration_fingerprint"), "configuration fingerprint"),
        tuple(map(str, _list(payload["strategy_versions"], "strategy versions"))),
    )


class _FilesystemStateStorage:
    def __init__(self, root: ProjectRoot, collection: str) -> None:
        self._directory = root.path / ".contextforge" / "state" / collection
        self._latest = self._directory / "latest.json"

    def _write_atomic(self, destination: Path, content: str) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        temporary = self._directory / f".{destination.name}.{uuid4().hex}.tmp"
        try:
            temporary.write_text(content, encoding="utf-8", newline="\n")
            os.replace(temporary, destination)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise ProjectStateStorageError(f"Could not persist {destination.name}") from error

    def _save(self, identity: str, project_id: ProjectId, envelope: SerializationEnvelope) -> None:
        self._write_atomic(self._directory / f"{identity}.json", envelope.to_json() + "\n")
        pointer = json.dumps(
            {"artifact_id": identity, "project_id": str(project_id), "schema_version": "1"},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        self._write_atomic(self._latest, pointer + "\n")

    def _load_envelope(self, identity: str) -> SerializationEnvelope | None:
        path = self._directory / f"{identity}.json"
        if not path.is_file():
            return None
        try:
            return SerializationEnvelope.from_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise ProjectStateStorageError(f"Invalid project-state record {path.name}") from error

    def _latest_identity(self, project_id: ProjectId) -> str | None:
        if not self._latest.is_file():
            return None
        try:
            pointer = json.loads(self._latest.read_text(encoding="utf-8"))
            data = _object(pointer, "latest pointer")
            if data.get("project_id") != str(project_id):
                return None
            return _string(data["artifact_id"], "latest artifact id")
        except (OSError, json.JSONDecodeError, TypeError, ValueError, KeyError) as error:
            raise ProjectStateStorageError("Invalid latest project-state pointer") from error


class FilesystemInventoryStorage(_FilesystemStateStorage):
    """Persist immutable inventory snapshots below ``.contextforge/state``."""

    def __init__(self, root: ProjectRoot) -> None:
        super().__init__(root, "inventories")

    def load(self, inventory_id: InventoryId) -> ProjectInventory | None:
        envelope = self._load_envelope(str(inventory_id))
        return _inventory_from_envelope(envelope) if envelope is not None else None

    def load_latest(self, project_id: ProjectId) -> ProjectInventory | None:
        identity = self._latest_identity(project_id)
        if identity is None:
            return None
        return self.load(InventoryId.from_string(identity))

    def save(self, inventory: ProjectInventory) -> None:
        envelope = SerializationEnvelope(
            _INVENTORY_SCHEMA,
            _SCHEMA_VERSION,
            str(inventory.inventory_id),
            inventory.discovered_at,
            inventory.scanner_version,
            _inventory_payload(inventory),
            {"project_id": str(inventory.project_id)},
        )
        self._save(str(inventory.inventory_id), inventory.project_id, envelope)


class FilesystemIndexStorage(_FilesystemStateStorage):
    """Persist immutable project-index snapshots below ``.contextforge/state``."""

    def __init__(self, root: ProjectRoot) -> None:
        super().__init__(root, "indexes")

    def load(self, project_id: ProjectId) -> ProjectIndex | None:
        identity = self._latest_identity(project_id)
        if identity is None:
            return None
        envelope = self._load_envelope(identity)
        project_index = _index_from_envelope(envelope) if envelope is not None else None
        if project_index is not None and project_index.project_id != project_id:
            raise ProjectStateStorageError("Latest index belongs to another project")
        return project_index

    def save(self, project_index: ProjectIndex) -> None:
        envelope = SerializationEnvelope(
            _INDEX_SCHEMA,
            _SCHEMA_VERSION,
            str(project_index.index_id),
            project_index.created_at,
            project_index.indexer_version,
            _index_payload(project_index),
            {"project_id": str(project_index.project_id)},
        )
        self._save(str(project_index.index_id), project_index.project_id, envelope)

    def remove(self, index_id: IndexId) -> None:
        path = self._directory / f"{index_id}.json"
        try:
            path.unlink(missing_ok=True)
            if self._latest.is_file():
                pointer = _object(
                    json.loads(self._latest.read_text(encoding="utf-8")),
                    "latest pointer",
                )
                if pointer.get("artifact_id") == str(index_id):
                    self._latest.unlink()
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
            raise ProjectStateStorageError(f"Could not remove index {index_id}") from error
