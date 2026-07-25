"""Tests for CF-014 increment I025 normalized Python Symbols."""

from contextforge.domain import ArtifactPath, new_artifact_id, new_project_id
from contextforge.indexer import (
    PythonAstParser,
    PythonSymbolBuilder,
    SymbolKind,
)
from contextforge.scanner import (
    ArtifactClassification,
    ArtifactKind,
    ProjectArtifact,
)


def make_artifact() -> ProjectArtifact:
    return ProjectArtifact(
        new_artifact_id(),
        new_project_id(),
        ArtifactPath("package/module.py"),
        ArtifactKind.SOURCE,
        (ArtifactClassification.SOURCE,),
    )


def build_symbols(source: str):
    artifact = make_artifact()
    parsed = PythonAstParser().parse(artifact, source.encode())
    return PythonSymbolBuilder().build(parsed)


def test_nested_classes_and_functions_have_normalized_parents() -> None:
    result = build_symbols(
        """class Outer:
    class Inner:
        def method(self):
            def nested():
                pass
"""
    )
    symbols = {symbol.qualified_name: symbol for symbol in result.symbols}

    assert tuple(symbols) == (
        "package.module",
        "package.module.Outer",
        "package.module.Outer.Inner",
        "package.module.Outer.Inner.method",
        "package.module.Outer.Inner.method.nested",
    )
    assert symbols["package.module.Outer.Inner.method"].kind is SymbolKind.METHOD
    assert symbols["package.module.Outer.Inner.method.nested"].kind is SymbolKind.FUNCTION
    assert (
        symbols["package.module.Outer.Inner.method"].parent_symbol_id
        == symbols["package.module.Outer.Inner"].symbol_id
    )


def test_decorators_are_preserved_as_python_metadata() -> None:
    result = build_symbols(
        """@registry.register("job")
@staticmethod
def execute():
    pass
"""
    )
    execute = result.symbols[1]

    assert dict(execute.metadata)["decorators"] == 'registry.register("job")\nstaticmethod'
    assert execute.language == "python"


def test_async_function_is_normalized_without_losing_async_kind() -> None:
    result = build_symbols("async def serve():\n    pass\n")
    serve = result.symbols[1]

    assert serve.kind is SymbolKind.FUNCTION
    assert dict(serve.metadata)["python_definition_kind"] == "async_function"


def test_duplicate_names_in_different_scopes_have_distinct_identity() -> None:
    result = build_symbols(
        """class First:
    def run(self):
        pass

class Second:
    def run(self):
        pass
"""
    )
    runs = tuple(symbol for symbol in result.symbols if symbol.name == "run")

    assert tuple(symbol.qualified_name for symbol in runs) == (
        "package.module.First.run",
        "package.module.Second.run",
    )
    assert runs[0].symbol_id != runs[1].symbol_id


def test_syntax_errors_produce_no_symbols_and_preserve_diagnostic() -> None:
    result = build_symbols("def broken(:\n")

    assert result.symbols == ()
    assert {str(item.code) for item in result.diagnostics} == {"INDEX_PYTHON_SYNTAX_ERROR"}


def test_unicode_identifiers_are_preserved_in_names_and_identity() -> None:
    artifact = make_artifact()
    parsed = PythonAstParser().parse(
        artifact,
        "class Serviço:\n    def executar(self):\n        pass\n".encode(),
    )
    builder = PythonSymbolBuilder()

    first = builder.build(parsed)
    second = builder.build(parsed)

    assert tuple(symbol.name for symbol in first.symbols) == (
        "module",
        "Serviço",
        "executar",
    )
    assert tuple(symbol.symbol_id for symbol in first.symbols) == tuple(
        symbol.symbol_id for symbol in second.symbols
    )
