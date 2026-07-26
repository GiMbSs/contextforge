"""Tests for validation of untrusted provider patch envelopes."""

import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from contextforge.diagnostics import DiagnosticCollection
from contextforge.domain import (
    new_inference_request_id,
    new_inference_response_id,
    new_task_id,
)
from contextforge.patch import (
    ProviderResponseEnvelopeValidator,
    ResponseEnvelopeValidationError,
)
from contextforge.prompt import patch_response_contract
from contextforge.provider import (
    InferenceResponse,
    ProviderDiagnostics,
    ProviderExecutionMeasurements,
    ProviderFinishReason,
    ProviderFinishState,
    ProviderResponseFormat,
    ProviderResponseMetadata,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _payload() -> dict[str, object]:
    return {
        "response_type": "patch_proposal",
        "summary": "Modify app.",
        "assumptions": [],
        "patch_format": "structured_changes",
        "patch_payload": '{"changes":[]}',
        "affected_files": ["src/app.py"],
        "warnings": [],
        "changes": [
            {
                "path": "src/app.py",
                "operation": "modify",
                "explanation": "Modify app.",
                "new_content": "updated",
            }
        ],
    }


def _response(content: str) -> InferenceResponse:
    return InferenceResponse(
        new_inference_response_id(),
        new_inference_request_id(),
        new_task_id(),
        content,
        ProviderResponseFormat.PATCH_ENVELOPE,
        ProviderResponseMetadata(
            "provider",
            "adapter",
            "1",
            "model",
            "profile",
            NOW,
            NOW,
        ),
        None,
        ProviderExecutionMeasurements(1),
        ProviderFinishState.COMPLETED,
        ProviderDiagnostics(DiagnosticCollection()),
        NOW,
        ProviderFinishReason.NATURAL_COMPLETION,
    )


def _assert_rejected(content: str, code: str) -> None:
    with pytest.raises(ResponseEnvelopeValidationError) as captured:
        ProviderResponseEnvelopeValidator().validate(
            _response(content),
            patch_response_contract(),
        )

    assert str(captured.value.diagnostics[0].code) == code


def test_valid_envelope_is_canonicalized_and_bound_to_contract() -> None:
    result = ProviderResponseEnvelopeValidator().validate(
        _response(json.dumps(_payload())),
        patch_response_contract(),
    )

    assert result.response_type == "patch_proposal"
    assert tuple(map(str, result.affected_files)) == ("src/app.py",)
    assert result.canonical_json == json.dumps(
        _payload(),
        separators=(",", ":"),
        sort_keys=True,
    )


def test_invalid_json_is_rejected() -> None:
    _assert_rejected('{"response_type":', "PATCH_ENVELOPE_INVALID_JSON")


def test_missing_required_fields_are_rejected() -> None:
    payload = _payload()
    del payload["summary"]

    _assert_rejected(
        json.dumps(payload),
        "PATCH_ENVELOPE_MISSING_FIELDS",
    )


def test_wrong_response_type_is_rejected() -> None:
    payload = _payload()
    payload["response_type"] = "analysis"

    _assert_rejected(
        json.dumps(payload),
        "PATCH_ENVELOPE_WRONG_RESPONSE_TYPE",
    )


def test_unknown_patch_format_is_rejected() -> None:
    payload = _payload()
    payload["patch_format"] = "shell_script"

    _assert_rejected(
        json.dumps(payload),
        "PATCH_ENVELOPE_UNKNOWN_FORMAT",
    )


def test_inconsistent_affected_files_are_rejected() -> None:
    payload = _payload()
    payload["affected_files"] = ["src/other.py"]

    _assert_rejected(
        json.dumps(payload),
        "PATCH_ENVELOPE_INCONSISTENT_AFFECTED_FILES",
    )


def test_mixed_prose_and_json_is_rejected() -> None:
    _assert_rejected(
        f"Here is the patch:\n{json.dumps(_payload())}",
        "PATCH_ENVELOPE_INVALID_JSON",
    )


def test_validation_uses_the_exact_declared_contract() -> None:
    contract = replace(patch_response_contract(), response_type="different")

    with pytest.raises(ResponseEnvelopeValidationError):
        ProviderResponseEnvelopeValidator().validate(
            _response(json.dumps(_payload())),
            contract,
        )
