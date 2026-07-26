"""Provider-independent contracts used by the Provider Port."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from contextforge.diagnostics import Diagnostic, DiagnosticCollection
from contextforge.domain import (
    InferenceRequestId,
    InferenceResponseId,
    TaskId,
)


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


class ProviderOperation(StrEnum):
    """Operations an adapter may advertise."""

    GET_CAPABILITIES = "get_capabilities"
    HEALTH_CHECK = "health_check"
    LIST_MODELS = "list_models"
    INVOKE = "invoke"
    CANCEL = "cancel"


class ProviderCapabilities(Protocol):
    """Minimum capability view required by the Provider Port."""

    @property
    def provider_id(self) -> str:
        """Stable configured provider identity."""
        ...

    @property
    def adapter_id(self) -> str:
        """Stable adapter implementation identity."""
        ...

    @property
    def supported_operations(self) -> tuple[ProviderOperation, ...]:
        """Operations this configuration supports."""
        ...


class ProviderHealthStatus(StrEnum):
    """Normalized provider health state."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    """Provider-neutral health-check result."""

    status: ProviderHealthStatus
    checked_at: datetime
    message: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ProviderHealthStatus):
            raise TypeError("status must be a ProviderHealthStatus")
        _require_aware(self.checked_at, "checked_at")
        if self.message is not None:
            _require_text(self.message, "message")


@dataclass(frozen=True, slots=True)
class ProviderModel:
    """One model reported by a provider without provider SDK types."""

    model_id: str
    display_name: str | None = None
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.model_id, "model_id")
        if self.display_name is not None:
            _require_text(self.display_name, "display_name")
        metadata = tuple(self.metadata)
        keys = tuple(key for key, _ in metadata)
        if any(not key.strip() or not value.strip() for key, value in metadata):
            raise ValueError("metadata must contain non-empty strings")
        if len(set(keys)) != len(keys):
            raise ValueError("metadata keys must be unique")
        object.__setattr__(self, "metadata", tuple(sorted(metadata)))


@dataclass(frozen=True, slots=True)
class ProviderExecutionContext:
    """Correlation and control data that contains no project content."""

    correlation_id: str
    retry_attempt: int = 0
    deadline: datetime | None = None
    trace_metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.correlation_id, "correlation_id")
        if type(self.retry_attempt) is not int:
            raise TypeError("retry_attempt must be an integer")
        if self.retry_attempt < 0:
            raise ValueError("retry_attempt must not be negative")
        if self.deadline is not None:
            _require_aware(self.deadline, "deadline")
        metadata = tuple(self.trace_metadata)
        keys = tuple(key for key, _ in metadata)
        if any(not key.strip() or not value.strip() for key, value in metadata):
            raise ValueError("trace_metadata must contain non-empty strings")
        if len(set(keys)) != len(keys):
            raise ValueError("trace_metadata keys must be unique")
        object.__setattr__(self, "trace_metadata", tuple(sorted(metadata)))


class ProviderResponseFormat(StrEnum):
    """Representation of returned content, not its correctness."""

    PLAIN_TEXT = "plain_text"
    JSON_TEXT = "json_text"
    STRUCTURED_OBJECT = "structured_object"
    PATCH_ENVELOPE = "patch_envelope"
    ANALYSIS_ENVELOPE = "analysis_envelope"
    UNKNOWN = "unknown"


class ProviderFinishState(StrEnum):
    """Normalized completion state of one invocation."""

    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    FAILED = "failed"


class ProviderFinishReason(StrEnum):
    """Provider-independent explanation for an invocation ending."""

    NATURAL_COMPLETION = "natural_completion"
    OUTPUT_LIMIT_REACHED = "output_limit_reached"
    STOP_SEQUENCE = "stop_sequence"
    CONTENT_FILTER = "content_filter"
    TOOL_CALL_REQUESTED = "tool_call_requested"
    PROVIDER_CANCELLATION = "provider_cancellation"
    CLIENT_CANCELLATION = "client_cancellation"
    TIMEOUT = "timeout"
    PROVIDER_ERROR = "provider_error"
    MALFORMED_OUTPUT = "malformed_output"
    STREAM_INTERRUPTED = "stream_interrupted"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ProviderDiagnostics:
    """Normalized immutable diagnostics associated with provider output."""

    collection: DiagnosticCollection = field(default_factory=DiagnosticCollection)

    def __post_init__(self) -> None:
        if not isinstance(self.collection, DiagnosticCollection):
            raise TypeError("collection must be a DiagnosticCollection")

    def __iter__(self) -> Iterator[Diagnostic]:
        return iter(self.collection)

    def __len__(self) -> int:
        return len(self.collection)

    def with_diagnostic(self, diagnostic: Diagnostic) -> ProviderDiagnostics:
        """Return diagnostics with one additional normalized item."""
        return ProviderDiagnostics(self.collection.with_diagnostic(diagnostic))


@dataclass(frozen=True, slots=True)
class ProviderUsage:
    """Usage values reported by a provider; absent means unknown."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    input_bytes: int | None = None
    output_bytes: int | None = None
    values_are_estimates: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "input_bytes",
            "output_bytes",
        ):
            value = getattr(self, field_name)
            if value is not None:
                if type(value) is not int:
                    raise TypeError(f"{field_name} must be an integer")
                if value < 0:
                    raise ValueError(f"{field_name} must not be negative")
        if (
            self.total_tokens is not None
            and self.input_tokens is not None
            and self.output_tokens is not None
            and self.total_tokens != self.input_tokens + self.output_tokens
        ):
            raise ValueError("total_tokens must equal input_tokens plus output_tokens")
        if type(self.values_are_estimates) is not bool:
            raise TypeError("values_are_estimates must be a boolean")


@dataclass(frozen=True, slots=True)
class ProviderExecutionMeasurements:
    """Non-semantic provider execution timings in milliseconds."""

    total_duration_ms: int
    connection_duration_ms: int | None = None
    provider_duration_ms: int | None = None
    retry_count: int = 0

    def __post_init__(self) -> None:
        for field_name in self.__dataclass_fields__:
            value = getattr(self, field_name)
            if value is not None:
                if type(value) is not int:
                    raise TypeError("Execution measurements must be integers")
                if value < 0:
                    raise ValueError("Execution measurements must not be negative")


@dataclass(frozen=True, slots=True)
class ProviderResponseMetadata:
    """Identities and timestamps describing the effective invocation."""

    provider_id: str
    adapter_id: str
    adapter_version: str
    model_id: str
    capability_profile_id: str
    invoked_at: datetime
    completed_at: datetime
    provider_request_id: str | None = None
    retry_attempt: int = 0

    def __post_init__(self) -> None:
        for field_name in (
            "provider_id",
            "adapter_id",
            "adapter_version",
            "model_id",
            "capability_profile_id",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_aware(self.invoked_at, "invoked_at")
        _require_aware(self.completed_at, "completed_at")
        if self.completed_at < self.invoked_at:
            raise ValueError("completed_at must not precede invoked_at")
        if self.provider_request_id is not None:
            _require_text(self.provider_request_id, "provider_request_id")
        if type(self.retry_attempt) is not int:
            raise TypeError("retry_attempt must be an integer")
        if self.retry_attempt < 0:
            raise ValueError("retry_attempt must not be negative")


@dataclass(frozen=True, slots=True)
class InferenceResponse:
    """Normalized immutable result returned through the Provider Port."""

    response_id: InferenceResponseId
    request_id: InferenceRequestId
    task_id: TaskId
    content: str
    response_format: ProviderResponseFormat
    metadata: ProviderResponseMetadata
    usage: ProviderUsage | None
    measurements: ProviderExecutionMeasurements
    finish_state: ProviderFinishState
    diagnostics: ProviderDiagnostics
    created_at: datetime
    finish_reason: ProviderFinishReason = ProviderFinishReason.UNKNOWN
    provider_stop_reason: str | None = None
    raw_response: bytes | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.response_id, InferenceResponseId):
            raise TypeError("response_id must be an InferenceResponseId")
        if not isinstance(self.request_id, InferenceRequestId):
            raise TypeError("request_id must be an InferenceRequestId")
        if not isinstance(self.task_id, TaskId):
            raise TypeError("task_id must be a TaskId")
        if not isinstance(self.content, str):
            raise TypeError("content must be a string")
        if not isinstance(self.response_format, ProviderResponseFormat):
            raise TypeError("response_format must be a ProviderResponseFormat")
        if not isinstance(self.metadata, ProviderResponseMetadata):
            raise TypeError("metadata must be ProviderResponseMetadata")
        if self.usage is not None and not isinstance(self.usage, ProviderUsage):
            raise TypeError("usage must be ProviderUsage or None")
        if not isinstance(self.measurements, ProviderExecutionMeasurements):
            raise TypeError("measurements must be ProviderExecutionMeasurements")
        if not isinstance(self.finish_state, ProviderFinishState):
            raise TypeError("finish_state must be a ProviderFinishState")
        if not isinstance(self.diagnostics, ProviderDiagnostics):
            raise TypeError("diagnostics must be ProviderDiagnostics")
        _require_aware(self.created_at, "created_at")
        if not isinstance(self.finish_reason, ProviderFinishReason):
            raise TypeError("finish_reason must be a ProviderFinishReason")
        if self.provider_stop_reason is not None:
            _require_text(self.provider_stop_reason, "provider_stop_reason")
        if self.raw_response is not None and not isinstance(self.raw_response, bytes):
            raise TypeError("raw_response must be bytes")
        if self.finish_state is ProviderFinishState.PARTIAL and self.finish_reason in (
            ProviderFinishReason.NATURAL_COMPLETION,
            ProviderFinishReason.UNKNOWN,
        ):
            raise ValueError("Partial responses require an incomplete finish reason")
        if self.finish_state is ProviderFinishState.CANCELLED and self.finish_reason not in (
            ProviderFinishReason.CLIENT_CANCELLATION,
            ProviderFinishReason.PROVIDER_CANCELLATION,
        ):
            raise ValueError("Cancelled responses require a cancellation finish reason")
        if (
            self.finish_state is ProviderFinishState.TIMED_OUT
            and self.finish_reason is not ProviderFinishReason.TIMEOUT
        ):
            raise ValueError("Timed-out responses require the timeout finish reason")


class CancellationStatus(StrEnum):
    """Normalized result of a cancellation request."""

    CANCELLED = "cancelled"
    ALREADY_FINISHED = "already_finished"
    NOT_FOUND = "not_found"
    NOT_SUPPORTED = "not_supported"


@dataclass(frozen=True, slots=True)
class CancellationResult:
    """Outcome of a provider cancellation request."""

    request_id: InferenceRequestId
    status: CancellationStatus
    message: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, InferenceRequestId):
            raise TypeError("request_id must be an InferenceRequestId")
        if not isinstance(self.status, CancellationStatus):
            raise TypeError("status must be a CancellationStatus")
        if self.message is not None:
            _require_text(self.message, "message")


class ProviderOperationNotSupportedError(RuntimeError):
    """An optional Provider Port operation is not advertised."""
