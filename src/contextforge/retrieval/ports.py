"""Context Retriever capability port."""

from typing import Protocol

from contextforge.retrieval.models import RetrievalRequest, RetrievalResult


class ContextRetriever(Protocol):
    """Select minimal sufficient context with explicit explanations."""

    def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        """Produce an immutable Retrieval Result."""
        ...
