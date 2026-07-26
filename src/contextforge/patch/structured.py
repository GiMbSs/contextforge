"""Parser for the safest machine-readable patch representation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import NoReturn

from contextforge.diagnostics import DiagnosticCode, DiagnosticSeverity
from contextforge.domain import ArtifactPath, ContentFingerprint
from contextforge.patch.envelope import ValidatedResponseEnvelope
from contextforge.patch.models import PatchDiagnostic, PatchOperation, ProposedChange
from contextforge.prompt import PatchPayloadFormat


class StructuredPatchParseError(ValueError):
    """Normalized rejection of an untrusted structured patch."""

    def __init__(self, diagnostics: tuple[PatchDiagnostic, ...]) -> None:
        if not diagnostics:
            raise ValueError("diagnostics must not be empty")
        self.diagnostics = diagnostics
        super().__init__(diagnostics[0].message)


@dataclass(frozen=True, slots=True)
class StructuredPatchParser:
    """Parse structured changes without reading or modifying project files."""

    def parse(self, envelope: ValidatedResponseEnvelope) -> tuple[ProposedChange, ...]:
        """Return deterministic immutable changes or reject the entire payload."""
        if not isinstance(envelope, ValidatedResponseEnvelope):
            raise TypeError("envelope must be a ValidatedResponseEnvelope")
        if envelope.patch_format is not PatchPayloadFormat.STRUCTURED_CHANGES:
            _reject(
                "PATCH_STRUCTURED_WRONG_FORMAT",
                "Envelope is not a structured changes payload.",
            )

        outer = _json_object(envelope.canonical_json, "envelope")
        embedded = _json_object(_required_text(outer, "patch_payload"), "patch payload")
        raw_changes = embedded.get("changes")
        if not isinstance(raw_changes, list) or not raw_changes:
            _reject(
                "PATCH_STRUCTURED_MISSING_CHANGES",
                "Structured patch must contain a non-empty changes list.",
            )
        if "changes" in outer and outer["changes"] != raw_changes:
            _reject(
                "PATCH_STRUCTURED_CONFLICTING_REPRESENTATIONS",
                "Envelope changes differ from the structured patch payload.",
            )

        changes = tuple(_parse_change(item) for item in raw_changes)
        paths = tuple(change.path for change in changes)
        if len(set(paths)) != len(paths):
            _reject(
                "PATCH_STRUCTURED_DUPLICATE_OPERATION",
                "Structured patch contains repeated operations for one target path.",
            )
        declared_paths = {
            path
            for change in changes
            for path in (change.path, change.destination_path)
            if path is not None
        }
        if declared_paths != set(envelope.affected_files):
            _reject(
                "PATCH_STRUCTURED_INCONSISTENT_PATHS",
                "Parsed changes do not match the envelope affected files.",
            )
        return tuple(sorted(changes, key=lambda change: str(change.path)))


def _parse_change(value: object) -> ProposedChange:
    if not isinstance(value, dict):
        _reject(
            "PATCH_STRUCTURED_INVALID_CHANGE",
            "Each structured change must be an object.",
        )
    path = _path(value, "path")
    operation_value = value.get("operation")
    if not isinstance(operation_value, str):
        _reject(
            "PATCH_STRUCTURED_UNSUPPORTED_OPERATION",
            "Structured change operation must be canonical text.",
        )
    try:
        operation = PatchOperation(operation_value)
    except ValueError:
        _reject(
            "PATCH_STRUCTURED_UNSUPPORTED_OPERATION",
            "Structured change uses an unsupported operation.",
        )

    explanation = _required_text(value, "explanation")
    assumptions = _text_sequence(value.get("assumptions", []), "assumptions")
    destination = (
        _path(value, "destination_path") if value.get("destination_path") is not None else None
    )
    new_content = value.get("new_content")
    if operation in (PatchOperation.CREATE, PatchOperation.MODIFY):
        if not isinstance(new_content, str):
            _reject(
                "PATCH_STRUCTURED_MISSING_NEW_CONTENT",
                "Create and modify operations require string new_content.",
            )
    elif new_content is not None:
        _reject(
            "PATCH_STRUCTURED_UNEXPECTED_NEW_CONTENT",
            "Delete and rename operations must not contain new_content.",
        )

    old_fingerprint_value = value.get("expected_old_fingerprint")
    expected_old_fingerprint: ContentFingerprint | None = None
    if operation is PatchOperation.CREATE:
        if old_fingerprint_value is not None:
            _reject(
                "PATCH_STRUCTURED_UNEXPECTED_FINGERPRINT",
                "Create operations must not declare an old fingerprint.",
            )
    else:
        if not isinstance(old_fingerprint_value, str):
            _reject(
                "PATCH_STRUCTURED_MISSING_FINGERPRINT",
                "Existing-artifact operations require expected_old_fingerprint.",
            )
        try:
            expected_old_fingerprint = ContentFingerprint(old_fingerprint_value)
        except ValueError:
            _reject(
                "PATCH_STRUCTURED_INVALID_FINGERPRINT",
                "Expected old fingerprint is not canonical.",
            )

    if operation is PatchOperation.RENAME and destination is None:
        _reject(
            "PATCH_STRUCTURED_MISSING_RENAME_SOURCE_OR_DESTINATION",
            "Rename requires source path and destination_path.",
        )
    if operation is not PatchOperation.RENAME and destination is not None:
        _reject(
            "PATCH_STRUCTURED_UNEXPECTED_DESTINATION",
            "Only rename operations may declare destination_path.",
        )

    canonical = json.dumps(value, separators=(",", ":"), sort_keys=True)
    change_id = value.get("change_id")
    if change_id is None:
        change_id = f"change_{hashlib.sha256(canonical.encode()).hexdigest()[:24]}"
    if not isinstance(change_id, str) or not change_id.strip():
        _reject(
            "PATCH_STRUCTURED_INVALID_CHANGE_ID",
            "Structured change identifier must be non-empty text.",
        )
    return ProposedChange(
        change_id=change_id,
        path=path,
        operation=operation,
        explanation=explanation,
        patch_payload=new_content,
        destination_path=destination,
        assumptions=assumptions,
        expected_old_fingerprint=expected_old_fingerprint,
    )


def _json_object(content: str, label: str) -> dict[str, object]:
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        _reject(
            "PATCH_STRUCTURED_INVALID_JSON",
            f"Structured {label} is not valid JSON.",
        )
    if not isinstance(value, dict):
        _reject(
            "PATCH_STRUCTURED_INVALID_STRUCTURE",
            f"Structured {label} must be an object.",
        )
    return value


def _required_text(value: dict[str, object], field_name: str) -> str:
    field = value.get(field_name)
    if not isinstance(field, str) or not field.strip():
        _reject(
            "PATCH_STRUCTURED_MISSING_FIELD",
            f"Structured patch field '{field_name}' must be non-empty text.",
        )
    return field


def _text_sequence(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        _reject(
            "PATCH_STRUCTURED_INVALID_FIELD",
            f"Structured patch field '{field_name}' must be a text list.",
        )
    return tuple(value)


def _path(value: dict[str, object], field_name: str) -> ArtifactPath:
    raw_path = value.get(field_name)
    if not isinstance(raw_path, str):
        _reject(
            "PATCH_STRUCTURED_INVALID_PATH",
            f"Structured change field '{field_name}' must be a path.",
        )
    try:
        return ArtifactPath(raw_path)
    except ValueError:
        _reject(
            "PATCH_STRUCTURED_INVALID_PATH",
            f"Structured change field '{field_name}' is not project-relative.",
        )


def _reject(code: str, message: str) -> NoReturn:
    raise StructuredPatchParseError(
        (
            PatchDiagnostic(
                DiagnosticCode(code),
                DiagnosticSeverity.ERROR,
                message,
            ),
        )
    )
