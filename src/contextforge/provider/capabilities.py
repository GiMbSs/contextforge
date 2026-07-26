"""Validated Provider Capability Profiles."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from contextforge.provider.models import ProviderOperation, ProviderResponseFormat


class ProviderExecutionMode(StrEnum):
    """Explicit provider execution boundary."""

    LOCAL = "local"
    REMOTE = "remote"


class ProviderRequestFeature(StrEnum):
    """Features an Inference Request may require."""

    SYSTEM_ROLE = "system_role"
    MULTIPLE_MESSAGES = "multiple_messages"
    STRUCTURED_OUTPUT = "structured_output"
    JSON_SCHEMA = "json_schema"
    STREAMING = "streaming"
    CANCELLATION = "cancellation"
    USAGE_REPORTING = "usage_reporting"
    SEED = "seed"
    TOOL_CALLS = "tool_calls"


@dataclass(frozen=True, slots=True)
class ProviderCapabilityProfile:
    """Immutable capabilities of one adapter and provider configuration."""

    profile_id: str
    provider_id: str
    adapter_id: str
    adapter_version: str
    execution_mode: ProviderExecutionMode
    context_limit_tokens: int | None
    maximum_output_tokens: int | None
    structured_output_supported: bool
    streaming_supported: bool
    cancellation_supported: bool
    usage_reporting_supported: bool
    supported_request_features: tuple[ProviderRequestFeature, ...]
    supported_response_formats: tuple[ProviderResponseFormat, ...]
    system_role_supported: bool = True
    multiple_messages_supported: bool = True
    json_schema_supported: bool = False
    seed_supported: bool = False
    tool_calls_supported: bool = False
    health_check_supported: bool = False
    model_discovery_supported: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "profile_id",
            "provider_id",
            "adapter_id",
            "adapter_version",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must not be empty")
            if field_name != "adapter_version" and any(character.isspace() for character in value):
                raise ValueError(f"{field_name} must not contain whitespace")
        if not isinstance(self.execution_mode, ProviderExecutionMode):
            raise TypeError("execution_mode must be a ProviderExecutionMode")
        for field_name in ("context_limit_tokens", "maximum_output_tokens"):
            value = getattr(self, field_name)
            if value is not None:
                if type(value) is not int:
                    raise TypeError(f"{field_name} must be an integer")
                if value < 1:
                    raise ValueError(f"{field_name} must be positive")
        for field_name in (
            "structured_output_supported",
            "streaming_supported",
            "cancellation_supported",
            "usage_reporting_supported",
            "system_role_supported",
            "multiple_messages_supported",
            "json_schema_supported",
            "seed_supported",
            "tool_calls_supported",
            "health_check_supported",
            "model_discovery_supported",
        ):
            if type(getattr(self, field_name)) is not bool:
                raise TypeError(f"{field_name} must be a boolean")

        features = tuple(self.supported_request_features)
        if any(not isinstance(feature, ProviderRequestFeature) for feature in features):
            raise TypeError("supported_request_features must contain ProviderRequestFeature values")
        if len(set(features)) != len(features):
            raise ValueError("supported_request_features must not contain duplicates")
        response_formats = tuple(self.supported_response_formats)
        if not response_formats:
            raise ValueError("supported_response_formats must not be empty")
        if any(
            not isinstance(response_format, ProviderResponseFormat)
            for response_format in response_formats
        ):
            raise TypeError("supported_response_formats must contain ProviderResponseFormat values")
        if len(set(response_formats)) != len(response_formats):
            raise ValueError("supported_response_formats must not contain duplicates")

        declared = set(features)
        feature_flags = (
            (ProviderRequestFeature.SYSTEM_ROLE, self.system_role_supported),
            (
                ProviderRequestFeature.MULTIPLE_MESSAGES,
                self.multiple_messages_supported,
            ),
            (
                ProviderRequestFeature.STRUCTURED_OUTPUT,
                self.structured_output_supported,
            ),
            (ProviderRequestFeature.JSON_SCHEMA, self.json_schema_supported),
            (ProviderRequestFeature.STREAMING, self.streaming_supported),
            (ProviderRequestFeature.CANCELLATION, self.cancellation_supported),
            (
                ProviderRequestFeature.USAGE_REPORTING,
                self.usage_reporting_supported,
            ),
            (ProviderRequestFeature.SEED, self.seed_supported),
            (ProviderRequestFeature.TOOL_CALLS, self.tool_calls_supported),
        )
        inconsistent = tuple(
            feature.value
            for feature, supported in feature_flags
            if (feature in declared) is not supported
        )
        if inconsistent:
            raise ValueError(
                "Feature flags must match supported_request_features: " + ", ".join(inconsistent)
            )
        object.__setattr__(self, "supported_request_features", features)
        object.__setattr__(self, "supported_response_formats", response_formats)

    @property
    def supported_operations(self) -> tuple[ProviderOperation, ...]:
        """Derive supported port operations from explicit capability flags."""
        operations = [
            ProviderOperation.GET_CAPABILITIES,
            ProviderOperation.INVOKE,
        ]
        if self.health_check_supported:
            operations.append(ProviderOperation.HEALTH_CHECK)
        if self.model_discovery_supported:
            operations.append(ProviderOperation.LIST_MODELS)
        if self.cancellation_supported:
            operations.append(ProviderOperation.CANCEL)
        return tuple(sorted(operations, key=lambda operation: operation.value))
