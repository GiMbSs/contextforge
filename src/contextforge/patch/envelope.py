"""Validation of untrusted provider response envelopes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import NoReturn

from contextforge.diagnostics import DiagnosticCode, DiagnosticSeverity
from contextforge.domain import ArtifactPath
from contextforge.patch.models import PatchDiagnostic
from contextforge.prompt import PatchPayloadFormat, ResponseContract
from contextforge.provider import InferenceResponse

MAX_PROVIDER_RESPONSE_BYTES = 1_000_000


@dataclass(frozen=True, slots=True)
class ValidatedResponseEnvelope:
    """Canonical JSON envelope accepted against one declared contract."""

    contract_id: str
    contract_version: str
    canonical_json: str
    response_type: str
    patch_format: PatchPayloadFormat
    affected_files: tuple[ArtifactPath, ...]


class ResponseEnvelopeValidationError(ValueError):
    """Failure containing normalized diagnostics safe for presentation."""

    def __init__(self, diagnostics: tuple[PatchDiagnostic, ...]) -> None:
        if not diagnostics:
            raise ValueError("diagnostics must not be empty")
        self.diagnostics = diagnostics
        super().__init__(diagnostics[0].message)


@dataclass(frozen=True, slots=True)
class ProviderResponseEnvelopeValidator:
    """Validate one provider response against its exact response contract."""

    def validate(
        self,
        response: InferenceResponse,
        contract: ResponseContract,
    ) -> ValidatedResponseEnvelope:
        """Reject any response that does not satisfy the declared envelope."""
        if not isinstance(response, InferenceResponse):
            raise TypeError("response must be an InferenceResponse")
        if not isinstance(contract, ResponseContract):
            raise TypeError("contract must be a ResponseContract")
        if len(response.content.encode("utf-8")) > MAX_PROVIDER_RESPONSE_BYTES:
            _reject(
                "PATCH_ENVELOPE_PAYLOAD_TOO_LARGE",
                "Provider response exceeds the maximum accepted payload size.",
            )

        payload = _decode_object(response.content)
        missing = tuple(field for field in contract.required_fields if field not in payload)
        if missing:
            _reject(
                "PATCH_ENVELOPE_MISSING_FIELDS",
                f"Response envelope is missing required fields: {', '.join(missing)}.",
            )

        response_type = payload.get("response_type")
        if response_type != contract.response_type:
            _reject(
                "PATCH_ENVELOPE_WRONG_RESPONSE_TYPE",
                "Response envelope type does not match the declared contract.",
            )

        patch_format_value = payload.get("patch_format")
        if not isinstance(patch_format_value, str):
            _reject(
                "PATCH_ENVELOPE_UNKNOWN_FORMAT",
                "Response envelope declares an unknown patch format.",
            )
        try:
            patch_format = PatchPayloadFormat(patch_format_value)
        except ValueError:
            _reject(
                "PATCH_ENVELOPE_UNKNOWN_FORMAT",
                "Response envelope declares an unknown patch format.",
            )

        _require_nonempty_text(payload, "summary")
        _require_text_sequence(payload, "assumptions")
        _require_text_sequence(payload, "warnings")
        _require_nonempty_text(payload, "patch_payload")
        affected_files = _affected_files(payload)
        _validate_declared_changes(payload, affected_files)

        return ValidatedResponseEnvelope(
            contract.contract_id,
            contract.version,
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            response_type,
            patch_format,
            affected_files,
        )


def _decode_object(content: str) -> dict[str, object]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        _reject(
            "PATCH_ENVELOPE_INVALID_JSON",
            "Provider response is not one complete JSON document.",
        )
    if not isinstance(payload, dict):
        _reject(
            "PATCH_ENVELOPE_INVALID_STRUCTURE",
            "Provider response envelope must be a JSON object.",
        )
    return payload


def _require_nonempty_text(payload: dict[str, object], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        _reject(
            "PATCH_ENVELOPE_INVALID_FIELD",
            f"Response envelope field '{field_name}' must be non-empty text.",
        )
    return value


def _require_text_sequence(payload: dict[str, object], field_name: str) -> tuple[str, ...]:
    value = payload.get(field_name)
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        _reject(
            "PATCH_ENVELOPE_INVALID_FIELD",
            f"Response envelope field '{field_name}' must be a list of non-empty text.",
        )
    return tuple(value)


def _affected_files(payload: dict[str, object]) -> tuple[ArtifactPath, ...]:
    values = payload.get("affected_files")
    if not isinstance(values, list) or not values:
        _reject(
            "PATCH_ENVELOPE_INVALID_AFFECTED_FILES",
            "Response envelope must declare affected files.",
        )
    try:
        paths = tuple(ArtifactPath(value) for value in values if isinstance(value, str))
    except ValueError:
        _reject(
            "PATCH_ENVELOPE_INVALID_AFFECTED_FILES",
            "Response envelope contains an invalid affected path.",
        )
    if len(paths) != len(values) or len(set(paths)) != len(paths):
        _reject(
            "PATCH_ENVELOPE_INVALID_AFFECTED_FILES",
            "Response envelope affected files must be unique project-relative paths.",
        )
    return paths


def _validate_declared_changes(
    payload: dict[str, object],
    affected_files: tuple[ArtifactPath, ...],
) -> None:
    changes = payload.get("changes")
    if changes is None:
        return
    if not isinstance(changes, list):
        _reject(
            "PATCH_ENVELOPE_INVALID_CHANGES",
            "Response envelope changes must be a list.",
        )
    declared: set[ArtifactPath] = set()
    for change in changes:
        if not isinstance(change, dict):
            _reject(
                "PATCH_ENVELOPE_INVALID_CHANGES",
                "Every declared change must be an object.",
            )
        for field_name in ("path", "destination_path"):
            value = change.get(field_name)
            if value is not None:
                if not isinstance(value, str):
                    _reject(
                        "PATCH_ENVELOPE_INVALID_CHANGES",
                        "Declared change paths must be text.",
                    )
                try:
                    declared.add(ArtifactPath(value))
                except ValueError:
                    _reject(
                        "PATCH_ENVELOPE_INVALID_CHANGES",
                        "Declared change contains an invalid project path.",
                    )
    if declared != set(affected_files):
        _reject(
            "PATCH_ENVELOPE_INCONSISTENT_AFFECTED_FILES",
            "Affected files do not exactly match declared changes.",
        )


def _reject(code: str, message: str) -> NoReturn:
    raise ResponseEnvelopeValidationError(
        (
            PatchDiagnostic(
                DiagnosticCode(code),
                DiagnosticSeverity.ERROR,
                message,
            ),
        )
    )
