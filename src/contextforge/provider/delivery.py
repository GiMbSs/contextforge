"""Fail-closed provider delivery authorization policy."""

from __future__ import annotations

from dataclasses import dataclass

from contextforge.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticCollection,
    DiagnosticSeverity,
)
from contextforge.prompt import InferenceRequest, PromptRole, ResponseFormat
from contextforge.provider.capabilities import (
    ProviderCapabilityProfile,
    ProviderExecutionMode,
    ProviderRequestFeature,
)
from contextforge.provider.models import ProviderResponseFormat


@dataclass(frozen=True, slots=True)
class ProviderDeliveryPolicy:
    """Configured bounds on eligible provider delivery."""

    allowed_execution_modes: tuple[ProviderExecutionMode, ...]
    allowed_provider_ids: tuple[str, ...] = ()
    allow_sensitive_local: bool = True
    allow_sensitive_remote: bool = False
    require_explicit_remote_authorization: bool = True
    maximum_input_bytes: int | None = None
    maximum_input_tokens: int | None = None

    def __post_init__(self) -> None:
        modes = tuple(self.allowed_execution_modes)
        if not modes:
            raise ValueError("allowed_execution_modes must not be empty")
        if any(not isinstance(mode, ProviderExecutionMode) for mode in modes):
            raise TypeError("allowed_execution_modes must contain ProviderExecutionMode values")
        if len(set(modes)) != len(modes):
            raise ValueError("allowed_execution_modes must not contain duplicates")
        providers = tuple(self.allowed_provider_ids)
        if any(not provider.strip() for provider in providers):
            raise ValueError("allowed_provider_ids must contain non-empty values")
        if len(set(providers)) != len(providers):
            raise ValueError("allowed_provider_ids must not contain duplicates")
        for field_name in (
            "allow_sensitive_local",
            "allow_sensitive_remote",
            "require_explicit_remote_authorization",
        ):
            if type(getattr(self, field_name)) is not bool:
                raise TypeError(f"{field_name} must be a boolean")
        for field_name in ("maximum_input_bytes", "maximum_input_tokens"):
            value = getattr(self, field_name)
            if value is not None:
                if type(value) is not int:
                    raise TypeError(f"{field_name} must be an integer")
                if value < 1:
                    raise ValueError(f"{field_name} must be positive")
        object.__setattr__(self, "allowed_execution_modes", modes)
        object.__setattr__(self, "allowed_provider_ids", providers)


@dataclass(frozen=True, slots=True)
class ProviderDeliveryAuthorization:
    """Explicit user authorization supplied by orchestration."""

    delivery_authorized: bool
    remote_delivery_authorized: bool = False
    sensitive_delivery_authorized: bool = False

    def __post_init__(self) -> None:
        for field_name in self.__dataclass_fields__:
            if type(getattr(self, field_name)) is not bool:
                raise TypeError(f"{field_name} must be a boolean")


@dataclass(frozen=True, slots=True)
class ProviderDeliveryDecision:
    """Immutable authorization result produced before transport."""

    authorized: bool
    diagnostics: DiagnosticCollection

    def __post_init__(self) -> None:
        if type(self.authorized) is not bool:
            raise TypeError("authorized must be a boolean")
        if not isinstance(self.diagnostics, DiagnosticCollection):
            raise TypeError("diagnostics must be a DiagnosticCollection")
        if self.authorized is (len(self.diagnostics) > 0):
            raise ValueError("Authorized decisions must be diagnostic-free")


@dataclass(frozen=True, slots=True)
class ProviderDeliveryPolicyEvaluator:
    """Evaluate all delivery constraints without performing transport."""

    def evaluate(
        self,
        request: InferenceRequest,
        profile: ProviderCapabilityProfile,
        policy: ProviderDeliveryPolicy,
        authorization: ProviderDeliveryAuthorization,
    ) -> ProviderDeliveryDecision:
        """Return a fail-closed decision covering policy and compatibility."""
        if not isinstance(request, InferenceRequest):
            raise TypeError("request must be an InferenceRequest")
        if not isinstance(profile, ProviderCapabilityProfile):
            raise TypeError("profile must be a ProviderCapabilityProfile")
        if not isinstance(policy, ProviderDeliveryPolicy):
            raise TypeError("policy must be a ProviderDeliveryPolicy")
        if not isinstance(authorization, ProviderDeliveryAuthorization):
            raise TypeError("authorization must be a ProviderDeliveryAuthorization")

        diagnostics: list[Diagnostic] = []
        if not authorization.delivery_authorized:
            diagnostics.append(
                _error(
                    "PROVIDER_DELIVERY_NOT_AUTHORIZED",
                    "Provider delivery lacks explicit user authorization.",
                )
            )
        if profile.execution_mode not in policy.allowed_execution_modes:
            diagnostics.append(
                _error(
                    "PROVIDER_EXECUTION_MODE_PROHIBITED",
                    f"Provider execution mode is prohibited: {profile.execution_mode.value}.",
                )
            )
        if policy.allowed_provider_ids and profile.provider_id not in policy.allowed_provider_ids:
            diagnostics.append(
                _error(
                    "PROVIDER_NOT_ALLOWED",
                    f"Provider is not present in the configured allowlist: {profile.provider_id}.",
                )
            )

        self._evaluate_remote(request, profile, policy, authorization, diagnostics)
        self._evaluate_sensitivity(request, profile, policy, authorization, diagnostics)
        self._evaluate_size(request, profile, policy, diagnostics)
        self._evaluate_capabilities(request, profile, diagnostics)
        collection = DiagnosticCollection(tuple(diagnostics))
        return ProviderDeliveryDecision(not diagnostics, collection)

    @staticmethod
    def _evaluate_remote(
        request: InferenceRequest,
        profile: ProviderCapabilityProfile,
        policy: ProviderDeliveryPolicy,
        authorization: ProviderDeliveryAuthorization,
        diagnostics: list[Diagnostic],
    ) -> None:
        if profile.execution_mode is not ProviderExecutionMode.REMOTE:
            return
        if not request.delivery_requirements.remote_delivery_allowed:
            diagnostics.append(
                _error(
                    "PROVIDER_REMOTE_DELIVERY_PROHIBITED",
                    "Inference Request does not permit remote delivery.",
                )
            )
        if (
            policy.require_explicit_remote_authorization
            and not authorization.remote_delivery_authorized
        ):
            diagnostics.append(
                _error(
                    "PROVIDER_REMOTE_AUTHORIZATION_REQUIRED",
                    "Remote delivery requires explicit user authorization.",
                )
            )

    @staticmethod
    def _evaluate_sensitivity(
        request: InferenceRequest,
        profile: ProviderCapabilityProfile,
        policy: ProviderDeliveryPolicy,
        authorization: ProviderDeliveryAuthorization,
        diagnostics: list[Diagnostic],
    ) -> None:
        actual_sensitive = request.measurements.sensitive_item_count > 0
        declared_sensitive = request.delivery_requirements.contains_sensitive_context
        if actual_sensitive is not declared_sensitive:
            diagnostics.append(
                _error(
                    "PROVIDER_SENSITIVITY_METADATA_MISMATCH",
                    "Sensitive-context metadata disagrees with prompt measurements.",
                )
            )
        if not actual_sensitive:
            return
        mode_allowed = (
            policy.allow_sensitive_local
            if profile.execution_mode is ProviderExecutionMode.LOCAL
            else policy.allow_sensitive_remote
        )
        if not mode_allowed:
            diagnostics.append(
                _error(
                    "PROVIDER_SENSITIVE_DELIVERY_PROHIBITED",
                    "Configured policy prohibits sensitive context for this execution mode.",
                )
            )
        if not authorization.sensitive_delivery_authorized:
            diagnostics.append(
                _error(
                    "PROVIDER_SENSITIVE_AUTHORIZATION_REQUIRED",
                    "Sensitive context delivery requires explicit user authorization.",
                )
            )

    @staticmethod
    def _evaluate_size(
        request: InferenceRequest,
        profile: ProviderCapabilityProfile,
        policy: ProviderDeliveryPolicy,
        diagnostics: list[Diagnostic],
    ) -> None:
        requirements = request.delivery_requirements
        comparisons = (
            (
                request.measurements.byte_count,
                requirements.maximum_input_bytes,
                "request byte requirement",
            ),
            (
                request.measurements.byte_count,
                policy.maximum_input_bytes,
                "policy byte limit",
            ),
            (
                request.measurements.estimated_tokens,
                policy.maximum_input_tokens,
                "policy token limit",
            ),
            (
                request.measurements.estimated_tokens,
                profile.context_limit_tokens,
                "provider context limit",
            ),
            (
                request.maximum_output_tokens or 0,
                profile.maximum_output_tokens,
                "provider output limit",
            ),
        )
        for actual, maximum, label in comparisons:
            if maximum is not None and actual > maximum:
                diagnostics.append(
                    _error(
                        "PROVIDER_REQUEST_SIZE_INCOMPATIBLE",
                        f"Inference Request exceeds {label}: {actual} > {maximum}.",
                    )
                )
        if (
            requirements.maximum_output_bytes is not None
            and request.response_contract.maximum_response_bytes is not None
            and request.response_contract.maximum_response_bytes > requirements.maximum_output_bytes
        ):
            diagnostics.append(
                _error(
                    "PROVIDER_OUTPUT_SIZE_INCOMPATIBLE",
                    "Response Contract exceeds the authorized output byte limit.",
                )
            )

    @staticmethod
    def _evaluate_capabilities(
        request: InferenceRequest,
        profile: ProviderCapabilityProfile,
        diagnostics: list[Diagnostic],
    ) -> None:
        supported = set(profile.supported_request_features)
        for capability in request.delivery_requirements.required_capabilities:
            try:
                feature = ProviderRequestFeature(capability)
            except ValueError:
                diagnostics.append(
                    _error(
                        "PROVIDER_CAPABILITY_UNKNOWN",
                        f"Inference Request requires an unknown capability: {capability}.",
                    )
                )
                continue
            if feature not in supported:
                diagnostics.append(
                    _error(
                        "PROVIDER_CAPABILITY_MISSING",
                        f"Provider lacks required capability: {capability}.",
                    )
                )
        if (
            request.delivery_requirements.structured_output_required
            and not profile.structured_output_supported
        ):
            diagnostics.append(
                _error(
                    "PROVIDER_CAPABILITY_MISSING",
                    "Provider lacks required structured-output support.",
                )
            )
        if any(message.role is PromptRole.SYSTEM for message in request.messages) and not (
            profile.system_role_supported
        ):
            diagnostics.append(
                _error(
                    "PROVIDER_CAPABILITY_MISSING",
                    "Provider cannot preserve required system-role messages.",
                )
            )
        if len(request.messages) > 1 and not profile.multiple_messages_supported:
            diagnostics.append(
                _error(
                    "PROVIDER_CAPABILITY_MISSING",
                    "Provider cannot preserve multiple required prompt messages.",
                )
            )
        compatible_formats = {
            ResponseFormat.TEXT: {
                ProviderResponseFormat.PLAIN_TEXT,
                ProviderResponseFormat.UNKNOWN,
            },
            ResponseFormat.JSON: {
                ProviderResponseFormat.JSON_TEXT,
                ProviderResponseFormat.STRUCTURED_OBJECT,
                ProviderResponseFormat.ANALYSIS_ENVELOPE,
            },
            ResponseFormat.UNIFIED_DIFF: {
                ProviderResponseFormat.PLAIN_TEXT,
                ProviderResponseFormat.PATCH_ENVELOPE,
            },
            ResponseFormat.STRUCTURED_PATCH: {
                ProviderResponseFormat.STRUCTURED_OBJECT,
                ProviderResponseFormat.PATCH_ENVELOPE,
            },
        }[request.response_contract.output_format]
        if not compatible_formats.intersection(profile.supported_response_formats):
            diagnostics.append(
                _error(
                    "PROVIDER_RESPONSE_FORMAT_UNSUPPORTED",
                    "Provider cannot represent the required response format.",
                )
            )


def _error(code: str, message: str) -> Diagnostic:
    return Diagnostic(
        DiagnosticCode(code),
        DiagnosticSeverity.ERROR,
        message,
        "provider-delivery-policy",
    )
