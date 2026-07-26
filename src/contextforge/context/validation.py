"""Context Bundle validation against its authoritative Retrieval Result."""

from __future__ import annotations

from dataclasses import dataclass

from contextforge.context.models import ContextBundle, ContextItem
from contextforge.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticCollection,
    DiagnosticSeverity,
)
from contextforge.retrieval import CandidateType, ContextBudget, RetrievalResult


@dataclass(frozen=True, slots=True)
class ContextBundleValidationResult:
    """Complete deterministic validation outcome."""

    diagnostics: DiagnosticCollection

    @property
    def is_valid(self) -> bool:
        """Whether no validation error was found."""
        return not any(
            diagnostic.severity in (DiagnosticSeverity.ERROR, DiagnosticSeverity.CRITICAL)
            for diagnostic in self.diagnostics
        )


@dataclass(frozen=True, slots=True)
class ContextBundleValidator:
    """Validate a bundle without modifying it or making retrieval decisions."""

    def validate(
        self,
        bundle: ContextBundle,
        retrieval_result: RetrievalResult,
    ) -> ContextBundleValidationResult:
        """Validate all normative Context Bundle invariants."""
        if not isinstance(bundle, ContextBundle):
            raise TypeError("bundle must be a ContextBundle")
        if not isinstance(retrieval_result, RetrievalResult):
            raise TypeError("retrieval_result must be a RetrievalResult")

        diagnostics: list[Diagnostic] = []
        self._validate_identity(bundle, retrieval_result, diagnostics)
        self._validate_membership(bundle, retrieval_result, diagnostics)
        self._validate_spans(bundle, diagnostics)
        self._validate_items(bundle, retrieval_result, diagnostics)
        self._validate_budget(bundle, retrieval_result.applied_budget, diagnostics)
        return ContextBundleValidationResult(DiagnosticCollection(tuple(diagnostics)))

    @staticmethod
    def _validate_identity(
        bundle: ContextBundle,
        retrieval_result: RetrievalResult,
        diagnostics: list[Diagnostic],
    ) -> None:
        comparisons = (
            (bundle.retrieval_id, retrieval_result.retrieval_id, "retrieval"),
            (bundle.task_id, retrieval_result.task_id, "task"),
            (
                bundle.project_fingerprint,
                retrieval_result.project_fingerprint,
                "project fingerprint",
            ),
        )
        for actual, expected, label in comparisons:
            if actual != expected:
                diagnostics.append(
                    _error(
                        "CONTEXT_TRACEABILITY_MISMATCH",
                        f"Context Bundle {label} does not match its Retrieval Result.",
                    )
                )

    @staticmethod
    def _validate_membership(
        bundle: ContextBundle,
        retrieval_result: RetrievalResult,
        diagnostics: list[Diagnostic],
    ) -> None:
        bundle_ids = tuple(item.context_item_id for item in bundle.items)
        retrieval_ids = tuple(item.context_item_id for item in retrieval_result.selected_items)
        if set(bundle_ids) != set(retrieval_ids) or len(bundle_ids) != len(retrieval_ids):
            diagnostics.append(
                _error(
                    "CONTEXT_MEMBERSHIP_MISMATCH",
                    "Context Bundle membership differs from retrieval selection.",
                )
            )

    @staticmethod
    def _validate_spans(
        bundle: ContextBundle,
        diagnostics: list[Diagnostic],
    ) -> None:
        seen: set[tuple[object, ...]] = set()
        for item in bundle.items:
            span = _source_span(item)
            if span in seen:
                diagnostics.append(
                    _error(
                        "CONTEXT_DUPLICATE_SOURCE_SPAN",
                        f"Duplicate source span: {item.source_reference}.",
                    )
                )
            seen.add(span)

    @staticmethod
    def _validate_items(
        bundle: ContextBundle,
        retrieval_result: RetrievalResult,
        diagnostics: list[Diagnostic],
    ) -> None:
        selected_by_id = {item.context_item_id: item for item in retrieval_result.selected_items}
        for item in bundle.items:
            selected = selected_by_id.get(item.context_item_id)
            if selected is None:
                continue
            if item.selected_item != selected:
                diagnostics.append(
                    _error(
                        "CONTEXT_TRACEABILITY_MISMATCH",
                        f"Item provenance changed: {item.context_item_id}.",
                    )
                )
            if item.source_reference != selected.content_reference:
                diagnostics.append(
                    _error(
                        "CONTEXT_TRACEABILITY_MISMATCH",
                        f"Item source reference changed: {item.context_item_id}.",
                    )
                )
            expected_fingerprint = selected.content_fingerprint
            if selected.artifact_id is not None and expected_fingerprint is None:
                diagnostics.append(
                    _error(
                        "CONTEXT_SOURCE_FINGERPRINT_MISSING",
                        f"Artifact item has no source fingerprint: {item.context_item_id}.",
                    )
                )
            elif (
                expected_fingerprint is not None
                and item.verified_source_fingerprint != expected_fingerprint
            ):
                diagnostics.append(
                    _error(
                        "CONTEXT_SOURCE_FINGERPRINT_MISMATCH",
                        f"Source fingerprint is not verified: {item.context_item_id}.",
                    )
                )
            if selected.sensitivity_classification == "unclassified":
                diagnostics.append(
                    _error(
                        "CONTEXT_SENSITIVITY_MISSING",
                        f"Item sensitivity is unclassified: {item.context_item_id}.",
                    )
                )

    @staticmethod
    def _validate_budget(
        bundle: ContextBundle,
        budget: ContextBudget,
        diagnostics: list[Diagnostic],
    ) -> None:
        item_bytes = tuple(len(item.content.encode("utf-8")) for item in bundle.items)
        measurements = (
            (budget.max_items, len(bundle.items), "items"),
            (budget.max_bytes, sum(item_bytes), "bytes"),
            (
                budget.max_characters,
                sum(len(item.content) for item in bundle.items),
                "characters",
            ),
            (
                budget.max_estimated_tokens,
                sum(item.selected_item.estimated_tokens or 0 for item in bundle.items),
                "estimated tokens",
            ),
            (
                budget.max_artifacts,
                len(
                    {
                        item.selected_item.artifact_id
                        for item in bundle.items
                        if item.selected_item.artifact_id is not None
                    }
                ),
                "artifacts",
            ),
            (
                budget.max_excerpts,
                sum(
                    item.selected_item.candidate_type is CandidateType.SOURCE_EXCERPT
                    for item in bundle.items
                ),
                "excerpts",
            ),
        )
        for maximum, actual, label in measurements:
            if maximum is not None and actual > maximum:
                diagnostics.append(
                    _error(
                        "CONTEXT_BUDGET_EXCEEDED",
                        f"Context Bundle exceeds the {label} budget ({actual} > {maximum}).",
                    )
                )
        if budget.max_item_bytes is not None and any(
            value > budget.max_item_bytes for value in item_bytes
        ):
            diagnostics.append(
                _error(
                    "CONTEXT_ITEM_BUDGET_EXCEEDED",
                    "A Context Item exceeds the per-item byte budget.",
                )
            )


def _source_span(item: ContextItem) -> tuple[object, ...]:
    location = item.selected_item.location
    if location is None:
        return (
            item.selected_item.artifact_id,
            item.selected_item.content_reference,
            None,
        )
    return (
        location.artifact_id,
        location.start_line,
        location.start_column,
        location.end_line,
        location.end_column,
    )


def _error(code: str, message: str) -> Diagnostic:
    return Diagnostic(
        DiagnosticCode(code),
        DiagnosticSeverity.ERROR,
        message,
        "context-builder",
    )
