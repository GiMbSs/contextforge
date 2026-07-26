"""Tests for CF-014 increment I033 deterministic lexical search."""

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
from contextforge.retrieval import LexicalSearchStrategy, TaskQueryNormalizer

FINGERPRINT = ProjectFingerprint("project_sha256_" + "2" * 64)


def make_index(contents: tuple[tuple[str, str, str], ...]) -> ProjectIndex:
    artifacts = []
    units = []
    for order, (unit_id, path, text) in enumerate(contents):
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
        units.append(
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
        search_units=tuple(units),
    )


def search(text: str, index: ProjectIndex):
    task = TaskSpecification(
        new_task_id(),
        text,
        TaskKind.EXPLAIN,
        RequestedOutput.ANALYSIS,
    )
    return LexicalSearchStrategy().search(TaskQueryNormalizer().normalize(task), index)


def test_more_token_overlap_ranks_first() -> None:
    index = make_index(
        (
            ("unit_partial", "src/partial.py", "cache helper"),
            ("unit_complete", "src/complete.py", "cache invalidation helper"),
        )
    )

    result = search("Explain cache invalidation", index)

    assert [item.source_reference for item in result.candidates] == [
        "unit_complete",
        "unit_partial",
    ]
    assert [item.rationale.rank for item in result.candidates if item.rationale] == [1, 2]


def test_term_frequency_breaks_equal_overlap() -> None:
    index = make_index(
        (
            ("unit_once", "once.py", "cache unrelated words"),
            ("unit_twice", "twice.py", "cache cache"),
        )
    )

    result = search("Explain cache", index)

    assert result.candidates[0].source_reference == "unit_twice"


def test_exact_quoted_phrase_receives_bonus_and_evidence() -> None:
    index = make_index(
        (
            ("unit_split", "split.py", "cache handles invalidation"),
            ("unit_phrase", "phrase.py", "cache invalidation"),
        )
    )

    result = search('Explain "cache invalidation"', index)

    assert result.candidates[0].source_reference == "unit_phrase"
    assert "exact_phrase=true" in result.candidates[0].evidence[0].detail


def test_path_match_can_generate_candidate() -> None:
    index = make_index((("unit_query", "src/retrieval/query.py", "normalizes tasks"),))

    result = search("Explain retrieval", index)

    assert len(result.candidates) == 1
    assert "path_match=true" in result.candidates[0].evidence[0].detail


def test_ties_are_ordered_by_stable_search_unit_identifier() -> None:
    index = make_index(
        (
            ("unit_b", "b.py", "cache"),
            ("unit_a", "a.py", "cache"),
        )
    )

    first = search("Explain cache", index)
    second = search("Explain cache", index)

    assert [item.source_reference for item in first.candidates] == ["unit_a", "unit_b"]
    assert first == second
