"""Strict, non-applying parser for unified diff payloads."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import NoReturn

from contextforge.diagnostics import DiagnosticCode, DiagnosticSeverity
from contextforge.domain import ArtifactPath
from contextforge.patch.envelope import ValidatedResponseEnvelope
from contextforge.patch.models import PatchDiagnostic, PatchOperation
from contextforge.prompt import PatchPayloadFormat

_HUNK_HEADER = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? "
    r"\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@(?P<section>.*)$"
)
_NO_NEWLINE_MARKER = r"\ No newline at end of file"


class UnifiedDiffLineKind(StrEnum):
    """Semantic kind of one line inside a unified diff hunk."""

    CONTEXT = "context"
    ADDITION = "addition"
    REMOVAL = "removal"


@dataclass(frozen=True, slots=True)
class UnifiedDiffLine:
    """One content line, preserving an adjacent no-newline marker."""

    kind: UnifiedDiffLineKind
    content: str
    no_newline_at_end: bool = False


@dataclass(frozen=True, slots=True)
class UnifiedDiffHunk:
    """One validated unified diff hunk."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int
    section: str
    lines: tuple[UnifiedDiffLine, ...]


@dataclass(frozen=True, slots=True)
class UnifiedFilePatch:
    """One normalized file operation represented by one or more hunks."""

    operation: PatchOperation
    path: ArtifactPath
    old_path: ArtifactPath | None
    new_path: ArtifactPath | None
    hunks: tuple[UnifiedDiffHunk, ...]


@dataclass(frozen=True, slots=True)
class UnifiedDiff:
    """Immutable parsed representation of a complete unified diff."""

    files: tuple[UnifiedFilePatch, ...]


class UnifiedDiffParseError(ValueError):
    """Normalized rejection of a malformed unified diff."""

    def __init__(self, diagnostics: tuple[PatchDiagnostic, ...]) -> None:
        if not diagnostics:
            raise ValueError("diagnostics must not be empty")
        self.diagnostics = diagnostics
        super().__init__(diagnostics[0].message)


@dataclass(frozen=True, slots=True)
class UnifiedDiffParser:
    """Parse unified diffs without filesystem access or patch application."""

    def parse(self, envelope: ValidatedResponseEnvelope) -> UnifiedDiff:
        """Parse and validate every file header and hunk in the payload."""
        if not isinstance(envelope, ValidatedResponseEnvelope):
            raise TypeError("envelope must be a ValidatedResponseEnvelope")
        if envelope.patch_format is not PatchPayloadFormat.UNIFIED_DIFF:
            _reject("PATCH_DIFF_WRONG_FORMAT", "Envelope is not a unified diff payload.")

        payload = _extract_patch_payload(envelope.canonical_json)
        lines = payload.splitlines()
        if not lines:
            _reject("PATCH_DIFF_EMPTY", "Unified diff payload must not be empty.")

        files: list[UnifiedFilePatch] = []
        position = 0
        while position < len(lines):
            while position < len(lines) and _is_file_metadata(lines[position]):
                position += 1
            if position >= len(lines):
                break
            if not lines[position].startswith("--- "):
                _reject(
                    "PATCH_DIFF_MALFORMED_FILE_HEADER",
                    "Unified diff file section must begin with an old-file header.",
                )
            old_path = _header_path(lines[position][4:])
            position += 1
            if position >= len(lines) or not lines[position].startswith("+++ "):
                _reject(
                    "PATCH_DIFF_MALFORMED_FILE_HEADER",
                    "Unified diff old-file header must be followed by a new-file header.",
                )
            new_path = _header_path(lines[position][4:])
            position += 1
            operation, path = _operation(old_path, new_path)

            hunks: list[UnifiedDiffHunk] = []
            while position < len(lines) and not lines[position].startswith("--- "):
                if _is_file_metadata(lines[position]):
                    break
                if not lines[position].startswith("@@ "):
                    _reject(
                        "PATCH_DIFF_MALFORMED_HUNK_HEADER",
                        "Unified diff file content must begin with a hunk header.",
                    )
                hunk, position = _parse_hunk(lines, position)
                hunks.append(hunk)
            if not hunks:
                _reject(
                    "PATCH_DIFF_MISSING_HUNK",
                    "Every unified diff file section must contain at least one hunk.",
                )
            files.append(
                UnifiedFilePatch(
                    operation,
                    path,
                    old_path,
                    new_path,
                    tuple(hunks),
                )
            )

        if not files:
            _reject("PATCH_DIFF_EMPTY", "Unified diff contains no file patches.")
        paths = tuple(file.path for file in files)
        if len(set(paths)) != len(paths):
            _reject(
                "PATCH_DIFF_DUPLICATE_FILE",
                "Unified diff contains repeated file sections.",
            )
        if set(paths) != set(envelope.affected_files):
            _reject(
                "PATCH_DIFF_INCONSISTENT_PATHS",
                "Unified diff files do not match the envelope affected files.",
            )
        return UnifiedDiff(tuple(files))


def _parse_hunk(lines: list[str], position: int) -> tuple[UnifiedDiffHunk, int]:
    match = _HUNK_HEADER.fullmatch(lines[position])
    if match is None:
        _reject(
            "PATCH_DIFF_MALFORMED_HUNK_HEADER",
            "Unified diff contains a malformed hunk header.",
        )
    old_start = int(match.group("old_start"))
    old_count = int(match.group("old_count") or "1")
    new_start = int(match.group("new_start"))
    new_count = int(match.group("new_count") or "1")
    position += 1
    parsed_lines: list[UnifiedDiffLine] = []
    while position < len(lines):
        line = lines[position]
        consumed_old = sum(
            item.kind in (UnifiedDiffLineKind.CONTEXT, UnifiedDiffLineKind.REMOVAL)
            for item in parsed_lines
        )
        consumed_new = sum(
            item.kind in (UnifiedDiffLineKind.CONTEXT, UnifiedDiffLineKind.ADDITION)
            for item in parsed_lines
        )
        counts_complete = consumed_old == old_count and consumed_new == new_count
        if line.startswith("@@ ") or _is_file_metadata(line):
            break
        if line.startswith("--- ") and counts_complete:
            break
        if line == _NO_NEWLINE_MARKER:
            if not parsed_lines or parsed_lines[-1].no_newline_at_end:
                _reject(
                    "PATCH_DIFF_INVALID_NEWLINE_MARKER",
                    "No-newline marker must follow exactly one hunk content line.",
                )
            parsed_lines[-1] = replace(parsed_lines[-1], no_newline_at_end=True)
            position += 1
            continue
        kind = {
            " ": UnifiedDiffLineKind.CONTEXT,
            "+": UnifiedDiffLineKind.ADDITION,
            "-": UnifiedDiffLineKind.REMOVAL,
        }.get(line[:1])
        if kind is None:
            _reject(
                "PATCH_DIFF_INVALID_HUNK_LINE",
                "Unified diff hunk contains an invalid line prefix.",
            )
        parsed_lines.append(UnifiedDiffLine(kind, line[1:]))
        position += 1

    actual_old = sum(
        line.kind in (UnifiedDiffLineKind.CONTEXT, UnifiedDiffLineKind.REMOVAL)
        for line in parsed_lines
    )
    actual_new = sum(
        line.kind in (UnifiedDiffLineKind.CONTEXT, UnifiedDiffLineKind.ADDITION)
        for line in parsed_lines
    )
    if actual_old != old_count or actual_new != new_count:
        _reject(
            "PATCH_DIFF_HUNK_COUNT_MISMATCH",
            "Unified diff hunk line counts do not match its header.",
        )
    return (
        UnifiedDiffHunk(
            old_start,
            old_count,
            new_start,
            new_count,
            match.group("section").lstrip(),
            tuple(parsed_lines),
        ),
        position,
    )


def _header_path(value: str) -> ArtifactPath | None:
    raw = value.split("\t", 1)[0]
    if raw == "/dev/null":
        return None
    if raw.startswith(("a/", "b/")):
        raw = raw[2:]
    try:
        return ArtifactPath(raw)
    except (TypeError, ValueError):
        _reject(
            "PATCH_DIFF_INVALID_PATH",
            "Unified diff contains a non-project-relative path.",
        )


def _operation(
    old_path: ArtifactPath | None,
    new_path: ArtifactPath | None,
) -> tuple[PatchOperation, ArtifactPath]:
    if old_path is None and new_path is None:
        _reject(
            "PATCH_DIFF_INVALID_OPERATION",
            "Unified diff cannot use /dev/null for both file headers.",
        )
    if old_path is None:
        assert new_path is not None
        return PatchOperation.CREATE, new_path
    if new_path is None:
        return PatchOperation.DELETE, old_path
    if old_path != new_path:
        _reject(
            "PATCH_DIFF_INVALID_OPERATION",
            "Unified diff modify headers must identify the same normalized path.",
        )
    return PatchOperation.MODIFY, old_path


def _is_file_metadata(line: str) -> bool:
    return line.startswith(
        (
            "diff --git ",
            "index ",
            "new file mode ",
            "deleted file mode ",
            "old mode ",
            "new mode ",
        )
    )


def _extract_patch_payload(canonical_json: str) -> str:
    import json

    try:
        outer = json.loads(canonical_json)
    except json.JSONDecodeError:
        _reject("PATCH_DIFF_INVALID_ENVELOPE", "Validated envelope is not JSON.")
    if not isinstance(outer, dict):
        _reject("PATCH_DIFF_INVALID_ENVELOPE", "Validated envelope must be an object.")
    payload = outer.get("patch_payload")
    if not isinstance(payload, str):
        _reject(
            "PATCH_DIFF_INVALID_ENVELOPE",
            "Validated envelope patch_payload must be text.",
        )
    return payload


def _reject(code: str, message: str) -> NoReturn:
    raise UnifiedDiffParseError(
        (
            PatchDiagnostic(
                DiagnosticCode(code),
                DiagnosticSeverity.ERROR,
                message,
            ),
        )
    )
