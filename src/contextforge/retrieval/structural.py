"""Deterministic structural retrieval from indexed symbol evidence."""

from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from contextforge.indexer import ProjectIndex, RelationshipKind, SearchUnit, Symbol, SymbolKind
from contextforge.retrieval.models import (
    CandidateEligibility,
    CandidateOutcome,
    CandidateType,
    RetrievalCandidate,
    RetrievalEvidence,
    SelectionDecision,
    SelectionRationale,
    SelectionReason,
)
from contextforge.retrieval.query import NormalizedTaskQuery

STRUCTURAL_RETRIEVAL_STRATEGY_VERSION = "structural-retrieval-v1"


class StructuralRole(StrEnum):
    """Why a search unit is structurally relevant to a named symbol."""

    DEFINITION = "definition"
    CONTAINING_SCOPE = "containing_scope"
    DEFINING_MODULE = "defining_module"
    REQUIRED_IMPORT = "required_import"


@dataclass(frozen=True, slots=True)
class StructuralSearchResult:
    """Ordered structural candidates produced from explicit index links."""

    candidates: tuple[RetrievalCandidate, ...]
    strategy_version: str = STRUCTURAL_RETRIEVAL_STRATEGY_VERSION

    def __post_init__(self) -> None:
        candidates = tuple(self.candidates)
        if any(not isinstance(candidate, RetrievalCandidate) for candidate in candidates):
            raise TypeError("candidates must contain RetrievalCandidate values")
        if not self.strategy_version.strip():
            raise ValueError("strategy_version must not be empty")
        object.__setattr__(self, "candidates", candidates)


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def _candidate(unit: SearchUnit, role: StructuralRole, root: Symbol) -> RetrievalCandidate:
    digest = hashlib.sha256(f"{unit.search_unit_id}\0{role.value}".encode()).hexdigest()[:20]
    candidate_id = f"structural_{digest}"
    reason = (
        SelectionReason.EXACT_SYMBOL_MATCH
        if role is StructuralRole.DEFINITION
        else (
            SelectionReason.DEPENDENCY_RELATIONSHIP
            if role is StructuralRole.REQUIRED_IMPORT
            else SelectionReason.DECLARATION_RELATIONSHIP
        )
    )
    evidence = RetrievalEvidence(
        f"structural-{role.value}",
        STRUCTURAL_RETRIEVAL_STRATEGY_VERSION,
        f"{root.qualified_name or root.name} -> {unit.search_unit_id}",
        1.0 if role is StructuralRole.DEFINITION else 0.8,
    )
    rationale = SelectionRationale(
        candidate_id,
        SelectionDecision.SELECTED,
        reason,
        (evidence,),
        score=evidence.weight,
        explanation=f"Included as {role.value.replace('_', ' ')}.",
    )
    return RetrievalCandidate(
        candidate_id,
        CandidateType.SYMBOL_DEFINITION
        if role in (StructuralRole.DEFINITION, StructuralRole.CONTAINING_SCOPE)
        else CandidateType.STRUCTURAL_UNIT,
        unit.search_unit_id,
        f"search-unit:{unit.search_unit_id}",
        (evidence,),
        CandidateEligibility.ELIGIBLE,
        CandidateOutcome.SELECTED,
        len(unit.text.encode()),
        artifact_id=unit.artifact_id,
        location=unit.location,
        rationale=rationale,
    )


@dataclass(frozen=True, slots=True)
class StructuralRetrievalStrategy:
    """Select definitions and directly evidenced structural context."""

    version: str = STRUCTURAL_RETRIEVAL_STRATEGY_VERSION

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("version must not be empty")

    def search(
        self,
        query: NormalizedTaskQuery,
        project_index: ProjectIndex,
    ) -> StructuralSearchResult:
        """Resolve named symbols and include their bounded structural context."""
        if not isinstance(query, NormalizedTaskQuery):
            raise TypeError("query must be a NormalizedTaskQuery")
        if not isinstance(project_index, ProjectIndex):
            raise TypeError("project_index must be a ProjectIndex")

        references = tuple(dict.fromkeys((*query.symbols, *query.quoted_identifiers)))
        roots = tuple(
            symbol
            for symbol in project_index.symbols
            if any(
                _normalize(symbol.name) == _normalize(reference)
                or (
                    symbol.qualified_name is not None
                    and _normalize(symbol.qualified_name) == _normalize(reference)
                )
                for reference in references
            )
        )
        symbols = {symbol.symbol_id: symbol for symbol in project_index.symbols}
        units_by_symbol: dict[str, list[SearchUnit]] = {}
        for unit in project_index.search_units:
            for symbol_id in unit.symbol_ids:
                units_by_symbol.setdefault(symbol_id, []).append(unit)

        selected: dict[str, tuple[SearchUnit, StructuralRole, Symbol]] = {}
        for root in roots:
            self._add_units(selected, units_by_symbol, root, StructuralRole.DEFINITION, root)
            current = root
            seen = {root.symbol_id}
            while current.parent_symbol_id is not None:
                parent = symbols.get(current.parent_symbol_id)
                if parent is None or parent.symbol_id in seen:
                    break
                seen.add(parent.symbol_id)
                role = (
                    StructuralRole.DEFINING_MODULE
                    if parent.kind is SymbolKind.MODULE
                    else StructuralRole.CONTAINING_SCOPE
                )
                self._add_units(selected, units_by_symbol, parent, role, root)
                current = parent

            scope_ids = seen
            if current.kind is SymbolKind.MODULE:
                scope_ids.add(current.symbol_id)
            importing_ids = {
                relationship.source_reference
                for relationship in project_index.relationships
                if relationship.kind is RelationshipKind.IMPORTS
                and relationship.source_reference in scope_ids
            }
            for symbol_id in sorted(importing_ids):
                symbol = symbols.get(symbol_id)
                if symbol is not None:
                    self._add_units(
                        selected,
                        units_by_symbol,
                        symbol,
                        StructuralRole.REQUIRED_IMPORT,
                        root,
                        import_only=True,
                    )

        role_order = {role: index for index, role in enumerate(StructuralRole)}
        ordered = sorted(
            selected.values(),
            key=lambda item: (role_order[item[1]], item[0].order, item[0].search_unit_id),
        )
        return StructuralSearchResult(
            tuple(_candidate(unit, role, root) for unit, role, root in ordered),
            self.version,
        )

    @staticmethod
    def _add_units(
        selected: dict[str, tuple[SearchUnit, StructuralRole, Symbol]],
        units_by_symbol: dict[str, list[SearchUnit]],
        symbol: Symbol,
        role: StructuralRole,
        root: Symbol,
        *,
        import_only: bool = False,
    ) -> None:
        for unit in units_by_symbol.get(symbol.symbol_id, ()):
            if import_only and unit.kind.value != "source_block":
                continue
            if (
                not import_only
                and role is StructuralRole.DEFINING_MODULE
                and unit.kind.value != "file_summary"
            ):
                continue
            selected.setdefault(unit.search_unit_id, (unit, role, root))
