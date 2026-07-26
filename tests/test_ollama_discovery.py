"""Tests for Ollama-compatible health and model discovery."""

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from contextforge.adapters.providers import (
    HttpResponse,
    OllamaDiscoveryAdapter,
    OllamaDiscoveryError,
)
from contextforge.provider import ProviderHealthStatus

NOW = datetime(2026, 7, 26, tzinfo=UTC)


@dataclass
class MockTransport:
    responses: dict[str, HttpResponse | BaseException]

    def __post_init__(self) -> None:
        self.requests: list[tuple[str, str, bytes | None, tuple[tuple[str, str], ...], float]] = []

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
        result = self.responses[path]
        if isinstance(result, BaseException):
            raise result
        return result


def test_health_check_uses_bounded_read_only_version_request() -> None:
    transport = MockTransport({"/api/version": HttpResponse(200, b'{"version":"0.9.1"}')})

    health = OllamaDiscoveryAdapter(transport, 2.5, NOW).health_check()

    assert health.status is ProviderHealthStatus.HEALTHY
    assert "0.9.1" in (health.message or "")
    assert transport.requests == [
        (
            "GET",
            "/api/version",
            None,
            (("Accept", "application/json"),),
            2.5,
        )
    ]


def test_health_transport_error_is_sanitized() -> None:
    transport = MockTransport({"/api/version": OSError("secret endpoint and credential")})

    health = OllamaDiscoveryAdapter(transport, 1, NOW).health_check()

    assert health.status is ProviderHealthStatus.UNAVAILABLE
    assert "secret" not in (health.message or "")
    assert "credential" not in (health.message or "")


def test_model_discovery_normalizes_and_sorts_models() -> None:
    body = b"""{
      "models": [
        {"name":"zeta:latest","digest":"abc","size":42},
        {"model":"alpha:7b","modified_at":"2026-01-01","details":{"family":"alpha"}}
      ]
    }"""
    transport = MockTransport({"/api/tags": HttpResponse(200, body)})

    models = OllamaDiscoveryAdapter(transport, 3, NOW).list_models()

    assert tuple(model.model_id for model in models) == ("alpha:7b", "zeta:latest")
    assert dict(models[0].metadata)["family"] == "alpha"
    assert transport.requests[0][2] is None


def test_model_discovery_rejects_malformed_response() -> None:
    transport = MockTransport({"/api/tags": HttpResponse(200, b'{"models":"bad"}')})

    with pytest.raises(OllamaDiscoveryError, match="model list is invalid"):
        OllamaDiscoveryAdapter(transport, 3, NOW).list_models()


def test_model_discovery_never_leaks_transport_error() -> None:
    transport = MockTransport({"/api/tags": TimeoutError("api_key=secret")})

    with pytest.raises(OllamaDiscoveryError) as captured:
        OllamaDiscoveryAdapter(transport, 3, NOW).list_models()

    assert "api_key" not in str(captured.value)
    assert "secret" not in str(captured.value)
