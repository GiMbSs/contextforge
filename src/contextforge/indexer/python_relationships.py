"""Build evidence-backed relationships from Python syntax and Symbols."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid5

from contextforge.diagnostics import DiagnosticCollection
from contextforge.indexer.models import (
    Relationship,
    RelationshipKind,
    RelationshipResolution,
    SourceLocation,
    Symbol,
)
from contextforge.indexer.python_ast import PythonAstResult, PythonImport
from contextforge.indexer.python_symbols import PythonSymbolResult

PYTHON_RELATIONSHIP_STRATEGY_VERSION = "python-relationship-v1"
_RELATIONSHIP_NAMESPACE = UUID("00505e85-acb2-5477-8c58-cdbbed2ecf38")


def _relationship(
    source: str,
    target: str,
    kind: RelationshipKind,
    evidence: str,
    location: SourceLocation,
    resolution: RelationshipResolution,
    strategy_version: str,
) -> Relationship:
    identity = uuid5(
        _RELATIONSHIP_NAMESPACE,
        ":".join(
            (
                source,
                target,
                kind.value,
                evidence,
                str(location.start_line),
                str(location.start_column),
                strategy_version,
            )
        ),
    )
    return Relationship(
        f"relationship_{identity.hex}",
        source,
        target,
        kind,
        evidence,
        location,
        resolution,
    )


def _import_targets(imported: PythonImport) -> tuple[tuple[str, str], ...]:
    prefix = "." * imported.level
    if imported.module is not None:
        module = f"{prefix}{imported.module}"
        return tuple(
            (
                f"python-module:{module}.{name.name}",
                f"python-import:{module}:{name.name}:alias={name.alias or ''}",
            )
            for name in imported.names
        )
    return tuple(
        (
            f"python-module:{name.name}",
            f"python-import:{name.name}:alias={name.alias or ''}",
        )
        for name in imported.names
    )


@dataclass(frozen=True, slots=True)
class PythonRelationshipResult:
    """Relationships produced from Python syntax with inherited diagnostics."""

    relationships: tuple[Relationship, ...] = ()
    diagnostics: DiagnosticCollection = field(default_factory=DiagnosticCollection)

    def __post_init__(self) -> None:
        relationships = tuple(self.relationships)
        if any(not isinstance(item, Relationship) for item in relationships):
            raise TypeError("relationships must contain Relationship values")
        if len({item.relationship_id for item in relationships}) != len(relationships):
            raise ValueError("Relationship identifiers must be unique")
        if not isinstance(self.diagnostics, DiagnosticCollection):
            raise TypeError("diagnostics must be a DiagnosticCollection")
        object.__setattr__(self, "relationships", relationships)


@dataclass(frozen=True, slots=True)
class PythonRelationshipBuilder:
    """Build only relationships directly supported by Python syntax."""

    strategy_version: str = PYTHON_RELATIONSHIP_STRATEGY_VERSION

    def __post_init__(self) -> None:
        if not self.strategy_version.strip():
            raise ValueError("strategy_version must not be empty")

    def build(
        self,
        parsed: PythonAstResult,
        symbol_result: PythonSymbolResult,
    ) -> PythonRelationshipResult:
        """Create structural and unresolved textual relationships."""
        if not isinstance(parsed, PythonAstResult):
            raise TypeError("parsed must be a PythonAstResult")
        if not isinstance(symbol_result, PythonSymbolResult):
            raise TypeError("symbol_result must be a PythonSymbolResult")
        diagnostics = symbol_result.diagnostics
        if parsed.module is None:
            return PythonRelationshipResult(diagnostics=diagnostics)

        symbols_by_qualified_name = {
            symbol.qualified_name: symbol
            for symbol in symbol_result.symbols
            if symbol.qualified_name is not None
        }
        module = parsed.module
        module_symbol = symbols_by_qualified_name.get(module.name)
        if module_symbol is None:
            raise ValueError("Python module Symbol is required")

        relationships: list[Relationship] = []
        for definition in module.definitions:
            qualified_name = f"{module.name}.{definition.qualified_name}"
            child = symbols_by_qualified_name.get(qualified_name)
            if child is None:
                raise ValueError(f"Missing Symbol for Python definition: {qualified_name}")
            parent = self._scope_symbol(
                module_symbol,
                symbols_by_qualified_name,
                module.name,
                definition.parent_qualified_name,
            )
            relationships.extend(
                (
                    _relationship(
                        parent.symbol_id,
                        child.symbol_id,
                        RelationshipKind.CONTAINS,
                        "python-ast:lexical-containment",
                        definition.location,
                        RelationshipResolution.RESOLVED_INTERNAL,
                        self.strategy_version,
                    ),
                    _relationship(
                        parent.symbol_id,
                        child.symbol_id,
                        RelationshipKind.DEFINES,
                        "python-ast:declaration",
                        definition.location,
                        RelationshipResolution.RESOLVED_INTERNAL,
                        self.strategy_version,
                    ),
                )
            )

        for imported in module.imports:
            source = self._scope_symbol(
                module_symbol,
                symbols_by_qualified_name,
                module.name,
                imported.scope_qualified_name,
            )
            for target, evidence in _import_targets(imported):
                relationships.extend(
                    (
                        _relationship(
                            source.symbol_id,
                            target,
                            RelationshipKind.IMPORTS,
                            evidence,
                            imported.location,
                            RelationshipResolution.UNRESOLVED,
                            self.strategy_version,
                        ),
                        _relationship(
                            source.symbol_id,
                            target,
                            RelationshipKind.DEPENDS_ON,
                            evidence,
                            imported.location,
                            RelationshipResolution.UNRESOLVED,
                            self.strategy_version,
                        ),
                    )
                )

        for reference in module.references:
            source = self._scope_symbol(
                module_symbol,
                symbols_by_qualified_name,
                module.name,
                reference.scope_qualified_name,
            )
            relationships.append(
                _relationship(
                    source.symbol_id,
                    f"python-name:{reference.target_text}",
                    RelationshipKind.REFERENCES,
                    "python-ast:name-load",
                    reference.location,
                    RelationshipResolution.UNRESOLVED,
                    self.strategy_version,
                )
            )

        return PythonRelationshipResult(tuple(relationships), diagnostics)

    @staticmethod
    def _scope_symbol(
        module_symbol: Symbol,
        symbols_by_qualified_name: dict[str, Symbol],
        module_name: str,
        scope_qualified_name: str | None,
    ) -> Symbol:
        if scope_qualified_name is None:
            return module_symbol
        qualified_name = f"{module_name}.{scope_qualified_name}"
        symbol = symbols_by_qualified_name.get(qualified_name)
        if symbol is None:
            raise ValueError(f"Missing Symbol for Python scope: {qualified_name}")
        return symbol
