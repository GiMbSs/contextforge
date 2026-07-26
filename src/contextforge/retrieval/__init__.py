"""Context Retriever Core contracts."""

from contextforge.retrieval.models import (
    CandidateEligibility,
    CandidateOutcome,
    CandidateType,
    ContextBudget,
    RetrievalCandidate,
    RetrievalEvidence,
    RetrievalRequest,
    RetrievalResult,
    RetrievalStatistics,
    RetrievalStatus,
    SelectedContextItem,
    SelectionDecision,
    SelectionRationale,
    SelectionReason,
)
from contextforge.retrieval.ports import ContextRetriever
from contextforge.retrieval.query import (
    TASK_QUERY_NORMALIZER_VERSION,
    NormalizedTaskQuery,
    QueryTerm,
    QueryTermKind,
    TaskQueryNormalizer,
)

__all__ = [
    "TASK_QUERY_NORMALIZER_VERSION",
    "CandidateEligibility",
    "CandidateOutcome",
    "CandidateType",
    "ContextBudget",
    "ContextRetriever",
    "NormalizedTaskQuery",
    "QueryTerm",
    "QueryTermKind",
    "RetrievalCandidate",
    "RetrievalEvidence",
    "RetrievalRequest",
    "RetrievalResult",
    "RetrievalStatistics",
    "RetrievalStatus",
    "SelectedContextItem",
    "SelectionDecision",
    "SelectionRationale",
    "SelectionReason",
    "TaskQueryNormalizer",
]
