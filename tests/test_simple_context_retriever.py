"""Tests for SimpleContextRetriever."""

from __future__ import annotations

from dataclasses import replace
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
    max_artifacts: int | None = None,
    max_estimated_tokens: int | None = None,
) -> RetrievalRequest:
    return RetrievalRequest(
        task=TaskSpecification(
            new_task_id(),
            task_text,
            TaskKind.EXPLAIN,
            RequestedOutput.ANALYSIS,
        ),
        project_index=index,
        budget=ContextBudget(
            max_items=max_items,
            max_bytes=max_bytes,
            max_artifacts=max_artifacts,
            max_estimated_tokens=max_estimated_tokens,
        ),
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


def test_retriever_expands_reviewed_semantic_aliases_deterministically() -> None:
    index = _make_index(
        (
            ("unit_service", "src/service.py", "runtime greeting formatter"),
            ("unit_other", "src/other.py", "unrelated utility"),
        )
    )

    result = SimpleContextRetriever().retrieve(
        _request("explain the runtime salutation", index, max_artifacts=1)
    )

    assert result.selected_items[0].content_reference == "src/service.py"
    assert result.strategy_versions[0] == "simple-retriever-v3"


def test_retriever_suppresses_historical_distractors_for_runtime_tasks() -> None:
    index = _make_index(
        (
            ("unit_archive", "src/greeting_archive.py", "historical legacy greeting"),
            ("unit_service", "src/service.py", "runtime greeting"),
        )
    )

    runtime_result = SimpleContextRetriever().retrieve(
        _request("explain the runtime greeting", index, max_artifacts=2)
    )
    historical_result = SimpleContextRetriever().retrieve(
        _request("explain the historical greeting archive", index, max_artifacts=1)
    )

    assert tuple(item.content_reference for item in runtime_result.selected_items) == (
        "src/service.py",
    )
    assert historical_result.selected_items[0].content_reference == "src/greeting_archive.py"
    archive_rationale = next(
        rationale
        for rationale in runtime_result.rationales
        if rationale.candidate_id == "unit_archive"
    )
    assert "historical_penalty=" in archive_rationale.evidence[0].detail


def test_historical_marker_applies_to_every_unit_in_the_artifact() -> None:
    index = _make_index(
        (
            ("unit_heading", "docs/greetings.md", "Greeting examples"),
            ("unit_service", "src/service.py", "runtime greeting implementation"),
        )
    )
    documentation = index.indexed_artifacts[0]
    historical_note = replace(
        index.search_units[0],
        search_unit_id="unit_note",
        text="Historical documentation only.",
        order=2,
    )
    documentation = replace(
        documentation,
        search_unit_ids=("unit_heading", "unit_note"),
    )
    index = replace(
        index,
        indexed_artifacts=(documentation, index.indexed_artifacts[1]),
        search_units=(
            index.search_units[0],
            historical_note,
            index.search_units[1],
        ),
    )

    result = SimpleContextRetriever().retrieve(
        _request("explain the runtime greeting", index, max_artifacts=2)
    )

    assert tuple(item.content_reference for item in result.selected_items) == ("src/service.py",)


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


def test_retriever_respects_artifact_and_token_budgets() -> None:
    index = _make_index(
        (
            ("unit_a", "src/a.py", "helper " * 20),
            ("unit_b", "src/b.py", "helper " * 20),
        )
    )

    artifact_limited = SimpleContextRetriever().retrieve(
        _request(
            "explain helper",
            index,
            max_artifacts=1,
            max_estimated_tokens=100,
        )
    )
    token_limited = SimpleContextRetriever().retrieve(
        _request(
            "explain helper",
            index,
            max_artifacts=2,
            max_estimated_tokens=1,
        )
    )

    assert len({item.artifact_id for item in artifact_limited.selected_items}) == 1
    assert artifact_limited.statistics.candidates_budget_excluded == 1
    assert token_limited.status is RetrievalStatus.INCOMPLETE
    assert not token_limited.selected_items


def test_retriever_suppresses_duplicate_source_spans() -> None:
    index = _make_index((("unit_a", "src/a.py", "helper function"),))
    original = index.search_units[0]
    duplicate = replace(original, search_unit_id="unit_duplicate", order=1)
    artifact = replace(
        index.indexed_artifacts[0],
        search_unit_ids=("unit_a", "unit_duplicate"),
    )
    duplicated_index = replace(
        index,
        indexed_artifacts=(artifact,),
        search_units=(original, duplicate),
    )

    result = SimpleContextRetriever().retrieve(
        _request("explain helper", duplicated_index, max_items=10)
    )

    assert len(result.selected_items) == 1
    assert result.statistics.duplicates_suppressed == 1
    assert any(
        rationale.primary_reason is SelectionReason.DUPLICATE_CONTENT
        for rationale in result.rationales
    )
