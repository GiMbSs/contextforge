#!/usr/bin/env python3
"""Build release artifacts for ContextForge.

This script produces:

- A wheel (.whl)
- A source distribution (.tar.gz)
- A SHA-256 checksum file for every artifact in dist/

It is intended to be run from the repository root after the quality gate
passes.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path


def _run_build(dist_dir: Path) -> list[Path]:
    """Clean dist/ and run ``python -m build``."""
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    subprocess.run(
        [sys.executable, "-m", "build"],
        check=True,
    )
    return sorted(dist_dir.iterdir())


def _sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_checksums(dist_dir: Path, version: str) -> Path:
    """Write a checksum file for all artifacts in dist/."""
    checksum_file = dist_dir / f"contextforge-{version}.checksums.txt"
    lines: list[str] = []
    for artifact in sorted(dist_dir.iterdir()):
        if artifact.name == checksum_file.name:
            continue
        if artifact.is_file():
            lines.append(f"{_sha256_file(artifact)}  {artifact.name}\n")
    checksum_file.write_text("".join(lines), encoding="utf-8")
    return checksum_file


def main() -> int:
    """Parse arguments and build release artifacts."""
    parser = argparse.ArgumentParser(
        description="Build ContextForge release artifacts and checksums.",
    )
    parser.add_argument(
        "--version",
        default="0.1.0",
        help="Release version used in the checksum file name.",
    )
    arguments = parser.parse_args()

    dist_dir = Path("dist")
    artifacts = _run_build(dist_dir)
    checksum_file = _write_checksums(dist_dir, arguments.version)

    print("Built artifacts:")
    for artifact in artifacts:
        print(f"  - {artifact}")
    print(f"  - {checksum_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
