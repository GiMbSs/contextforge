"""Tests for CF-015-E005 deterministic baseline strategies."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from contextforge.domain import (
    ArtifactPath,
    ProjectFingerprint,
    new_artifact_id,
    new_index_id,
    new_inventory_id,
    new_project_id,
)
from contextforge.domain.tasks import RequestedOutput, TaskKind
from contextforge.evaluation import (
    ArtifactBudgetEstimate,
    BaselineMetricDelta,
    BudgetedAllFilesBaseline,
    EvaluationCase,
    EvaluationStrategy,
    EvaluationStrategyRequest,
    ExplicitOnlyBaseline,
    LexicalOnlyBaseline,
    MetricResult,
    calculate_baseline_deltas,
)
from contextforge.indexer import (
    IndexedArtifact,
    IndexingState,
    ProjectIndex,
    SearchUnit,
    SearchUnitKind,
    SourceLocation,
    Symbol,
    SymbolKind,
)
from contextforge.retrieval import ContextBudget

FINGERPRINT = ProjectFingerprint("project_sha256_" + "4" * 64)
NOW = datetime(2026, 7, 29, tzinfo=UTC)
DEFAULT_BUDGET = ContextBudget(max_artifacts=4)


def make_index() -> ProjectIndex:
    specifications = (
        ("src/app.py", "entry point calls greeting service"),
        ("src/service.py", "greeting service formats greeting"),
        ("src/settings.py", "configuration value"),
        ("docs/notes.md", "historical greeting notes"),
    )
    artifacts: list[IndexedArtifact] = []
    units: list[SearchUnit] = []
    for order, (path, text) in enumerate(specifications):
        artifact_id = new_artifact_id()
        unit_id = f"search_unit_{order}"
        artifacts.append(
            IndexedArtifact(
                artifact_id,
                IndexingState.FULLY_INDEXED,
                "test",
                "1",
                FINGERPRINT,
                search_unit_ids=(unit_id,),
                path=ArtifactPath(path),
            )
        )
        units.append(
            SearchUnit(
                unit_id,
                artifact_id,
                SourceLocation(artifact_id, 1, 1, 1, len(text)),
                SearchUnitKind.SOURCE_BLOCK,
                text,
                order,
            )
        )
    service = artifacts[1]
    symbol = Symbol(
        "symbol_format_greeting",
        "format_greeting",
        SymbolKind.FUNCTION,
        service.artifact_id,
        SourceLocation(service.artifact_id, 1, 1, 1, 10),
    )
    return ProjectIndex(
        new_index_id(),
        new_project_id(),
        new_inventory_id(),
        FINGERPRINT,
        "1",
        "test",
        tuple(artifacts),
        NOW,
        symbols=(symbol,),
        search_units=tuple(units),
    )


def make_case(
    text: str,
    budget: ContextBudget = DEFAULT_BUDGET,
) -> EvaluationCase:
    return EvaluationCase(
        "baseline-case",
        "fixture",
        FINGERPRINT,
        text,
        TaskKind.EXPLAIN,
        RequestedOutput.ANALYSIS,
        (),
        budget,
    )


def make_request(
    text: str,
    *,
    budget: ContextBudget = DEFAULT_BUDGET,
) -> EvaluationStrategyRequest:
    index = make_index()
    estimates = tuple(
        ArtifactBudgetEstimate(artifact.path, 40, 40, 11)
        for artifact in index.indexed_artifacts
        if artifact.path is not None
    )
    return EvaluationStrategyRequest(make_case(text, budget), index, estimates)


def test_lexical_baseline_ranks_task_text_matches_and_deduplicates_artifacts() -> None:
    request = make_request("Explain greeting service.")

    result = LexicalOnlyBaseline().evaluate(request)

    assert tuple(str(item.path) for item in result.selections[:2]) == (
        "src/service.py",
        "src/app.py",
    )
    assert len({item.path for item in result.selections}) == len(result.selections)
    assert result.duration_ms == 0.0


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Explain src/app.py.", ("src/app.py",)),
        ("Explain `format_greeting`.", ("src/service.py",)),
        ("Explain greeting behavior.", ()),
    ],
)
def test_explicit_baseline_uses_only_direct_references(
    text: str,
    expected: tuple[str, ...],
) -> None:
    result = ExplicitOnlyBaseline().evaluate(make_request(text))

    assert tuple(str(item.path) for item in result.selections) == expected


def test_all_files_baseline_uses_path_order_and_the_same_budget() -> None:
    request = make_request(
        "Explain the project.",
        budget=ContextBudget(max_artifacts=2, max_bytes=80, max_estimated_tokens=22),
    )

    result = BudgetedAllFilesBaseline().evaluate(request)

    assert tuple(str(item.path) for item in result.selections) == (
        "docs/notes.md",
        "src/app.py",
    )


def test_every_baseline_receives_the_identical_request_contract() -> None:
    request = make_request(
        "Explain src/app.py greeting.",
        budget=ContextBudget(max_artifacts=1),
    )
    strategies: tuple[EvaluationStrategy, ...] = (
        LexicalOnlyBaseline(),
        ExplicitOnlyBaseline(),
        BudgetedAllFilesBaseline(),
    )

    results = tuple(strategy.evaluate(request) for strategy in strategies)

    assert {result.case_id for result in results} == {request.case.case_id}
    assert all(len(result.selections) <= 1 for result in results)
    assert request.case.context_budget.max_artifacts == 1


def test_budget_skips_oversized_artifacts_without_mutating_snapshot() -> None:
    request = make_request(
        "Explain greeting.",
        budget=ContextBudget(max_artifacts=2, max_item_bytes=39),
    )
    before = request.project_index

    result = BudgetedAllFilesBaseline().evaluate(request)

    assert result.selections == ()
    assert request.project_index is before
    assert request.project_index.indexed_artifacts == before.indexed_artifacts


def test_strategy_request_requires_estimates_for_the_exact_snapshot() -> None:
    index = make_index()

    with pytest.raises(ValueError, match="exactly cover"):
        EvaluationStrategyRequest(make_case("Explain."), index, ())


def test_metric_deltas_compare_primary_with_each_baseline() -> None:
    primary = (MetricResult("baseline-case", "contextforge", "required-recall", 0.75),)
    baselines = (
        MetricResult("baseline-case", "baseline-lexical", "required-recall", 0.5),
        MetricResult("baseline-case", "baseline-explicit", "required-recall", 1.0),
    )

    deltas = calculate_baseline_deltas(primary, baselines)

    assert deltas == (
        BaselineMetricDelta(
            "baseline-case",
            "required-recall",
            "contextforge",
            "baseline-explicit",
            0.75,
            1.0,
            -0.25,
        ),
        BaselineMetricDelta(
            "baseline-case",
            "required-recall",
            "contextforge",
            "baseline-lexical",
            0.75,
            0.5,
            0.25,
        ),
    )
