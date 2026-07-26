"""Immutable contracts for materialized Context Bundles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from contextforge.diagnostics import DiagnosticCollection
from contextforge.domain import (
    ArtifactPath,
    ContextBundleId,
    ProjectFingerprint,
    ProjectId,
    RetrievalId,
    TaskId,
)
from contextforge.retrieval import SelectedContextItem


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_identifier(value: str, field_name: str) -> None:
    _require_text(value, field_name)
    if any(character.isspace() for character in value):
        raise ValueError(f"{field_name} must not contain whitespace")


class ContextSectionKind(StrEnum):
    """Stable semantic groups available to bundle consumers."""

    USER_CONTENT = "user_content"
    EXPLICIT_REFERENCE = "explicit_reference"
    PRIMARY_IMPLEMENTATION = "primary_implementation"
    SUPPORTING_DECLARATION = "supporting_declaration"
    CONFIGURATION = "configuration"
    TEST = "test"
    DOCUMENTATION = "documentation"
    OTHER = "other"


class CoverageStatus(StrEnum):
    """Degree to which one requested context dimension is represented."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, slots=True)
class ContextItem:
    """Materialized content that retains its retrieval provenance."""

    selected_item: SelectedContextItem
    source_reference: str
    content: str
    source_path: ArtifactPath | None = None
    verified_source_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.selected_item, SelectedContextItem):
            raise TypeError("selected_item must be a SelectedContextItem")
        _require_text(self.source_reference, "source_reference")
        if not isinstance(self.content, str):
            raise TypeError("content must be a string")
        if self.source_path is not None and not isinstance(self.source_path, ArtifactPath):
            raise TypeError("source_path must be an ArtifactPath")
        if self.selected_item.artifact_id is None and self.source_path is not None:
            raise ValueError("source_path requires an artifact-backed selected item")
        if self.verified_source_fingerprint is not None and not (
            self.verified_source_fingerprint.startswith("sha256:")
            and len(self.verified_source_fingerprint) == 71
        ):
            raise ValueError("verified_source_fingerprint must use SHA-256")

    @property
    def context_item_id(self) -> str:
        """Return the identity assigned by retrieval."""
        return self.selected_item.context_item_id


@dataclass(frozen=True, slots=True)
class ContextSection:
    """An ordered semantic grouping of Context Items."""

    section_id: str
    kind: ContextSectionKind
    title: str
    item_ids: tuple[str, ...]
    order: int

    def __post_init__(self) -> None:
        _require_identifier(self.section_id, "section_id")
        if not isinstance(self.kind, ContextSectionKind):
            raise TypeError("kind must be a ContextSectionKind")
        _require_text(self.title, "title")
        item_ids = tuple(self.item_ids)
        if not item_ids:
            raise ValueError("Context Section must contain at least one item")
        for item_id in item_ids:
            _require_identifier(item_id, "item_id")
        if len(set(item_ids)) != len(item_ids):
            raise ValueError("Context Section item identifiers must be unique")
        if type(self.order) is not int:
            raise TypeError("order must be an integer")
        if self.order < 0:
            raise ValueError("order must not be negative")
        object.__setattr__(self, "item_ids", item_ids)


@dataclass(frozen=True, slots=True)
class ContextStatistics:
    """Deterministic measurements of one Context Bundle."""

    item_count: int = 0
    artifact_count: int = 0
    excerpt_count: int = 0
    symbol_count: int = 0
    relationship_count: int = 0
    documentation_count: int = 0
    test_count: int = 0
    configuration_count: int = 0
    generated_count: int = 0
    character_count: int = 0
    byte_count: int = 0
    line_count: int = 0
    estimated_tokens: int = 0

    def __post_init__(self) -> None:
        values = tuple(getattr(self, field_name) for field_name in self.__dataclass_fields__)
        if any(type(value) is not int for value in values):
            raise TypeError("Context statistics must be integers")
        if any(value < 0 for value in values):
            raise ValueError("Context statistics must not be negative")


@dataclass(frozen=True, slots=True)
class ContextCoverage:
    """Coverage assessment for task-relevant context dimensions."""

    targets: CoverageStatus = CoverageStatus.NOT_APPLICABLE
    dependencies: CoverageStatus = CoverageStatus.NOT_APPLICABLE
    interfaces: CoverageStatus = CoverageStatus.NOT_APPLICABLE
    tests: CoverageStatus = CoverageStatus.NOT_APPLICABLE
    configuration: CoverageStatus = CoverageStatus.NOT_APPLICABLE
    constraints: CoverageStatus = CoverageStatus.NOT_APPLICABLE
    error_locations: CoverageStatus = CoverageStatus.NOT_APPLICABLE
    missing_references: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "targets",
            "dependencies",
            "interfaces",
            "tests",
            "configuration",
            "constraints",
            "error_locations",
        ):
            if not isinstance(getattr(self, field_name), CoverageStatus):
                raise TypeError(f"{field_name} must be a CoverageStatus")
        missing_references = tuple(self.missing_references)
        if any(not isinstance(value, str) or not value.strip() for value in missing_references):
            raise ValueError("missing_references must contain non-empty strings")
        if len(set(missing_references)) != len(missing_references):
            raise ValueError("missing_references must be unique")
        object.__setattr__(self, "missing_references", missing_references)


@dataclass(frozen=True, slots=True)
class ContextBundle:
    """Immutable, traceable output of Context Bundle construction."""

    bundle_id: ContextBundleId
    task_id: TaskId
    retrieval_id: RetrievalId
    project_id: ProjectId
    project_fingerprint: ProjectFingerprint
    items: tuple[ContextItem, ...]
    source_selected_item_ids: tuple[str, ...]
    sections: tuple[ContextSection, ...]
    statistics: ContextStatistics
    coverage: ContextCoverage
    diagnostics: DiagnosticCollection
    bundle_version: str
    builder_version: str
    created_at: datetime

    def __post_init__(self) -> None:
        for value, expected_type, field_name in (
            (self.bundle_id, ContextBundleId, "bundle_id"),
            (self.task_id, TaskId, "task_id"),
            (self.retrieval_id, RetrievalId, "retrieval_id"),
            (self.project_id, ProjectId, "project_id"),
            (self.project_fingerprint, ProjectFingerprint, "project_fingerprint"),
        ):
            if not isinstance(value, expected_type):
                raise TypeError(f"{field_name} must be a {expected_type.__name__}")

        items = tuple(self.items)
        source_ids = tuple(self.source_selected_item_ids)
        sections = tuple(self.sections)
        if any(not isinstance(item, ContextItem) for item in items):
            raise TypeError("items must contain ContextItem values")
        if any(not isinstance(section, ContextSection) for section in sections):
            raise TypeError("sections must contain ContextSection values")
        item_ids = tuple(item.context_item_id for item in items)
        if len(set(item_ids)) != len(item_ids):
            raise ValueError("Context Bundle item identifiers must be unique")
        if item_ids != source_ids:
            raise ValueError(
                "Context Bundle items must exactly preserve retrieval selection and order"
            )

        section_ids = tuple(section.section_id for section in sections)
        if len(set(section_ids)) != len(section_ids):
            raise ValueError("Context Section identifiers must be unique")
        if tuple(section.order for section in sections) != tuple(range(len(sections))):
            raise ValueError("Context Sections must have contiguous zero-based order")
        section_item_ids = tuple(item_id for section in sections for item_id in section.item_ids)
        if section_item_ids != item_ids:
            raise ValueError("Context Sections must cover bundle items exactly once and in order")

        if not isinstance(self.statistics, ContextStatistics):
            raise TypeError("statistics must be ContextStatistics")
        if self.statistics.item_count != len(items):
            raise ValueError("statistics item_count must match bundle items")
        if self.statistics.character_count != sum(len(item.content) for item in items):
            raise ValueError("statistics character_count must match materialized content")
        if self.statistics.byte_count != sum(len(item.content.encode("utf-8")) for item in items):
            raise ValueError("statistics byte_count must match UTF-8 content")
        if self.statistics.line_count != sum(
            0 if not item.content else item.content.count("\n") + 1 for item in items
        ):
            raise ValueError("statistics line_count must match materialized content")
        if not isinstance(self.coverage, ContextCoverage):
            raise TypeError("coverage must be ContextCoverage")
        if not isinstance(self.diagnostics, DiagnosticCollection):
            raise TypeError("diagnostics must be a DiagnosticCollection")
        _require_text(self.bundle_version, "bundle_version")
        _require_text(self.builder_version, "builder_version")
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be a datetime")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")

        object.__setattr__(self, "items", items)
        object.__setattr__(self, "source_selected_item_ids", source_ids)
        object.__setattr__(self, "sections", sections)
