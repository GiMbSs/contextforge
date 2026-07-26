"""Tests for cancellation, stage diagnostics, and terminal cleanup."""

from contextforge.application import ExecutionController, StageOutcome
from contextforge.diagnostics import DiagnosticCollection
from contextforge.domain import (
    Execution,
    ExecutionStage,
    ExecutionStatus,
    new_execution_id,
    new_inference_request_id,
    new_project_id,
    new_task_id,
)
from contextforge.provider import (
    CancellationResult,
    CancellationStatus,
    ProviderOperation,
)


class MemoryStorage:
    def __init__(self):
        self.executions = []
        self.stages = []

    def save_execution(self, execution):
        self.executions.append(execution)

    def save_stage_diagnostics(self, diagnostics):
        self.stages.append(diagnostics)


class Capabilities:
    provider_id = "provider"
    adapter_id = "adapter"

    def __init__(self, cancellation_supported):
        self.supported_operations = (
            (ProviderOperation.INVOKE, ProviderOperation.CANCEL)
            if cancellation_supported
            else (ProviderOperation.INVOKE,)
        )


class Provider:
    def __init__(self, cancellation_supported=True):
        self.capabilities = Capabilities(cancellation_supported)
        self.cancelled = []

    def get_capabilities(self):
        return self.capabilities

    def health_check(self):
        raise NotImplementedError

    def list_models(self):
        return ()

    def invoke(self, request, execution_context):
        raise NotImplementedError

    def cancel(self, request_id):
        self.cancelled.append(request_id)
        return CancellationResult(request_id, CancellationStatus.CANCELLED)


def _controller():
    storage = MemoryStorage()
    execution = Execution(new_execution_id(), new_project_id(), new_task_id())
    return ExecutionController(execution, storage), storage


def test_completed_stage_diagnostics_remain_inspectable_after_cancellation() -> None:
    controller, storage = _controller()
    controller.complete_stage(ExecutionStage.SCAN)
    controller.complete_stage(ExecutionStage.INDEX)

    controller.cancel()

    assert [record.stage for record in storage.stages] == [
        ExecutionStage.RESOLVE,
        ExecutionStage.SCAN,
        ExecutionStage.INDEX,
    ]
    assert [record.outcome for record in storage.stages] == [
        StageOutcome.COMPLETED,
        StageOutcome.COMPLETED,
        StageOutcome.CANCELLED,
    ]
    assert controller.execution.status is ExecutionStatus.CANCELLED
    assert controller.execution.status is not ExecutionStatus.COMPLETED


def test_cancellation_propagates_only_when_provider_supports_it() -> None:
    controller, _ = _controller()
    provider = Provider()
    request_id = new_inference_request_id()

    result = controller.cancel(provider=provider, request_id=request_id)

    assert result is not None
    assert result.status is CancellationStatus.CANCELLED
    assert provider.cancelled == [request_id]

    unsupported_controller, _ = _controller()
    unsupported = Provider(False)
    unsupported_result = unsupported_controller.cancel(
        provider=unsupported,
        request_id=new_inference_request_id(),
    )
    assert unsupported_result is not None
    assert unsupported_result.status is CancellationStatus.NOT_SUPPORTED
    assert unsupported.cancelled == []


def test_cancel_releases_all_resources_even_when_one_cleanup_fails() -> None:
    controller, storage = _controller()
    released = []

    controller.register_cleanup(lambda: released.append("lock"))

    def fail_cleanup():
        released.append("temporary")
        raise OSError("injected cleanup failure")

    controller.register_cleanup(fail_cleanup)
    controller.register_cleanup(lambda: released.append("provider"))

    controller.cancel()

    assert released == ["provider", "temporary", "lock"]
    assert len(storage.stages[-1].diagnostics) == 1
    assert (
        str(storage.stages[-1].diagnostics.diagnostics[0].code)
        == "EXECUTION_RESOURCE_RELEASE_FAILED"
    )


def test_completion_releases_resources() -> None:
    controller, _ = _controller()
    released = []
    controller.register_cleanup(lambda: released.append("released"))

    for stage in tuple(ExecutionStage)[1:]:
        controller.complete_stage(stage, DiagnosticCollection())

    assert controller.execution.status is ExecutionStatus.COMPLETED
    assert released == ["released"]
