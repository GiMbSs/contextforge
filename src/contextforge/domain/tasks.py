"""Immutable representation of user-requested engineering tasks."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Self, cast

from contextforge.domain.identifiers import TaskId

type TaskMetadataValue = str | int | float | bool | None
type TaskMetadata = tuple[tuple[str, TaskMetadataValue], ...]


class TaskKind(StrEnum):
    """Canonical MVP engineering operation types."""

    ANALYZE = "analyze"
    EXPLAIN = "explain"
    MODIFY = "modify"
    FIX = "fix"
    REFACTOR = "refactor"
    ADD = "add"
    REMOVE = "remove"
    TEST = "test"
    DOCUMENT = "document"
    UNKNOWN = "unknown"


class RequestedOutput(StrEnum):
    """Provider-independent output requested for a task."""

    ANALYSIS = "analysis"
    PATCH_PROPOSAL = "patch_proposal"
    TEST_PLAN = "test_plan"
    DOCUMENTATION = "documentation"
    STRUCTURED_DIAGNOSTIC = "structured_diagnostic"


def _normalize_metadata(metadata: TaskMetadata) -> TaskMetadata:
    normalized: list[tuple[str, TaskMetadataValue]] = []
    seen_keys: set[str] = set()

    for key, value in metadata:
        normalized_key = key.strip()
        if not normalized_key:
            raise ValueError("Task metadata keys must not be empty")
        if normalized_key in seen_keys:
            raise ValueError(f"Duplicate Task metadata key: {normalized_key}")
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise ValueError("Task metadata values must be scalar")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Task metadata values must be finite")
        seen_keys.add(normalized_key)
        normalized.append((normalized_key, value))

    return tuple(sorted(normalized))


@dataclass(frozen=True, slots=True, eq=False)
class TaskSpecification:
    """One immutable normalized task that preserves the original user text."""

    task_id: TaskId
    task_text: str
    task_kind: TaskKind
    requested_output: RequestedOutput
    constraints: tuple[str, ...] = ()
    metadata: TaskMetadata = ()

    def __post_init__(self) -> None:
        if not isinstance(self.task_id, TaskId):
            raise TypeError("task_id must be a TaskId")
        if not isinstance(self.task_text, str):
            raise TypeError("task_text must be a string")
        if not isinstance(self.task_kind, TaskKind):
            raise TypeError("task_kind must be a TaskKind")
        if not isinstance(self.requested_output, RequestedOutput):
            raise TypeError("requested_output must be a RequestedOutput")
        if not self.task_text.strip():
            raise ValueError("Task text must not be empty")

        normalized_constraints = tuple(self.constraints)
        if any(not constraint.strip() for constraint in normalized_constraints):
            raise ValueError("Task constraints must not be empty")

        object.__setattr__(self, "constraints", normalized_constraints)
        object.__setattr__(self, "metadata", _normalize_metadata(tuple(self.metadata)))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TaskSpecification):
            return NotImplemented
        return self.task_id == other.task_id

    def __hash__(self) -> int:
        return hash(self.task_id)

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic serialization-ready representation."""
        return {
            "constraints": list(self.constraints),
            "metadata": dict(self.metadata),
            "requested_output": self.requested_output.value,
            "task_id": str(self.task_id),
            "task_kind": self.task_kind.value,
            "task_text": self.task_text,
        }

    @classmethod
    def from_dict(cls, serialized: dict[str, object]) -> Self:
        """Restore and validate a Task Specification from serialized data."""
        expected_fields = {
            "constraints",
            "metadata",
            "requested_output",
            "task_id",
            "task_kind",
            "task_text",
        }
        if set(serialized) != expected_fields:
            raise ValueError("Serialized Task Specification fields do not match the schema")

        task_id = serialized["task_id"]
        task_text = serialized["task_text"]
        task_kind = serialized["task_kind"]
        requested_output = serialized["requested_output"]
        constraints = serialized["constraints"]
        metadata = serialized["metadata"]

        if not all(
            isinstance(value, str) for value in (task_id, task_text, task_kind, requested_output)
        ):
            raise ValueError("Task identity, text, kind, and requested output must be strings")
        if not isinstance(constraints, list) or not all(
            isinstance(constraint, str) for constraint in constraints
        ):
            raise ValueError("Task constraints must be a list of strings")
        if not isinstance(metadata, dict) or not all(
            isinstance(key, str) and (value is None or isinstance(value, (str, int, float, bool)))
            for key, value in metadata.items()
        ):
            raise ValueError("Task metadata must be an object containing scalar values")

        normalized_constraints = cast("list[str]", constraints)
        normalized_metadata = cast("dict[str, TaskMetadataValue]", metadata)
        return cls(
            task_id=TaskId.from_string(cast("str", task_id)),
            task_text=cast("str", task_text),
            task_kind=TaskKind(cast("str", task_kind)),
            requested_output=RequestedOutput(cast("str", requested_output)),
            constraints=tuple(normalized_constraints),
            metadata=tuple(normalized_metadata.items()),
        )
