"""Tests for strict non-applying unified diff parsing."""

import json

import pytest

from contextforge.domain import ArtifactPath
from contextforge.patch import (
    PatchOperation,
    UnifiedDiffLineKind,
    UnifiedDiffParseError,
    UnifiedDiffParser,
    ValidatedResponseEnvelope,
)
from contextforge.prompt import PatchPayloadFormat


def _envelope(payload: str, affected: tuple[str, ...]) -> ValidatedResponseEnvelope:
    outer = {
        "patch_payload": payload,
        "patch_format": "unified_diff",
        "response_type": "patch_proposal",
    }
    return ValidatedResponseEnvelope(
        "patch-proposal-response",
        "v1",
        json.dumps(outer, separators=(",", ":"), sort_keys=True),
        "patch_proposal",
        PatchPayloadFormat.UNIFIED_DIFF,
        tuple(ArtifactPath(path) for path in affected),
    )


def _assert_rejected(payload: str, affected: tuple[str, ...], code: str) -> None:
    with pytest.raises(UnifiedDiffParseError) as captured:
        UnifiedDiffParser().parse(_envelope(payload, affected))
    assert str(captured.value.diagnostics[0].code) == code


def test_multiple_files_and_hunks_are_preserved() -> None:
    payload = "\n".join(
        (
            "diff --git a/src/a.py b/src/a.py",
            "--- a/src/a.py",
            "+++ b/src/a.py",
            "@@ -1 +1 @@ first",
            "-old",
            "+new",
            "@@ -3,2 +3,2 @@ second",
            " context",
            "-before",
            "+after",
            "--- /dev/null",
            "+++ b/src/b.py",
            "@@ -0,0 +1,2 @@",
            "+one",
            "+two",
        )
    )

    result = UnifiedDiffParser().parse(_envelope(payload, ("src/a.py", "src/b.py")))

    assert len(result.files) == 2
    assert len(result.files[0].hunks) == 2
    assert result.files[0].operation is PatchOperation.MODIFY
    assert result.files[1].operation is PatchOperation.CREATE


def test_delete_marker_produces_delete_operation() -> None:
    payload = "\n".join(
        (
            "--- a/obsolete.py",
            "+++ /dev/null",
            "@@ -1 +0,0 @@",
            "-obsolete",
        )
    )

    result = UnifiedDiffParser().parse(_envelope(payload, ("obsolete.py",)))

    assert result.files[0].operation is PatchOperation.DELETE


def test_no_newline_marker_is_attached_to_preceding_line() -> None:
    payload = "\n".join(
        (
            "--- a/value.txt",
            "+++ b/value.txt",
            "@@ -1 +1 @@",
            "-old",
            r"\ No newline at end of file",
            "+new",
            r"\ No newline at end of file",
        )
    )

    result = UnifiedDiffParser().parse(_envelope(payload, ("value.txt",)))
    lines = result.files[0].hunks[0].lines

    assert lines[0].kind is UnifiedDiffLineKind.REMOVAL
    assert lines[0].no_newline_at_end
    assert lines[1].kind is UnifiedDiffLineKind.ADDITION
    assert lines[1].no_newline_at_end


def test_malformed_file_header_is_rejected() -> None:
    _assert_rejected(
        "--- a/file.py\n@@ -1 +1 @@\n-old\n+new",
        ("file.py",),
        "PATCH_DIFF_MALFORMED_FILE_HEADER",
    )


def test_malformed_hunk_header_is_rejected() -> None:
    _assert_rejected(
        "--- a/file.py\n+++ b/file.py\n@@ broken @@\n-old\n+new",
        ("file.py",),
        "PATCH_DIFF_MALFORMED_HUNK_HEADER",
    )


def test_hunk_counts_are_validated() -> None:
    _assert_rejected(
        "--- a/file.py\n+++ b/file.py\n@@ -1,2 +1 @@\n-old\n+new",
        ("file.py",),
        "PATCH_DIFF_HUNK_COUNT_MISMATCH",
    )


def test_paths_are_normalized_after_transport_prefixes() -> None:
    payload = "--- a/src/./app.py\n+++ b/src/app.py\n@@ -1 +1 @@\n-old\n+new"

    result = UnifiedDiffParser().parse(_envelope(payload, ("src/app.py",)))

    assert result.files[0].path == ArtifactPath("src/app.py")


def test_removed_content_that_resembles_a_file_header_is_preserved() -> None:
    payload = "--- a/file.txt\n+++ b/file.txt\n@@ -1 +1 @@\n--- old heading\n+++ new heading"

    result = UnifiedDiffParser().parse(_envelope(payload, ("file.txt",)))

    lines = result.files[0].hunks[0].lines
    assert lines[0].content == "-- old heading"
    assert lines[1].content == "++ new heading"


def test_parent_traversal_is_rejected() -> None:
    _assert_rejected(
        "--- a/../outside.py\n+++ b/../outside.py\n@@ -1 +1 @@\n-old\n+new",
        ("outside.py",),
        "PATCH_DIFF_INVALID_PATH",
    )
