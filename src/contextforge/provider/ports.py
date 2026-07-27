"""Provider Port boundary."""

from typing import Protocol, runtime_checkable

from contextforge.domain import InferenceRequestId
from contextforge.prompt import InferenceRequest
from contextforge.provider.models import (
    CancellationResult,
    InferenceResponse,
    ProviderCapabilities,
    ProviderExecutionContext,
    ProviderHealth,
    ProviderModel,
)


@runtime_checkable
class ProviderPort(Protocol):
    """Execute immutable inference requests through interchangeable adapters."""

    def get_capabilities(self) -> ProviderCapabilities:
        """Return an honest capability description for this configuration."""
        ...

    def health_check(self) -> ProviderHealth:
        """Return normalized health when the operation is supported."""
        ...

    def list_models(self) -> tuple[ProviderModel, ...]:
        """Return available models when discovery is supported."""
        ...

    def invoke(
        self,
        request: InferenceRequest,
        execution_context: ProviderExecutionContext,
    ) -> InferenceResponse:
        """Execute one request and preserve its correlation identities."""
        ...

    def cancel(self, request_id: InferenceRequestId) -> CancellationResult:
        """Request cancellation when advertised by capabilities."""
        ...
