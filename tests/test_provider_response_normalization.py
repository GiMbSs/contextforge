"""Tests for normative provider response normalization."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from contextforge.diagnostics import DiagnosticCollection
from contextforge.domain import (
    new_inference_request_id,
    new_inference_response_id,
    new_task_id,
)
from contextforge.provider import (
    InferenceResponseNormalizer,
    ProviderDiagnostics,
    ProviderExecutionMeasurements,
    ProviderFinishReason,
    ProviderFinishState,
    ProviderResponseFormat,
    ProviderResponseMetadata,
    ProviderResponseObservation,
    RawResponseRetentionPolicy,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _observation(
    *,
    content: str = '{"result":"ok"}',
    response_format: ProviderResponseFormat = ProviderResponseFormat.JSON_TEXT,
    finish_state: ProviderFinishState = ProviderFinishState.COMPLETED,
    finish_reason: ProviderFinishReason = ProviderFinishReason.NATURAL_COMPLETION,
) -> ProviderResponseObservation:
    return ProviderResponseObservation(
        response_id=new_inference_response_id(),
        request_id=new_inference_request_id(),
        task_id=new_task_id(),
        content=content,
        response_format=response_format,
        metadata=ProviderResponseMetadata(
            "provider",
            "adapter",
            "1",
            "model",
            "profile",
            NOW,
            NOW,
        ),
        usage=None,
        measurements=ProviderExecutionMeasurements(1),
        finish_state=finish_state,
        finish_reason=finish_reason,
        diagnostics=ProviderDiagnostics(DiagnosticCollection()),
        created_at=NOW,
        raw_response=b'{"result":"ok"}',
    )


@pytest.mark.parametrize(
    ("policy", "finish_state", "retained"),
    [
        (RawResponseRetentionPolicy.NEVER, ProviderFinishState.FAILED, False),
        (RawResponseRetentionPolicy.ALWAYS, ProviderFinishState.COMPLETED, True),
        (RawResponseRetentionPolicy.ON_INCOMPLETE, ProviderFinishState.COMPLETED, False),
        (RawResponseRetentionPolicy.ON_INCOMPLETE, ProviderFinishState.FAILED, True),
    ],
)
def test_raw_response_retention_obeys_policy(
    policy: RawResponseRetentionPolicy,
    finish_state: ProviderFinishState,
    retained: bool,
) -> None:
    observation = _observation(
        finish_state=finish_state,
        finish_reason=(
            ProviderFinishReason.PROVIDER_ERROR
            if finish_state is ProviderFinishState.FAILED
            else ProviderFinishReason.NATURAL_COMPLETION
        ),
    )

    response = InferenceResponseNormalizer().normalize(observation, policy)

    assert (response.raw_response is not None) is retained


def test_missing_usage_remains_absent() -> None:
    response = InferenceResponseNormalizer().normalize(
        _observation(),
        RawResponseRetentionPolicy.NEVER,
    )

    assert response.usage is None


def test_malformed_structured_output_is_classified_and_diagnosed() -> None:
    response = InferenceResponseNormalizer().normalize(
        _observation(content='{"result":'),
        RawResponseRetentionPolicy.NEVER,
    )

    assert response.finish_state is ProviderFinishState.FAILED
    assert response.finish_reason is ProviderFinishReason.MALFORMED_OUTPUT
    assert {str(item.code) for item in response.diagnostics} == {"PROVIDER_RESPONSE_MALFORMED"}


@pytest.mark.parametrize(
    ("finish_state", "finish_reason"),
    [
        (ProviderFinishState.TIMED_OUT, ProviderFinishReason.TIMEOUT),
        (ProviderFinishState.CANCELLED, ProviderFinishReason.CLIENT_CANCELLATION),
        (ProviderFinishState.FAILED, ProviderFinishReason.MALFORMED_OUTPUT),
    ],
)
def test_terminal_conditions_remain_distinct(
    finish_state: ProviderFinishState,
    finish_reason: ProviderFinishReason,
) -> None:
    response = InferenceResponseNormalizer().normalize(
        _observation(
            response_format=ProviderResponseFormat.PLAIN_TEXT,
            finish_state=finish_state,
            finish_reason=finish_reason,
        ),
        RawResponseRetentionPolicy.NEVER,
    )

    assert response.finish_state is finish_state
    assert response.finish_reason is finish_reason


def test_normalized_response_is_immutable() -> None:
    response = InferenceResponseNormalizer().normalize(
        _observation(),
        RawResponseRetentionPolicy.NEVER,
    )

    with pytest.raises(FrozenInstanceError):
        response.content = "changed"  # type: ignore[misc]
