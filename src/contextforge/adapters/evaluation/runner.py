"""Read-only filesystem composition for evaluation case execution."""

from __future__ import annotations

import hashlib
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
        bundle: ContextBundle,
        retrieval_result: RetrievalResult,
    ) -> tuple[MetricResult, ...]:
        """Return bounded validation metrics for the primary strategy."""
        ...


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
        bundle = SimpleContextBuilder(root).build(retrieval, project_id=project_id)

        strategy_results = [primary]
        strategy_results.extend(strategy.evaluate(request) for strategy in self.baseline_strategies)
        metrics = [
            metric
            for result in strategy_results
            for metric in evaluate_retrieval_metrics(case, result)
        ]
        metrics.extend(
            evaluate_context_efficiency(
                case,
                CONTEXTFORGE_STRATEGY_ID,
                bundle,
                retrieval,
            ).quality_metrics()
        )
        for validator in self.validators:
            metrics.extend(validator.validate(case, bundle, retrieval))
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
