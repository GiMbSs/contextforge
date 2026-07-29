from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

import contextforge.adapters.project_commands as project_commands
from contextforge.adapters.filesystem import (
    FilesystemExecutionControlStorage,
    LocalProjectLock,
)
from contextforge.adapters.project_commands import _project_id
from contextforge.application import ExecutionController
from contextforge.cli.main import app
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
from contextforge.provider import DeterministicMockProvider, MockProviderScenario

runner = CliRunner()


def _root(path: Path) -> ProjectRoot:
    return ProjectRoot(path.resolve(), ProjectRootSource.EXPLICIT)


def _payload(result: object) -> dict[str, object]:
    envelope = json.loads(result.stdout)  # type: ignore[attr-defined]
    return envelope["data"]


def test_execution_show_and_cancel_reopen_persisted_state(tmp_path: Path) -> None:
    root = _root(tmp_path)
    execution = Execution(new_execution_id(), _project_id(root), new_task_id())
    ExecutionController(execution, FilesystemExecutionControlStorage(root))

    shown = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--format",
            "json",
            "execution",
            "show",
            str(execution.execution_id),
        ],
    )
    cancelled = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--format",
            "json",
            "execution",
            "cancel",
            str(execution.execution_id),
        ],
    )

    assert shown.exit_code == 0
    assert _payload(shown)["execution"]["status"] == "running"  # type: ignore[index]
    assert cancelled.exit_code == 0
    assert _payload(cancelled)["execution"]["status"] == "cancelled"  # type: ignore[index]


def test_execution_list_is_scoped_to_the_resolved_project(tmp_path: Path) -> None:
    root = _root(tmp_path)
    storage = FilesystemExecutionControlStorage(root)
    included = Execution(new_execution_id(), _project_id(root), new_task_id())
    excluded = Execution(new_execution_id(), new_project_id(), new_task_id())
    ExecutionController(included, storage)
    ExecutionController(excluded, storage)
    storage.save_task(
        included.execution_id,
        TaskSpecification(
            included.task_id,
            "Included task",
            TaskKind.ANALYZE,
            RequestedOutput.ANALYSIS,
        ),
    )

    result = runner.invoke(
        app,
        ["--project", str(tmp_path), "--format", "json", "execution", "list"],
    )

    assert result.exit_code == 0
    executions = _payload(result)["executions"]
    assert isinstance(executions, list)
    assert [item["execution_id"] for item in executions] == [str(included.execution_id)]
    assert executions[0]["recovery"]["disposition"] == "resumable"


def test_execution_commands_hide_another_project_execution(tmp_path: Path) -> None:
    root = _root(tmp_path)
    execution = Execution(new_execution_id(), new_project_id(), new_task_id())
    ExecutionController(execution, FilesystemExecutionControlStorage(root))

    result = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--format",
            "json",
            "execution",
            "show",
            str(execution.execution_id),
        ],
    )

    assert result.exit_code == 1
    assert _payload(result)["status"] == "failed"


def test_execution_resume_reconstructs_only_deterministic_stages(tmp_path: Path) -> None:
    root = _root(tmp_path)
    storage = FilesystemExecutionControlStorage(root)
    task = TaskSpecification(
        new_task_id(),
        "Explain deterministic recovery",
        TaskKind.EXPLAIN,
        RequestedOutput.ANALYSIS,
        metadata=(("provider_id", "provider-that-must-not-run"),),
    )
    execution = Execution(
        new_execution_id(),
        _project_id(root),
        task.task_id,
        workflow=ExecutionWorkflow.ANALYSIS,
    )
    ExecutionController(execution, storage)
    storage.save_task(execution.execution_id, task)

    result = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--format",
            "json",
            "execution",
            "resume",
            str(execution.execution_id),
        ],
    )

    assert result.exit_code == 0
    payload = _payload(result)
    assert payload["status"] == "paused_before_provider"
    assert payload["execution"]["stage"] == "invoke_provider"  # type: ignore[index]
    assert payload["execution"]["recovery"]["disposition"] == (  # type: ignore[index]
        "awaiting_action"
    )
    assert (tmp_path / ".contextforge" / "executions" / "latest-context.json").is_file()
    assert (tmp_path / ".contextforge" / "executions" / "latest-prompt.json").is_file()
    assert task.task_text not in result.stdout


def test_execution_resume_rejects_provider_boundary(tmp_path: Path) -> None:
    root = _root(tmp_path)
    storage = FilesystemExecutionControlStorage(root)
    task = TaskSpecification(
        new_task_id(),
        "Do not invoke the provider",
        TaskKind.EXPLAIN,
        RequestedOutput.ANALYSIS,
    )
    execution = Execution(
        new_execution_id(),
        _project_id(root),
        task.task_id,
        workflow=ExecutionWorkflow.ANALYSIS,
    )
    controller = ExecutionController(execution, storage)
    storage.save_task(execution.execution_id, task)
    for stage in (
        ExecutionStage.SCAN,
        ExecutionStage.INDEX,
        ExecutionStage.RETRIEVE,
        ExecutionStage.BUILD_CONTEXT,
        ExecutionStage.BUILD_PROMPT,
        ExecutionStage.INVOKE_PROVIDER,
    ):
        controller.complete_stage(stage)

    result = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--format",
            "json",
            "execution",
            "resume",
            str(execution.execution_id),
        ],
    )

    assert result.exit_code == 14
    assert _payload(result)["status"] == "recovery_rejected"
    restored = storage.load_execution(execution.execution_id)
    assert restored is not None
    assert restored.stage is ExecutionStage.INVOKE_PROVIDER


def test_execution_invoke_requires_confirmation_and_persists_response(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    storage = FilesystemExecutionControlStorage(root)
    task = TaskSpecification(
        new_task_id(),
        "Explain explicit invocation",
        TaskKind.EXPLAIN,
        RequestedOutput.ANALYSIS,
        metadata=(("provider_id", "mock-provider"),),
    )
    execution = Execution(
        new_execution_id(),
        _project_id(root),
        task.task_id,
        workflow=ExecutionWorkflow.ANALYSIS,
    )
    ExecutionController(execution, storage)
    storage.save_task(execution.execution_id, task)
    resumed = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--format",
            "json",
            "execution",
            "resume",
            str(execution.execution_id),
        ],
    )
    assert resumed.exit_code == 0

    unconfirmed = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--format",
            "json",
            "execution",
            "invoke",
            str(execution.execution_id),
        ],
    )
    assert unconfirmed.exit_code == 11
    assert storage.load_invocation(execution.execution_id) is None

    invoked = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--format",
            "json",
            "execution",
            "invoke",
            str(execution.execution_id),
            "--confirm",
        ],
    )

    assert invoked.exit_code == 0
    payload = _payload(invoked)
    assert payload["status"] == "response_persisted"
    assert payload["execution"]["stage"] == "validate_response"  # type: ignore[index]
    assert payload["invocation"]["status"] == "received"  # type: ignore[index]
    assert "content" not in payload["invocation"]["response"]  # type: ignore[index]
    assert task.task_text not in invoked.stdout
    invocation = storage.load_invocation(execution.execution_id)
    assert invocation is not None
    assert invocation["status"] == "received"

    repeated = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--format",
            "json",
            "execution",
            "invoke",
            str(execution.execution_id),
            "--confirm",
        ],
    )
    assert repeated.exit_code == 14


def test_execution_invoke_never_repeats_an_unknown_provider_outcome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _root(tmp_path)
    storage = FilesystemExecutionControlStorage(root)
    task = TaskSpecification(
        new_task_id(),
        "Exercise unknown invocation outcome",
        TaskKind.EXPLAIN,
        RequestedOutput.ANALYSIS,
        metadata=(("provider_id", "mock-provider"),),
    )
    execution = Execution(
        new_execution_id(),
        _project_id(root),
        task.task_id,
        workflow=ExecutionWorkflow.ANALYSIS,
    )
    ExecutionController(execution, storage)
    storage.save_task(execution.execution_id, task)
    resumed = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--format",
            "json",
            "execution",
            "resume",
            str(execution.execution_id),
        ],
    )
    assert resumed.exit_code == 0

    failing_provider = DeterministicMockProvider(
        MockProviderScenario.TIMEOUT,
        datetime(2026, 7, 28, tzinfo=UTC),
    )

    class _Registry:
        @staticmethod
        def get(provider_id: str) -> DeterministicMockProvider | None:
            return failing_provider if provider_id == "mock-provider" else None

    monkeypatch.setattr(
        project_commands,
        "_provider_registry",
        lambda *_args, **_kwargs: _Registry(),
    )
    command = [
        "--project",
        str(tmp_path),
        "--format",
        "json",
        "execution",
        "invoke",
        str(execution.execution_id),
        "--confirm",
    ]

    first = runner.invoke(app, command)
    repeated = runner.invoke(app, command)

    assert first.exit_code == 9
    assert repeated.exit_code == 9
    assert _payload(first)["status"] == "outcome_unknown"
    assert _payload(repeated)["status"] == "outcome_unknown"
    invocation = storage.load_invocation(execution.execution_id)
    assert invocation is not None
    assert invocation["status"] == "submitted"
    restored = storage.load_execution(execution.execution_id)
    assert restored is not None
    assert restored.stage is ExecutionStage.INVOKE_PROVIDER


def test_lock_show_reports_only_non_secret_metadata(tmp_path: Path) -> None:
    root = _root(tmp_path)
    lock = LocalProjectLock(root, "patch_apply")
    lock.acquire()
    try:
        result = runner.invoke(
            app,
            ["--project", str(tmp_path), "--format", "json", "lock", "show"],
        )
    finally:
        lock.release()

    assert result.exit_code == 0
    payload = _payload(result)
    assert payload["status"] == "locked"
    assert payload["lock"]["operation"] == "patch_apply"  # type: ignore[index]
    assert "owner_token" not in result.stdout


def test_lock_recover_requires_force_and_removes_old_dead_owner(tmp_path: Path) -> None:
    root = _root(tmp_path)
    lock = LocalProjectLock(
        root,
        "patch_apply",
        clock=lambda: datetime.now(UTC) - timedelta(hours=2),
    )
    lock.acquire()
    lock_path = tmp_path / ".contextforge" / "locks" / "project.lock"
    record = json.loads(lock_path.read_text(encoding="utf-8"))
    record["owner_pid"] = 99_999_999
    lock_path.write_text(json.dumps(record), encoding="utf-8")

    refused = runner.invoke(
        app,
        ["--project", str(tmp_path), "lock", "recover"],
    )
    recovered = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--format",
            "json",
            "lock",
            "recover",
            "--force",
        ],
    )

    assert refused.exit_code == 2
    assert recovered.exit_code == 0
    assert _payload(recovered)["status"] == "recovered"
    assert not lock_path.exists()
