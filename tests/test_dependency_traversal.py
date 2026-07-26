"""Tests for CF-014 increment I035 dependency traversal."""

from __future__ import annotations

from datetime import UTC, datetime

from contextforge.domain import (
    ArtifactPath,
    ProjectFingerprint,
    new_artifact_id,
    new_index_id,
    new_inventory_id,
    new_project_id,
)
from contextforge.indexer import (
    IndexedArtifact,
    IndexingState,
    ProjectIndex,
    Relationship,
    RelationshipKind,
    RelationshipResolution,
)
from contextforge.retrieval import (
    DependencyTraversalConfig,
    DependencyTraversalStrategy,
)

FINGERPRINT = ProjectFingerprint("project_sha256_" + "4" * 64)


def make_index(
    paths: tuple[str, ...],
    links: tuple[tuple[int, int, RelationshipKind], ...],
) -> tuple[ProjectIndex, tuple[IndexedArtifact, ...]]:
    artifacts = tuple(
        IndexedArtifact(
            new_artifact_id(),
            IndexingState.FULLY_INDEXED,
            "test",
            "1",
            FINGERPRINT,
            path=ArtifactPath(path),
        )
        for path in paths
    )
    relationships = tuple(
        Relationship(
            f"relationship_{position}",
            str(artifacts[source].artifact_id),
            str(artifacts[target].artifact_id),
            kind,
            "test",
            resolution=RelationshipResolution.RESOLVED_INTERNAL,
        )
        for position, (source, target, kind) in enumerate(links)
    )
    return (
        ProjectIndex(
            new_index_id(),
            new_project_id(),
            new_inventory_id(),
            FINGERPRINT,
            "1",
            "test",
            artifacts,
            datetime(2026, 7, 26, tzinfo=UTC),
            relationships=relationships,
        ),
        artifacts,
    )


def test_traversal_is_breadth_first_weighted_and_traceable() -> None:
    index, artifacts = make_index(
        ("a.py", "b.py", "c.py"),
        (
            (0, 1, RelationshipKind.IMPORTS),
            (1, 2, RelationshipKind.DEPENDS_ON),
        ),
    )

    result = DependencyTraversalStrategy().traverse(
        (str(artifacts[0].artifact_id),),
        index,
    )

    assert [candidate.artifact_id for candidate in result.candidates] == [
        artifacts[1].artifact_id,
        artifacts[2].artifact_id,
    ]
    assert len(result.paths[1].steps) == 2
    assert result.paths[0].cumulative_weight == 0.95
    assert result.paths[1].cumulative_weight == 0.76
    assert "imports" in result.candidates[0].evidence[0].detail


def test_cycle_is_visited_only_once() -> None:
    index, artifacts = make_index(
        ("a.py", "b.py"),
        (
            (0, 1, RelationshipKind.DEPENDS_ON),
            (1, 0, RelationshipKind.DEPENDS_ON),
        ),
    )

    result = DependencyTraversalStrategy().traverse(
        (str(artifacts[0].artifact_id),),
        index,
    )

    assert [candidate.artifact_id for candidate in result.candidates] == [artifacts[1].artifact_id]


def test_depth_limit_is_reported() -> None:
    index, artifacts = make_index(
        ("a.py", "b.py", "c.py"),
        (
            (0, 1, RelationshipKind.DEPENDS_ON),
            (1, 2, RelationshipKind.DEPENDS_ON),
        ),
    )
    strategy = DependencyTraversalStrategy(DependencyTraversalConfig(max_depth=1))

    result = strategy.traverse((str(artifacts[0].artifact_id),), index)

    assert len(result.candidates) == 1
    assert "RETRIEVAL_RELATIONSHIP_LIMIT" in {
        str(diagnostic.code) for diagnostic in result.diagnostics
    }


def test_fan_out_is_bounded_in_deterministic_order() -> None:
    index, artifacts = make_index(
        ("root.py", "c.py", "a.py", "b.py"),
        tuple((0, target, RelationshipKind.IMPORTS) for target in (1, 2, 3)),
    )
    strategy = DependencyTraversalStrategy(DependencyTraversalConfig(max_fan_out=2))

    first = strategy.traverse((str(artifacts[0].artifact_id),), index)
    second = strategy.traverse((str(artifacts[0].artifact_id),), index)

    assert first == second
    assert len(first.candidates) == 2
    assert "RETRIEVAL_HIGH_FAN_OUT" in {str(diagnostic.code) for diagnostic in first.diagnostics}


def test_unresolved_relationship_is_not_traversed() -> None:
    index, artifacts = make_index(("a.py",), ())
    unresolved = Relationship(
        "relationship_unresolved",
        str(artifacts[0].artifact_id),
        "python-name:external",
        RelationshipKind.IMPORTS,
        "test",
        resolution=RelationshipResolution.UNRESOLVED,
    )
    index = ProjectIndex(
        index.index_id,
        index.project_id,
        index.source_inventory_id,
        index.project_fingerprint,
        index.format_version,
        index.indexer_version,
        index.indexed_artifacts,
        index.created_at,
        relationships=(unresolved,),
    )

    result = DependencyTraversalStrategy().traverse(
        (str(artifacts[0].artifact_id),),
        index,
    )

    assert result.candidates == ()
