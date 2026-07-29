"""Post-budget Context Bundle effectiveness and efficiency metrics."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from contextforge.context import ContextBundle
from contextforge.domain import ArtifactPath
from contextforge.evaluation.metrics import artifact_recall, precision_over_judged
from contextforge.evaluation.models import (
    EvaluationCase,
    MetricResult,
    RelevanceLevel,
    StrategySelection,
)
from contextforge.prompt import estimate_text_tokens
from contextforge.retrieval import (
    CandidateOutcome,
    ContextBudget,
    RetrievalResult,
    SelectionReason,
)


@dataclass(frozen=True, slots=True)
class ContextEfficiencyResult:
    """Traceable post-budget measurements for one case and strategy."""

    case_id: str
    strategy_id: str
    required_evidence_retained: float
    supporting_evidence_retained: float
    context_precision: float
    irrelevant_context_ratio: float
    budget_utilization: float
    context_bytes: int
    estimated_tokens: int
    selected_paths: tuple[ArtifactPath, ...]
    exclusion_reason_counts: tuple[tuple[SelectionReason, int], ...]

    def __post_init__(self) -> None:
        for field_name in (
            "required_evidence_retained",
            "supporting_evidence_retained",
            "context_precision",
            "irrelevant_context_ratio",
            "budget_utilization",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{field_name} must be a finite number")
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{field_name} must be between zero and one")
        for field_name in ("context_bytes", "estimated_tokens"):
            value = getattr(self, field_name)
            if type(value) is not int:
                raise TypeError(f"{field_name} must be an integer")
            if value < 0:
                raise ValueError(f"{field_name} must not be negative")
        paths = tuple(self.selected_paths)
        if any(not isinstance(path, ArtifactPath) for path in paths):
            raise TypeError("selected_paths must contain ArtifactPath values")
        if len(set(paths)) != len(paths):
            raise ValueError("selected_paths must not contain duplicates")
        reasons = tuple(self.exclusion_reason_counts)
        if any(
            not isinstance(reason, SelectionReason) or type(count) is not int or count < 1
            for reason, count in reasons
        ):
            raise ValueError("exclusion_reason_counts must contain positive reason counts")
        if len({reason for reason, _ in reasons}) != len(reasons):
            raise ValueError("exclusion reasons must be unique")
        if reasons != tuple(sorted(reasons, key=lambda item: item[0].value)):
            raise ValueError("exclusion reasons must use canonical ordering")
        object.__setattr__(self, "selected_paths", paths)
        object.__setattr__(self, "exclusion_reason_counts", reasons)

    def quality_metrics(self) -> tuple[MetricResult, ...]:
        """Return bounded quality and efficiency scores for run aggregation."""
        values = (
            ("context-required-evidence-retained", self.required_evidence_retained),
            ("context-supporting-evidence-retained", self.supporting_evidence_retained),
            ("context-precision", self.context_precision),
            ("context-irrelevant-ratio", self.irrelevant_context_ratio),
            ("context-budget-utilization", self.budget_utilization),
        )
        return tuple(
            MetricResult(self.case_id, self.strategy_id, metric_name, value)
            for metric_name, value in values
        )


def _bundle_paths(bundle: ContextBundle) -> tuple[ArtifactPath, ...]:
    return tuple(
        dict.fromkeys(item.source_path for item in bundle.items if item.source_path is not None)
    )


def _budget_utilization(
    bundle: ContextBundle,
    budget: ContextBudget,
    estimated_tokens: int,
) -> float:
    usages: list[float] = []
    statistics = bundle.statistics
    values = (
        (estimated_tokens, budget.max_estimated_tokens),
        (statistics.character_count, budget.max_characters),
        (statistics.byte_count, budget.max_bytes),
        (statistics.artifact_count, budget.max_artifacts),
        (statistics.excerpt_count, budget.max_excerpts),
        (statistics.item_count, budget.max_items),
    )
    usages.extend(actual / maximum for actual, maximum in values if maximum is not None)
    if budget.max_item_bytes is not None:
        largest_item = max((len(item.content.encode("utf-8")) for item in bundle.items), default=0)
        usages.append(largest_item / budget.max_item_bytes)
    if not usages:
        return 0.0
    return min(max(usages), 1.0)


def evaluate_context_efficiency(
    case: EvaluationCase,
    strategy_id: str,
    bundle: ContextBundle,
    retrieval_result: RetrievalResult,
) -> ContextEfficiencyResult:
    """Evaluate retained evidence and cost after Context Bundle budgeting."""
    if not isinstance(case, EvaluationCase):
        raise TypeError("case must be an EvaluationCase")
    if not isinstance(strategy_id, str) or not strategy_id.strip():
        raise ValueError("strategy_id must be a non-empty string")
    if not isinstance(bundle, ContextBundle):
        raise TypeError("bundle must be a ContextBundle")
    if not isinstance(retrieval_result, RetrievalResult):
        raise TypeError("retrieval_result must be a RetrievalResult")
    if bundle.retrieval_id != retrieval_result.retrieval_id:
        raise ValueError("Context Bundle must belong to the Retrieval Result")
    if bundle.project_fingerprint != retrieval_result.project_fingerprint:
        raise ValueError("Context Bundle and Retrieval Result fingerprints must match")

    paths = _bundle_paths(bundle)
    selections = tuple(StrategySelection(path, rank) for rank, path in enumerate(paths, start=1))
    irrelevant = {
        judgment.path
        for judgment in case.judgments
        if judgment.relevance is RelevanceLevel.IRRELEVANT
    }
    irrelevant_ratio = len(irrelevant.intersection(paths)) / len(paths) if paths else 0.0
    context_text = "\n".join(item.content for item in bundle.items)
    estimated_tokens = estimate_text_tokens(context_text)
    excluded_reasons = Counter(
        candidate.rationale.primary_reason
        for candidate in retrieval_result.candidates
        if candidate.outcome in (CandidateOutcome.EXCLUDED, CandidateOutcome.DEFERRED)
        and candidate.rationale is not None
    )

    return ContextEfficiencyResult(
        case_id=case.case_id,
        strategy_id=strategy_id,
        required_evidence_retained=artifact_recall(
            case.judgments,
            selections,
            RelevanceLevel.REQUIRED,
        ),
        supporting_evidence_retained=artifact_recall(
            case.judgments,
            selections,
            RelevanceLevel.SUPPORTING,
        ),
        context_precision=precision_over_judged(case.judgments, selections),
        irrelevant_context_ratio=irrelevant_ratio,
        budget_utilization=_budget_utilization(
            bundle,
            retrieval_result.applied_budget,
            estimated_tokens,
        ),
        context_bytes=bundle.statistics.byte_count,
        estimated_tokens=estimated_tokens,
        selected_paths=paths,
        exclusion_reason_counts=tuple(
            sorted(excluded_reasons.items(), key=lambda item: item[0].value)
        ),
    )
