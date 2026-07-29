"""Tests for SimpleContextBuilder."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from contextforge.context import (
    ContextBundle,
    ContextSectionKind,
    ContextStatistics,
    CoverageStatus,
    SimpleContextBuilder,
)
from contextforge.diagnostics import DiagnosticCollection
from contextforge.domain import (
    ProjectFingerprint,
    new_artifact_id,
    new_index_id,
    new_project_id,
    new_retrieval_id,
    new_task_id,
)
from contextforge.indexer import SourceLocation
from contextforge.retrieval import (
    CandidateEligibility,
    CandidateOutcome,
    CandidateType,
    ContextBudget,
    RetrievalCandidate,
    RetrievalEvidence,
    RetrievalResult,
    RetrievalStatistics,
    RetrievalStatus,
    SelectedContextItem,
    SelectionDecision,
    SelectionRationale,
    SelectionReason,
)

NOW = datetime(2026, 7, 26, tzinfo=UTC)
FINGERPRINT = ProjectFingerprint("project_sha256_" + "2" * 64)


def _content_fingerprint(content: str) -> str:
    return f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"


def _make_selected_item(
    item_id: str,
    content: str,
    content_reference: str,
    candidate_type: CandidateType,
    *,
    location: SourceLocation | None = None,
    wrong_fingerprint: bool = False,
) -> SelectedContextItem:
    artifact_id = location.artifact_id if location is not None else new_artifact_id()
    candidate_id = f"candidate-{item_id}"
    evidence = (RetrievalEvidence("test", "builder", item_id),)
    rationale = SelectionRationale(
        candidate_id,
        SelectionDecision.SELECTED,
        SelectionReason.EXPLICIT_PATH_REFERENCE,
        evidence,
        rank=1,
    )
    fingerprint = _content_fingerprint(content)
    if wrong_fingerprint:
        fingerprint = f"sha256:{hashlib.sha256(b'wrong').hexdigest()}"
    return SelectedContextItem(
        context_item_id=item_id,
        candidate_id=candidate_id,
        artifact_id=artifact_id,
        content_reference=content_reference,
        candidate_type=candidate_type,
        rationale=rationale,
        location=location,
        estimated_tokens=len(content.split()),
        content_fingerprint=fingerprint,
        estimated_bytes=len(content.encode("utf-8")),
        estimated_characters=len(content),
        sensitivity_classification="standard",
    )


def _make_retrieval_result(
    selected_items: tuple[SelectedContextItem, ...],
) -> RetrievalResult:
    candidates: list[RetrievalCandidate] = []
    rationales: list[SelectionRationale] = []
    for selected in selected_items:
        candidate = RetrievalCandidate(
            candidate_id=selected.candidate_id,
            candidate_type=selected.candidate_type,
            source_reference=selected.content_reference,
            content_reference=selected.content_reference,
            evidence=selected.rationale.evidence,
            eligibility=CandidateEligibility.ELIGIBLE,
            outcome=CandidateOutcome.SELECTED,
            estimated_bytes=selected.estimated_bytes or 0,
            estimated_tokens=selected.estimated_tokens,
            artifact_id=selected.artifact_id,
            location=selected.location,
            rationale=selected.rationale,
        )
        candidates.append(candidate)
        rationales.append(selected.rationale)

    return RetrievalResult(
        retrieval_id=new_retrieval_id(),
        task_id=new_task_id(),
        index_id=new_index_id(),
        project_fingerprint=FINGERPRINT,
        strategy_versions=("test-v1",),
        candidates=tuple(candidates),
        selected_items=selected_items,
        rationales=tuple(rationales),
        applied_budget=ContextBudget(max_items=10, max_bytes=10000),
        diagnostics=DiagnosticCollection(),
        statistics=RetrievalStatistics(
            candidates_generated=len(candidates),
            candidates_evaluated=len(candidates),
        ),
        status=RetrievalStatus.COMPLETE,
        created_at=NOW,
    )


def test_builds_bundle_with_materialized_content(tmp_path: Path) -> None:
    content = "database connection module"
    reference = "src/db.py"
    (tmp_path / "src").mkdir()
    (tmp_path / reference).write_text(content, encoding="utf-8")

    selected = _make_selected_item(
        "item-db",
        content,
        reference,
        CandidateType.SOURCE_EXCERPT,
    )
    result = _make_retrieval_result((selected,))
    project_id = new_project_id()

    bundle = SimpleContextBuilder(tmp_path).build(result, project_id=project_id)

    assert isinstance(bundle, ContextBundle)
    assert bundle.project_id == project_id
    assert bundle.task_id == result.task_id
    assert bundle.retrieval_id == result.retrieval_id
    assert bundle.project_fingerprint == result.project_fingerprint
    assert len(bundle.items) == 1
    item = bundle.items[0]
    assert item.context_item_id == "item-db"
    assert item.content == content
    assert item.source_reference == reference
    assert item.verified_source_fingerprint == _content_fingerprint(content)

    assert bundle.source_selected_item_ids == ("item-db",)
    assert len(bundle.sections) == 1
    section = bundle.sections[0]
    assert section.section_id == "primary"
    assert section.kind is ContextSectionKind.PRIMARY_IMPLEMENTATION
    assert section.title == "Primary implementation context"
    assert section.item_ids == ("item-db",)

    assert bundle.statistics == ContextStatistics(
        item_count=1,
        artifact_count=1,
        excerpt_count=1,
        byte_count=len(content.encode("utf-8")),
        character_count=len(content),
        line_count=1,
        estimated_tokens=len(content.split()),
    )
    assert bundle.coverage.targets is CoverageStatus.PARTIAL
    assert bundle.diagnostics == DiagnosticCollection()


def test_empty_retrieval_result_produces_empty_bundle(tmp_path: Path) -> None:
    result = _make_retrieval_result(())
    project_id = new_project_id()

    bundle = SimpleContextBuilder(tmp_path).build(result, project_id=project_id)

    assert bundle.items == ()
    assert bundle.source_selected_item_ids == ()
    assert bundle.sections == ()
    assert bundle.statistics == ContextStatistics()
    assert bundle.coverage.targets is CoverageStatus.MISSING


def test_stale_item_is_skipped_with_diagnostic(tmp_path: Path) -> None:
    content = "fresh content"
    reference = "src/stale.py"
    (tmp_path / "src").mkdir()
    (tmp_path / reference).write_text(content, encoding="utf-8")

    stale = _make_selected_item(
        "item-stale",
        content,
        reference,
        CandidateType.SOURCE_EXCERPT,
        wrong_fingerprint=True,
    )
    valid = _make_selected_item(
        "item-valid",
        "valid content",
        "src/valid.py",
        CandidateType.SYMBOL_DEFINITION,
    )
    (tmp_path / "src" / "valid.py").write_text("valid content", encoding="utf-8")

    result = _make_retrieval_result((stale, valid))
    project_id = new_project_id()

    bundle = SimpleContextBuilder(tmp_path).build(result, project_id=project_id)

    assert len(bundle.items) == 1
    assert bundle.items[0].context_item_id == "item-valid"
    assert bundle.source_selected_item_ids == ("item-valid",)
    assert len(bundle.diagnostics) == 1
    diagnostic = next(iter(bundle.diagnostics))
    assert str(diagnostic.code) == "CONTEXT_MATERIALIZATION_FAILED"
    assert "stale" in diagnostic.message.lower()
    assert bundle.statistics.symbol_count == 1
    assert bundle.statistics.excerpt_count == 0


def test_build_rejects_invalid_retrieval_result_type(tmp_path: Path) -> None:
    builder = SimpleContextBuilder(tmp_path)
    with pytest.raises(TypeError):
        builder.build(object(), project_id=new_project_id())  # type: ignore[arg-type]


def test_build_rejects_invalid_project_id_type(tmp_path: Path) -> None:
    result = _make_retrieval_result(())
    builder = SimpleContextBuilder(tmp_path)
    with pytest.raises(TypeError):
        builder.build(result, project_id="not-a-project-id")  # type: ignore[arg-type]
