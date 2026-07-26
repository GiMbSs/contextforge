"""Read-only ports used by Context Bundle construction."""

from typing import Protocol

from contextforge.context.materialization import SourceContent
from contextforge.retrieval import SelectedContextItem


class ContextContentSource(Protocol):
    """Resolve only a retrieval-selected content reference without mutation."""

    def read(self, selected_item: SelectedContextItem) -> SourceContent:
        """Return the exact source bytes for one selected item."""
        ...
