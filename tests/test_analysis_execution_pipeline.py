"""Tests for the first complete analysis-only application pipeline."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from contextforge.application import (
    AnalysisExecutionPipeline,
    AnalysisPipelineError,
    ExecuteTask,
)
from contextforge.context import (
    ContextBundle,
    ContextCoverage,
    ContextStatistics,
)
from contextforge.diagnostics import DiagnosticCollection
from contextforge.domain import (
    FingerprintOrdering,
    IndexId,
    InventoryId,
    ProjectId,
    RequestedOutput,
    TaskKind,
    TaskSpecification,
    fingerprint_project,
    new_context_bundle_id,
    new_index_id,
    new_inventory_id,
    new_project_id,
    new_retrieval_id,
    new_task_id,
)
from contextforge.indexer import (
    IndexMeasurements,
    IndexRequest,
    IndexStatus,
    ProjectIndex,
)
from contextforge.provider import (
    DeterministicMockProvider,
    MockProviderScenario,
)
from contextforge.retrieval import (
    ContextBudget,
    RetrievalRequest,
    RetrievalResult,
    RetrievalStatistics,
    RetrievalStatus,
)
from contextforge.scanner import (
    DiscoveryStatus,
    ProjectInventory,
    ScanStatistics,
)

NOW = datetime(2026, 7, 26, tzinfo=UTC)


def _inputs() -> tuple[ProjectId, ProjectInventory, ProjectIndex, TaskSpecification]:
    project_id = new_project_id()
    fingerprint = fingerprint_project(("project",), ordering=FingerprintOrdering.ORDERED)
    inventory = ProjectInventory(
        new_inventory_id(),
        project_id,
        fingerprint,
        (),
        ScanStatistics(),
        NOW,
        "scanner-v1",
        status=DiscoveryStatus.COMPLETE,
    )
    project_index = ProjectIndex(
        new_index_id(),
        project_id,
        inventory.inventory_id,
        fingerprint,
        "1",
        "indexer-v1",
        (),
        NOW,
        status=IndexStatus.COMPLETE,
        measurements=IndexMeasurements(),
    )
    task = TaskSpecification(
        new_task_id(),
        "Explain the project.",
        TaskKind.EXPLAIN,
        RequestedOutput.ANALYSIS,
    )
    return project_id, inventory, project_index, task


class _InventoryStorage:
    def __init__(self, inventory: ProjectInventory) -> None:
        self.inventory = inventory

    def load(self, inventory_id: InventoryId) -> ProjectInventory | None:
        return self.inventory

    def load_latest(self, project_id: ProjectId) -> ProjectInventory | None:
        return self.inventory

    def save(self, inventory: ProjectInventory) -> None:
        raise AssertionError("existing inventory must be reused")


class _IndexStorage:
    def __init__(self, project_index: ProjectIndex) -> None:
        self.project_index = project_index

    def load(self, project_id: ProjectId) -> ProjectIndex | None:
        return self.project_index

    def save(self, project_index: ProjectIndex) -> None:
        raise AssertionError("existing index must be reused")

    def remove(self, index_id: IndexId) -> None:
        raise AssertionError("remove must not be called")


class _UnusedIndexer:
    def index(self, request: IndexRequest) -> ProjectIndex:
        raise AssertionError("compatible index must be reused")


class _Retriever:
    def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        return RetrievalResult(
            new_retrieval_id(),
            request.task.task_id,
            request.project_index.index_id,
            request.project_index.project_fingerprint,
            ("test-retriever-v1",),
            (),
            (),
            (),
            request.budget,
            DiagnosticCollection(),
            RetrievalStatistics(),
            RetrievalStatus.INCOMPLETE,
            NOW,
        )


class _BundleBuilder:
    def build(
        self,
        retrieval_result: RetrievalResult,
        *,
        project_id: ProjectId,
    ) -> ContextBundle:
        return ContextBundle(
            new_context_bundle_id(),
            retrieval_result.task_id,
            retrieval_result.retrieval_id,
            project_id,
            retrieval_result.project_fingerprint,
            (),
            (),
            (),
            ContextStatistics(),
            ContextCoverage(),
            DiagnosticCollection(),
            "1",
            "test-builder-v1",
            NOW,
        )


class _Providers:
    def __init__(self) -> None:
        self.provider = DeterministicMockProvider(
            MockProviderScenario.SUCCESSFUL_ANALYSIS,
            NOW,
        )

    def get(self, provider_id: str) -> DeterministicMockProvider | None:
        return self.provider if provider_id == "mock" else None


def _pipeline(
    inventory: ProjectInventory,
    project_index: ProjectIndex,
) -> AnalysisExecutionPipeline:
    return AnalysisExecutionPipeline(
        inventory_storage=_InventoryStorage(inventory),
        index_storage=_IndexStorage(project_index),
        indexer=_UnusedIndexer(),
        retriever=_Retriever(),
        context_builder=_BundleBuilder(),
        providers=_Providers(),
        budget=ContextBudget(max_items=5, max_bytes=10_000),
        clock=lambda: NOW,
    )


def test_analysis_pipeline_runs_every_read_only_stage_with_traceability() -> None:
    project_id, inventory, project_index, task = _inputs()

    result = _pipeline(inventory, project_index).execute(ExecuteTask(project_id, task, "mock"))

    assert result.inventory_id == inventory.inventory_id
    assert result.project_index is project_index
    assert result.retrieval_result.task_id == task.task_id
    assert result.context_bundle.retrieval_id == result.retrieval_result.retrieval_id
    assert result.inference_request.context_bundle_id == result.context_bundle.bundle_id
    assert result.inference_response.request_id == result.inference_request.request_id
    assert result.analysis.summary == "Deterministic mock analysis."


def test_analysis_pipeline_rejects_patch_output_before_provider_invocation() -> None:
    project_id, inventory, project_index, task = _inputs()
    patch_task = TaskSpecification(
        task.task_id,
        task.task_text,
        TaskKind.MODIFY,
        RequestedOutput.PATCH_PROPOSAL,
    )

    with pytest.raises(AnalysisPipelineError, match="requires analysis"):
        _pipeline(inventory, project_index).execute(ExecuteTask(project_id, patch_task, "mock"))
