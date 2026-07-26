"""Tests for CF-014 increment I027 Python Search Units."""

from contextforge.domain import ArtifactPath, new_artifact_id, new_project_id
from contextforge.indexer import (
    PythonAstParser,
    PythonSearchConfig,
    PythonSearchUnitBuilder,
    PythonSymbolBuilder,
    SearchUnitKind,
)
from contextforge.scanner import (
    ArtifactClassification,
    ArtifactKind,
    ProjectArtifact,
)


def build_units(source: str, maximum_bytes: int = 4_096):
    artifact = ProjectArtifact(
        new_artifact_id(),
        new_project_id(),
        ArtifactPath("package/module.py"),
        ArtifactKind.SOURCE,
        (ArtifactClassification.SOURCE,),
    )
    content = source.encode()
    parsed = PythonAstParser().parse(artifact, content)
    symbols = PythonSymbolBuilder().build(parsed)
    result = PythonSearchUnitBuilder(PythonSearchConfig(max_search_unit_bytes=maximum_bytes)).build(
        parsed, symbols, content
    )
    return symbols, result


def test_builds_module_summary_definition_and_import_units() -> None:
    symbols, result = build_units(
        """import os

class Service:
    def run(self):
        return os.name
"""
    )

    assert tuple(unit.kind for unit in result.search_units) == (
        SearchUnitKind.FILE_SUMMARY,
        SearchUnitKind.SOURCE_BLOCK,
        SearchUnitKind.SYMBOL_DEFINITION,
        SearchUnitKind.SYMBOL_DEFINITION,
    )
    assert result.search_units[0].text == ("module package.module; definitions=2; imports=1")
    assert result.search_units[1].text == "import os"
    assert result.search_units[2].text.startswith("class Service:")
    assert result.search_units[3].text.startswith("def run")
    assert result.search_units[3].symbol_ids == (symbols.symbols[2].symbol_id,)


def test_decorators_are_included_in_definition_source_span() -> None:
    _, result = build_units(
        """@registry.register("job")
def execute():
    pass
"""
    )
    definition = next(
        unit for unit in result.search_units if unit.kind is SearchUnitKind.SYMBOL_DEFINITION
    )

    assert definition.location.start_line == 1
    assert definition.text.startswith('@registry.register("job")\ndef execute')


def test_large_definition_is_bounded_and_preserves_locations() -> None:
    _, result = build_units(
        """def calculate():
    first_value = 1
    second_value = 2
    return first_value + second_value
""",
        maximum_bytes=16,
    )
    definition_units = tuple(
        unit for unit in result.search_units if unit.kind is SearchUnitKind.SYMBOL_DEFINITION
    )

    assert len(definition_units) > 1
    assert all(len(unit.text.encode()) <= 16 for unit in definition_units)
    assert tuple(unit.order for unit in result.search_units) == tuple(
        range(len(result.search_units))
    )
    assert tuple(unit.location.start_line for unit in definition_units) == tuple(
        sorted(unit.location.start_line for unit in definition_units)
    )


def test_unicode_is_split_only_between_valid_utf8_code_points() -> None:
    _, result = build_units(
        """def função():
    descrição = "áéíóú"
    return descrição
""",
        maximum_bytes=8,
    )
    definition_units = tuple(
        unit for unit in result.search_units if unit.kind is SearchUnitKind.SYMBOL_DEFINITION
    )

    assert all(len(unit.text.encode()) <= 8 for unit in definition_units)
    assert all(unit.text.encode().decode() == unit.text for unit in definition_units)


def test_every_unit_has_location_content_fingerprint_and_stable_identity() -> None:
    artifact = ProjectArtifact(
        new_artifact_id(),
        new_project_id(),
        ArtifactPath("module.py"),
        ArtifactKind.SOURCE,
        (ArtifactClassification.SOURCE,),
    )
    content = b"def run():\n    return 1\n"
    parsed = PythonAstParser().parse(artifact, content)
    symbols = PythonSymbolBuilder().build(parsed)
    builder = PythonSearchUnitBuilder()

    first = builder.build(parsed, symbols, content)
    second = builder.build(parsed, symbols, content)

    assert all(unit.content_fingerprint is not None for unit in first.search_units)
    assert all(
        unit.content_fingerprint.startswith("sha256:")
        for unit in first.search_units
        if unit.content_fingerprint is not None
    )
    assert tuple(unit.search_unit_id for unit in first.search_units) == tuple(
        unit.search_unit_id for unit in second.search_units
    )


def test_syntax_error_produces_no_units_and_preserves_diagnostic() -> None:
    _, result = build_units("def broken(:\n")

    assert result.search_units == ()
    assert {str(item.code) for item in result.diagnostics} == {"INDEX_PYTHON_SYNTAX_ERROR"}
