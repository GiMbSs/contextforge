"""Execution correlation and lifecycle primitives."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from contextforge.domain.identifiers import ExecutionId, ProjectId, TaskId


class ExecutionStage(StrEnum):
    """Canonical stages of a ContextForge execution."""

    RESOLVE = "resolve"
    SCAN = "scan"
    INDEX = "index"
    RETRIEVE = "retrieve"
    BUILD_CONTEXT = "build_context"
    BUILD_PROMPT = "build_prompt"
    INVOKE_PROVIDER = "invoke_provider"
    VALIDATE_RESPONSE = "validate_response"
    BUILD_PROPOSAL = "build_proposal"
    AWAIT_APPROVAL = "await_approval"
    APPLY = "apply"
    COMPLETE = "complete"


class ExecutionStatus(StrEnum):
    """Coarse lifecycle status independent of the current stage."""

    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        """Whether no further lifecycle transition is allowed."""
        return self in {
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
        }


EXECUTION_STAGE_ORDER: tuple[ExecutionStage, ...] = tuple(ExecutionStage)


@dataclass(frozen=True, slots=True, eq=False)
class Execution:
    """One immutable snapshot of a correlated workflow execution."""

    execution_id: ExecutionId
    project_id: ProjectId
    task_id: TaskId
    stage: ExecutionStage = ExecutionStage.RESOLVE
    status: ExecutionStatus = ExecutionStatus.CREATED
    completed_stages: tuple[ExecutionStage, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.execution_id, ExecutionId):
            raise TypeError("execution_id must be an ExecutionId")
        if not isinstance(self.project_id, ProjectId):
            raise TypeError("project_id must be a ProjectId")
        if not isinstance(self.task_id, TaskId):
            raise TypeError("task_id must be a TaskId")
        if not isinstance(self.stage, ExecutionStage):
            raise TypeError("stage must be an ExecutionStage")
        if not isinstance(self.status, ExecutionStatus):
            raise TypeError("status must be an ExecutionStatus")

        completed_stages = tuple(self.completed_stages)
        if any(not isinstance(stage, ExecutionStage) for stage in completed_stages):
            raise TypeError("completed_stages must contain only ExecutionStage values")
        object.__setattr__(self, "completed_stages", completed_stages)

        stage_index = EXECUTION_STAGE_ORDER.index(self.stage)
        if completed_stages != EXECUTION_STAGE_ORDER[:stage_index]:
            raise ValueError("completed_stages must be the canonical prefix before stage")
        if self.status is ExecutionStatus.CREATED and self.stage is not ExecutionStage.RESOLVE:
            raise ValueError("A created Execution must be at the RESOLVE stage")
        if self.status is ExecutionStatus.COMPLETED and self.stage is not ExecutionStage.COMPLETE:
            raise ValueError("A completed Execution must be at the COMPLETE stage")
        if self.stage is ExecutionStage.COMPLETE and self.status is not ExecutionStatus.COMPLETED:
            raise ValueError("The COMPLETE stage requires completed status")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Execution):
            return NotImplemented
        return self.execution_id == other.execution_id

    def __hash__(self) -> int:
        return hash(self.execution_id)

    def start(self) -> Execution:
        """Start a newly created execution."""
        if self.status is not ExecutionStatus.CREATED:
            raise ValueError("Only a created Execution can be started")
        return replace(self, status=ExecutionStatus.RUNNING)

    def advance(self, next_stage: ExecutionStage) -> Execution:
        """Advance a running execution to its single canonical next stage."""
        if self.status is not ExecutionStatus.RUNNING:
            raise ValueError("Only a running Execution can advance")
        if not isinstance(next_stage, ExecutionStage):
            raise TypeError("next_stage must be an ExecutionStage")

        stage_index = EXECUTION_STAGE_ORDER.index(self.stage)
        expected_index = stage_index + 1
        if expected_index >= len(EXECUTION_STAGE_ORDER):
            raise ValueError("The Execution has no next stage")
        expected_stage = EXECUTION_STAGE_ORDER[expected_index]
        if next_stage is not expected_stage:
            raise ValueError(f"Expected next stage {expected_stage.name}, got {next_stage.name}")

        status = (
            ExecutionStatus.COMPLETED
            if next_stage is ExecutionStage.COMPLETE
            else ExecutionStatus.RUNNING
        )
        return replace(
            self,
            stage=next_stage,
            status=status,
            completed_stages=(*self.completed_stages, self.stage),
        )

    def fail(self) -> Execution:
        """Terminate a created or running execution as failed."""
        self._ensure_non_terminal()
        return replace(self, status=ExecutionStatus.FAILED)

    def cancel(self) -> Execution:
        """Terminate a created or running execution as cancelled."""
        self._ensure_non_terminal()
        return replace(self, status=ExecutionStatus.CANCELLED)

    def _ensure_non_terminal(self) -> None:
        if self.status.is_terminal:
            raise ValueError("A terminal Execution cannot transition")
