"""Build bounded, source-traceable Search Units from Python syntax."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from uuid import UUID, uuid5

from contextforge.diagnostics import DiagnosticCollection
from contextforge.indexer.models import (
    SearchUnit,
    SearchUnitKind,
    SourceLocation,
)
from contextforge.indexer.python_ast import PythonAstResult, PythonDefinition
from contextforge.indexer.python_symbols import PythonSymbolResult

PYTHON_SEARCH_STRATEGY_VERSION = "python-search-v1"
_SEARCH_NAMESPACE = UUID("e86b5f27-0264-5ca4-92de-17fac85655d1")


@dataclass(frozen=True, slots=True)
class PythonSearchConfig:
    """Resource boundary for one Python Search Unit."""

    max_search_unit_bytes: int = 4_096

    def __post_init__(self) -> None:
        if type(self.max_search_unit_bytes) is not int:
            raise TypeError("max_search_unit_bytes must be an integer")
        if self.max_search_unit_bytes < 4:
            raise ValueError("max_search_unit_bytes must be at least 4 bytes")


@dataclass(frozen=True, slots=True)
class PythonSearchResult:
    """Ordered Python Search Units with inherited diagnostics."""

    search_units: tuple[SearchUnit, ...] = ()
    diagnostics: DiagnosticCollection = field(default_factory=DiagnosticCollection)

    def __post_init__(self) -> None:
        units = tuple(self.search_units)
        if any(not isinstance(unit, SearchUnit) for unit in units):
            raise TypeError("search_units must contain SearchUnit values")
        if len({unit.search_unit_id for unit in units}) != len(units):
            raise ValueError("Search Unit identifiers must be unique")
        if not isinstance(self.diagnostics, DiagnosticCollection):
            raise TypeError("diagnostics must be a DiagnosticCollection")
        object.__setattr__(self, "search_units", units)


def _fingerprint(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def _split_text(text: str, maximum_bytes: int) -> tuple[str, ...]:
    fragments: list[str] = []
    start = 0
    size = 0
    for position, character in enumerate(text):
        character_size = len(character.encode("utf-8"))
        if size and size + character_size > maximum_bytes:
            fragments.append(text[start:position])
            start = position
            size = 0
        size += character_size
    if start < len(text):
        fragments.append(text[start:])
    return tuple(fragments)


def _unit(
    artifact_id: object,
    location: SourceLocation,
    kind: SearchUnitKind,
    text: str,
    order: int,
    symbol_ids: tuple[str, ...],
    strategy_version: str,
) -> SearchUnit:
    fingerprint = _fingerprint(text)
    identity = uuid5(
        _SEARCH_NAMESPACE,
        ":".join(
            (
                str(artifact_id),
                kind.value,
                str(location.start_line),
                str(location.start_column),
                str(location.end_line),
                str(location.end_column),
                str(order),
                fingerprint,
                strategy_version,
            )
        ),
    )
    return SearchUnit(
        f"search_{identity.hex}",
        location.artifact_id,
        location,
        kind,
        text,
        order,
        symbol_ids,
        fingerprint,
        "python",
    )


def _source_span(content: bytes, location: SourceLocation) -> bytes:
    lines = content.splitlines(keepends=True)
    if not lines:
        return b""
    start_line = location.start_line - 1
    end_line = location.end_line - 1
    if start_line == end_line:
        return lines[start_line][location.start_column - 1 : location.end_column]
    selected = [lines[start_line][location.start_column - 1 :]]
    selected.extend(lines[start_line + 1 : end_line])
    selected.append(lines[end_line][: location.end_column])
    return b"".join(selected)


def _definition_location(definition: PythonDefinition) -> SourceLocation:
    if not definition.decorators:
        return definition.location
    first_decorator = definition.decorators[0].location
    return SourceLocation(
        definition.location.artifact_id,
        first_decorator.start_line,
        max(1, first_decorator.start_column - 1),
        definition.location.end_line,
        definition.location.end_column,
    )


def _bounded_spans(
    content: bytes,
    location: SourceLocation,
    maximum_bytes: int,
) -> tuple[tuple[str, SourceLocation], ...]:
    complete = _source_span(content, location)
    if len(complete) <= maximum_bytes:
        return ((complete.decode("utf-8"), location),) if complete else ()

    source_lines = content.splitlines()
    fragments: list[tuple[str, SourceLocation]] = []
    for line_number in range(location.start_line, location.end_line + 1):
        line = source_lines[line_number - 1]
        start = location.start_column - 1 if line_number == location.start_line else 0
        end = location.end_column if line_number == location.end_line else len(line)
        selected = line[start:end]
        byte_offset = start
        while selected:
            boundary = min(maximum_bytes, len(selected))
            while boundary and (
                selected[boundary : boundary + 1] or selected[boundary - 1 : boundary]
            ):
                try:
                    fragment = selected[:boundary].decode("utf-8")
                    break
                except UnicodeDecodeError:
                    boundary -= 1
            else:
                raise UnicodeDecodeError("utf-8", selected, 0, len(selected), "invalid UTF-8")
            fragment_location = SourceLocation(
                location.artifact_id,
                line_number,
                byte_offset + 1,
                line_number,
                byte_offset + boundary,
            )
            fragments.append((fragment, fragment_location))
            selected = selected[boundary:]
            byte_offset += boundary
    return tuple(fragments)


@dataclass(frozen=True, slots=True)
class PythonSearchUnitBuilder:
    """Create useful bounded Python units without assigning task relevance."""

    configuration: PythonSearchConfig = field(default_factory=PythonSearchConfig)
    strategy_version: str = PYTHON_SEARCH_STRATEGY_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, PythonSearchConfig):
            raise TypeError("configuration must be a PythonSearchConfig")
        if not self.strategy_version.strip():
            raise ValueError("strategy_version must not be empty")

    def build(
        self,
        parsed: PythonAstResult,
        symbol_result: PythonSymbolResult,
        content: bytes,
    ) -> PythonSearchResult:
        """Build module, definition, and import units from authorized bytes."""
        if not isinstance(parsed, PythonAstResult):
            raise TypeError("parsed must be a PythonAstResult")
        if not isinstance(symbol_result, PythonSymbolResult):
            raise TypeError("symbol_result must be a PythonSymbolResult")
        if not isinstance(content, bytes):
            raise TypeError("content must be bytes")
        if parsed.module is None:
            return PythonSearchResult(diagnostics=symbol_result.diagnostics)
        content.decode("utf-8")

        module = parsed.module
        symbols_by_name = {
            symbol.qualified_name: symbol
            for symbol in symbol_result.symbols
            if symbol.qualified_name is not None
        }
        module_symbol = symbols_by_name.get(module.name)
        if module_symbol is None:
            raise ValueError("Python module Symbol is required")
        summary = (
            f"module {module.name}; definitions={len(module.definitions)}; "
            f"imports={len(module.imports)}"
        )
        units = [
            _unit(
                module.location.artifact_id,
                module.location,
                SearchUnitKind.FILE_SUMMARY,
                fragment,
                order,
                (module_symbol.symbol_id,),
                self.strategy_version,
            )
            for order, fragment in enumerate(
                _split_text(summary, self.configuration.max_search_unit_bytes)
            )
        ]

        entries: list[tuple[SourceLocation, SearchUnitKind, tuple[str, ...]]] = []
        for definition in module.definitions:
            qualified_name = f"{module.name}.{definition.qualified_name}"
            symbol = symbols_by_name.get(qualified_name)
            if symbol is None:
                raise ValueError(f"Missing Symbol for Python definition: {qualified_name}")
            entries.append(
                (
                    _definition_location(definition),
                    SearchUnitKind.SYMBOL_DEFINITION,
                    (symbol.symbol_id,),
                )
            )
        entries.extend(
            (imported.location, SearchUnitKind.SOURCE_BLOCK, (module_symbol.symbol_id,))
            for imported in module.imports
        )
        entries.sort(
            key=lambda item: (
                item[0].start_line,
                item[0].start_column,
                item[1].value,
            )
        )

        for location, kind, symbol_ids in entries:
            for text, fragment_location in _bounded_spans(
                content,
                location,
                self.configuration.max_search_unit_bytes,
            ):
                units.append(
                    _unit(
                        module.location.artifact_id,
                        fragment_location,
                        kind,
                        text,
                        len(units),
                        symbol_ids,
                        self.strategy_version,
                    )
                )
        return PythonSearchResult(tuple(units), symbol_result.diagnostics)
