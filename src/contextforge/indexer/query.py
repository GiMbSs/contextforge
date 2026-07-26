"""Read-only deterministic Project Index queries."""

from dataclasses import dataclass

from contextforge.domain import ArtifactId, ArtifactPath
from contextforge.indexer.models import (
    IndexedArtifact,
    ProjectIndex,
    Relationship,
    Symbol,
)


@dataclass(frozen=True, slots=True)
class ProjectIndexQuery:
    """Provide lookup without task-specific ranking or index mutation."""

    project_index: ProjectIndex

    def __post_init__(self) -> None:
        if not isinstance(self.project_index, ProjectIndex):
            raise TypeError("project_index must be a ProjectIndex")

    def find_artifact(
        self,
        reference: ArtifactId | ArtifactPath | str,
    ) -> IndexedArtifact | None:
        value = str(reference)
        return next(
            (
                artifact
                for artifact in self.project_index.indexed_artifacts
                if str(artifact.artifact_id) == value
                or (artifact.path is not None and artifact.path.value == value)
            ),
            None,
        )

    def find_symbols(self, name: str) -> tuple[Symbol, ...]:
        normalized = name.casefold()
        return tuple(
            symbol
            for symbol in self.project_index.symbols
            if symbol.name.casefold() == normalized
            or (
                symbol.qualified_name is not None and symbol.qualified_name.casefold() == normalized
            )
        )

    def find_text(self, query: str) -> tuple[str, ...]:
        if not query:
            raise ValueError("query must not be empty")
        normalized = query.casefold()
        return tuple(
            unit.search_unit_id
            for unit in self.project_index.search_units
            if normalized in unit.text.casefold()
        )

    def find_relationships(self, reference: str) -> tuple[Relationship, ...]:
        return tuple(
            relationship
            for relationship in self.project_index.relationships
            if relationship.source_reference == reference
            or relationship.target_reference == reference
        )
