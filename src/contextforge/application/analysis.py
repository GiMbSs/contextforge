"""End-to-end, analysis-only application execution pipeline."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from contextforge.application.indexing import (
    InventoryNotFoundError,
    InventoryStorage,
    ProjectIndexBuild,
)
from contextforge.application.messages import BuildProjectIndex, ExecuteTask
from contextforge.context import (
    ContextBundle,
    ContextBundleSerializer,
    ContextBundleValidator,
)
from contextforge.diagnostics import DiagnosticCollection
from contextforge.domain import (
    InventoryId,
    ProjectId,
    RequestedOutput,
    new_inference_request_id,
)
from contextforge.indexer import Indexer, IndexStorage, ProjectIndex
from contextforge.prompt import (
    AnalysisResponse,
    DeliveryRequirements,
    InferenceRequest,
    PromptLimits,
    PromptMeasurer,
    PromptTemplateAssembler,
    analysis_response_contract,
    decode_analysis_response,
)
from contextforge.provider import (
    InferenceResponse,
    ProviderExecutionContext,
    ProviderFinishState,
    ProviderPort,
)
from contextforge.retrieval import (
    ContextBudget,
    ContextRetriever,
    RetrievalRequest,
    RetrievalResult,
)


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


class ProviderRegistry(Protocol):
    """Resolve configured providers without coupling orchestration to adapters."""

    def get(self, provider_id: str) -> ProviderPort | None:
        """Return the exact configured provider, when available."""
        ...


class ProviderNotFoundError(LookupError):
    """The provider selected by the command is not configured."""


class AnalysisPipelineError(RuntimeError):
    """A pipeline stage returned inconsistent or unusable output."""


@dataclass(frozen=True, slots=True)
class AnalysisExecutionResult:
    """Traceable result retaining every immutable analysis pipeline artifact."""

    inventory_id: InventoryId
    project_index: ProjectIndex
    retrieval_result: RetrievalResult
    context_bundle: ContextBundle
    inference_request: InferenceRequest
    inference_response: InferenceResponse
    analysis: AnalysisResponse
    diagnostics: DiagnosticCollection


def _merge_diagnostics(*collections: DiagnosticCollection) -> DiagnosticCollection:
    unique = {item.to_json(): item for collection in collections for item in collection}
    return DiagnosticCollection(tuple(unique.values()))


class AnalysisExecutionPipeline:
    """Run the complete read-only analysis flow through injected capability ports."""

    def __init__(
        self,
        *,
        inventory_storage: InventoryStorage,
        index_storage: IndexStorage,
        indexer: Indexer,
        retriever: ContextRetriever,
        context_builder: ContextBundleBuilder,
        providers: ProviderRegistry,
        budget: ContextBudget,
        prompt_limits: PromptLimits | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._inventory_storage = inventory_storage
        self._index_storage = index_storage
        self._indexer = indexer
        self._retriever = retriever
        self._context_builder = context_builder
        self._providers = providers
        self._budget = budget
        self._prompt_limits = prompt_limits or PromptLimits()
        self._clock = clock

    def execute(self, command: ExecuteTask) -> AnalysisExecutionResult:
        """Execute an analysis task without exposing any mutation capability."""
        if not isinstance(command, ExecuteTask):
            raise TypeError("command must be an ExecuteTask")
        if command.task.requested_output is not RequestedOutput.ANALYSIS:
            raise AnalysisPipelineError("Analysis pipeline requires analysis output")

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
            raise AnalysisPipelineError("Retriever returned inconsistent traceability")

        bundle = self._context_builder.build(retrieval, project_id=command.project_id)
        validation = ContextBundleValidator().validate(bundle, retrieval)
        if not validation.is_valid:
            raise AnalysisPipelineError("Context Bundle validation failed")
        if bundle.project_id != command.project_id:
            raise AnalysisPipelineError("Context Bundle belongs to another project")

        contract = analysis_response_contract()
        serialized = ContextBundleSerializer().serialize(bundle)
        assembly = PromptTemplateAssembler().assemble(
            command.task,
            bundle,
            serialized,
            contract,
        )
        measurements = PromptMeasurer().measure(
            assembly,
            bundle,
            self._prompt_limits,
        )
        diagnostics = _merge_diagnostics(
            inventory.diagnostics,
            project_index.diagnostics,
            retrieval.diagnostics,
            bundle.diagnostics,
            validation.diagnostics,
        )
        request = InferenceRequest(
            new_inference_request_id(),
            command.task.task_id,
            bundle.bundle_id,
            command.project_id,
            inventory.project_fingerprint,
            assembly.template_version,
            assembly.messages,
            contract,
            DeliveryRequirements(
                ("structured_output",),
                contains_sensitive_context=measurements.sensitive_item_count > 0,
                structured_output_required=True,
            ),
            measurements,
            diagnostics,
            self._clock(),
            (("provider_id", command.provider_id),),
        )

        provider = self._providers.get(command.provider_id)
        if provider is None:
            raise ProviderNotFoundError(command.provider_id)
        response = provider.invoke(
            request,
            ProviderExecutionContext(str(request.request_id)),
        )
        if response.request_id != request.request_id or response.task_id != command.task.task_id:
            raise AnalysisPipelineError("Provider returned inconsistent traceability")
        if response.finish_state not in (
            ProviderFinishState.COMPLETED,
            ProviderFinishState.COMPLETED_WITH_WARNINGS,
        ):
            raise AnalysisPipelineError("Provider did not complete the analysis")

        analysis = decode_analysis_response(response.content)
        known_references = {item.context_item_id for item in bundle.items}
        cited_references = {
            reference for finding in analysis.findings for reference in finding.evidence_references
        }
        if not cited_references <= known_references:
            raise AnalysisPipelineError("Analysis cites context outside the Context Bundle")
        all_diagnostics = _merge_diagnostics(
            diagnostics,
            response.diagnostics.collection,
        )
        return AnalysisExecutionResult(
            inventory.inventory_id,
            project_index,
            retrieval,
            bundle,
            request,
            response,
            analysis,
            all_diagnostics,
        )
