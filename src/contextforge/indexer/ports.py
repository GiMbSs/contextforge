"""Project Indexer and optional persistence port contracts."""

from typing import Protocol

from contextforge.domain import IndexId, ProjectId
from contextforge.indexer.models import IndexRequest, ProjectIndex


class Indexer(Protocol):
    """Transform a Project Inventory into immutable structured knowledge."""

    def index(self, request: IndexRequest) -> ProjectIndex:
        """Produce a valid Project Index."""
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
