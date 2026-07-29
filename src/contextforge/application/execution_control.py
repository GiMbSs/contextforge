"""Execution-stage diagnostics, cancellation, and resource cleanup."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from contextforge.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticCollection,
    DiagnosticSeverity,
)
from contextforge.domain import (
    Execution,
    ExecutionId,
    ExecutionStage,
    ExecutionStatus,
    InferenceRequestId,
)
from contextforge.provider import (
    CancellationResult,
    CancellationStatus,
    ProviderOperation,
    ProviderPort,
)


class StageOutcome(StrEnum):
    """Inspectable outcome of one execution stage."""

    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class StageDiagnostics:
    """Durable diagnostics retained for one attempted stage."""

    execution_id: ExecutionId
    stage: ExecutionStage
    outcome: StageOutcome
    diagnostics: DiagnosticCollection = field(default_factory=DiagnosticCollection)

    def __post_init__(self) -> None:
        if not isinstance(self.execution_id, ExecutionId):
            raise TypeError("execution_id must be an ExecutionId")
        if not isinstance(self.stage, ExecutionStage):
            raise TypeError("stage must be an ExecutionStage")
        if not isinstance(self.outcome, StageOutcome):
            raise TypeError("outcome must be a StageOutcome")
        if not isinstance(self.diagnostics, DiagnosticCollection):
            raise TypeError("diagnostics must be a DiagnosticCollection")


class ExecutionControlStorage(Protocol):
    """Persist execution snapshots and independently inspectable stage records."""

    def save_execution(self, execution: Execution) -> None:
        """Persist the latest immutable execution snapshot."""
        ...

    def save_stage_diagnostics(self, diagnostics: StageDiagnostics) -> None:
        """Persist a stage outcome without replacing prior completed stages."""
        ...


class ExecutionControlError(RuntimeError):
    """An invalid operation was requested from execution control."""


class ExecutionController:
    """Track stages and guarantee registered cleanup on every terminal path."""

    def __init__(
        self,
        execution: Execution,
        storage: ExecutionControlStorage,
    ) -> None:
        if not isinstance(execution, Execution):
            raise TypeError("execution must be an Execution")
        self._execution = execution.start()
        self._storage = storage
        self._cleanups: list[Callable[[], None]] = []
        self._released = False
        self._storage.save_execution(self._execution)

    @classmethod
    def resume(
        cls,
        execution: Execution,
        storage: ExecutionControlStorage,
    ) -> ExecutionController:
        """Continue a persisted non-terminal execution without restarting it."""
        if not isinstance(execution, Execution):
            raise TypeError("execution must be an Execution")
        if execution.status.is_terminal:
            raise ExecutionControlError("terminal execution cannot be resumed")
        if execution.status is not ExecutionStatus.RUNNING:
            raise ExecutionControlError("only a running execution can be resumed")
        controller = cls.__new__(cls)
        controller._execution = execution
        controller._storage = storage
        controller._cleanups = []
        controller._released = False
        return controller

    @property
    def execution(self) -> Execution:
        """Return the latest immutable execution snapshot."""
        return self._execution

    def register_cleanup(self, cleanup: Callable[[], None]) -> None:
        """Register one lock or temporary-resource release operation."""
        if self._execution.status.is_terminal:
            raise ExecutionControlError("terminal execution cannot acquire resources")
        if not callable(cleanup):
            raise TypeError("cleanup must be callable")
        self._cleanups.append(cleanup)

    def complete_stage(
        self,
        next_stage: ExecutionStage,
        diagnostics: DiagnosticCollection | None = None,
    ) -> Execution:
        """Persist the completed stage before advancing the execution."""
        diagnostics = diagnostics or DiagnosticCollection()
        self._require_diagnostics(diagnostics)
        self._storage.save_stage_diagnostics(
            StageDiagnostics(
                self._execution.execution_id,
                self._execution.stage,
                StageOutcome.COMPLETED,
                diagnostics,
            )
        )
        self._execution = self._execution.advance(next_stage)
        self._storage.save_execution(self._execution)
        if self._execution.status.is_terminal:
            self._release()
        return self._execution

    def cancel(
        self,
        *,
        provider: ProviderPort | None = None,
        request_id: InferenceRequestId | None = None,
    ) -> CancellationResult | None:
        """Cancel execution and propagate to a supporting active provider."""
        if self._execution.status.is_terminal:
            raise ExecutionControlError("execution is already terminal")
        if (provider is None) != (request_id is None):
            raise ValueError("provider and request_id must be supplied together")

        cancellation: CancellationResult | None = None
        if provider is not None and request_id is not None:
            supported = provider.get_capabilities().supported_operations
            cancellation = (
                provider.cancel(request_id)
                if ProviderOperation.CANCEL in supported
                else CancellationResult(request_id, CancellationStatus.NOT_SUPPORTED)
            )
        self._execution = self._execution.cancel()
        cleanup_diagnostics = self._release()
        diagnostics = cleanup_diagnostics
        if cancellation is not None:
            diagnostics = diagnostics.with_diagnostic(
                Diagnostic(
                    DiagnosticCode("EXECUTION_PROVIDER_CANCELLATION"),
                    DiagnosticSeverity.INFO,
                    f"Provider cancellation result: {cancellation.status.value}.",
                    "execution",
                )
            )
        self._storage.save_stage_diagnostics(
            StageDiagnostics(
                self._execution.execution_id,
                self._execution.stage,
                StageOutcome.CANCELLED,
                diagnostics,
            )
        )
        self._storage.save_execution(self._execution)
        return cancellation

    def fail(self, diagnostics: DiagnosticCollection) -> Execution:
        """Persist failure diagnostics and release every registered resource."""
        self._require_diagnostics(diagnostics)
        self._execution = self._execution.fail()
        merged = DiagnosticCollection((*diagnostics, *self._release()))
        self._storage.save_stage_diagnostics(
            StageDiagnostics(
                self._execution.execution_id,
                self._execution.stage,
                StageOutcome.FAILED,
                merged,
            )
        )
        self._storage.save_execution(self._execution)
        return self._execution

    def _release(self) -> DiagnosticCollection:
        if self._released:
            return DiagnosticCollection()
        self._released = True
        diagnostics: list[Diagnostic] = []
        for cleanup in reversed(self._cleanups):
            try:
                cleanup()
            except Exception as error:
                diagnostics.append(
                    Diagnostic(
                        DiagnosticCode("EXECUTION_RESOURCE_RELEASE_FAILED"),
                        DiagnosticSeverity.ERROR,
                        "An execution resource could not be released.",
                        "execution",
                        technical_details=str(error),
                    )
                )
        self._cleanups.clear()
        return DiagnosticCollection(tuple(diagnostics))

    @staticmethod
    def _require_diagnostics(diagnostics: DiagnosticCollection) -> None:
        if not isinstance(diagnostics, DiagnosticCollection):
            raise TypeError("diagnostics must be a DiagnosticCollection")
