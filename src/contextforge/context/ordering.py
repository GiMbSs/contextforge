"""Deterministic ordering derived from Retrieval Result semantics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from contextforge.context.models import ContextItem
from contextforge.retrieval import CandidateType, SelectedContextItem, SelectionReason


class ContextOrderingTier(IntEnum):
    """Normative initial Context Bundle ordering tiers."""

    DIRECT_REFERENCE = 0
    PRIMARY_DEFINITION = 1
    STRUCTURAL_SUPPORT = 2
    DEPENDENCY = 3
    SUPPLEMENTARY = 4


_DIRECT_REASONS = frozenset(
    {
        SelectionReason.EXPLICIT_PATH_REFERENCE,
        SelectionReason.EXPLICIT_SYMBOL_REFERENCE,
        SelectionReason.ERROR_LOCATION_REFERENCE,
        SelectionReason.EXACT_PATH_MATCH,
        SelectionReason.EXACT_SYMBOL_MATCH,
        SelectionReason.USER_PROVIDED_CONTEXT,
    }
)
_PRIMARY_TYPES = frozenset(
    {
        CandidateType.FULL_ARTIFACT,
        CandidateType.SYMBOL_DEFINITION,
    }
)
_STRUCTURAL_TYPES = frozenset(
    {
        CandidateType.STRUCTURAL_UNIT,
        CandidateType.RELATED_DECLARATION,
        CandidateType.RELATIONSHIP_SUMMARY,
    }
)


@dataclass(frozen=True, slots=True)
class ContextItemOrderer:
    """Order selected or materialized items with stable semantic keys."""

    def tier(self, item: SelectedContextItem) -> ContextOrderingTier:
        """Classify one selected item using only retrieval-produced evidence."""
        if not isinstance(item, SelectedContextItem):
            raise TypeError("item must be a SelectedContextItem")
        if item.rationale.primary_reason in _DIRECT_REASONS:
            return ContextOrderingTier.DIRECT_REFERENCE
        if item.dependency_path:
            return ContextOrderingTier.DEPENDENCY
        if item.candidate_type in _PRIMARY_TYPES:
            return ContextOrderingTier.PRIMARY_DEFINITION
        if item.candidate_type in _STRUCTURAL_TYPES:
            return ContextOrderingTier.STRUCTURAL_SUPPORT
        if item.candidate_type is CandidateType.DEPENDENCY_RECORD:
            return ContextOrderingTier.DEPENDENCY
        return ContextOrderingTier.SUPPLEMENTARY

    def order_selected(
        self,
        items: tuple[SelectedContextItem, ...],
    ) -> tuple[SelectedContextItem, ...]:
        """Return retrieval selections in deterministic Context Bundle order."""
        selected_items = tuple(items)
        if any(not isinstance(item, SelectedContextItem) for item in selected_items):
            raise TypeError("items must contain SelectedContextItem values")
        return tuple(sorted(selected_items, key=self._key))

    def order_materialized(
        self,
        items: tuple[ContextItem, ...],
    ) -> tuple[ContextItem, ...]:
        """Order materialized items by their retained retrieval provenance."""
        context_items = tuple(items)
        if any(not isinstance(item, ContextItem) for item in context_items):
            raise TypeError("items must contain ContextItem values")
        return tuple(sorted(context_items, key=lambda item: self._key(item.selected_item)))

    def _key(self, item: SelectedContextItem) -> tuple[object, ...]:
        location = item.location
        return (
            self.tier(item),
            item.rationale.rank if item.rationale.rank is not None else float("inf"),
            item.content_reference.casefold(),
            location.start_line if location is not None else 0,
            location.start_column if location is not None else 0,
            location.end_line if location is not None else 0,
            location.end_column if location is not None else 0,
            item.candidate_id,
            item.context_item_id,
        )
