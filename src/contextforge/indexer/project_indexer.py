"""Complete deterministic Project Index assembly for current MVP strategies."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid5

from contextforge.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticCollection,
    DiagnosticLocation,
    DiagnosticSeverity,
)
from contextforge.domain import IndexId, ProjectFingerprint, ProjectId
from contextforge.indexer.generic import (
    GENERIC_TEXT_STRATEGY_VERSION,
    GenericTextIndexConfig,
    GenericTextIndexer,
)
from contextforge.indexer.models import (
    IndexedArtifact,
    IndexingState,
    IndexMeasurements,
    IndexRequest,
    IndexStatus,
    ProjectIndex,
    Relationship,
    SearchUnit,
    Symbol,
)
from contextforge.indexer.ports import ProjectSource
from contextforge.indexer.python_ast import (
    PYTHON_AST_STRATEGY_VERSION,
    PythonAstParser,
)
from contextforge.indexer.python_relationships import (
    PYTHON_RELATIONSHIP_STRATEGY_VERSION,
    PythonRelationshipBuilder,
)
from contextforge.indexer.python_search import (
    PYTHON_SEARCH_STRATEGY_VERSION,
    PythonSearchConfig,
    PythonSearchUnitBuilder,
)
from contextforge.indexer.python_symbols import (
    PYTHON_SYMBOL_STRATEGY_VERSION,
    PythonSymbolBuilder,
)
from contextforge.scanner import (
    ArtifactAvailability,
    ArtifactClassification,
    ArtifactKind,
    ProjectArtifact,
)

INDEX_FORMAT_VERSION = "1"
INDEXER_VERSION = "contextforge-indexer-v1"
_INDEX_NAMESPACE = UUID("6604e2ae-2295-5b46-aaf7-7ec8f17e6f35")


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class ProjectIndexerConfig:
    """Effective policy for complete Project Index construction."""

    max_artifact_bytes: int = 1_000_000
    max_search_unit_bytes: int = 4_096
    enable_generic_text: bool = True
    index_sensitive_content: bool = False

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.max_artifact_bytes, "max_artifact_bytes"),
            (self.max_search_unit_bytes, "max_search_unit_bytes"),
        ):
            if type(value) is not int:
                raise TypeError(f"{field_name} must be an integer")
            if value < 4:
                raise ValueError(f"{field_name} must be at least 4 bytes")
        if type(self.enable_generic_text) is not bool:
            raise TypeError("enable_generic_text must be a boolean")
        if type(self.index_sensitive_content) is not bool:
            raise TypeError("index_sensitive_content must be a boolean")


def _diagnostic(
    artifact: ProjectArtifact,
    code: str,
    message: str,
    severity: DiagnosticSeverity = DiagnosticSeverity.WARNING,
) -> Diagnostic:
    return Diagnostic(
        DiagnosticCode(code),
        severity,
        message,
        "indexer",
        DiagnosticLocation(artifact.path.value),
    )


def _content_fingerprint(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _metadata_fingerprint(artifact: ProjectArtifact) -> str | None:
    value = dict(artifact.metadata).get("content_fingerprint")
    return value if isinstance(value, str) else None


def _is_python(artifact: ProjectArtifact) -> bool:
    language = dict(artifact.metadata).get("detected_language")
    return language == "python" or artifact.path.parts[-1].casefold().endswith(".py")


def _index_id(request: IndexRequest, configuration: ProjectIndexerConfig) -> IndexId:
    identity = uuid5(
        _INDEX_NAMESPACE,
        ":".join(
            (
                str(request.inventory.project_id),
                str(request.inventory.inventory_id),
                str(request.inventory.project_fingerprint),
                INDEX_FORMAT_VERSION,
                INDEXER_VERSION,
                repr(configuration),
                PYTHON_AST_STRATEGY_VERSION,
                PYTHON_SYMBOL_STRATEGY_VERSION,
                PYTHON_RELATIONSHIP_STRATEGY_VERSION,
                PYTHON_SEARCH_STRATEGY_VERSION,
                GENERIC_TEXT_STRATEGY_VERSION,
            )
        ),
    )
    return IndexId(f"index_{identity.hex}")


@dataclass(slots=True)
class DeterministicProjectIndexer:
    """Build a complete immutable index from an Inventory and content port."""

    source: ProjectSource
    configuration: ProjectIndexerConfig = field(default_factory=ProjectIndexerConfig)
    clock: Callable[[], datetime] = _utc_now

    def index(self, request: IndexRequest) -> ProjectIndex:
        """Index every inventory artifact independently and honestly."""
        if not isinstance(request, IndexRequest):
            raise TypeError("request must be an IndexRequest")
        inventory = request.inventory
        indexed_artifacts: list[IndexedArtifact] = []
        symbols: list[Symbol] = []
        relationships: list[Relationship] = []
        search_units: list[SearchUnit] = []
        diagnostics = list(inventory.diagnostics)
        incomplete = False
        fallback_operations = 0
        parsing_failures = 0
        indexed_bytes = 0

        for artifact in inventory.artifacts:
            artifact_symbols: tuple[Symbol, ...] = ()
            artifact_relationships: tuple[Relationship, ...] = ()
            artifact_units: tuple[SearchUnit, ...] = ()
            strategy = "metadata-only"
            strategy_version = INDEXER_VERSION
            state = IndexingState.METADATA_ONLY
            fingerprint = _metadata_fingerprint(artifact)

            if artifact.availability is not ArtifactAvailability.INCLUDED:
                strategy = "skip"
                state = IndexingState.SKIPPED
            elif artifact.kind is ArtifactKind.BINARY:
                strategy = "skip-binary"
                state = IndexingState.SKIPPED
            elif artifact.kind is ArtifactKind.DIRECTORY:
                strategy = "metadata-only-directory"
            elif (
                ArtifactClassification.SENSITIVE in artifact.classifications
                and not self.configuration.index_sensitive_content
            ):
                strategy = "skip-sensitive"
                state = IndexingState.SKIPPED
            else:
                try:
                    content = self.source.read(artifact)
                except (OSError, LookupError):
                    diagnostics.append(
                        _diagnostic(
                            artifact,
                            "INDEX_SOURCE_UNAVAILABLE",
                            "Artifact content was unavailable from the Project Source.",
                        )
                    )
                    state = IndexingState.FAILED
                    strategy = "source-unavailable"
                    incomplete = True
                else:
                    actual_fingerprint = _content_fingerprint(content)
                    if fingerprint is not None and fingerprint != actual_fingerprint:
                        diagnostics.append(
                            _diagnostic(
                                artifact,
                                "INDEX_PROJECT_STATE_MISMATCH",
                                "Artifact content does not match its Inventory fingerprint.",
                                DiagnosticSeverity.ERROR,
                            )
                        )
                        state = IndexingState.FAILED
                        strategy = "state-mismatch"
                        incomplete = True
                    elif len(content) > self.configuration.max_artifact_bytes:
                        diagnostics.append(
                            _diagnostic(
                                artifact,
                                "INDEX_ARTIFACT_SIZE_LIMIT",
                                "Artifact exceeded the configured indexing size limit.",
                            )
                        )
                        fingerprint = actual_fingerprint
                        strategy = "metadata-only-size-limit"
                        incomplete = True
                    elif _is_python(artifact):
                        (
                            state,
                            strategy,
                            strategy_version,
                            artifact_symbols,
                            artifact_relationships,
                            artifact_units,
                            artifact_diagnostics,
                        ) = self._index_python(artifact, content)
                        diagnostics.extend(artifact_diagnostics)
                        fingerprint = actual_fingerprint
                        indexed_bytes += len(content)
                        if state is IndexingState.FAILED:
                            parsing_failures += 1
                            incomplete = True
                    elif self.configuration.enable_generic_text:
                        generic = GenericTextIndexer(
                            GenericTextIndexConfig(
                                max_content_bytes=self.configuration.max_artifact_bytes,
                                max_search_unit_bytes=self.configuration.max_search_unit_bytes,
                            )
                        ).index_artifact(artifact, content)
                        artifact_units = generic.search_units
                        diagnostics.extend(generic.diagnostics)
                        fingerprint = actual_fingerprint
                        strategy = "generic-text"
                        strategy_version = GENERIC_TEXT_STRATEGY_VERSION
                        fallback_operations += 1
                        if generic.diagnostics.diagnostics:
                            state = IndexingState.METADATA_ONLY
                            incomplete = True
                        else:
                            state = IndexingState.FULLY_INDEXED
                            indexed_bytes += generic.indexed_bytes

            symbols.extend(artifact_symbols)
            relationships.extend(artifact_relationships)
            search_units.extend(artifact_units)
            indexed_artifacts.append(
                IndexedArtifact(
                    artifact.artifact_id,
                    state,
                    strategy,
                    strategy_version,
                    inventory.project_fingerprint,
                    tuple(item.symbol_id for item in artifact_symbols),
                    tuple(item.relationship_id for item in artifact_relationships),
                    tuple(item.search_unit_id for item in artifact_units),
                    fingerprint,
                    artifact.path,
                )
            )

        symbols.sort(
            key=lambda item: (
                item.artifact_id.value,
                item.location.start_line,
                item.location.start_column,
                item.qualified_name or item.name,
            )
        )
        relationships.sort(
            key=lambda item: (
                item.source_reference,
                item.kind.value,
                item.target_reference,
                item.relationship_id,
            )
        )
        search_units.sort(
            key=lambda item: (
                item.artifact_id.value,
                item.location.start_line,
                item.location.start_column,
                item.order,
            )
        )
        diagnostics_collection = DiagnosticCollection(tuple(diagnostics))
        has_warnings = bool(diagnostics_collection.diagnostics)
        status = (
            IndexStatus.INCOMPLETE
            if incomplete
            else (IndexStatus.COMPLETE_WITH_WARNINGS if has_warnings else IndexStatus.COMPLETE)
        )
        measurements = IndexMeasurements(
            artifacts_evaluated=len(inventory.artifacts),
            artifacts_indexed=sum(
                item.state in (IndexingState.FULLY_INDEXED, IndexingState.PARTIALLY_INDEXED)
                for item in indexed_artifacts
            ),
            artifacts_skipped=sum(
                item.state is IndexingState.SKIPPED for item in indexed_artifacts
            ),
            artifacts_metadata_only=sum(
                item.state is IndexingState.METADATA_ONLY for item in indexed_artifacts
            ),
            symbols_extracted=len(symbols),
            relationships_extracted=len(relationships),
            search_units_generated=len(search_units),
            total_indexed_bytes=indexed_bytes,
            parsing_failures=parsing_failures,
            fallback_operations=fallback_operations,
        )
        return ProjectIndex(
            _index_id(request, self.configuration),
            inventory.project_id,
            inventory.inventory_id,
            inventory.project_fingerprint,
            INDEX_FORMAT_VERSION,
            INDEXER_VERSION,
            tuple(indexed_artifacts),
            self.clock(),
            tuple(symbols),
            tuple(relationships),
            tuple(search_units),
            diagnostics_collection,
            status,
            measurements,
        )

    def _index_python(
        self,
        artifact: ProjectArtifact,
        content: bytes,
    ) -> tuple[
        IndexingState,
        str,
        str,
        tuple[Symbol, ...],
        tuple[Relationship, ...],
        tuple[SearchUnit, ...],
        tuple[Diagnostic, ...],
    ]:
        parsed = PythonAstParser().parse(artifact, content)
        symbol_result = PythonSymbolBuilder().build(parsed)
        relationship_result = PythonRelationshipBuilder().build(parsed, symbol_result)
        search_result = PythonSearchUnitBuilder(
            PythonSearchConfig(self.configuration.max_search_unit_bytes)
        ).build(parsed, symbol_result, content)
        if parsed.module is None:
            return (
                IndexingState.FAILED,
                "python-ast",
                PYTHON_AST_STRATEGY_VERSION,
                (),
                (),
                (),
                tuple(parsed.diagnostics),
            )
        return (
            IndexingState.FULLY_INDEXED,
            "python-ast",
            PYTHON_SEARCH_STRATEGY_VERSION,
            symbol_result.symbols,
            relationship_result.relationships,
            search_result.search_units,
            tuple(parsed.diagnostics),
        )


@dataclass(slots=True)
class InMemoryIndexStorage:
    """Atomic immutable-index storage suitable for embedding and tests."""

    _indexes: dict[ProjectId, ProjectIndex] = field(default_factory=dict)

    def load(self, project_id: ProjectId) -> ProjectIndex | None:
        if not isinstance(project_id, ProjectId):
            raise TypeError("project_id must be a ProjectId")
        return self._indexes.get(project_id)

    def save(self, project_index: ProjectIndex) -> None:
        if not isinstance(project_index, ProjectIndex):
            raise TypeError("project_index must be a ProjectIndex")
        replacement = dict(self._indexes)
        replacement[project_index.project_id] = project_index
        self._indexes = replacement

    def remove(self, index_id: IndexId) -> None:
        if not isinstance(index_id, IndexId):
            raise TypeError("index_id must be an IndexId")
        self._indexes = {
            project_id: project_index
            for project_id, project_index in self._indexes.items()
            if project_index.index_id != index_id
        }

    def load_compatible(
        self,
        project_id: ProjectId,
        project_fingerprint: ProjectFingerprint,
        format_version: str = INDEX_FORMAT_VERSION,
    ) -> ProjectIndex | None:
        candidate = self.load(project_id)
        if candidate is None:
            return None
        if (
            candidate.project_fingerprint != project_fingerprint
            or candidate.format_version != format_version
        ):
            return None
        return candidate
