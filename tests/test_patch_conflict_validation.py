"""Tests for deterministic patch conflict and consistency validation."""

import pytest

from contextforge.domain import ArtifactPath, ProjectFingerprint
from contextforge.patch import (
    PatchConflictValidationError,
    PatchConflictValidator,
    PatchConsistencyEvidence,
    PatchOperation,
    ProposedChange,
)

FINGERPRINT = ProjectFingerprint("project_sha256_" + "a" * 64)
OTHER_FINGERPRINT = ProjectFingerprint("project_sha256_" + "b" * 64)


def _change(
    identifier: str,
    path: str,
    operation: PatchOperation = PatchOperation.MODIFY,
    destination: str | None = None,
) -> ProposedChange:
    return ProposedChange(
        identifier,
        ArtifactPath(path),
        operation,
        "Apply change.",
        patch_payload=(
            "content" if operation in (PatchOperation.CREATE, PatchOperation.MODIFY) else None
        ),
        destination_path=ArtifactPath(destination) if destination is not None else None,
    )


def _evidence(
    *paths: str,
    expected: ProjectFingerprint = FINGERPRINT,
    source: ProjectFingerprint = FINGERPRINT,
) -> PatchConsistencyEvidence:
    return PatchConsistencyEvidence(
        tuple(ArtifactPath(path) for path in paths),
        expected,
        source,
    )


def _codes(
    changes: tuple[ProposedChange, ...],
    evidence: PatchConsistencyEvidence,
) -> tuple[str, ...]:
    with pytest.raises(PatchConflictValidationError) as captured:
        PatchConflictValidator().validate(changes, evidence)
    return tuple(str(item.code) for item in captured.value.diagnostics)


def test_duplicate_operation_on_one_path_is_detected() -> None:
    changes = (
        _change("one", "app.py"),
        _change("two", "app.py"),
    )

    assert "PATCH_CONFLICT_DUPLICATE_OPERATION" in _codes(changes, _evidence("app.py"))


def test_modify_and_delete_on_one_path_are_incompatible() -> None:
    changes = (
        _change("modify", "app.py"),
        _change("delete", "app.py", PatchOperation.DELETE),
    )

    assert "PATCH_CONFLICT_INCOMPATIBLE_OPERATIONS" in _codes(changes, _evidence("app.py"))


def test_duplicate_change_identifiers_are_detected() -> None:
    changes = (
        _change("same", "a.py"),
        _change("same", "b.py"),
    )

    assert "PATCH_CONFLICT_DUPLICATE_CHANGE_ID" in _codes(changes, _evidence("a.py", "b.py"))


def test_multiple_renames_cannot_share_a_destination() -> None:
    changes = (
        _change("one", "a.py", PatchOperation.RENAME, "target.py"),
        _change("two", "b.py", PatchOperation.RENAME, "target.py"),
    )

    assert "PATCH_CONFLICT_RENAME_DESTINATION" in _codes(
        changes, _evidence("a.py", "b.py", "target.py")
    )


def test_rename_destination_cannot_be_changed_directly() -> None:
    changes = (
        _change("rename", "a.py", PatchOperation.RENAME, "target.py"),
        _change("modify", "target.py"),
    )

    assert "PATCH_CONFLICT_RENAME_DESTINATION" in _codes(changes, _evidence("a.py", "target.py"))


def test_rename_cycles_are_detected_once() -> None:
    changes = (
        _change("one", "a.py", PatchOperation.RENAME, "b.py"),
        _change("two", "b.py", PatchOperation.RENAME, "a.py"),
    )

    codes = _codes(changes, _evidence("a.py", "b.py"))

    assert codes.count("PATCH_CONFLICT_RENAME_CYCLE") == 1


def test_affected_file_list_must_match_all_sources_and_destinations() -> None:
    changes = (_change("rename", "a.py", PatchOperation.RENAME, "b.py"),)

    assert "PATCH_CONSISTENCY_AFFECTED_FILES_MISMATCH" in _codes(changes, _evidence("a.py"))


def test_project_fingerprint_must_match_source_state() -> None:
    changes = (_change("modify", "app.py"),)

    assert "PATCH_CONSISTENCY_PROJECT_FINGERPRINT_MISMATCH" in _codes(
        changes,
        _evidence("app.py", expected=FINGERPRINT, source=OTHER_FINGERPRINT),
    )


def test_valid_changes_are_returned_in_deterministic_path_order() -> None:
    changes = (
        _change("second", "b.py"),
        _change("first", "a.py", PatchOperation.CREATE),
    )

    result = PatchConflictValidator().validate(
        changes,
        _evidence("a.py", "b.py"),
    )

    assert tuple(str(change.path) for change in result) == ("a.py", "b.py")
