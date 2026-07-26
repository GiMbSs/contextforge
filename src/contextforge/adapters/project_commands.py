"""Thin CLI composition for foundational project commands."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import IntEnum
from pathlib import Path
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

import typer

from contextforge.adapters.filesystem import (
    LocalProjectInitialization,
    LocalProjectScanner,
)
from contextforge.application import (
    AnalysisExecutionPipeline,
    ExecuteTask,
    InitializeProject,
    ProjectInitialization,
)
from contextforge.configuration import ScannerConfig
from contextforge.context import (
    ContextBundle,
    ContextBundleSerializer,
    ContextCoverage,
    ContextStatistics,
)
from contextforge.diagnostics import DiagnosticCollection
from contextforge.domain import (
    IndexId,
    InventoryId,
    ProjectId,
    RequestedOutput,
    TaskKind,
    TaskSpecification,
    new_context_bundle_id,
    new_retrieval_id,
    new_task_id,
)
from contextforge.indexer import (
    DeterministicProjectIndexer,
    IndexRequest,
    ProjectIndex,
)
from contextforge.project import ProjectRoot, resolve_project_root
from contextforge.prompt import InferenceRequest
from contextforge.provider import (
    DeterministicMockProvider,
    MockProviderScenario,
    ProviderPort,
)
from contextforge.retrieval import (
    ContextBudget,
    RetrievalRequest,
    RetrievalResult,
    RetrievalStatistics,
    RetrievalStatus,
)
from contextforge.scanner import DiscoveryStatus, ProjectArtifact, ProjectInventory, ScanRequest


class CliExitCode(IntEnum):
    """Stable process exit codes assigned by the CLI specification."""

    SUCCESS = 0
    GENERAL_FAILURE = 1
    PROJECT_RESOLUTION_FAILURE = 4
    SCAN_FAILURE = 5
    INDEX_FAILURE = 6
    PARTIAL_RESULT = 17


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
    ) -> CliCommandResult: ...

    def inspect_context(
        self,
        root: ProjectRoot,
        operation: str,
        *,
        target: str | None = None,
        destination: Path | None = None,
    ) -> CliCommandResult: ...

    def inspect_prompt(
        self,
        root: ProjectRoot,
        operation: str,
        *,
        destination: Path | None = None,
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
    scanner_configuration: ScannerConfig = field(default_factory=ScannerConfig)

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
        return CliCommandResult(
            {
                "command": "status",
                "configuration_present": configuration.is_file(),
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
        project_index = DeterministicProjectIndexer(_LocalSource(root.path)).index(
            IndexRequest(inventory)
        )
        failed = project_index.status.value == "failed"
        return CliCommandResult(
            {
                "artifact_count": len(project_index.indexed_artifacts),
                "command": "index",
                "index_id": str(project_index.index_id),
                "project_fingerprint": str(project_index.project_fingerprint),
                "project_root": str(root.path),
                "relationships": len(project_index.relationships),
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
    ) -> CliCommandResult:
        inventory = self._scan(root)
        project_index = DeterministicProjectIndexer(_LocalSource(root.path)).index(
            IndexRequest(inventory)
        )
        pipeline = AnalysisExecutionPipeline(
            inventory_storage=_SingleInventoryStorage(inventory),
            index_storage=_SingleIndexStorage(project_index),
            indexer=DeterministicProjectIndexer(_LocalSource(root.path)),
            retriever=_EmptyRetriever(),
            context_builder=_EmptyContextBuilder(),
            providers=_MockProviders(),
            budget=ContextBudget(max_items=20, max_bytes=64_000),
        )
        task = TaskSpecification(
            new_task_id(),
            task_text,
            TaskKind.EXPLAIN,
            RequestedOutput.ANALYSIS,
        )
        result = pipeline.execute(ExecuteTask(_project_id(root), task, provider_id))
        self._persist_context(root, result.context_bundle)
        self._persist_prompt(root, result.inference_request)
        return CliCommandResult(
            {
                "command": "run",
                "findings": len(result.analysis.findings),
                "mode": "analysis_only",
                "project_root": str(root.path),
                "request_id": str(result.inference_request.request_id),
                "status": "completed",
                "summary": result.analysis.summary,
                "task": task_text,
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

    def _scan(self, root: ProjectRoot) -> ProjectInventory:
        return self.scanner.scan(ScanRequest(_project_id(root), root, self.scanner_configuration))


def _project_id(root: ProjectRoot) -> ProjectId:
    identity = uuid5(NAMESPACE_URL, root.path.as_uri())
    return ProjectId(f"project_{identity.hex}")


@dataclass(slots=True)
class _SingleInventoryStorage:
    inventory: ProjectInventory

    def load(self, inventory_id: InventoryId) -> ProjectInventory | None:
        return self.inventory if inventory_id == self.inventory.inventory_id else None

    def load_latest(self, project_id: ProjectId) -> ProjectInventory | None:
        return self.inventory if project_id == self.inventory.project_id else None

    def save(self, inventory: ProjectInventory) -> None:
        self.inventory = inventory


@dataclass(slots=True)
class _SingleIndexStorage:
    project_index: ProjectIndex

    def load(self, project_id: ProjectId) -> ProjectIndex | None:
        return self.project_index if project_id == self.project_index.project_id else None

    def save(self, project_index: ProjectIndex) -> None:
        self.project_index = project_index

    def remove(self, index_id: IndexId) -> None:
        if index_id == self.project_index.index_id:
            raise ValueError("active CLI index cannot be removed")


class _EmptyRetriever:
    def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        return RetrievalResult(
            new_retrieval_id(),
            request.task.task_id,
            request.project_index.index_id,
            request.project_index.project_fingerprint,
            ("cli-empty-retriever-v1",),
            (),
            (),
            (),
            request.budget,
            DiagnosticCollection(),
            RetrievalStatistics(),
            RetrievalStatus.INCOMPLETE,
            datetime.now(UTC),
        )


class _EmptyContextBuilder:
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
            "cli-empty-context-v1",
            datetime.now(UTC),
        )


class _MockProviders:
    def get(self, provider_id: str) -> ProviderPort | None:
        if provider_id != "mock-provider":
            return None
        return DeterministicMockProvider(
            MockProviderScenario.SUCCESSFUL_ANALYSIS,
            datetime.now(UTC),
        )


def _diagnostics(collection: DiagnosticCollection) -> tuple[dict[str, object], ...]:
    return tuple(item.to_dict() for item in collection)


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
        typer.echo(json.dumps(result.data, ensure_ascii=False, sort_keys=True))
    else:
        for key, value in result.data.items():
            typer.echo(f"{key.replace('_', ' ').title()}: {value}")
    for diagnostic in result.diagnostics:
        typer.echo(
            f"{diagnostic['code']}: {diagnostic['message']}",
            err=True,
        )
