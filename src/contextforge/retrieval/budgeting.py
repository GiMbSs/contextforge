"""Deterministic hard-budget selection for eligible retrieval candidates."""

from __future__ import annotations

from dataclasses import dataclass, replace

from contextforge.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticCollection,
    DiagnosticSeverity,
)
from contextforge.domain import ArtifactId
from contextforge.retrieval.models import (
    CandidateEligibility,
    CandidateOutcome,
    CandidateType,
    ContextBudget,
    RetrievalCandidate,
    RetrievalEvidence,
    SelectionDecision,
    SelectionRationale,
    SelectionReason,
)
from contextforge.retrieval.scoring import CandidateScore

CONTEXT_BUDGET_PLANNER_VERSION = "context-budget-v1"
_MANDATORY_REASONS = frozenset(
    {
        SelectionReason.EXPLICIT_PATH_REFERENCE,
        SelectionReason.EXPLICIT_SYMBOL_REFERENCE,
        SelectionReason.ERROR_LOCATION_REFERENCE,
        SelectionReason.EXACT_PATH_MATCH,
        SelectionReason.EXACT_SYMBOL_MATCH,
        SelectionReason.REQUIRED_CONTEXT,
        SelectionReason.USER_PROVIDED_CONTEXT,
    }
)


@dataclass(frozen=True, slots=True)
class ContextBudgetReservation:
    """Capacity retained for instructions and the response contract."""

    estimated_tokens: int = 0
    characters: int = 0
    bytes: int = 0

    def __post_init__(self) -> None:
        if any(
            type(value) is not int or value < 0
            for value in (self.estimated_tokens, self.characters, self.bytes)
        ):
            raise ValueError("reserved capacities must be non-negative integers")


@dataclass(frozen=True, slots=True)
class CandidateBudgetEstimate:
    """Provider-neutral size dimensions unavailable on RetrievalCandidate."""

    candidate_id: str
    characters: int

    def __post_init__(self) -> None:
        if not self.candidate_id or any(character.isspace() for character in self.candidate_id):
            raise ValueError("candidate_id must be a non-empty identifier")
        if type(self.characters) is not int or self.characters < 0:
            raise ValueError("characters must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class BudgetUsage:
    """Selected capacity consumption after reservations."""

    estimated_tokens: int = 0
    characters: int = 0
    bytes: int = 0
    items: int = 0
    artifacts: int = 0
    excerpts: int = 0


@dataclass(frozen=True, slots=True)
class BudgetSelectionResult:
    """Candidates with final budget outcomes and complete accounting."""

    candidates: tuple[RetrievalCandidate, ...]
    selected_candidate_ids: tuple[str, ...]
    usage: BudgetUsage
    reservation: ContextBudgetReservation
    diagnostics: DiagnosticCollection
    mandatory_overflow: bool
    planner_version: str = CONTEXT_BUDGET_PLANNER_VERSION


def _budget_diagnostic(message: str) -> Diagnostic:
    return Diagnostic(
        DiagnosticCode("RETRIEVAL_BUDGET_EXCEEDED"),
        DiagnosticSeverity.WARNING,
        message,
        "context-retriever",
    )


def _budget_excluded(candidate: RetrievalCandidate) -> RetrievalCandidate:
    evidence = (
        *candidate.evidence,
        RetrievalEvidence(
            "context-budget",
            CONTEXT_BUDGET_PLANNER_VERSION,
            "Candidate does not fit within the remaining hard budget.",
        ),
    )
    return replace(
        candidate,
        outcome=CandidateOutcome.EXCLUDED,
        rationale=SelectionRationale(
            candidate.candidate_id,
            SelectionDecision.EXCLUDED,
            SelectionReason.CONTEXT_BUDGET_EXCEEDED,
            evidence,
            explanation="Excluded because a hard Context Budget limit would overflow.",
        ),
        evidence=evidence,
    )


def _selected(candidate: RetrievalCandidate, rank: int, score: float) -> RetrievalCandidate:
    evidence = candidate.evidence
    return replace(
        candidate,
        outcome=CandidateOutcome.SELECTED,
        rationale=SelectionRationale(
            candidate.candidate_id,
            SelectionDecision.SELECTED,
            candidate.rationale.primary_reason
            if candidate.rationale is not None
            else SelectionReason.REQUIRED_CONTEXT,
            evidence,
            score=score,
            rank=rank,
            explanation="Selected within the active hard Context Budget.",
        ),
    )


@dataclass(frozen=True, slots=True)
class ContextBudgetPlanner:
    """Select mandatory then highest-scored eligible candidates without overflow."""

    version: str = CONTEXT_BUDGET_PLANNER_VERSION

    def select(
        self,
        candidates: tuple[RetrievalCandidate, ...],
        scores: tuple[CandidateScore, ...],
        budget: ContextBudget,
        reservation: ContextBudgetReservation | None = None,
        estimates: tuple[CandidateBudgetEstimate, ...] = (),
        mandatory_candidate_ids: tuple[str, ...] = (),
    ) -> BudgetSelectionResult:
        """Apply every active budget dimension using deterministic ordering."""
        if not isinstance(budget, ContextBudget):
            raise TypeError("budget must be a ContextBudget")
        if reservation is None:
            reservation = ContextBudgetReservation()
        elif not isinstance(reservation, ContextBudgetReservation):
            raise TypeError("reservation must be a ContextBudgetReservation")
        score_by_id = {score.candidate_id: score for score in scores}
        if len(score_by_id) != len(scores):
            raise ValueError("scores must not contain duplicate candidate identifiers")
        candidate_ids = {candidate.candidate_id for candidate in candidates}
        if set(score_by_id) != candidate_ids:
            raise ValueError("scores must cover every candidate exactly once")
        characters_by_id = {estimate.candidate_id: estimate.characters for estimate in estimates}
        if len(characters_by_id) != len(estimates):
            raise ValueError("estimates must not contain duplicate candidate identifiers")
        if not set(characters_by_id) <= candidate_ids:
            raise ValueError("estimates must reference known candidates")
        explicit_mandatory = set(mandatory_candidate_ids)
        if not explicit_mandatory <= candidate_ids:
            raise ValueError("mandatory_candidate_ids must reference known candidates")
        reservation_overflow = any(
            (
                budget.max_estimated_tokens is not None
                and reservation.estimated_tokens > budget.max_estimated_tokens,
                budget.max_characters is not None
                and reservation.characters > budget.max_characters,
                budget.max_bytes is not None and reservation.bytes > budget.max_bytes,
            )
        )

        def is_mandatory(candidate: RetrievalCandidate) -> bool:
            return candidate.candidate_id in explicit_mandatory or (
                candidate.rationale is not None
                and candidate.rationale.primary_reason in _MANDATORY_REASONS
            )

        ranked = sorted(
            candidates,
            key=lambda candidate: (
                not is_mandatory(candidate),
                score_by_id[candidate.candidate_id].rank,
                candidate.candidate_id,
            ),
        )
        selected_ids: list[str] = []
        transformed: dict[str, RetrievalCandidate] = {}
        selected_artifact_ids: set[ArtifactId] = set()
        tokens = characters = bytes_used = excerpts = 0
        mandatory_overflow = False

        for candidate in ranked:
            if (
                candidate.eligibility is not CandidateEligibility.ELIGIBLE
                or candidate.outcome is CandidateOutcome.DEFERRED
            ):
                transformed[candidate.candidate_id] = candidate
                continue
            candidate_tokens = candidate.estimated_tokens or 0
            candidate_characters = characters_by_id.get(
                candidate.candidate_id, candidate.estimated_bytes
            )
            candidate_bytes = candidate.estimated_bytes
            is_excerpt = candidate.candidate_type is not CandidateType.FULL_ARTIFACT
            next_artifacts = set(selected_artifact_ids)
            if candidate.artifact_id is not None:
                next_artifacts.add(candidate.artifact_id)
            fits = all(
                (
                    budget.max_estimated_tokens is None
                    or reservation.estimated_tokens + tokens + candidate_tokens
                    <= budget.max_estimated_tokens,
                    budget.max_characters is None
                    or reservation.characters + characters + candidate_characters
                    <= budget.max_characters,
                    budget.max_bytes is None
                    or reservation.bytes + bytes_used + candidate_bytes <= budget.max_bytes,
                    budget.max_item_bytes is None or candidate_bytes <= budget.max_item_bytes,
                    budget.max_items is None or len(selected_ids) + 1 <= budget.max_items,
                    budget.max_artifacts is None or len(next_artifacts) <= budget.max_artifacts,
                    budget.max_excerpts is None
                    or excerpts + int(is_excerpt) <= budget.max_excerpts,
                )
            )
            if fits:
                score = score_by_id[candidate.candidate_id]
                selected_ids.append(candidate.candidate_id)
                selected_artifact_ids = next_artifacts
                tokens += candidate_tokens
                characters += candidate_characters
                bytes_used += candidate_bytes
                excerpts += int(is_excerpt)
                transformed[candidate.candidate_id] = _selected(
                    candidate, len(selected_ids), score.normalized_score
                )
            else:
                transformed[candidate.candidate_id] = _budget_excluded(candidate)
                mandatory_overflow |= is_mandatory(candidate)

        diagnostics = []
        if reservation_overflow:
            diagnostics.append(
                _budget_diagnostic(
                    "Reserved instruction and response capacity exceeds the Context Budget."
                )
            )
        if mandatory_overflow:
            diagnostics.append(
                _budget_diagnostic(
                    "One or more mandatory eligible candidates exceed the Context Budget."
                )
            )
        return BudgetSelectionResult(
            tuple(transformed[candidate.candidate_id] for candidate in candidates),
            tuple(selected_ids),
            BudgetUsage(
                tokens,
                characters,
                bytes_used,
                len(selected_ids),
                len(selected_artifact_ids),
                excerpts,
            ),
            reservation,
            DiagnosticCollection(tuple(diagnostics)),
            mandatory_overflow,
            self.version,
        )
