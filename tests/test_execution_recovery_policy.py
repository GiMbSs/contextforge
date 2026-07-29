from contextforge.application import RecoveryDisposition, assess_execution_recovery
from contextforge.domain import (
    Execution,
    ExecutionStage,
    ExecutionWorkflow,
    new_execution_id,
    new_project_id,
    new_task_id,
)


def _running_at(
    stage: ExecutionStage,
    *,
    workflow: ExecutionWorkflow = ExecutionWorkflow.PATCH,
) -> Execution:
    execution = Execution(
        new_execution_id(),
        new_project_id(),
        new_task_id(),
        workflow=workflow,
    ).start()
    order = (
        (
            ExecutionStage.RESOLVE,
            ExecutionStage.SCAN,
            ExecutionStage.INDEX,
            ExecutionStage.RETRIEVE,
            ExecutionStage.BUILD_CONTEXT,
            ExecutionStage.BUILD_PROMPT,
            ExecutionStage.INVOKE_PROVIDER,
            ExecutionStage.VALIDATE_RESPONSE,
            ExecutionStage.COMPLETE,
        )
        if workflow is ExecutionWorkflow.ANALYSIS
        else tuple(ExecutionStage)
    )
    for next_stage in order[1 : order.index(stage) + 1]:
        execution = execution.advance(next_stage)
    return execution


def test_deterministic_stage_is_resumable() -> None:
    execution = _running_at(ExecutionStage.INDEX)

    assessment = assess_execution_recovery(execution)

    assert assessment.disposition is RecoveryDisposition.RESUMABLE
    assert assessment.resume_from is ExecutionStage.INDEX


def test_deterministic_stage_without_task_requires_manual_review() -> None:
    execution = _running_at(
        ExecutionStage.INDEX,
        workflow=ExecutionWorkflow.ANALYSIS,
    )

    assessment = assess_execution_recovery(execution, task_available=False)

    assert assessment.disposition is RecoveryDisposition.MANUAL_REVIEW_REQUIRED
    assert assessment.resume_from is None


def test_provider_stage_requires_manual_review() -> None:
    execution = _running_at(ExecutionStage.INVOKE_PROVIDER)

    assessment = assess_execution_recovery(execution)

    assert assessment.disposition is RecoveryDisposition.MANUAL_REVIEW_REQUIRED


def test_patch_waiting_and_apply_require_explicit_action() -> None:
    awaiting = _running_at(ExecutionStage.AWAIT_APPROVAL)
    applying = _running_at(ExecutionStage.APPLY)

    assert assess_execution_recovery(awaiting).disposition is RecoveryDisposition.AWAITING_ACTION
    assert assess_execution_recovery(applying).disposition is RecoveryDisposition.AWAITING_ACTION


def test_terminal_execution_is_not_resumable() -> None:
    execution = _running_at(
        ExecutionStage.COMPLETE,
        workflow=ExecutionWorkflow.ANALYSIS,
    )

    assert assess_execution_recovery(execution).disposition is RecoveryDisposition.TERMINAL
