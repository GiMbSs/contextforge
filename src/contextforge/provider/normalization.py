"""Central normalization of provider response observations."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from contextforge.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticSeverity,
)
from contextforge.domain import (
    InferenceRequestId,
    InferenceResponseId,
    TaskId,
)
from contextforge.provider.models import (
    InferenceResponse,
    ProviderDiagnostics,
    ProviderExecutionMeasurements,
    ProviderFinishReason,
    ProviderFinishState,
    ProviderResponseFormat,
    ProviderResponseMetadata,
    ProviderUsage,
)


class RawResponseRetentionPolicy(StrEnum):
    """When raw provider bytes may be retained."""

    NEVER = "never"
    ON_INCOMPLETE = "on_incomplete"
    ALWAYS = "always"


@dataclass(frozen=True, slots=True)
class ProviderResponseObservation:
    """Adapter observation before retention and representation normalization."""

    response_id: InferenceResponseId
    request_id: InferenceRequestId
    task_id: TaskId
    content: str
    response_format: ProviderResponseFormat
    metadata: ProviderResponseMetadata
    usage: ProviderUsage | None
    measurements: ProviderExecutionMeasurements
    finish_state: ProviderFinishState
    finish_reason: ProviderFinishReason
    diagnostics: ProviderDiagnostics
    created_at: datetime
    provider_stop_reason: str | None = None
    raw_response: bytes | None = None


@dataclass(frozen=True, slots=True)
class InferenceResponseNormalizer:
    """Normalize representation state without changing semantic content."""

    def normalize(
        self,
        observation: ProviderResponseObservation,
        retention_policy: RawResponseRetentionPolicy,
    ) -> InferenceResponse:
        """Create an immutable response and enforce raw-retention policy."""
        if not isinstance(observation, ProviderResponseObservation):
            raise TypeError("observation must be a ProviderResponseObservation")
        if not isinstance(retention_policy, RawResponseRetentionPolicy):
            raise TypeError("retention_policy must be a RawResponseRetentionPolicy")

        normalized = observation
        if (
            observation.finish_state
            in (
                ProviderFinishState.COMPLETED,
                ProviderFinishState.COMPLETED_WITH_WARNINGS,
            )
            and observation.response_format
            in (
                ProviderResponseFormat.JSON_TEXT,
                ProviderResponseFormat.STRUCTURED_OBJECT,
                ProviderResponseFormat.PATCH_ENVELOPE,
                ProviderResponseFormat.ANALYSIS_ENVELOPE,
            )
            and not _is_json_object(observation.content)
        ):
            normalized = replace(
                observation,
                finish_state=ProviderFinishState.FAILED,
                finish_reason=ProviderFinishReason.MALFORMED_OUTPUT,
                diagnostics=observation.diagnostics.with_diagnostic(
                    _diagnostic(
                        "PROVIDER_RESPONSE_MALFORMED",
                        "Provider output is not a valid JSON object.",
                    )
                ),
            )

        retain_raw = retention_policy is RawResponseRetentionPolicy.ALWAYS or (
            retention_policy is RawResponseRetentionPolicy.ON_INCOMPLETE
            and normalized.finish_state
            not in (
                ProviderFinishState.COMPLETED,
                ProviderFinishState.COMPLETED_WITH_WARNINGS,
            )
        )
        return InferenceResponse(
            response_id=normalized.response_id,
            request_id=normalized.request_id,
            task_id=normalized.task_id,
            content=normalized.content,
            response_format=normalized.response_format,
            metadata=normalized.metadata,
            usage=normalized.usage,
            measurements=normalized.measurements,
            finish_state=normalized.finish_state,
            diagnostics=normalized.diagnostics,
            created_at=normalized.created_at,
            finish_reason=normalized.finish_reason,
            provider_stop_reason=normalized.provider_stop_reason,
            raw_response=normalized.raw_response if retain_raw else None,
        )


def _is_json_object(content: str) -> bool:
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        return False
    return isinstance(value, dict)


def _diagnostic(code: str, message: str) -> Diagnostic:
    return Diagnostic(
        DiagnosticCode(code),
        DiagnosticSeverity.ERROR,
        message,
        "provider-response-normalizer",
    )
