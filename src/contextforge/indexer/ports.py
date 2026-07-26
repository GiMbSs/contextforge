"""Project Indexer and optional persistence port contracts."""

from typing import Protocol

from contextforge.domain import IndexId, ProjectId
from contextforge.indexer.models import IndexRequest, ProjectIndex
from contextforge.scanner import ProjectArtifact


class Indexer(Protocol):
    """Transform a Project Inventory into immutable structured knowledge."""

    def index(self, request: IndexRequest) -> ProjectIndex:
        """Produce a valid Project Index."""
        ...


class IncrementalIndexer(Indexer, Protocol):
    """Indexer capable of updating a compatible prior index."""

    def update(
        self,
        previous_index: ProjectIndex,
        request: IndexRequest,
    ) -> ProjectIndex:
        """Produce a new index while reusing compatible artifact knowledge."""
        ...


class ProjectSource(Protocol):
    """Authorized content source for artifacts already present in an Inventory."""

    def read(self, artifact: ProjectArtifact) -> bytes:
        """Return exact artifact bytes without changing project state."""
        ...


class IndexStorage(Protocol):
    """Optional persistence boundary for Project Index values."""

    def load(self, project_id: ProjectId) -> ProjectIndex | None:
        """Load the stored index for a project when one exists."""
        ...

    def save(self, project_index: ProjectIndex) -> None:
        """Persist a fully validated Project Index."""
        ...

    def remove(self, index_id: IndexId) -> None:
        """Remove a stored index by identity."""
        ...
