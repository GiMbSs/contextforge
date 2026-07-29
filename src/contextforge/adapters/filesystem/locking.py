"""Exclusive, process-safe locks for local project operations."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from contextforge.project import ProjectRoot


class ProjectLockUnavailableError(RuntimeError):
    """Another process currently owns the requested project lock."""


class ProjectLockOwnershipError(RuntimeError):
    """A process attempted to release a lock it does not own."""


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
