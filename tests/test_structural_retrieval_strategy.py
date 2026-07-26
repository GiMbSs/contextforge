"""Tests for CF-014 increment I034 structural retrieval."""

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
    Relationship,
    RelationshipKind,
    SearchUnit,
    SearchUnitKind,
    SourceLocation,
    Symbol,
    SymbolKind,
)
from contextforge.retrieval import StructuralRetrievalStrategy, TaskQueryNormalizer

FINGERPRINT = ProjectFingerprint("project_sha256_" + "3" * 64)


def fixture_index() -> ProjectIndex:
    artifact_id = new_artifact_id()
    location = SourceLocation(artifact_id, 1, 1, 20, 1)
    module = Symbol("symbol_module", "service", SymbolKind.MODULE, artifact_id, location)
    parent = Symbol(
        "symbol_class",
        "Service",
        SymbolKind.CLASS,
        artifact_id,
        location,
        qualified_name="service.Service",
        parent_symbol_id=module.symbol_id,
    )
    method = Symbol(
        "symbol_method",
        "run",
        SymbolKind.METHOD,
        artifact_id,
        location,
        qualified_name="service.Service.run",
        parent_symbol_id=parent.symbol_id,
    )
    units = (
        SearchUnit(
            "unit_module",
            artifact_id,
            location,
            SearchUnitKind.FILE_SUMMARY,
            "module",
            0,
            (module.symbol_id,),
        ),
        SearchUnit(
            "unit_import",
            artifact_id,
            location,
            SearchUnitKind.SOURCE_BLOCK,
            "import dependency",
            1,
            (module.symbol_id,),
        ),
        SearchUnit(
            "unit_class",
            artifact_id,
            location,
            SearchUnitKind.SYMBOL_DEFINITION,
            "class Service",
            2,
            (parent.symbol_id,),
        ),
        SearchUnit(
            "unit_method",
            artifact_id,
            location,
            SearchUnitKind.SYMBOL_DEFINITION,
            "def run",
            3,
            (method.symbol_id,),
        ),
    )
    return ProjectIndex(
        new_index_id(),
        new_project_id(),
        new_inventory_id(),
        FINGERPRINT,
        "1",
        "test",
        (
            IndexedArtifact(
                artifact_id,
                IndexingState.FULLY_INDEXED,
                "test",
                "1",
                FINGERPRINT,
                path=ArtifactPath("service.py"),
            ),
        ),
        datetime(2026, 7, 26, tzinfo=UTC),
        symbols=(module, parent, method),
        relationships=(
            Relationship(
                "relationship_import",
                module.symbol_id,
                "python-name:dependency",
                RelationshipKind.IMPORTS,
                "ast",
            ),
        ),
        search_units=units,
    )


def test_named_method_includes_definition_scope_module_and_import() -> None:
    task = TaskSpecification(
        new_task_id(), "Explain service.Service.run", TaskKind.EXPLAIN, RequestedOutput.ANALYSIS
    )
    query = TaskQueryNormalizer().normalize(task)

    result = StructuralRetrievalStrategy().search(query, fixture_index())

    assert {candidate.source_reference for candidate in result.candidates} == {
        "unit_method",
        "unit_class",
        "unit_module",
        "unit_import",
    }
    evidence_types = {candidate.evidence[0].evidence_type for candidate in result.candidates}
    assert evidence_types == {
        "structural-definition",
        "structural-containing_scope",
        "structural-defining_module",
        "structural-required_import",
    }


def test_unknown_symbol_does_not_invent_structural_context() -> None:
    task = TaskSpecification(
        new_task_id(), "Explain MissingType", TaskKind.EXPLAIN, RequestedOutput.ANALYSIS
    )

    result = StructuralRetrievalStrategy().search(
        TaskQueryNormalizer().normalize(task),
        fixture_index(),
    )

    assert result.candidates == ()


def test_structural_result_is_deterministic() -> None:
    task = TaskSpecification(
        new_task_id(), "Explain service.Service.run", TaskKind.EXPLAIN, RequestedOutput.ANALYSIS
    )
    strategy = StructuralRetrievalStrategy()
    query = TaskQueryNormalizer().normalize(task)
    index = fixture_index()

    assert strategy.search(query, index) == strategy.search(query, index)
