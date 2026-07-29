from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from contextforge.adapters.filesystem import (
    ExecutionStorageError,
    FilesystemExecutionControlStorage,
)
from contextforge.application import ExecutionController, StageDiagnostics, StageOutcome
from contextforge.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticCollection,
    DiagnosticSeverity,
)
from contextforge.domain import (
    Execution,
    ExecutionStage,
    ExecutionWorkflow,
    RequestedOutput,
    TaskKind,
    TaskSpecification,
    new_execution_id,
    new_project_id,
    new_task_id,
)
from contextforge.project import ProjectRoot, ProjectRootSource

NOW = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)


def _storage(tmp_path: Path) -> FilesystemExecutionControlStorage:
    root = ProjectRoot(tmp_path, ProjectRootSource.EXPLICIT)
    return FilesystemExecutionControlStorage(root, clock=lambda: NOW)


def test_execution_controller_state_survives_storage_reopen(tmp_path: Path) -> None:
    execution = Execution(new_execution_id(), new_project_id(), new_task_id())
    storage = _storage(tmp_path)
    controller = ExecutionController(execution, storage)
    diagnostic = Diagnostic(
        DiagnosticCode("EXECUTION_SCAN_COMPLETE"),
        DiagnosticSeverity.INFO,
        "Project scan completed.",
        "execution",
    )

    expected = controller.complete_stage(
        ExecutionStage.SCAN,
        DiagnosticCollection((diagnostic,)),
    )
    reopened = _storage(tmp_path)

    assert reopened.load_execution(execution.execution_id) == expected
    assert reopened.load_latest(execution.project_id) == expected
    stages = reopened.load_stage_diagnostics(execution.execution_id)
    assert stages == (
        StageDiagnostics(
            execution.execution_id,
            ExecutionStage.RESOLVE,
            StageOutcome.COMPLETED,
            DiagnosticCollection((diagnostic,)),
        ),
    )


def test_stage_outcomes_are_idempotent_but_cannot_be_rewritten(tmp_path: Path) -> None:
    execution = Execution(new_execution_id(), new_project_id(), new_task_id())
    storage = _storage(tmp_path)
    completed = StageDiagnostics(
        execution.execution_id,
        ExecutionStage.RESOLVE,
        StageOutcome.COMPLETED,
    )
    storage.save_stage_diagnostics(completed)
    storage.save_stage_diagnostics(completed)

    with pytest.raises(ExecutionStorageError, match="different outcome"):
        storage.save_stage_diagnostics(
            StageDiagnostics(
                execution.execution_id,
                ExecutionStage.RESOLVE,
                StageOutcome.FAILED,
            )
        )


def test_corrupt_execution_snapshot_fails_closed(tmp_path: Path) -> None:
    execution_id = new_execution_id()
    destination = tmp_path / ".contextforge" / "executions" / str(execution_id) / "execution.json"
    destination.parent.mkdir(parents=True)
    destination.write_text("{", encoding="utf-8")

    with pytest.raises(ExecutionStorageError, match="Invalid execution record"):
        _storage(tmp_path).load_execution(execution_id)


def test_analysis_workflow_completes_without_patch_stages(tmp_path: Path) -> None:
    execution = Execution(
        new_execution_id(),
        new_project_id(),
        new_task_id(),
        workflow=ExecutionWorkflow.ANALYSIS,
    )
    controller = ExecutionController(execution, _storage(tmp_path))

    for stage in (
        ExecutionStage.SCAN,
        ExecutionStage.INDEX,
        ExecutionStage.RETRIEVE,
        ExecutionStage.BUILD_CONTEXT,
        ExecutionStage.BUILD_PROMPT,
        ExecutionStage.INVOKE_PROVIDER,
        ExecutionStage.VALIDATE_RESPONSE,
        ExecutionStage.COMPLETE,
    ):
        controller.complete_stage(stage)

    assert controller.execution.status.value == "completed"
    assert ExecutionStage.BUILD_PROPOSAL not in controller.execution.completed_stages


def test_running_execution_can_resume_in_another_controller(tmp_path: Path) -> None:
    execution = Execution(new_execution_id(), new_project_id(), new_task_id())
    storage = _storage(tmp_path)
    first = ExecutionController(execution, storage)
    first.complete_stage(ExecutionStage.SCAN)

    restored = storage.find_by_task(execution.task_id)
    assert restored is not None
    resumed = ExecutionController.resume(restored, _storage(tmp_path))
    resumed.complete_stage(ExecutionStage.INDEX)

    assert resumed.execution.stage is ExecutionStage.INDEX


def test_execution_task_survives_storage_reopen_and_is_immutable(tmp_path: Path) -> None:
    task = TaskSpecification(
        new_task_id(),
        "Explain the recovery pipeline",
        TaskKind.EXPLAIN,
        RequestedOutput.ANALYSIS,
        constraints=("Do not modify files",),
        metadata=(("source", "cli"),),
    )
    execution = Execution(new_execution_id(), new_project_id(), task.task_id)
    storage = _storage(tmp_path)
    ExecutionController(execution, storage)

    storage.save_task(execution.execution_id, task)
    storage.save_task(execution.execution_id, task)

    assert _storage(tmp_path).load_task(execution.execution_id) == task
    replacement = TaskSpecification(
        task.task_id,
        "Different task text",
        task.task_kind,
        task.requested_output,
    )
    with pytest.raises(ExecutionStorageError, match="cannot be replaced"):
        storage.save_task(execution.execution_id, replacement)


def test_execution_task_must_match_execution_identity(tmp_path: Path) -> None:
    execution = Execution(new_execution_id(), new_project_id(), new_task_id())
    storage = _storage(tmp_path)
    ExecutionController(execution, storage)
    unrelated = TaskSpecification(
        new_task_id(),
        "Unrelated task",
        TaskKind.ANALYZE,
        RequestedOutput.ANALYSIS,
    )

    with pytest.raises(ExecutionStorageError, match="does not belong"):
        storage.save_task(execution.execution_id, unrelated)
