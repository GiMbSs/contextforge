"""Tests for bounded, read-only context item materialization."""

import hashlib
from dataclasses import dataclass, replace

import pytest

from contextforge.context import (
    ContextItemMaterializer,
    ContextMaterializationError,
    SourceContent,
    StaleContextContentError,
)
from contextforge.domain import ArtifactPath, new_artifact_id
from contextforge.indexer import SourceLocation
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
    item_id: str,
    content: bytes,
    *,
    location: SourceLocation | None = None,
) -> SelectedContextItem:
    artifact_id = location.artifact_id if location is not None else new_artifact_id()
    candidate_id = f"candidate-{item_id}"
    rationale = SelectionRationale(
        candidate_id,
        SelectionDecision.SELECTED,
        SelectionReason.EXPLICIT_PATH_REFERENCE,
        (RetrievalEvidence("explicit", "task", item_id),),
    )
    return SelectedContextItem(
        item_id,
        candidate_id,
        artifact_id,
        f"artifact:{item_id}",
        CandidateType.SOURCE_EXCERPT,
        rationale,
        location=location,
        content_fingerprint=_fingerprint(content),
    )


@dataclass
class RecordingContentSource:
    sources: dict[str, SourceContent]

    def __post_init__(self) -> None:
        self.read_references: list[str] = []

    def read(self, selected_item: SelectedContextItem) -> SourceContent:
        self.read_references.append(selected_item.content_reference)
        return self.sources[selected_item.content_reference]


def test_materializer_reads_only_selected_items_and_preserves_order() -> None:
    first_bytes = b"first"
    second_bytes = b"second"
    unselected_bytes = b"unselected"
    first = _selected_item("item-1", first_bytes)
    second = _selected_item("item-2", second_bytes)
    source = RecordingContentSource(
        {
            first.content_reference: SourceContent(
                first.content_reference,
                first_bytes,
                first.artifact_id,
                ArtifactPath("src/first.py"),
            ),
            second.content_reference: SourceContent(
                second.content_reference,
                second_bytes,
                second.artifact_id,
                ArtifactPath("src/second.py"),
            ),
            "artifact:unselected": SourceContent("artifact:unselected", unselected_bytes),
        }
    )

    items = ContextItemMaterializer(source).materialize((second, first))

    assert source.read_references == ["artifact:item-2", "artifact:item-1"]
    assert tuple(item.context_item_id for item in items) == ("item-2", "item-1")
    assert items[0].source_path == ArtifactPath("src/second.py")


def test_materializer_verifies_fingerprint_before_decoding() -> None:
    selected = _selected_item("item-1", b"original")
    source = RecordingContentSource(
        {
            selected.content_reference: SourceContent(
                selected.content_reference,
                b"changed",
                selected.artifact_id,
            )
        }
    )

    with pytest.raises(StaleContextContentError, match="stale"):
        ContextItemMaterializer(source).materialize((selected,))


def test_materializer_preserves_selected_line_and_column_range() -> None:
    content = b"zero\r\nalpha\r\nbravo\r\nlast"
    artifact_id = new_artifact_id()
    location = SourceLocation(artifact_id, 2, 2, 3, 3)
    selected = _selected_item("item-1", content, location=location)
    source = RecordingContentSource(
        {
            selected.content_reference: SourceContent(
                selected.content_reference,
                content,
                artifact_id,
                ArtifactPath("src/example.py"),
            )
        }
    )

    item = ContextItemMaterializer(source).materialize((selected,))[0]

    assert item.content == "lpha\nbra"
    assert item.selected_item.location == location
    assert item.source_path == ArtifactPath("src/example.py")


def test_materializer_decodes_bom_marked_utf16_safely() -> None:
    content = "olá".encode("utf-16")
    selected = _selected_item("item-1", content)
    source = RecordingContentSource(
        {
            selected.content_reference: SourceContent(
                selected.content_reference,
                content,
                selected.artifact_id,
            )
        }
    )

    assert ContextItemMaterializer(source).materialize((selected,))[0].content == "olá"


def test_materializer_rejects_unsupported_encoding() -> None:
    content = b"\x80\x81"
    selected = _selected_item("item-1", content)
    source = RecordingContentSource(
        {
            selected.content_reference: SourceContent(
                selected.content_reference,
                content,
                selected.artifact_id,
            )
        }
    )

    with pytest.raises(ContextMaterializationError, match="UTF-8"):
        ContextItemMaterializer(source).materialize((selected,))


def test_materializer_rejects_source_identity_mismatch() -> None:
    content = b"content"
    selected = _selected_item("item-1", content)
    mismatched = SourceContent(
        selected.content_reference,
        content,
        new_artifact_id(),
    )

    with pytest.raises(ContextMaterializationError, match="different artifact"):
        ContextItemMaterializer(
            RecordingContentSource({selected.content_reference: mismatched})
        ).materialize((selected,))


def test_materializer_rejects_out_of_bounds_source_span() -> None:
    content = b"one line"
    selected = _selected_item("item-1", content)
    selected = replace(
        selected,
        location=SourceLocation(selected.artifact_id, 2, 1, 2, 1),  # type: ignore[arg-type]
    )
    source = RecordingContentSource(
        {
            selected.content_reference: SourceContent(
                selected.content_reference,
                content,
                selected.artifact_id,
            )
        }
    )

    with pytest.raises(ContextMaterializationError, match="out of bounds"):
        ContextItemMaterializer(source).materialize((selected,))
