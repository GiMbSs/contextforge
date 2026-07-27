"""Tests for the OllamaProvider implementing the Provider Port."""

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from contextforge.adapters.providers import (
    _DEFAULT_OLLAMA_MODEL,
    HttpResponse,
    OllamaProvider,
)
from contextforge.configuration import ProviderConfig
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
    ProviderExecutionMode,
    ProviderFinishState,
    ProviderHealthStatus,
    ProviderOperationNotSupportedError,
    ProviderPort,
    ProviderRequestFeature,
    ProviderResponseFormat,
)

NOW = datetime(2026, 7, 26, tzinfo=UTC)


@dataclass
class _MockTransport:
    response: HttpResponse | BaseException

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None,
        headers: tuple[tuple[str, str], ...],
        timeout_seconds: float,
    ) -> HttpResponse:
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


def _config(**overrides: object) -> ProviderConfig:
    defaults = {
        "provider_id": "ollama",
        "model_id": "code-model:latest",
        "endpoint": "http://localhost:11434",
        "execution_mode": "local",
        "timeout_seconds": 5.0,
    }
    defaults.update(overrides)
    return ProviderConfig(**defaults)  # type: ignore[arg-type]


def _provider(config: ProviderConfig | None = None) -> OllamaProvider:
    return OllamaProvider(
        config=config or _config(),
        transport=_MockTransport(HttpResponse(200, b'{"version":"0.9.1"}')),
    )


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
        ),
        analysis_response_contract(),
        DeliveryRequirements(structured_output_required=True),
        PromptMeasurements(100, 100, 1, 25, 10, 10, 60, 20, 1, 1, 0),
        DiagnosticCollection(),  # type: ignore[name-defined]
        NOW,
        maximum_output_tokens=200,
        temperature=0,
    )


def test_provider_implements_provider_port() -> None:
    provider: ProviderPort = _provider()
    assert provider.get_capabilities().provider_id == "ollama-local"


def test_capabilities_report_local_execution_mode_by_default() -> None:
    provider = _provider()
    capabilities = provider.get_capabilities()

    assert capabilities.execution_mode is ProviderExecutionMode.LOCAL
    assert capabilities.structured_output_supported
    assert capabilities.health_check_supported
    assert capabilities.model_discovery_supported
    assert ProviderRequestFeature.SYSTEM_ROLE in capabilities.supported_request_features
    assert ProviderResponseFormat.JSON_TEXT in capabilities.supported_response_formats


def test_capabilities_report_remote_execution_mode_when_configured() -> None:
    provider = _provider(_config(execution_mode="remote"))
    capabilities = provider.get_capabilities()

    assert capabilities.execution_mode is ProviderExecutionMode.REMOTE


def test_health_check_uses_discovery_adapter() -> None:
    provider = _provider()
    health = provider.health_check()

    assert health.status is ProviderHealthStatus.HEALTHY
    assert "0.9.1" in (health.message or "")


def test_list_models_normalizes_models() -> None:
    body = b'{"models":[{"name":"alpha:7b"},{"name":"zeta:latest"}]}'
    provider = OllamaProvider(
        config=_config(),
        transport=_MockTransport(HttpResponse(200, body)),
    )

    models = provider.list_models()

    assert tuple(model.model_id for model in models) == ("alpha:7b", "zeta:latest")


def test_invoke_translates_and_returns_normalized_response() -> None:
    body = (
        b'{"model":"code-model:latest","message":{"content":"{\\"summary\\":\\"ok\\"}"},'
        b'"done":true,"prompt_eval_count":10,"eval_count":5}'
    )
    provider = OllamaProvider(
        config=_config(),
        transport=_MockTransport(HttpResponse(200, body)),
    )
    request = _request()

    response = provider.invoke(request, ProviderExecutionContext("execution-1"))

    assert response.request_id == request.request_id
    assert response.task_id == request.task_id
    assert response.finish_state is ProviderFinishState.COMPLETED
    assert '"summary":"ok"' in response.content


def test_invoke_uses_default_model_when_model_id_is_unset() -> None:
    config = _config(model_id=None)
    provider = OllamaProvider(
        config=config,
        transport=_MockTransport(HttpResponse(200, b'{"done":true}')),
    )

    assert provider._model_id == _DEFAULT_OLLAMA_MODEL


def test_cancel_is_not_supported() -> None:
    provider = _provider()
    with pytest.raises(ProviderOperationNotSupportedError):
        provider.cancel(new_inference_request_id())


def test_from_config_builds_httpx_transport() -> None:
    config = _config(endpoint="http://ollama.example.com:11434", timeout_seconds=10.0)
    provider = OllamaProvider.from_config(config)

    assert isinstance(provider, OllamaProvider)
    assert provider.config.endpoint == "http://ollama.example.com:11434"


def test_from_config_raises_clear_error_when_httpx_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins

    original_import = builtins.__import__

    def _fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "httpx":
            raise ImportError("No module named 'httpx'")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    with pytest.raises(RuntimeError, match="httpx"):
        OllamaProvider.from_config(_config())


def test_provider_rejects_invalid_transport() -> None:
    with pytest.raises(TypeError, match="transport must be an OllamaHttpTransport"):
        OllamaProvider(config=_config(), transport="not-a-transport")  # type: ignore[arg-type]


def test_provider_repr_does_not_expose_secrets() -> None:
    provider = _provider(_config(endpoint="http://localhost:11434", model_id="x"))
    representation = repr(provider)

    assert "OllamaProvider" in representation
    assert "localhost" in representation
    assert "x" in representation
