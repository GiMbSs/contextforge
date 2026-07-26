"""Bounded policy for required dependency-closure additions."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from contextforge.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticCollection,
    DiagnosticSeverity,
)
from contextforge.indexer import RelationshipKind
from contextforge.retrieval.budgeting import (
    BudgetSelectionResult,
    CandidateBudgetEstimate,
    ContextBudgetPlanner,
    ContextBudgetReservation,
)
from contextforge.retrieval.dependencies import (
    DependencyTraversalPath,
    DependencyTraversalResult,
)
from contextforge.retrieval.models import (
    CandidateEligibility,
    CandidateOutcome,
    ContextBudget,
    RetrievalCandidate,
    RetrievalEvidence,
    SelectionDecision,
    SelectionRationale,
    SelectionReason,
)
from contextforge.retrieval.scoring import RetrievalScoringModel

DEPENDENCY_CLOSURE_POLICY_VERSION = "dependency-closure-v1"
_DEFAULT_KINDS = (
    RelationshipKind.DEPENDS_ON,
    RelationshipKind.IMPORTS,
    RelationshipKind.EXTENDS,
    RelationshipKind.IMPLEMENTS,
    RelationshipKind.CONFIGURES,
)


@dataclass(frozen=True, slots=True)
class DependencyClosureConfig:
    """Limits on which traversal results become required context."""

    max_additions: int = 20
    minimum_weight: float = 0.5
    allowed_relationship_kinds: tuple[RelationshipKind, ...] = _DEFAULT_KINDS

    def __post_init__(self) -> None:
        if type(self.max_additions) is not int or self.max_additions < 1:
            raise ValueError("max_additions must be a positive integer")
        if not 0 <= self.minimum_weight <= 1:
            raise ValueError("minimum_weight must be between zero and one")
        kinds = tuple(self.allowed_relationship_kinds)
        if not kinds or any(not isinstance(kind, RelationshipKind) for kind in kinds):
            raise ValueError("allowed_relationship_kinds must contain relationship kinds")
        if len(set(kinds)) != len(kinds):
            raise ValueError("allowed_relationship_kinds must not contain duplicates")
        object.__setattr__(self, "allowed_relationship_kinds", kinds)


@dataclass(frozen=True, slots=True)
class ClosureAddition:
    """Why one supporting candidate is required by a primary candidate."""

    primary_candidate_id: str
    supporting_candidate_id: str
    path: DependencyTraversalPath


@dataclass(frozen=True, slots=True)
class DependencyClosureResult:
    """Budgeted closure with explicit additions and completeness state."""

    budget_result: BudgetSelectionResult
    additions: tuple[ClosureAddition, ...]
    diagnostics: DiagnosticCollection
    incomplete: bool
    policy_version: str = DEPENDENCY_CLOSURE_POLICY_VERSION


def _diagnostic(message: str) -> Diagnostic:
    return Diagnostic(
        DiagnosticCode("RETRIEVAL_INSUFFICIENT_CONTEXT"),
        DiagnosticSeverity.WARNING,
        message,
        "context-retriever",
    )


def _seed_references(candidate: RetrievalCandidate) -> frozenset[str]:
    references = {candidate.content_reference}
    if ":" in candidate.content_reference:
        references.add(candidate.content_reference.split(":", 1)[1])
    if candidate.artifact_id is not None:
        references.add(str(candidate.artifact_id))
    return frozenset(references)


def _required_candidate(
    candidate: RetrievalCandidate,
    primary: RetrievalCandidate,
    path: DependencyTraversalPath,
) -> RetrievalCandidate:
    trace = " -> ".join(f"{step.source_reference}[{step.kind.value}]" for step in path.steps)
    evidence = (
        *candidate.evidence,
        RetrievalEvidence(
            "dependency-closure-required",
            DEPENDENCY_CLOSURE_POLICY_VERSION,
            f"required_by={primary.candidate_id}; path={trace} -> {path.target_reference}",
            path.cumulative_weight,
        ),
    )
    return replace(
        candidate,
        evidence=evidence,
        outcome=CandidateOutcome.SELECTED,
        rationale=SelectionRationale(
            candidate.candidate_id,
            SelectionDecision.SELECTED,
            SelectionReason.REQUIRED_CONTEXT,
            evidence,
            score=path.cumulative_weight,
            explanation=f"Required to interpret candidate {primary.candidate_id}.",
        ),
    )


@dataclass(frozen=True, slots=True)
class DependencyClosurePolicy:
    """Promote bounded eligible traversal targets to required context."""

    config: DependencyClosureConfig = field(default_factory=DependencyClosureConfig)
    scorer: RetrievalScoringModel = field(default_factory=RetrievalScoringModel)
    budget_planner: ContextBudgetPlanner = field(default_factory=ContextBudgetPlanner)
    version: str = DEPENDENCY_CLOSURE_POLICY_VERSION

    def apply(
        self,
        primary_candidates: tuple[RetrievalCandidate, ...],
        traversal: DependencyTraversalResult,
        budget: ContextBudget,
        reservation: ContextBudgetReservation | None = None,
        estimates: tuple[CandidateBudgetEstimate, ...] = (),
    ) -> DependencyClosureResult:
        """Add required supports while preserving security and hard limits."""
        if any(
            candidate.outcome is not CandidateOutcome.SELECTED for candidate in primary_candidates
        ):
            raise ValueError("primary_candidates must already be selected")
        primary_by_seed = {
            reference: candidate
            for candidate in primary_candidates
            for reference in _seed_references(candidate)
        }
        existing_content = {candidate.content_reference for candidate in primary_candidates}
        additions: list[ClosureAddition] = []
        support_candidates: list[RetrievalCandidate] = []
        diagnostics = list(traversal.diagnostics)
        incomplete = False

        ordered = sorted(
            zip(traversal.candidates, traversal.paths, strict=True),
            key=lambda item: (
                -item[1].cumulative_weight,
                item[0].candidate_id,
            ),
        )
        for candidate, path in ordered:
            kind = path.steps[-1].kind
            if (
                kind not in self.config.allowed_relationship_kinds
                or path.cumulative_weight < self.config.minimum_weight
                or candidate.content_reference in existing_content
            ):
                continue
            primary = primary_by_seed.get(path.seed_reference)
            if primary is None:
                continue
            if candidate.eligibility is not CandidateEligibility.ELIGIBLE:
                incomplete = True
                diagnostics.append(
                    _diagnostic(
                        f"Required support {candidate.candidate_id} is prohibited or unavailable."
                    )
                )
                continue
            if len(additions) >= self.config.max_additions:
                incomplete = True
                diagnostics.append(
                    _diagnostic("Dependency closure reached its maximum addition limit.")
                )
                break
            required = _required_candidate(candidate, primary, path)
            support_candidates.append(required)
            additions.append(
                ClosureAddition(
                    primary.candidate_id,
                    required.candidate_id,
                    path,
                )
            )
            existing_content.add(candidate.content_reference)

        combined = (*primary_candidates, *support_candidates)
        scored = {score.candidate_id: score for score in self.scorer.score(combined).scores}
        scores = tuple(
            replace(scored[candidate.candidate_id], rank=rank)
            for rank, candidate in enumerate(combined, start=1)
        )
        mandatory_ids = tuple(candidate.candidate_id for candidate in combined)
        budget_result = self.budget_planner.select(
            combined,
            scores,
            budget,
            reservation,
            estimates,
            mandatory_ids,
        )
        selected = set(budget_result.selected_candidate_ids)
        omitted_additions = [
            addition for addition in additions if addition.supporting_candidate_id not in selected
        ]
        if omitted_additions or budget_result.mandatory_overflow:
            incomplete = True
            diagnostics.append(
                _diagnostic("Required dependency closure does not fit the hard Context Budget.")
            )
        diagnostics.extend(budget_result.diagnostics)
        return DependencyClosureResult(
            budget_result,
            tuple(additions),
            DiagnosticCollection(tuple(diagnostics)),
            incomplete,
            self.version,
        )
