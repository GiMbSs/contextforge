"""Ollama-compatible non-streaming inference invocation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from contextforge.adapters.providers.ollama import (
    HttpResponse,
    OllamaDiscoveryError,
    OllamaHttpTransport,
)
from contextforge.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticCollection,
    DiagnosticSeverity,
)
from contextforge.domain import InferenceRequestId, InferenceResponseId
from contextforge.prompt import InferenceRequest, ResponseFormat
from contextforge.provider import (
    InferenceResponse,
    ProviderExecutionContext,
    ProviderExecutionMeasurements,
    ProviderFailure,
    ProviderFailureCategory,
    ProviderFinishState,
    ProviderInvocationError,
    ProviderResponseFormat,
    ProviderResponseMetadata,
    ProviderUsage,
)

OLLAMA_PROVIDER_ID = "ollama-local"
OLLAMA_ADAPTER_ID = "ollama-http"
OLLAMA_ADAPTER_VERSION = "1"
OLLAMA_CAPABILITY_PROFILE_ID = "ollama-compatible-v1"


@dataclass(frozen=True, slots=True)
class OllamaInvocationAdapter:
    """Translate and invoke one request without fallback or tool execution."""

    transport: OllamaHttpTransport
    model_id: str
    timeout_seconds: float
    invoked_at: datetime
    completed_at: datetime
    provider_id: str = OLLAMA_PROVIDER_ID
    adapter_id: str = OLLAMA_ADAPTER_ID
    adapter_version: str = OLLAMA_ADAPTER_VERSION
    capability_profile_id: str = OLLAMA_CAPABILITY_PROFILE_ID

    def __post_init__(self) -> None:
        for field_name in (
            "model_id",
            "provider_id",
            "adapter_id",
            "adapter_version",
            "capability_profile_id",
        ):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must not be empty")
        if not isinstance(self.timeout_seconds, (int, float)):
            raise TypeError("timeout_seconds must be numeric")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        for field_name in ("invoked_at", "completed_at"):
            value = getattr(self, field_name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field_name} must be timezone-aware")
        if self.completed_at < self.invoked_at:
            raise ValueError("completed_at must not precede invoked_at")

    def invoke(
        self,
        request: InferenceRequest,
        execution_context: ProviderExecutionContext,
    ) -> InferenceResponse:
        """Perform exactly one bounded `/api/chat` invocation."""
        if not isinstance(request, InferenceRequest):
            raise TypeError("request must be an InferenceRequest")
        if not isinstance(execution_context, ProviderExecutionContext):
            raise TypeError("execution_context must be a ProviderExecutionContext")

        body = _request_body(request, self.model_id)
        try:
            response = self.transport.request(
                "POST",
                "/api/chat",
                body=body,
                headers=(
                    ("Accept", "application/json"),
                    ("Content-Type", "application/json"),
                ),
                timeout_seconds=float(self.timeout_seconds),
            )
        except TimeoutError as error:
            raise self._failure(
                request,
                ProviderFailureCategory.TIMEOUT,
                "Ollama-compatible invocation timed out.",
                True,
                "PROVIDER_TIMEOUT",
            ) from error
        except OSError as error:
            raise self._failure(
                request,
                ProviderFailureCategory.PROVIDER_UNAVAILABLE,
                "Ollama-compatible provider is unavailable.",
                True,
                "PROVIDER_UNAVAILABLE",
            ) from error
        if not isinstance(response, HttpResponse):
            raise TypeError("transport must return HttpResponse")
        if response.status_code != 200:
            raise self._failure(
                request,
                ProviderFailureCategory.RESPONSE_INVALID,
                f"Ollama-compatible invocation returned HTTP {response.status_code}.",
                False,
                "PROVIDER_REQUEST_REJECTED",
            )
        try:
            payload = _json_object(response.body)
            return self._normalize(request, execution_context, payload)
        except OllamaDiscoveryError as error:
            raise self._failure(
                request,
                ProviderFailureCategory.RESPONSE_INVALID,
                "Ollama-compatible provider returned an invalid response.",
                False,
                "PROVIDER_RESPONSE_INVALID",
            ) from error

    def _normalize(
        self,
        request: InferenceRequest,
        execution_context: ProviderExecutionContext,
        payload: dict[str, object],
    ) -> InferenceResponse:
        message = payload.get("message")
        if not isinstance(message, dict):
            raise OllamaDiscoveryError("Ollama response message is missing.")
        content = message.get("content")
        if not isinstance(content, str):
            raise OllamaDiscoveryError("Ollama response content is invalid.")
        tool_calls = message.get("tool_calls")
        diagnostics: list[Diagnostic] = []
        stop_reason: str | None = None
        done = payload.get("done")
        finish_state = (
            ProviderFinishState.COMPLETED if done is True else ProviderFinishState.PARTIAL
        )
        if done is not True:
            stop_reason = "incomplete_response"
            diagnostics.append(
                _diagnostic(
                    "PROVIDER_PARTIAL_RESPONSE",
                    "Ollama-compatible provider did not mark the response complete.",
                )
            )
        if tool_calls:
            finish_state = ProviderFinishState.PARTIAL
            stop_reason = "unexpected_tool_call"
            diagnostics.append(
                _diagnostic(
                    "PROVIDER_UNEXPECTED_TOOL_CALL",
                    "Provider requested an unsupported tool call; it was not executed.",
                )
            )
            if not content:
                content = json.dumps(
                    {"untrusted_tool_calls": tool_calls},
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )

        return InferenceResponse(
            _response_id(request.request_id),
            request.request_id,
            request.task_id,
            content,
            _response_format(request.response_contract.output_format),
            ProviderResponseMetadata(
                self.provider_id,
                self.adapter_id,
                self.adapter_version,
                _effective_model(payload, self.model_id),
                self.capability_profile_id,
                self.invoked_at,
                self.completed_at,
                retry_attempt=execution_context.retry_attempt,
            ),
            _usage(payload),
            ProviderExecutionMeasurements(
                _nanoseconds_to_milliseconds(payload.get("total_duration")) or 0,
                provider_duration_ms=_nanoseconds_to_milliseconds(payload.get("eval_duration")),
                retry_count=execution_context.retry_attempt,
            ),
            finish_state,
            DiagnosticCollection(tuple(diagnostics)),
            self.completed_at,
            stop_reason,
        )

    def _failure(
        self,
        request: InferenceRequest,
        category: ProviderFailureCategory,
        message: str,
        retryable: bool,
        code: str,
    ) -> ProviderInvocationError:
        digest = hashlib.sha256(f"{request.request_id}\0{category.value}".encode()).hexdigest()[:24]
        failure = ProviderFailure(
            f"provider_failure_{digest}",
            request.request_id,
            self.provider_id,
            self.adapter_id,
            self.model_id,
            category,
            message,
            retryable,
            DiagnosticCollection((_diagnostic(code, message),)),
            self.completed_at,
        )
        return ProviderInvocationError(failure)


def _request_body(request: InferenceRequest, model_id: str) -> bytes:
    payload: dict[str, object] = {
        "messages": [
            {"content": message.content, "role": message.role.value} for message in request.messages
        ],
        "model": model_id,
        "stream": False,
    }
    if request.response_contract.output_format in (
        ResponseFormat.JSON,
        ResponseFormat.STRUCTURED_PATCH,
    ):
        payload["format"] = "json"
    options: dict[str, object] = {}
    if request.temperature is not None:
        options["temperature"] = request.temperature
    if request.maximum_output_tokens is not None:
        options["num_predict"] = request.maximum_output_tokens
    if request.stop_conditions:
        options["stop"] = request.stop_conditions
    if options:
        payload["options"] = options
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _json_object(body: bytes) -> dict[str, object]:
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OllamaDiscoveryError("Ollama response is invalid JSON.") from error
    if not isinstance(value, dict):
        raise OllamaDiscoveryError("Ollama response must be a JSON object.")
    return value


def _usage(payload: dict[str, object]) -> ProviderUsage:
    input_tokens = _optional_nonnegative_int(payload.get("prompt_eval_count"))
    output_tokens = _optional_nonnegative_int(payload.get("eval_count"))
    total_tokens = (
        input_tokens + output_tokens
        if input_tokens is not None and output_tokens is not None
        else None
    )
    return ProviderUsage(input_tokens, output_tokens, total_tokens)


def _optional_nonnegative_int(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _nanoseconds_to_milliseconds(value: object) -> int | None:
    nanoseconds = _optional_nonnegative_int(value)
    return nanoseconds // 1_000_000 if nanoseconds is not None else None


def _effective_model(payload: dict[str, object], requested_model: str) -> str:
    model = payload.get("model")
    return model if isinstance(model, str) and model.strip() else requested_model


def _response_format(output_format: ResponseFormat) -> ProviderResponseFormat:
    return {
        ResponseFormat.TEXT: ProviderResponseFormat.PLAIN_TEXT,
        ResponseFormat.JSON: ProviderResponseFormat.JSON_TEXT,
        ResponseFormat.UNIFIED_DIFF: ProviderResponseFormat.PLAIN_TEXT,
        ResponseFormat.STRUCTURED_PATCH: ProviderResponseFormat.PATCH_ENVELOPE,
    }[output_format]


def _response_id(request_id: InferenceRequestId) -> InferenceResponseId:
    digest = hashlib.sha256(f"{request_id}\0ollama".encode()).hexdigest()[:32]
    return InferenceResponseId(f"inference_response_{digest}")


def _diagnostic(code: str, message: str) -> Diagnostic:
    return Diagnostic(
        DiagnosticCode(code),
        DiagnosticSeverity.WARNING,
        message,
        "ollama-provider",
    )
