"""Tests for validated Provider Capability Profiles."""

from dataclasses import FrozenInstanceError, replace

import pytest

from contextforge.provider import (
    ProviderCapabilities,
    ProviderCapabilityProfile,
    ProviderExecutionMode,
    ProviderOperation,
    ProviderRequestFeature,
    ProviderResponseFormat,
)


def _profile() -> ProviderCapabilityProfile:
    return ProviderCapabilityProfile(
        "profile-mock-v1",
        "mock-provider",
        "mock-deterministic",
        "1",
        ProviderExecutionMode.LOCAL,
        8192,
        2048,
        True,
        False,
        True,
        True,
        (
            ProviderRequestFeature.SYSTEM_ROLE,
            ProviderRequestFeature.MULTIPLE_MESSAGES,
            ProviderRequestFeature.STRUCTURED_OUTPUT,
            ProviderRequestFeature.CANCELLATION,
            ProviderRequestFeature.USAGE_REPORTING,
            ProviderRequestFeature.SEED,
        ),
        (
            ProviderResponseFormat.JSON_TEXT,
            ProviderResponseFormat.STRUCTURED_OBJECT,
        ),
        seed_supported=True,
        health_check_supported=True,
        model_discovery_supported=True,
    )


def test_profile_reports_normative_capabilities_and_execution_mode() -> None:
    profile = _profile()
    capabilities: ProviderCapabilities = profile

    assert profile.execution_mode is ProviderExecutionMode.LOCAL
    assert profile.context_limit_tokens == 8192
    assert profile.structured_output_supported
    assert not profile.streaming_supported
    assert profile.cancellation_supported
    assert profile.usage_reporting_supported
    assert ProviderRequestFeature.STRUCTURED_OUTPUT in profile.supported_request_features
    assert capabilities.provider_id == "mock-provider"


def test_supported_operations_are_derived_honestly() -> None:
    profile = _profile()

    assert set(profile.supported_operations) == {
        ProviderOperation.GET_CAPABILITIES,
        ProviderOperation.HEALTH_CHECK,
        ProviderOperation.LIST_MODELS,
        ProviderOperation.INVOKE,
        ProviderOperation.CANCEL,
    }
    without_optional = replace(
        profile,
        cancellation_supported=False,
        health_check_supported=False,
        model_discovery_supported=False,
        supported_request_features=tuple(
            feature
            for feature in profile.supported_request_features
            if feature is not ProviderRequestFeature.CANCELLATION
        ),
    )
    assert without_optional.supported_operations == (
        ProviderOperation.GET_CAPABILITIES,
        ProviderOperation.INVOKE,
    )


def test_feature_flags_must_match_supported_feature_declaration() -> None:
    with pytest.raises(ValueError, match="Feature flags"):
        replace(_profile(), streaming_supported=True)


def test_unknown_context_limit_is_explicitly_none() -> None:
    profile = replace(_profile(), context_limit_tokens=None)

    assert profile.context_limit_tokens is None


def test_profile_is_immutable() -> None:
    profile = _profile()

    with pytest.raises(FrozenInstanceError):
        profile.provider_id = "changed"  # type: ignore[misc]
