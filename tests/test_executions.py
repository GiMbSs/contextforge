"""Tests for execution correlation and lifecycle transitions."""

from dataclasses import FrozenInstanceError

import pytest

from contextforge.domain import (
    EXECUTION_STAGE_ORDER,
    Execution,
    ExecutionStage,
    ExecutionStatus,
    new_execution_id,
    new_project_id,
    new_task_id,
)


def make_execution() -> Execution:
    return Execution(new_execution_id(), new_project_id(), new_task_id())


def test_execution_advances_through_all_canonical_stages() -> None:
    execution = make_execution().start()

    for stage in EXECUTION_STAGE_ORDER[1:]:
        execution = execution.advance(stage)

    assert execution.stage is ExecutionStage.COMPLETE
    assert execution.status is ExecutionStatus.COMPLETED
    assert execution.completed_stages == EXECUTION_STAGE_ORDER[:-1]


@pytest.mark.parametrize(
    "next_stage",
    [ExecutionStage.RESOLVE, ExecutionStage.SCAN, ExecutionStage.RETRIEVE],
)
def test_execution_rejects_backward_or_skipped_stage(next_stage: ExecutionStage) -> None:
    execution = make_execution().start().advance(ExecutionStage.SCAN)

    with pytest.raises(ValueError, match="Expected next stage INDEX"):
        execution.advance(next_stage)


def test_execution_must_be_started_before_advancing() -> None:
    with pytest.raises(ValueError, match="running"):
        make_execution().advance(ExecutionStage.SCAN)


@pytest.mark.parametrize("terminal_action", ["fail", "cancel"])
def test_failed_and_cancelled_executions_are_terminal(terminal_action: str) -> None:
    execution = make_execution().start().advance(ExecutionStage.SCAN)
    terminal = getattr(execution, terminal_action)()

    assert terminal.status.is_terminal
    with pytest.raises(ValueError, match="terminal"):
        terminal.fail()
    with pytest.raises(ValueError, match="terminal"):
        terminal.cancel()
    with pytest.raises(ValueError, match="running"):
        terminal.advance(ExecutionStage.INDEX)


def test_completed_execution_is_terminal() -> None:
    execution = make_execution().start()
    for stage in EXECUTION_STAGE_ORDER[1:]:
        execution = execution.advance(stage)

    with pytest.raises(ValueError, match="terminal"):
        execution.cancel()


def test_execution_equality_uses_execution_identifier() -> None:
    execution = make_execution()
    correlated_snapshot = Execution(
        execution.execution_id,
        execution.project_id,
        execution.task_id,
    ).start()

    assert execution == correlated_snapshot
    assert hash(execution) == hash(correlated_snapshot)


def test_execution_snapshot_is_immutable() -> None:
    execution = make_execution()

    with pytest.raises(FrozenInstanceError):
        execution.status = ExecutionStatus.RUNNING  # type: ignore[misc]


def test_execution_rejects_inconsistent_completed_stage_history() -> None:
    with pytest.raises(ValueError, match="canonical prefix"):
        Execution(
            new_execution_id(),
            new_project_id(),
            new_task_id(),
            stage=ExecutionStage.INDEX,
            status=ExecutionStatus.RUNNING,
            completed_stages=(ExecutionStage.RESOLVE,),
        )
