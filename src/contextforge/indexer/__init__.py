"""Project Indexer Core contracts."""

from contextforge.indexer.generic import (
    GENERIC_TEXT_STRATEGY_VERSION,
    GenericTextIndexConfig,
    GenericTextIndexer,
    GenericTextIndexResult,
)
from contextforge.indexer.models import (
    IndexedArtifact,
    IndexingState,
    IndexRequest,
    IndexStatus,
    ProjectIndex,
    Relationship,
    RelationshipKind,
    SearchUnit,
    SearchUnitKind,
    SourceLocation,
    Symbol,
    SymbolKind,
)
from contextforge.indexer.ports import Indexer, IndexStorage

__all__ = [
    "GENERIC_TEXT_STRATEGY_VERSION",
    "GenericTextIndexConfig",
    "GenericTextIndexResult",
    "GenericTextIndexer",
    "IndexRequest",
    "IndexStatus",
    "IndexStorage",
    "IndexedArtifact",
    "Indexer",
    "IndexingState",
    "ProjectIndex",
    "Relationship",
    "RelationshipKind",
    "SearchUnit",
    "SearchUnitKind",
    "SourceLocation",
    "Symbol",
    "SymbolKind",
]
