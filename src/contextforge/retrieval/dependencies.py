"""Bounded deterministic traversal of explicit Project Index relationships."""

from __future__ import annotations

import hashlib
from collections import deque
from dataclasses import dataclass, field

from contextforge.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticCollection,
    DiagnosticSeverity,
)
from contextforge.indexer import (
    IndexedArtifact,
    ProjectIndex,
    Relationship,
    RelationshipKind,
    RelationshipResolution,
    Symbol,
)
from contextforge.retrieval.models import (
    CandidateEligibility,
    CandidateOutcome,
    CandidateType,
    RetrievalCandidate,
    RetrievalEvidence,
    SelectionDecision,
    SelectionRationale,
    SelectionReason,
)

DEPENDENCY_TRAVERSAL_STRATEGY_VERSION = "dependency-traversal-v1"
_DEFAULT_WEIGHTS = {
    RelationshipKind.DEPENDS_ON: 1.0,
    RelationshipKind.IMPORTS: 0.95,
    RelationshipKind.EXTENDS: 0.9,
    RelationshipKind.IMPLEMENTS: 0.9,
    RelationshipKind.CALLS: 0.8,
    RelationshipKind.REFERENCES: 0.7,
    RelationshipKind.CONFIGURES: 0.85,
    RelationshipKind.TESTS: 0.8,
    RelationshipKind.DOCUMENTS: 0.6,
}


@dataclass(frozen=True, slots=True)
class DependencyTraversalConfig:
    """Hard limits and deterministic relevance policy for graph traversal."""

    max_depth: int = 2
    max_candidates: int = 50
    max_fan_out: int = 20
    relevance_decay: float = 0.8
    relationship_weights: tuple[tuple[RelationshipKind, float], ...] = field(
        default_factory=lambda: tuple(_DEFAULT_WEIGHTS.items())
    )

    def __post_init__(self) -> None:
        for value, name in (
            (self.max_depth, "max_depth"),
            (self.max_candidates, "max_candidates"),
            (self.max_fan_out, "max_fan_out"),
        ):
            if type(value) is not int:
                raise TypeError(f"{name} must be an integer")
            if value < 1:
                raise ValueError(f"{name} must be positive")
        if not 0 < self.relevance_decay <= 1:
            raise ValueError("relevance_decay must be greater than zero and at most one")
        weights = tuple(self.relationship_weights)
        kinds = tuple(kind for kind, _ in weights)
        if len(set(kinds)) != len(kinds):
            raise ValueError("relationship_weights must not contain duplicate kinds")
        if any(
            not isinstance(kind, RelationshipKind) or not 0 < weight <= 1
            for kind, weight in weights
        ):
            raise ValueError("relationship weights must use valid kinds and values in (0, 1]")
        object.__setattr__(self, "relationship_weights", weights)


@dataclass(frozen=True, slots=True)
class DependencyTraversalStep:
    """One relationship edge in a candidate's trace."""

    relationship_id: str
    kind: RelationshipKind
    source_reference: str
    target_reference: str
    weight: float


@dataclass(frozen=True, slots=True)
class DependencyTraversalPath:
    """Complete trace from a seed to one resolved candidate."""

    seed_reference: str
    target_reference: str
    steps: tuple[DependencyTraversalStep, ...]
    cumulative_weight: float

    def __post_init__(self) -> None:
        steps = tuple(self.steps)
        if not self.seed_reference or not self.target_reference:
            raise ValueError("path references must not be empty")
        if not steps:
            raise ValueError("a traversal path must contain at least one step")
        if not 0 < self.cumulative_weight <= 1:
            raise ValueError("cumulative_weight must be in (0, 1]")
        object.__setattr__(self, "steps", steps)


@dataclass(frozen=True, slots=True)
class DependencyTraversalResult:
    """Resolved candidates, their paths, and limit diagnostics."""

    candidates: tuple[RetrievalCandidate, ...]
    paths: tuple[DependencyTraversalPath, ...]
    diagnostics: DiagnosticCollection
    strategy_version: str = DEPENDENCY_TRAVERSAL_STRATEGY_VERSION

    def __post_init__(self) -> None:
        candidates = tuple(self.candidates)
        paths = tuple(self.paths)
        if len(candidates) != len(paths):
            raise ValueError("each dependency candidate must have one traversal path")
        if not isinstance(self.diagnostics, DiagnosticCollection):
            raise TypeError("diagnostics must be a DiagnosticCollection")
        object.__setattr__(self, "candidates", candidates)
        object.__setattr__(self, "paths", paths)


def _limit_diagnostic(code: str, message: str) -> Diagnostic:
    return Diagnostic(
        DiagnosticCode(code),
        DiagnosticSeverity.WARNING,
        message,
        "context-retriever",
    )


def _reason(kind: RelationshipKind) -> SelectionReason:
    return {
        RelationshipKind.IMPORTS: SelectionReason.DEPENDENCY_RELATIONSHIP,
        RelationshipKind.DEPENDS_ON: SelectionReason.DEPENDENCY_RELATIONSHIP,
        RelationshipKind.REFERENCES: SelectionReason.REFERENCE_RELATIONSHIP,
        RelationshipKind.CALLS: SelectionReason.CALL_RELATIONSHIP,
        RelationshipKind.EXTENDS: SelectionReason.INHERITANCE_RELATIONSHIP,
        RelationshipKind.IMPLEMENTS: SelectionReason.INHERITANCE_RELATIONSHIP,
        RelationshipKind.TESTS: SelectionReason.TEST_RELATIONSHIP,
        RelationshipKind.CONFIGURES: SelectionReason.CONFIGURATION_RELATIONSHIP,
        RelationshipKind.DOCUMENTS: SelectionReason.DOCUMENTATION_RELATIONSHIP,
    }[kind]


@dataclass(frozen=True, slots=True)
class DependencyTraversalStrategy:
    """Expand seed references through bounded, resolved, forward relationships."""

    config: DependencyTraversalConfig = field(default_factory=DependencyTraversalConfig)
    version: str = DEPENDENCY_TRAVERSAL_STRATEGY_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.config, DependencyTraversalConfig):
            raise TypeError("config must be a DependencyTraversalConfig")
        if not self.version.strip():
            raise ValueError("version must not be empty")

    def traverse(
        self,
        seed_references: tuple[str, ...],
        project_index: ProjectIndex,
    ) -> DependencyTraversalResult:
        """Traverse each seed in stable breadth-first order."""
        if not isinstance(project_index, ProjectIndex):
            raise TypeError("project_index must be a ProjectIndex")
        seeds = tuple(dict.fromkeys(seed_references))
        if any(not seed.strip() for seed in seeds):
            raise ValueError("seed_references must contain non-empty values")

        weights = dict(self.config.relationship_weights)
        adjacency: dict[str, list[Relationship]] = {}
        for relationship in project_index.relationships:
            if (
                relationship.kind in weights
                and relationship.resolution is RelationshipResolution.RESOLVED_INTERNAL
            ):
                adjacency.setdefault(relationship.source_reference, []).append(relationship)
        for relationships in adjacency.values():
            relationships.sort(
                key=lambda item: (
                    item.kind.value,
                    item.target_reference,
                    item.relationship_id,
                )
            )

        symbols = {symbol.symbol_id: symbol for symbol in project_index.symbols}
        artifacts = {
            str(artifact.artifact_id): artifact for artifact in project_index.indexed_artifacts
        }
        queue: deque[tuple[str, tuple[DependencyTraversalStep, ...], int, float]] = deque(
            (seed, (), 0, 1.0) for seed in seeds
        )
        visited = set(seeds)
        candidates: list[RetrievalCandidate] = []
        paths: list[DependencyTraversalPath] = []
        diagnostics: list[Diagnostic] = []
        depth_limited = False
        fan_out_limited = False

        while queue and len(candidates) < self.config.max_candidates:
            current, previous_steps, depth, cumulative = queue.popleft()
            outgoing = adjacency.get(current, ())
            if depth >= self.config.max_depth:
                depth_limited |= bool(outgoing)
                continue
            if len(outgoing) > self.config.max_fan_out:
                fan_out_limited = True
            for relationship in outgoing[: self.config.max_fan_out]:
                target = relationship.target_reference
                if target in visited:
                    continue
                visited.add(target)
                edge_weight = weights[relationship.kind]
                total_weight = round(
                    cumulative * edge_weight * (self.config.relevance_decay if depth else 1.0),
                    8,
                )
                step = DependencyTraversalStep(
                    relationship.relationship_id,
                    relationship.kind,
                    relationship.source_reference,
                    target,
                    edge_weight,
                )
                steps = (*previous_steps, step)
                entity = symbols.get(target) or artifacts.get(target)
                if entity is not None:
                    path = DependencyTraversalPath(
                        previous_steps[0].source_reference if previous_steps else current,
                        target,
                        steps,
                        total_weight,
                    )
                    candidates.append(self._candidate(entity, path, relationship.kind))
                    paths.append(path)
                    if len(candidates) >= self.config.max_candidates:
                        break
                queue.append((target, steps, depth + 1, total_weight))

        if depth_limited:
            diagnostics.append(
                _limit_diagnostic(
                    "RETRIEVAL_RELATIONSHIP_LIMIT",
                    "Dependency traversal reached its maximum depth.",
                )
            )
        if fan_out_limited:
            diagnostics.append(
                _limit_diagnostic(
                    "RETRIEVAL_HIGH_FAN_OUT",
                    "Dependency traversal omitted relationships beyond its fan-out limit.",
                )
            )
        if queue and len(candidates) >= self.config.max_candidates:
            diagnostics.append(
                _limit_diagnostic(
                    "RETRIEVAL_RELATIONSHIP_LIMIT",
                    "Dependency traversal reached its candidate limit.",
                )
            )
        return DependencyTraversalResult(
            tuple(candidates),
            tuple(paths),
            DiagnosticCollection(tuple(diagnostics)),
            self.version,
        )

    def _candidate(
        self,
        entity: Symbol | IndexedArtifact,
        path: DependencyTraversalPath,
        kind: RelationshipKind,
    ) -> RetrievalCandidate:
        symbol = entity if isinstance(entity, Symbol) else None
        artifact = None if symbol is not None else entity
        if symbol is not None:
            entity_id = symbol.symbol_id
            source_reference = symbol.qualified_name or symbol.name
            artifact_id = symbol.artifact_id
            location = symbol.location
        else:
            assert isinstance(artifact, IndexedArtifact)
            entity_id = str(artifact.artifact_id)
            source_reference = (
                artifact.path.value if artifact.path is not None else str(artifact.artifact_id)
            )
            artifact_id = artifact.artifact_id
            location = None
        digest = hashlib.sha256(entity_id.encode()).hexdigest()[:20]
        candidate_id = f"dependency_{digest}"
        trace = " -> ".join(f"{step.source_reference}[{step.kind.value}]" for step in path.steps)
        evidence = RetrievalEvidence(
            "dependency-traversal-path",
            self.version,
            f"{trace} -> {path.target_reference}",
            path.cumulative_weight,
        )
        rationale = SelectionRationale(
            candidate_id,
            SelectionDecision.SELECTED,
            _reason(kind),
            (evidence,),
            score=path.cumulative_weight,
            explanation=f"Resolved through {len(path.steps)} relationship(s).",
        )
        return RetrievalCandidate(
            candidate_id,
            CandidateType.SYMBOL_DEFINITION if symbol is not None else CandidateType.FULL_ARTIFACT,
            source_reference,
            f"symbol:{entity_id}" if symbol is not None else f"artifact:{entity_id}",
            (evidence,),
            CandidateEligibility.ELIGIBLE,
            CandidateOutcome.SELECTED,
            0,
            artifact_id=artifact_id,
            location=location,
            rationale=rationale,
        )
