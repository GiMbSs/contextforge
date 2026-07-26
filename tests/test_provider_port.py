"""Contract tests for the provider-independent Provider Port."""

from dataclasses import FrozenInstanceError, dataclass
from datetime import UTC, datetime

import pytest

from contextforge.diagnostics import DiagnosticCollection
from contextforge.domain import (
    InferenceRequestId,
    new_inference_request_id,
    new_inference_response_id,
    new_task_id,
)
from contextforge.prompt import InferenceRequest
from contextforge.provider import (
    CancellationResult,
    CancellationStatus,
    InferenceResponse,
    ProviderCapabilities,
    ProviderExecutionContext,
    ProviderExecutionMeasurements,
    ProviderFinishState,
    ProviderHealth,
    ProviderHealthStatus,
    ProviderModel,
    ProviderOperation,
    ProviderPort,
    ProviderResponseFormat,
    ProviderResponseMetadata,
    ProviderUsage,
)

NOW = datetime(2026, 7, 26, tzinfo=UTC)


@dataclass(frozen=True)
class MinimalCapabilities:
    provider_id: str = "fake-provider"
    adapter_id: str = "fake-adapter"
    supported_operations: tuple[ProviderOperation, ...] = (
        ProviderOperation.GET_CAPABILITIES,
        ProviderOperation.HEALTH_CHECK,
        ProviderOperation.LIST_MODELS,
        ProviderOperation.INVOKE,
        ProviderOperation.CANCEL,
    )


class FakePort:
    def get_capabilities(self) -> ProviderCapabilities:
        return MinimalCapabilities()

    def health_check(self) -> ProviderHealth:
        return ProviderHealth(ProviderHealthStatus.HEALTHY, NOW)

    def list_models(self) -> tuple[ProviderModel, ...]:
        return (ProviderModel("model-1"),)

    def invoke(
        self,
        request: InferenceRequest,
        execution_context: ProviderExecutionContext,
    ) -> InferenceResponse:
        raise NotImplementedError

    def cancel(self, request_id: InferenceRequestId) -> CancellationResult:
        return CancellationResult(request_id, CancellationStatus.CANCELLED)


def test_provider_port_exposes_all_normative_operations() -> None:
    port: ProviderPort = FakePort()

    capabilities = port.get_capabilities()

    assert capabilities.supported_operations == tuple(ProviderOperation)
    assert port.health_check().status is ProviderHealthStatus.HEALTHY
    assert port.list_models()[0].model_id == "model-1"


def test_inference_response_is_immutable_and_preserves_correlation() -> None:
    request_id = new_inference_request_id()
    task_id = new_task_id()
    response = InferenceResponse(
        new_inference_response_id(),
        request_id,
        task_id,
        '{"summary":"done"}',
        ProviderResponseFormat.JSON_TEXT,
        ProviderResponseMetadata(
            "fake-provider",
            "fake-adapter",
            "1",
            "model-1",
            "profile-1",
            NOW,
            NOW,
        ),
        ProviderUsage(10, 5, 15),
        ProviderExecutionMeasurements(25),
        ProviderFinishState.COMPLETED,
        DiagnosticCollection(),
        NOW,
    )

    assert response.request_id == request_id
    assert response.task_id == task_id
    with pytest.raises(FrozenInstanceError):
        response.content = "changed"  # type: ignore[misc]


def test_partial_response_requires_an_explicit_stop_reason() -> None:
    with pytest.raises(ValueError, match="stop_reason"):
        InferenceResponse(
            new_inference_response_id(),
            new_inference_request_id(),
            new_task_id(),
            "partial",
            ProviderResponseFormat.PLAIN_TEXT,
            ProviderResponseMetadata(
                "fake-provider",
                "fake-adapter",
                "1",
                "model-1",
                "profile-1",
                NOW,
                NOW,
            ),
            ProviderUsage(),
            ProviderExecutionMeasurements(1),
            ProviderFinishState.PARTIAL,
            DiagnosticCollection(),
            NOW,
        )


def test_missing_usage_is_represented_without_fabricated_zeroes() -> None:
    usage = ProviderUsage()

    assert usage.input_tokens is None
    assert usage.output_tokens is None
    assert usage.total_tokens is None
