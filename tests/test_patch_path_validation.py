"""Tests for policy-aware patch path validation."""

import pytest

from contextforge.domain import ArtifactPath
from contextforge.patch import (
    PatchOperation,
    PatchPathValidationError,
    PatchPathValidator,
    ProtectedPathPolicy,
)


@pytest.mark.parametrize(
    "path",
    (
        "/etc/passwd",
        r"C:\Windows\system.ini",
        "../outside.py",
        r"\\server\share\file.py",
        r"\\?\C:\project\file.py",
    ),
)
def test_paths_outside_project_or_unsupported_roots_are_rejected(path: str) -> None:
    with pytest.raises(PatchPathValidationError):
        PatchPathValidator().validate(path, PatchOperation.MODIFY)


@pytest.mark.parametrize(
    "path",
    (
        "NUL",
        "src/COM1.txt",
        "src/file.py:secret",
        r"\\.\PhysicalDrive0",
    ),
)
def test_windows_device_and_stream_paths_are_rejected(path: str) -> None:
    with pytest.raises(PatchPathValidationError) as captured:
        PatchPathValidator().validate(path, PatchOperation.CREATE)

    assert str(captured.value.diagnostics[0].code) == "PATCH_PATH_UNSUPPORTED_DEVICE"


def test_paths_are_normalized_before_return() -> None:
    result = PatchPathValidator(ProtectedPathPolicy(forbid_protected_paths=False)).validate(
        "src/./package\\module.py", PatchOperation.MODIFY
    )

    assert result.source == ArtifactPath("src/package/module.py")


@pytest.mark.parametrize("path", (".git/config", ".env", "secrets/token.txt"))
def test_default_policy_rejects_protected_areas(path: str) -> None:
    with pytest.raises(PatchPathValidationError) as captured:
        PatchPathValidator().validate(path, PatchOperation.MODIFY)

    assert str(captured.value.diagnostics[0].code) == "PATCH_PATH_PROTECTED"


def test_policy_can_explicitly_allow_protected_paths() -> None:
    result = PatchPathValidator(ProtectedPathPolicy(forbid_protected_paths=False)).validate(
        ".env", PatchOperation.MODIFY
    )

    assert result.source == ArtifactPath(".env")


def test_rename_requires_distinct_source_and_destination() -> None:
    with pytest.raises(PatchPathValidationError, match="differ"):
        PatchPathValidator().validate(
            "src/app.py",
            PatchOperation.RENAME,
            "src/./app.py",
        )


def test_non_rename_rejects_destination_path() -> None:
    with pytest.raises(PatchPathValidationError, match="Only rename"):
        PatchPathValidator().validate(
            "src/app.py",
            PatchOperation.MODIFY,
            "src/new.py",
        )


def test_valid_rename_returns_both_canonical_paths() -> None:
    result = PatchPathValidator().validate(
        "src/old.py",
        PatchOperation.RENAME,
        "src/new.py",
    )

    assert result.source == ArtifactPath("src/old.py")
    assert result.destination == ArtifactPath("src/new.py")
