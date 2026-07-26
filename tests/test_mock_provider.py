"""Tests for every deterministic Mock Provider scenario."""

from datetime import UTC, datetime

import pytest

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
    DeterministicMockProvider,
    MockProviderScenario,
    ProviderExecutionContext,
    ProviderFailureCategory,
    ProviderFinishState,
    ProviderInvocationError,
    ProviderPort,
)

NOW = datetime(2026, 7, 26, tzinfo=UTC)


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
                "task",
                0,
                PromptRole.USER,
                PromptTrust.TRUSTED,
                "Analyze.",
            ),
        ),
        analysis_response_contract(),
        DeliveryRequirements(),
        PromptMeasurements(10, 10, 1, 3, 0, 10, 0, 0, 0, 0, 0),
        DiagnosticCollection(),
        NOW,
    )


@pytest.mark.parametrize("scenario", tuple(MockProviderScenario))
def test_every_normative_scenario_is_deterministic(
    scenario: MockProviderScenario,
) -> None:
    request = _request()
    context = ProviderExecutionContext("execution-1")
    provider: ProviderPort = DeterministicMockProvider(scenario, NOW)

    if scenario in (
        MockProviderScenario.TIMEOUT,
        MockProviderScenario.RETRYABLE_FAILURE,
        MockProviderScenario.NON_RETRYABLE_FAILURE,
    ):
        with pytest.raises(ProviderInvocationError) as first:
            provider.invoke(request, context)
        with pytest.raises(ProviderInvocationError) as second:
            provider.invoke(request, context)
        assert first.value.failure == second.value.failure
    else:
        assert provider.invoke(request, context) == provider.invoke(request, context)


def test_successful_analysis_and_patch_have_structured_formats() -> None:
    request = _request()
    context = ProviderExecutionContext("execution-1")

    analysis = DeterministicMockProvider(MockProviderScenario.SUCCESSFUL_ANALYSIS, NOW).invoke(
        request, context
    )
    patch = DeterministicMockProvider(MockProviderScenario.SUCCESSFUL_STRUCTURED_PATCH, NOW).invoke(
        request, context
    )

    assert analysis.finish_state is ProviderFinishState.COMPLETED
    assert '"summary":"Deterministic mock analysis."' in analysis.content
    assert patch.finish_state is ProviderFinishState.COMPLETED
    assert '"response_type":"patch_proposal"' in patch.content


def test_failures_expose_explicit_retryability() -> None:
    request = _request()
    context = ProviderExecutionContext("execution-1")

    with pytest.raises(ProviderInvocationError) as retryable:
        DeterministicMockProvider(MockProviderScenario.RETRYABLE_FAILURE, NOW).invoke(
            request, context
        )
    with pytest.raises(ProviderInvocationError) as terminal:
        DeterministicMockProvider(MockProviderScenario.NON_RETRYABLE_FAILURE, NOW).invoke(
            request, context
        )

    assert retryable.value.failure.retryable
    assert retryable.value.failure.category is ProviderFailureCategory.PROVIDER_UNAVAILABLE
    assert not terminal.value.failure.retryable


def test_partial_stream_and_tool_call_are_never_complete() -> None:
    request = _request()
    context = ProviderExecutionContext("execution-1")

    partial = DeterministicMockProvider(MockProviderScenario.PARTIAL_STREAM, NOW).invoke(
        request, context
    )
    tool_call = DeterministicMockProvider(MockProviderScenario.UNEXPECTED_TOOL_CALL, NOW).invoke(
        request, context
    )

    assert partial.finish_state is ProviderFinishState.PARTIAL
    assert tool_call.finish_state is ProviderFinishState.PARTIAL
    assert "untrusted" in tool_call.content
    assert any(
        str(diagnostic.code) == "PROVIDER_UNEXPECTED_TOOL_CALL"
        for diagnostic in tool_call.diagnostics
    )


def test_missing_usage_data_is_not_fabricated() -> None:
    response = DeterministicMockProvider(MockProviderScenario.MISSING_USAGE_DATA, NOW).invoke(
        _request(), ProviderExecutionContext("execution-1")
    )

    assert response.usage is None
