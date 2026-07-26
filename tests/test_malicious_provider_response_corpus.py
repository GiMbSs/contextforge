"""Data-driven malicious provider-response hardening corpus."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

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
    StructuredPatchParseError,
    StructuredPatchParser,
)
from contextforge.patch.envelope import MAX_PROVIDER_RESPONSE_BYTES
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

CORPUS_PATH = Path(__file__).parent / "fixtures" / "malicious_provider_responses.json"
CORPUS = cast("dict[str, list[dict[str, object]]]", json.loads(CORPUS_PATH.read_text("utf-8")))
NOW = datetime(2026, 7, 26, tzinfo=UTC)
FINGERPRINT = "content_sha256_" + "a" * 64


def _change() -> dict[str, object]:
    return {
        "change_id": "change-1",
        "expected_old_fingerprint": FINGERPRINT,
        "explanation": "Update behavior.",
        "new_content": "updated\n",
        "operation": "modify",
        "path": "src/app.py",
    }


def _payload() -> dict[str, object]:
    changes = [_change()]
    return {
        "affected_files": ["src/app.py"],
        "assumptions": [],
        "changes": changes,
        "patch_format": "structured_changes",
        "patch_payload": json.dumps({"changes": changes}),
        "response_type": "patch_proposal",
        "summary": "Update behavior.",
        "warnings": [],
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


def _content(case: dict[str, object]) -> str:
    mutation = case["mutation"]
    if mutation == "raw":
        return str(case["value"])
    payload = _payload()
    if mutation == "path":
        path = str(case["value"])
        payload["affected_files"] = [path]
        cast("dict[str, object]", cast("list[object]", payload["changes"])[0])["path"] = path
    elif mutation == "duplicate_change":
        duplicate = _change()
        duplicate["change_id"] = "change-2"
        changes = cast("list[object]", payload["changes"])
        changes.append(duplicate)
        payload["patch_payload"] = json.dumps({"changes": changes})
    elif mutation == "oversized":
        payload["summary"] = "x" * MAX_PROVIDER_RESPONSE_BYTES
    else:
        payload[str(mutation)] = case["value"]
    return json.dumps(payload)


@pytest.mark.parametrize(
    "case",
    CORPUS["cases"],
    ids=lambda case: str(case["category"]),
)
def test_malicious_provider_response_corpus(case: dict[str, object]) -> None:
    content = _content(case)
    expected_stage = case["expected_stage"]
    validator = ProviderResponseEnvelopeValidator()

    if expected_stage == "envelope":
        with pytest.raises(ResponseEnvelopeValidationError) as captured:
            validator.validate(_response(content), patch_response_contract())
        assert str(captured.value.diagnostics[0].code) == case["expected_code"]
        return

    envelope = validator.validate(_response(content), patch_response_contract())
    if expected_stage == "structured":
        with pytest.raises(StructuredPatchParseError) as captured:
            StructuredPatchParser().parse(envelope)
        assert str(captured.value.diagnostics[0].code) == case["expected_code"]
        return

    changes = StructuredPatchParser().parse(envelope)
    assert len(changes) == 1
    assert str(case["value"]) in envelope.canonical_json
    assert not hasattr(changes[0], "tool_calls")
