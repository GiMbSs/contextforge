"""Reusable preparation of validated task context for inference pipelines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from contextforge.application.indexing import (
    InventoryNotFoundError,
    InventoryStorage,
    ProjectIndexBuild,
)
from contextforge.application.messages import BuildProjectIndex, ExecuteTask
from contextforge.context import (
    ContextBundle,
    ContextBundleValidationResult,
    ContextBundleValidator,
)
from contextforge.diagnostics import DiagnosticCollection
from contextforge.domain import InventoryId, ProjectId
from contextforge.indexer import Indexer, IndexStorage, ProjectIndex
from contextforge.retrieval import (
    ContextBudget,
    ContextRetriever,
    RetrievalRequest,
    RetrievalResult,
)
from contextforge.scanner import ProjectInventory


class ContextBundleBuilder(Protocol):
    """Application-facing boundary for validated context construction."""

    def build(
        self,
        retrieval_result: RetrievalResult,
        *,
        project_id: ProjectId,
    ) -> ContextBundle:
        """Build exactly the context selected by retrieval."""
        ...


class ContextPreparationError(RuntimeError):
    """A context preparation stage returned inconsistent output."""


@dataclass(frozen=True, slots=True)
class ContextPreparationResult:
    """Immutable artifacts shared by analysis and patch prompt pipelines."""

    inventory_id: InventoryId
    inventory: ProjectInventory
    project_index: ProjectIndex
    retrieval_result: RetrievalResult
    context_bundle: ContextBundle
    validation: ContextBundleValidationResult
    diagnostics: DiagnosticCollection


def merge_diagnostics(*collections: DiagnosticCollection) -> DiagnosticCollection:
    """Merge and deterministically deduplicate diagnostic collections."""
    unique = {item.to_json(): item for collection in collections for item in collection}
    return DiagnosticCollection(tuple(unique.values()))


class ContextPreparationPipeline:
    """Prepare the exact validated project context needed by a task."""

    def __init__(
        self,
        *,
        inventory_storage: InventoryStorage,
        index_storage: IndexStorage,
        indexer: Indexer,
        retriever: ContextRetriever,
        context_builder: ContextBundleBuilder,
        budget: ContextBudget,
    ) -> None:
        self._inventory_storage = inventory_storage
        self._index_storage = index_storage
        self._indexer = indexer
        self._retriever = retriever
        self._context_builder = context_builder
        self._budget = budget

    def prepare(self, command: ExecuteTask) -> ContextPreparationResult:
        """Resolve or build every read-only artifact through the context bundle."""
        if not isinstance(command, ExecuteTask):
            raise TypeError("command must be an ExecuteTask")
        inventory = self._inventory_storage.load_latest(command.project_id)
        if inventory is None:
            raise InventoryNotFoundError(str(command.project_id))
        project_index = self._index_storage.load(command.project_id)
        if (
            project_index is None
            or project_index.source_inventory_id != inventory.inventory_id
            or project_index.project_fingerprint != inventory.project_fingerprint
        ):
            project_index = ProjectIndexBuild(
                self._indexer,
                self._inventory_storage,
                self._index_storage,
            ).execute(BuildProjectIndex(command.project_id, inventory.inventory_id))

        retrieval = self._retriever.retrieve(
            RetrievalRequest(command.task, project_index, self._budget)
        )
        if (
            retrieval.task_id != command.task.task_id
            or retrieval.index_id != project_index.index_id
        ):
            raise ContextPreparationError("Retriever returned inconsistent traceability")
        bundle = self._context_builder.build(retrieval, project_id=command.project_id)
        validation = ContextBundleValidator().validate(bundle, retrieval)
        if not validation.is_valid:
            raise ContextPreparationError("Context Bundle validation failed")
        if bundle.project_id != command.project_id:
            raise ContextPreparationError("Context Bundle belongs to another project")

        diagnostics = merge_diagnostics(
            inventory.diagnostics,
            project_index.diagnostics,
            retrieval.diagnostics,
            bundle.diagnostics,
            validation.diagnostics,
        )
        return ContextPreparationResult(
            inventory.inventory_id,
            inventory,
            project_index,
            retrieval,
            bundle,
            validation,
            diagnostics,
        )
