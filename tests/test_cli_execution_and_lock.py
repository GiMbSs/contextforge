from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from contextforge.adapters.filesystem import (
    FilesystemExecutionControlStorage,
    LocalProjectLock,
)
from contextforge.adapters.project_commands import _project_id
from contextforge.application import ExecutionController
from contextforge.cli.main import app
from contextforge.domain import Execution, new_execution_id, new_project_id, new_task_id
from contextforge.project import ProjectRoot, ProjectRootSource

runner = CliRunner()


def _root(path: Path) -> ProjectRoot:
    return ProjectRoot(path.resolve(), ProjectRootSource.EXPLICIT)


def _payload(result: object) -> dict[str, object]:
    envelope = json.loads(result.stdout)  # type: ignore[attr-defined]
    return envelope["data"]


def test_execution_show_and_cancel_reopen_persisted_state(tmp_path: Path) -> None:
    root = _root(tmp_path)
    execution = Execution(new_execution_id(), new_project_id(), new_task_id())
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

    result = runner.invoke(
        app,
        ["--project", str(tmp_path), "--format", "json", "execution", "list"],
    )

    assert result.exit_code == 0
    executions = _payload(result)["executions"]
    assert isinstance(executions, list)
    assert [item["execution_id"] for item in executions] == [str(included.execution_id)]
    assert executions[0]["recovery"]["disposition"] == "resumable"


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
