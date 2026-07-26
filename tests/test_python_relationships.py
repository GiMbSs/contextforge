"""Tests for CF-014 increment I026 deterministic Python relationships."""

from contextforge.domain import ArtifactPath, new_artifact_id, new_project_id
from contextforge.indexer import (
    PythonAstParser,
    PythonRelationshipBuilder,
    PythonSymbolBuilder,
    RelationshipKind,
    RelationshipResolution,
)
from contextforge.scanner import (
    ArtifactClassification,
    ArtifactKind,
    ProjectArtifact,
)


def build_relationships(source: str):
    artifact = ProjectArtifact(
        new_artifact_id(),
        new_project_id(),
        ArtifactPath("package/module.py"),
        ArtifactKind.SOURCE,
        (ArtifactClassification.SOURCE,),
    )
    parsed = PythonAstParser().parse(artifact, source.encode())
    symbols = PythonSymbolBuilder().build(parsed)
    return symbols, PythonRelationshipBuilder().build(parsed, symbols)


def test_definitions_have_resolved_contains_and_defines_relationships() -> None:
    symbols, result = build_relationships(
        """class Service:
    def run(self):
        pass
"""
    )
    by_name = {symbol.qualified_name: symbol for symbol in symbols.symbols}
    service = by_name["package.module.Service"]
    run = by_name["package.module.Service.run"]

    assert {
        (item.source_reference, item.target_reference, item.kind, item.resolution)
        for item in result.relationships
        if item.target_reference == run.symbol_id
    } == {
        (
            service.symbol_id,
            run.symbol_id,
            RelationshipKind.CONTAINS,
            RelationshipResolution.RESOLVED_INTERNAL,
        ),
        (
            service.symbol_id,
            run.symbol_id,
            RelationshipKind.DEFINES,
            RelationshipResolution.RESOLVED_INTERNAL,
        ),
    }


def test_imports_create_unresolved_import_and_dependency_evidence() -> None:
    symbols, result = build_relationships(
        """import http.client as client
from .domain import Model
"""
    )
    module = symbols.symbols[0]

    assert {
        (item.source_reference, item.target_reference, item.kind, item.resolution)
        for item in result.relationships
    } == {
        (
            module.symbol_id,
            "python-module:http.client",
            RelationshipKind.IMPORTS,
            RelationshipResolution.UNRESOLVED,
        ),
        (
            module.symbol_id,
            "python-module:http.client",
            RelationshipKind.DEPENDS_ON,
            RelationshipResolution.UNRESOLVED,
        ),
        (
            module.symbol_id,
            "python-module:.domain.Model",
            RelationshipKind.IMPORTS,
            RelationshipResolution.UNRESOLVED,
        ),
        (
            module.symbol_id,
            "python-module:.domain.Model",
            RelationshipKind.DEPENDS_ON,
            RelationshipResolution.UNRESOLVED,
        ),
    }
    assert all(item.evidence.startswith("python-import:") for item in result.relationships)


def test_name_loads_create_unresolved_textual_references_in_scope() -> None:
    symbols, result = build_relationships(
        """def execute(value):
    return transform(value)
"""
    )
    execute = next(symbol for symbol in symbols.symbols if symbol.name == "execute")
    references = tuple(
        item for item in result.relationships if item.kind is RelationshipKind.REFERENCES
    )

    assert {
        (item.source_reference, item.target_reference, item.resolution) for item in references
    } == {
        (
            execute.symbol_id,
            "python-name:transform",
            RelationshipResolution.UNRESOLVED,
        ),
        (
            execute.symbol_id,
            "python-name:value",
            RelationshipResolution.UNRESOLVED,
        ),
    }
    assert all(item.evidence == "python-ast:name-load" for item in references)


def test_relationship_identity_is_deterministic() -> None:
    artifact = ProjectArtifact(
        new_artifact_id(),
        new_project_id(),
        ArtifactPath("module.py"),
        ArtifactKind.SOURCE,
        (ArtifactClassification.SOURCE,),
    )
    parsed = PythonAstParser().parse(artifact, b"import os\nvalue = os.name\n")
    symbols = PythonSymbolBuilder().build(parsed)
    builder = PythonRelationshipBuilder()

    first = builder.build(parsed, symbols)
    second = builder.build(parsed, symbols)

    assert tuple(item.relationship_id for item in first.relationships) == tuple(
        item.relationship_id for item in second.relationships
    )


def test_syntax_error_produces_no_relationships_and_preserves_diagnostics() -> None:
    _, result = build_relationships("def broken(:\n")

    assert result.relationships == ()
    assert {str(item.code) for item in result.diagnostics} == {"INDEX_PYTHON_SYNTAX_ERROR"}
