"""Tests for Ollama-compatible invocation through mocked transport."""

import json
from datetime import UTC, datetime

import pytest

from contextforge.adapters.providers import (
    HttpResponse,
    OllamaInvocationAdapter,
)
from contextforge.diagnostics import DiagnosticCollection
from contextforge.domain import (
    FingerprintOrdering,
    fingerprint_project,
    new_context_bundle_id,
    new_inference_request_id,
    new_project_id,
    new_task_id,
)
from contextforge.prompt import (
    DeliveryRequirements,
    InferenceRequest,
    PromptMeasurements,
    PromptMessage,
    PromptRole,
    PromptTrust,
    analysis_response_contract,
)
from contextforge.provider import (
    ProviderExecutionContext,
    ProviderFinishReason,
    ProviderFinishState,
    ProviderInvocationError,
)

NOW = datetime(2026, 7, 26, tzinfo=UTC)


class RecordingTransport:
    def __init__(self, result: HttpResponse | BaseException) -> None:
        self.result = result
        self.requests: list[tuple[object, ...]] = []

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None,
        headers: tuple[tuple[str, str], ...],
        timeout_seconds: float,
    ) -> HttpResponse:
        self.requests.append((method, path, body, headers, timeout_seconds))
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def _request() -> InferenceRequest:
    return InferenceRequest(
        new_inference_request_id(),
        new_task_id(),
        new_context_bundle_id(),
        new_project_id(),
        fingerprint_project(("project",), ordering=FingerprintOrdering.ORDERED),
        "template-v1",
        (
            PromptMessage(
                "system",
                0,
                PromptRole.SYSTEM,
                PromptTrust.TRUSTED,
                "Follow rules.",
            ),
            PromptMessage(
                "context",
                1,
                PromptRole.USER,
                PromptTrust.UNTRUSTED,
                "Project context.",
            ),
        ),
        analysis_response_contract(),
        DeliveryRequirements(structured_output_required=True),
        PromptMeasurements(100, 100, 2, 25, 10, 10, 60, 20, 1, 1, 0),
        DiagnosticCollection(),
        NOW,
        maximum_output_tokens=200,
        temperature=0,
        stop_conditions=("END",),
    )


def _adapter(transport: RecordingTransport) -> OllamaInvocationAdapter:
    return OllamaInvocationAdapter(transport, "code-model:latest", 7.5, NOW, NOW)


def test_invocation_translates_messages_with_explicit_timeout_once() -> None:
    transport = RecordingTransport(
        HttpResponse(
            200,
            b'{"model":"code-model:latest","message":{"content":"{\\"summary\\":\\"ok\\"}"},'
            b'"done":true,"prompt_eval_count":10,"eval_count":5}',
        )
    )
    request = _request()

    response = _adapter(transport).invoke(
        request,
        ProviderExecutionContext("execution-1"),
    )

    assert response.request_id == request.request_id
    assert response.task_id == request.task_id
    assert len(transport.requests) == 1
    method, path, body, _, timeout = transport.requests[0]
    assert (method, path, timeout) == ("POST", "/api/chat", 7.5)
    assert isinstance(body, bytes)
    payload = json.loads(body)
    assert payload["stream"] is False
    assert payload["format"] == "json"
    assert payload["messages"][1]["content"] == "Project context."
    assert payload["options"] == {
        "num_predict": 200,
        "stop": ["END"],
        "temperature": 0,
    }


def test_transport_errors_are_sanitized_without_implicit_fallback() -> None:
    transport = RecordingTransport(TimeoutError("endpoint=https://secret token=credential"))

    with pytest.raises(ProviderInvocationError) as captured:
        _adapter(transport).invoke(
            _request(),
            ProviderExecutionContext("execution-1"),
        )

    assert len(transport.requests) == 1
    assert captured.value.failure.retryable
    assert "secret" not in str(captured.value)
    assert "credential" not in str(captured.value)


def test_unexpected_tool_calls_are_not_executed() -> None:
    body = json.dumps(
        {
            "message": {
                "content": "",
                "tool_calls": [{"function": {"name": "shell", "arguments": {"command": "danger"}}}],
            },
            "done": True,
        }
    ).encode()
    transport = RecordingTransport(HttpResponse(200, body))

    response = _adapter(transport).invoke(
        _request(),
        ProviderExecutionContext("execution-1"),
    )

    assert response.finish_state is ProviderFinishState.PARTIAL
    assert response.finish_reason is ProviderFinishReason.TOOL_CALL_REQUESTED
    assert "untrusted_tool_calls" in response.content
    assert "danger" in response.content
    assert len(transport.requests) == 1


def test_missing_usage_remains_unavailable() -> None:
    transport = RecordingTransport(HttpResponse(200, b'{"message":{"content":"ok"},"done":true}'))

    response = _adapter(transport).invoke(
        _request(),
        ProviderExecutionContext("execution-1"),
    )

    assert response.usage is None


def test_malformed_response_becomes_sanitized_normalized_failure() -> None:
    transport = RecordingTransport(HttpResponse(200, b'{"message":'))

    with pytest.raises(ProviderInvocationError) as captured:
        _adapter(transport).invoke(
            _request(),
            ProviderExecutionContext("execution-1"),
        )

    assert not captured.value.failure.retryable
    assert "invalid response" in str(captured.value)
