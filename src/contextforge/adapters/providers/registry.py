"""Provider registry that resolves configured providers through adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from contextforge.adapters.providers.ollama_provider import OllamaProvider
from contextforge.configuration import ProviderConfig
from contextforge.provider import (
    MOCK_PROVIDER_ID,
    DeterministicMockProvider,
    MockProviderScenario,
    ProviderPort,
)


class ProviderNotFoundError(LookupError):
    """The requested provider identifier is not available."""


@dataclass(frozen=True, slots=True)
class ConfiguredProviderRegistry:
    """Resolve providers from a validated configuration snapshot."""

    config: ProviderConfig
    mock_scenario: MockProviderScenario = MockProviderScenario.SUCCESSFUL_ANALYSIS

    def __post_init__(self) -> None:
        if not isinstance(self.config, ProviderConfig):
            raise TypeError("config must be a ProviderConfig")
        if not isinstance(self.mock_scenario, MockProviderScenario):
            raise TypeError("mock_scenario must be a MockProviderScenario")

    @property
    def provider_ids(self) -> tuple[str, ...]:
        """Return identifiers that are reachable from this configuration."""
        return (self.config.provider_id,)

    def get(self, provider_id: str) -> ProviderPort | None:
        """Return the configured provider, or None if unknown."""
        if provider_id == MOCK_PROVIDER_ID:
            return DeterministicMockProvider(
                self.mock_scenario,
                datetime.now(UTC),
            )
        if provider_id == self.config.provider_id and provider_id == "ollama":
            return OllamaProvider.from_config(self.config)
        return None

    def get_required(self, provider_id: str) -> ProviderPort:
        """Return a provider or raise a stable lookup error."""
        provider = self.get(provider_id)
        if provider is None:
            raise ProviderNotFoundError(provider_id)
        return provider


__all__ = ["ConfiguredProviderRegistry", "ProviderNotFoundError"]
