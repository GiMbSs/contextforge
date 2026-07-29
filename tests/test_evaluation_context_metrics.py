"""Tests for CF-015-E004 post-budget Context Bundle metrics."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from contextforge.context import (
    ContextBundle,
    ContextCoverage,
    ContextItem,
    ContextSection,
    ContextSectionKind,
    ContextStatistics,
)
from contextforge.diagnostics import DiagnosticCollection
from contextforge.domain import (
    ArtifactPath,
    FingerprintOrdering,
    fingerprint_project,
    new_artifact_id,
    new_context_bundle_id,
    new_index_id,
    new_project_id,
    new_retrieval_id,
    new_task_id,
)
from contextforge.domain.tasks import RequestedOutput, TaskKind
from contextforge.evaluation import (
    EvaluationCase,
    RelevanceJudgment,
    RelevanceLevel,
    evaluate_context_efficiency,
    evaluate_retrieval_metrics,
)
from contextforge.evaluation.models import StrategyResult, StrategySelection
from contextforge.prompt import estimate_text_tokens
from contextforge.retrieval import (
    CandidateEligibility,
    CandidateOutcome,
    CandidateType,
    ContextBudget,
    RetrievalCandidate,
    RetrievalEvidence,
    RetrievalResult,
    RetrievalStatistics,
    RetrievalStatus,
    SelectedContextItem,
    SelectionDecision,
    SelectionRationale,
    SelectionReason,
)

NOW = datetime(2026, 7, 29, tzinfo=UTC)
FINGERPRINT = fingerprint_project(("fixture",), ordering=FingerprintOrdering.ORDERED)


def make_case() -> EvaluationCase:
    return EvaluationCase(
        "budget-pressure",
        "fixture",
        FINGERPRINT,
        "Explain the behavior.",
        TaskKind.EXPLAIN,
        RequestedOutput.ANALYSIS,
        (
            RelevanceJudgment(ArtifactPath("required.py"), RelevanceLevel.REQUIRED),
            RelevanceJudgment(ArtifactPath("supporting.py"), RelevanceLevel.SUPPORTING),
            RelevanceJudgment(ArtifactPath("irrelevant.py"), RelevanceLevel.IRRELEVANT),
        ),
        ContextBudget(max_items=2, max_bytes=1_000, max_estimated_tokens=100),
    )


def make_retrieval_and_bundle(
    selected: tuple[tuple[str, str], ...],
    excluded: tuple[tuple[str, SelectionReason], ...] = (),
) -> tuple[RetrievalResult, ContextBundle]:
    task_id = new_task_id()
    retrieval_id = new_retrieval_id()
    candidates: list[RetrievalCandidate] = []
    selected_items: list[SelectedContextItem] = []
    context_items: list[ContextItem] = []
    rationales: list[SelectionRationale] = []

    for index, (path, content) in enumerate(selected):
        candidate_id = f"candidate_selected_{index}"
        artifact_id = new_artifact_id()
        rationale = SelectionRationale(
            candidate_id,
            SelectionDecision.SELECTED,
            SelectionReason.REQUIRED_CONTEXT,
            (RetrievalEvidence("test", "fixture", path),),
            rank=index + 1,
        )
        candidate = RetrievalCandidate(
            candidate_id,
            CandidateType.FULL_ARTIFACT,
            path,
            f"artifact:{path}",
            rationale.evidence,
            CandidateEligibility.ELIGIBLE,
            CandidateOutcome.SELECTED,
            len(content.encode("utf-8")),
            estimate_text_tokens(content),
            artifact_id,
            rationale=rationale,
        )
        item = SelectedContextItem(
            f"context_item_{index}",
            candidate_id,
            artifact_id,
            candidate.content_reference,
            CandidateType.FULL_ARTIFACT,
            rationale,
            estimated_tokens=estimate_text_tokens(content),
            estimated_bytes=len(content.encode("utf-8")),
            estimated_characters=len(content),
        )
        candidates.append(candidate)
        selected_items.append(item)
        context_items.append(
            ContextItem(
                item,
                candidate.content_reference,
                content,
                ArtifactPath(path),
            )
        )
        rationales.append(rationale)

    for index, (path, reason) in enumerate(excluded):
        candidate_id = f"candidate_excluded_{index}"
        rationale = SelectionRationale(
            candidate_id,
            SelectionDecision.EXCLUDED,
            reason,
            (RetrievalEvidence("test", "fixture", path),),
        )
        candidates.append(
            RetrievalCandidate(
                candidate_id,
                CandidateType.FULL_ARTIFACT,
                path,
                f"artifact:{path}",
                rationale.evidence,
                CandidateEligibility.ELIGIBLE,
                CandidateOutcome.EXCLUDED,
                10,
                3,
                new_artifact_id(),
                rationale=rationale,
            )
        )
        rationales.append(rationale)

    retrieval = RetrievalResult(
        retrieval_id,
        task_id,
        new_index_id(),
        FINGERPRINT,
        ("test-strategy-v1",),
        tuple(candidates),
        tuple(selected_items),
        tuple(rationales),
        make_case().context_budget,
        DiagnosticCollection(),
        RetrievalStatistics(
            candidates_generated=len(candidates),
            candidates_evaluated=len(candidates),
            artifacts_selected=len(selected_items),
            candidates_budget_excluded=len(excluded),
            estimated_selected_tokens=sum(item.estimated_tokens or 0 for item in selected_items),
        ),
        RetrievalStatus.COMPLETE,
        NOW,
    )
    contents = tuple(item.content for item in context_items)
    item_ids = tuple(item.context_item_id for item in context_items)
    sections = (
        (
            ContextSection(
                "primary",
                ContextSectionKind.PRIMARY_IMPLEMENTATION,
                "Primary",
                item_ids,
                0,
            ),
        )
        if context_items
        else ()
    )
    bundle = ContextBundle(
        new_context_bundle_id(),
        task_id,
        retrieval_id,
        new_project_id(),
        FINGERPRINT,
        tuple(context_items),
        item_ids,
        sections,
        ContextStatistics(
            item_count=len(context_items),
            artifact_count=len(context_items),
            character_count=sum(len(content) for content in contents),
            byte_count=sum(len(content.encode("utf-8")) for content in contents),
            line_count=sum(content.count("\n") + 1 for content in contents if content),
            estimated_tokens=sum(item.estimated_tokens or 0 for item in selected_items),
        ),
        ContextCoverage(),
        DiagnosticCollection(),
        "1",
        "test-builder-v1",
        NOW,
    )
    return retrieval, bundle


def test_context_metrics_measure_retention_precision_cost_and_exclusions() -> None:
    retrieval, bundle = make_retrieval_and_bundle(
        (("required.py", "required content"), ("irrelevant.py", "distractor")),
        (("supporting.py", SelectionReason.CONTEXT_BUDGET_EXCEEDED),),
    )

    result = evaluate_context_efficiency(make_case(), "contextforge", bundle, retrieval)

    assert result.required_evidence_retained == 1.0
    assert result.supporting_evidence_retained == 0.0
    assert result.context_precision == 0.5
    assert result.irrelevant_context_ratio == 0.5
    assert result.context_bytes == len("required contentdistractor")
    assert result.estimated_tokens == estimate_text_tokens("required content\ndistractor")
    assert result.budget_utilization == 1.0
    assert result.exclusion_reason_counts == ((SelectionReason.CONTEXT_BUDGET_EXCEEDED, 1),)


def test_retrieval_and_context_quality_are_reported_separately() -> None:
    case = make_case()
    retrieval, bundle = make_retrieval_and_bundle(
        (("required.py", "required"),),
        (("supporting.py", SelectionReason.CONTEXT_BUDGET_EXCEEDED),),
    )
    ranking = StrategyResult(
        case.case_id,
        "contextforge",
        (
            StrategySelection(ArtifactPath("required.py"), 1),
            StrategySelection(ArtifactPath("supporting.py"), 2),
        ),
        0.0,
    )

    retrieval_metrics = evaluate_retrieval_metrics(case, ranking)
    context_result = evaluate_context_efficiency(case, "contextforge", bundle, retrieval)

    assert (
        next(
            metric.value
            for metric in retrieval_metrics
            if metric.metric_name == "supporting-artifact-recall"
        )
        == 1.0
    )
    assert context_result.supporting_evidence_retained == 0.0
    assert all(
        metric.metric_name.startswith("context-") for metric in context_result.quality_metrics()
    )


def test_empty_context_has_explicit_semantics_and_zero_size() -> None:
    retrieval, bundle = make_retrieval_and_bundle(
        (),
        (("required.py", SelectionReason.CONTEXT_BUDGET_EXCEEDED),),
    )

    result = evaluate_context_efficiency(make_case(), "contextforge", bundle, retrieval)

    assert result.required_evidence_retained == 0.0
    assert result.supporting_evidence_retained == 0.0
    assert result.context_precision == 1.0
    assert result.irrelevant_context_ratio == 0.0
    assert result.context_bytes == 0
    assert result.estimated_tokens == 0
    assert result.budget_utilization == 0.0


def test_context_metric_rejects_unrelated_retrieval_result() -> None:
    retrieval, bundle = make_retrieval_and_bundle((("required.py", "required"),))
    other, _ = make_retrieval_and_bundle((("required.py", "required"),))

    with pytest.raises(ValueError, match="belong"):
        evaluate_context_efficiency(make_case(), "contextforge", bundle, other)

    assert retrieval.retrieval_id == bundle.retrieval_id
