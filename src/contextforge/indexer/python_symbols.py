"""Normalize extracted Python AST structures into canonical Symbols."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid5

from contextforge.diagnostics import DiagnosticCollection
from contextforge.indexer.models import SourceLocation, Symbol, SymbolKind
from contextforge.indexer.python_ast import (
    PYTHON_AST_STRATEGY_VERSION,
    PythonAstResult,
    PythonDefinition,
    PythonDefinitionKind,
)

PYTHON_SYMBOL_STRATEGY_VERSION = "python-symbol-v1"
_SYMBOL_NAMESPACE = UUID("301f02f4-fc4a-5e20-8a8a-d01741732bce")


def _symbol_id(
    qualified_name: str,
    kind: SymbolKind,
    location: SourceLocation,
    strategy_version: str,
) -> str:
    identity = uuid5(
        _SYMBOL_NAMESPACE,
        ":".join(
            (
                str(location.artifact_id),
                qualified_name,
                kind.value,
                str(location.start_line),
                str(location.start_column),
                strategy_version,
            )
        ),
    )
    return f"symbol_{identity.hex}"


def _symbol_kind(
    definition: PythonDefinition,
    definitions_by_name: dict[str, PythonDefinition],
) -> SymbolKind:
    if definition.kind is PythonDefinitionKind.CLASS:
        return SymbolKind.CLASS
    parent = (
        definitions_by_name.get(definition.parent_qualified_name)
        if definition.parent_qualified_name is not None
        else None
    )
    return (
        SymbolKind.METHOD
        if parent is not None and parent.kind is PythonDefinitionKind.CLASS
        else SymbolKind.FUNCTION
    )


@dataclass(frozen=True, slots=True)
class PythonSymbolResult:
    """Normalized Python symbols plus diagnostics inherited from parsing."""

    symbols: tuple[Symbol, ...] = ()
    diagnostics: DiagnosticCollection = field(default_factory=DiagnosticCollection)

    def __post_init__(self) -> None:
        symbols = tuple(self.symbols)
        if any(not isinstance(symbol, Symbol) for symbol in symbols):
            raise TypeError("symbols must contain Symbol values")
        if len({symbol.symbol_id for symbol in symbols}) != len(symbols):
            raise ValueError("Symbol identifiers must be unique")
        if not isinstance(self.diagnostics, DiagnosticCollection):
            raise TypeError("diagnostics must be a DiagnosticCollection")
        object.__setattr__(self, "symbols", symbols)


@dataclass(frozen=True, slots=True)
class PythonSymbolBuilder:
    """Build stable Symbols without type inference or name resolution."""

    strategy_version: str = PYTHON_SYMBOL_STRATEGY_VERSION
    ast_strategy_version: str = PYTHON_AST_STRATEGY_VERSION

    def __post_init__(self) -> None:
        if not self.strategy_version.strip():
            raise ValueError("strategy_version must not be empty")
        if not self.ast_strategy_version.strip():
            raise ValueError("ast_strategy_version must not be empty")

    def build(self, parsed: PythonAstResult) -> PythonSymbolResult:
        """Normalize a parsed Python module, preserving parse diagnostics."""
        if not isinstance(parsed, PythonAstResult):
            raise TypeError("parsed must be a PythonAstResult")
        if parsed.module is None:
            return PythonSymbolResult(diagnostics=parsed.diagnostics)

        module = parsed.module
        module_id = _symbol_id(
            module.name,
            SymbolKind.MODULE,
            module.location,
            self.strategy_version,
        )
        symbols = [
            Symbol(
                module_id,
                module.name.rsplit(".", 1)[-1],
                SymbolKind.MODULE,
                module.location.artifact_id,
                module.location,
                qualified_name=module.name,
                language="python",
                metadata=(("ast_strategy_version", self.ast_strategy_version),),
            )
        ]
        definitions_by_name = {
            definition.qualified_name: definition for definition in module.definitions
        }
        identifiers_by_name: dict[str, str] = {}

        for definition in module.definitions:
            kind = _symbol_kind(definition, definitions_by_name)
            qualified_name = f"{module.name}.{definition.qualified_name}"
            identifier = _symbol_id(
                qualified_name,
                kind,
                definition.location,
                self.strategy_version,
            )
            parent_identifier = (
                identifiers_by_name.get(definition.parent_qualified_name)
                if definition.parent_qualified_name is not None
                else module_id
            )
            metadata = [
                ("ast_strategy_version", self.ast_strategy_version),
                ("python_definition_kind", definition.kind.value),
            ]
            if definition.decorators:
                metadata.append(
                    (
                        "decorators",
                        "\n".join(item.expression for item in definition.decorators),
                    )
                )
            symbols.append(
                Symbol(
                    identifier,
                    definition.name,
                    kind,
                    definition.location.artifact_id,
                    definition.location,
                    qualified_name=qualified_name,
                    parent_symbol_id=parent_identifier,
                    language="python",
                    metadata=tuple(metadata),
                )
            )
            identifiers_by_name[definition.qualified_name] = identifier

        return PythonSymbolResult(tuple(symbols), parsed.diagnostics)
