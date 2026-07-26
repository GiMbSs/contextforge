"""Tests for CF-014 increment I028 complete Project Index assembly."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from contextforge.domain import (
    ArtifactPath,
    ProjectId,
    new_artifact_id,
    new_inventory_id,
    new_project_id,
)
from contextforge.domain.fingerprints import FingerprintOrdering, fingerprint_project
from contextforge.indexer import (
    DeterministicProjectIndexer,
    IndexingState,
    IndexRequest,
    IndexStatus,
    InMemoryIndexStorage,
    ProjectIndexQuery,
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


def fingerprint(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def make_artifact(
    project_id: ProjectId,
    path: str,
    content: bytes | None,
    kind: ArtifactKind = ArtifactKind.SOURCE,
    classification: ArtifactClassification = ArtifactClassification.SOURCE,
) -> ProjectArtifact:
    metadata = (("content_fingerprint", fingerprint(content)),) if content is not None else ()
    return ProjectArtifact(
        new_artifact_id(),
        project_id,
        ArtifactPath(path),
        kind,
        (classification,),
        ArtifactAvailability.INCLUDED,
        metadata,
    )


def make_inventory(
    artifacts: tuple[ProjectArtifact, ...],
    project_id: ProjectId,
) -> ProjectInventory:
    return ProjectInventory(
        new_inventory_id(),
        project_id,
        fingerprint_project(("state",), ordering=FingerprintOrdering.ORDERED),
        artifacts,
        ScanStatistics(
            artifacts_discovered=len(artifacts),
            artifacts_included=len(artifacts),
        ),
        NOW,
        "scanner-v1",
    )


class MappingProjectSource:
    def __init__(self, content: dict[str, bytes]) -> None:
        self.content = content

    def read(self, artifact: ProjectArtifact) -> bytes:
        try:
            return self.content[artifact.path.value]
        except KeyError as error:
            raise OSError("content unavailable") from error


def test_builds_complete_index_with_python_generic_and_honest_skips() -> None:
    project_id = new_project_id()
    python_content = b"import os\n\ndef run():\n    return os.name\n"
    text_content = b"Project notes\n"
    artifacts = (
        make_artifact(project_id, "src/main.py", python_content),
        make_artifact(
            project_id,
            "README.txt",
            text_content,
            ArtifactKind.DOCUMENTATION,
            ArtifactClassification.DOCUMENTATION,
        ),
        make_artifact(
            project_id,
            "image.png",
            None,
            ArtifactKind.BINARY,
            ArtifactClassification.BINARY,
        ),
    )
    inventory = make_inventory(artifacts, project_id)

    project_index = DeterministicProjectIndexer(
        MappingProjectSource(
            {
                "src/main.py": python_content,
                "README.txt": text_content,
            }
        ),
        clock=lambda: NOW,
    ).index(IndexRequest(inventory))
    records = {
        record.path.value: record for record in project_index.indexed_artifacts if record.path
    }

    assert project_index.status is IndexStatus.COMPLETE
    assert records["src/main.py"].state is IndexingState.FULLY_INDEXED
    assert records["README.txt"].strategy == "generic-text"
    assert records["image.png"].state is IndexingState.SKIPPED
    assert project_index.symbols
    assert project_index.relationships
    assert project_index.search_units
    assert project_index.measurements.artifacts_evaluated == 3


def test_syntax_error_does_not_abort_unrelated_artifact() -> None:
    project_id = new_project_id()
    broken = b"def broken(:\n"
    valid = b"def valid():\n    return 1\n"
    artifacts = (
        make_artifact(project_id, "broken.py", broken),
        make_artifact(project_id, "valid.py", valid),
    )
    inventory = make_inventory(artifacts, project_id)

    project_index = DeterministicProjectIndexer(
        MappingProjectSource({"broken.py": broken, "valid.py": valid}),
        clock=lambda: NOW,
    ).index(IndexRequest(inventory))

    assert project_index.status is IndexStatus.INCOMPLETE
    assert "valid" in {symbol.name for symbol in project_index.symbols}
    assert {str(item.code) for item in project_index.diagnostics} == {"INDEX_PYTHON_SYNTAX_ERROR"}
    assert tuple(record.state for record in project_index.indexed_artifacts) == (
        IndexingState.FAILED,
        IndexingState.FULLY_INDEXED,
    )


def test_semantic_output_and_index_identity_are_deterministic() -> None:
    project_id = new_project_id()
    content = b"def run():\n    return 1\n"
    inventory = make_inventory(
        (make_artifact(project_id, "main.py", content),),
        project_id,
    )
    indexer = DeterministicProjectIndexer(
        MappingProjectSource({"main.py": content}),
        clock=lambda: NOW,
    )

    first = indexer.index(IndexRequest(inventory))
    second = indexer.index(IndexRequest(inventory))

    assert first == second
    assert first.index_id == second.index_id


def test_project_state_mismatch_is_not_silently_indexed() -> None:
    project_id = new_project_id()
    scanned = b"value = 1\n"
    changed = b"value = 2\n"
    artifact = make_artifact(project_id, "main.py", scanned)
    inventory = make_inventory((artifact,), project_id)

    project_index = DeterministicProjectIndexer(
        MappingProjectSource({"main.py": changed}),
        clock=lambda: NOW,
    ).index(IndexRequest(inventory))

    assert project_index.status is IndexStatus.INCOMPLETE
    assert project_index.indexed_artifacts[0].state is IndexingState.FAILED
    assert {str(item.code) for item in project_index.diagnostics} == {
        "INDEX_PROJECT_STATE_MISMATCH"
    }


def test_index_can_be_saved_reloaded_and_queried() -> None:
    project_id = new_project_id()
    content = b"def search_target():\n    return 'needle'\n"
    inventory = make_inventory(
        (make_artifact(project_id, "main.py", content),),
        project_id,
    )
    project_index = DeterministicProjectIndexer(
        MappingProjectSource({"main.py": content}),
        clock=lambda: NOW,
    ).index(IndexRequest(inventory))
    storage = InMemoryIndexStorage()

    storage.save(project_index)
    reloaded = storage.load_compatible(project_id, inventory.project_fingerprint)
    assert reloaded == project_index
    assert reloaded is not None
    query = ProjectIndexQuery(reloaded)
    artifact = query.find_artifact("main.py")
    symbols = query.find_symbols("search_target")
    text_units = query.find_text("needle")

    assert artifact is not None
    assert artifact.path == ArtifactPath("main.py")
    assert len(symbols) == 1
    assert text_units
    assert query.find_relationships(symbols[0].parent_symbol_id or "")
