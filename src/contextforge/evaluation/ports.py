"""Ports and immutable inputs for evaluation strategies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from contextforge.domain import ArtifactPath
from contextforge.evaluation.models import EvaluationCase, StrategyResult
from contextforge.indexer import ProjectIndex


@dataclass(frozen=True, slots=True)
class ArtifactBudgetEstimate:
    """Provider-neutral size estimate for one snapshot artifact."""

    path: ArtifactPath
    byte_count: int
    character_count: int
    estimated_tokens: int

    def __post_init__(self) -> None:
        if not isinstance(self.path, ArtifactPath):
            raise TypeError("path must be an ArtifactPath")
        for field_name in ("byte_count", "character_count", "estimated_tokens"):
            value = getattr(self, field_name)
            if type(value) is not int:
                raise TypeError(f"{field_name} must be an integer")
            if value < 0:
                raise ValueError(f"{field_name} must not be negative")


@dataclass(frozen=True, slots=True)
class EvaluationStrategyRequest:
    """Identical case, project snapshot, and budget inputs for every strategy."""

    case: EvaluationCase
    project_index: ProjectIndex
    artifact_estimates: tuple[ArtifactBudgetEstimate, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.case, EvaluationCase):
            raise TypeError("case must be an EvaluationCase")
        if not isinstance(self.project_index, ProjectIndex):
            raise TypeError("project_index must be a ProjectIndex")
        estimates = tuple(self.artifact_estimates)
        if any(not isinstance(item, ArtifactBudgetEstimate) for item in estimates):
            raise TypeError("artifact_estimates must contain ArtifactBudgetEstimate values")
        estimate_paths = tuple(item.path for item in estimates)
        if len(set(estimate_paths)) != len(estimates):
            raise ValueError("artifact_estimates must contain unique paths")
        indexed_paths = {
            artifact.path
            for artifact in self.project_index.indexed_artifacts
            if artifact.path is not None
        }
        if set(estimate_paths) != indexed_paths:
            raise ValueError("artifact_estimates must exactly cover indexed artifact paths")
        object.__setattr__(
            self,
            "artifact_estimates",
            tuple(sorted(estimates, key=lambda item: item.path)),
        )


class EvaluationStrategy(Protocol):
    """Produce one budgeted artifact ranking without mutating its snapshot."""

    @property
    def strategy_id(self) -> str:
        """Return the stable strategy identifier."""
        ...

    def evaluate(self, request: EvaluationStrategyRequest) -> StrategyResult:
        """Evaluate one case against an immutable project snapshot."""
        ...
