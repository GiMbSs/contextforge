"""Safe materialization of retrieval-selected source content."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from contextforge.context.models import ContextItem
from contextforge.domain import ArtifactId, ArtifactPath
from contextforge.retrieval import SelectedContextItem

if TYPE_CHECKING:
    from contextforge.context.ports import ContextContentSource


class ContextMaterializationError(ValueError):
    """Base error for content that cannot be safely materialized."""


class StaleContextContentError(ContextMaterializationError):
    """The selected source changed after retrieval."""


@dataclass(frozen=True, slots=True)
class SourceContent:
    """Exact bytes returned by a bounded, read-only content source."""

    content_reference: str
    content: bytes
    artifact_id: ArtifactId | None = None
    path: ArtifactPath | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.content_reference, str) or not self.content_reference.strip():
            raise ValueError("content_reference must not be empty")
        if not isinstance(self.content, bytes):
            raise TypeError("content must be bytes")
        if self.artifact_id is not None and not isinstance(self.artifact_id, ArtifactId):
            raise TypeError("artifact_id must be an ArtifactId")
        if self.path is not None and not isinstance(self.path, ArtifactPath):
            raise TypeError("path must be an ArtifactPath")
        if self.artifact_id is None and self.path is not None:
            raise ValueError("path requires artifact_id")


@dataclass(frozen=True, slots=True)
class ContextItemMaterializer:
    """Load and verify exactly the items selected by retrieval."""

    content_source: ContextContentSource

    def materialize(
        self,
        selected_items: tuple[SelectedContextItem, ...],
    ) -> tuple[ContextItem, ...]:
        """Materialize selected items in their retrieval order."""
        items = tuple(selected_items)
        if any(not isinstance(item, SelectedContextItem) for item in items):
            raise TypeError("selected_items must contain SelectedContextItem values")
        return tuple(self._materialize_item(item) for item in items)

    def _materialize_item(self, selected_item: SelectedContextItem) -> ContextItem:
        source = self.content_source.read(selected_item)
        if not isinstance(source, SourceContent):
            raise TypeError("content source must return SourceContent")
        if source.content_reference != selected_item.content_reference:
            raise ContextMaterializationError(
                "Content source returned a different content reference"
            )
        if source.artifact_id != selected_item.artifact_id:
            raise ContextMaterializationError("Content source returned a different artifact")

        expected_fingerprint = selected_item.content_fingerprint
        if expected_fingerprint is not None:
            actual_fingerprint = f"sha256:{hashlib.sha256(source.content).hexdigest()}"
            if actual_fingerprint != expected_fingerprint:
                raise StaleContextContentError(
                    f"Selected content is stale: {selected_item.content_reference}"
                )

        text = _decode_source(source.content)
        content = _select_source_span(text, selected_item)
        return ContextItem(
            selected_item=selected_item,
            source_reference=source.content_reference,
            content=content,
            source_path=source.path,
        )


def _decode_source(content: bytes) -> str:
    try:
        if content.startswith((b"\xff\xfe", b"\xfe\xff")):
            decoded = content.decode("utf-16")
        else:
            decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ContextMaterializationError(
            "Selected content is not valid UTF-8 or BOM-marked UTF-16"
        ) from error
    return decoded.replace("\r\n", "\n").replace("\r", "\n")


def _select_source_span(text: str, selected_item: SelectedContextItem) -> str:
    location = selected_item.location
    if location is None:
        return text

    lines = text.splitlines(keepends=True)
    if location.end_line > len(lines):
        raise ContextMaterializationError("Selected source line range is out of bounds")
    first = lines[location.start_line - 1]
    last = lines[location.end_line - 1]
    if location.start_column > len(first) + 1 or location.end_column > len(last):
        raise ContextMaterializationError("Selected source column range is out of bounds")

    selected_lines = lines[location.start_line - 1 : location.end_line]
    if len(selected_lines) == 1:
        return selected_lines[0][location.start_column - 1 : location.end_column]
    selected_lines[0] = selected_lines[0][location.start_column - 1 :]
    selected_lines[-1] = selected_lines[-1][: location.end_column]
    return "".join(selected_lines)
