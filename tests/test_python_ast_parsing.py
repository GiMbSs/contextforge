"""Tests for CF-014 increment I024 Python AST parsing."""

from contextforge.domain import ArtifactPath, new_artifact_id, new_project_id
from contextforge.indexer import (
    PythonAstParser,
    PythonDefinitionKind,
)
from contextforge.scanner import (
    ArtifactClassification,
    ArtifactKind,
    ProjectArtifact,
)


def make_artifact(path: str = "src/package/module.py") -> ProjectArtifact:
    return ProjectArtifact(
        new_artifact_id(),
        new_project_id(),
        ArtifactPath(path),
        ArtifactKind.SOURCE,
        (ArtifactClassification.SOURCE,),
    )


def test_extracts_module_classes_functions_and_async_functions() -> None:
    content = b"""class Service:
    def run(self):
        pass

async def main():
    pass
"""

    result = PythonAstParser().parse(make_artifact(), content)

    assert result.module is not None
    assert result.module.name == "src.package.module"
    assert tuple(
        (definition.qualified_name, definition.kind) for definition in result.module.definitions
    ) == (
        ("Service", PythonDefinitionKind.CLASS),
        ("Service.run", PythonDefinitionKind.FUNCTION),
        ("main", PythonDefinitionKind.ASYNC_FUNCTION),
    )


def test_extracts_imports_and_imported_names_without_resolution() -> None:
    content = b"""import os, pathlib as paths
from ..domain.models import Item as DomainItem, Other
"""

    result = PythonAstParser().parse(make_artifact(), content)

    assert result.module is not None
    first, second = result.module.imports
    assert first.module is None
    assert tuple((item.name, item.alias) for item in first.names) == (
        ("os", None),
        ("pathlib", "paths"),
    )
    assert second.module == "domain.models"
    assert second.level == 2
    assert tuple((item.name, item.alias) for item in second.names) == (
        ("Item", "DomainItem"),
        ("Other", None),
    )


def test_extracts_decorators_with_source_locations() -> None:
    content = b"""@registry.register("task")
@staticmethod
def execute():
    pass
"""

    result = PythonAstParser().parse(make_artifact(), content)

    assert result.module is not None
    definition = result.module.definitions[0]
    assert tuple(item.expression for item in definition.decorators) == (
        'registry.register("task")',
        "staticmethod",
    )
    assert tuple(item.location.start_line for item in definition.decorators) == (1, 2)
    assert definition.location.start_line == 3


def test_preserves_nested_scope_and_duplicate_names() -> None:
    content = b"""def outer():
    def duplicate():
        pass

class Container:
    def duplicate(self):
        pass
"""

    result = PythonAstParser().parse(make_artifact(), content)

    assert result.module is not None
    assert tuple(item.qualified_name for item in result.module.definitions) == (
        "outer",
        "outer.duplicate",
        "Container",
        "Container.duplicate",
    )
    assert tuple(item.parent_qualified_name for item in result.module.definitions) == (
        None,
        "outer",
        None,
        "Container",
    )


def test_syntax_error_is_isolated_as_diagnostic() -> None:
    result = PythonAstParser().parse(make_artifact("broken.py"), b"def broken(:\n")

    assert result.module is None
    assert {str(item.code) for item in result.diagnostics} == {"INDEX_PYTHON_SYNTAX_ERROR"}
    diagnostic = result.diagnostics.diagnostics[0]
    assert diagnostic.location is not None
    assert diagnostic.location.reference == "broken.py"
    assert diagnostic.location.line == 1


def test_unicode_identifiers_and_locations_are_preserved() -> None:
    result = PythonAstParser().parse(
        make_artifact(),
        "def função(parâmetro):\n    return parâmetro\n".encode(),
    )

    assert result.module is not None
    definition = result.module.definitions[0]
    assert definition.name == "função"
    assert definition.qualified_name == "função"
    assert definition.location.start_line == 1
    assert definition.location.end_line == 2


def test_package_initializer_has_package_module_name() -> None:
    result = PythonAstParser().parse(make_artifact("src/package/__init__.py"), b"")

    assert result.module is not None
    assert result.module.name == "src.package"
    assert result.module.definitions == ()
    assert result.module.imports == ()
