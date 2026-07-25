"""Tests for CF-014 increment I015 project root resolution."""

from pathlib import Path

import pytest

from contextforge.project import ProjectRootSource, resolve_project_root


def test_explicit_project_path_has_highest_precedence(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit"
    explicit.mkdir()
    nested_project = tmp_path / "other"
    nested_project.mkdir()
    (nested_project / ".contextforge").mkdir()

    result = resolve_project_root(
        explicit_project=explicit,
        working_directory=nested_project,
    )

    assert result.succeeded
    assert result.root is not None
    assert result.root.path == explicit.resolve()
    assert result.root.source is ProjectRootSource.EXPLICIT


def test_relative_explicit_path_is_resolved_against_working_directory(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()

    result = resolve_project_root(
        explicit_project="project",
        working_directory=tmp_path,
    )

    assert result.root is not None
    assert result.root.path == project.resolve()


def test_nearest_metadata_parent_wins_from_nested_directory(
    tmp_path: Path,
) -> None:
    outer = tmp_path / "outer"
    inner = outer / "inner"
    nested = inner / "src" / "package"
    nested.mkdir(parents=True)
    (outer / ".contextforge").mkdir()
    (inner / ".contextforge").mkdir()

    result = resolve_project_root(working_directory=nested)

    assert result.succeeded
    assert result.root is not None
    assert result.root.path == inner.resolve()
    assert result.root.source is ProjectRootSource.METADATA_PARENT


def test_valid_working_directory_is_fallback(tmp_path: Path) -> None:
    result = resolve_project_root(working_directory=tmp_path)

    assert result.succeeded
    assert result.root is not None
    assert result.root.path == tmp_path.resolve()
    assert result.root.source is ProjectRootSource.WORKING_DIRECTORY


def test_invalid_explicit_path_does_not_fall_back(tmp_path: Path) -> None:
    result = resolve_project_root(
        explicit_project="missing",
        working_directory=tmp_path,
    )

    assert not result.succeeded
    assert result.root is None
    assert str(next(iter(result.diagnostics)).code) == "CLI_PROJECT_NOT_FOUND"


def test_no_project_found_produces_stable_diagnostic(tmp_path: Path) -> None:
    missing = tmp_path / "missing"

    result = resolve_project_root(working_directory=missing)

    assert not result.succeeded
    assert result.root is None
    diagnostic = next(iter(result.diagnostics))
    assert str(diagnostic.code) == "CLI_PROJECT_NOT_FOUND"
    assert diagnostic.capability == "project_resolution"


def test_symlinked_working_directory_resolves_to_physical_project(
    tmp_path: Path,
) -> None:
    project = tmp_path / "physical-project"
    nested = project / "src"
    nested.mkdir(parents=True)
    (project / ".contextforge").mkdir()
    link = tmp_path / "linked-project"
    try:
        link.symlink_to(project, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"Directory symlinks are unavailable: {error}")

    result = resolve_project_root(working_directory=link / "src")

    assert result.succeeded
    assert result.root is not None
    assert result.root.path == project.resolve()
    assert result.root.source is ProjectRootSource.METADATA_PARENT


def test_explicit_regular_file_is_rejected(tmp_path: Path) -> None:
    file_path = tmp_path / "not-a-directory"
    file_path.write_text("content", encoding="utf-8")

    result = resolve_project_root(
        explicit_project=file_path,
        working_directory=tmp_path,
    )

    assert not result.succeeded
