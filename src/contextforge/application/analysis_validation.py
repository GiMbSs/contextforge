"""Deterministic validation for grounded analysis responses."""

from __future__ import annotations

from contextforge.prompt import AnalysisResponse, AnalysisResponseStatus


class AnalysisResponseValidationError(ValueError):
    """An analysis response is not grounded in its supplied context."""


def validate_analysis_response(
    response: AnalysisResponse,
    *,
    known_references: frozenset[str],
    context_complete: bool,
) -> None:
    """Reject ungrounded findings and unsupported completion claims."""
    if not isinstance(response, AnalysisResponse):
        raise TypeError("response must be an AnalysisResponse")
    if not isinstance(known_references, frozenset) or any(
        not isinstance(reference, str) or not reference.strip() for reference in known_references
    ):
        raise TypeError("known_references must be a frozenset of non-empty strings")
    if not isinstance(context_complete, bool):
        raise TypeError("context_complete must be a bool")

    if not context_complete and response.status is AnalysisResponseStatus.COMPLETE:
        raise AnalysisResponseValidationError(
            "Analysis claims completion from an incomplete retrieval result"
        )

    for finding in response.findings:
        if not finding.evidence_references:
            raise AnalysisResponseValidationError(
                f"Analysis finding {finding.finding_id!r} has no evidence reference"
            )
        unknown = frozenset(finding.evidence_references) - known_references
        if unknown:
            references = ", ".join(sorted(unknown))
            raise AnalysisResponseValidationError(
                f"Analysis finding {finding.finding_id!r} cites unknown context: {references}"
            )
