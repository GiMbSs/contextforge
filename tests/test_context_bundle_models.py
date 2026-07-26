"""Tests for immutable Context Bundle contracts."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime

import pytest

from contextforge.context import (
    ContextBundle,
    ContextCoverage,
    ContextItem,
    ContextSection,
    ContextSectionKind,
    ContextStatistics,
    CoverageStatus,
)
from contextforge.diagnostics import DiagnosticCollection
from contextforge.domain import (
    FingerprintOrdering,
    fingerprint_project,
    new_context_bundle_id,
    new_project_id,
    new_retrieval_id,
    new_task_id,
)
from contextforge.retrieval import (
    CandidateType,
    RetrievalEvidence,
    SelectedContextItem,
    SelectionDecision,
    SelectionRationale,
    SelectionReason,
)


def _selected_item(item_id: str, candidate_id: str) -> SelectedContextItem:
    evidence = RetrievalEvidence("explicit", "task", candidate_id)
    rationale = SelectionRationale(
        candidate_id,
        SelectionDecision.SELECTED,
        SelectionReason.EXPLICIT_PATH_REFERENCE,
        (evidence,),
    )
    return SelectedContextItem(
        item_id,
        candidate_id,
        None,
        f"content:{candidate_id}",
        CandidateType.USER_PROVIDED_CONTENT,
        rationale,
    )


def _bundle() -> ContextBundle:
    first = ContextItem(_selected_item("item-1", "candidate-1"), "user:first", "alpha\n")
    second = ContextItem(_selected_item("item-2", "candidate-2"), "user:second", "β")
    return ContextBundle(
        bundle_id=new_context_bundle_id(),
        task_id=new_task_id(),
        retrieval_id=new_retrieval_id(),
        project_id=new_project_id(),
        project_fingerprint=fingerprint_project(("project",), ordering=FingerprintOrdering.ORDERED),
        items=(first, second),
        source_selected_item_ids=("item-1", "item-2"),
        sections=(
            ContextSection(
                "section-user",
                ContextSectionKind.USER_CONTENT,
                "User content",
                ("item-1", "item-2"),
                0,
            ),
        ),
        statistics=ContextStatistics(
            item_count=2,
            character_count=7,
            byte_count=8,
            line_count=3,
        ),
        coverage=ContextCoverage(targets=CoverageStatus.COMPLETE),
        diagnostics=DiagnosticCollection(),
        bundle_version="1",
        builder_version="context-builder/1",
        created_at=datetime(2026, 7, 26, tzinfo=UTC),
    )


def test_context_bundle_is_immutable_and_preserves_traceability() -> None:
    bundle = _bundle()

    assert tuple(item.context_item_id for item in bundle.items) == (
        "item-1",
        "item-2",
    )
    assert bundle.items[0].selected_item.rationale.evidence[0].source == "task"
    with pytest.raises(FrozenInstanceError):
        bundle.bundle_version = "2"  # type: ignore[misc]


@pytest.mark.parametrize(
    "source_ids",
    [
        ("item-1",),
        ("item-1", "item-2", "introduced"),
        ("item-2", "item-1"),
    ],
)
def test_context_bundle_rejects_changed_retrieval_selection(
    source_ids: tuple[str, ...],
) -> None:
    with pytest.raises(ValueError, match="exactly preserve"):
        replace(_bundle(), source_selected_item_ids=source_ids)


def test_context_bundle_rejects_sections_that_change_item_order() -> None:
    bundle = _bundle()
    changed_section = replace(bundle.sections[0], item_ids=("item-2", "item-1"))

    with pytest.raises(ValueError, match="cover bundle items exactly"):
        replace(bundle, sections=(changed_section,))


def test_context_bundle_rejects_inconsistent_content_statistics() -> None:
    bundle = _bundle()

    with pytest.raises(ValueError, match="byte_count"):
        replace(
            bundle,
            statistics=replace(bundle.statistics, byte_count=7),
        )


def test_context_sections_require_contiguous_order() -> None:
    bundle = _bundle()

    with pytest.raises(ValueError, match="contiguous"):
        replace(bundle, sections=(replace(bundle.sections[0], order=1),))


def test_context_coverage_rejects_duplicate_missing_references() -> None:
    with pytest.raises(ValueError, match="unique"):
        ContextCoverage(missing_references=("missing.py", "missing.py"))
