"""End-to-end, analysis-only application execution pipeline."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from contextforge.application.analysis_validation import (
    AnalysisResponseValidationError,
    validate_analysis_response,
)
from contextforge.application.context_pipeline import (
    ContextBundleBuilder,
    ContextPreparationPipeline,
    merge_diagnostics,
)
from contextforge.application.indexing import (
    InventoryStorage,
)
from contextforge.application.messages import ExecuteTask
from contextforge.context import (
    ContextBundle,
    ContextBundleSerializer,
)
from contextforge.diagnostics import DiagnosticCollection
from contextforge.domain import (
    InventoryId,
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
    RetrievalResult,
    RetrievalStatus,
)


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
        self._context_pipeline = ContextPreparationPipeline(
            inventory_storage=inventory_storage,
            index_storage=index_storage,
            indexer=indexer,
            retriever=retriever,
            context_builder=context_builder,
            budget=budget,
        )
        self._prompt_limits = prompt_limits or PromptLimits()
        self._clock = clock

    def execute(self, command: ExecuteTask) -> AnalysisExecutionResult:
        """Execute an analysis task without exposing any mutation capability."""
        if not isinstance(command, ExecuteTask):
            raise TypeError("command must be an ExecuteTask")
        if command.task.requested_output is not RequestedOutput.ANALYSIS:
            raise AnalysisPipelineError("Analysis pipeline requires analysis output")

        prepared = self._context_pipeline.prepare(command)
        inventory = prepared.inventory
        project_index = prepared.project_index
        retrieval = prepared.retrieval_result
        bundle = prepared.context_bundle

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
        diagnostics = prepared.diagnostics
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
        try:
            validate_analysis_response(
                analysis,
                known_references=frozenset(item.context_item_id for item in bundle.items),
                context_complete=retrieval.status
                in (RetrievalStatus.COMPLETE, RetrievalStatus.COMPLETE_WITH_WARNINGS),
            )
        except AnalysisResponseValidationError as error:
            raise AnalysisPipelineError(str(error)) from error
        all_diagnostics = merge_diagnostics(
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
