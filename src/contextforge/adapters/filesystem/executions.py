"""Durable local storage for execution lifecycle snapshots and stage outcomes."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from contextforge.application import StageDiagnostics, StageOutcome
from contextforge.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticCollection,
    DiagnosticLocation,
    DiagnosticSeverity,
)
from contextforge.domain import (
    EXECUTION_STAGE_ORDER,
    Execution,
    ExecutionId,
    ExecutionStage,
    ExecutionStatus,
    ExecutionWorkflow,
    ProjectId,
    TaskId,
    TaskSpecification,
)
from contextforge.project import ProjectRoot
from contextforge.prompt import InferenceRequest
from contextforge.provider import InferenceResponse
from contextforge.shared import SerializationEnvelope

_SCHEMA_VERSION = "1.0"
_EXECUTION_SCHEMA = "contextforge.execution"
_STAGE_SCHEMA = "contextforge.execution_stage"
_TASK_SCHEMA = "contextforge.execution_task"
_INVOCATION_SCHEMA = "contextforge.execution_invocation"
_RESULT_SCHEMA = "contextforge.execution_result"


class ExecutionStorageError(RuntimeError):
    """An execution record is malformed or cannot be persisted safely."""


def _object(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ExecutionStorageError(f"{name} must be an object")
    return dict(value)


def _string(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ExecutionStorageError(f"{name} must be a string")
    return value


def _diagnostics_payload(collection: DiagnosticCollection) -> list[dict[str, object]]:
    return [diagnostic.to_dict() for diagnostic in collection]


def _restore_diagnostics(value: object) -> DiagnosticCollection:
    if not isinstance(value, (tuple, list)):
        raise ExecutionStorageError("diagnostics must be an array")
    restored: list[Diagnostic] = []
    for raw in value:
        item = _object(raw, "diagnostic")
        raw_location = item.get("location")
        location = None
        if raw_location is not None:
            location_data = _object(raw_location, "diagnostic location")
            location = DiagnosticLocation(
                _string(location_data["reference"], "diagnostic reference"),
                location_data.get("line"),
                location_data.get("column"),
            )
        metadata = _object(item.get("metadata", {}), "diagnostic metadata")
        restored.append(
            Diagnostic(
                DiagnosticCode(_string(item["code"], "diagnostic code")),
                DiagnosticSeverity(_string(item["severity"], "diagnostic severity")),
                _string(item["message"], "diagnostic message"),
                _string(item["capability"], "diagnostic capability"),
                location,
                item.get("guidance"),
                item.get("technical_details"),
                tuple(sorted(metadata.items())),
            )
        )
    return DiagnosticCollection(tuple(restored))


class FilesystemExecutionControlStorage:
    """Store restart-safe execution state below ``.contextforge/executions``."""

    def __init__(
        self,
        root: ProjectRoot,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._directory = root.path / ".contextforge" / "executions"
        self._clock = clock or (lambda: datetime.now(UTC))

    def save_execution(self, execution: Execution) -> None:
        envelope = SerializationEnvelope(
            _EXECUTION_SCHEMA,
            _SCHEMA_VERSION,
            str(execution.execution_id),
            self._clock(),
            "execution-control-v1",
            {
                "completed_stages": [stage.value for stage in execution.completed_stages],
                "project_id": str(execution.project_id),
                "stage": execution.stage.value,
                "status": execution.status.value,
                "task_id": str(execution.task_id),
                "workflow": execution.workflow.value,
            },
            {"project_id": str(execution.project_id)},
        )
        self._write_atomic(self._execution_path(execution.execution_id), envelope.to_json() + "\n")
        self._write_atomic(
            self._directory / "latest-execution.json",
            json.dumps(
                {
                    "execution_id": str(execution.execution_id),
                    "project_id": str(execution.project_id),
                    "schema_version": "1",
                },
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n",
        )

    def save_stage_diagnostics(self, diagnostics: StageDiagnostics) -> None:
        stage_number = EXECUTION_STAGE_ORDER.index(diagnostics.stage)
        destination = (
            self._execution_directory(diagnostics.execution_id)
            / "stages"
            / f"{stage_number:02d}-{diagnostics.stage.value}.json"
        )
        envelope = SerializationEnvelope(
            _STAGE_SCHEMA,
            _SCHEMA_VERSION,
            f"{diagnostics.execution_id}:{diagnostics.stage.value}",
            self._clock(),
            "execution-control-v1",
            {
                "diagnostics": _diagnostics_payload(diagnostics.diagnostics),
                "execution_id": str(diagnostics.execution_id),
                "outcome": diagnostics.outcome.value,
                "stage": diagnostics.stage.value,
            },
            {},
        )
        serialized = envelope.to_json() + "\n"
        if destination.is_file():
            existing = self._load_envelope(destination)
            existing_payload = _object(existing.payload, "stage payload")
            proposed_payload = _object(envelope.payload, "stage payload")
            if existing_payload != proposed_payload:
                raise ExecutionStorageError(
                    f"Stage {diagnostics.stage.value} already has a different outcome"
                )
            return
        self._write_atomic(destination, serialized)

    def save_task(self, execution_id: ExecutionId, task: TaskSpecification) -> None:
        """Persist the immutable task input correlated with an execution."""
        execution = self.load_execution(execution_id)
        if execution is None:
            raise ExecutionStorageError("Cannot persist a task without its execution")
        if execution.task_id != task.task_id:
            raise ExecutionStorageError("Task does not belong to the requested execution")
        destination = self._task_path(execution_id)
        envelope = SerializationEnvelope(
            _TASK_SCHEMA,
            _SCHEMA_VERSION,
            str(task.task_id),
            self._clock(),
            "execution-control-v1",
            task.to_dict(),
            {
                "execution_id": str(execution_id),
                "project_id": str(execution.project_id),
            },
        )
        serialized = envelope.to_json() + "\n"
        if destination.is_file():
            existing = self._load_envelope(destination)
            if (
                existing.schema_name != _TASK_SCHEMA
                or existing.artifact_id != str(task.task_id)
                or _object(existing.to_dict()["payload"], "task payload") != task.to_dict()
            ):
                raise ExecutionStorageError("Execution task cannot be replaced")
            return
        self._write_atomic(destination, serialized)

    def load_execution(self, execution_id: ExecutionId) -> Execution | None:
        destination = self._execution_path(execution_id)
        if not destination.is_file():
            return None
        envelope = self._load_envelope(destination)
        if envelope.schema_name != _EXECUTION_SCHEMA or envelope.artifact_id != str(execution_id):
            raise ExecutionStorageError("Record is not the requested execution")
        payload = _object(envelope.payload, "execution payload")
        completed = payload["completed_stages"]
        if not isinstance(completed, (tuple, list)):
            raise ExecutionStorageError("completed_stages must be an array")
        try:
            return Execution(
                execution_id,
                ProjectId.from_string(_string(payload["project_id"], "project_id")),
                TaskId.from_string(_string(payload["task_id"], "task_id")),
                ExecutionStage(_string(payload["stage"], "execution stage")),
                ExecutionStatus(_string(payload["status"], "execution status")),
                tuple(ExecutionStage(_string(stage, "completed stage")) for stage in completed),
                ExecutionWorkflow(_string(payload["workflow"], "execution workflow")),
            )
        except (TypeError, ValueError, KeyError) as error:
            raise ExecutionStorageError("Invalid execution snapshot") from error

    def load_latest(self, project_id: ProjectId) -> Execution | None:
        pointer = self._directory / "latest-execution.json"
        if not pointer.is_file():
            return None
        try:
            data = _object(json.loads(pointer.read_text(encoding="utf-8")), "latest pointer")
            if data.get("project_id") != str(project_id):
                return None
            execution_id = ExecutionId.from_string(_string(data["execution_id"], "execution_id"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError, KeyError) as error:
            raise ExecutionStorageError("Invalid latest execution pointer") from error
        return self.load_execution(execution_id)

    def load_stage_diagnostics(
        self,
        execution_id: ExecutionId,
    ) -> tuple[StageDiagnostics, ...]:
        stages = self._execution_directory(execution_id) / "stages"
        if not stages.is_dir():
            return ()
        restored: list[StageDiagnostics] = []
        for destination in sorted(stages.glob("*.json")):
            envelope = self._load_envelope(destination)
            if envelope.schema_name != _STAGE_SCHEMA:
                raise ExecutionStorageError(f"Record {destination.name} is not a stage outcome")
            payload = _object(envelope.payload, "stage payload")
            if payload.get("execution_id") != str(execution_id):
                raise ExecutionStorageError("Stage outcome belongs to another execution")
            try:
                restored.append(
                    StageDiagnostics(
                        execution_id,
                        ExecutionStage(_string(payload["stage"], "execution stage")),
                        StageOutcome(_string(payload["outcome"], "stage outcome")),
                        _restore_diagnostics(payload["diagnostics"]),
                    )
                )
            except (TypeError, ValueError, KeyError) as error:
                raise ExecutionStorageError("Invalid stage outcome") from error
        return tuple(restored)

    def load_task(self, execution_id: ExecutionId) -> TaskSpecification | None:
        """Restore the validated task input correlated with an execution."""
        destination = self._task_path(execution_id)
        if not destination.is_file():
            return None
        execution = self.load_execution(execution_id)
        if execution is None:
            raise ExecutionStorageError("Execution task has no execution snapshot")
        envelope = self._load_envelope(destination)
        metadata = _object(envelope.metadata, "task metadata")
        if (
            envelope.schema_name != _TASK_SCHEMA
            or envelope.artifact_id != str(execution.task_id)
            or metadata.get("execution_id") != str(execution_id)
            or metadata.get("project_id") != str(execution.project_id)
        ):
            raise ExecutionStorageError("Task record is not bound to the requested execution")
        try:
            task = TaskSpecification.from_dict(
                _object(envelope.to_dict()["payload"], "task payload")
            )
        except (TypeError, ValueError, KeyError) as error:
            raise ExecutionStorageError("Invalid execution task") from error
        if task.task_id != execution.task_id:
            raise ExecutionStorageError("Task record is not bound to the requested execution")
        return task

    def begin_invocation(
        self,
        execution: Execution,
        request: InferenceRequest,
        provider_id: str,
        context_references: tuple[str, ...],
    ) -> None:
        """Durably mark provider submission before the external call starts."""
        if execution.stage is not ExecutionStage.INVOKE_PROVIDER:
            raise ExecutionStorageError("Execution is not at the provider boundary")
        if request.task_id != execution.task_id or request.project_id != execution.project_id:
            raise ExecutionStorageError("Inference request does not belong to the execution")
        destination = self._invocation_path(execution.execution_id)
        if destination.exists():
            raise ExecutionStorageError("Provider invocation was already attempted")
        envelope = SerializationEnvelope(
            _INVOCATION_SCHEMA,
            _SCHEMA_VERSION,
            str(request.request_id),
            self._clock(),
            "execution-control-v1",
            {
                "execution_id": str(execution.execution_id),
                "context_references": list(context_references),
                "provider_id": provider_id,
                "project_fingerprint": str(request.project_fingerprint),
                "request_id": str(request.request_id),
                "response": None,
                "status": "submitted",
                "task_id": str(execution.task_id),
            },
            {"project_id": str(execution.project_id)},
        )
        self._write_atomic(destination, envelope.to_json() + "\n")

    def save_result(
        self,
        execution: Execution,
        result_type: str,
        payload: Mapping[str, object],
    ) -> None:
        """Persist one immutable validated workflow result."""
        destination = self._result_path(execution.execution_id)
        result_payload = {
            "execution_id": str(execution.execution_id),
            "result": dict(payload),
            "result_type": result_type,
            "task_id": str(execution.task_id),
        }
        if destination.exists():
            existing = self._load_envelope(destination)
            if (
                existing.schema_name == _RESULT_SCHEMA
                and existing.artifact_id == str(execution.execution_id)
                and _object(existing.to_dict()["payload"], "result payload") == result_payload
            ):
                return
            raise ExecutionStorageError("Execution result already exists")
        envelope = SerializationEnvelope(
            _RESULT_SCHEMA,
            _SCHEMA_VERSION,
            str(execution.execution_id),
            self._clock(),
            "execution-control-v1",
            result_payload,
            {"project_id": str(execution.project_id)},
        )
        self._write_atomic(destination, envelope.to_json() + "\n")

    def load_result(self, execution_id: ExecutionId) -> dict[str, object] | None:
        """Load a detached validated result record."""
        destination = self._result_path(execution_id)
        if not destination.is_file():
            return None
        envelope = self._load_envelope(destination)
        if envelope.schema_name != _RESULT_SCHEMA or envelope.artifact_id != str(execution_id):
            raise ExecutionStorageError("Record is not the requested execution result")
        return _object(envelope.to_dict()["payload"], "result payload")

    def complete_invocation(
        self,
        execution: Execution,
        response: InferenceResponse,
    ) -> None:
        """Persist normalized provider output before workflow advancement."""
        destination = self._invocation_path(execution.execution_id)
        if not destination.is_file():
            raise ExecutionStorageError("Provider invocation was not durably started")
        existing = self._load_envelope(destination)
        payload = _object(existing.to_dict()["payload"], "invocation payload")
        if (
            existing.schema_name != _INVOCATION_SCHEMA
            or payload.get("status") != "submitted"
            or payload.get("execution_id") != str(execution.execution_id)
            or payload.get("request_id") != str(response.request_id)
            or payload.get("task_id") != str(response.task_id)
            or payload.get("provider_id") != response.metadata.provider_id
        ):
            raise ExecutionStorageError("Provider response does not match the invocation")
        payload["status"] = "received"
        payload["response"] = {
            "content": response.content,
            "created_at": response.created_at.isoformat(),
            "finish_reason": response.finish_reason.value,
            "finish_state": response.finish_state.value,
            "measurements": {
                field_name: getattr(response.measurements, field_name)
                for field_name in response.measurements.__dataclass_fields__
            },
            "metadata": {
                field_name: (
                    getattr(response.metadata, field_name).isoformat()
                    if isinstance(getattr(response.metadata, field_name), datetime)
                    else getattr(response.metadata, field_name)
                )
                for field_name in response.metadata.__dataclass_fields__
            },
            "response_format": response.response_format.value,
            "response_id": str(response.response_id),
            "usage": (
                {
                    field_name: getattr(response.usage, field_name)
                    for field_name in response.usage.__dataclass_fields__
                }
                if response.usage is not None
                else None
            ),
        }
        envelope = SerializationEnvelope(
            _INVOCATION_SCHEMA,
            _SCHEMA_VERSION,
            existing.artifact_id,
            existing.created_at,
            existing.producer_version,
            payload,
            existing.metadata,
        )
        self._write_atomic(destination, envelope.to_json() + "\n")

    def load_invocation(self, execution_id: ExecutionId) -> dict[str, object] | None:
        """Return a detached invocation record for inspection and recovery."""
        destination = self._invocation_path(execution_id)
        if not destination.is_file():
            return None
        envelope = self._load_envelope(destination)
        if envelope.schema_name != _INVOCATION_SCHEMA:
            raise ExecutionStorageError("Record is not a provider invocation")
        return _object(envelope.to_dict()["payload"], "invocation payload")

    def find_by_task(self, task_id: TaskId) -> Execution | None:
        """Find the newest persisted execution correlated with a task."""
        if not self._directory.is_dir():
            return None
        matches: list[tuple[int, Execution]] = []
        for destination in self._directory.glob("execution_*/execution.json"):
            try:
                execution_id = ExecutionId.from_string(destination.parent.name)
                execution = self.load_execution(execution_id)
            except (ExecutionStorageError, ValueError):
                continue
            if execution is not None and execution.task_id == task_id:
                matches.append((destination.stat().st_mtime_ns, execution))
        return max(matches, key=lambda item: item[0])[1] if matches else None

    def list_executions(self, project_id: ProjectId) -> tuple[Execution, ...]:
        """List project executions newest first with every snapshot validated."""
        if not self._directory.is_dir():
            return ()
        matches: list[tuple[int, Execution]] = []
        for destination in self._directory.glob("execution_*/execution.json"):
            try:
                execution_id = ExecutionId.from_string(destination.parent.name)
            except ValueError as error:
                raise ExecutionStorageError(
                    f"Invalid execution directory {destination.parent.name}"
                ) from error
            execution = self.load_execution(execution_id)
            if execution is not None and execution.project_id == project_id:
                matches.append((destination.stat().st_mtime_ns, execution))
        return tuple(
            execution
            for _modified_at, execution in sorted(
                matches,
                key=lambda item: item[0],
                reverse=True,
            )
        )

    def _execution_directory(self, execution_id: ExecutionId) -> Path:
        return self._directory / str(execution_id)

    def _execution_path(self, execution_id: ExecutionId) -> Path:
        return self._execution_directory(execution_id) / "execution.json"

    def _task_path(self, execution_id: ExecutionId) -> Path:
        return self._execution_directory(execution_id) / "task.json"

    def _invocation_path(self, execution_id: ExecutionId) -> Path:
        return self._execution_directory(execution_id) / "invocation.json"

    def _result_path(self, execution_id: ExecutionId) -> Path:
        return self._execution_directory(execution_id) / "result.json"

    @staticmethod
    def _load_envelope(destination: Path) -> SerializationEnvelope:
        try:
            return SerializationEnvelope.from_json(destination.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError) as error:
            raise ExecutionStorageError(f"Invalid execution record {destination.name}") from error

    @staticmethod
    def _write_atomic(destination: Path, content: str) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.parent / f".{destination.name}.{uuid4().hex}.tmp"
        try:
            temporary.write_text(content, encoding="utf-8", newline="\n")
            os.replace(temporary, destination)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise ExecutionStorageError(f"Could not persist {destination.name}") from error
