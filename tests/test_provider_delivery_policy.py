"""Tests for fail-closed provider delivery authorization."""

from dataclasses import replace
from datetime import UTC, datetime

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
    ProviderCapabilityProfile,
    ProviderDeliveryAuthorization,
    ProviderDeliveryDecision,
    ProviderDeliveryPolicy,
    ProviderDeliveryPolicyEvaluator,
    ProviderExecutionMode,
    ProviderRequestFeature,
    ProviderResponseFormat,
)

NOW = datetime(2026, 7, 26, tzinfo=UTC)


def _profile(
    mode: ProviderExecutionMode = ProviderExecutionMode.LOCAL,
) -> ProviderCapabilityProfile:
    return ProviderCapabilityProfile(
        "profile-1",
        "provider-1",
        "adapter-1",
        "1",
        mode,
        1_000,
        500,
        True,
        False,
        False,
        True,
        (
            ProviderRequestFeature.SYSTEM_ROLE,
            ProviderRequestFeature.MULTIPLE_MESSAGES,
            ProviderRequestFeature.STRUCTURED_OUTPUT,
            ProviderRequestFeature.USAGE_REPORTING,
        ),
        (
            ProviderResponseFormat.JSON_TEXT,
            ProviderResponseFormat.ANALYSIS_ENVELOPE,
        ),
    )


def _request(
    *,
    remote_allowed: bool = False,
    sensitive: bool = False,
    required_capabilities: tuple[str, ...] = ("structured_output",),
) -> InferenceRequest:
    return InferenceRequest(
        new_inference_request_id(),
        new_task_id(),
        new_context_bundle_id(),
        new_project_id(),
        fingerprint_project(("project",), ordering=FingerprintOrdering.ORDERED),
        "template-v1",
        (
            PromptMessage(
                "system",
                0,
                PromptRole.SYSTEM,
                PromptTrust.TRUSTED,
                "Rules.",
            ),
            PromptMessage(
                "context",
                1,
                PromptRole.USER,
                PromptTrust.UNTRUSTED,
                "Context.",
            ),
        ),
        analysis_response_contract(),
        DeliveryRequirements(
            required_capabilities,
            remote_delivery_allowed=remote_allowed,
            contains_sensitive_context=sensitive,
            structured_output_required=True,
        ),
        PromptMeasurements(
            100,
            100,
            2,
            25,
            10,
            10,
            60,
            20,
            1,
            1,
            int(sensitive),
        ),
        DiagnosticCollection(),
        NOW,
        maximum_output_tokens=100,
    )


def _policy(
    *modes: ProviderExecutionMode,
    allow_sensitive_remote: bool = False,
) -> ProviderDeliveryPolicy:
    return ProviderDeliveryPolicy(
        modes or (ProviderExecutionMode.LOCAL,),
        ("provider-1",),
        allow_sensitive_remote=allow_sensitive_remote,
        maximum_input_bytes=1_000,
        maximum_input_tokens=500,
    )


def _codes(decision: ProviderDeliveryDecision) -> set[str]:
    return {str(diagnostic.code) for diagnostic in decision.diagnostics}


def test_authorized_compatible_local_request_is_allowed() -> None:
    decision = ProviderDeliveryPolicyEvaluator().evaluate(
        _request(),
        _profile(),
        _policy(ProviderExecutionMode.LOCAL),
        ProviderDeliveryAuthorization(True),
    )

    assert decision.authorized
    assert len(decision.diagnostics) == 0


def test_remote_delivery_requires_request_policy_and_user_authorization() -> None:
    decision = ProviderDeliveryPolicyEvaluator().evaluate(
        _request(remote_allowed=False),
        _profile(ProviderExecutionMode.REMOTE),
        _policy(ProviderExecutionMode.REMOTE),
        ProviderDeliveryAuthorization(True),
    )

    assert not decision.authorized
    assert {
        "PROVIDER_REMOTE_DELIVERY_PROHIBITED",
        "PROVIDER_REMOTE_AUTHORIZATION_REQUIRED",
    } <= _codes(decision)


def test_sensitive_remote_delivery_requires_policy_and_explicit_authorization() -> None:
    request = _request(remote_allowed=True, sensitive=True)
    authorization = ProviderDeliveryAuthorization(
        True,
        remote_delivery_authorized=True,
        sensitive_delivery_authorized=True,
    )
    denied = ProviderDeliveryPolicyEvaluator().evaluate(
        request,
        _profile(ProviderExecutionMode.REMOTE),
        _policy(ProviderExecutionMode.REMOTE),
        authorization,
    )
    allowed = ProviderDeliveryPolicyEvaluator().evaluate(
        request,
        _profile(ProviderExecutionMode.REMOTE),
        _policy(
            ProviderExecutionMode.REMOTE,
            allow_sensitive_remote=True,
        ),
        authorization,
    )

    assert "PROVIDER_SENSITIVE_DELIVERY_PROHIBITED" in _codes(denied)
    assert allowed.authorized


def test_request_size_is_checked_against_policy_and_provider() -> None:
    request = replace(
        _request(),
        measurements=replace(
            _request().measurements,
            byte_count=2_000,
            character_count=2_000,
            estimated_tokens=1_500,
        ),
    )
    decision = ProviderDeliveryPolicyEvaluator().evaluate(
        request,
        _profile(),
        _policy(ProviderExecutionMode.LOCAL),
        ProviderDeliveryAuthorization(True),
    )

    assert "PROVIDER_REQUEST_SIZE_INCOMPATIBLE" in _codes(decision)


def test_missing_or_unknown_capabilities_are_rejected() -> None:
    request = _request(required_capabilities=("streaming", "future_feature"))
    decision = ProviderDeliveryPolicyEvaluator().evaluate(
        request,
        _profile(),
        _policy(ProviderExecutionMode.LOCAL),
        ProviderDeliveryAuthorization(True),
    )

    assert {
        "PROVIDER_CAPABILITY_MISSING",
        "PROVIDER_CAPABILITY_UNKNOWN",
    } <= _codes(decision)


def test_explicit_general_authorization_is_always_required() -> None:
    decision = ProviderDeliveryPolicyEvaluator().evaluate(
        _request(),
        _profile(),
        _policy(ProviderExecutionMode.LOCAL),
        ProviderDeliveryAuthorization(False),
    )

    assert "PROVIDER_DELIVERY_NOT_AUTHORIZED" in _codes(decision)
