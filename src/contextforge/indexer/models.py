"""Provider- and parser-independent Project Index contracts."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from contextforge.diagnostics import DiagnosticCollection
from contextforge.domain import (
    ArtifactId,
    ArtifactPath,
    IndexId,
    InventoryId,
    ProjectFingerprint,
    ProjectId,
)
from contextforge.scanner import ProjectInventory


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_identifier(value: str, field_name: str) -> None:
    _require_text(value, field_name)
    if any(character.isspace() for character in value):
        raise ValueError(f"{field_name} must not contain whitespace")


class SymbolKind(StrEnum):
    """Canonical kinds of named structural elements."""

    MODULE = "module"
    NAMESPACE = "namespace"
    CLASS = "class"
    INTERFACE = "interface"
    FUNCTION = "function"
    METHOD = "method"
    PROPERTY = "property"
    VARIABLE = "variable"
    CONSTANT = "constant"
    TYPE = "type"
    IMPORT = "import"


class RelationshipKind(StrEnum):
    """Canonical deterministic project relationship kinds."""

    IMPORTS = "imports"
    REFERENCES = "references"
    DEFINES = "defines"
    CONTAINS = "contains"
    EXTENDS = "extends"
    IMPLEMENTS = "implements"
    CALLS = "calls"
    CONFIGURES = "configures"
    TESTS = "tests"
    DOCUMENTS = "documents"
    DEPENDS_ON = "depends_on"


class RelationshipResolution(StrEnum):
    """Resolution confidence for relationship targets."""

    RESOLVED_INTERNAL = "resolved_internal"
    RESOLVED_EXTERNAL = "resolved_external"
    UNRESOLVED = "unresolved"
    AMBIGUOUS = "ambiguous"


class SearchUnitKind(StrEnum):
    """Canonical kinds of bounded searchable text."""

    SYMBOL_DEFINITION = "symbol_definition"
    SOURCE_BLOCK = "source_block"
    CONFIGURATION_BLOCK = "configuration_block"
    DOCUMENTATION_SECTION = "documentation_section"
    MANIFEST_SECTION = "manifest_section"
    FILE_SUMMARY = "file_summary"
    GENERIC_TEXT_BLOCK = "generic_text_block"
    COMMENT_BLOCK = "comment_block"
    METADATA_RECORD = "metadata_record"


class IndexingState(StrEnum):
    """Outcome of indexing one inventory artifact."""

    FULLY_INDEXED = "fully_indexed"
    PARTIALLY_INDEXED = "partially_indexed"
    METADATA_ONLY = "metadata_only"
    SKIPPED = "skipped"
    FAILED = "failed"


class IndexStatus(StrEnum):
    """Completion status visible to downstream retrieval."""

    COMPLETE = "complete"
    COMPLETE_WITH_WARNINGS = "complete_with_warnings"
    INCOMPLETE = "incomplete"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SourceLocation:
    """Inclusive one-based source region inside one artifact."""

    artifact_id: ArtifactId
    start_line: int
    start_column: int
    end_line: int
    end_column: int

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_id, ArtifactId):
            raise TypeError("artifact_id must be an ArtifactId")
        positions = (self.start_line, self.start_column, self.end_line, self.end_column)
        if any(type(position) is not int for position in positions):
            raise TypeError("Source positions must be integers")
        if any(position < 1 for position in positions):
            raise ValueError("Source positions must be one-based")
        if (self.end_line, self.end_column) < (self.start_line, self.start_column):
            raise ValueError("Source location end must not precede its start")


@dataclass(frozen=True, slots=True)
class IndexedArtifact:
    """Indexing outcome for one Project Artifact."""

    artifact_id: ArtifactId
    state: IndexingState
    strategy: str
    strategy_version: str
    source_project_fingerprint: ProjectFingerprint
    symbol_ids: tuple[str, ...] = ()
    relationship_ids: tuple[str, ...] = ()
    search_unit_ids: tuple[str, ...] = ()
    content_fingerprint: str | None = None
    path: ArtifactPath | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_id, ArtifactId):
            raise TypeError("artifact_id must be an ArtifactId")
        if not isinstance(self.state, IndexingState):
            raise TypeError("state must be an IndexingState")
        _require_text(self.strategy, "strategy")
        _require_text(self.strategy_version, "strategy_version")
        if not isinstance(self.source_project_fingerprint, ProjectFingerprint):
            raise TypeError("source_project_fingerprint must be a ProjectFingerprint")
        for values, field_name in (
            (self.symbol_ids, "symbol_ids"),
            (self.relationship_ids, "relationship_ids"),
            (self.search_unit_ids, "search_unit_ids"),
        ):
            normalized = tuple(values)
            if len(set(normalized)) != len(normalized):
                raise ValueError(f"{field_name} must not contain duplicates")
            for value in normalized:
                _require_identifier(value, field_name)
            object.__setattr__(self, field_name, normalized)
        if self.content_fingerprint is not None:
            _require_text(self.content_fingerprint, "content_fingerprint")
        if self.path is not None and not isinstance(self.path, ArtifactPath):
            raise TypeError("path must be an ArtifactPath")


@dataclass(frozen=True, slots=True)
class IndexMeasurements:
    """Operational indexing measurements excluded from semantic identity."""

    artifacts_evaluated: int = 0
    artifacts_indexed: int = 0
    artifacts_skipped: int = 0
    artifacts_metadata_only: int = 0
    symbols_extracted: int = 0
    relationships_extracted: int = 0
    search_units_generated: int = 0
    total_indexed_bytes: int = 0
    parsing_failures: int = 0
    fallback_operations: int = 0

    def __post_init__(self) -> None:
        values = tuple(getattr(self, field_name) for field_name in self.__dataclass_fields__)
        if any(type(value) is not int for value in values):
            raise TypeError("Index measurements must be integers")
        if any(value < 0 for value in values):
            raise ValueError("Index measurements must not be negative")


@dataclass(frozen=True, slots=True)
class Symbol:
    """Named structural element supported by deterministic evidence."""

    symbol_id: str
    name: str
    kind: SymbolKind
    artifact_id: ArtifactId
    location: SourceLocation
    qualified_name: str | None = None
    signature: str | None = None
    parent_symbol_id: str | None = None
    language: str | None = None
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _require_identifier(self.symbol_id, "symbol_id")
        _require_text(self.name, "name")
        if not isinstance(self.kind, SymbolKind):
            raise TypeError("kind must be a SymbolKind")
        if not isinstance(self.artifact_id, ArtifactId):
            raise TypeError("artifact_id must be an ArtifactId")
        if not isinstance(self.location, SourceLocation):
            raise TypeError("location must be a SourceLocation")
        if self.location.artifact_id != self.artifact_id:
            raise ValueError("Symbol location must belong to its declaring artifact")
        for value, field_name in (
            (self.qualified_name, "qualified_name"),
            (self.signature, "signature"),
            (self.parent_symbol_id, "parent_symbol_id"),
            (self.language, "language"),
        ):
            if value is not None:
                _require_text(value, field_name)
        metadata = tuple(self.metadata)
        keys = tuple(key for key, _ in metadata)
        if len(set(keys)) != len(keys):
            raise ValueError("Symbol metadata keys must be unique")
        for key, value in metadata:
            _require_text(key, "metadata key")
            _require_text(value, "metadata value")
        object.__setattr__(self, "metadata", tuple(sorted(metadata)))


@dataclass(frozen=True, slots=True)
class Relationship:
    """Evidence-backed relationship between index entities."""

    relationship_id: str
    source_reference: str
    target_reference: str
    kind: RelationshipKind
    evidence: str
    location: SourceLocation | None = None
    resolution: RelationshipResolution = RelationshipResolution.UNRESOLVED

    def __post_init__(self) -> None:
        _require_identifier(self.relationship_id, "relationship_id")
        _require_identifier(self.source_reference, "source_reference")
        _require_identifier(self.target_reference, "target_reference")
        if not isinstance(self.kind, RelationshipKind):
            raise TypeError("kind must be a RelationshipKind")
        _require_text(self.evidence, "evidence")
        if self.location is not None and not isinstance(self.location, SourceLocation):
            raise TypeError("location must be a SourceLocation")
        if not isinstance(self.resolution, RelationshipResolution):
            raise TypeError("resolution must be a RelationshipResolution")


@dataclass(frozen=True, slots=True)
class SearchUnit:
    """Bounded text region available to later deterministic retrieval."""

    search_unit_id: str
    artifact_id: ArtifactId
    location: SourceLocation
    kind: SearchUnitKind
    text: str
    order: int
    symbol_ids: tuple[str, ...] = ()
    content_fingerprint: str | None = None
    language: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.search_unit_id, "search_unit_id")
        if not isinstance(self.artifact_id, ArtifactId):
            raise TypeError("artifact_id must be an ArtifactId")
        if not isinstance(self.location, SourceLocation):
            raise TypeError("location must be a SourceLocation")
        if self.location.artifact_id != self.artifact_id:
            raise ValueError("Search Unit location must belong to its artifact")
        if not isinstance(self.kind, SearchUnitKind):
            raise TypeError("kind must be a SearchUnitKind")
        if not isinstance(self.text, str):
            raise TypeError("text must be a string")
        if type(self.order) is not int:
            raise TypeError("order must be an integer")
        if self.order < 0:
            raise ValueError("order must not be negative")
        symbol_ids = tuple(self.symbol_ids)
        if len(set(symbol_ids)) != len(symbol_ids):
            raise ValueError("symbol_ids must not contain duplicates")
        for symbol_id in symbol_ids:
            _require_identifier(symbol_id, "symbol_ids")
        if self.content_fingerprint is not None:
            if not self.content_fingerprint.startswith("sha256:"):
                raise ValueError("content_fingerprint must use SHA-256")
            _require_text(self.content_fingerprint, "content_fingerprint")
        if self.language is not None:
            _require_text(self.language, "language")
        object.__setattr__(self, "symbol_ids", symbol_ids)


@dataclass(frozen=True, slots=True)
class IndexRequest:
    """Validated input to an Indexer implementation."""

    inventory: ProjectInventory

    def __post_init__(self) -> None:
        if not isinstance(self.inventory, ProjectInventory):
            raise TypeError("inventory must be a ProjectInventory")


@dataclass(frozen=True, slots=True)
class ProjectIndex:
    """Immutable structured knowledge derived from one Project Inventory."""

    index_id: IndexId
    project_id: ProjectId
    source_inventory_id: InventoryId
    project_fingerprint: ProjectFingerprint
    format_version: str
    indexer_version: str
    indexed_artifacts: tuple[IndexedArtifact, ...]
    created_at: datetime
    symbols: tuple[Symbol, ...] = ()
    relationships: tuple[Relationship, ...] = ()
    search_units: tuple[SearchUnit, ...] = ()
    diagnostics: DiagnosticCollection = field(default_factory=DiagnosticCollection)
    status: IndexStatus = IndexStatus.COMPLETE
    measurements: IndexMeasurements = field(default_factory=IndexMeasurements)

    def __post_init__(self) -> None:
        if not isinstance(self.index_id, IndexId):
            raise TypeError("index_id must be an IndexId")
        if not isinstance(self.project_id, ProjectId):
            raise TypeError("project_id must be a ProjectId")
        if not isinstance(self.source_inventory_id, InventoryId):
            raise TypeError("source_inventory_id must be an InventoryId")
        if not isinstance(self.project_fingerprint, ProjectFingerprint):
            raise TypeError("project_fingerprint must be a ProjectFingerprint")
        _require_text(self.format_version, "format_version")
        _require_text(self.indexer_version, "indexer_version")
        if not isinstance(self.diagnostics, DiagnosticCollection):
            raise TypeError("diagnostics must be a DiagnosticCollection")
        if not isinstance(self.status, IndexStatus):
            raise TypeError("status must be an IndexStatus")
        if not isinstance(self.measurements, IndexMeasurements):
            raise TypeError("measurements must be IndexMeasurements")
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be a datetime")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")

        indexed_artifacts = tuple(self.indexed_artifacts)
        symbols = tuple(self.symbols)
        relationships = tuple(self.relationships)
        search_units = tuple(self.search_units)
        artifact_ids = tuple(item.artifact_id for item in indexed_artifacts)
        if len(set(artifact_ids)) != len(artifact_ids):
            raise ValueError("Indexed Artifact identifiers must be unique")
        self._require_unique((item.symbol_id for item in symbols), "Symbol")
        self._require_unique(
            (item.relationship_id for item in relationships),
            "Relationship",
        )
        self._require_unique((item.search_unit_id for item in search_units), "Search Unit")
        known_artifacts = set(artifact_ids)
        if any(item.artifact_id not in known_artifacts for item in symbols):
            raise ValueError("Every Symbol must reference an indexed artifact")
        if any(item.artifact_id not in known_artifacts for item in search_units):
            raise ValueError("Every Search Unit must reference an indexed artifact")
        object.__setattr__(self, "indexed_artifacts", indexed_artifacts)
        object.__setattr__(self, "symbols", symbols)
        object.__setattr__(self, "relationships", relationships)
        object.__setattr__(self, "search_units", search_units)

    @staticmethod
    def _require_unique(values: Iterable[str], entity_name: str) -> None:
        normalized = tuple(values)
        if len(set(normalized)) != len(normalized):
            raise ValueError(f"{entity_name} identifiers must be unique")
