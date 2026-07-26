"""Tests for CF-014 increment I032 explicit-reference retrieval."""

from __future__ import annotations

from datetime import UTC, datetime

from contextforge.diagnostics import DiagnosticCollection
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
    SourceLocation,
    Symbol,
    SymbolKind,
)
from contextforge.retrieval import (
    CandidateOutcome,
    ExplicitReferenceKind,
    ExplicitReferenceStrategy,
    ExplicitResolutionState,
    SelectionReason,
    TaskQueryNormalizer,
)

FINGERPRINT = ProjectFingerprint("project_sha256_" + "1" * 64)


def artifact(_label: str, path: str) -> IndexedArtifact:
    return IndexedArtifact(
        new_artifact_id(),
        IndexingState.FULLY_INDEXED,
        "test",
        "1",
        FINGERPRINT,
        path=ArtifactPath(path),
    )


def make_index(
    artifacts: tuple[IndexedArtifact, ...],
    symbols: tuple[Symbol, ...] = (),
) -> ProjectIndex:
    return ProjectIndex(
        new_index_id(),
        new_project_id(),
        new_inventory_id(),
        FINGERPRINT,
        "1",
        "test",
        artifacts,
        datetime(2026, 7, 25, tzinfo=UTC),
        symbols=symbols,
    )


def resolve(text: str, index: ProjectIndex):
    task = TaskSpecification(
        new_task_id(),
        text,
        TaskKind.MODIFY,
        RequestedOutput.PATCH_PROPOSAL,
    )
    return ExplicitReferenceStrategy().resolve(TaskQueryNormalizer().normalize(task), index)


def test_exact_path_is_selected_with_high_priority_evidence() -> None:
    target = artifact("artifact_query", "src/contextforge/retrieval/query.py")

    result = resolve("Fix src/contextforge/retrieval/query.py.", make_index((target,)))

    assert len(result.candidates) == 1
    assert result.candidates[0].artifact_id == target.artifact_id
    assert result.candidates[0].outcome is CandidateOutcome.SELECTED
    assert result.candidates[0].rationale is not None
    assert result.candidates[0].rationale.primary_reason is SelectionReason.EXACT_PATH_MATCH
    assert result.candidates[0].rationale.score == 1.0
    assert result.resolutions[0].state is ExplicitResolutionState.EXACT
    assert len(result.diagnostics) == 0


def test_filename_only_resolves_unique_artifact() -> None:
    target = artifact("artifact_main", "src/contextforge/main.py")

    result = resolve("Explain main.py.", make_index((target,)))

    assert [candidate.artifact_id for candidate in result.candidates] == [target.artifact_id]
    assert result.resolutions[0].kind is ExplicitReferenceKind.FILENAME
    assert result.resolutions[0].state is ExplicitResolutionState.EXACT


def test_symbol_reference_selects_its_definition() -> None:
    target = artifact("artifact_service", "src/service.py")
    symbol = Symbol(
        "symbol_service_run",
        "run",
        SymbolKind.METHOD,
        target.artifact_id,
        SourceLocation(target.artifact_id, 10, 5, 12, 20),
        qualified_name="Service.run",
    )

    result = resolve("Fix Service.run.", make_index((target,), (symbol,)))

    assert len(result.candidates) == 1
    assert result.candidates[0].content_reference == "symbol:symbol_service_run"
    assert result.candidates[0].location == symbol.location
    assert result.candidates[0].rationale is not None
    assert result.candidates[0].rationale.primary_reason is SelectionReason.EXACT_SYMBOL_MATCH


def test_ambiguous_filename_preserves_all_candidates() -> None:
    first = artifact("artifact_one", "src/one/config.py")
    second = artifact("artifact_two", "src/two/config.py")

    result = resolve("Fix config.py.", make_index((first, second)))

    assert {candidate.artifact_id for candidate in result.candidates} == {
        first.artifact_id,
        second.artifact_id,
    }
    assert all(candidate.outcome is CandidateOutcome.DEFERRED for candidate in result.candidates)
    assert result.resolutions[0].state is ExplicitResolutionState.AMBIGUOUS
    assert [str(item.code) for item in result.diagnostics] == ["RETRIEVAL_REFERENCE_AMBIGUOUS"]


def test_missing_reference_produces_diagnostic_without_inventing_target() -> None:
    result = resolve("Fix missing.py.", make_index(()))

    assert result.candidates == ()
    assert result.resolutions[0].state is ExplicitResolutionState.NOT_FOUND
    assert [str(item.code) for item in result.diagnostics] == ["RETRIEVAL_REFERENCE_NOT_FOUND"]
    assert isinstance(result.diagnostics, DiagnosticCollection)


def test_path_derived_filename_is_not_resolved_as_a_separate_reference() -> None:
    named_path = artifact("artifact_named", "src/target/config.py")
    same_filename = artifact("artifact_other", "src/other/config.py")

    result = resolve(
        "Fix src/target/config.py.",
        make_index((named_path, same_filename)),
    )

    assert [candidate.artifact_id for candidate in result.candidates] == [named_path.artifact_id]
    assert len(result.resolutions) == 1
