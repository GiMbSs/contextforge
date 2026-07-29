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
    LocalStagedPatchApplication,
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


def _awaiting_patch_execution(
    tmp_path: Path,
) -> tuple[FilesystemExecutionControlStorage, Execution, str]:
    root = _root(tmp_path)
    storage = FilesystemExecutionControlStorage(root)
    task = TaskSpecification(
        new_task_id(),
        "Prepare a recoverable patch",
        TaskKind.MODIFY,
        RequestedOutput.PATCH_PROPOSAL,
        metadata=(("provider_id", "mock-provider"),),
    )
    execution = Execution(
        new_execution_id(),
        _project_id(root),
        task.task_id,
        workflow=ExecutionWorkflow.PATCH,
    )
    ExecutionController(execution, storage)
    storage.save_task(execution.execution_id, task)
    base = ["--project", str(tmp_path), "--format", "json", "execution"]
    assert (
        runner.invoke(
            app,
            [*base, "resume", str(execution.execution_id)],
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            app,
            [*base, "invoke", str(execution.execution_id), "--confirm"],
        ).exit_code
        == 0
    )
    validated = runner.invoke(
        app,
        [*base, "validate", str(execution.execution_id)],
    )
    assert validated.exit_code == 0, validated.stdout
    proposal_id = _payload(validated)["proposal_id"]
    assert isinstance(proposal_id, str)
    return storage, execution, proposal_id


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

    validated = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--format",
            "json",
            "execution",
            "validate",
            str(execution.execution_id),
        ],
    )

    assert validated.exit_code == 0
    validated_payload = _payload(validated)
    assert validated_payload["status"] == "completed"
    assert validated_payload["execution"]["status"] == "completed"  # type: ignore[index]
    result_record = storage.load_result(execution.execution_id)
    assert result_record is not None
    assert result_record["result_type"] == "analysis"


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


def test_execution_validate_materializes_patch_proposal(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    storage = FilesystemExecutionControlStorage(root)
    task = TaskSpecification(
        new_task_id(),
        "Prepare a patch",
        TaskKind.MODIFY,
        RequestedOutput.PATCH_PROPOSAL,
        metadata=(("provider_id", "mock-provider"),),
    )
    execution = Execution(
        new_execution_id(),
        _project_id(root),
        task.task_id,
        workflow=ExecutionWorkflow.PATCH,
    )
    ExecutionController(execution, storage)
    storage.save_task(execution.execution_id, task)
    for command in ("resume", "invoke"):
        arguments = [
            "--project",
            str(tmp_path),
            "--format",
            "json",
            "execution",
            command,
            str(execution.execution_id),
        ]
        if command == "invoke":
            arguments.append("--confirm")
        assert runner.invoke(app, arguments).exit_code == 0

    validated = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--format",
            "json",
            "execution",
            "validate",
            str(execution.execution_id),
        ],
    )

    assert validated.exit_code == 0, validated.stdout
    payload = _payload(validated)
    assert payload["status"] == "awaiting_approval"
    assert isinstance(payload["proposal_id"], str)
    restored = storage.load_execution(execution.execution_id)
    assert restored is not None
    assert restored.stage is ExecutionStage.AWAIT_APPROVAL
    result = storage.load_result(execution.execution_id)
    assert result is not None
    assert result["result_type"] == "patch_proposal"
    proposal_id = payload["proposal_id"]
    assert isinstance(proposal_id, str)

    approved = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--non-interactive",
            "--format",
            "json",
            "patch",
            "approve",
            proposal_id,
            "--approve",
            proposal_id,
        ],
    )

    assert approved.exit_code == 0, approved.stdout
    approval_id = _payload(approved)["approval_id"]
    repeated_approval = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--non-interactive",
            "--format",
            "json",
            "patch",
            "approve",
            proposal_id,
            "--approve",
            proposal_id,
        ],
    )
    assert repeated_approval.exit_code == 0, repeated_approval.stdout
    assert _payload(repeated_approval)["approval_id"] == approval_id
    assert len(tuple((tmp_path / ".contextforge" / "approvals").glob("*.json"))) == 1
    after_approval = storage.load_execution(execution.execution_id)
    assert after_approval is not None
    assert after_approval.stage is ExecutionStage.APPLY

    applied = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--format",
            "json",
            "patch",
            "apply",
            proposal_id,
        ],
    )

    assert applied.exit_code == 0, applied.stdout
    completed = storage.load_execution(execution.execution_id)
    assert completed is not None
    assert completed.stage is ExecutionStage.COMPLETE
    assert completed.status.value == "completed"
    assert (tmp_path / "src" / "contextforge_generated.py").read_text(
        encoding="utf-8"
    ) == "value = 42\n"
    repeated_application = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--format",
            "json",
            "patch",
            "apply",
            proposal_id,
        ],
    )
    assert repeated_application.exit_code == 0, repeated_application.stdout
    assert _payload(repeated_application)["status"] == "applied"


def test_execution_validate_rejects_patch_when_project_changed_after_invocation(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    storage = FilesystemExecutionControlStorage(root)
    task = TaskSpecification(
        new_task_id(),
        "Prepare a stale patch",
        TaskKind.MODIFY,
        RequestedOutput.PATCH_PROPOSAL,
        metadata=(("provider_id", "mock-provider"),),
    )
    execution = Execution(
        new_execution_id(),
        _project_id(root),
        task.task_id,
        workflow=ExecutionWorkflow.PATCH,
    )
    ExecutionController(execution, storage)
    storage.save_task(execution.execution_id, task)
    base = [
        "--project",
        str(tmp_path),
        "--format",
        "json",
        "execution",
    ]
    assert (
        runner.invoke(
            app,
            [*base, "resume", str(execution.execution_id)],
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            app,
            [*base, "invoke", str(execution.execution_id), "--confirm"],
        ).exit_code
        == 0
    )
    (tmp_path / "changed.py").write_text("value = 1\n", encoding="utf-8")

    validated = runner.invoke(
        app,
        [*base, "validate", str(execution.execution_id)],
    )

    assert validated.exit_code == 10
    assert _payload(validated)["status"] == "validation_failed"
    restored = storage.load_execution(execution.execution_id)
    assert restored is not None
    assert restored.status.value == "failed"


def test_execution_resume_reconciles_approval_persisted_before_stage_advance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage, execution, proposal_id = _awaiting_patch_execution(tmp_path)
    original_complete_stage = ExecutionController.complete_stage

    def interrupt_stage_advance(
        controller: ExecutionController,
        next_stage: ExecutionStage,
        *args: object,
        **kwargs: object,
    ) -> object:
        if next_stage is ExecutionStage.APPLY:
            raise RuntimeError("simulated interruption after approval")
        return original_complete_stage(controller, next_stage, *args, **kwargs)

    monkeypatch.setattr(ExecutionController, "complete_stage", interrupt_stage_advance)
    approved = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--non-interactive",
            "patch",
            "approve",
            proposal_id,
            "--approve",
            proposal_id,
        ],
    )
    assert approved.exit_code == 1
    monkeypatch.setattr(ExecutionController, "complete_stage", original_complete_stage)

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

    assert resumed.exit_code == 0, resumed.stdout
    assert _payload(resumed)["status"] == "ready_to_apply"
    restored = storage.load_execution(execution.execution_id)
    assert restored is not None
    assert restored.stage is ExecutionStage.APPLY


def test_execution_resume_reconciles_application_persisted_before_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage, execution, proposal_id = _awaiting_patch_execution(tmp_path)
    approved = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--non-interactive",
            "patch",
            "approve",
            proposal_id,
            "--approve",
            proposal_id,
        ],
    )
    assert approved.exit_code == 0
    original_complete_stage = ExecutionController.complete_stage

    def interrupt_completion(
        controller: ExecutionController,
        next_stage: ExecutionStage,
        *args: object,
        **kwargs: object,
    ) -> object:
        if next_stage is ExecutionStage.COMPLETE:
            raise RuntimeError("simulated interruption after application")
        return original_complete_stage(controller, next_stage, *args, **kwargs)

    monkeypatch.setattr(ExecutionController, "complete_stage", interrupt_completion)
    applied = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "patch",
            "apply",
            proposal_id,
        ],
    )
    assert applied.exit_code == 1
    monkeypatch.setattr(ExecutionController, "complete_stage", original_complete_stage)

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

    assert resumed.exit_code == 0, resumed.stdout
    assert _payload(resumed)["status"] == "completed_after_application"
    restored = storage.load_execution(execution.execution_id)
    assert restored is not None
    assert restored.stage is ExecutionStage.COMPLETE
    assert (tmp_path / "src" / "contextforge_generated.py").read_text(
        encoding="utf-8"
    ) == "value = 42\n"


def test_repeated_patch_rejection_reuses_fact_and_keeps_execution_cancelled(
    tmp_path: Path,
) -> None:
    storage, execution, proposal_id = _awaiting_patch_execution(tmp_path)
    command = [
        "--project",
        str(tmp_path),
        "--format",
        "json",
        "patch",
        "reject",
        proposal_id,
        "--reason",
        "Use a smaller change.",
    ]

    first = runner.invoke(app, command, input="y\n")
    repeated = runner.invoke(app, command, input="y\n")

    assert first.exit_code == 0
    assert repeated.exit_code == 0
    repeated_payload = json.loads(repeated.stdout.splitlines()[-1])["data"]
    assert repeated_payload["reason"] == "Use a smaller change."
    restored = storage.load_execution(execution.execution_id)
    assert restored is not None
    assert restored.status.value == "cancelled"


def test_patch_application_with_unknown_outcome_is_never_retried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage, execution, proposal_id = _awaiting_patch_execution(tmp_path)
    approved = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--non-interactive",
            "patch",
            "approve",
            proposal_id,
            "--approve",
            proposal_id,
        ],
    )
    assert approved.exit_code == 0
    original_apply = LocalStagedPatchApplication.apply_proposal

    def interrupt_after_mutation(
        application: LocalStagedPatchApplication,
        *args: object,
        **kwargs: object,
    ) -> object:
        generated = tmp_path / "src" / "contextforge_generated.py"
        generated.parent.mkdir(parents=True, exist_ok=True)
        generated.write_text("unknown outcome\n", encoding="utf-8")
        raise RuntimeError("simulated process interruption during mutation")

    monkeypatch.setattr(
        LocalStagedPatchApplication,
        "apply_proposal",
        interrupt_after_mutation,
    )
    command = [
        "--project",
        str(tmp_path),
        "--format",
        "json",
        "patch",
        "apply",
        proposal_id,
    ]
    interrupted = runner.invoke(app, command)
    assert interrupted.exit_code == 1
    monkeypatch.setattr(
        LocalStagedPatchApplication,
        "apply_proposal",
        original_apply,
    )

    repeated = runner.invoke(app, command)

    assert repeated.exit_code == 14
    assert "CLI_PATCH_APPLICATION_OUTCOME_UNKNOWN" in repeated.stdout
    assert (tmp_path / "src" / "contextforge_generated.py").read_text(
        encoding="utf-8"
    ) == "unknown outcome\n"
    attempt = json.loads(
        (tmp_path / ".contextforge" / "applications" / f"{proposal_id}.json").read_text(
            encoding="utf-8"
        )
    )
    assert attempt["attempt_status"] == "submitted"
    restored = storage.load_execution(execution.execution_id)
    assert restored is not None
    assert restored.stage is ExecutionStage.APPLY
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
    assert resumed.exit_code == 14
    assert _payload(resumed)["status"] == "application_outcome_unknown"


@pytest.mark.parametrize(
    ("workflow", "task_kind", "requested_output", "expected_exit_code"),
    [
        (ExecutionWorkflow.ANALYSIS, TaskKind.EXPLAIN, RequestedOutput.ANALYSIS, 8),
        (
            ExecutionWorkflow.PATCH,
            TaskKind.MODIFY,
            RequestedOutput.PATCH_PROPOSAL,
            10,
        ),
    ],
)
def test_execution_validate_fails_closed_on_malformed_persisted_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    workflow: ExecutionWorkflow,
    task_kind: TaskKind,
    requested_output: RequestedOutput,
    expected_exit_code: int,
) -> None:
    root = _root(tmp_path)
    storage = FilesystemExecutionControlStorage(root)
    task = TaskSpecification(
        new_task_id(),
        "Validate malformed output",
        task_kind,
        requested_output,
        metadata=(("provider_id", "mock-provider"),),
    )
    execution = Execution(
        new_execution_id(),
        _project_id(root),
        task.task_id,
        workflow=workflow,
    )
    ExecutionController(execution, storage)
    storage.save_task(execution.execution_id, task)
    assert (
        runner.invoke(
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
        ).exit_code
        == 0
    )
    malformed_provider = DeterministicMockProvider(
        MockProviderScenario.MALFORMED_RESPONSE,
        datetime(2026, 7, 28, tzinfo=UTC),
    )

    class _Registry:
        @staticmethod
        def get(provider_id: str) -> DeterministicMockProvider | None:
            return malformed_provider if provider_id == "mock-provider" else None

    monkeypatch.setattr(
        project_commands,
        "_provider_registry",
        lambda *_args, **_kwargs: _Registry(),
    )
    base = [
        "--project",
        str(tmp_path),
        "--format",
        "json",
        "execution",
    ]
    assert (
        runner.invoke(
            app,
            [*base, "invoke", str(execution.execution_id), "--confirm"],
        ).exit_code
        == 0
    )

    validated = runner.invoke(
        app,
        [*base, "validate", str(execution.execution_id)],
    )

    assert validated.exit_code == expected_exit_code
    assert _payload(validated)["status"] == "validation_failed"
    restored = storage.load_execution(execution.execution_id)
    assert restored is not None
    assert restored.status.value == "failed"
    assert storage.load_result(execution.execution_id) is None


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
