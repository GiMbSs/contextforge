"""Tests for the structured patch parser."""

import json

import pytest

from contextforge.domain import ArtifactPath
from contextforge.patch import (
    PatchOperation,
    StructuredPatchParseError,
    StructuredPatchParser,
    ValidatedResponseEnvelope,
)
from contextforge.prompt import PatchPayloadFormat

FINGERPRINT = "content_sha256_" + "a" * 64


def _change(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "path": "src/app.py",
        "operation": "modify",
        "explanation": "Update behavior.",
        "expected_old_fingerprint": FINGERPRINT,
        "new_content": "updated\n",
    }
    value.update(overrides)
    return value


def _envelope(changes: list[object], affected: tuple[str, ...] = ("src/app.py",)):
    patch_payload = json.dumps({"changes": changes}, separators=(",", ":"), sort_keys=True)
    outer = {
        "response_type": "patch_proposal",
        "summary": "Update.",
        "assumptions": [],
        "patch_format": "structured_changes",
        "patch_payload": patch_payload,
        "affected_files": list(affected),
        "warnings": [],
        "changes": changes,
    }
    return ValidatedResponseEnvelope(
        "patch-proposal-response",
        "v1",
        json.dumps(outer, separators=(",", ":"), sort_keys=True),
        "patch_proposal",
        PatchPayloadFormat.STRUCTURED_CHANGES,
        tuple(ArtifactPath(path) for path in affected),
    )


def _assert_rejected(changes: list[object], code: str) -> None:
    with pytest.raises(StructuredPatchParseError) as captured:
        StructuredPatchParser().parse(_envelope(changes))
    assert str(captured.value.diagnostics[0].code) == code


def test_parser_preserves_content_fingerprint_and_operation() -> None:
    (change,) = StructuredPatchParser().parse(_envelope([_change()]))

    assert change.operation is PatchOperation.MODIFY
    assert change.patch_payload == "updated\n"
    assert str(change.expected_old_fingerprint) == FINGERPRINT
    assert change.change_id.startswith("change_")


def test_unknown_operation_is_rejected() -> None:
    _assert_rejected(
        [_change(operation="execute")],
        "PATCH_STRUCTURED_UNSUPPORTED_OPERATION",
    )


def test_escaping_target_path_is_rejected() -> None:
    _assert_rejected(
        [_change(path="../outside.py")],
        "PATCH_STRUCTURED_INVALID_PATH",
    )


def test_rename_requires_source_destination_and_old_fingerprint() -> None:
    rename = _change(
        operation="rename",
        new_content=None,
        destination_path="src/renamed.py",
    )

    (change,) = StructuredPatchParser().parse(_envelope([rename], ("src/app.py", "src/renamed.py")))

    assert change.operation is PatchOperation.RENAME
    assert change.destination_path == ArtifactPath("src/renamed.py")


def test_missing_expected_old_fingerprint_is_rejected() -> None:
    change = _change()
    del change["expected_old_fingerprint"]

    _assert_rejected([change], "PATCH_STRUCTURED_MISSING_FINGERPRINT")


def test_create_requires_new_content_but_no_old_fingerprint() -> None:
    create = _change(
        operation="create",
        expected_old_fingerprint=None,
        new_content="",
    )

    (change,) = StructuredPatchParser().parse(_envelope([create]))

    assert change.operation is PatchOperation.CREATE
    assert change.patch_payload == ""
    assert change.expected_old_fingerprint is None


def test_missing_new_content_is_rejected() -> None:
    change = _change()
    del change["new_content"]

    _assert_rejected([change], "PATCH_STRUCTURED_MISSING_NEW_CONTENT")


def test_duplicate_target_operations_are_rejected() -> None:
    _assert_rejected(
        [_change(change_id="one"), _change(change_id="two")],
        "PATCH_STRUCTURED_DUPLICATE_OPERATION",
    )
