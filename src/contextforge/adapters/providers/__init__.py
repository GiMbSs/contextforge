"""Inference provider adapters."""

from contextforge.adapters.providers.ollama import (
    HttpResponse,
    OllamaDiscoveryAdapter,
    OllamaDiscoveryError,
    OllamaHttpTransport,
)
from contextforge.adapters.providers.ollama_invocation import (
    OLLAMA_ADAPTER_ID,
    OLLAMA_ADAPTER_VERSION,
    OLLAMA_CAPABILITY_PROFILE_ID,
    OLLAMA_PROVIDER_ID,
    OllamaInvocationAdapter,
)
from contextforge.adapters.providers.ollama_provider import (
    _DEFAULT_OLLAMA_MODEL,
    OllamaProvider,
)
from contextforge.adapters.providers.ollama_transport import HttpxOllamaTransport
from contextforge.adapters.providers.registry import (
    ConfiguredProviderRegistry,
    ProviderNotFoundError,
)

__all__ = [
    "OLLAMA_ADAPTER_ID",
    "OLLAMA_ADAPTER_VERSION",
    "OLLAMA_CAPABILITY_PROFILE_ID",
    "OLLAMA_PROVIDER_ID",
    "_DEFAULT_OLLAMA_MODEL",
    "ConfiguredProviderRegistry",
    "HttpResponse",
    "HttpxOllamaTransport",
    "OllamaDiscoveryAdapter",
    "OllamaDiscoveryError",
    "OllamaHttpTransport",
    "OllamaInvocationAdapter",
    "OllamaProvider",
    "ProviderNotFoundError",
]
