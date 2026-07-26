"""Context Retriever Core contracts."""

from contextforge.retrieval.explicit import (
    EXPLICIT_REFERENCE_STRATEGY_VERSION,
    ExplicitReferenceKind,
    ExplicitReferenceResolution,
    ExplicitReferenceResult,
    ExplicitReferenceStrategy,
    ExplicitResolutionState,
)
from contextforge.retrieval.lexical import (
    LEXICAL_SEARCH_STRATEGY_VERSION,
    LexicalSearchResult,
    LexicalSearchStrategy,
)
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
    "EXPLICIT_REFERENCE_STRATEGY_VERSION",
    "LEXICAL_SEARCH_STRATEGY_VERSION",
    "TASK_QUERY_NORMALIZER_VERSION",
    "CandidateEligibility",
    "CandidateOutcome",
    "CandidateType",
    "ContextBudget",
    "ContextRetriever",
    "ExplicitReferenceKind",
    "ExplicitReferenceResolution",
    "ExplicitReferenceResult",
    "ExplicitReferenceStrategy",
    "ExplicitResolutionState",
    "LexicalSearchResult",
    "LexicalSearchStrategy",
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
