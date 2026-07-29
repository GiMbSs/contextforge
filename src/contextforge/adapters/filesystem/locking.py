"""Exclusive, process-safe locks for local project operations."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict, cast
from uuid import uuid4

from contextforge.project import ProjectRoot


class ProjectLockUnavailableError(RuntimeError):
    """Another process currently owns the requested project lock."""


class ProjectLockOwnershipError(RuntimeError):
    """A process attempted to release a lock it does not own."""


@dataclass(frozen=True, slots=True)
class ProjectLockInfo:
    """Non-secret metadata describing the current project lock."""

    operation: str
    owner_pid: int
    acquired_at: datetime


class _LockPayload(TypedDict):
    acquired_at: str
    operation: str
    owner_pid: int
    owner_token: str
    schema_version: str


class LocalProjectLock:
    """Acquire one lock atomically and release it only with the owner token."""

    def __init__(
        self,
        root: ProjectRoot,
        operation: str,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not operation.strip():
            raise ValueError("operation must not be empty")
        self._path = root.path / ".contextforge" / "locks" / "project.lock"
        self._operation = operation
        self._clock = clock or (lambda: datetime.now(UTC))
        self._token = uuid4().hex
        self._acquired = False

    def acquire(self) -> None:
        """Atomically acquire the project lock without stealing stale locks."""
        if self._acquired:
            raise ProjectLockOwnershipError("lock is already held by this owner")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {
                "acquired_at": self._clock().isoformat(),
                "operation": self._operation,
                "owner_pid": os.getpid(),
                "owner_token": self._token,
                "schema_version": "1",
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        try:
            descriptor = os.open(
                self._path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError as error:
            raise ProjectLockUnavailableError(
                "Another ContextForge operation is active for this project"
            ) from error
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(payload + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            self._path.unlink(missing_ok=True)
            raise
        self._acquired = True

    def release(self) -> None:
        """Release the lock after verifying its unguessable ownership token."""
        if not self._acquired:
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ProjectLockOwnershipError("lock ownership cannot be verified") from error
        if not isinstance(payload, dict) or payload.get("owner_token") != self._token:
            raise ProjectLockOwnershipError("project lock belongs to another owner")
        self._path.unlink()
        self._acquired = False

    def __enter__(self) -> LocalProjectLock:
        self.acquire()
        return self

    def __exit__(self, *_error: object) -> None:
        self.release()

    @classmethod
    def inspect(cls, root: ProjectRoot) -> ProjectLockInfo | None:
        """Inspect lock metadata without acquiring or modifying the lock."""
        path = root.path / ".contextforge" / "locks" / "project.lock"
        if not path.is_file():
            return None
        payload, _serialized = cls._read_lock(path)
        return ProjectLockInfo(
            operation=payload["operation"],
            owner_pid=payload["owner_pid"],
            acquired_at=datetime.fromisoformat(payload["acquired_at"]),
        )

    @classmethod
    def recover_abandoned(
        cls,
        root: ProjectRoot,
        *,
        minimum_age_seconds: int = 3600,
        clock: Callable[[], datetime] | None = None,
        process_alive: Callable[[int], bool] | None = None,
    ) -> ProjectLockInfo:
        """Remove a sufficiently old lock only when its owner is confirmed dead."""
        if type(minimum_age_seconds) is not int or minimum_age_seconds < 1:
            raise ValueError("minimum_age_seconds must be a positive integer")
        path = root.path / ".contextforge" / "locks" / "project.lock"
        if not path.is_file():
            raise ProjectLockUnavailableError("No project lock exists")
        payload, serialized = cls._read_lock(path)
        acquired_at = datetime.fromisoformat(payload["acquired_at"])
        now = (clock or (lambda: datetime.now(UTC)))()
        if acquired_at.tzinfo is None or now.tzinfo is None:
            raise ProjectLockOwnershipError("lock timestamps must be timezone-aware")
        age = (now - acquired_at).total_seconds()
        if age < minimum_age_seconds:
            raise ProjectLockUnavailableError("Project lock is not old enough for recovery")
        owner_pid = payload["owner_pid"]
        alive = (process_alive or cls._process_alive)(owner_pid)
        if alive:
            raise ProjectLockUnavailableError("Project lock owner is still active")
        try:
            if path.read_text(encoding="utf-8") != serialized:
                raise ProjectLockOwnershipError("project lock changed during recovery")
            path.unlink()
        except OSError as error:
            raise ProjectLockOwnershipError("project lock could not be recovered") from error
        return ProjectLockInfo(payload["operation"], owner_pid, acquired_at)

    @staticmethod
    def _read_lock(path: Path) -> tuple[_LockPayload, str]:
        try:
            serialized = path.read_text(encoding="utf-8")
            payload = json.loads(serialized)
        except (OSError, json.JSONDecodeError) as error:
            raise ProjectLockOwnershipError("project lock metadata is invalid") from error
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("operation"), str)
            or type(payload.get("owner_pid")) is not int
            or not isinstance(payload.get("acquired_at"), str)
            or not isinstance(payload.get("owner_token"), str)
        ):
            raise ProjectLockOwnershipError("project lock metadata is invalid")
        try:
            datetime.fromisoformat(payload["acquired_at"])
        except ValueError as error:
            raise ProjectLockOwnershipError("project lock timestamp is invalid") from error
        return cast("_LockPayload", payload), serialized

    @staticmethod
    def _process_alive(process_id: int) -> bool:
        if sys.platform == "win32":
            return LocalProjectLock._windows_process_alive(process_id)
        try:
            os.kill(process_id, 0)
        except ProcessLookupError:
            return False
        except (PermissionError, OSError):
            return True
        return True

    @staticmethod
    def _windows_process_alive(process_id: int) -> bool:
        import ctypes

        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information,
            False,
            process_id,
        )
        if not handle:
            return bool(ctypes.windll.kernel32.GetLastError() != 87)
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
