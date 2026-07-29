"""Conservative recovery policy for persisted workflow executions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from contextforge.domain import Execution, ExecutionStage


class RecoveryDisposition(StrEnum):
    """Safe operational action available for one persisted execution."""

    RESUMABLE = "resumable"
    AWAITING_ACTION = "awaiting_action"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"
    TERMINAL = "terminal"


@dataclass(frozen=True, slots=True)
class ExecutionRecoveryAssessment:
    """Explain whether and how an execution may continue."""

    disposition: RecoveryDisposition
    reason: str
    resume_from: ExecutionStage | None = None


_DETERMINISTIC_STAGES = frozenset(
    {
        ExecutionStage.RESOLVE,
        ExecutionStage.SCAN,
        ExecutionStage.INDEX,
        ExecutionStage.RETRIEVE,
        ExecutionStage.BUILD_CONTEXT,
        ExecutionStage.BUILD_PROMPT,
    }
)


def assess_execution_recovery(
    execution: Execution,
    *,
    task_available: bool = True,
) -> ExecutionRecoveryAssessment:
    """Classify recovery without repeating externally observable operations."""
    if not isinstance(execution, Execution):
        raise TypeError("execution must be an Execution")
    if not isinstance(task_available, bool):
        raise TypeError("task_available must be a bool")
    if execution.status.is_terminal:
        return ExecutionRecoveryAssessment(
            RecoveryDisposition.TERMINAL,
            "The execution is already terminal.",
        )
    if execution.stage in _DETERMINISTIC_STAGES:
        if not task_available:
            return ExecutionRecoveryAssessment(
                RecoveryDisposition.MANUAL_REVIEW_REQUIRED,
                "The original task input is unavailable, so the execution cannot be reconstructed.",
            )
        return ExecutionRecoveryAssessment(
            RecoveryDisposition.RESUMABLE,
            "The current stage is deterministic and may be reconstructed from persisted state.",
            execution.stage,
        )
    if execution.stage is ExecutionStage.AWAIT_APPROVAL:
        return ExecutionRecoveryAssessment(
            RecoveryDisposition.AWAITING_ACTION,
            "The patch proposal requires explicit approval or rejection.",
        )
    if execution.stage is ExecutionStage.APPLY:
        return ExecutionRecoveryAssessment(
            RecoveryDisposition.AWAITING_ACTION,
            "Application requires an explicit command and current-state revalidation.",
        )
    return ExecutionRecoveryAssessment(
        RecoveryDisposition.MANUAL_REVIEW_REQUIRED,
        "The stage may have external side effects and must not be replayed automatically.",
    )
