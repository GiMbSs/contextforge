"""Tests for CF-015-E001 immutable evaluation models."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from contextforge.domain import ArtifactPath
from contextforge.domain.fingerprints import FingerprintOrdering, fingerprint_project
from contextforge.domain.tasks import RequestedOutput, TaskKind
from contextforge.evaluation import (
    EvaluationCase,
    EvaluationRunResult,
    EvaluationSuite,
    MetricResult,
    RelevanceJudgment,
    RelevanceLevel,
    StrategyResult,
    StrategySelection,
)
from contextforge.retrieval import ContextBudget

FINGERPRINT = fingerprint_project(("fixture",), ordering=FingerprintOrdering.ORDERED)


def make_case(case_id: str = "direct-path") -> EvaluationCase:
    return EvaluationCase(
        case_id=case_id,
        fixture_project_id="small-python",
        fixture_fingerprint=FINGERPRINT,
        task_text="Explain src/main.py.",
        task_kind=TaskKind.EXPLAIN,
        requested_output=RequestedOutput.ANALYSIS,
        judgments=(
            RelevanceJudgment(ArtifactPath("tests/test_main.py"), RelevanceLevel.SUPPORTING),
            RelevanceJudgment(ArtifactPath("src/main.py"), RelevanceLevel.REQUIRED, ("main",)),
        ),
        context_budget=ContextBudget(max_estimated_tokens=500),
        tags=("retrieval", "direct"),
        expected_evidence=("src/main.py",),
    )


def test_case_normalizes_unordered_gold_data_for_deterministic_serialization() -> None:
    case = make_case()

    assert [str(item.path) for item in case.judgments] == [
        "src/main.py",
        "tests/test_main.py",
    ]
    assert case.tags == ("direct", "retrieval")
    assert (
        EvaluationSuite("core", "1.0", (case,)).to_json()
        == EvaluationSuite("core", "1.0", (case,)).to_json()
    )


@pytest.mark.parametrize("identifier", ["", "Has Caps", "../escape", "contains space"])
def test_invalid_evaluation_identifiers_fail_closed(identifier: str) -> None:
    with pytest.raises(ValueError):
        EvaluationSuite(identifier, "1.0", (make_case(),))


def test_invalid_artifact_paths_fail_before_entering_gold_data() -> None:
    with pytest.raises(ValueError, match="Parent traversal"):
        RelevanceJudgment(ArtifactPath("../secret"), RelevanceLevel.REQUIRED)


def test_duplicate_or_contradictory_artifact_judgments_fail_closed() -> None:
    required = RelevanceJudgment(ArtifactPath("src/main.py"), RelevanceLevel.REQUIRED)
    irrelevant = RelevanceJudgment(ArtifactPath("src/main.py"), RelevanceLevel.IRRELEVANT)

    with pytest.raises(ValueError, match="duplicate or contradictory"):
        EvaluationCase(
            "conflict",
            "small-python",
            FINGERPRINT,
            "Explain main.",
            TaskKind.EXPLAIN,
            RequestedOutput.ANALYSIS,
            (required, irrelevant),
            ContextBudget(max_items=1),
        )


def test_duplicate_symbols_labels_and_case_ids_fail_closed() -> None:
    with pytest.raises(ValueError, match="duplicates"):
        RelevanceJudgment(ArtifactPath("src/main.py"), RelevanceLevel.REQUIRED, ("main", "main"))
    with pytest.raises(ValueError, match="identifiers"):
        EvaluationSuite("core", "1.0", (make_case(), make_case()))


def test_strategy_and_metric_results_enforce_order_identity_and_bounds() -> None:
    selection = StrategySelection(ArtifactPath("src/main.py"), 1, 0.9)
    result = StrategyResult("direct-path", "contextforge", (selection,), 1.25)
    metric = MetricResult("direct-path", "contextforge", "required-recall", 1.0)

    assert result.selections == (selection,)
    assert metric.value == 1.0
    with pytest.raises(ValueError, match="contiguous"):
        StrategyResult(
            "direct-path",
            "contextforge",
            (StrategySelection(ArtifactPath("src/main.py"), 2),),
            1.0,
        )
    with pytest.raises(ValueError, match="between zero and one"):
        MetricResult("direct-path", "contextforge", "recall", 1.01)


def test_run_result_is_immutable_and_serializes_in_canonical_order() -> None:
    alpha = StrategyResult("alpha", "lexical", (), 0.0)
    beta = StrategyResult("beta", "lexical", (), 0.0)
    metrics = (
        MetricResult("beta", "lexical", "recall", 0.5),
        MetricResult("alpha", "lexical", "recall", 1.0),
    )
    run = EvaluationRunResult(
        "run-001",
        "core",
        (beta, alpha),
        metrics,
        datetime(2026, 7, 29, 12, tzinfo=UTC),
    )

    assert [item.case_id for item in run.strategy_results] == ["alpha", "beta"]
    assert '"created_at":"2026-07-29T12:00:00Z"' in run.to_json()
    with pytest.raises(FrozenInstanceError):
        run.run_id = "changed"  # type: ignore[misc]


def test_run_result_rejects_non_utc_timestamps_and_duplicate_results() -> None:
    result = StrategyResult("direct-path", "lexical", (), 0.0)
    with pytest.raises(ValueError, match="UTC"):
        EvaluationRunResult(
            "run-001",
            "core",
            (result,),
            (),
            datetime(2026, 7, 29),
        )
    with pytest.raises(ValueError, match="unique"):
        EvaluationRunResult(
            "run-001",
            "core",
            (result, result),
            (),
            datetime(2026, 7, 29, tzinfo=UTC),
        )
