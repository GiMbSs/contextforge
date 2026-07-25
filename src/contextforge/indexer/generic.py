"""Deterministic generic text indexing without language-specific semantics."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid5

from contextforge.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticCollection,
    DiagnosticLocation,
    DiagnosticSeverity,
)
from contextforge.indexer.models import (
    SearchUnit,
    SearchUnitKind,
    SourceLocation,
)
from contextforge.scanner import ProjectArtifact

GENERIC_TEXT_STRATEGY_VERSION = "generic-text-v1"
_SEARCH_UNIT_NAMESPACE = UUID("fb663d56-9511-522c-a37c-48d939731ab9")


@dataclass(frozen=True, slots=True)
class GenericTextIndexConfig:
    """Resource boundaries for generic UTF-8 text indexing."""

    max_content_bytes: int = 1_000_000
    max_search_unit_bytes: int = 4_096

    def __post_init__(self) -> None:
        for value, name in (
            (self.max_content_bytes, "max_content_bytes"),
            (self.max_search_unit_bytes, "max_search_unit_bytes"),
        ):
            if type(value) is not int:
                raise TypeError(f"{name} must be an integer")
            if value < 4:
                raise ValueError(f"{name} must be at least 4 bytes")


@dataclass(frozen=True, slots=True)
class GenericTextIndexResult:
    """Bounded generic units and any non-fatal indexing diagnostics."""

    search_units: tuple[SearchUnit, ...] = ()
    diagnostics: DiagnosticCollection = field(default_factory=DiagnosticCollection)
    indexed_bytes: int = 0
    truncated: bool = False

    def __post_init__(self) -> None:
        units = tuple(self.search_units)
        if any(not isinstance(unit, SearchUnit) for unit in units):
            raise TypeError("search_units must contain SearchUnit values")
        if not isinstance(self.diagnostics, DiagnosticCollection):
            raise TypeError("diagnostics must be a DiagnosticCollection")
        if type(self.indexed_bytes) is not int:
            raise TypeError("indexed_bytes must be an integer")
        if self.indexed_bytes < 0:
            raise ValueError("indexed_bytes must not be negative")
        if type(self.truncated) is not bool:
            raise TypeError("truncated must be a boolean")
        object.__setattr__(self, "search_units", units)


def _diagnostic(
    artifact: ProjectArtifact,
    code: str,
    message: str,
) -> Diagnostic:
    return Diagnostic(
        DiagnosticCode(code),
        DiagnosticSeverity.WARNING,
        message,
        "indexer",
        DiagnosticLocation(artifact.path.value),
    )


def _decode_bounded_utf8(content: bytes, limit: int) -> tuple[str, int, bool]:
    """Decode a valid UTF-8 prefix without cutting through a code point."""
    truncated = len(content) > limit
    prefix = content[:limit]
    while True:
        try:
            return prefix.decode("utf-8"), len(prefix), truncated
        except UnicodeDecodeError as error:
            if not truncated or error.end != len(prefix):
                raise
            prefix = prefix[: error.start]


def _split_by_utf8_size(text: str, maximum_bytes: int) -> tuple[tuple[str, int, int], ...]:
    """Return text fragments with one-based inclusive character columns."""
    fragments: list[tuple[str, int, int]] = []
    start = 0
    current_bytes = 0
    for position, character in enumerate(text):
        character_bytes = len(character.encode("utf-8"))
        if current_bytes and current_bytes + character_bytes > maximum_bytes:
            fragments.append((text[start:position], start + 1, position))
            start = position
            current_bytes = 0
        current_bytes += character_bytes
    if start < len(text):
        fragments.append((text[start:], start + 1, len(text)))
    return tuple(fragments)


@dataclass(frozen=True, slots=True)
class GenericTextIndexer:
    """Create line-based, byte-bounded Search Units from UTF-8 content."""

    configuration: GenericTextIndexConfig = field(default_factory=GenericTextIndexConfig)
    strategy_version: str = GENERIC_TEXT_STRATEGY_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, GenericTextIndexConfig):
            raise TypeError("configuration must be a GenericTextIndexConfig")
        if not self.strategy_version.strip():
            raise ValueError("strategy_version must not be empty")

    def index_artifact(
        self,
        artifact: ProjectArtifact,
        content: bytes,
    ) -> GenericTextIndexResult:
        """Index eligible bytes without inventing symbols or relationships."""
        if not isinstance(artifact, ProjectArtifact):
            raise TypeError("artifact must be a ProjectArtifact")
        if not isinstance(content, bytes):
            raise TypeError("content must be bytes")
        try:
            text, indexed_bytes, truncated = _decode_bounded_utf8(
                content,
                self.configuration.max_content_bytes,
            )
        except UnicodeDecodeError:
            return GenericTextIndexResult(
                diagnostics=DiagnosticCollection(
                    (
                        _diagnostic(
                            artifact,
                            "INDEX_UNSUPPORTED_ENCODING",
                            "Artifact content is not valid UTF-8 and was not indexed.",
                        ),
                    )
                )
            )

        units: list[SearchUnit] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            for fragment, start_column, end_column in _split_by_utf8_size(
                line,
                self.configuration.max_search_unit_bytes,
            ):
                location = SourceLocation(
                    artifact.artifact_id,
                    line_number,
                    start_column,
                    line_number,
                    end_column,
                )
                identity = uuid5(
                    _SEARCH_UNIT_NAMESPACE,
                    ":".join(
                        (
                            str(artifact.artifact_id),
                            self.strategy_version,
                            str(line_number),
                            str(start_column),
                            str(end_column),
                            fragment,
                        )
                    ),
                )
                units.append(
                    SearchUnit(
                        f"search_{identity.hex}",
                        artifact.artifact_id,
                        location,
                        SearchUnitKind.GENERIC_TEXT_BLOCK,
                        fragment,
                        len(units),
                    )
                )

        diagnostics = (
            (
                _diagnostic(
                    artifact,
                    "INDEX_CONTENT_LIMIT_REACHED",
                    "Artifact content exceeded the configured generic indexing limit.",
                ),
            )
            if truncated
            else ()
        )
        return GenericTextIndexResult(
            tuple(units),
            DiagnosticCollection(diagnostics),
            indexed_bytes,
            truncated,
        )
