"""Patch proposal execution pipeline with no application capability."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol, cast

from contextforge.application.analysis import ProviderNotFoundError, ProviderRegistry
from contextforge.application.context_pipeline import (
    ContextBundleBuilder,
    ContextPreparationPipeline,
    ContextPreparationResult,
    merge_diagnostics,
)
from contextforge.application.indexing import InventoryStorage
from contextforge.application.messages import ExecuteTask
from contextforge.context import ContextBundleSerializer
from contextforge.diagnostics import DiagnosticCollection
from contextforge.domain import (
    ProjectFingerprint,
    RequestedOutput,
    new_inference_request_id,
    new_patch_proposal_id,
)
from contextforge.indexer import Indexer, IndexStorage
from contextforge.patch import (
    PatchConsistencyEvidence,
    PatchDiagnostic,
    PatchProposal,
    PatchProposalLifecycle,
    PatchProposalMaterialization,
    PatchProposalMaterializer,
    PatchSourceState,
    ProposalLifecycleState,
    ProviderResponseEnvelopeValidator,
    StructuredPatchParser,
    fingerprint_patch_proposal,
)
from contextforge.prompt import (
    DeliveryRequirements,
    InferenceRequest,
    PromptLimits,
    PromptMeasurer,
    PromptTemplateAssembler,
    patch_response_contract,
)
from contextforge.provider import (
    InferenceResponse,
    ProviderExecutionContext,
    ProviderFinishState,
)
from contextforge.retrieval import ContextBudget, ContextRetriever
from contextforge.scanner import ProjectInventory


class PatchSourceStateProvider(Protocol):
    """Supply trusted operation preconditions for one immutable inventory."""

    def load(self, inventory: ProjectInventory) -> PatchSourceState:
        """Return source state bound to the inventory snapshot."""
        ...


class PatchProposalStorage(Protocol):
    """Persist a proposal together with its explicit lifecycle."""

    def save(
        self,
        proposal: PatchProposal,
        lifecycle: PatchProposalLifecycle,
    ) -> None:
        """Persist proposal content and state atomically."""
        ...


class PatchProposalPipelineError(RuntimeError):
    """A patch proposal stage returned inconsistent or unusable output."""


class PatchProposalRejectedError(PatchProposalPipelineError):
    """The Patch Engine safely rejected all proposal materialization."""

    def __init__(self, diagnostics: tuple[PatchDiagnostic, ...]) -> None:
        self.diagnostics = diagnostics
        super().__init__("Patch Engine rejected the provider response")


@dataclass(frozen=True, slots=True)
class PatchProposalExecutionResult:
    """Traceable result ending at explicit approval wait state."""

    context: ContextPreparationResult
    inference_request: InferenceRequest
    inference_response: InferenceResponse
    proposal: PatchProposal
    lifecycle: PatchProposalLifecycle
    diagnostics: DiagnosticCollection


@dataclass(frozen=True, slots=True)
class StructuredPatchEngine:
    """Compose envelope, structured-change, and proposal safety validators."""

    materializer: PatchProposalMaterializer = field(default_factory=PatchProposalMaterializer)

    def build(
        self,
        *,
        response: InferenceResponse,
        request: InferenceRequest,
        source_state: PatchSourceState,
        expected_project_fingerprint: ProjectFingerprint,
        created_at: datetime,
    ) -> PatchProposalMaterialization:
        """Validate untrusted structured output into one immutable proposal."""
        contract = patch_response_contract()
        envelope = ProviderResponseEnvelopeValidator().validate(response, contract)
        changes = StructuredPatchParser().parse(envelope)
        payload = cast("dict[str, object]", json.loads(envelope.canonical_json))
        summary = payload["summary"]
        if not isinstance(summary, str):
            raise PatchProposalPipelineError("Validated patch summary is not text")
        return self.materializer.materialize(
            proposal_id=new_patch_proposal_id(),
            task_id=request.task_id,
            request_id=request.request_id,
            response_id=response.response_id,
            changes=changes,
            source_state=source_state,
            consistency=PatchConsistencyEvidence(
                envelope.affected_files,
                expected_project_fingerprint,
                request.project_fingerprint,
            ),
            created_at=created_at,
            summary=summary,
        )


class PatchProposalExecutionPipeline:
    """Run task context through proposal creation, never patch application."""

    def __init__(
        self,
        *,
        inventory_storage: InventoryStorage,
        index_storage: IndexStorage,
        indexer: Indexer,
        retriever: ContextRetriever,
        context_builder: ContextBundleBuilder,
        providers: ProviderRegistry,
        source_states: PatchSourceStateProvider,
        proposal_storage: PatchProposalStorage,
        budget: ContextBudget,
        prompt_limits: PromptLimits | None = None,
        engine: StructuredPatchEngine | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._context_pipeline = ContextPreparationPipeline(
            inventory_storage=inventory_storage,
            index_storage=index_storage,
            indexer=indexer,
            retriever=retriever,
            context_builder=context_builder,
            budget=budget,
        )
        self._providers = providers
        self._source_states = source_states
        self._proposal_storage = proposal_storage
        self._prompt_limits = prompt_limits or PromptLimits()
        self._engine = engine or StructuredPatchEngine()
        self._clock = clock

    def execute(self, command: ExecuteTask) -> PatchProposalExecutionResult:
        """Produce and persist an awaiting-approval proposal without applying it."""
        if not isinstance(command, ExecuteTask):
            raise TypeError("command must be an ExecuteTask")
        if command.task.requested_output is not RequestedOutput.PATCH_PROPOSAL:
            raise PatchProposalPipelineError("Patch pipeline requires patch proposal output")

        prepared = self._context_pipeline.prepare(command)
        bundle = prepared.context_bundle
        contract = patch_response_contract()
        assembly = PromptTemplateAssembler().assemble(
            command.task,
            bundle,
            ContextBundleSerializer().serialize(bundle),
            contract,
        )
        measurements = PromptMeasurer().measure(assembly, bundle, self._prompt_limits)
        request = InferenceRequest(
            new_inference_request_id(),
            command.task.task_id,
            bundle.bundle_id,
            command.project_id,
            prepared.inventory.project_fingerprint,
            assembly.template_version,
            assembly.messages,
            contract,
            DeliveryRequirements(
                ("structured_output", "structured_patch"),
                contains_sensitive_context=measurements.sensitive_item_count > 0,
                structured_output_required=True,
            ),
            measurements,
            prepared.diagnostics,
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
            raise PatchProposalPipelineError("Provider returned inconsistent traceability")
        if response.finish_state not in (
            ProviderFinishState.COMPLETED,
            ProviderFinishState.COMPLETED_WITH_WARNINGS,
        ):
            raise PatchProposalPipelineError("Provider did not complete the patch proposal")

        materialization = self._engine.build(
            response=response,
            request=request,
            source_state=self._source_states.load(prepared.inventory),
            expected_project_fingerprint=prepared.inventory.project_fingerprint,
            created_at=self._clock(),
        )
        if materialization.proposal is None:
            raise PatchProposalRejectedError(materialization.diagnostics)
        proposal = materialization.proposal
        proposal_fingerprint = fingerprint_patch_proposal(proposal)
        lifecycle = PatchProposalLifecycle.proposed(
            proposal.proposal_id,
            proposal_fingerprint,
            proposal.created_at,
        )
        lifecycle = lifecycle.transition(
            ProposalLifecycleState.VALIDATED,
            at=self._clock(),
            proposal_fingerprint=proposal_fingerprint,
        ).transition(
            ProposalLifecycleState.AWAITING_APPROVAL,
            at=self._clock(),
            proposal_fingerprint=proposal_fingerprint,
        )
        self._proposal_storage.save(proposal, lifecycle)
        diagnostics = merge_diagnostics(
            prepared.diagnostics,
            response.diagnostics.collection,
        )
        return PatchProposalExecutionResult(
            prepared,
            request,
            response,
            proposal,
            lifecycle,
            diagnostics,
        )
