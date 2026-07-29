from __future__ import annotations

import json
from pathlib import Path

import pytest

from contextforge.adapters.filesystem import (
    LocalProjectLock,
    ProjectLockOwnershipError,
    ProjectLockUnavailableError,
)
from contextforge.project import ProjectRoot, ProjectRootSource


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
