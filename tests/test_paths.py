"""Tests for CF-014 increment I014 canonical project-relative paths."""

from dataclasses import FrozenInstanceError

import pytest

from contextforge.domain import ArtifactPath, ProjectPath


@pytest.mark.parametrize(
    ("external", "canonical"),
    [
        ("src/contextforge/main.py", "src/contextforge/main.py"),
        (r"src\contextforge\main.py", "src/contextforge/main.py"),
        (r"src\contextforge/tests\test_main.py", "src/contextforge/tests/test_main.py"),
        ("src//contextforge///main.py", "src/contextforge/main.py"),
        ("./src/./contextforge/./main.py", "src/contextforge/main.py"),
        ("src/contextforge/", "src/contextforge"),
    ],
)
def test_posix_and_windows_inputs_have_canonical_separator(
    external: str,
    canonical: str,
) -> None:
    assert str(ProjectPath(external)) == canonical
    assert str(ArtifactPath(external)) == canonical


@pytest.mark.parametrize(
    "external",
    [
        "../secret.txt",
        "src/../secret.txt",
        r"src\..\secret.txt",
        "src/nested/../../secret.txt",
    ],
)
def test_parent_traversal_is_always_rejected(external: str) -> None:
    with pytest.raises(ValueError, match="Parent traversal"):
        ProjectPath(external)
    with pytest.raises(ValueError, match="Parent traversal"):
        ArtifactPath(external)


@pytest.mark.parametrize(
    "external",
    [
        "/etc/passwd",
        r"\Windows\System32",
        "C:/Windows/System32",
        r"c:relative\but-drive-qualified",
        r"\\server\share\file.py",
        "//server/share/file.py",
        r"\\?\C:\project\file.py",
    ],
)
def test_absolute_drive_and_unc_paths_are_rejected(external: str) -> None:
    with pytest.raises(ValueError, match="project-relative"):
        ProjectPath(external)


def test_project_root_empty_path_policy_is_explicit() -> None:
    assert ProjectPath("").is_root
    assert ProjectPath(".").is_root
    assert ProjectPath("///".lstrip("/")).is_root
    assert ProjectPath("").parts == ()


@pytest.mark.parametrize("external", ["", ".", "./", "////".lstrip("/")])
def test_artifact_path_rejects_empty_normalized_path(external: str) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        ArtifactPath(external)


def test_unicode_is_supported_and_normalized_to_nfc() -> None:
    composed = ArtifactPath("documentação/café.md")
    decomposed = ArtifactPath("documentac\u0327a\u0303o/cafe\u0301.md")

    assert composed == decomposed
    assert str(decomposed) == "documentação/café.md"


def test_nul_is_rejected() -> None:
    with pytest.raises(ValueError, match="NUL"):
        ProjectPath("src/\x00hidden.py")


def test_path_preserves_valid_spaces_and_reserved_posix_characters() -> None:
    path = ArtifactPath("docs/file name: draft?.md")

    assert str(path) == "docs/file name: draft?.md"


def test_paths_round_trip_from_canonical_string() -> None:
    path = ArtifactPath.from_string(r"src\main.py")

    assert ArtifactPath.from_string(str(path)) == path
    assert path.parts == ("src", "main.py")


def test_paths_are_immutable() -> None:
    path = ProjectPath("src")

    with pytest.raises(FrozenInstanceError):
        path.value = "tests"  # type: ignore[misc]
