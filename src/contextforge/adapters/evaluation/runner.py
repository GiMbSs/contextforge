"""Read-only filesystem composition for evaluation case execution."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from contextforge.adapters.evaluation.filesystem import (
    FilesystemEvaluationSuiteLoader,
    fingerprint_fixture_project,
)
from contextforge.adapters.filesystem.scanner import LocalProjectScanner
from contextforge.configuration import ScannerConfig
from contextforge.context import ContextBundle, SimpleContextBuilder
from contextforge.domain import ArtifactId, ArtifactPath, ProjectId, TaskId
from contextforge.domain.tasks import TaskSpecification
from contextforge.evaluation import (
    ArtifactBudgetEstimate,
    BudgetedAllFilesBaseline,
    CaseEvaluationError,
    CaseEvaluationOutput,
    EvaluationCase,
    EvaluationStrategy,
    EvaluationStrategyRequest,
    ExplicitOnlyBaseline,
    LexicalOnlyBaseline,
    MetricResult,
    StrategyResult,
    StrategySelection,
    evaluate_context_efficiency,
    evaluate_retrieval_metrics,
)
from contextforge.indexer import DeterministicProjectIndexer, IndexedArtifact, IndexRequest
from contextforge.project import ProjectRoot, ProjectRootSource
from contextforge.prompt import estimate_text_tokens
from contextforge.retrieval import RetrievalRequest, RetrievalResult, SimpleContextRetriever
from contextforge.scanner import ProjectArtifact, ScanRequest

CONTEXTFORGE_STRATEGY_ID = "contextforge"
_FIXED_TIME = datetime(2000, 1, 1, tzinfo=UTC)


class EvaluationOutputValidator(Protocol):
    """Optional provider or patch validation applied after context construction."""

    def validate(
        self,
        case: EvaluationCase,
        root: Path,
        bundle: ContextBundle,
        retrieval_result: RetrievalResult,
    ) -> tuple[MetricResult, ...]:
        """Return bounded validation metrics for the primary strategy."""
        ...


@dataclass(frozen=True, slots=True)
class FilesystemPatchBehaviorValidator:
    """Apply and behaviorally validate a patch inside an isolated fixture root."""

    patch_applier: Callable[[EvaluationCase, Path], None]
    behavior_check: Callable[[EvaluationCase, Path], bool]

    def validate(
        self,
        case: EvaluationCase,
        root: Path,
        bundle: ContextBundle,
        retrieval_result: RetrievalResult,
    ) -> tuple[MetricResult, ...]:
        """Measure resulting paths and behavior after applying a candidate patch."""
        del bundle, retrieval_result
        if case.requested_output.value != "patch_proposal" and not case.expected_changed_paths:
            return ()

        isolated_root = root.resolve(strict=True)
        if not isolated_root.is_dir():
            raise ValueError("Patch validation root must be a directory")
        before = self._snapshot(isolated_root)
        self.patch_applier(case, isolated_root)
        after = self._snapshot(isolated_root)

        changed = {
            path for path in before.keys() | after.keys() if before.get(path) != after.get(path)
        }
        expected = {str(path) for path in case.expected_changed_paths}
        expected_recall = (
            len(changed & expected) / len(expected) if expected else float(not changed)
        )
        exact_paths = changed == expected
        behavior_passed = bool(self.behavior_check(case, isolated_root))
        return (
            MetricResult(
                case.case_id,
                CONTEXTFORGE_STRATEGY_ID,
                "patch-expected-path-recall",
                expected_recall,
            ),
            MetricResult(
                case.case_id,
                CONTEXTFORGE_STRATEGY_ID,
                "patch-paths-exact",
                float(exact_paths),
            ),
            MetricResult(
                case.case_id,
                CONTEXTFORGE_STRATEGY_ID,
                "patch-fixture-tests-passed",
                float(behavior_passed),
            ),
        )

    @staticmethod
    def _snapshot(root: Path) -> dict[str, str]:
        snapshot: dict[str, str] = {}
        for candidate in sorted(root.rglob("*")):
            if not candidate.is_file():
                continue
            relative = candidate.relative_to(root).as_posix()
            snapshot[relative] = hashlib.sha256(candidate.read_bytes()).hexdigest()
        return snapshot


@dataclass(slots=True)
class _FixtureSource:
    root: Path

    def read(self, artifact: ProjectArtifact) -> bytes:
        target = self.root.joinpath(*artifact.path.parts).resolve(strict=True)
        target.relative_to(self.root)
        return target.read_bytes()


def _stable_task(case: EvaluationCase) -> TaskSpecification:
    digest = hashlib.sha256(f"{case.case_id}\0{case.fixture_fingerprint}".encode()).hexdigest()[:32]
    return TaskSpecification(
        TaskId(f"task_{digest}"),
        case.task_text,
        case.task_kind,
        case.requested_output,
    )


@dataclass(slots=True)
class FilesystemEvaluationCaseExecutor:
    """Run the production pipeline and baselines against verified fixtures."""

    loader: FilesystemEvaluationSuiteLoader
    baseline_strategies: tuple[EvaluationStrategy, ...] = field(
        default_factory=lambda: (
            LexicalOnlyBaseline(),
            ExplicitOnlyBaseline(),
            BudgetedAllFilesBaseline(),
        )
    )
    validators: tuple[EvaluationOutputValidator, ...] = ()
    scanner_configuration: ScannerConfig = field(default_factory=ScannerConfig)

    def execute(self, case: EvaluationCase) -> CaseEvaluationOutput:
        """Evaluate one fixture without writing to it or invoking a provider by default."""
        root = self.loader.fixture_root(case.fixture_project_id)
        if fingerprint_fixture_project(root) != case.fixture_fingerprint:
            raise ValueError("Fixture fingerprint does not match the evaluation case")
        if case.requested_output.value == "patch_proposal" or case.expected_changed_paths:
            with tempfile.TemporaryDirectory(prefix="contextforge-evaluation-") as temporary:
                isolated = Path(temporary) / "fixture"
                shutil.copytree(root, isolated)
                return self._execute_at_root(case, isolated)
        return self._execute_at_root(case, root)

    def _execute_at_root(
        self,
        case: EvaluationCase,
        root: Path,
    ) -> CaseEvaluationOutput:
        """Execute the common pipeline against an authorized source or temporary copy."""
        root = root.resolve(strict=True)
        project_id = ProjectId(
            f"project_{hashlib.sha256(case.fixture_project_id.encode()).hexdigest()[:32]}"
        )
        inventory = LocalProjectScanner().scan(
            ScanRequest(
                project_id,
                ProjectRoot(root, ProjectRootSource.EXPLICIT),
                self.scanner_configuration,
            )
        )
        project_index = DeterministicProjectIndexer(
            _FixtureSource(root),
            clock=lambda: _FIXED_TIME,
        ).index(IndexRequest(inventory))
        estimates = self._estimates(root, project_index.indexed_artifacts)
        request = EvaluationStrategyRequest(case, project_index, estimates)

        retrieval = SimpleContextRetriever().retrieve(
            RetrievalRequest(_stable_task(case), project_index, case.context_budget)
        )
        primary = self._primary_result(case, project_index.indexed_artifacts, retrieval)
        strategy_results = [primary]
        strategy_results.extend(strategy.evaluate(request) for strategy in self.baseline_strategies)
        metrics = [
            metric
            for result in strategy_results
            for metric in evaluate_retrieval_metrics(case, result)
        ]
        partial_output = CaseEvaluationOutput(tuple(strategy_results), tuple(metrics))
        try:
            bundle = SimpleContextBuilder(root).build(retrieval, project_id=project_id)
        except (OSError, ValueError) as error:
            raise CaseEvaluationError(str(error), partial_output) from error
        metrics.extend(
            evaluate_context_efficiency(
                case,
                CONTEXTFORGE_STRATEGY_ID,
                bundle,
                retrieval,
            ).quality_metrics()
        )
        for validator in self.validators:
            metrics.extend(validator.validate(case, root, bundle, retrieval))
        return CaseEvaluationOutput(tuple(strategy_results), tuple(metrics))

    @staticmethod
    def _estimates(
        root: Path,
        indexed_artifacts: tuple[IndexedArtifact, ...],
    ) -> tuple[ArtifactBudgetEstimate, ...]:
        estimates: list[ArtifactBudgetEstimate] = []
        for artifact in indexed_artifacts:
            path = artifact.path
            if path is None:
                continue
            target = root.joinpath(*path.parts)
            content = target.read_bytes() if target.is_file() else b""
            text = content.decode("utf-8", errors="replace")
            estimates.append(
                ArtifactBudgetEstimate(
                    path,
                    len(content),
                    len(text),
                    estimate_text_tokens(text),
                )
            )
        return tuple(estimates)

    @staticmethod
    def _primary_result(
        case: EvaluationCase,
        indexed_artifacts: tuple[IndexedArtifact, ...],
        retrieval: RetrievalResult,
    ) -> StrategyResult:
        paths: dict[ArtifactId, ArtifactPath] = {
            artifact.artifact_id: artifact.path
            for artifact in indexed_artifacts
            if artifact.path is not None
        }
        selections: list[StrategySelection] = []
        seen: set[ArtifactPath] = set()
        for item in retrieval.selected_items:
            if item.artifact_id is None or item.artifact_id not in paths:
                continue
            path = paths[item.artifact_id]
            if path in seen:
                continue
            seen.add(path)
            selections.append(StrategySelection(path, len(selections) + 1, item.rationale.score))
        return StrategyResult(
            case.case_id,
            CONTEXTFORGE_STRATEGY_ID,
            tuple(selections),
            0.0,
        )
