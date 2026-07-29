"""Tests for release artifact generation."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def dist_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run the build-release script in a temporary copy and return dist/."""
    repo_root = Path(__file__).resolve().parent.parent
    work_dir = tmp_path / "repo"
    shutil.copytree(
        repo_root,
        work_dir,
        ignore=shutil.ignore_patterns(
            ".git",
            "__pycache__",
            "*.pyc",
            ".pytest_cache",
            ".mypy_cache",
            "dist",
            "build",
            ".venv",
            "venv",
        ),
    )
    stale_build = work_dir / "build"
    stale_build.mkdir()
    (stale_build / "__init__.py").write_text(
        'raise RuntimeError("stale local build package imported")\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(work_dir)
    result = subprocess.run(
        [sys.executable, str(work_dir / "scripts" / "build-release.py")],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Built artifacts:" in result.stdout
    return work_dir / "dist"


def _artifact(dist_dir: Path, suffix: str) -> Path:
    """Return exactly one artifact with the requested suffix."""
    candidates = [path for path in dist_dir.iterdir() if path.suffix == suffix]
    assert len(candidates) == 1, f"expected one {suffix} artifact, got {candidates}"
    return candidates[0]


def test_builds_wheel(dist_dir: Path) -> None:
    """A wheel is produced."""
    wheel = _artifact(dist_dir, ".whl")
    assert wheel.name.startswith("contextforge-")


def test_builds_source_distribution(dist_dir: Path) -> None:
    """A source distribution is produced."""
    sdist = _artifact(dist_dir, ".gz")
    assert sdist.name.startswith("contextforge-")
    assert sdist.name.endswith(".tar.gz")


def test_checksum_file_matches_artifacts(dist_dir: Path) -> None:
    """The checksum file contains valid SHA-256 hashes for every artifact."""
    checksum_file = [path for path in dist_dir.iterdir() if path.suffix == ".txt"]
    assert len(checksum_file) == 1
    checksums = {
        line.split()[1]: line.split()[0]
        for line in checksum_file[0].read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    for artifact in dist_dir.iterdir():
        if artifact.name == checksum_file[0].name:
            continue
        assert artifact.name in checksums, f"missing checksum for {artifact.name}"
        expected = hashlib.sha256(artifact.read_bytes()).hexdigest()
        assert checksums[artifact.name] == expected


def test_release_build_is_reproducible_offline(tmp_path: Path) -> None:
    """Two network-independent builds produce identical package hashes."""
    repo_root = Path(__file__).resolve().parent.parent
    work_dir = tmp_path / "repo"
    shutil.copytree(
        repo_root,
        work_dir,
        ignore=shutil.ignore_patterns(
            ".git",
            "__pycache__",
            "*.pyc",
            ".pytest_cache",
            ".mypy_cache",
            "dist",
            "build",
            ".venv",
            "venv",
        ),
    )
    stale_build = work_dir / "build"
    stale_build.mkdir()
    (stale_build / "__init__.py").write_text(
        'raise RuntimeError("stale local build package imported")\n',
        encoding="utf-8",
    )
    command = [sys.executable, str(work_dir / "scripts" / "build-release.py")]
    environment = {"PATH": "", "PYTHONHASHSEED": "0", "SOURCE_DATE_EPOCH": "315532800"}

    subprocess.run(
        command,
        cwd=work_dir,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    first = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (work_dir / "dist").iterdir()
        if path.suffix in {".whl", ".gz"}
    }
    subprocess.run(
        command,
        cwd=work_dir,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    second = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (work_dir / "dist").iterdir()
        if path.suffix in {".whl", ".gz"}
    }

    assert first == second
