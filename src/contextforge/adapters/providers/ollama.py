"""Ollama-compatible health and model discovery adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from contextforge.provider import (
    ProviderHealth,
    ProviderHealthStatus,
    ProviderModel,
)


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """Minimal transport response independent of an HTTP library."""

    status_code: int
    body: bytes

    def __post_init__(self) -> None:
        if type(self.status_code) is not int:
            raise TypeError("status_code must be an integer")
        if not 100 <= self.status_code <= 599:
            raise ValueError("status_code must be a valid HTTP status")
        if not isinstance(self.body, bytes):
            raise TypeError("body must be bytes")


@runtime_checkable
class OllamaHttpTransport(Protocol):
    """Injected HTTP boundary used by Ollama-compatible adapters."""

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None,
        headers: tuple[tuple[str, str], ...],
        timeout_seconds: float,
    ) -> HttpResponse:
        """Execute one bounded request."""
        ...


class OllamaDiscoveryError(RuntimeError):
    """Model discovery failed without exposing raw transport details."""


@dataclass(frozen=True, slots=True)
class OllamaDiscoveryAdapter:
    """Perform read-only health and model discovery through injected transport."""

    transport: OllamaHttpTransport
    timeout_seconds: float
    checked_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.timeout_seconds, (int, float)):
            raise TypeError("timeout_seconds must be numeric")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.checked_at.tzinfo is None or self.checked_at.utcoffset() is None:
            raise ValueError("checked_at must be timezone-aware")

    def health_check(self) -> ProviderHealth:
        """Check the version endpoint without transmitting project content."""
        try:
            response = self._get("/api/version")
        except (OSError, TimeoutError):
            return ProviderHealth(
                ProviderHealthStatus.UNAVAILABLE,
                self.checked_at,
                "Ollama-compatible provider is unavailable.",
            )
        if response.status_code != 200:
            return ProviderHealth(
                ProviderHealthStatus.UNAVAILABLE,
                self.checked_at,
                f"Ollama-compatible health check returned HTTP {response.status_code}.",
            )
        try:
            payload = _json_object(response.body)
        except OllamaDiscoveryError:
            return ProviderHealth(
                ProviderHealthStatus.DEGRADED,
                self.checked_at,
                "Ollama-compatible provider returned invalid health metadata.",
            )
        version = payload.get("version")
        if not isinstance(version, str) or not version.strip():
            return ProviderHealth(
                ProviderHealthStatus.DEGRADED,
                self.checked_at,
                "Ollama-compatible provider omitted its version.",
            )
        return ProviderHealth(
            ProviderHealthStatus.HEALTHY,
            self.checked_at,
            f"Ollama-compatible provider version {version}.",
        )

    def list_models(self) -> tuple[ProviderModel, ...]:
        """List installed models without triggering model downloads."""
        try:
            response = self._get("/api/tags")
        except (OSError, TimeoutError) as error:
            raise OllamaDiscoveryError(
                "Ollama-compatible model discovery is unavailable."
            ) from error
        if response.status_code != 200:
            raise OllamaDiscoveryError(
                f"Ollama-compatible model discovery returned HTTP {response.status_code}."
            )
        payload = _json_object(response.body)
        raw_models = payload.get("models")
        if not isinstance(raw_models, list):
            raise OllamaDiscoveryError("Ollama-compatible model list is invalid.")

        models = tuple(_model(item) for item in raw_models)
        model_ids = tuple(model.model_id for model in models)
        if len(set(model_ids)) != len(model_ids):
            raise OllamaDiscoveryError("Ollama-compatible model list contains duplicates.")
        return tuple(sorted(models, key=lambda model: model.model_id.casefold()))

    def _get(self, path: str) -> HttpResponse:
        response = self.transport.request(
            "GET",
            path,
            body=None,
            headers=(("Accept", "application/json"),),
            timeout_seconds=float(self.timeout_seconds),
        )
        if not isinstance(response, HttpResponse):
            raise TypeError("transport must return HttpResponse")
        return response


def _json_object(body: bytes) -> dict[str, object]:
    try:
        decoded = body.decode("utf-8")
        payload = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OllamaDiscoveryError("Ollama-compatible response is not valid JSON.") from error
    if not isinstance(payload, dict):
        raise OllamaDiscoveryError("Ollama-compatible response must be a JSON object.")
    return payload


def _model(value: object) -> ProviderModel:
    if not isinstance(value, dict):
        raise OllamaDiscoveryError("Ollama-compatible model entry is invalid.")
    model_id = value.get("model", value.get("name"))
    if not isinstance(model_id, str) or not model_id.strip():
        raise OllamaDiscoveryError("Ollama-compatible model entry has no identifier.")
    metadata: list[tuple[str, str]] = []
    for key in ("digest", "modified_at", "size"):
        item = value.get(key)
        if isinstance(item, (str, int)):
            metadata.append((key, str(item)))
    details = value.get("details")
    if isinstance(details, dict):
        family = details.get("family")
        if isinstance(family, str) and family.strip():
            metadata.append(("family", family))
    return ProviderModel(model_id, metadata=tuple(metadata))
