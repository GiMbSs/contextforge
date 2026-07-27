"""Ollama-compatible provider implementing the Provider Port."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from contextforge.adapters.providers.ollama import OllamaDiscoveryAdapter, OllamaHttpTransport
from contextforge.adapters.providers.ollama_invocation import (
    OLLAMA_ADAPTER_ID,
    OLLAMA_ADAPTER_VERSION,
    OLLAMA_CAPABILITY_PROFILE_ID,
    OLLAMA_PROVIDER_ID,
    OllamaInvocationAdapter,
)
from contextforge.adapters.providers.ollama_transport import HttpxOllamaTransport
from contextforge.configuration import ProviderConfig
from contextforge.domain import InferenceRequestId
from contextforge.prompt import InferenceRequest
from contextforge.provider import (
    CancellationResult,
    InferenceResponse,
    ProviderCapabilities,
    ProviderCapabilityProfile,
    ProviderExecutionContext,
    ProviderExecutionMode,
    ProviderHealth,
    ProviderModel,
    ProviderOperationNotSupportedError,
    ProviderPort,
    ProviderRequestFeature,
    ProviderResponseFormat,
)

_DEFAULT_OLLAMA_MODEL = "qwen2.5-coder:7b"


@dataclass(frozen=True, slots=True)
class OllamaProvider(ProviderPort):
    """Ollama-compatible provider bound to a concrete HTTP transport."""

    config: ProviderConfig
    transport: OllamaHttpTransport

    def __post_init__(self) -> None:
        if not isinstance(self.config, ProviderConfig):
            raise TypeError("config must be a ProviderConfig")
        if not isinstance(self.transport, OllamaHttpTransport):
            raise TypeError("transport must be an OllamaHttpTransport")

    @classmethod
    def from_config(cls, config: ProviderConfig) -> OllamaProvider:
        """Build an Ollama provider from validated configuration."""
        try:
            import httpx  # noqa: F401
        except ImportError as error:
            raise RuntimeError(
                "The 'httpx' package is required for Ollama providers. "
                "Install contextforge with: pip install 'contextforge[providers]'"
            ) from error
        endpoint = config.endpoint or "http://localhost:11434"
        transport = HttpxOllamaTransport(
            endpoint=endpoint,
            timeout_seconds=config.timeout_seconds,
        )
        return cls(config=config, transport=transport)

    def get_capabilities(self) -> ProviderCapabilities:
        """Return honest Ollama-compatible capabilities."""
        return ProviderCapabilityProfile(
            profile_id=OLLAMA_CAPABILITY_PROFILE_ID,
            provider_id=OLLAMA_PROVIDER_ID,
            adapter_id=OLLAMA_ADAPTER_ID,
            adapter_version=OLLAMA_ADAPTER_VERSION,
            execution_mode=ProviderExecutionMode(self.config.execution_mode),
            context_limit_tokens=None,
            maximum_output_tokens=None,
            structured_output_supported=True,
            streaming_supported=False,
            cancellation_supported=False,
            usage_reporting_supported=True,
            supported_request_features=(
                ProviderRequestFeature.SYSTEM_ROLE,
                ProviderRequestFeature.MULTIPLE_MESSAGES,
                ProviderRequestFeature.STRUCTURED_OUTPUT,
                ProviderRequestFeature.USAGE_REPORTING,
                ProviderRequestFeature.SEED,
            ),
            supported_response_formats=(
                ProviderResponseFormat.PLAIN_TEXT,
                ProviderResponseFormat.JSON_TEXT,
                ProviderResponseFormat.PATCH_ENVELOPE,
                ProviderResponseFormat.ANALYSIS_ENVELOPE,
            ),
            system_role_supported=True,
            multiple_messages_supported=True,
            json_schema_supported=False,
            seed_supported=True,
            tool_calls_supported=False,
            health_check_supported=True,
            model_discovery_supported=True,
        )

    def health_check(self) -> ProviderHealth:
        """Check the Ollama-compatible endpoint without project content."""
        return self._discovery().health_check()

    def list_models(self) -> tuple[ProviderModel, ...]:
        """List installed models without triggering downloads."""
        return self._discovery().list_models()

    def invoke(
        self,
        request: InferenceRequest,
        execution_context: ProviderExecutionContext,
    ) -> InferenceResponse:
        """Invoke one request through the Ollama-compatible chat endpoint."""
        now = datetime.now(UTC)
        adapter = OllamaInvocationAdapter(
            transport=self.transport,
            model_id=self._model_id,
            timeout_seconds=self.config.timeout_seconds,
            invoked_at=now,
            completed_at=now,
        )
        return adapter.invoke(request, execution_context)

    def cancel(self, request_id: InferenceRequestId) -> CancellationResult:
        """Cancellation is not supported by this adapter."""
        raise ProviderOperationNotSupportedError(
            "Ollama-compatible adapter does not support cancellation."
        )

    def _discovery(self) -> OllamaDiscoveryAdapter:
        return OllamaDiscoveryAdapter(
            transport=self.transport,
            timeout_seconds=self.config.timeout_seconds,
            checked_at=datetime.now(UTC),
        )

    @property
    def _model_id(self) -> str:
        return self.config.model_id or _DEFAULT_OLLAMA_MODEL

    def __repr__(self) -> str:
        return f"OllamaProvider(endpoint={self.config.endpoint!r}, model={self._model_id!r})"


__all__ = ["_DEFAULT_OLLAMA_MODEL", "OllamaProvider"]
