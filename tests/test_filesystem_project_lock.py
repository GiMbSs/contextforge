from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from contextforge.adapters.filesystem import (
    LocalProjectLock,
    ProjectLockOwnershipError,
    ProjectLockUnavailableError,
)
from contextforge.project import ProjectRoot, ProjectRootSource

NOW = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)


def _root(path: Path) -> ProjectRoot:
    return ProjectRoot(path, ProjectRootSource.EXPLICIT)


def test_project_lock_excludes_another_owner_and_is_reusable(tmp_path: Path) -> None:
    root = _root(tmp_path)
    first = LocalProjectLock(root, "patch_apply")
    second = LocalProjectLock(root, "patch_apply")

    first.acquire()
    with pytest.raises(ProjectLockUnavailableError):
        second.acquire()
    first.release()

    second.acquire()
    second.release()


def test_context_manager_releases_lock_after_failure(tmp_path: Path) -> None:
    root = _root(tmp_path)

    with pytest.raises(RuntimeError, match="injected"), LocalProjectLock(root, "test"):
        raise RuntimeError("injected")

    with LocalProjectLock(root, "retry"):
        pass


def test_lock_cannot_remove_another_owners_record(tmp_path: Path) -> None:
    lock = LocalProjectLock(_root(tmp_path), "patch_apply")
    lock.acquire()
    destination = tmp_path / ".contextforge" / "locks" / "project.lock"
    payload = json.loads(destination.read_text(encoding="utf-8"))
    payload["owner_token"] = "another-owner"
    destination.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProjectLockOwnershipError):
        lock.release()

    assert destination.is_file()


def test_abandoned_lock_recovery_requires_age_and_dead_owner(tmp_path: Path) -> None:
    root = _root(tmp_path)
    lock = LocalProjectLock(root, "patch_apply", clock=lambda: NOW - timedelta(hours=2))
    lock.acquire()

    with pytest.raises(ProjectLockUnavailableError, match="still active"):
        LocalProjectLock.recover_abandoned(
            root,
            clock=lambda: NOW,
            process_alive=lambda _pid: True,
        )

    recovered = LocalProjectLock.recover_abandoned(
        root,
        clock=lambda: NOW,
        process_alive=lambda _pid: False,
    )

    assert recovered.operation == "patch_apply"
    assert LocalProjectLock.inspect(root) is None


def test_recent_abandoned_lock_is_not_recovered(tmp_path: Path) -> None:
    root = _root(tmp_path)
    LocalProjectLock(root, "patch_apply", clock=lambda: NOW).acquire()

    with pytest.raises(ProjectLockUnavailableError, match="not old enough"):
        LocalProjectLock.recover_abandoned(
            root,
            clock=lambda: NOW + timedelta(minutes=5),
            process_alive=lambda _pid: False,
        )
