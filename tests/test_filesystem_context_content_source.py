"""Tests for FilesystemContextContentSource."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from contextforge.context import (
    ContextMaterializationError,
    FilesystemContextContentSource,
)
from contextforge.domain import ArtifactId, ArtifactPath, new_artifact_id
from contextforge.retrieval import (
    CandidateType,
    RetrievalEvidence,
    SelectedContextItem,
    SelectionDecision,
    SelectionRationale,
    SelectionReason,
)


def _fingerprint(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _selected_item(
    reference: str,
    content: bytes | None = None,
    *,
    artifact_id: ArtifactId | None = None,
) -> SelectedContextItem:
    if artifact_id is None:
        artifact_id = new_artifact_id()
    candidate_id = f"candidate-{reference}"
    rationale = SelectionRationale(
        candidate_id=candidate_id,
        decision=SelectionDecision.SELECTED,
        primary_reason=SelectionReason.EXPLICIT_PATH_REFERENCE,
        evidence=(RetrievalEvidence("explicit", "task", reference),),
    )
    return SelectedContextItem(
        context_item_id=f"item-{reference}",
        candidate_id=candidate_id,
        artifact_id=artifact_id,
        content_reference=reference,
        candidate_type=CandidateType.FULL_ARTIFACT,
        rationale=rationale,
        content_fingerprint=_fingerprint(content) if content is not None else None,
    )


def test_reads_file_relative_to_project_root(tmp_path: Path) -> None:
    content = b"hello, world!"
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "example.py").write_bytes(content)
    source = FilesystemContextContentSource(tmp_path)
    item = _selected_item("src/example.py", content)

    result = source.read(item)

    assert result.content_reference == "src/example.py"
    assert result.content == content
    assert result.artifact_id == item.artifact_id
    assert result.path == ArtifactPath("src/example.py")


def test_missing_file_raises_materialization_error(tmp_path: Path) -> None:
    source = FilesystemContextContentSource(tmp_path)
    item = _selected_item("missing.py")

    with pytest.raises(ContextMaterializationError, match="Failed to read"):
        source.read(item)


def test_dotdot_reference_raises_materialization_error(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_bytes(b"outside content")
    source = FilesystemContextContentSource(tmp_path)
    item = _selected_item("../outside.txt")

    with pytest.raises(ContextMaterializationError, match="escapes project root"):
        source.read(item)


def test_absolute_reference_raises_materialization_error(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_bytes(b"outside content")
    source = FilesystemContextContentSource(tmp_path)
    item = _selected_item(str(outside))

    with pytest.raises(ContextMaterializationError, match="escapes project root"):
        source.read(item)
