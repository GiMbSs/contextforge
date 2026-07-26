"""Tests for CF-014 increment I029 incremental Project indexing."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from contextforge.domain import (
    ArtifactId,
    ArtifactPath,
    ProjectId,
    new_artifact_id,
    new_inventory_id,
    new_project_id,
)
from contextforge.domain.fingerprints import FingerprintOrdering, fingerprint_project
from contextforge.indexer import (
    DeterministicProjectIndexer,
    IndexRequest,
    ProjectIndexerConfig,
)
from contextforge.scanner import (
    ArtifactAvailability,
    ArtifactClassification,
    ArtifactKind,
    ProjectArtifact,
    ProjectInventory,
    ScanStatistics,
)

NOW = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)


def content_fingerprint(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def make_artifact(
    project_id: ProjectId,
    artifact_id: ArtifactId,
    path: str,
    content: bytes,
) -> ProjectArtifact:
    return ProjectArtifact(
        artifact_id,
        project_id,
        ArtifactPath(path),
        ArtifactKind.SOURCE,
        (ArtifactClassification.SOURCE,),
        ArtifactAvailability.INCLUDED,
        (
            ("content_fingerprint", content_fingerprint(content)),
            ("size_bytes", len(content)),
        ),
    )


def make_inventory(
    project_id: ProjectId,
    artifacts: tuple[ProjectArtifact, ...],
    state: str,
) -> ProjectInventory:
    return ProjectInventory(
        new_inventory_id(),
        project_id,
        fingerprint_project((state,), ordering=FingerprintOrdering.ORDERED),
        artifacts,
        ScanStatistics(
            artifacts_discovered=len(artifacts),
            artifacts_included=len(artifacts),
            total_bytes=sum(dict(artifact.metadata).get("size_bytes", 0) for artifact in artifacts),
        ),
        NOW,
        "scanner-v1",
    )


class CountingProjectSource:
    def __init__(self, content: dict[str, bytes]) -> None:
        self.content = content
        self.read_paths: list[str] = []

    def read(self, artifact: ProjectArtifact) -> bytes:
        self.read_paths.append(artifact.path.value)
        return self.content[artifact.path.value]


def build_initial(
    content: dict[str, bytes],
) -> tuple[ProjectId, tuple[ProjectArtifact, ...], ProjectInventory, object]:
    project_id = new_project_id()
    artifacts = tuple(
        make_artifact(project_id, new_artifact_id(), path, value)
        for path, value in sorted(content.items())
    )
    inventory = make_inventory(project_id, artifacts, "initial")
    source = CountingProjectSource(content)
    project_index = DeterministicProjectIndexer(source, clock=lambda: NOW).index(
        IndexRequest(inventory)
    )
    return project_id, artifacts, inventory, project_index


def test_unchanged_artifacts_are_reused_without_source_reads() -> None:
    content = {"a.py": b"value = 1\n", "b.py": b"value = 2\n"}
    _, artifacts, inventory, previous = build_initial(content)
    source = CountingProjectSource(content)
    indexer = DeterministicProjectIndexer(source, clock=lambda: NOW)

    incremental = indexer.update(previous, IndexRequest(inventory))

    assert source.read_paths == []
    assert incremental.measurements.artifacts_reused == 2
    assert incremental.semantically_equivalent_to(previous)
    assert tuple(item.symbol_id for item in incremental.symbols) == tuple(
        item.symbol_id for item in previous.symbols
    )
    assert len(artifacts) == 2


def test_one_file_change_reindexes_only_changed_artifact() -> None:
    original = {"a.py": b"value = 1\n", "b.py": b"value = 2\n"}
    project_id, artifacts, _, previous = build_initial(original)
    changed_content = {"a.py": b"value = 3\n", "b.py": original["b.py"]}
    changed_artifacts = (
        make_artifact(project_id, artifacts[0].artifact_id, "a.py", changed_content["a.py"]),
        artifacts[1],
    )
    inventory = make_inventory(project_id, changed_artifacts, "changed-a")
    source = CountingProjectSource(changed_content)
    indexer = DeterministicProjectIndexer(source, clock=lambda: NOW)

    incremental = indexer.update(previous, IndexRequest(inventory))
    complete = DeterministicProjectIndexer(
        CountingProjectSource(changed_content),
        clock=lambda: NOW,
    ).index(IndexRequest(inventory))

    assert source.read_paths == ["a.py"]
    assert incremental.measurements.artifacts_reused == 1
    assert incremental.semantically_equivalent_to(complete)


def test_deleted_artifact_disappears_without_reindexing_survivor() -> None:
    content = {"a.py": b"value = 1\n", "b.py": b"value = 2\n"}
    project_id, artifacts, _, previous = build_initial(content)
    inventory = make_inventory(project_id, (artifacts[0],), "deleted-b")
    source = CountingProjectSource({"a.py": content["a.py"]})
    indexer = DeterministicProjectIndexer(source, clock=lambda: NOW)

    incremental = indexer.update(previous, IndexRequest(inventory))
    complete = DeterministicProjectIndexer(
        CountingProjectSource({"a.py": content["a.py"]}),
        clock=lambda: NOW,
    ).index(IndexRequest(inventory))

    assert source.read_paths == []
    assert tuple(record.path.value for record in incremental.indexed_artifacts if record.path) == (
        "a.py",
    )
    assert incremental.semantically_equivalent_to(complete)


def test_parser_version_change_forces_rebuild() -> None:
    content = {"main.py": b"def run():\n    return 1\n"}
    _, _, inventory, previous = build_initial(content)
    source = CountingProjectSource(content)
    indexer = DeterministicProjectIndexer(
        source,
        ProjectIndexerConfig(python_ast_strategy_version="python-ast-v2"),
        clock=lambda: NOW,
    )

    updated = indexer.update(previous, IndexRequest(inventory))

    assert source.read_paths == ["main.py"]
    assert updated.measurements.artifacts_reused == 0
    assert "python-ast-v2" in updated.strategy_versions


def test_index_schema_change_forces_rebuild() -> None:
    content = {"main.py": b"def run():\n    return 1\n"}
    _, _, inventory, previous = build_initial(content)
    source = CountingProjectSource(content)
    indexer = DeterministicProjectIndexer(
        source,
        clock=lambda: NOW,
        format_version="2",
    )

    updated = indexer.update(previous, IndexRequest(inventory))

    assert source.read_paths == ["main.py"]
    assert updated.format_version == "2"
    assert updated.measurements.artifacts_reused == 0
