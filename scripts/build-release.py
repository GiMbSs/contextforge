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
import gzip
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

REPRODUCIBLE_TIMESTAMP = 315532800


def _run_build(dist_dir: Path) -> list[Path]:
    """Clean dist/ and build without network-dependent isolation."""
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    environment = os.environ.copy()
    environment.setdefault("PYTHONHASHSEED", "0")
    environment.setdefault("SOURCE_DATE_EPOCH", str(REPRODUCIBLE_TIMESTAMP))
    subprocess.run(
        [sys.executable, "-m", "build", "--no-isolation"],
        check=True,
        env=environment,
    )
    artifacts = sorted(dist_dir.iterdir())
    for artifact in artifacts:
        if artifact.name.endswith(".tar.gz"):
            _normalize_sdist(artifact)
    return artifacts


def _normalize_sdist(path: Path) -> None:
    """Rewrite one source archive with stable gzip and tar metadata."""
    entries: list[tuple[tarfile.TarInfo, bytes | None]] = []
    with tarfile.open(path, "r:gz") as source:
        for member in source.getmembers():
            extracted = source.extractfile(member) if member.isfile() else None
            entries.append((member, extracted.read() if extracted is not None else None))

    temporary = path.with_name(f".{path.name}.tmp")
    with (
        temporary.open("wb") as raw,
        gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw,
            mtime=REPRODUCIBLE_TIMESTAMP,
        ) as compressed,
        tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as target,
    ):
        for member, content in entries:
            member.mtime = REPRODUCIBLE_TIMESTAMP
            member.uid = 0
            member.gid = 0
            member.uname = ""
            member.gname = ""
            member.pax_headers = {}
            target.addfile(member, None if content is None else io.BytesIO(content))
    temporary.replace(path)


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
        default="0.1.1",
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
