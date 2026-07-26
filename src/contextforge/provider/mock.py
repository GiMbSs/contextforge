"""Deterministic Provider Port test implementation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from contextforge.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticCollection,
    DiagnosticSeverity,
)
from contextforge.domain import (
    InferenceRequestId,
    InferenceResponseId,
)
from contextforge.prompt import InferenceRequest
from contextforge.provider.capabilities import (
    ProviderCapabilityProfile,
    ProviderExecutionMode,
    ProviderRequestFeature,
)
from contextforge.provider.models import (
    CancellationResult,
    CancellationStatus,
    InferenceResponse,
    ProviderDiagnostics,
    ProviderExecutionContext,
    ProviderExecutionMeasurements,
    ProviderFinishReason,
    ProviderFinishState,
    ProviderHealth,
    ProviderHealthStatus,
    ProviderModel,
    ProviderResponseFormat,
    ProviderResponseMetadata,
    ProviderUsage,
)
from contextforge.provider.normalization import (
    InferenceResponseNormalizer,
    ProviderResponseObservation,
    RawResponseRetentionPolicy,
)

MOCK_PROVIDER_ID = "mock-provider"
MOCK_ADAPTER_ID = "mock-deterministic"
MOCK_ADAPTER_VERSION = "1"
MOCK_MODEL_ID = "mock-model"
MOCK_CAPABILITY_PROFILE_ID = "mock-profile-v1"


class MockProviderScenario(StrEnum):
    """Normative deterministic provider scenarios."""

    SUCCESSFUL_ANALYSIS = "successful_analysis"
    SUCCESSFUL_STRUCTURED_PATCH = "successful_structured_patch"
    MALFORMED_RESPONSE = "malformed_response"
    TIMEOUT = "timeout"
    CANCELLATION = "cancellation"
    RETRYABLE_FAILURE = "retryable_failure"
    NON_RETRYABLE_FAILURE = "non_retryable_failure"
    PARTIAL_STREAM = "partial_stream"
    UNEXPECTED_TOOL_CALL = "unexpected_tool_call"
    MISSING_USAGE_DATA = "missing_usage_data"


class ProviderFailureCategory(StrEnum):
    """Canonical failure categories used by deterministic test failures."""

    TIMEOUT = "timeout"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    RESPONSE_INVALID = "response_invalid"


@dataclass(frozen=True, slots=True)
class ProviderFailure:
    """Normalized provider failure independent of transport exceptions."""

    failure_id: str
    request_id: InferenceRequestId
    provider_id: str
    adapter_id: str
    model_id: str
    category: ProviderFailureCategory
    message: str
    retryable: bool
    diagnostics: DiagnosticCollection
    occurred_at: datetime

    def __post_init__(self) -> None:
        if not self.failure_id.strip():
            raise ValueError("failure_id must not be empty")
        if not isinstance(self.request_id, InferenceRequestId):
            raise TypeError("request_id must be an InferenceRequestId")
        if not isinstance(self.category, ProviderFailureCategory):
            raise TypeError("category must be a ProviderFailureCategory")
        if not self.message.strip():
            raise ValueError("message must not be empty")
        if type(self.retryable) is not bool:
            raise TypeError("retryable must be a boolean")
        if not isinstance(self.diagnostics, DiagnosticCollection):
            raise TypeError("diagnostics must be a DiagnosticCollection")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")


class ProviderInvocationError(RuntimeError):
    """Exception carrying one normalized Provider Failure."""

    def __init__(self, failure: ProviderFailure) -> None:
        super().__init__(failure.message)
        self.failure = failure


@dataclass(frozen=True, slots=True)
class DeterministicMockProvider:
    """Provider Port implementation with no external effects or nondeterminism."""

    scenario: MockProviderScenario
    timestamp: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.scenario, MockProviderScenario):
            raise TypeError("scenario must be a MockProviderScenario")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")

    def get_capabilities(self) -> ProviderCapabilityProfile:
        """Return static, honest mock capabilities."""
        features = (
            ProviderRequestFeature.SYSTEM_ROLE,
            ProviderRequestFeature.MULTIPLE_MESSAGES,
            ProviderRequestFeature.STRUCTURED_OUTPUT,
            ProviderRequestFeature.STREAMING,
            ProviderRequestFeature.CANCELLATION,
            ProviderRequestFeature.USAGE_REPORTING,
            ProviderRequestFeature.SEED,
        )
        return ProviderCapabilityProfile(
            MOCK_CAPABILITY_PROFILE_ID,
            MOCK_PROVIDER_ID,
            MOCK_ADAPTER_ID,
            MOCK_ADAPTER_VERSION,
            ProviderExecutionMode.LOCAL,
            32_768,
            8_192,
            True,
            True,
            True,
            True,
            features,
            (
                ProviderResponseFormat.JSON_TEXT,
                ProviderResponseFormat.STRUCTURED_OBJECT,
                ProviderResponseFormat.PATCH_ENVELOPE,
                ProviderResponseFormat.ANALYSIS_ENVELOPE,
            ),
            seed_supported=True,
            health_check_supported=True,
            model_discovery_supported=True,
        )

    def health_check(self) -> ProviderHealth:
        """Return a deterministic healthy result."""
        return ProviderHealth(ProviderHealthStatus.HEALTHY, self.timestamp)

    def list_models(self) -> tuple[ProviderModel, ...]:
        """Return the single deterministic mock model."""
        return (ProviderModel(MOCK_MODEL_ID, "ContextForge deterministic mock"),)

    def invoke(
        self,
        request: InferenceRequest,
        execution_context: ProviderExecutionContext,
    ) -> InferenceResponse:
        """Produce the configured scenario without I/O or waiting."""
        if not isinstance(request, InferenceRequest):
            raise TypeError("request must be an InferenceRequest")
        if not isinstance(execution_context, ProviderExecutionContext):
            raise TypeError("execution_context must be a ProviderExecutionContext")
        if self.scenario in (
            MockProviderScenario.TIMEOUT,
            MockProviderScenario.RETRYABLE_FAILURE,
            MockProviderScenario.NON_RETRYABLE_FAILURE,
        ):
            raise ProviderInvocationError(self._failure(request))

        content, response_format, finish_state, diagnostics, finish_reason = self._response_data()
        usage = (
            None
            if self.scenario is MockProviderScenario.MISSING_USAGE_DATA
            else ProviderUsage(100, 50, 150, values_are_estimates=False)
        )
        observation = ProviderResponseObservation(
            response_id=_response_id(request.request_id),
            request_id=request.request_id,
            task_id=request.task_id,
            content=content,
            response_format=response_format,
            metadata=ProviderResponseMetadata(
                MOCK_PROVIDER_ID,
                MOCK_ADAPTER_ID,
                MOCK_ADAPTER_VERSION,
                MOCK_MODEL_ID,
                MOCK_CAPABILITY_PROFILE_ID,
                self.timestamp,
                self.timestamp,
                provider_request_id=f"mock-{request.request_id}",
                retry_attempt=execution_context.retry_attempt,
            ),
            usage=usage,
            measurements=ProviderExecutionMeasurements(0, 0, 0, execution_context.retry_attempt),
            finish_state=finish_state,
            finish_reason=finish_reason,
            diagnostics=ProviderDiagnostics(diagnostics),
            created_at=self.timestamp,
            raw_response=content.encode(),
        )
        return InferenceResponseNormalizer().normalize(
            observation,
            RawResponseRetentionPolicy.NEVER,
        )

    def cancel(self, request_id: InferenceRequestId) -> CancellationResult:
        """Acknowledge cancellation deterministically."""
        return CancellationResult(
            request_id,
            CancellationStatus.CANCELLED,
            "Mock invocation cancelled.",
        )

    def _failure(self, request: InferenceRequest) -> ProviderFailure:
        scenario_data = {
            MockProviderScenario.TIMEOUT: (
                ProviderFailureCategory.TIMEOUT,
                "Mock provider timed out.",
                True,
                "PROVIDER_TIMEOUT",
            ),
            MockProviderScenario.RETRYABLE_FAILURE: (
                ProviderFailureCategory.PROVIDER_UNAVAILABLE,
                "Mock provider is temporarily unavailable.",
                True,
                "PROVIDER_UNAVAILABLE",
            ),
            MockProviderScenario.NON_RETRYABLE_FAILURE: (
                ProviderFailureCategory.RESPONSE_INVALID,
                "Mock provider returned a terminal invalid response.",
                False,
                "PROVIDER_RESPONSE_INVALID",
            ),
        }
        category, message, retryable, code = scenario_data[self.scenario]
        diagnostic = _diagnostic(code, message)
        digest = hashlib.sha256(f"{request.request_id}\0{self.scenario}".encode()).hexdigest()[:24]
        return ProviderFailure(
            f"provider_failure_{digest}",
            request.request_id,
            MOCK_PROVIDER_ID,
            MOCK_ADAPTER_ID,
            MOCK_MODEL_ID,
            category,
            message,
            retryable,
            DiagnosticCollection((diagnostic,)),
            self.timestamp,
        )

    def _response_data(
        self,
    ) -> tuple[
        str,
        ProviderResponseFormat,
        ProviderFinishState,
        DiagnosticCollection,
        ProviderFinishReason,
    ]:
        if self.scenario is MockProviderScenario.SUCCESSFUL_ANALYSIS:
            return (
                json.dumps(
                    {
                        "assumptions": [],
                        "diagnostics": [],
                        "findings": [],
                        "limitations": [],
                        "status": "complete",
                        "summary": "Deterministic mock analysis.",
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                ProviderResponseFormat.ANALYSIS_ENVELOPE,
                ProviderFinishState.COMPLETED,
                DiagnosticCollection(),
                ProviderFinishReason.NATURAL_COMPLETION,
            )
        if self.scenario is MockProviderScenario.SUCCESSFUL_STRUCTURED_PATCH:
            return (
                json.dumps(
                    {
                        "affected_files": ["src/example.py"],
                        "assumptions": [],
                        "patch_format": "unified_diff",
                        "patch_payload": "--- a/src/example.py\n+++ b/src/example.py\n",
                        "response_type": "patch_proposal",
                        "summary": "Deterministic mock patch.",
                        "warnings": [],
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                ProviderResponseFormat.PATCH_ENVELOPE,
                ProviderFinishState.COMPLETED,
                DiagnosticCollection(),
                ProviderFinishReason.NATURAL_COMPLETION,
            )
        if self.scenario is MockProviderScenario.MALFORMED_RESPONSE:
            return (
                '{"summary":',
                ProviderResponseFormat.JSON_TEXT,
                ProviderFinishState.COMPLETED,
                DiagnosticCollection(),
                ProviderFinishReason.NATURAL_COMPLETION,
            )
        if self.scenario is MockProviderScenario.CANCELLATION:
            return (
                "",
                ProviderResponseFormat.UNKNOWN,
                ProviderFinishState.CANCELLED,
                DiagnosticCollection((_diagnostic("PROVIDER_CANCELLED", "Invocation cancelled."),)),
                ProviderFinishReason.CLIENT_CANCELLATION,
            )
        if self.scenario is MockProviderScenario.PARTIAL_STREAM:
            return (
                '{"summary":"partial',
                ProviderResponseFormat.JSON_TEXT,
                ProviderFinishState.PARTIAL,
                DiagnosticCollection(
                    (_diagnostic("PROVIDER_STREAM_INTERRUPTED", "Mock stream interrupted."),)
                ),
                ProviderFinishReason.STREAM_INTERRUPTED,
            )
        if self.scenario is MockProviderScenario.UNEXPECTED_TOOL_CALL:
            return (
                '{"tool":"shell","arguments":{"command":"untrusted"}}',
                ProviderResponseFormat.STRUCTURED_OBJECT,
                ProviderFinishState.PARTIAL,
                DiagnosticCollection(
                    (
                        _diagnostic(
                            "PROVIDER_UNEXPECTED_TOOL_CALL",
                            "Provider requested an unsupported tool call; it was not executed.",
                        ),
                    )
                ),
                ProviderFinishReason.TOOL_CALL_REQUESTED,
            )
        return (
            '{"summary":"usage unavailable"}',
            ProviderResponseFormat.JSON_TEXT,
            ProviderFinishState.COMPLETED_WITH_WARNINGS,
            DiagnosticCollection(
                (_diagnostic("PROVIDER_USAGE_UNAVAILABLE", "Usage data is unavailable."),)
            ),
            ProviderFinishReason.NATURAL_COMPLETION,
        )


def _response_id(request_id: InferenceRequestId) -> InferenceResponseId:
    digest = hashlib.sha256(str(request_id).encode()).hexdigest()[:32]
    return InferenceResponseId(f"inference_response_{digest}")


def _diagnostic(code: str, message: str) -> Diagnostic:
    return Diagnostic(
        DiagnosticCode(code),
        DiagnosticSeverity.WARNING,
        message,
        "mock-provider",
    )
