"""Security tests for CF-014 increment I018 safe filesystem traversal."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from contextforge.adapters.filesystem import LocalProjectTraversal
from contextforge.configuration import ScannerConfig
from contextforge.project import ProjectRoot, ProjectRootSource
from contextforge.scanner import IgnorePolicy, TraversalEntryType


def traverse(
    root_path: Path,
    *,
    configuration: ScannerConfig | None = None,
    policy: IgnorePolicy | None = None,
):
    config = configuration or ScannerConfig(use_default_exclusions=False)
    ignore_policy = policy or IgnorePolicy.from_inputs(config)
    root = ProjectRoot(root_path.resolve(), ProjectRootSource.EXPLICIT)
    return LocalProjectTraversal().traverse(root, config, ignore_policy)


def diagnostic_codes(result: object) -> tuple[str, ...]:
    return tuple(str(item.code) for item in result.diagnostics)  # type: ignore[attr-defined]


def create_directory_symlink(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"Directory symlinks are unavailable: {error}")


def test_traversal_returns_deterministic_canonical_order(tmp_path: Path) -> None:
    (tmp_path / "zeta").mkdir()
    (tmp_path / "alpha").mkdir()
    (tmp_path / "zeta" / "last.py").write_text("", encoding="utf-8")
    (tmp_path / "alpha" / "first.py").write_text("", encoding="utf-8")
    (tmp_path / "middle.py").write_text("", encoding="utf-8")

    first = traverse(tmp_path)
    second = traverse(tmp_path)

    paths = tuple(entry.path.value for entry in first.entries)
    assert paths == tuple(sorted(paths))
    assert first.entries == second.entries


def test_default_policy_prunes_git_venv_and_build_outputs(tmp_path: Path) -> None:
    for directory in (".git", ".venv", "build"):
        target = tmp_path / directory
        target.mkdir()
        (target / "ignored.txt").write_text("ignored", encoding="utf-8")
    (tmp_path / "included.py").write_text("included", encoding="utf-8")
    configuration = ScannerConfig()

    result = traverse(
        tmp_path,
        configuration=configuration,
        policy=IgnorePolicy.from_inputs(configuration),
    )

    assert tuple(entry.path.value for entry in result.entries) == ("included.py",)


def test_include_override_can_reach_child_of_excluded_directory(
    tmp_path: Path,
) -> None:
    build = tmp_path / "build"
    build.mkdir()
    (build / "keep.txt").write_text("keep", encoding="utf-8")
    (build / "drop.txt").write_text("drop", encoding="utf-8")
    configuration = ScannerConfig()
    policy = IgnorePolicy.from_inputs(
        configuration,
        user_inclusions=("build/keep.txt",),
    )

    result = traverse(tmp_path, configuration=configuration, policy=policy)

    assert tuple(entry.path.value for entry in result.entries) == ("build/keep.txt",)


def test_traversal_does_not_read_file_contents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "source.py").write_text("raise RuntimeError", encoding="utf-8")

    def fail_read(*args: object, **kwargs: object) -> bytes:
        pytest.fail(f"Traversal attempted content read: {args!r} {kwargs!r}")

    monkeypatch.setattr(Path, "read_bytes", fail_read)
    monkeypatch.setattr(Path, "read_text", fail_read)

    result = traverse(tmp_path)

    assert tuple(entry.path.value for entry in result.entries) == ("source.py",)


def test_symlink_is_skipped_by_default(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "data.txt").write_text("data", encoding="utf-8")
    create_directory_symlink(tmp_path / "link", target)

    result = traverse(tmp_path)

    assert "SCAN_SYMLINK_SKIPPED" in diagnostic_codes(result)
    assert "link" not in {entry.path.value for entry in result.entries}


def test_symlink_to_parent_is_detected_as_cycle(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    create_directory_symlink(nested / "parent", tmp_path)

    result = traverse(
        tmp_path,
        configuration=ScannerConfig(
            follow_symlinks=True,
            use_default_exclusions=False,
        ),
    )

    assert "SCAN_CYCLE_DETECTED" in diagnostic_codes(result)


def test_symlink_to_external_directory_never_escapes_root(tmp_path: Path) -> None:
    project = tmp_path / "project"
    external = tmp_path / "external"
    project.mkdir()
    external.mkdir()
    (external / "secret.txt").write_text("secret", encoding="utf-8")
    create_directory_symlink(project / "outside", external)

    result = traverse(
        project,
        configuration=ScannerConfig(
            follow_symlinks=True,
            use_default_exclusions=False,
        ),
    )

    assert "SCAN_SYMLINK_OUTSIDE_ROOT" in diagnostic_codes(result)
    assert all("secret.txt" not in entry.path.value for entry in result.entries)


def test_cyclic_symlink_does_not_recurse_forever(tmp_path: Path) -> None:
    directory = tmp_path / "directory"
    directory.mkdir()
    create_directory_symlink(directory / "self", directory)

    result = traverse(
        tmp_path,
        configuration=ScannerConfig(
            follow_symlinks=True,
            use_default_exclusions=False,
        ),
    )

    assert "SCAN_CYCLE_DETECTED" in diagnostic_codes(result)
    assert len(result.entries) < 5


def test_unreadable_descendant_produces_incomplete_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    original_scandir = os.scandir

    def controlled_scandir(path: os.PathLike[str]):
        if Path(path).name == "locked":
            raise PermissionError("denied")
        return original_scandir(path)

    monkeypatch.setattr(
        "contextforge.adapters.filesystem.local.os.scandir",
        controlled_scandir,
    )

    result = traverse(tmp_path)

    assert not result.is_complete
    assert "SCAN_PATH_UNREADABLE" in diagnostic_codes(result)
    assert result.statistics.unreadable_paths == 1


def test_deep_nesting_uses_bounded_iterative_traversal(tmp_path: Path) -> None:
    current = tmp_path
    for index in range(60):
        current = current / f"d{index}"
        current.mkdir()
    (current / "deep.py").write_text("", encoding="utf-8")

    result = traverse(tmp_path)

    assert result.is_complete
    assert any(entry.path.value.endswith("deep.py") for entry in result.entries)
    assert result.statistics.directories_visited == 61


def test_maximum_depth_includes_boundary_but_does_not_descend(
    tmp_path: Path,
) -> None:
    level_one = tmp_path / "one"
    level_two = level_one / "two"
    level_two.mkdir(parents=True)
    (level_two / "hidden.py").write_text("", encoding="utf-8")

    result = traverse(
        tmp_path,
        configuration=ScannerConfig(
            max_depth=1,
            use_default_exclusions=False,
        ),
    )

    assert tuple(entry.path.value for entry in result.entries) == ("one",)
    assert result.entries[0].entry_type is TraversalEntryType.DIRECTORY
    assert "SCAN_MAX_DEPTH_REACHED" in diagnostic_codes(result)


def test_missing_root_returns_terminal_diagnostic(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    root = ProjectRoot(missing.absolute(), ProjectRootSource.EXPLICIT)
    configuration = ScannerConfig(use_default_exclusions=False)

    result = LocalProjectTraversal().traverse(
        root,
        configuration,
        IgnorePolicy.from_inputs(configuration),
    )

    assert not result.is_complete
    assert result.entries == ()
    assert diagnostic_codes(result) == ("SCAN_ROOT_NOT_FOUND",)
