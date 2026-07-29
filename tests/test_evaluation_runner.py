"""Tests for CF-015-E006 end-to-end evaluation orchestration."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from contextforge.adapters.evaluation import (
    FilesystemEvaluationCaseExecutor,
    FilesystemEvaluationSuiteLoader,
    FilesystemPatchBehaviorValidator,
)
from contextforge.domain import ArtifactPath
from contextforge.domain.tasks import RequestedOutput
from contextforge.evaluation import (
    CaseEvaluationOutput,
    CaseRunStatus,
    EvaluationCase,
    EvaluationRunner,
    StrategyResult,
)

FIXED_TIME = datetime(2026, 1, 2, 3, 4, tzinfo=UTC)
FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "evaluation"


@dataclass
class _RecordingExecutor:
    failed_case_id: str | None = None

    def execute(self, case: EvaluationCase) -> CaseEvaluationOutput:
        if case.case_id == self.failed_case_id:
            raise RuntimeError("intentional failure")
        return CaseEvaluationOutput(
            (StrategyResult(case.case_id, "test-strategy", (), 0.0),),
            (),
        )


def _suite():
    return FilesystemEvaluationSuiteLoader(FIXTURE_ROOT).load(Path("suites/core.json"))


def test_runner_filters_by_identifier_and_all_requested_tags() -> None:
    result = EvaluationRunner(_RecordingExecutor(), clock=lambda: FIXED_TIME).run(
        _suite(),
        case_ids=("budget-pressure", "dependency-closure"),
        tags=("dependency", "retrieval"),
    )

    assert result.metadata.selected_case_ids == ("dependency-closure",)
    assert result.metadata.selected_tags == ("dependency", "retrieval")
    assert result.metadata.offline is True
    assert result.cases[0].status is CaseRunStatus.COMPLETED


def test_runner_isolates_case_failures_and_records_reproducibility_metadata() -> None:
    runner = EvaluationRunner(
        _RecordingExecutor("budget-pressure"),
        configuration=(("profile", "offline"),),
        source_revision="abc123",
        clock=lambda: FIXED_TIME,
    )

    first = runner.run(
        _suite(),
        case_ids=("budget-pressure", "dependency-closure"),
    )
    second = runner.run(
        _suite(),
        case_ids=("budget-pressure", "dependency-closure"),
    )

    assert [record.status for record in first.cases] == [
        CaseRunStatus.FAILED,
        CaseRunStatus.COMPLETED,
    ]
    assert tuple(item.case_id for item in first.run.strategy_results) == ("dependency-closure",)
    assert first.metadata.source_revision == "abc123"
    assert first.metadata.configuration_fingerprint.startswith("sha256:")
    assert first.run.to_json() == second.run.to_json()


def test_runner_rejects_unknown_case_filter() -> None:
    with pytest.raises(ValueError, match="Unknown evaluation case"):
        EvaluationRunner(_RecordingExecutor()).run(_suite(), case_ids=("missing",))


def test_runner_completes_production_pipeline_offline() -> None:
    loader = FilesystemEvaluationSuiteLoader(FIXTURE_ROOT)
    result = EvaluationRunner(
        FilesystemEvaluationCaseExecutor(loader),
        clock=lambda: FIXED_TIME,
    ).run(_suite(), case_ids=("direct-path",))

    assert result.cases[0].status is CaseRunStatus.COMPLETED
    assert result.cases[0].error_type is None
    assert result.cases[0].error_message is None
    assert result.metadata.offline is True
    assert result.run.strategy_results
    assert result.run.metric_results
    assert any(
        metric.metric_name == "context-required-evidence-retained"
        for metric in result.run.metric_results
    )


def test_runner_completes_every_initial_core_case() -> None:
    loader = FilesystemEvaluationSuiteLoader(FIXTURE_ROOT)

    result = EvaluationRunner(
        FilesystemEvaluationCaseExecutor(loader),
        clock=lambda: FIXED_TIME,
    ).run(_suite())

    assert all(record.status is CaseRunStatus.COMPLETED for record in result.cases)


def test_core_suite_covers_retrieval_dependencies_and_insufficient_evidence() -> None:
    suite = _suite()

    assert len(suite.cases) == 12
    assert {
        "direct",
        "symbol",
        "synonym",
        "ambiguity",
        "dependency",
        "budget",
        "deep",
        "homonym",
        "test-navigation",
        "unsolvable",
    } <= {tag for case in suite.cases for tag in case.tags}


def test_unsolvable_case_reports_zero_required_recall_without_failing() -> None:
    loader = FilesystemEvaluationSuiteLoader(FIXTURE_ROOT)
    result = EvaluationRunner(
        FilesystemEvaluationCaseExecutor(loader),
        clock=lambda: FIXED_TIME,
    ).run(_suite(), case_ids=("unsolvable-missing-artifact",))

    assert result.cases[0].status is CaseRunStatus.COMPLETED
    primary_recall = next(
        metric
        for metric in result.run.metric_results
        if metric.strategy_id == "contextforge" and metric.metric_name == "required-artifact-recall"
    )
    assert primary_recall.value == 0.0


def test_direct_symbol_case_prioritizes_the_defining_artifact() -> None:
    loader = FilesystemEvaluationSuiteLoader(FIXTURE_ROOT)
    result = EvaluationRunner(
        FilesystemEvaluationCaseExecutor(loader),
        clock=lambda: FIXED_TIME,
    ).run(_suite(), case_ids=("direct-symbol",))

    primary_recall = next(
        metric
        for metric in result.run.metric_results
        if metric.strategy_id == "contextforge" and metric.metric_name == "required-artifact-recall"
    )
    assert primary_recall.value == 1.0


class _IsolationRecordingExecutor(FilesystemEvaluationCaseExecutor):
    seen_root: Path | None = None

    def _execute_at_root(
        self,
        case: EvaluationCase,
        root: Path,
    ) -> CaseEvaluationOutput:
        assert root.is_dir()
        self.seen_root = root
        return CaseEvaluationOutput((), ())


def test_patch_cases_execute_only_on_temporary_fixture_copies() -> None:
    loader = FilesystemEvaluationSuiteLoader(FIXTURE_ROOT)
    original = next(case for case in _suite().cases if case.case_id == "direct-path")
    patch_case = replace(original, requested_output=RequestedOutput.PATCH_PROPOSAL)
    executor = _IsolationRecordingExecutor(loader)

    executor.execute(patch_case)

    assert executor.seen_root is not None
    assert executor.seen_root != loader.fixture_root(original.fixture_project_id)
    assert not executor.seen_root.exists()


def test_patch_behavior_is_measured_only_inside_the_temporary_copy() -> None:
    loader = FilesystemEvaluationSuiteLoader(FIXTURE_ROOT)
    original = next(case for case in _suite().cases if case.case_id == "direct-path")
    patch_case = replace(
        original,
        requested_output=RequestedOutput.PATCH_PROPOSAL,
        expected_changed_paths=(ArtifactPath("src/app.py"),),
    )
    original_app = loader.fixture_root(original.fixture_project_id) / "src" / "app.py"
    original_content = original_app.read_text(encoding="utf-8")

    def apply_patch(case: EvaluationCase, root: Path) -> None:
        del case
        target = root / "src" / "app.py"
        target.write_text(
            target.read_text(encoding="utf-8").replace(
                "return format_greeting(name)",
                "return format_greeting(name).upper()",
            ),
            encoding="utf-8",
        )

    def check_behavior(case: EvaluationCase, root: Path) -> bool:
        del case
        return "return format_greeting(name).upper()" in (root / "src" / "app.py").read_text(
            encoding="utf-8"
        )

    result = EvaluationRunner(
        FilesystemEvaluationCaseExecutor(
            loader,
            validators=(FilesystemPatchBehaviorValidator(apply_patch, check_behavior),),
        ),
        clock=lambda: FIXED_TIME,
    ).run(replace(_suite(), cases=(patch_case,)))

    metrics = {
        metric.metric_name: metric.value
        for metric in result.run.metric_results
        if metric.strategy_id == "contextforge"
    }
    assert result.cases[0].status is CaseRunStatus.COMPLETED
    assert metrics["patch-expected-path-recall"] == 1.0
    assert metrics["patch-paths-exact"] == 1.0
    assert metrics["patch-fixture-tests-passed"] == 1.0
    assert original_app.read_text(encoding="utf-8") == original_content
