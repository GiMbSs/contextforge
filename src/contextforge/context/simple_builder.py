"""Minimal ContextBundle builder backed by the project filesystem."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from contextforge.context.filesystem_source import FilesystemContextContentSource
from contextforge.context.materialization import (
    ContextItemMaterializer,
    ContextMaterializationError,
)
from contextforge.context.models import (
    ContextBundle,
    ContextCoverage,
    ContextItem,
    ContextSection,
    ContextSectionKind,
    ContextStatistics,
    CoverageStatus,
)
from contextforge.context.ordering import ContextItemOrderer
from contextforge.context.validation import ContextBundleValidator
from contextforge.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticCollection,
    DiagnosticSeverity,
)
from contextforge.domain import ProjectId, new_context_bundle_id
from contextforge.retrieval import CandidateType, RetrievalResult

SIMPLE_CONTEXT_BUILDER_VERSION = "simple-context-builder-v1"


@dataclass(slots=True)
class SimpleContextBuilder:
    """Build a validated ContextBundle from a RetrievalResult."""

    _root: Path

    def __post_init__(self) -> None:
        if not isinstance(self._root, Path):
            raise TypeError("root must be a pathlib.Path")

    def build(
        self,
        retrieval_result: RetrievalResult,
        *,
        project_id: ProjectId,
    ) -> ContextBundle:
        """Materialize, order, and validate the selected retrieval result."""
        if not isinstance(retrieval_result, RetrievalResult):
            raise TypeError("retrieval_result must be a RetrievalResult")
        if not isinstance(project_id, ProjectId):
            raise TypeError("project_id must be a ProjectId")

        source = FilesystemContextContentSource(self._root)
        materializer = ContextItemMaterializer(source)

        materialized: list[ContextItem] = []
        diagnostics: list[Diagnostic] = []
        for selected_item in retrieval_result.selected_items:
            try:
                materialized.extend(
                    materializer.materialize((selected_item,)),
                )
            except ContextMaterializationError as error:
                diagnostics.append(
                    _materialization_diagnostic(
                        f"Failed to materialize {selected_item.context_item_id}: {error}"
                    )
                )

        ordered = ContextItemOrderer().order_materialized(tuple(materialized))
        statistics = _compute_statistics(ordered)
        coverage = _compute_coverage(ordered)
        sections = _build_sections(ordered)

        bundle = ContextBundle(
            bundle_id=new_context_bundle_id(),
            task_id=retrieval_result.task_id,
            retrieval_id=retrieval_result.retrieval_id,
            project_id=project_id,
            project_fingerprint=retrieval_result.project_fingerprint,
            items=ordered,
            source_selected_item_ids=tuple(item.context_item_id for item in ordered),
            sections=sections,
            statistics=statistics,
            coverage=coverage,
            diagnostics=DiagnosticCollection(tuple(diagnostics)),
            bundle_version="1",
            builder_version=SIMPLE_CONTEXT_BUILDER_VERSION,
            created_at=datetime.now(UTC),
        )

        validation = ContextBundleValidator().validate(bundle, retrieval_result)
        if not validation.is_valid:
            messages = "; ".join(
                f"{diagnostic.code}: {diagnostic.message}" for diagnostic in validation.diagnostics
            )
            raise ValueError(f"ContextBundle validation failed: {messages}")

        return bundle


def _materialization_diagnostic(message: str) -> Diagnostic:
    return Diagnostic(
        DiagnosticCode("CONTEXT_MATERIALIZATION_FAILED"),
        DiagnosticSeverity.WARNING,
        message,
        "simple-context-builder",
    )


def _compute_statistics(items: tuple[ContextItem, ...]) -> ContextStatistics:
    artifact_ids = {
        item.selected_item.artifact_id
        for item in items
        if item.selected_item.artifact_id is not None
    }
    return ContextStatistics(
        item_count=len(items),
        artifact_count=len(artifact_ids),
        symbol_count=sum(
            1
            for item in items
            if item.selected_item.candidate_type is CandidateType.SYMBOL_DEFINITION
        ),
        excerpt_count=sum(
            1 for item in items if item.selected_item.candidate_type is CandidateType.SOURCE_EXCERPT
        ),
        byte_count=sum(len(item.content.encode("utf-8")) for item in items),
        character_count=sum(len(item.content) for item in items),
        line_count=sum(0 if not item.content else item.content.count("\n") + 1 for item in items),
        estimated_tokens=sum(item.selected_item.estimated_tokens or 0 for item in items),
    )


def _compute_coverage(items: tuple[ContextItem, ...]) -> ContextCoverage:
    targets = CoverageStatus.PARTIAL if items else CoverageStatus.MISSING
    return ContextCoverage(targets=targets)


def _build_sections(items: tuple[ContextItem, ...]) -> tuple[ContextSection, ...]:
    if not items:
        return ()
    return (
        ContextSection(
            section_id="primary",
            kind=ContextSectionKind.PRIMARY_IMPLEMENTATION,
            title="Primary implementation context",
            item_ids=tuple(item.context_item_id for item in items),
            order=0,
        ),
    )
