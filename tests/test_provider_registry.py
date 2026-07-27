"""Tests for the configured provider registry."""

from datetime import UTC, datetime

import pytest

from contextforge.adapters.providers import (
    _DEFAULT_OLLAMA_MODEL,
    ConfiguredProviderRegistry,
    OllamaProvider,
    ProviderNotFoundError,
)
from contextforge.configuration import ProviderConfig
from contextforge.provider import (
    MOCK_PROVIDER_ID,
    DeterministicMockProvider,
    ProviderPort,
)

NOW = datetime(2026, 7, 26, tzinfo=UTC)


def test_registry_returns_mock_provider_by_default() -> None:
    registry = ConfiguredProviderRegistry(ProviderConfig())

    provider = registry.get(MOCK_PROVIDER_ID)

    assert isinstance(provider, DeterministicMockProvider)


def test_registry_returns_ollama_provider_when_configured() -> None:
    config = ProviderConfig(
        provider_id="ollama",
        model_id="llama3.1:8b",
        execution_mode="local",
    )
    registry = ConfiguredProviderRegistry(config)

    provider = registry.get("ollama")

    assert isinstance(provider, OllamaProvider)


def test_registry_provider_ids_reflects_configured_provider() -> None:
    config = ProviderConfig(provider_id="ollama", execution_mode="local")
    registry = ConfiguredProviderRegistry(config)

    assert registry.provider_ids == ("ollama",)


def test_registry_returns_none_for_unknown_provider() -> None:
    registry = ConfiguredProviderRegistry(ProviderConfig())

    assert registry.get("unknown-provider") is None


def test_registry_raises_for_required_unknown_provider() -> None:
    registry = ConfiguredProviderRegistry(ProviderConfig())

    with pytest.raises(ProviderNotFoundError):
        registry.get_required("unknown-provider")


def test_registry_ollama_provider_uses_default_model() -> None:
    config = ProviderConfig(provider_id="ollama", execution_mode="local", model_id=None)
    registry = ConfiguredProviderRegistry(config)
    provider = registry.get("ollama")

    assert isinstance(provider, OllamaProvider)
    assert provider._model_id == _DEFAULT_OLLAMA_MODEL


def test_registry_validates_config_type() -> None:
    with pytest.raises(TypeError, match="config must be a ProviderConfig"):
        ConfiguredProviderRegistry("not-a-config")  # type: ignore[arg-type]


def test_registry_get_required_returns_provider() -> None:
    registry = ConfiguredProviderRegistry(ProviderConfig())

    provider = registry.get_required(MOCK_PROVIDER_ID)

    assert isinstance(provider, ProviderPort)
