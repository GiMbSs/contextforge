"""Deterministic Python structural extraction using the standard library AST."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from enum import StrEnum

from contextforge.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticCollection,
    DiagnosticLocation,
    DiagnosticSeverity,
)
from contextforge.indexer.models import SourceLocation
from contextforge.scanner import ProjectArtifact

PYTHON_AST_STRATEGY_VERSION = "python-ast-v1"


class PythonDefinitionKind(StrEnum):
    """Python definition kinds extracted before Symbol normalization."""

    CLASS = "class"
    FUNCTION = "function"
    ASYNC_FUNCTION = "async_function"


@dataclass(frozen=True, slots=True)
class PythonDecorator:
    """One syntactically declared Python decorator."""

    expression: str
    location: SourceLocation

    def __post_init__(self) -> None:
        if not self.expression.strip():
            raise ValueError("Decorator expression must not be empty")
        if not isinstance(self.location, SourceLocation):
            raise TypeError("location must be a SourceLocation")


@dataclass(frozen=True, slots=True)
class PythonImportedName:
    """One name declared by an import statement."""

    name: str
    alias: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Imported name must not be empty")
        if self.alias is not None and not self.alias.strip():
            raise ValueError("Import alias must not be empty")


@dataclass(frozen=True, slots=True)
class PythonImport:
    """One import statement without attempting target resolution."""

    module: str | None
    names: tuple[PythonImportedName, ...]
    level: int
    location: SourceLocation
    scope_qualified_name: str | None = None

    def __post_init__(self) -> None:
        names = tuple(self.names)
        if not names:
            raise ValueError("Import must contain at least one imported name")
        if any(not isinstance(name, PythonImportedName) for name in names):
            raise TypeError("names must contain PythonImportedName values")
        if self.module is not None and not self.module.strip():
            raise ValueError("Import module must not be empty")
        if type(self.level) is not int:
            raise TypeError("level must be an integer")
        if self.level < 0:
            raise ValueError("level must not be negative")
        if not isinstance(self.location, SourceLocation):
            raise TypeError("location must be a SourceLocation")
        if self.scope_qualified_name is not None and not self.scope_qualified_name.strip():
            raise ValueError("scope_qualified_name must not be empty")
        object.__setattr__(self, "names", names)


@dataclass(frozen=True, slots=True)
class PythonReference:
    """One unresolved textual name use proven by Python syntax."""

    target_text: str
    location: SourceLocation
    scope_qualified_name: str | None = None

    def __post_init__(self) -> None:
        if not self.target_text.strip():
            raise ValueError("Reference target_text must not be empty")
        if not isinstance(self.location, SourceLocation):
            raise TypeError("location must be a SourceLocation")
        if self.scope_qualified_name is not None and not self.scope_qualified_name.strip():
            raise ValueError("scope_qualified_name must not be empty")


@dataclass(frozen=True, slots=True)
class PythonDefinition:
    """One class, function, or async function declaration."""

    name: str
    qualified_name: str
    kind: PythonDefinitionKind
    location: SourceLocation
    parent_qualified_name: str | None = None
    decorators: tuple[PythonDecorator, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Definition name must not be empty")
        if not self.qualified_name.strip():
            raise ValueError("qualified_name must not be empty")
        if not isinstance(self.kind, PythonDefinitionKind):
            raise TypeError("kind must be a PythonDefinitionKind")
        if not isinstance(self.location, SourceLocation):
            raise TypeError("location must be a SourceLocation")
        if self.parent_qualified_name is not None and not self.parent_qualified_name.strip():
            raise ValueError("parent_qualified_name must not be empty")
        decorators = tuple(self.decorators)
        if any(not isinstance(decorator, PythonDecorator) for decorator in decorators):
            raise TypeError("decorators must contain PythonDecorator values")
        object.__setattr__(self, "decorators", decorators)


@dataclass(frozen=True, slots=True)
class PythonModule:
    """Structural knowledge extracted from one Python artifact."""

    name: str
    location: SourceLocation
    definitions: tuple[PythonDefinition, ...] = ()
    imports: tuple[PythonImport, ...] = ()
    references: tuple[PythonReference, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Module name must not be empty")
        if not isinstance(self.location, SourceLocation):
            raise TypeError("location must be a SourceLocation")
        definitions = tuple(self.definitions)
        imports = tuple(self.imports)
        references = tuple(self.references)
        if any(not isinstance(item, PythonDefinition) for item in definitions):
            raise TypeError("definitions must contain PythonDefinition values")
        if any(not isinstance(item, PythonImport) for item in imports):
            raise TypeError("imports must contain PythonImport values")
        if any(not isinstance(item, PythonReference) for item in references):
            raise TypeError("references must contain PythonReference values")
        object.__setattr__(self, "definitions", definitions)
        object.__setattr__(self, "imports", imports)
        object.__setattr__(self, "references", references)


@dataclass(frozen=True, slots=True)
class PythonAstResult:
    """Python module extraction result with isolated diagnostics."""

    module: PythonModule | None = None
    diagnostics: DiagnosticCollection = field(default_factory=DiagnosticCollection)

    def __post_init__(self) -> None:
        if self.module is not None and not isinstance(self.module, PythonModule):
            raise TypeError("module must be a PythonModule")
        if not isinstance(self.diagnostics, DiagnosticCollection):
            raise TypeError("diagnostics must be a DiagnosticCollection")


def _location(artifact: ProjectArtifact, node: ast.AST) -> SourceLocation:
    start_line = getattr(node, "lineno", 1)
    start_column = getattr(node, "col_offset", 0) + 1
    end_line = getattr(node, "end_lineno", start_line)
    end_column = getattr(node, "end_col_offset", start_column)
    return SourceLocation(
        artifact.artifact_id,
        start_line,
        start_column,
        end_line,
        max(1, end_column),
    )


def _module_name(artifact: ProjectArtifact) -> str:
    parts = list(artifact.path.parts)
    filename = parts.pop()
    stem = filename[:-3] if filename.casefold().endswith(".py") else filename
    if stem != "__init__":
        parts.append(stem)
    return ".".join(parts) or "__init__"


def _module_location(artifact: ProjectArtifact, source: str) -> SourceLocation:
    lines = source.splitlines()
    if not lines:
        return SourceLocation(artifact.artifact_id, 1, 1, 1, 1)
    return SourceLocation(
        artifact.artifact_id,
        1,
        1,
        len(lines),
        max(1, len(lines[-1])),
    )


class _StructureVisitor(ast.NodeVisitor):
    def __init__(self, artifact: ProjectArtifact, source: str) -> None:
        self.artifact = artifact
        self.source = source
        self.definitions: list[PythonDefinition] = []
        self.imports: list[PythonImport] = []
        self.references: list[PythonReference] = []
        self.scope: list[str] = []

    def _visit_definition(
        self,
        node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
        kind: PythonDefinitionKind,
    ) -> None:
        parent = ".".join(self.scope) or None
        qualified_name = ".".join((*self.scope, node.name))
        decorators = tuple(
            PythonDecorator(
                ast.get_source_segment(self.source, decorator) or ast.unparse(decorator),
                _location(self.artifact, decorator),
            )
            for decorator in node.decorator_list
        )
        self.definitions.append(
            PythonDefinition(
                node.name,
                qualified_name,
                kind,
                _location(self.artifact, node),
                parent,
                decorators,
            )
        )
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_definition(node, PythonDefinitionKind.CLASS)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_definition(node, PythonDefinitionKind.FUNCTION)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_definition(node, PythonDefinitionKind.ASYNC_FUNCTION)

    def visit_Import(self, node: ast.Import) -> None:
        self.imports.append(
            PythonImport(
                None,
                tuple(PythonImportedName(alias.name, alias.asname) for alias in node.names),
                0,
                _location(self.artifact, node),
                ".".join(self.scope) or None,
            )
        )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.imports.append(
            PythonImport(
                node.module,
                tuple(PythonImportedName(alias.name, alias.asname) for alias in node.names),
                node.level,
                _location(self.artifact, node),
                ".".join(self.scope) or None,
            )
        )

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self.references.append(
                PythonReference(
                    node.id,
                    _location(self.artifact, node),
                    ".".join(self.scope) or None,
                )
            )


@dataclass(frozen=True, slots=True)
class PythonAstParser:
    """Parse Python source structurally without importing or executing it."""

    strategy_version: str = PYTHON_AST_STRATEGY_VERSION

    def __post_init__(self) -> None:
        if not self.strategy_version.strip():
            raise ValueError("strategy_version must not be empty")

    def parse(self, artifact: ProjectArtifact, content: bytes) -> PythonAstResult:
        """Extract deterministic Python syntax or return a diagnostic."""
        if not isinstance(artifact, ProjectArtifact):
            raise TypeError("artifact must be a ProjectArtifact")
        if not isinstance(content, bytes):
            raise TypeError("content must be bytes")
        try:
            syntax_tree = ast.parse(content, filename=artifact.path.value)
            source = content.decode("utf-8")
        except (SyntaxError, UnicodeDecodeError) as error:
            line = getattr(error, "lineno", None)
            column = getattr(error, "offset", None)
            diagnostic = Diagnostic(
                DiagnosticCode("INDEX_PYTHON_SYNTAX_ERROR"),
                DiagnosticSeverity.WARNING,
                "Python source could not be parsed.",
                "indexer",
                DiagnosticLocation(artifact.path.value, line, column if line else None),
            )
            return PythonAstResult(diagnostics=DiagnosticCollection((diagnostic,)))

        visitor = _StructureVisitor(artifact, source)
        visitor.visit(syntax_tree)
        return PythonAstResult(
            PythonModule(
                _module_name(artifact),
                _module_location(artifact, source),
                tuple(visitor.definitions),
                tuple(visitor.imports),
                tuple(visitor.references),
            )
        )
