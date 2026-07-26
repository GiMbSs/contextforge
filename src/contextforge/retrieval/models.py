"""Immutable, strategy-independent Context Retriever contracts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from contextforge.diagnostics import DiagnosticCollection
from contextforge.domain import (
    ArtifactId,
    IndexId,
    ProjectFingerprint,
    RetrievalId,
    TaskId,
)
from contextforge.domain.tasks import TaskSpecification
from contextforge.indexer import ProjectIndex, SourceLocation


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_identifier(value: str, field_name: str) -> None:
    _require_text(value, field_name)
    if any(character.isspace() for character in value):
        raise ValueError(f"{field_name} must not contain whitespace")


class CandidateType(StrEnum):
    """Canonical forms of retrievable context."""

    FULL_ARTIFACT = "full_artifact"
    STRUCTURAL_UNIT = "structural_unit"
    SYMBOL_DEFINITION = "symbol_definition"
    SOURCE_EXCERPT = "source_excerpt"
    CONFIGURATION_BLOCK = "configuration_block"
    DOCUMENTATION_SECTION = "documentation_section"
    MANIFEST_SECTION = "manifest_section"
    TEST_ARTIFACT = "test_artifact"
    RELATED_DECLARATION = "related_declaration"
    DEPENDENCY_RECORD = "dependency_record"
    RELATIONSHIP_SUMMARY = "relationship_summary"
    PROJECT_SUMMARY = "project_summary"
    USER_PROVIDED_CONTENT = "user_provided_content"


class CandidateEligibility(StrEnum):
    """Whether policy permits a candidate to enter selection."""

    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    PROHIBITED = "prohibited"
    UNAVAILABLE = "unavailable"


class CandidateOutcome(StrEnum):
    """Final observable disposition of a candidate."""

    SELECTED = "selected"
    EXCLUDED = "excluded"
    DEFERRED = "deferred"
    TRUNCATED = "truncated"


class SelectionDecision(StrEnum):
    """Canonical rationale decisions."""

    SELECTED = "selected"
    EXCLUDED = "excluded"
    DEFERRED = "deferred"


class SelectionReason(StrEnum):
    """Stable MVP reason codes for inclusion or exclusion."""

    EXPLICIT_PATH_REFERENCE = "EXPLICIT_PATH_REFERENCE"
    EXPLICIT_SYMBOL_REFERENCE = "EXPLICIT_SYMBOL_REFERENCE"
    ERROR_LOCATION_REFERENCE = "ERROR_LOCATION_REFERENCE"
    EXACT_PATH_MATCH = "EXACT_PATH_MATCH"
    PARTIAL_PATH_MATCH = "PARTIAL_PATH_MATCH"
    EXACT_SYMBOL_MATCH = "EXACT_SYMBOL_MATCH"
    LEXICAL_CONTENT_MATCH = "LEXICAL_CONTENT_MATCH"
    DECLARATION_RELATIONSHIP = "DECLARATION_RELATIONSHIP"
    DEPENDENCY_RELATIONSHIP = "DEPENDENCY_RELATIONSHIP"
    REFERENCE_RELATIONSHIP = "REFERENCE_RELATIONSHIP"
    CALL_RELATIONSHIP = "CALL_RELATIONSHIP"
    INHERITANCE_RELATIONSHIP = "INHERITANCE_RELATIONSHIP"
    TEST_RELATIONSHIP = "TEST_RELATIONSHIP"
    CONFIGURATION_RELATIONSHIP = "CONFIGURATION_RELATIONSHIP"
    DOCUMENTATION_RELATIONSHIP = "DOCUMENTATION_RELATIONSHIP"
    SOURCE_LOCALITY = "SOURCE_LOCALITY"
    REQUIRED_CONTEXT = "REQUIRED_CONTEXT"
    USER_PROVIDED_CONTEXT = "USER_PROVIDED_CONTEXT"
    BELOW_RELEVANCE_THRESHOLD = "BELOW_RELEVANCE_THRESHOLD"
    DUPLICATE_CONTENT = "DUPLICATE_CONTENT"
    CONTEXT_BUDGET_EXCEEDED = "CONTEXT_BUDGET_EXCEEDED"
    SECURITY_PROHIBITED = "SECURITY_PROHIBITED"
    ARTIFACT_POLICY_EXCLUDED = "ARTIFACT_POLICY_EXCLUDED"
    CONTENT_UNAVAILABLE = "CONTENT_UNAVAILABLE"
    GENERATED_DEPRIORITIZED = "GENERATED_DEPRIORITIZED"
    DEFERRED_AMBIGUITY = "DEFERRED_AMBIGUITY"


class RetrievalStatus(StrEnum):
    """Completion state of a Retrieval Result."""

    COMPLETE = "complete"
    COMPLETE_WITH_WARNINGS = "complete_with_warnings"
    INCOMPLETE = "incomplete"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ContextBudget:
    """Hard provider-neutral context limits."""

    max_estimated_tokens: int | None = None
    max_characters: int | None = None
    max_bytes: int | None = None
    max_artifacts: int | None = None
    max_excerpts: int | None = None
    max_item_bytes: int | None = None
    max_items: int | None = None

    def __post_init__(self) -> None:
        for field_name in self.__dataclass_fields__:
            value = getattr(self, field_name)
            if value is not None:
                if type(value) is not int:
                    raise TypeError(f"{field_name} must be an integer")
                if value < 1:
                    raise ValueError(f"{field_name} must be positive")


@dataclass(frozen=True, slots=True)
class RetrievalEvidence:
    """One deterministic observation supporting a candidate decision."""

    evidence_type: str
    source: str
    detail: str
    weight: float | None = None

    def __post_init__(self) -> None:
        _require_text(self.evidence_type, "evidence_type")
        _require_text(self.source, "source")
        _require_text(self.detail, "detail")
        if self.weight is not None:
            if not isinstance(self.weight, (int, float)):
                raise TypeError("weight must be numeric")
            if not math.isfinite(self.weight):
                raise ValueError("weight must be finite")


@dataclass(frozen=True, slots=True)
class SelectionRationale:
    """Explain one selected, excluded, or deferred decision."""

    candidate_id: str
    decision: SelectionDecision
    primary_reason: SelectionReason
    evidence: tuple[RetrievalEvidence, ...]
    score: float | None = None
    rank: int | None = None
    explanation: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.candidate_id, "candidate_id")
        if not isinstance(self.decision, SelectionDecision):
            raise TypeError("decision must be a SelectionDecision")
        if not isinstance(self.primary_reason, SelectionReason):
            raise TypeError("primary_reason must be a SelectionReason")
        evidence = tuple(self.evidence)
        if not evidence:
            raise ValueError("Selection Rationale must contain evidence")
        if any(not isinstance(item, RetrievalEvidence) for item in evidence):
            raise TypeError("evidence must contain RetrievalEvidence values")
        if self.score is not None:
            if not isinstance(self.score, (int, float)):
                raise TypeError("score must be numeric")
            if not math.isfinite(self.score):
                raise ValueError("score must be finite")
        if self.rank is not None:
            if type(self.rank) is not int:
                raise TypeError("rank must be an integer")
            if self.rank < 1:
                raise ValueError("rank must be positive")
        if self.explanation is not None:
            _require_text(self.explanation, "explanation")
        object.__setattr__(self, "evidence", evidence)


@dataclass(frozen=True, slots=True)
class RetrievalCandidate:
    """One possible context inclusion with its final disposition."""

    candidate_id: str
    candidate_type: CandidateType
    source_reference: str
    content_reference: str
    evidence: tuple[RetrievalEvidence, ...]
    eligibility: CandidateEligibility
    outcome: CandidateOutcome
    estimated_bytes: int
    estimated_tokens: int | None = None
    artifact_id: ArtifactId | None = None
    location: SourceLocation | None = None
    rationale: SelectionRationale | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.candidate_id, "candidate_id")
        if not isinstance(self.candidate_type, CandidateType):
            raise TypeError("candidate_type must be a CandidateType")
        _require_text(self.source_reference, "source_reference")
        _require_text(self.content_reference, "content_reference")
        evidence = tuple(self.evidence)
        if not evidence:
            raise ValueError("Retrieval Candidate must contain evidence")
        if any(not isinstance(item, RetrievalEvidence) for item in evidence):
            raise TypeError("evidence must contain RetrievalEvidence values")
        if not isinstance(self.eligibility, CandidateEligibility):
            raise TypeError("eligibility must be a CandidateEligibility")
        if not isinstance(self.outcome, CandidateOutcome):
            raise TypeError("outcome must be a CandidateOutcome")
        for value, field_name in (
            (self.estimated_bytes, "estimated_bytes"),
            (self.estimated_tokens, "estimated_tokens"),
        ):
            if value is not None:
                if type(value) is not int:
                    raise TypeError(f"{field_name} must be an integer")
                if value < 0:
                    raise ValueError(f"{field_name} must not be negative")
        if self.artifact_id is not None and not isinstance(self.artifact_id, ArtifactId):
            raise TypeError("artifact_id must be an ArtifactId")
        if self.location is not None:
            if not isinstance(self.location, SourceLocation):
                raise TypeError("location must be a SourceLocation")
            if self.artifact_id != self.location.artifact_id:
                raise ValueError("Candidate location must belong to its artifact")
        if self.rationale is not None:
            if not isinstance(self.rationale, SelectionRationale):
                raise TypeError("rationale must be a SelectionRationale")
            if self.rationale.candidate_id != self.candidate_id:
                raise ValueError("Candidate rationale must reference the candidate")
            expected_decision = {
                CandidateOutcome.SELECTED: SelectionDecision.SELECTED,
                CandidateOutcome.TRUNCATED: SelectionDecision.SELECTED,
                CandidateOutcome.EXCLUDED: SelectionDecision.EXCLUDED,
                CandidateOutcome.DEFERRED: SelectionDecision.DEFERRED,
            }[self.outcome]
            if self.rationale.decision is not expected_decision:
                raise ValueError("Candidate outcome must match its rationale decision")
        if self.eligibility is not CandidateEligibility.ELIGIBLE and self.outcome in (
            CandidateOutcome.SELECTED,
            CandidateOutcome.TRUNCATED,
        ):
            raise ValueError("Ineligible candidates must not be selected")
        object.__setattr__(self, "evidence", evidence)


@dataclass(frozen=True, slots=True)
class SelectedContextItem:
    """One candidate approved for later Context Bundle construction."""

    context_item_id: str
    candidate_id: str
    artifact_id: ArtifactId | None
    content_reference: str
    candidate_type: CandidateType
    rationale: SelectionRationale
    location: SourceLocation | None = None
    estimated_tokens: int | None = None
    content_fingerprint: str | None = None
    is_truncated: bool = False
    estimated_bytes: int | None = None
    estimated_characters: int | None = None
    score_breakdown: tuple[tuple[str, float], ...] = ()
    sensitivity_classification: str = "unclassified"
    dependency_path: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier(self.context_item_id, "context_item_id")
        _require_identifier(self.candidate_id, "candidate_id")
        if self.artifact_id is not None and not isinstance(self.artifact_id, ArtifactId):
            raise TypeError("artifact_id must be an ArtifactId")
        _require_text(self.content_reference, "content_reference")
        if not isinstance(self.candidate_type, CandidateType):
            raise TypeError("candidate_type must be a CandidateType")
        if not isinstance(self.rationale, SelectionRationale):
            raise TypeError("rationale must be a SelectionRationale")
        if self.rationale.candidate_id != self.candidate_id:
            raise ValueError("Item rationale must reference its candidate")
        if self.rationale.decision is not SelectionDecision.SELECTED:
            raise ValueError("Selected Context Item requires a selected rationale")
        if self.location is not None:
            if not isinstance(self.location, SourceLocation):
                raise TypeError("location must be a SourceLocation")
            if self.artifact_id != self.location.artifact_id:
                raise ValueError("Item location must belong to its artifact")
        for value, field_name in (
            (self.estimated_tokens, "estimated_tokens"),
            (self.estimated_bytes, "estimated_bytes"),
            (self.estimated_characters, "estimated_characters"),
        ):
            if value is not None:
                if type(value) is not int:
                    raise TypeError(f"{field_name} must be an integer")
                if value < 0:
                    raise ValueError(f"{field_name} must not be negative")
        if self.content_fingerprint is not None and not self.content_fingerprint.startswith(
            "sha256:"
        ):
            raise ValueError("content_fingerprint must use SHA-256")
        if type(self.is_truncated) is not bool:
            raise TypeError("is_truncated must be a boolean")
        score_breakdown = tuple(self.score_breakdown)
        score_keys = tuple(key for key, _ in score_breakdown)
        if len(set(score_keys)) != len(score_keys):
            raise ValueError("score_breakdown keys must be unique")
        if any(
            not key.strip() or not isinstance(value, (int, float)) or not math.isfinite(value)
            for key, value in score_breakdown
        ):
            raise ValueError("score_breakdown must contain named finite values")
        _require_text(self.sensitivity_classification, "sensitivity_classification")
        dependency_path = tuple(self.dependency_path)
        if any(not value.strip() for value in dependency_path):
            raise ValueError("dependency_path must contain non-empty values")
        object.__setattr__(self, "score_breakdown", score_breakdown)
        object.__setattr__(self, "dependency_path", dependency_path)


@dataclass(frozen=True, slots=True)
class RetrievalStatistics:
    """Operational retrieval measurements."""

    candidates_generated: int = 0
    candidates_evaluated: int = 0
    artifacts_selected: int = 0
    excerpts_selected: int = 0
    symbols_selected: int = 0
    relationships_traversed: int = 0
    candidates_budget_excluded: int = 0
    duplicates_suppressed: int = 0
    estimated_selected_tokens: int = 0

    def __post_init__(self) -> None:
        values = tuple(getattr(self, field_name) for field_name in self.__dataclass_fields__)
        if any(type(value) is not int for value in values):
            raise TypeError("Retrieval statistics must be integers")
        if any(value < 0 for value in values):
            raise ValueError("Retrieval statistics must not be negative")


@dataclass(frozen=True, slots=True)
class RetrievalRequest:
    """Validated input for a Context Retriever."""

    task: TaskSpecification
    project_index: ProjectIndex
    budget: ContextBudget

    def __post_init__(self) -> None:
        if not isinstance(self.task, TaskSpecification):
            raise TypeError("task must be a TaskSpecification")
        if not isinstance(self.project_index, ProjectIndex):
            raise TypeError("project_index must be a ProjectIndex")
        if not isinstance(self.budget, ContextBudget):
            raise TypeError("budget must be a ContextBudget")


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    """Immutable, explainable context selection outcome."""

    retrieval_id: RetrievalId
    task_id: TaskId
    index_id: IndexId
    project_fingerprint: ProjectFingerprint
    strategy_versions: tuple[str, ...]
    candidates: tuple[RetrievalCandidate, ...]
    selected_items: tuple[SelectedContextItem, ...]
    rationales: tuple[SelectionRationale, ...]
    applied_budget: ContextBudget
    diagnostics: DiagnosticCollection
    statistics: RetrievalStatistics
    status: RetrievalStatus
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.retrieval_id, RetrievalId):
            raise TypeError("retrieval_id must be a RetrievalId")
        if not isinstance(self.task_id, TaskId):
            raise TypeError("task_id must be a TaskId")
        if not isinstance(self.index_id, IndexId):
            raise TypeError("index_id must be an IndexId")
        if not isinstance(self.project_fingerprint, ProjectFingerprint):
            raise TypeError("project_fingerprint must be a ProjectFingerprint")
        strategy_versions = tuple(self.strategy_versions)
        if any(not version.strip() for version in strategy_versions):
            raise ValueError("strategy_versions must not contain empty values")
        candidates = tuple(self.candidates)
        selected_items = tuple(self.selected_items)
        rationales = tuple(self.rationales)
        if any(not isinstance(item, RetrievalCandidate) for item in candidates):
            raise TypeError("candidates must contain RetrievalCandidate values")
        if any(not isinstance(item, SelectedContextItem) for item in selected_items):
            raise TypeError("selected_items must contain SelectedContextItem values")
        if any(not isinstance(item, SelectionRationale) for item in rationales):
            raise TypeError("rationales must contain SelectionRationale values")
        candidate_ids = tuple(item.candidate_id for item in candidates)
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("Candidate identifiers must be unique")
        rationale_ids = tuple(item.candidate_id for item in rationales)
        if len(set(rationale_ids)) != len(rationale_ids):
            raise ValueError("Rationales must reference unique candidates")
        if set(rationale_ids) != set(candidate_ids):
            raise ValueError("Every candidate must have exactly one rationale")
        selected_candidate_ids = {
            candidate.candidate_id
            for candidate in candidates
            if candidate.outcome in (CandidateOutcome.SELECTED, CandidateOutcome.TRUNCATED)
        }
        item_candidate_ids = {item.candidate_id for item in selected_items}
        if item_candidate_ids != selected_candidate_ids:
            raise ValueError("Selected items must match selected candidate outcomes")
        outcomes = {candidate.candidate_id: candidate.outcome for candidate in candidates}
        if any(
            item.is_truncated is not (outcomes[item.candidate_id] is CandidateOutcome.TRUNCATED)
            for item in selected_items
        ):
            raise ValueError("Item truncation must match its candidate outcome")
        if not isinstance(self.applied_budget, ContextBudget):
            raise TypeError("applied_budget must be a ContextBudget")
        if not isinstance(self.diagnostics, DiagnosticCollection):
            raise TypeError("diagnostics must be a DiagnosticCollection")
        if not isinstance(self.statistics, RetrievalStatistics):
            raise TypeError("statistics must be RetrievalStatistics")
        if not isinstance(self.status, RetrievalStatus):
            raise TypeError("status must be a RetrievalStatus")
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be a datetime")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        object.__setattr__(self, "strategy_versions", tuple(sorted(strategy_versions)))
        object.__setattr__(self, "candidates", candidates)
        object.__setattr__(self, "selected_items", selected_items)
        object.__setattr__(self, "rationales", rationales)
