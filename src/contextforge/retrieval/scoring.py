"""Inspectable deterministic scoring for retrieval candidates."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum

from contextforge.retrieval.models import (
    CandidateEligibility,
    CandidateType,
    RetrievalCandidate,
    SelectionReason,
)

RETRIEVAL_SCORING_MODEL_VERSION = "retrieval-scoring-v1"


class ScoreComponent(StrEnum):
    """Stable dimensions of candidate relevance."""

    EXPLICIT_REFERENCE = "explicit_reference"
    PATH_MATCH = "path_match"
    SYMBOL_MATCH = "symbol_match"
    LEXICAL_RELEVANCE = "lexical_relevance"
    STRUCTURAL_RELEVANCE = "structural_relevance"
    DEPENDENCY_DISTANCE = "dependency_distance"
    ARTIFACT_PRIORITY = "artifact_priority"
    SENSITIVITY_PENALTY = "sensitivity_penalty"
    GENERATED_PENALTY = "generated_penalty"


_DEFAULT_WEIGHTS = {
    ScoreComponent.EXPLICIT_REFERENCE: 1.0,
    ScoreComponent.PATH_MATCH: 0.9,
    ScoreComponent.SYMBOL_MATCH: 0.9,
    ScoreComponent.LEXICAL_RELEVANCE: 0.7,
    ScoreComponent.STRUCTURAL_RELEVANCE: 0.7,
    ScoreComponent.DEPENDENCY_DISTANCE: 0.6,
    ScoreComponent.ARTIFACT_PRIORITY: 0.4,
    ScoreComponent.SENSITIVITY_PENALTY: 1.0,
    ScoreComponent.GENERATED_PENALTY: 0.5,
}
_PENALTIES = frozenset({ScoreComponent.SENSITIVITY_PENALTY, ScoreComponent.GENERATED_PENALTY})
_ARTIFACT_PRIORITY = {
    CandidateType.FULL_ARTIFACT: 1.0,
    CandidateType.SYMBOL_DEFINITION: 0.95,
    CandidateType.STRUCTURAL_UNIT: 0.9,
    CandidateType.SOURCE_EXCERPT: 0.85,
    CandidateType.TEST_ARTIFACT: 0.75,
    CandidateType.CONFIGURATION_BLOCK: 0.8,
    CandidateType.MANIFEST_SECTION: 0.75,
    CandidateType.DOCUMENTATION_SECTION: 0.6,
}


@dataclass(frozen=True, slots=True)
class RetrievalScoringConfig:
    """Validated component weights."""

    weights: tuple[tuple[ScoreComponent, float], ...] = field(
        default_factory=lambda: tuple(_DEFAULT_WEIGHTS.items())
    )

    def __post_init__(self) -> None:
        weights = tuple(self.weights)
        components = tuple(component for component, _ in weights)
        if set(components) != set(ScoreComponent):
            raise ValueError("weights must define every ScoreComponent exactly once")
        if len(components) != len(set(components)):
            raise ValueError("weights must not contain duplicate components")
        if any(
            not isinstance(component, ScoreComponent)
            or not isinstance(weight, (int, float))
            or not math.isfinite(weight)
            or weight < 0
            for component, weight in weights
        ):
            raise ValueError("weights must be finite non-negative numbers")
        object.__setattr__(self, "weights", weights)


@dataclass(frozen=True, slots=True)
class ScoreContribution:
    """One visible component value and its weighted effect."""

    component: ScoreComponent
    value: float
    weight: float
    weighted_value: float
    evidence_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.component, ScoreComponent):
            raise TypeError("component must be a ScoreComponent")
        if not 0 <= self.value <= 1:
            raise ValueError("component value must be between zero and one")
        if self.evidence_count < 0:
            raise ValueError("evidence_count must not be negative")


@dataclass(frozen=True, slots=True)
class CandidateScore:
    """Complete inspectable score for one candidate."""

    candidate_id: str
    components: tuple[ScoreContribution, ...]
    raw_score: float
    normalized_score: float
    rank: int

    def __post_init__(self) -> None:
        components = tuple(self.components)
        if tuple(item.component for item in components) != tuple(ScoreComponent):
            raise ValueError("components must follow the complete canonical order")
        if not 0 <= self.normalized_score <= 1:
            raise ValueError("normalized_score must be between zero and one")
        if self.rank < 1:
            raise ValueError("rank must be positive")
        object.__setattr__(self, "components", components)


@dataclass(frozen=True, slots=True)
class RetrievalScoreResult:
    """Candidate scores in final stable rank order."""

    scores: tuple[CandidateScore, ...]
    model_version: str = RETRIEVAL_SCORING_MODEL_VERSION


def _component_for_evidence(evidence_type: str) -> ScoreComponent | None:
    value = evidence_type.casefold()
    if value.startswith("explicit-"):
        return ScoreComponent.EXPLICIT_REFERENCE
    if "path" in value:
        return ScoreComponent.PATH_MATCH
    if "symbol" in value:
        return ScoreComponent.SYMBOL_MATCH
    if "lexical" in value:
        return ScoreComponent.LEXICAL_RELEVANCE
    if "structural" in value:
        return ScoreComponent.STRUCTURAL_RELEVANCE
    if "dependency" in value or "relationship" in value:
        return ScoreComponent.DEPENDENCY_DISTANCE
    if "generated" in value:
        return ScoreComponent.GENERATED_PENALTY
    if "sensitive" in value or "security" in value:
        return ScoreComponent.SENSITIVITY_PENALTY
    return None


@dataclass(frozen=True, slots=True)
class RetrievalScoringModel:
    """Combine evidence into comparable scores without hiding components."""

    config: RetrievalScoringConfig = field(default_factory=RetrievalScoringConfig)
    version: str = RETRIEVAL_SCORING_MODEL_VERSION

    def score(self, candidates: tuple[RetrievalCandidate, ...]) -> RetrievalScoreResult:
        """Score and rank candidates reproducibly."""
        if any(not isinstance(candidate, RetrievalCandidate) for candidate in candidates):
            raise TypeError("candidates must contain RetrievalCandidate values")
        weights = dict(self.config.weights)
        raw_entries = [
            (candidate.candidate_id, *self._components(candidate, weights))
            for candidate in candidates
        ]
        raw_values = [raw for _, _, raw in raw_entries]
        minimum = min(raw_values, default=0.0)
        maximum = max(raw_values, default=0.0)

        normalized_entries = []
        for candidate_id, components, raw in raw_entries:
            if maximum == minimum:
                normalized = 1.0 if raw > 0 else 0.0
            else:
                normalized = (raw - minimum) / (maximum - minimum)
            normalized_entries.append((candidate_id, components, raw, round(normalized, 8)))
        normalized_entries.sort(key=lambda item: (-item[3], -item[2], item[0]))
        return RetrievalScoreResult(
            tuple(
                CandidateScore(candidate_id, components, raw, normalized, rank)
                for rank, (candidate_id, components, raw, normalized) in enumerate(
                    normalized_entries, start=1
                )
            ),
            self.version,
        )

    @staticmethod
    def _components(
        candidate: RetrievalCandidate,
        weights: dict[ScoreComponent, float],
    ) -> tuple[tuple[ScoreContribution, ...], float]:
        evidence_by_component: dict[ScoreComponent, dict[tuple[object, ...], float]] = {}
        for evidence in candidate.evidence:
            component = _component_for_evidence(evidence.evidence_type)
            if component is None:
                continue
            signature = (evidence.evidence_type, evidence.source, evidence.detail)
            value = min(max(float(evidence.weight or 0.0), 0.0), 1.0)
            evidence_by_component.setdefault(component, {})[signature] = value

        values = {component: 0.0 for component in ScoreComponent}
        for component, component_evidence in evidence_by_component.items():
            values[component] = max(component_evidence.values(), default=0.0)
        if candidate.rationale is not None:
            reason = candidate.rationale.primary_reason
            if reason in (
                SelectionReason.EXPLICIT_PATH_REFERENCE,
                SelectionReason.EXPLICIT_SYMBOL_REFERENCE,
            ):
                values[ScoreComponent.EXPLICIT_REFERENCE] = 1.0
            if reason in (
                SelectionReason.EXACT_PATH_MATCH,
                SelectionReason.PARTIAL_PATH_MATCH,
            ):
                values[ScoreComponent.PATH_MATCH] = 1.0
            if reason is SelectionReason.EXACT_SYMBOL_MATCH:
                values[ScoreComponent.SYMBOL_MATCH] = 1.0
        values[ScoreComponent.ARTIFACT_PRIORITY] = _ARTIFACT_PRIORITY.get(
            candidate.candidate_type, 0.5
        )
        if candidate.eligibility is CandidateEligibility.PROHIBITED or (
            candidate.rationale is not None
            and candidate.rationale.primary_reason is SelectionReason.SECURITY_PROHIBITED
        ):
            values[ScoreComponent.SENSITIVITY_PENALTY] = 1.0

        contributions = []
        raw = 0.0
        for component in ScoreComponent:
            weighted = values[component] * weights[component]
            if component in _PENALTIES:
                weighted = -weighted
            raw += weighted
            contributions.append(
                ScoreContribution(
                    component,
                    values[component],
                    weights[component],
                    round(weighted, 8),
                    len(evidence_by_component.get(component, ())),
                )
            )
        return tuple(contributions), round(raw, 8)
