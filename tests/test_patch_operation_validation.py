"""Tests for patch operation validation against trusted source state."""

import pytest

from contextforge.domain import ArtifactPath, ContentFingerprint
from contextforge.patch import (
    OperationValidationPolicy,
    PatchOperation,
    PatchOperationValidationError,
    PatchOperationValidator,
    PatchSourceArtifact,
    PatchSourceState,
    ProposedChange,
)

FINGERPRINT = ContentFingerprint("content_sha256_" + "a" * 64)


def _change(operation: PatchOperation, **overrides: object) -> ProposedChange:
    values: dict[str, object] = {
        "change_id": "change-1",
        "path": ArtifactPath("src/app.py"),
        "operation": operation,
        "explanation": "Apply the requested change.",
    }
    if operation in (PatchOperation.CREATE, PatchOperation.MODIFY):
        values["patch_payload"] = "new content\n"
    if operation is PatchOperation.RENAME:
        values["destination_path"] = ArtifactPath("src/renamed.py")
    if operation is not PatchOperation.CREATE:
        values["expected_old_fingerprint"] = FINGERPRINT
    values.update(overrides)
    return ProposedChange(**values)  # type: ignore[arg-type]


def _state(*paths: str) -> PatchSourceState:
    return PatchSourceState(
        tuple(PatchSourceArtifact(ArtifactPath(path), FINGERPRINT) for path in paths)
    )


def _assert_code(change: ProposedChange, state: PatchSourceState, code: str) -> None:
    with pytest.raises(PatchOperationValidationError) as captured:
        PatchOperationValidator().validate(change, state)
    diagnostic = captured.value.diagnostics[0]
    assert str(diagnostic.code) == code
    assert diagnostic.change_id == change.change_id


def test_create_requires_an_absent_target_by_default() -> None:
    _assert_code(
        _change(PatchOperation.CREATE),
        _state("src/app.py"),
        "PATCH_OPERATION_CREATE_EXISTS",
    )


def test_explicit_policy_can_allow_create_overwrite() -> None:
    change = _change(PatchOperation.CREATE)
    validator = PatchOperationValidator(OperationValidationPolicy(allow_create_overwrite=True))

    assert validator.validate(change, _state("src/app.py")) is change


@pytest.mark.parametrize(
    ("operation", "code"),
    (
        (PatchOperation.MODIFY, "PATCH_OPERATION_MODIFY_MISSING_SOURCE"),
        (PatchOperation.DELETE, "PATCH_OPERATION_DELETE_MISSING_SOURCE"),
        (PatchOperation.RENAME, "PATCH_OPERATION_RENAME_MISSING_SOURCE"),
    ),
)
def test_existing_artifact_operations_require_a_source(
    operation: PatchOperation, code: str
) -> None:
    _assert_code(_change(operation), PatchSourceState(), code)


def test_rename_requires_an_absent_destination() -> None:
    _assert_code(
        _change(PatchOperation.RENAME),
        _state("src/app.py", "src/renamed.py"),
        "PATCH_OPERATION_RENAME_TARGET_EXISTS",
    )


def test_expected_fingerprint_must_match_source_state() -> None:
    change = _change(
        PatchOperation.MODIFY,
        expected_old_fingerprint=ContentFingerprint("content_sha256_" + "b" * 64),
    )

    _assert_code(
        change,
        _state("src/app.py"),
        "PATCH_OPERATION_FINGERPRINT_MISMATCH",
    )


@pytest.mark.parametrize(
    "operation",
    (PatchOperation.MODIFY, PatchOperation.DELETE, PatchOperation.RENAME),
)
def test_valid_existing_artifact_operations_are_returned_unchanged(
    operation: PatchOperation,
) -> None:
    change = _change(operation)

    assert PatchOperationValidator().validate(change, _state("src/app.py")) is change


def test_absent_optional_fingerprint_does_not_invent_source_evidence() -> None:
    change = _change(PatchOperation.MODIFY, expected_old_fingerprint=None)

    assert PatchOperationValidator().validate(change, _state("src/app.py")) is change
