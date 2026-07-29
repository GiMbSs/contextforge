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
)
from contextforge.project import ProjectRoot
from contextforge.shared import SerializationEnvelope

_SCHEMA_VERSION = "1.0"
_EXECUTION_SCHEMA = "contextforge.execution"
_STAGE_SCHEMA = "contextforge.execution_stage"


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

    def _execution_directory(self, execution_id: ExecutionId) -> Path:
        return self._directory / str(execution_id)

    def _execution_path(self, execution_id: ExecutionId) -> Path:
        return self._execution_directory(execution_id) / "execution.json"

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
