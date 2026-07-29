"""Tests for SimpleContextRetriever."""

from __future__ import annotations

from datetime import UTC, datetime

from contextforge.domain import (
    ArtifactPath,
    ProjectFingerprint,
    new_artifact_id,
    new_index_id,
    new_inventory_id,
    new_project_id,
    new_task_id,
)
from contextforge.domain.tasks import RequestedOutput, TaskKind, TaskSpecification
from contextforge.indexer import (
    IndexedArtifact,
    IndexingState,
    ProjectIndex,
    SearchUnit,
    SearchUnitKind,
    SourceLocation,
)
from contextforge.retrieval import (
    CandidateType,
    ContextBudget,
    RetrievalRequest,
    RetrievalStatus,
    SelectionReason,
    SimpleContextRetriever,
)

FINGERPRINT = ProjectFingerprint("project_sha256_" + "2" * 64)


def _make_index(
    units: tuple[tuple[str, str, str], ...],
) -> ProjectIndex:
    artifacts = []
    search_units = []
    for order, (unit_id, path, text) in enumerate(units):
        artifact_id = new_artifact_id()
        artifacts.append(
            IndexedArtifact(
                artifact_id,
                IndexingState.FULLY_INDEXED,
                "test",
                "1",
                FINGERPRINT,
                search_unit_ids=(unit_id,),
                path=ArtifactPath(path),
            )
        )
        search_units.append(
            SearchUnit(
                unit_id,
                artifact_id,
                SourceLocation(artifact_id, 1, 1, 1, max(len(text), 1)),
                SearchUnitKind.SOURCE_BLOCK,
                text,
                order,
            )
        )
    return ProjectIndex(
        new_index_id(),
        new_project_id(),
        new_inventory_id(),
        FINGERPRINT,
        "1",
        "test",
        tuple(artifacts),
        datetime(2026, 7, 25, tzinfo=UTC),
        search_units=tuple(search_units),
    )


def _request(
    task_text: str,
    index: ProjectIndex,
    *,
    max_items: int | None = None,
    max_bytes: int | None = None,
) -> RetrievalRequest:
    return RetrievalRequest(
        task=TaskSpecification(
            new_task_id(),
            task_text,
            TaskKind.EXPLAIN,
            RequestedOutput.ANALYSIS,
        ),
        project_index=index,
        budget=ContextBudget(max_items=max_items, max_bytes=max_bytes),
    )


def test_retriever_selects_search_unit_matching_task_term() -> None:
    index = _make_index(
        (
            ("unit_db", "src/db.py", "database connection module"),
            ("unit_main", "src/main.py", "main entry point"),
        )
    )
    retriever = SimpleContextRetriever()
    request = _request("explain the database module", index, max_items=10, max_bytes=10000)

    result = retriever.retrieve(request)

    assert result.status is RetrievalStatus.COMPLETE
    assert len(result.selected_items) == 1
    selected = result.selected_items[0]
    assert selected.candidate_type is CandidateType.SOURCE_EXCERPT
    assert selected.candidate_id == "unit_db"
    assert selected.content_reference == "src/db.py"
    assert selected.rationale.primary_reason is SelectionReason.LEXICAL_CONTENT_MATCH
    assert selected.rationale.score is not None
    assert selected.rationale.score > 0


def test_retriever_falls_back_to_smallest_artifacts_when_no_match() -> None:
    index = _make_index(
        (
            ("unit_large", "src/large.py", "a" * 100),
            ("unit_small", "src/small.py", "tiny"),
        )
    )
    retriever = SimpleContextRetriever()
    request = _request("explain quantum physics", index, max_items=1, max_bytes=10000)

    result = retriever.retrieve(request)

    assert result.status is RetrievalStatus.COMPLETE
    assert len(result.selected_items) == 1
    selected = result.selected_items[0]
    assert selected.candidate_type is CandidateType.FULL_ARTIFACT
    assert selected.content_reference == "src/small.py"
    assert selected.rationale.primary_reason is SelectionReason.REQUIRED_CONTEXT
    assert selected.candidate_id == f"artifact-{selected.artifact_id}"


def test_retriever_respects_max_items_budget() -> None:
    index = _make_index(
        (
            ("unit_a", "src/a.py", "helper function"),
            ("unit_b", "src/b.py", "helper class"),
            ("unit_c", "src/c.py", "helper utility"),
        )
    )
    retriever = SimpleContextRetriever()
    request = _request("explain helper", index, max_items=1, max_bytes=10000)

    result = retriever.retrieve(request)

    assert result.status is RetrievalStatus.COMPLETE
    assert len(result.selected_items) == 1
    assert result.statistics.excerpts_selected == 1
