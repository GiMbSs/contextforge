"""Filesystem-backed context content source."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from contextforge.context.materialization import (
    ContextMaterializationError,
    SourceContent,
)
from contextforge.domain import ArtifactId, ArtifactPath
from contextforge.retrieval import SelectedContextItem


@dataclass(slots=True)
class FilesystemContextContentSource:
    """Read selected context items from a project root directory."""

    _root: Path

    def __post_init__(self) -> None:
        if not isinstance(self._root, Path):
            raise TypeError("root must be a pathlib.Path")
        self._root = self._root.resolve()

    def read(self, selected_item: SelectedContextItem) -> SourceContent:
        """Return the exact source bytes for one selected item."""
        reference = selected_item.content_reference
        try:
            target = self._root.joinpath(*Path(reference).parts).resolve()
            target.relative_to(self._root)
        except (ValueError, OSError) as error:
            raise ContextMaterializationError(
                f"Content reference escapes project root: {reference}"
            ) from error

        try:
            content = target.read_bytes()
        except OSError as error:
            raise ContextMaterializationError(
                f"Failed to read content reference: {reference}"
            ) from error

        path = self._artifact_path_for(reference, selected_item.artifact_id)
        return SourceContent(
            content_reference=reference,
            content=content,
            artifact_id=selected_item.artifact_id,
            path=path,
        )

    def _artifact_path_for(
        self, reference: str, artifact_id: ArtifactId | None
    ) -> ArtifactPath | None:
        if artifact_id is None:
            return None
        try:
            return ArtifactPath(reference)
        except (TypeError, ValueError):
            return None
