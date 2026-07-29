"""Thin CLI composition for foundational project commands."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import IntEnum
from pathlib import Path
from typing import Protocol, cast
from uuid import NAMESPACE_URL, uuid5

import typer

from contextforge.adapters.configuration import (
    inspect_configuration,
    runtime_diagnostics,
    set_configuration,
)
from contextforge.adapters.configuration.toml import TomlConfigurationSourceAdapter
from contextforge.adapters.filesystem import (
    FilesystemExecutionControlStorage,
    FilesystemIndexStorage,
    FilesystemInventoryStorage,
    LocalProjectInitialization,
    LocalProjectLock,
    LocalProjectScanner,
    LocalStagedPatchApplication,
    ProjectLockInfo,
    ProjectLockOwnershipError,
    ProjectLockUnavailableError,
)
from contextforge.adapters.patch_proposals import LocalPatchProposalStorage
from contextforge.adapters.providers import _DEFAULT_OLLAMA_MODEL, ConfiguredProviderRegistry
from contextforge.application import (
    AnalysisExecutionPipeline,
    ApplicationPreflightEvidence,
    ApplyPatchProposal,
    ApprovePatchProposal,
    BuildProjectIndex,
    ContextPreparationPipeline,
    ContextPreparationResult,
    ExecuteTask,
    ExecutionController,
    InitializeProject,
    PatchApplicationOutcomeUnknownError,
    PatchApplicationPreview,
    PatchApplicationReconciliationOutcome,
    PatchApplicationResult,
    PatchApplicationStatus,
    PatchApprovalApplicationPipeline,
    PatchApprovalBindingError,
    PatchApprovalNotFoundError,
    PatchProposalExecutionPipeline,
    PatchProposalNotFoundError,
    PatchWorkflowStateError,
    ProjectIndexBuild,
    ProjectInitialization,
    ProjectScan,
    ReconcilePatchApplication,
    RejectPatchProposal,
    ScanProject,
    StaleProjectStateError,
    StructuredPatchEngine,
    assess_execution_recovery,
)
from contextforge.configuration import (
    ProjectConfig,
    ProviderConfig,
    ScannerConfig,
    resolve_configuration,
)
from contextforge.context import (
    ContextBundle,
    ContextBundleSerializer,
)
from contextforge.context.simple_builder import SimpleContextBuilder
from contextforge.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticCollection,
    DiagnosticSeverity,
)
from contextforge.domain import (
    ArtifactPath,
    Execution,
    ExecutionId,
    ExecutionStage,
    ExecutionWorkflow,
    InferenceRequestId,
    InferenceResponseId,
    PatchProposalId,
    ProjectFingerprint,
    ProjectId,
    ProposalFingerprint,
    RequestedOutput,
    TaskKind,
    TaskSpecification,
    fingerprint_content,
    new_execution_id,
    new_inference_request_id,
    new_task_id,
)
from contextforge.indexer import (
    DeterministicProjectIndexer,
    ProjectIndex,
)
from contextforge.patch import (
    ApprovalMethod,
    ApprovalRecord,
    PatchProposal,
    PatchProposalLifecycle,
    PatchSourceArtifact,
    PatchSourceState,
    ProposalLifecycleState,
    fingerprint_patch_proposal,
)
from contextforge.project import ProjectRoot, resolve_project_root
from contextforge.prompt import (
    AnalysisResponse,
    DeliveryRequirements,
    InferenceRequest,
    PromptLimits,
    PromptMeasurer,
    PromptTemplateAssembler,
    analysis_response_contract,
    decode_analysis_response,
    patch_response_contract,
)
from contextforge.provider import (
    MOCK_MODEL_ID,
    MOCK_PROVIDER_ID,
    InferenceResponse,
    MockProviderScenario,
    ProviderCapabilityProfile,
    ProviderDiagnostics,
    ProviderExecutionContext,
    ProviderExecutionMeasurements,
    ProviderFinishReason,
    ProviderFinishState,
    ProviderPort,
    ProviderResponseFormat,
    ProviderResponseMetadata,
    ProviderUsage,
)
from contextforge.retrieval import (
    ContextBudget,
)
from contextforge.retrieval.simple_retriever import SimpleContextRetriever
from contextforge.scanner import DiscoveryStatus, ProjectArtifact, ProjectInventory


class CliExitCode(IntEnum):
    """Stable process exit codes assigned by the CLI specification."""

    SUCCESS = 0
    GENERAL_FAILURE = 1
    INVALID_USAGE = 2
    CONFIGURATION_FAILURE = 3
    PROJECT_RESOLUTION_FAILURE = 4
    SCAN_FAILURE = 5
    INDEX_FAILURE = 6
    RETRIEVAL_FAILURE = 7
    PROMPT_FAILURE = 8
    PROVIDER_FAILURE = 9
    PATCH_VALIDATION_FAILURE = 10
    APPROVAL_REQUIRED = 11
    PATCH_REJECTED = 12
    PATCH_APPLICATION_FAILURE = 13
    PROJECT_STATE_CONFLICT = 14
    SECURITY_POLICY_REJECTION = 15
    OPERATION_CANCELLED = 16
    PARTIAL_RESULT = 17
    UNSUPPORTED_CAPABILITY = 18
    EVALUATION_FAILURE = 19
    EVALUATION_REGRESSION = 20


@dataclass(frozen=True, slots=True)
class CliCommandResult:
    """Presentation-neutral result returned by CLI command composition."""

    data: dict[str, object]
    exit_code: CliExitCode = CliExitCode.SUCCESS
    diagnostics: tuple[dict[str, object], ...] = ()


class ProjectCommandGateway(Protocol):
    """Operations consumed by the CLI without embedding domain decisions."""

    def initialize(self, root: ProjectRoot) -> CliCommandResult: ...

    def status(self, root: ProjectRoot) -> CliCommandResult: ...

    def scan(self, root: ProjectRoot) -> CliCommandResult: ...

    def index(self, root: ProjectRoot) -> CliCommandResult: ...

    def analyze(
        self,
        root: ProjectRoot,
        task_text: str,
        provider_id: str,
        explicit_config: Path | None = None,
    ) -> CliCommandResult: ...

    def propose(
        self,
        root: ProjectRoot,
        task_text: str,
        provider_id: str,
        explicit_config: Path | None = None,
    ) -> CliCommandResult: ...

    def inspect_context(
        self,
        root: ProjectRoot,
        operation: str,
        *,
        target: str | None = None,
        destination: Path | None = None,
    ) -> CliCommandResult: ...

    def build_context_packet(
        self,
        root: ProjectRoot,
        task_text: str,
        *,
        max_items: int = 20,
        max_bytes: int = 64_000,
    ) -> CliCommandResult: ...

    def inspect_prompt(
        self,
        root: ProjectRoot,
        operation: str,
        *,
        destination: Path | None = None,
    ) -> CliCommandResult: ...

    def inspect_provider(
        self,
        operation: str,
        provider_id: str | None = None,
        root: ProjectRoot | None = None,
        explicit_config: Path | None = None,
        config: ProviderConfig | None = None,
    ) -> CliCommandResult: ...

    def inspect_patch(
        self,
        root: ProjectRoot,
        operation: str,
        *,
        proposal_id: str | None = None,
        destination: Path | None = None,
    ) -> CliCommandResult: ...

    def authorize_patch(
        self,
        root: ProjectRoot,
        operation: str,
        proposal_id: str,
        *,
        approval_method: str = "interactive",
        reason: str | None = None,
    ) -> CliCommandResult: ...

    def apply_patch_proposal(
        self,
        root: ProjectRoot,
        proposal_id: str,
    ) -> CliCommandResult: ...

    def reconcile_patch_application(
        self,
        root: ProjectRoot,
        proposal_id: str,
        *,
        outcome: str,
        recovery_reference: str,
    ) -> CliCommandResult: ...

    def configure(
        self,
        root: ProjectRoot,
        operation: str,
        *,
        key: str | None = None,
        value: str | None = None,
        explicit: Path | None = None,
        user_scope: bool = False,
    ) -> CliCommandResult: ...

    def diagnostics(
        self,
        root: ProjectRoot,
        *,
        explicit: Path | None = None,
    ) -> CliCommandResult: ...

    def inspect_execution(
        self,
        root: ProjectRoot,
        operation: str,
        execution_id: str | None = None,
    ) -> CliCommandResult: ...

    def invoke_execution(
        self,
        root: ProjectRoot,
        execution_id: str | None,
        *,
        confirmed: bool,
        explicit_config: Path | None = None,
    ) -> CliCommandResult: ...

    def validate_execution(
        self,
        root: ProjectRoot,
        execution_id: str | None,
    ) -> CliCommandResult: ...

    def manage_lock(
        self,
        root: ProjectRoot,
        operation: str,
        *,
        minimum_age_seconds: int = 3600,
    ) -> CliCommandResult: ...


@dataclass(slots=True)
class _LocalSource:
    root: Path

    def read(self, artifact: ProjectArtifact) -> bytes:
        candidate = self.root.joinpath(*artifact.path.parts).resolve(strict=True)
        candidate.relative_to(self.root)
        return candidate.read_bytes()


@dataclass(slots=True)
class LocalProjectCommandGateway:
    """Default local composition of existing application and adapter services."""

    scanner: LocalProjectScanner = field(default_factory=LocalProjectScanner)
    scanner_configuration: ScannerConfig = field(
        default_factory=lambda: ScannerConfig(exclude_patterns=(".contextforge/",))
    )

    def initialize(self, root: ProjectRoot) -> CliCommandResult:
        result = ProjectInitialization(LocalProjectInitialization()).execute(
            InitializeProject(root, create_config=True)
        )
        return CliCommandResult(
            {
                "command": "init",
                "configuration_created": result.configuration_created,
                "configuration_file": (
                    str(result.configuration_file)
                    if result.configuration_file is not None
                    else None
                ),
                "metadata_created": result.metadata_created,
                "metadata_directory": str(result.metadata_directory),
                "project_root": str(root.path),
                "status": "initialized" if result.succeeded else "failed",
            },
            CliExitCode.SUCCESS if result.succeeded else CliExitCode.GENERAL_FAILURE,
            _diagnostics(result.diagnostics),
        )

    def status(self, root: ProjectRoot) -> CliCommandResult:
        metadata = root.path / ".contextforge"
        configuration = metadata / "config.toml"
        initialized = metadata.is_dir()
        storage = FilesystemExecutionControlStorage(root)
        latest_execution = storage.load_latest(_project_id(root))
        latest_invocation = (
            storage.load_invocation(latest_execution.execution_id)
            if latest_execution is not None
            else None
        )
        return CliCommandResult(
            {
                "command": "status",
                "configuration_present": configuration.is_file(),
                "execution": (
                    _execution_payload(
                        latest_execution,
                        task_available=storage.load_task(latest_execution.execution_id) is not None,
                        invocation_status=_invocation_status(latest_invocation),
                    )
                    if latest_execution is not None
                    else None
                ),
                "initialized": initialized,
                "project_id": str(_project_id(root)),
                "project_root": str(root.path),
                "status": "ready" if initialized else "uninitialized",
            }
        )

    def scan(self, root: ProjectRoot) -> CliCommandResult:
        inventory = self._scan(root)
        statistics = inventory.statistics
        failed = inventory.status is DiscoveryStatus.FAILED
        partial = inventory.status is DiscoveryStatus.INCOMPLETE
        return CliCommandResult(
            {
                "artifact_count": len(inventory.artifacts),
                "command": "scan",
                "directories": statistics.directories_visited,
                "duration_seconds": statistics.duration_seconds,
                "ignored": statistics.artifacts_excluded,
                "inventory_id": str(inventory.inventory_id),
                "project_fingerprint": str(inventory.project_fingerprint),
                "project_root": str(root.path),
                "reused": statistics.artifacts_reused,
                "status": inventory.status.value,
            },
            (
                CliExitCode.SCAN_FAILURE
                if failed
                else CliExitCode.PARTIAL_RESULT
                if partial
                else CliExitCode.SUCCESS
            ),
            _diagnostics(inventory.diagnostics),
        )

    def index(self, root: ProjectRoot) -> CliCommandResult:
        inventory = self._scan(root)
        project_index = ProjectIndexBuild(
            DeterministicProjectIndexer(_LocalSource(root.path)),
            FilesystemInventoryStorage(root),
            FilesystemIndexStorage(root),
        ).execute(BuildProjectIndex(_project_id(root), inventory.inventory_id))
        failed = project_index.status.value == "failed"
        return CliCommandResult(
            {
                "artifact_count": len(project_index.indexed_artifacts),
                "command": "index",
                "index_id": str(project_index.index_id),
                "project_fingerprint": str(project_index.project_fingerprint),
                "project_root": str(root.path),
                "relationships": len(project_index.relationships),
                "reused": project_index.measurements.artifacts_reused,
                "search_units": len(project_index.search_units),
                "status": project_index.status.value,
                "symbols": len(project_index.symbols),
            },
            CliExitCode.INDEX_FAILURE if failed else CliExitCode.SUCCESS,
            _diagnostics(project_index.diagnostics),
        )

    def analyze(
        self,
        root: ProjectRoot,
        task_text: str,
        provider_id: str,
        explicit_config: Path | None = None,
    ) -> CliCommandResult:
        task = TaskSpecification(
            new_task_id(),
            task_text,
            TaskKind.EXPLAIN,
            RequestedOutput.ANALYSIS,
            metadata=(("provider_id", provider_id),),
        )
        storage = FilesystemExecutionControlStorage(root)
        controller = ExecutionController(
            Execution(
                new_execution_id(),
                _project_id(root),
                task.task_id,
                workflow=ExecutionWorkflow.ANALYSIS,
            ),
            storage,
        )
        storage.save_task(controller.execution.execution_id, task)
        controller.complete_stage(ExecutionStage.SCAN)
        inventory = self._scan(root)
        controller.complete_stage(ExecutionStage.INDEX, inventory.diagnostics)
        project_index = self._index_inventory(root, inventory)
        controller.complete_stage(ExecutionStage.RETRIEVE, project_index.diagnostics)
        pipeline = AnalysisExecutionPipeline(
            inventory_storage=FilesystemInventoryStorage(root),
            index_storage=FilesystemIndexStorage(root),
            indexer=DeterministicProjectIndexer(_LocalSource(root.path)),
            retriever=SimpleContextRetriever(),
            context_builder=SimpleContextBuilder(root.path),
            providers=_provider_registry(root, explicit_config),
            budget=ContextBudget(max_items=20, max_bytes=64_000),
        )
        try:
            result = pipeline.execute(ExecuteTask(_project_id(root), task, provider_id))
        except Exception as error:
            controller.fail(_execution_failure_diagnostics(error))
            raise
        for stage in (
            ExecutionStage.BUILD_CONTEXT,
            ExecutionStage.BUILD_PROMPT,
            ExecutionStage.INVOKE_PROVIDER,
            ExecutionStage.VALIDATE_RESPONSE,
            ExecutionStage.COMPLETE,
        ):
            controller.complete_stage(stage)
        self._persist_context(root, result.context_bundle)
        self._persist_prompt(root, result.inference_request)
        return CliCommandResult(
            {
                "command": "run",
                "findings": len(result.analysis.findings),
                "execution_id": str(controller.execution.execution_id),
                "mode": "analysis_only",
                "project_root": str(root.path),
                "request_id": str(result.inference_request.request_id),
                "status": "completed",
                "summary": result.analysis.summary,
                "task_id": str(task.task_id),
            },
            diagnostics=_diagnostics(result.diagnostics),
        )

    def propose(
        self,
        root: ProjectRoot,
        task_text: str,
        provider_id: str,
        explicit_config: Path | None = None,
    ) -> CliCommandResult:
        """Generate and persist a validated proposal without applying it."""
        task = TaskSpecification(
            new_task_id(),
            task_text,
            TaskKind.MODIFY,
            RequestedOutput.PATCH_PROPOSAL,
            metadata=(("provider_id", provider_id),),
        )
        storage = FilesystemExecutionControlStorage(root)
        controller = ExecutionController(
            Execution(
                new_execution_id(),
                _project_id(root),
                task.task_id,
                workflow=ExecutionWorkflow.PATCH,
            ),
            storage,
        )
        storage.save_task(controller.execution.execution_id, task)
        controller.complete_stage(ExecutionStage.SCAN)
        inventory = self._scan(root)
        controller.complete_stage(ExecutionStage.INDEX, inventory.diagnostics)
        project_index = self._index_inventory(root, inventory)
        controller.complete_stage(ExecutionStage.RETRIEVE, project_index.diagnostics)
        source = _LocalSource(root.path)
        try:
            result = PatchProposalExecutionPipeline(
                inventory_storage=FilesystemInventoryStorage(root),
                index_storage=FilesystemIndexStorage(root),
                indexer=DeterministicProjectIndexer(source),
                retriever=SimpleContextRetriever(),
                context_builder=SimpleContextBuilder(root.path),
                providers=_provider_registry(
                    root,
                    explicit_config,
                    mock_scenario=MockProviderScenario.SUCCESSFUL_STRUCTURED_PATCH,
                ),
                source_states=_LocalPatchSourceStates(root.path),
                proposal_storage=LocalPatchProposalStorage(root),
                budget=ContextBudget(max_items=20, max_bytes=64_000),
            ).execute(ExecuteTask(_project_id(root), task, provider_id))
        except Exception as error:
            controller.fail(_execution_failure_diagnostics(error))
            raise
        for stage in (
            ExecutionStage.BUILD_CONTEXT,
            ExecutionStage.BUILD_PROMPT,
            ExecutionStage.INVOKE_PROVIDER,
            ExecutionStage.VALIDATE_RESPONSE,
            ExecutionStage.BUILD_PROPOSAL,
            ExecutionStage.AWAIT_APPROVAL,
        ):
            controller.complete_stage(stage)
        self._persist_context(root, result.context.context_bundle)
        self._persist_prompt(root, result.inference_request)
        return CliCommandResult(
            {
                "change_count": len(result.proposal.changes),
                "command": "run",
                "execution_id": str(controller.execution.execution_id),
                "lifecycle_state": result.lifecycle.state.value,
                "mode": "patch_proposal",
                "project_root": str(root.path),
                "proposal_id": str(result.proposal.proposal_id),
                "status": "awaiting_approval",
                "summary": result.proposal.summary,
            },
            diagnostics=_diagnostics(result.diagnostics),
        )

    def inspect_context(
        self,
        root: ProjectRoot,
        operation: str,
        *,
        target: str | None = None,
        destination: Path | None = None,
    ) -> CliCommandResult:
        stored = _load_context(root)
        if stored is None:
            return _context_failure(
                "CLI_CONTEXT_NOT_FOUND",
                "No persisted Context Bundle is available.",
            )
        if operation == "show":
            data = {
                key: stored[key]
                for key in (
                    "bundle_id",
                    "created_at",
                    "coverage",
                    "project_fingerprint",
                    "retrieval_id",
                    "statistics",
                )
            }
            data["command"] = "context show"
            data["status"] = "available"
            return CliCommandResult(data)
        items = stored["items"]
        if not isinstance(items, list):
            return _context_failure("CLI_CONTEXT_INVALID", "Persisted context items are invalid.")
        if operation == "list":
            return CliCommandResult(
                {
                    "bundle_id": stored["bundle_id"],
                    "command": "context list",
                    "items": items,
                    "status": "available",
                }
            )
        if operation == "explain":
            selected = next(
                (
                    item
                    for item in items
                    if isinstance(item, dict)
                    and target in (item.get("context_item_id"), item.get("path"))
                ),
                None,
            )
            if selected is None:
                return _context_failure(
                    "CLI_CONTEXT_ITEM_NOT_FOUND",
                    "The requested context item or path is unavailable.",
                )
            return CliCommandResult(
                {
                    "bundle_id": stored["bundle_id"],
                    "command": "context explain",
                    "item": selected,
                    "status": "available",
                }
            )
        if operation == "export":
            if destination is not None:
                destination.write_text(
                    json.dumps(stored, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            return CliCommandResult(
                {
                    "bundle": stored,
                    "command": "context export",
                    "destination": str(destination) if destination is not None else None,
                    "status": "exported",
                }
            )
        return _context_failure("CLI_CONTEXT_OPERATION_INVALID", "Unknown context operation.")

    def build_context_packet(
        self,
        root: ProjectRoot,
        task_text: str,
        *,
        max_items: int = 20,
        max_bytes: int = 64_000,
    ) -> CliCommandResult:
        """Build a provider-neutral, read-only context packet for an external agent."""
        task = TaskSpecification(
            new_task_id(),
            task_text,
            TaskKind.ANALYZE,
            RequestedOutput.ANALYSIS,
        )
        self._scan(root, reuse_unchanged_inventory=True)
        prepared = ContextPreparationPipeline(
            inventory_storage=FilesystemInventoryStorage(root),
            index_storage=FilesystemIndexStorage(root),
            indexer=DeterministicProjectIndexer(_LocalSource(root.path)),
            retriever=SimpleContextRetriever(),
            context_builder=SimpleContextBuilder(root.path),
            budget=ContextBudget(max_items=max_items, max_bytes=max_bytes),
        ).prepare(ExecuteTask(_project_id(root), task, "external-agent"))
        return CliCommandResult(
            {
                "command": "context build",
                "packet": _context_packet(prepared, task_text, max_items, max_bytes),
                "status": "available",
            },
            diagnostics=_diagnostics(prepared.diagnostics),
        )

    def inspect_prompt(
        self,
        root: ProjectRoot,
        operation: str,
        *,
        destination: Path | None = None,
    ) -> CliCommandResult:
        stored = _load_prompt(root)
        if stored is None:
            return _prompt_failure(
                "CLI_PROMPT_NOT_FOUND",
                "No persisted prompt preview is available.",
            )
        if operation == "preview":
            return CliCommandResult(
                {
                    "command": "prompt preview",
                    "context_bundle_id": stored["context_bundle_id"],
                    "delivery_requirements": stored["delivery_requirements"],
                    "diagnostics": stored["diagnostics"],
                    "measurements": stored["measurements"],
                    "prompt_template_version": stored["prompt_template_version"],
                    "redacted": stored["redacted"],
                    "request_id": stored["request_id"],
                    "response_contract": stored["response_contract"],
                    "sections": stored["sections"],
                    "status": "available",
                }
            )
        if operation == "measure":
            return CliCommandResult(
                {
                    "command": "prompt measure",
                    "measurements": stored["measurements"],
                    "request_id": stored["request_id"],
                    "status": "available",
                }
            )
        if operation == "export":
            if destination is not None:
                destination.write_text(
                    json.dumps(stored, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            return CliCommandResult(
                {
                    "command": "prompt export",
                    "destination": str(destination) if destination is not None else None,
                    "prompt": stored,
                    "status": "exported",
                }
            )
        return _prompt_failure("CLI_PROMPT_OPERATION_INVALID", "Unknown prompt operation.")

    def inspect_provider(
        self,
        operation: str,
        provider_id: str | None = None,
        root: ProjectRoot | None = None,
        explicit_config: Path | None = None,
        config: ProviderConfig | None = None,
    ) -> CliCommandResult:
        provider_config = config or (
            _load_project_config(root, explicit_config).provider
            if root is not None
            else ProviderConfig()
        )
        registry = ConfiguredProviderRegistry(provider_config)
        if operation == "list":
            providers = tuple(
                _provider_summary(registry.get(configured_id), provider_config)
                for configured_id in registry.provider_ids
            )
            return CliCommandResult(
                {
                    "command": "provider list",
                    "providers": providers,
                    "status": "available",
                }
            )
        selected_id = provider_id or provider_config.provider_id
        provider = registry.get(selected_id)
        if provider is None:
            return _provider_failure(
                "CLI_PROVIDER_NOT_FOUND",
                f"Provider '{selected_id}' is not configured.",
            )
        if operation == "show":
            capabilities = cast(ProviderCapabilityProfile, provider.get_capabilities())
            return CliCommandResult(
                {
                    "capabilities": _provider_capabilities(capabilities),
                    "command": "provider show",
                    "configuration": _provider_configuration(provider, provider_config),
                    "delivery_policy_status": (
                        "local_only"
                        if capabilities.execution_mode.value == "local"
                        else "authorization_required"
                    ),
                    "status": "available",
                }
            )
        if operation == "health":
            health = provider.health_check()
            return CliCommandResult(
                {
                    "checked_at": health.checked_at.isoformat(),
                    "command": "provider health",
                    "health": health.status.value,
                    "message": health.message,
                    "project_content_transmitted": False,
                    "provider_id": selected_id,
                    "status": "available",
                }
            )
        if operation == "models":
            models = provider.list_models()
            return CliCommandResult(
                {
                    "command": "provider models",
                    "download_triggered": False,
                    "models": [
                        {
                            "display_name": model.display_name,
                            "metadata": dict(model.metadata),
                            "model_id": model.model_id,
                        }
                        for model in models
                    ],
                    "provider_id": selected_id,
                    "status": "available",
                }
            )
        return _provider_failure(
            "CLI_PROVIDER_OPERATION_INVALID",
            "Unknown provider operation.",
        )

    def inspect_patch(
        self,
        root: ProjectRoot,
        operation: str,
        *,
        proposal_id: str | None = None,
        destination: Path | None = None,
    ) -> CliCommandResult:
        storage = LocalPatchProposalStorage(root)
        if operation == "list":
            records = storage.list_records()
            return CliCommandResult(
                {
                    "command": "patch list",
                    "proposals": [_patch_summary(record) for record in records],
                    "status": "available",
                }
            )
        record = storage.load_record(proposal_id)
        if record is None:
            return _patch_failure(
                "CLI_PATCH_PROPOSAL_NOT_FOUND",
                "The requested patch proposal is unavailable.",
            )
        if operation == "show":
            return CliCommandResult(
                {
                    "command": "patch show",
                    "proposal": record,
                    "status": "available",
                }
            )
        if operation == "application":
            try:
                selected_id = PatchProposalId(str(record["proposal_id"]))
            except (KeyError, ValueError):
                return _patch_failure(
                    "CLI_PATCH_APPLICATION_RECORD_INVALID",
                    "The selected proposal has an invalid application record binding.",
                )
            application = storage.load_application_attempt(selected_id)
            if application is None:
                return _patch_failure(
                    "CLI_PATCH_APPLICATION_NOT_FOUND",
                    "The selected proposal has no application record.",
                )
            return CliCommandResult(
                {
                    "application": application,
                    "command": "patch application",
                    "lifecycle_state": record.get("lifecycle_state"),
                    "proposal_id": str(selected_id),
                    "status": application.get("attempt_status"),
                }
            )
        if operation == "review":
            return CliCommandResult(
                {
                    "command": "patch review",
                    "review": _patch_review(record),
                    "status": "available",
                }
            )
        if operation == "export":
            if destination is not None:
                destination.write_text(
                    json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            return CliCommandResult(
                {
                    "command": "patch export",
                    "destination": str(destination) if destination is not None else None,
                    "proposal": record,
                    "status": "exported",
                }
            )
        return _patch_failure(
            "CLI_PATCH_OPERATION_INVALID",
            "Unknown patch inspection operation.",
        )

    def authorize_patch(
        self,
        root: ProjectRoot,
        operation: str,
        proposal_id: str,
        *,
        approval_method: str = "interactive",
        reason: str | None = None,
    ) -> CliCommandResult:
        try:
            selected_id = PatchProposalId(proposal_id)
        except (TypeError, ValueError):
            return _patch_failure(
                "CLI_PATCH_PROPOSAL_NOT_FOUND",
                "The requested patch proposal is unavailable.",
            )
        storage = LocalPatchProposalStorage(root)
        proposal = storage.load_proposal(selected_id)
        if proposal is None:
            return _patch_failure(
                "CLI_PATCH_PROPOSAL_NOT_FOUND",
                "The requested patch proposal is unavailable.",
            )
        execution_controller = _patch_execution_controller(root, proposal)
        lifecycle = storage.load_lifecycle(selected_id)
        if (
            operation == "approve"
            and lifecycle is not None
            and lifecycle.state is ProposalLifecycleState.APPROVED
        ):
            approval = storage.load_active_approval(selected_id)
            if approval is None:
                return _patch_workflow_failure(
                    PatchApprovalNotFoundError("Approved proposal has no active Approval Record")
                )
            _reconcile_execution_controller(root, execution_controller)
            return _persisted_approval_result(
                proposal_id,
                approval,
                execution_controller,
            )
        if (
            operation == "reject"
            and lifecycle is not None
            and lifecycle.state is ProposalLifecycleState.REJECTED
        ):
            record = storage.load_record(proposal_id)
            rejection = record.get("rejection") if record is not None else None
            reason_value = rejection.get("reason") if isinstance(rejection, Mapping) else None
            _reconcile_execution_controller(root, execution_controller)
            return CliCommandResult(
                {
                    "command": "patch reject",
                    "execution_id": (
                        str(execution_controller.execution.execution_id)
                        if execution_controller is not None
                        else None
                    ),
                    "lifecycle_state": lifecycle.state.value,
                    "proposal_id": proposal_id,
                    "reason": reason_value,
                    "status": "rejected",
                }
            )
        current_fingerprint = self._scan(root).project_fingerprint
        pipeline = PatchApprovalApplicationPipeline(
            storage=storage,
            project_state=_FixedProjectState(current_fingerprint),
            application=_UnavailablePatchApplication(),
        )
        try:
            if operation == "approve":
                warning_codes = tuple(
                    str(diagnostic.code)
                    for diagnostic in proposal.validation.diagnostics
                    if diagnostic.severity.value in ("warning", "error", "critical")
                )
                approved = pipeline.approve(
                    ApprovePatchProposal(
                        selected_id,
                        ApprovalMethod(approval_method),
                        acknowledged_warnings=warning_codes,
                    )
                )
                if (
                    execution_controller is not None
                    and execution_controller.execution.stage is ExecutionStage.AWAIT_APPROVAL
                ):
                    execution_controller.complete_stage(ExecutionStage.APPLY)
                return CliCommandResult(
                    {
                        "approval_id": str(approved.approval.approval_id),
                        "command": "patch approve",
                        "execution_id": (
                            str(execution_controller.execution.execution_id)
                            if execution_controller is not None
                            else None
                        ),
                        "lifecycle_state": approved.lifecycle.state.value,
                        "method": approved.approval.method.value,
                        "project_fingerprint": str(approved.approval.project_fingerprint),
                        "proposal_fingerprint": str(approved.approval.proposal_fingerprint),
                        "proposal_id": proposal_id,
                        "status": "approved",
                    }
                )
            if operation == "reject":
                rejected = pipeline.reject(
                    RejectPatchProposal(
                        selected_id,
                        reason or "Rejected interactively.",
                    )
                )
                if execution_controller is not None:
                    execution_controller.cancel()
                return CliCommandResult(
                    {
                        "command": "patch reject",
                        "execution_id": (
                            str(execution_controller.execution.execution_id)
                            if execution_controller is not None
                            else None
                        ),
                        "lifecycle_state": rejected.lifecycle.state.value,
                        "proposal_id": proposal_id,
                        "reason": rejected.reason,
                        "status": "rejected",
                    }
                )
        except (
            PatchProposalNotFoundError,
            PatchWorkflowStateError,
            StaleProjectStateError,
        ) as error:
            return _patch_workflow_failure(error)
        return _patch_failure(
            "CLI_PATCH_OPERATION_INVALID",
            "Unknown patch authorization operation.",
        )

    def apply_patch_proposal(
        self,
        root: ProjectRoot,
        proposal_id: str,
    ) -> CliCommandResult:
        try:
            selected_id = PatchProposalId(proposal_id)
        except (TypeError, ValueError):
            return _patch_failure(
                "CLI_PATCH_PROPOSAL_NOT_FOUND",
                "The requested patch proposal is unavailable.",
            )
        storage = LocalPatchProposalStorage(root)
        proposal = storage.load_proposal(selected_id)
        if proposal is None:
            return _patch_failure(
                "CLI_PATCH_PROPOSAL_NOT_FOUND",
                "The requested patch proposal is unavailable.",
            )
        execution_controller = _patch_execution_controller(root, proposal)
        lifecycle = storage.load_lifecycle(selected_id)
        if lifecycle is not None and lifecycle.state is ProposalLifecycleState.APPLIED:
            persisted = storage.load_application_result(selected_id)
            if persisted is None:
                return _patch_application_failure(
                    PatchWorkflowStateError("Applied proposal has no persisted application result")
                )
            _reconcile_execution_controller(root, execution_controller)
            return CliCommandResult(
                {
                    "applied_change_ids": persisted.get("applied_change_ids", []),
                    "command": "patch apply",
                    "execution_id": (
                        str(execution_controller.execution.execution_id)
                        if execution_controller is not None
                        else None
                    ),
                    "lifecycle_state": lifecycle.state.value,
                    "proposal_id": proposal_id,
                    "recovery_reference": persisted.get("recovery_reference"),
                    "rollback_verified": persisted.get("rollback_verified"),
                    "status": persisted.get("status", "applied"),
                    "unapplied_change_ids": persisted.get(
                        "unapplied_change_ids",
                        [],
                    ),
                }
            )
        approval = storage.load_active_approval(selected_id)
        if approval is None:
            failed = _patch_failure(
                "CLI_PATCH_APPROVAL_REQUIRED",
                "An active Approval Record is required before application.",
            )
            return CliCommandResult(
                failed.data,
                CliExitCode.APPROVAL_REQUIRED,
                failed.diagnostics,
            )
        application = LocalStagedPatchApplication(
            root,
            lambda: _application_evidence(self, root, proposal),
        )
        pipeline = PatchApprovalApplicationPipeline(
            storage=storage,
            project_state=_FixedProjectState(self._scan(root).project_fingerprint),
            application=application,
        )
        try:
            with LocalProjectLock(root, "patch_apply"):
                result = pipeline.apply(ApplyPatchProposal(selected_id, approval.approval_id))
        except (
            PatchApprovalBindingError,
            PatchApprovalNotFoundError,
            PatchApplicationOutcomeUnknownError,
            PatchProposalNotFoundError,
            PatchWorkflowStateError,
            ProjectLockUnavailableError,
            StaleProjectStateError,
        ) as error:
            return _patch_application_failure(error)
        applied = result.application
        data: dict[str, object] = {
            "applied_change_ids": list(applied.applied_change_ids),
            "command": "patch apply",
            "lifecycle_state": result.lifecycle.state.value,
            "proposal_id": proposal_id,
            "recovery_reference": applied.recovery_reference,
            "rollback_verified": applied.rollback_verified,
            "status": applied.status.value,
            "unapplied_change_ids": list(applied.unapplied_change_ids),
        }
        diagnostics: tuple[dict[str, object], ...] = tuple(
            {
                "capability": "patch_application",
                "change_id": diagnostic.change_id,
                "code": str(diagnostic.code),
                "message": diagnostic.message,
                "severity": diagnostic.severity.value,
            }
            for diagnostic in applied.diagnostics
        )
        exit_code = (
            CliExitCode.SUCCESS
            if applied.status is PatchApplicationStatus.APPLIED
            else CliExitCode.PARTIAL_RESULT
            if applied.status is PatchApplicationStatus.PARTIALLY_APPLIED
            else CliExitCode.PATCH_APPLICATION_FAILURE
        )
        if execution_controller is not None:
            if (
                applied.status is PatchApplicationStatus.APPLIED
                and execution_controller.execution.stage is ExecutionStage.APPLY
            ):
                execution_controller.complete_stage(ExecutionStage.COMPLETE)
            elif not execution_controller.execution.status.is_terminal:
                execution_controller.fail(
                    DiagnosticCollection(
                        (
                            Diagnostic(
                                DiagnosticCode("EXECUTION_PATCH_APPLICATION_FAILED"),
                                DiagnosticSeverity.ERROR,
                                "The patch proposal was not fully applied.",
                                "execution",
                            ),
                        )
                    )
                )
            data["execution_id"] = str(execution_controller.execution.execution_id)
        return CliCommandResult(data, exit_code, diagnostics)

    def reconcile_patch_application(
        self,
        root: ProjectRoot,
        proposal_id: str,
        *,
        outcome: str,
        recovery_reference: str,
    ) -> CliCommandResult:
        """Persist an explicit operator resolution for an unknown mutation."""
        try:
            selected_id = PatchProposalId(proposal_id)
            selected_outcome = PatchApplicationReconciliationOutcome(outcome)
        except (TypeError, ValueError):
            return _patch_failure(
                "CLI_PATCH_RECONCILIATION_INVALID",
                "The proposal identifier or reconciliation outcome is invalid.",
            )
        if not recovery_reference.strip():
            return _patch_failure(
                "CLI_PATCH_RECONCILIATION_INVALID",
                "A non-empty recovery reference is required.",
            )
        storage = LocalPatchProposalStorage(root)
        proposal = storage.load_proposal(selected_id)
        approval = storage.load_active_approval(selected_id)
        if proposal is None:
            return _patch_failure(
                "CLI_PATCH_PROPOSAL_NOT_FOUND",
                "The requested patch proposal is unavailable.",
            )
        if approval is None:
            return _patch_failure(
                "CLI_PATCH_APPROVAL_REQUIRED",
                "An active Approval Record is required for reconciliation.",
            )
        pipeline = PatchApprovalApplicationPipeline(
            storage=storage,
            project_state=_FixedProjectState(proposal.project_fingerprint),
            application=_UnavailablePatchApplication(),
        )
        try:
            with LocalProjectLock(root, "patch_reconcile"):
                reconciled = pipeline.reconcile(
                    ReconcilePatchApplication(
                        selected_id,
                        approval.approval_id,
                        selected_outcome,
                        recovery_reference,
                    )
                )
        except (
            PatchApprovalBindingError,
            PatchProposalNotFoundError,
            PatchWorkflowStateError,
            ProjectLockUnavailableError,
        ) as error:
            return _patch_application_failure(error)
        execution_controller = _patch_execution_controller(root, proposal)
        if (
            selected_outcome is PatchApplicationReconciliationOutcome.APPLIED
            and execution_controller is not None
            and execution_controller.execution.stage is ExecutionStage.APPLY
        ):
            execution_controller.complete_stage(ExecutionStage.COMPLETE)
        return CliCommandResult(
            {
                "applied_change_ids": list(reconciled.application.applied_change_ids),
                "command": "patch reconcile",
                "execution_id": (
                    str(execution_controller.execution.execution_id)
                    if execution_controller is not None
                    else None
                ),
                "lifecycle_state": reconciled.lifecycle.state.value,
                "proposal_id": proposal_id,
                "recovery_reference": recovery_reference,
                "resolution": selected_outcome.value,
                "status": "reconciled",
                "unapplied_change_ids": list(reconciled.application.unapplied_change_ids),
            }
        )

    def configure(
        self,
        root: ProjectRoot,
        operation: str,
        *,
        key: str | None = None,
        value: str | None = None,
        explicit: Path | None = None,
        user_scope: bool = False,
    ) -> CliCommandResult:
        """Inspect or safely update local configuration."""
        if operation == "set":
            if key is None or value is None:
                return _configuration_failure(
                    "CONFIG_ARGUMENT_REQUIRED",
                    "Configuration key and value are required.",
                )
            destination = (
                Path.home() / ".config" / "contextforge" / "config.toml"
                if user_scope
                else root.path / ".contextforge" / "config.toml"
            )
            try:
                return CliCommandResult(set_configuration(destination, key, value))
            except (TypeError, ValueError, OSError) as error:
                code = str(error)
                if not code.startswith("CONFIG_"):
                    code = "CONFIG_WRITE_FAILED"
                return _configuration_failure(code, "Configuration was not updated.")
        data, diagnostics = inspect_configuration(
            root,
            operation,
            key=key,
            explicit=explicit,
        )
        return CliCommandResult(
            data,
            CliExitCode.SUCCESS if not diagnostics else CliExitCode.CONFIGURATION_FAILURE,
            diagnostics,
        )

    def diagnostics(
        self,
        root: ProjectRoot,
        *,
        explicit: Path | None = None,
    ) -> CliCommandResult:
        """Report runtime readiness without disclosing project content."""
        data = runtime_diagnostics(root, explicit)
        return CliCommandResult(
            data,
            (
                CliExitCode.SUCCESS
                if data["status"] == "healthy"
                else CliExitCode.CONFIGURATION_FAILURE
            ),
        )

    def inspect_execution(
        self,
        root: ProjectRoot,
        operation: str,
        execution_id: str | None = None,
    ) -> CliCommandResult:
        storage = FilesystemExecutionControlStorage(root)
        if operation == "list":
            return CliCommandResult(
                {
                    "command": "execution list",
                    "executions": [
                        _execution_payload(
                            item,
                            task_available=storage.load_task(item.execution_id) is not None,
                            invocation_status=_invocation_status(
                                storage.load_invocation(item.execution_id)
                            ),
                        )
                        for item in storage.list_executions(_project_id(root))
                    ],
                    "status": "available",
                }
            )
        if execution_id is None:
            execution = storage.load_latest(_project_id(root))
        else:
            try:
                selected_id = ExecutionId.from_string(execution_id)
            except (TypeError, ValueError):
                return _execution_not_found()
            execution = storage.load_execution(selected_id)
        if execution is None:
            return _execution_not_found()
        if execution.project_id != _project_id(root):
            return _execution_not_found()
        if operation == "cancel":
            try:
                ExecutionController.resume(execution, storage).cancel()
            except Exception as error:
                return CliCommandResult(
                    {"status": "failed"},
                    CliExitCode.PROJECT_STATE_CONFLICT,
                    _diagnostics(_execution_failure_diagnostics(error)),
                )
            execution = storage.load_execution(execution.execution_id) or execution
        elif operation == "resume":
            return self._resume_execution(root, execution, storage)
        elif operation != "show":
            return CliCommandResult(
                {"status": "failed"},
                CliExitCode.INVALID_USAGE,
            )
        stages = storage.load_stage_diagnostics(execution.execution_id)
        invocation = storage.load_invocation(execution.execution_id)
        return CliCommandResult(
            {
                "command": f"execution {operation}",
                "execution": _execution_payload(
                    execution,
                    task_available=storage.load_task(execution.execution_id) is not None,
                    invocation_status=_invocation_status(invocation),
                ),
                "invocation": _invocation_payload(invocation),
                "stage_outcomes": [
                    {
                        "diagnostics": _diagnostics(item.diagnostics),
                        "outcome": item.outcome.value,
                        "stage": item.stage.value,
                    }
                    for item in stages
                ],
                "status": "cancelled" if operation == "cancel" else "available",
            }
        )

    def invoke_execution(
        self,
        root: ProjectRoot,
        execution_id: str | None,
        *,
        confirmed: bool,
        explicit_config: Path | None = None,
    ) -> CliCommandResult:
        storage = FilesystemExecutionControlStorage(root)
        if execution_id is None:
            execution = storage.load_latest(_project_id(root))
        else:
            try:
                selected_id = ExecutionId.from_string(execution_id)
            except (TypeError, ValueError):
                return _execution_not_found()
            execution = storage.load_execution(selected_id)
        if execution is None or execution.project_id != _project_id(root):
            return _execution_not_found()
        task = storage.load_task(execution.execution_id)
        if (
            execution.stage is not ExecutionStage.INVOKE_PROVIDER
            or task is None
            or execution.status.is_terminal
        ):
            return CliCommandResult(
                {"command": "execution invoke", "status": "invocation_rejected"},
                CliExitCode.PROJECT_STATE_CONFLICT,
            )
        if not confirmed:
            return CliCommandResult(
                {
                    "command": "execution invoke",
                    "execution_id": str(execution.execution_id),
                    "status": "confirmation_required",
                },
                CliExitCode.APPROVAL_REQUIRED,
            )
        provider_id = _task_provider_id(task)
        provider = _provider_registry(
            root,
            explicit_config,
            mock_scenario=(
                MockProviderScenario.SUCCESSFUL_STRUCTURED_PATCH
                if execution.workflow is ExecutionWorkflow.PATCH
                else MockProviderScenario.SUCCESSFUL_ANALYSIS
            ),
        ).get(provider_id)
        if provider is None:
            return CliCommandResult(
                {"command": "execution invoke", "status": "provider_unavailable"},
                CliExitCode.PROVIDER_FAILURE,
            )
        lock = LocalProjectLock(root, "provider_invoke")
        try:
            lock.acquire()
            try:
                prepared = ContextPreparationPipeline(
                    inventory_storage=FilesystemInventoryStorage(root),
                    index_storage=FilesystemIndexStorage(root),
                    indexer=DeterministicProjectIndexer(_LocalSource(root.path)),
                    retriever=SimpleContextRetriever(),
                    context_builder=SimpleContextBuilder(root.path),
                    budget=ContextBudget(max_items=20, max_bytes=64_000),
                ).prepare(ExecuteTask(execution.project_id, task, provider_id))
                request = _build_inference_request(execution, task, prepared)
                storage.begin_invocation(
                    execution,
                    request,
                    provider_id,
                    tuple(item.context_item_id for item in prepared.context_bundle.items),
                )
                response = provider.invoke(
                    request,
                    ProviderExecutionContext(str(request.request_id)),
                )
                storage.complete_invocation(execution, response)
                controller = ExecutionController.resume(execution, storage)
                controller.complete_stage(
                    ExecutionStage.VALIDATE_RESPONSE,
                    response.diagnostics.collection,
                )
            finally:
                lock.release()
        except Exception as error:
            invocation = storage.load_invocation(execution.execution_id)
            return CliCommandResult(
                {
                    "command": "execution invoke",
                    "invocation": _invocation_payload(invocation),
                    "status": (
                        "outcome_unknown" if invocation is not None else "invocation_failed"
                    ),
                },
                CliExitCode.PROVIDER_FAILURE,
                _diagnostics(_execution_failure_diagnostics(error)),
            )
        return CliCommandResult(
            {
                "command": "execution invoke",
                "execution": _execution_payload(
                    controller.execution,
                    task_available=True,
                ),
                "invocation": _invocation_payload(storage.load_invocation(execution.execution_id)),
                "status": "response_persisted",
            }
        )

    def validate_execution(
        self,
        root: ProjectRoot,
        execution_id: str | None,
    ) -> CliCommandResult:
        storage = FilesystemExecutionControlStorage(root)
        if execution_id is None:
            execution = storage.load_latest(_project_id(root))
        else:
            try:
                selected_id = ExecutionId.from_string(execution_id)
            except (TypeError, ValueError):
                return _execution_not_found()
            execution = storage.load_execution(selected_id)
        if execution is None or execution.project_id != _project_id(root):
            return _execution_not_found()
        if execution.stage is not ExecutionStage.VALIDATE_RESPONSE or execution.status.is_terminal:
            return CliCommandResult(
                {"command": "execution validate", "status": "validation_rejected"},
                CliExitCode.PROJECT_STATE_CONFLICT,
            )
        invocation = storage.load_invocation(execution.execution_id)
        if execution.workflow is ExecutionWorkflow.PATCH:
            return self._validate_patch_execution(
                root,
                execution,
                storage,
                invocation,
            )
        try:
            analysis = _validate_persisted_analysis(invocation)
            storage.save_result(
                execution,
                "analysis",
                _analysis_result_payload(analysis),
            )
            controller = ExecutionController.resume(execution, storage)
            controller.complete_stage(ExecutionStage.COMPLETE)
        except Exception as error:
            controller = ExecutionController.resume(execution, storage)
            controller.fail(_execution_failure_diagnostics(error))
            return CliCommandResult(
                {"command": "execution validate", "status": "validation_failed"},
                CliExitCode.PROMPT_FAILURE,
                _diagnostics(_execution_failure_diagnostics(error)),
            )
        return CliCommandResult(
            {
                "command": "execution validate",
                "execution": _execution_payload(
                    controller.execution,
                    task_available=True,
                    invocation_status="received",
                ),
                "findings": len(analysis.findings),
                "status": "completed",
                "summary": analysis.summary,
            }
        )

    def _validate_patch_execution(
        self,
        root: ProjectRoot,
        execution: Execution,
        storage: FilesystemExecutionControlStorage,
        invocation: dict[str, object] | None,
    ) -> CliCommandResult:
        task = storage.load_task(execution.execution_id)
        try:
            if task is None:
                raise ValueError("The persisted task is unavailable")
            response = _restore_persisted_response(execution, invocation)
            expected_fingerprint = _invocation_project_fingerprint(invocation)
            current_inventory = self._scan(root)
            if current_inventory.project_fingerprint != expected_fingerprint:
                raise StaleProjectStateError(
                    "Project fingerprint changed after provider invocation"
                )
            prepared = ContextPreparationPipeline(
                inventory_storage=FilesystemInventoryStorage(root),
                index_storage=FilesystemIndexStorage(root),
                indexer=DeterministicProjectIndexer(_LocalSource(root.path)),
                retriever=SimpleContextRetriever(),
                context_builder=SimpleContextBuilder(root.path),
                budget=ContextBudget(max_items=20, max_bytes=64_000),
            ).prepare(
                ExecuteTask(
                    execution.project_id,
                    task,
                    _task_provider_id(task),
                )
            )
            request = _build_inference_request(
                execution,
                task,
                prepared,
                request_id=response.request_id,
            )
            materialization = StructuredPatchEngine().build(
                response=response,
                request=request,
                source_state=_LocalPatchSourceStates(root.path).load(prepared.inventory),
                expected_project_fingerprint=expected_fingerprint,
                created_at=datetime.now(UTC),
            )
            if materialization.proposal is None:
                raise ValueError("Patch Engine rejected the persisted response")
            proposal = materialization.proposal
            proposal_fingerprint = fingerprint_patch_proposal(proposal)
            lifecycle = PatchProposalLifecycle.proposed(
                proposal.proposal_id,
                proposal_fingerprint,
                proposal.created_at,
            )
            lifecycle = lifecycle.transition(
                ProposalLifecycleState.VALIDATED,
                at=datetime.now(UTC),
                proposal_fingerprint=proposal_fingerprint,
            ).transition(
                ProposalLifecycleState.AWAITING_APPROVAL,
                at=datetime.now(UTC),
                proposal_fingerprint=proposal_fingerprint,
            )
            LocalPatchProposalStorage(root).save(proposal, lifecycle)
            storage.save_result(
                execution,
                "patch_proposal",
                {
                    "change_count": len(proposal.changes),
                    "proposal_id": str(proposal.proposal_id),
                    "summary": proposal.summary,
                },
            )
            controller = ExecutionController.resume(execution, storage)
            controller.complete_stage(ExecutionStage.BUILD_PROPOSAL)
            controller.complete_stage(ExecutionStage.AWAIT_APPROVAL)
        except Exception as error:
            controller = ExecutionController.resume(execution, storage)
            controller.fail(_execution_failure_diagnostics(error))
            return CliCommandResult(
                {"command": "execution validate", "status": "validation_failed"},
                CliExitCode.PATCH_VALIDATION_FAILURE,
                _diagnostics(_execution_failure_diagnostics(error)),
            )
        return CliCommandResult(
            {
                "change_count": len(proposal.changes),
                "command": "execution validate",
                "execution": _execution_payload(
                    controller.execution,
                    task_available=True,
                    invocation_status="received",
                ),
                "proposal_id": str(proposal.proposal_id),
                "status": "awaiting_approval",
                "summary": proposal.summary,
            }
        )

    def _resume_execution(
        self,
        root: ProjectRoot,
        execution: Execution,
        storage: FilesystemExecutionControlStorage,
    ) -> CliCommandResult:
        reconciliation = _reconcile_patch_execution(root, execution, storage)
        if reconciliation is not None:
            return reconciliation
        task = storage.load_task(execution.execution_id)
        assessment = assess_execution_recovery(
            execution,
            task_available=task is not None,
        )
        if assessment.disposition.value != "resumable" or task is None:
            return CliCommandResult(
                {
                    "command": "execution resume",
                    "execution": _execution_payload(
                        execution,
                        task_available=task is not None,
                    ),
                    "status": "recovery_rejected",
                },
                CliExitCode.PROJECT_STATE_CONFLICT,
            )
        controller = ExecutionController.resume(execution, storage)
        try:
            if controller.execution.stage is ExecutionStage.RESOLVE:
                controller.complete_stage(ExecutionStage.SCAN)
            if controller.execution.stage is ExecutionStage.SCAN:
                inventory = self._scan(root)
                controller.complete_stage(ExecutionStage.INDEX, inventory.diagnostics)
            else:
                inventory = self._scan(root)
            if controller.execution.stage is ExecutionStage.INDEX:
                project_index = self._index_inventory(root, inventory)
                controller.complete_stage(
                    ExecutionStage.RETRIEVE,
                    project_index.diagnostics,
                )

            prepared = ContextPreparationPipeline(
                inventory_storage=FilesystemInventoryStorage(root),
                index_storage=FilesystemIndexStorage(root),
                indexer=DeterministicProjectIndexer(_LocalSource(root.path)),
                retriever=SimpleContextRetriever(),
                context_builder=SimpleContextBuilder(root.path),
                budget=ContextBudget(max_items=20, max_bytes=64_000),
            ).prepare(
                ExecuteTask(
                    execution.project_id,
                    task,
                    _task_provider_id(task),
                )
            )
            if controller.execution.stage is ExecutionStage.RETRIEVE:
                controller.complete_stage(
                    ExecutionStage.BUILD_CONTEXT,
                    prepared.diagnostics,
                )
            self._persist_context(root, prepared.context_bundle)
            if controller.execution.stage is ExecutionStage.BUILD_CONTEXT:
                controller.complete_stage(ExecutionStage.BUILD_PROMPT)
            if controller.execution.stage is ExecutionStage.BUILD_PROMPT:
                request = _build_inference_request(execution, task, prepared)
                self._persist_prompt(root, request)
                controller.complete_stage(ExecutionStage.INVOKE_PROVIDER)
        except Exception as error:
            controller.fail(_execution_failure_diagnostics(error))
            return CliCommandResult(
                {"command": "execution resume", "status": "failed"},
                CliExitCode.PROJECT_STATE_CONFLICT,
                _diagnostics(_execution_failure_diagnostics(error)),
            )
        return CliCommandResult(
            {
                "command": "execution resume",
                "execution": _execution_payload(
                    controller.execution,
                    task_available=True,
                ),
                "status": "paused_before_provider",
            }
        )

    def manage_lock(
        self,
        root: ProjectRoot,
        operation: str,
        *,
        minimum_age_seconds: int = 3600,
    ) -> CliCommandResult:
        try:
            if operation == "show":
                lock = LocalProjectLock.inspect(root)
                return CliCommandResult(
                    {
                        "command": "lock show",
                        "lock": _lock_payload(lock),
                        "status": "locked" if lock is not None else "unlocked",
                    }
                )
            if operation == "recover":
                recovered = LocalProjectLock.recover_abandoned(
                    root,
                    minimum_age_seconds=minimum_age_seconds,
                )
                return CliCommandResult(
                    {
                        "command": "lock recover",
                        "recovered_lock": _lock_payload(recovered),
                        "status": "recovered",
                    }
                )
        except (ProjectLockUnavailableError, ProjectLockOwnershipError) as error:
            return CliCommandResult(
                {"status": "failed"},
                CliExitCode.PROJECT_STATE_CONFLICT,
                (
                    {
                        "capability": "project_lock",
                        "code": "CLI_PROJECT_LOCK_RECOVERY_REJECTED",
                        "message": str(error),
                        "severity": "error",
                    },
                ),
            )
        return CliCommandResult({"status": "failed"}, CliExitCode.INVALID_USAGE)

    @staticmethod
    def _persist_context(root: ProjectRoot, bundle: ContextBundle) -> None:
        execution_directory = root.path / ".contextforge" / "executions"
        execution_directory.mkdir(parents=True, exist_ok=True)
        destination = execution_directory / "latest-context.json"
        temporary = execution_directory / "latest-context.json.tmp"
        payload = _context_payload(bundle)
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(destination)

    @staticmethod
    def _persist_prompt(root: ProjectRoot, request: InferenceRequest) -> None:
        execution_directory = root.path / ".contextforge" / "executions"
        execution_directory.mkdir(parents=True, exist_ok=True)
        destination = execution_directory / "latest-prompt.json"
        temporary = execution_directory / "latest-prompt.json.tmp"
        temporary.write_text(
            json.dumps(
                _prompt_payload(request),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(destination)

    def _scan(
        self,
        root: ProjectRoot,
        *,
        reuse_unchanged_inventory: bool = False,
    ) -> ProjectInventory:
        return ProjectScan(
            self.scanner,
            FilesystemInventoryStorage(root),
            self.scanner_configuration,
            reuse_unchanged_inventory=reuse_unchanged_inventory,
        ).execute(ScanProject(_project_id(root), root))

    def _prepare_project_state(self, root: ProjectRoot) -> ProjectIndex:
        inventory = self._scan(root)
        return self._index_inventory(root, inventory)

    @staticmethod
    def _index_inventory(
        root: ProjectRoot,
        inventory: ProjectInventory,
    ) -> ProjectIndex:
        return ProjectIndexBuild(
            DeterministicProjectIndexer(_LocalSource(root.path)),
            FilesystemInventoryStorage(root),
            FilesystemIndexStorage(root),
        ).execute(BuildProjectIndex(_project_id(root), inventory.inventory_id))


def _project_id(root: ProjectRoot) -> ProjectId:
    identity = uuid5(NAMESPACE_URL, root.path.as_uri())
    return ProjectId(f"project_{identity.hex}")


def _load_project_config(
    root: ProjectRoot,
    explicit: Path | None = None,
) -> ProjectConfig:
    """Load the effective project configuration without exposing secrets."""
    project_path = root.path / ".contextforge" / "config.toml"
    selected = explicit or project_path
    source = TomlConfigurationSourceAdapter().load(selected)
    values = source.values if source.succeeded else {}
    typed_values = cast("Mapping[object, object]", values)
    return resolve_configuration(
        explicit_file=(typed_values if explicit is not None and selected.exists() else None),
        project=typed_values if explicit is None and selected.exists() else None,
    ).config


def _provider_registry(
    root: ProjectRoot,
    explicit: Path | None = None,
    *,
    mock_scenario: MockProviderScenario = MockProviderScenario.SUCCESSFUL_ANALYSIS,
) -> ConfiguredProviderRegistry:
    """Build the configured provider registry for a project."""
    return ConfiguredProviderRegistry(
        _load_project_config(root, explicit).provider,
        mock_scenario,
    )


@dataclass(frozen=True, slots=True)
class _LocalPatchSourceStates:
    """Build trusted patch preconditions from the immutable scan snapshot."""

    root: Path

    def __post_init__(self) -> None:
        if not isinstance(self.root, Path):
            raise TypeError("root must be a Path")

    def load(self, inventory: ProjectInventory) -> PatchSourceState:
        return PatchSourceState(
            tuple(
                self._artifact_state(artifact)
                for artifact in inventory.artifacts
                if artifact.availability.value == "included"
            )
        )

    def _artifact_state(self, artifact: ProjectArtifact) -> PatchSourceArtifact:
        target = self.root.joinpath(*artifact.path.parts)
        try:
            content = target.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return PatchSourceArtifact(artifact.path)
        return PatchSourceArtifact(artifact.path, fingerprint_content(content))


def _provider_configuration(
    provider: ProviderPort,
    config: ProviderConfig,
) -> dict[str, object]:
    """Return a redacted provider configuration view."""
    return {
        "credentials_exposed": False,
        "default_model": _effective_model_id(provider, config),
        "endpoint": config.endpoint,
        "execution_mode": config.execution_mode,
        "provider_id": config.provider_id,
        "timeout_seconds": config.timeout_seconds,
    }


@dataclass(frozen=True, slots=True)
class _FixedProjectState:
    current: ProjectFingerprint

    def fingerprint(self, proposal: PatchProposal) -> ProjectFingerprint:
        del proposal
        return self.current


class _UnavailablePatchApplication:
    def preview_application(
        self,
        proposal: PatchProposal,
        proposal_fingerprint: ProposalFingerprint,
    ) -> PatchApplicationPreview:
        del proposal_fingerprint
        return PatchApplicationPreview(proposal.proposal_id, ())

    def apply_proposal(
        self,
        proposal: PatchProposal,
        proposal_fingerprint: ProposalFingerprint,
        approval: ApprovalRecord,
    ) -> PatchApplicationResult:
        del proposal, proposal_fingerprint, approval
        raise RuntimeError("patch application is unavailable in this increment")


def _application_evidence(
    gateway: LocalProjectCommandGateway,
    root: ProjectRoot,
    proposal: PatchProposal,
) -> ApplicationPreflightEvidence:
    paths = {
        path
        for change in proposal.changes
        for path in (change.path, change.destination_path)
        if path is not None
    }
    artifacts: list[PatchSourceArtifact] = []
    writable: list[ArtifactPath] = []
    for path in sorted(paths):
        target = root.path.joinpath(*path.parts)
        if target.is_file():
            try:
                content_fingerprint = fingerprint_content(target.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                content_fingerprint = None
            artifacts.append(PatchSourceArtifact(path, content_fingerprint))
        ancestor = target if target.exists() else target.parent
        while not ancestor.exists() and ancestor != root.path:
            ancestor = ancestor.parent
        if os.access(ancestor, os.W_OK):
            writable.append(path)
    return ApplicationPreflightEvidence(
        gateway._scan(root).project_fingerprint,
        PatchSourceState(tuple(artifacts)),
        tuple(writable),
        not (root.path / ".contextforge" / "mutation.lock").exists(),
    )


def _diagnostics(collection: DiagnosticCollection) -> tuple[dict[str, object], ...]:
    return tuple(item.to_dict() for item in collection)


def _execution_failure_diagnostics(error: Exception) -> DiagnosticCollection:
    return DiagnosticCollection(
        (
            Diagnostic(
                DiagnosticCode("EXECUTION_STAGE_FAILED"),
                DiagnosticSeverity.ERROR,
                "The execution could not complete its current stage.",
                "execution",
                technical_details=str(error),
            ),
        )
    )


def _execution_not_found() -> CliCommandResult:
    return CliCommandResult(
        {"status": "failed"},
        CliExitCode.GENERAL_FAILURE,
        (
            {
                "capability": "execution",
                "code": "CLI_EXECUTION_NOT_FOUND",
                "message": "The requested execution is unavailable.",
                "severity": "error",
            },
        ),
    )


def _execution_payload(
    execution: Execution,
    *,
    task_available: bool,
    invocation_status: str | None = None,
) -> dict[str, object]:
    recovery = assess_execution_recovery(
        execution,
        task_available=task_available,
        invocation_status=invocation_status,
    )
    return {
        "completed_stages": [stage.value for stage in execution.completed_stages],
        "execution_id": str(execution.execution_id),
        "project_id": str(execution.project_id),
        "recovery": {
            "disposition": recovery.disposition.value,
            "reason": recovery.reason,
            "resume_from": (
                recovery.resume_from.value if recovery.resume_from is not None else None
            ),
        },
        "stage": execution.stage.value,
        "status": execution.status.value,
        "task_id": str(execution.task_id),
        "workflow": execution.workflow.value,
    }


def _task_provider_id(task: TaskSpecification) -> str:
    provider_id = dict(task.metadata).get("provider_id")
    return provider_id if isinstance(provider_id, str) and provider_id else MOCK_PROVIDER_ID


def _invocation_payload(record: dict[str, object] | None) -> dict[str, object] | None:
    if record is None:
        return None
    response = record.get("response")
    response_summary = None
    if isinstance(response, dict):
        metadata = response.get("metadata")
        response_summary = {
            key: (
                metadata.get("provider_id")
                if key == "provider_id" and isinstance(metadata, dict)
                else response.get(key)
            )
            for key in (
                "created_at",
                "finish_reason",
                "finish_state",
                "provider_id",
                "response_format",
                "response_id",
            )
        }
    return {
        "provider_id": record.get("provider_id"),
        "request_id": record.get("request_id"),
        "response": response_summary,
        "status": record.get("status"),
    }


def _invocation_status(record: dict[str, object] | None) -> str | None:
    if record is None:
        return None
    status = record.get("status")
    return status if isinstance(status, str) else "invalid"


def _validate_persisted_analysis(
    invocation: dict[str, object] | None,
) -> AnalysisResponse:
    if invocation is None or invocation.get("status") != "received":
        raise ValueError("A received provider response is required")
    response = invocation.get("response")
    references = invocation.get("context_references")
    if not isinstance(response, dict) or not isinstance(references, list):
        raise ValueError("The provider invocation record is incomplete")
    if response.get("finish_state") not in {"completed", "completed_with_warnings"}:
        raise ValueError("The provider response did not complete successfully")
    content = response.get("content")
    if not isinstance(content, str):
        raise ValueError("The persisted provider response has no text content")
    analysis = decode_analysis_response(content)
    known_references = {item for item in references if isinstance(item, str)}
    cited_references = {
        reference for finding in analysis.findings for reference in finding.evidence_references
    }
    if not cited_references <= known_references:
        raise ValueError("Analysis cites context outside the invoked Context Bundle")
    return analysis


def _analysis_result_payload(analysis: AnalysisResponse) -> dict[str, object]:
    return {
        "assumptions": list(analysis.assumptions),
        "diagnostics": list(analysis.diagnostics),
        "findings": [
            {
                "confidence": finding.confidence,
                "evidence_references": list(finding.evidence_references),
                "finding_id": finding.finding_id,
                "statement": finding.statement,
            }
            for finding in analysis.findings
        ],
        "limitations": list(analysis.limitations),
        "recommended_next_action": analysis.recommended_next_action,
        "status": analysis.status.value,
        "summary": analysis.summary,
        "uncertainties": list(analysis.uncertainties),
    }


def _invocation_project_fingerprint(
    invocation: dict[str, object] | None,
) -> ProjectFingerprint:
    if invocation is None or invocation.get("status") != "received":
        raise ValueError("A received provider response is required")
    value = invocation.get("project_fingerprint")
    if not isinstance(value, str):
        raise ValueError("Invocation project fingerprint is unavailable")
    return ProjectFingerprint(value)


def _restore_persisted_response(
    execution: Execution,
    invocation: dict[str, object] | None,
) -> InferenceResponse:
    if invocation is None or invocation.get("status") != "received":
        raise ValueError("A received provider response is required")
    response = invocation.get("response")
    if not isinstance(response, dict):
        raise ValueError("The persisted provider response is unavailable")
    metadata = response.get("metadata")
    measurements = response.get("measurements")
    usage = response.get("usage")
    if not isinstance(metadata, dict) or not isinstance(measurements, dict):
        raise ValueError("Provider response metadata is incomplete")
    restored_usage = None
    if usage is not None:
        if not isinstance(usage, dict):
            raise ValueError("Provider usage is invalid")
        restored_usage = ProviderUsage(
            input_tokens=_optional_record_int(usage, "input_tokens"),
            output_tokens=_optional_record_int(usage, "output_tokens"),
            total_tokens=_optional_record_int(usage, "total_tokens"),
            input_bytes=_optional_record_int(usage, "input_bytes"),
            output_bytes=_optional_record_int(usage, "output_bytes"),
            values_are_estimates=_record_bool(usage, "values_are_estimates"),
        )
    return InferenceResponse(
        InferenceResponseId.from_string(str(response["response_id"])),
        InferenceRequestId.from_string(str(invocation["request_id"])),
        execution.task_id,
        str(response["content"]),
        ProviderResponseFormat(str(response["response_format"])),
        ProviderResponseMetadata(
            provider_id=str(metadata["provider_id"]),
            adapter_id=str(metadata["adapter_id"]),
            adapter_version=str(metadata["adapter_version"]),
            model_id=str(metadata["model_id"]),
            capability_profile_id=str(metadata["capability_profile_id"]),
            invoked_at=datetime.fromisoformat(str(metadata["invoked_at"])),
            completed_at=datetime.fromisoformat(str(metadata["completed_at"])),
            provider_request_id=(
                str(metadata["provider_request_id"])
                if metadata.get("provider_request_id") is not None
                else None
            ),
            retry_attempt=_record_int(metadata, "retry_attempt"),
        ),
        restored_usage,
        ProviderExecutionMeasurements(
            total_duration_ms=_record_int(measurements, "total_duration_ms"),
            connection_duration_ms=_optional_record_int(
                measurements,
                "connection_duration_ms",
            ),
            provider_duration_ms=_optional_record_int(
                measurements,
                "provider_duration_ms",
            ),
            retry_count=_record_int(measurements, "retry_count"),
        ),
        ProviderFinishState(str(response["finish_state"])),
        ProviderDiagnostics(),
        datetime.fromisoformat(str(response["created_at"])),
        ProviderFinishReason(str(response["finish_reason"])),
    )


def _record_int(record: dict[str, object], key: str) -> int:
    value = record.get(key)
    if type(value) is not int:
        raise ValueError(f"{key} must be an integer")
    return value


def _optional_record_int(record: dict[str, object], key: str) -> int | None:
    value = record.get(key)
    if value is None:
        return None
    if type(value) is not int:
        raise ValueError(f"{key} must be an integer or null")
    return value


def _record_bool(record: dict[str, object], key: str) -> bool:
    value = record.get(key)
    if type(value) is not bool:
        raise ValueError(f"{key} must be a boolean")
    return value


def _build_inference_request(
    execution: Execution,
    task: TaskSpecification,
    prepared: ContextPreparationResult,
    *,
    request_id: InferenceRequestId | None = None,
) -> InferenceRequest:
    bundle = prepared.context_bundle
    inventory = prepared.inventory
    contract = (
        analysis_response_contract()
        if execution.workflow is ExecutionWorkflow.ANALYSIS
        else patch_response_contract()
    )
    assembly = PromptTemplateAssembler().assemble(
        task,
        bundle,
        ContextBundleSerializer().serialize(bundle),
        contract,
    )
    measurements = PromptMeasurer().measure(assembly, bundle, PromptLimits())
    required_capabilities = (
        ("structured_output",)
        if execution.workflow is ExecutionWorkflow.ANALYSIS
        else ("structured_output", "structured_patch")
    )
    return InferenceRequest(
        request_id or new_inference_request_id(),
        task.task_id,
        bundle.bundle_id,
        execution.project_id,
        inventory.project_fingerprint,
        assembly.template_version,
        assembly.messages,
        contract,
        DeliveryRequirements(
            required_capabilities,
            contains_sensitive_context=measurements.sensitive_item_count > 0,
            structured_output_required=True,
        ),
        measurements,
        prepared.diagnostics,
        datetime.now(UTC),
        (("provider_id", _task_provider_id(task)),),
    )


def _lock_payload(lock: ProjectLockInfo | None) -> dict[str, object] | None:
    if lock is None:
        return None
    return {
        "acquired_at": lock.acquired_at.isoformat(),
        "operation": lock.operation,
        "owner_pid": lock.owner_pid,
    }


def _patch_execution_controller(
    root: ProjectRoot,
    proposal: PatchProposal,
) -> ExecutionController | None:
    storage = FilesystemExecutionControlStorage(root)
    execution = storage.find_by_patch_proposal(proposal.proposal_id)
    if execution is None:
        execution = storage.find_by_task(proposal.task_id)
    if execution is None or execution.status.is_terminal:
        return None
    return ExecutionController.resume(execution, storage)


def _reconcile_execution_controller(
    root: ProjectRoot,
    controller: ExecutionController | None,
) -> None:
    if controller is None:
        return
    storage = FilesystemExecutionControlStorage(root)
    execution = storage.load_execution(controller.execution.execution_id)
    if execution is not None:
        _reconcile_patch_execution(root, execution, storage)


def _persisted_approval_result(
    proposal_id: str,
    approval: ApprovalRecord,
    execution_controller: ExecutionController | None,
) -> CliCommandResult:
    return CliCommandResult(
        {
            "approval_id": str(approval.approval_id),
            "command": "patch approve",
            "execution_id": (
                str(execution_controller.execution.execution_id)
                if execution_controller is not None
                else None
            ),
            "lifecycle_state": ProposalLifecycleState.APPROVED.value,
            "method": approval.method.value,
            "project_fingerprint": str(approval.project_fingerprint),
            "proposal_fingerprint": str(approval.proposal_fingerprint),
            "proposal_id": proposal_id,
            "status": "approved",
        }
    )


def _reconcile_patch_execution(
    root: ProjectRoot,
    execution: Execution,
    storage: FilesystemExecutionControlStorage,
) -> CliCommandResult | None:
    if (
        execution.workflow is not ExecutionWorkflow.PATCH
        or execution.status.is_terminal
        or execution.stage not in {ExecutionStage.AWAIT_APPROVAL, ExecutionStage.APPLY}
    ):
        return None
    result = storage.load_result(execution.execution_id)
    if result is None or result.get("result_type") != "patch_proposal":
        return None
    payload = result.get("result")
    if not isinstance(payload, Mapping):
        return None
    raw_proposal_id = payload.get("proposal_id")
    if not isinstance(raw_proposal_id, str):
        return None
    try:
        proposal_id = PatchProposalId(raw_proposal_id)
    except ValueError:
        return None
    proposal_storage = LocalPatchProposalStorage(root)
    lifecycle = proposal_storage.load_lifecycle(proposal_id)
    if lifecycle is None:
        return None

    controller = ExecutionController.resume(execution, storage)
    try:
        if lifecycle.state is ProposalLifecycleState.APPROVED:
            if proposal_storage.application_attempt_started(proposal_id):
                return _patch_reconciliation_result(
                    controller.execution,
                    "application_outcome_unknown",
                    proposal_id,
                    exit_code=CliExitCode.PROJECT_STATE_CONFLICT,
                )
            application = proposal_storage.load_application_attempt(proposal_id)
            if (
                application is not None
                and application.get("attempt_status") == "reconciled"
                and application.get("resolution") == "applied"
            ):
                lifecycle = lifecycle.transition(
                    ProposalLifecycleState.APPLIED,
                    at=datetime.now(UTC),
                    proposal_fingerprint=lifecycle.proposal_fingerprint,
                )
                proposal_storage.save_lifecycle(lifecycle)
                if controller.execution.stage is ExecutionStage.AWAIT_APPROVAL:
                    controller.complete_stage(ExecutionStage.APPLY)
                controller.complete_stage(ExecutionStage.COMPLETE)
                return _patch_reconciliation_result(
                    controller.execution,
                    "completed_after_reconciled_application",
                    proposal_id,
                )
            if controller.execution.stage is ExecutionStage.AWAIT_APPROVAL:
                controller.complete_stage(ExecutionStage.APPLY)
            return _patch_reconciliation_result(
                controller.execution,
                "ready_to_apply",
                proposal_id,
            )
        if lifecycle.state is ProposalLifecycleState.REJECTED:
            controller.cancel()
            return _patch_reconciliation_result(
                controller.execution,
                "cancelled_after_rejection",
                proposal_id,
            )
        if lifecycle.state is ProposalLifecycleState.APPLIED:
            if controller.execution.stage is ExecutionStage.AWAIT_APPROVAL:
                controller.complete_stage(ExecutionStage.APPLY)
            controller.complete_stage(ExecutionStage.COMPLETE)
            return _patch_reconciliation_result(
                controller.execution,
                "completed_after_application",
                proposal_id,
            )
        if lifecycle.state in {
            ProposalLifecycleState.STALE,
            ProposalLifecycleState.APPLICATION_FAILED,
        }:
            controller.fail(
                DiagnosticCollection(
                    (
                        Diagnostic(
                            DiagnosticCode("EXECUTION_PATCH_RECONCILIATION_FAILED"),
                            DiagnosticSeverity.ERROR,
                            "The persisted patch lifecycle cannot continue.",
                            "execution",
                            technical_details=(f"Proposal lifecycle is {lifecycle.state.value}."),
                        ),
                    )
                )
            )
            return _patch_reconciliation_result(
                controller.execution,
                "failed_from_patch_lifecycle",
                proposal_id,
                exit_code=CliExitCode.PATCH_APPLICATION_FAILURE,
            )
    except Exception as error:
        return CliCommandResult(
            {"command": "execution resume", "status": "reconciliation_failed"},
            CliExitCode.PROJECT_STATE_CONFLICT,
            _diagnostics(_execution_failure_diagnostics(error)),
        )
    return None


def _patch_reconciliation_result(
    execution: Execution,
    status: str,
    proposal_id: PatchProposalId,
    *,
    exit_code: CliExitCode = CliExitCode.SUCCESS,
) -> CliCommandResult:
    return CliCommandResult(
        {
            "command": "execution resume",
            "execution": _execution_payload(
                execution,
                task_available=True,
            ),
            "proposal_id": str(proposal_id),
            "status": status,
        },
        exit_code,
    )


def _context_payload(bundle: ContextBundle) -> dict[str, object]:
    items = []
    for order, item in enumerate(bundle.items):
        selected = item.selected_item
        items.append(
            {
                "budget_cost": selected.estimated_bytes,
                "context_item_id": item.context_item_id,
                "evidence": [
                    {
                        "detail": evidence.detail,
                        "source": evidence.source,
                        "type": evidence.evidence_type,
                    }
                    for evidence in selected.rationale.evidence
                ],
                "order": order,
                "path": item.source_path.value if item.source_path is not None else None,
                "primary_reason": selected.rationale.primary_reason.value,
                "rank": order + 1,
                "sensitivity": selected.sensitivity_classification,
                "source_reference": item.source_reference,
                "type": selected.candidate_type.value,
            }
        )
    return {
        "bundle_id": str(bundle.bundle_id),
        "created_at": bundle.created_at.isoformat(),
        "coverage": {
            field_name: getattr(bundle.coverage, field_name).value
            for field_name in (
                "targets",
                "dependencies",
                "interfaces",
                "tests",
                "configuration",
                "constraints",
                "error_locations",
            )
        },
        "items": items,
        "media_type": ContextBundleSerializer().serialize(bundle).media_type,
        "project_fingerprint": str(bundle.project_fingerprint),
        "retrieval_id": str(bundle.retrieval_id),
        "statistics": {
            field_name: getattr(bundle.statistics, field_name)
            for field_name in bundle.statistics.__dataclass_fields__
        },
    }


def _context_packet(
    prepared: ContextPreparationResult,
    task_text: str,
    max_items: int,
    max_bytes: int,
) -> dict[str, object]:
    bundle = prepared.context_bundle
    selected = {item.context_item_id: item for item in prepared.retrieval_result.selected_items}
    items: list[dict[str, object]] = []
    for item in bundle.items:
        retrieval_item = selected[item.context_item_id]
        rationale = retrieval_item.rationale
        items.append(
            {
                "content": item.content,
                "context_item_id": item.context_item_id,
                "evidence": [
                    {
                        "detail": evidence.detail,
                        "source": evidence.source,
                        "type": evidence.evidence_type,
                        "weight": evidence.weight,
                    }
                    for evidence in rationale.evidence
                ],
                "path": item.source_path.value if item.source_path is not None else None,
                "primary_reason": rationale.primary_reason.value,
                "score": rationale.score,
                "sensitivity": retrieval_item.sensitivity_classification,
                "source_reference": item.source_reference,
                "truncated": retrieval_item.is_truncated,
                "type": retrieval_item.candidate_type.value,
            }
        )
    return {
        "budget": {"max_bytes": max_bytes, "max_items": max_items},
        "bundle_id": str(bundle.bundle_id),
        "coverage": {
            field_name: getattr(bundle.coverage, field_name).value
            for field_name in (
                "targets",
                "dependencies",
                "interfaces",
                "tests",
                "configuration",
                "constraints",
                "error_locations",
            )
        }
        | {"missing_references": list(bundle.coverage.missing_references)},
        "estimated_context_tokens": bundle.statistics.estimated_tokens,
        "items": items,
        "packet_version": "contextforge-agent-context-v1",
        "project_fingerprint": str(bundle.project_fingerprint),
        "retrieval_id": str(bundle.retrieval_id),
        "statistics": {
            field_name: getattr(bundle.statistics, field_name)
            for field_name in bundle.statistics.__dataclass_fields__
        },
        "task": task_text,
    }


def _load_context(root: ProjectRoot) -> dict[str, object] | None:
    source = root.path / ".contextforge" / "executions" / "latest-context.json"
    try:
        loaded = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


_PROMPT_SECRET_PATTERN = re.compile(
    r"\b(password|token|secret|api[_-]?key|credential|authorization)\s*([:=])\s*"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)",
    flags=re.IGNORECASE,
)
_PROMPT_BEARER_PATTERN = re.compile(
    r"\bbearer\s+[A-Za-z0-9._~+/=-]+",
    flags=re.IGNORECASE,
)


def _redact_prompt_text(value: str) -> tuple[str, bool]:
    redacted = _PROMPT_BEARER_PATTERN.sub("Bearer [REDACTED]", value)
    redacted = _PROMPT_SECRET_PATTERN.sub(
        lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]",
        redacted,
    )
    return redacted, redacted != value


def _prompt_payload(request: InferenceRequest) -> dict[str, object]:
    contains_sensitive = request.delivery_requirements.contains_sensitive_context
    was_redacted = False
    sections: list[dict[str, object]] = []
    for message in request.messages:
        if message.section_id == "serialized-context-bundle" and contains_sensitive:
            content = "[REDACTED: sensitive project context]"
            changed = True
        else:
            content, changed = _redact_prompt_text(message.content)
        was_redacted = was_redacted or changed
        sections.append(
            {
                "content": content,
                "order": message.order,
                "role": message.role.value,
                "section_id": message.section_id,
                "trust": message.trust.value,
            }
        )
    contract = request.response_contract
    requirements = request.delivery_requirements
    return {
        "context_bundle_id": str(request.context_bundle_id),
        "created_at": request.created_at.isoformat(),
        "delivery_requirements": {
            field_name: (list(value) if isinstance(value, tuple) else value)
            for field_name in requirements.__dataclass_fields__
            if (value := getattr(requirements, field_name)) is not None
        },
        "diagnostics": list(_diagnostics(request.diagnostics)),
        "measurements": {
            field_name: getattr(request.measurements, field_name)
            for field_name in request.measurements.__dataclass_fields__
        },
        "prompt_template_version": request.prompt_template_version,
        "redacted": was_redacted,
        "request_id": str(request.request_id),
        "response_contract": {
            "allow_commentary": contract.allow_commentary,
            "contract_id": contract.contract_id,
            "error_behavior": contract.error_behavior,
            "maximum_response_bytes": contract.maximum_response_bytes,
            "output_format": contract.output_format.value,
            "prohibited_operations": list(contract.prohibited_operations),
            "purpose": contract.purpose,
            "required_fields": list(contract.required_fields),
            "response_type": contract.response_type,
            "validation_instructions": list(contract.validation_instructions),
            "version": contract.version,
        },
        "sections": sections,
        "task_id": str(request.task_id),
    }


def _load_prompt(root: ProjectRoot) -> dict[str, object] | None:
    source = root.path / ".contextforge" / "executions" / "latest-prompt.json"
    try:
        loaded = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _context_failure(code: str, message: str) -> CliCommandResult:
    return CliCommandResult(
        {"status": "failed"},
        CliExitCode.GENERAL_FAILURE,
        (
            {
                "capability": "context_inspection",
                "code": code,
                "message": message,
            },
        ),
    )


def _prompt_failure(code: str, message: str) -> CliCommandResult:
    return CliCommandResult(
        {"status": "failed"},
        CliExitCode.GENERAL_FAILURE,
        (
            {
                "capability": "prompt_inspection",
                "code": code,
                "message": message,
            },
        ),
    )


def _provider_capabilities(
    capabilities: ProviderCapabilityProfile,
) -> dict[str, object]:
    return {
        "adapter_id": capabilities.adapter_id,
        "adapter_version": capabilities.adapter_version,
        "cancellation_supported": capabilities.cancellation_supported,
        "context_limit_tokens": capabilities.context_limit_tokens,
        "execution_mode": capabilities.execution_mode.value,
        "health_check_supported": capabilities.health_check_supported,
        "maximum_output_tokens": capabilities.maximum_output_tokens,
        "model_discovery_supported": capabilities.model_discovery_supported,
        "multiple_messages_supported": capabilities.multiple_messages_supported,
        "profile_id": capabilities.profile_id,
        "provider_id": capabilities.provider_id,
        "streaming_supported": capabilities.streaming_supported,
        "structured_output_supported": capabilities.structured_output_supported,
        "supported_request_features": [
            feature.value for feature in capabilities.supported_request_features
        ],
        "supported_response_formats": [
            response_format.value for response_format in capabilities.supported_response_formats
        ],
        "usage_reporting_supported": capabilities.usage_reporting_supported,
    }


def _provider_summary(
    provider: ProviderPort | None,
    config: ProviderConfig,
) -> dict[str, object]:
    if provider is None:
        raise RuntimeError("Configured provider registry is inconsistent")
    capabilities = cast(ProviderCapabilityProfile, provider.get_capabilities())
    health = provider.health_check()
    return {
        "adapter_id": capabilities.adapter_id,
        "context_limit_tokens": capabilities.context_limit_tokens,
        "default_model": _effective_model_id(provider, config),
        "execution_mode": capabilities.execution_mode.value,
        "health": health.status.value,
        "provider_id": capabilities.provider_id,
        "structured_output_supported": capabilities.structured_output_supported,
    }


def _effective_model_id(provider: ProviderPort, config: ProviderConfig) -> str | None:
    """Return the effective model identifier for presentation."""
    capabilities = cast(ProviderCapabilityProfile, provider.get_capabilities())
    if capabilities.provider_id == MOCK_PROVIDER_ID:
        return MOCK_MODEL_ID
    if capabilities.provider_id == "ollama-local":
        return config.model_id or _DEFAULT_OLLAMA_MODEL
    return config.model_id


def _provider_failure(code: str, message: str) -> CliCommandResult:
    return CliCommandResult(
        {"status": "failed"},
        CliExitCode.PROVIDER_FAILURE,
        (
            {
                "capability": "provider_inspection",
                "code": code,
                "message": message,
            },
        ),
    )


def _configuration_failure(code: str, message: str) -> CliCommandResult:
    return CliCommandResult(
        {"status": "failed"},
        CliExitCode.CONFIGURATION_FAILURE,
        (
            {
                "capability": "configuration",
                "code": code,
                "message": message,
            },
        ),
    )


def _patch_summary(record: dict[str, object]) -> dict[str, object]:
    changes = record.get("changes")
    lifecycle = record.get("lifecycle")
    validation = record.get("validation")
    return {
        "approval_state": record.get("approval_state"),
        "change_count": len(changes) if isinstance(changes, list) else 0,
        "created_at": record.get("created_at"),
        "lifecycle_state": (lifecycle.get("state") if isinstance(lifecycle, dict) else None),
        "project_fingerprint": record.get("project_fingerprint"),
        "proposal_id": record.get("proposal_id"),
        "summary": record.get("summary"),
        "validation_state": (validation.get("state") if isinstance(validation, dict) else None),
    }


def _patch_review(record: dict[str, object]) -> dict[str, object]:
    raw_changes = record.get("changes")
    changes = raw_changes if isinstance(raw_changes, list) else []
    reviewed_changes = [_review_change(change) for change in changes if isinstance(change, dict)]
    validation = record.get("validation")
    diagnostics = validation.get("diagnostics", []) if isinstance(validation, dict) else []
    warnings = [
        diagnostic
        for diagnostic in diagnostics
        if isinstance(diagnostic, dict)
        and diagnostic.get("severity") in ("warning", "error", "critical")
    ]
    return {
        "affected_files": sorted(
            {
                str(path)
                for change in reviewed_changes
                for path in (change["path"], change["destination_path"])
                if path is not None
            }
        ),
        "changes": reviewed_changes,
        "operation_counts": {
            operation: sum(change["operation"] == operation for change in reviewed_changes)
            for operation in ("create", "modify", "delete", "rename")
        },
        "project_fingerprint": record.get("project_fingerprint"),
        "proposal_id": record.get("proposal_id"),
        "state_conflicts": [
            warning
            for warning in warnings
            if "FINGERPRINT" in str(warning.get("code", ""))
            or "CONSISTENCY" in str(warning.get("code", ""))
            or "STALE" in str(warning.get("code", ""))
        ],
        "validation_state": (validation.get("state") if isinstance(validation, dict) else None),
        "warnings": warnings,
    }


def _review_change(change: dict[str, object]) -> dict[str, object]:
    payload = change.get("patch_payload")
    lines = payload.splitlines() if isinstance(payload, str) else []
    added = sum(line.startswith("+") and not line.startswith("+++") for line in lines)
    removed = sum(line.startswith("-") and not line.startswith("---") for line in lines)
    if lines and added == 0 and removed == 0:
        added = len(lines)
    return {
        "added_lines": added,
        "change_id": change.get("change_id"),
        "destination_path": change.get("destination_path"),
        "explanation": change.get("explanation"),
        "operation": change.get("operation"),
        "path": change.get("path"),
        "removed_lines": removed,
    }


def _patch_failure(code: str, message: str) -> CliCommandResult:
    return CliCommandResult(
        {"status": "failed"},
        CliExitCode.GENERAL_FAILURE,
        (
            {
                "capability": "patch_inspection",
                "code": code,
                "message": message,
            },
        ),
    )


def _patch_workflow_failure(error: Exception) -> CliCommandResult:
    code = (
        "CLI_PATCH_STALE"
        if isinstance(error, StaleProjectStateError)
        else "CLI_PATCH_STATE_INVALID"
        if isinstance(error, PatchWorkflowStateError)
        else "CLI_PATCH_PROPOSAL_NOT_FOUND"
    )
    return _patch_failure(code, str(error))


def _patch_application_failure(error: Exception) -> CliCommandResult:
    if isinstance(error, ProjectLockUnavailableError):
        code = "CLI_PROJECT_LOCKED"
        exit_code = CliExitCode.PROJECT_STATE_CONFLICT
    elif isinstance(error, PatchApplicationOutcomeUnknownError):
        code = "CLI_PATCH_APPLICATION_OUTCOME_UNKNOWN"
        exit_code = CliExitCode.PROJECT_STATE_CONFLICT
    elif isinstance(error, StaleProjectStateError):
        code = "CLI_PATCH_STALE"
        exit_code = CliExitCode.PROJECT_STATE_CONFLICT
    elif isinstance(error, (PatchApprovalBindingError, PatchApprovalNotFoundError)):
        code = "CLI_PATCH_SECURITY_REJECTED"
        exit_code = CliExitCode.SECURITY_POLICY_REJECTION
    elif isinstance(error, PatchWorkflowStateError):
        code = "CLI_PATCH_APPROVAL_REQUIRED"
        exit_code = CliExitCode.APPROVAL_REQUIRED
    else:
        code = "CLI_PATCH_PROPOSAL_NOT_FOUND"
        exit_code = CliExitCode.PATCH_APPLICATION_FAILURE
    failed = _patch_failure(code, str(error))
    return CliCommandResult(failed.data, exit_code, failed.diagnostics)


def resolve_cli_project(
    project: Path | None,
    *,
    working_directory: Path | None = None,
) -> tuple[ProjectRoot | None, CliCommandResult | None]:
    """Resolve a CLI project and normalize resolution failures."""
    resolution = resolve_project_root(
        explicit_project=project,
        working_directory=working_directory,
    )
    if resolution.root is not None and resolution.succeeded:
        return resolution.root, None
    return None, CliCommandResult(
        {"status": "failed"},
        CliExitCode.PROJECT_RESOLUTION_FAILURE,
        _diagnostics(resolution.diagnostics),
    )


def render_result(result: CliCommandResult, *, output_format: str | None) -> None:
    """Render requested results to stdout and diagnostics to stderr."""
    if output_format == "json":
        status = (
            "success"
            if result.exit_code is CliExitCode.SUCCESS
            else "partial"
            if result.exit_code is CliExitCode.PARTIAL_RESULT
            else "failed"
        )
        envelope = {
            "data": result.data,
            "diagnostics": list(result.diagnostics),
            "schema_version": "1.0",
            "status": status,
        }
        typer.echo(json.dumps(envelope, ensure_ascii=False, sort_keys=True))
    else:
        for key, value in result.data.items():
            typer.echo(f"{key.replace('_', ' ').title()}: {value}")
    for diagnostic in result.diagnostics:
        typer.echo(
            f"{diagnostic['code']}: {diagnostic['message']}",
            err=True,
        )
