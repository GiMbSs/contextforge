"""Tests for deterministic grounding of analysis responses."""

import pytest

from contextforge.application import (
    AnalysisResponseValidationError,
    validate_analysis_response,
)
from contextforge.prompt import AnalysisFinding, AnalysisResponse, AnalysisResponseStatus


def response(
    status: AnalysisResponseStatus,
    *findings: AnalysisFinding,
) -> AnalysisResponse:
    return AnalysisResponse(
        status,
        "Grounded analysis.",
        findings,
        (),
        ("More context is required.",)
        if status is AnalysisResponseStatus.INSUFFICIENT_CONTEXT
        else (),
    )


def test_complete_response_requires_complete_retrieval() -> None:
    with pytest.raises(AnalysisResponseValidationError, match="incomplete retrieval"):
        validate_analysis_response(
            response(AnalysisResponseStatus.COMPLETE),
            known_references=frozenset(),
            context_complete=False,
        )


def test_every_finding_requires_evidence() -> None:
    finding = AnalysisFinding("finding-1", "An unsupported claim.", ())

    with pytest.raises(AnalysisResponseValidationError, match="has no evidence"):
        validate_analysis_response(
            response(AnalysisResponseStatus.COMPLETE, finding),
            known_references=frozenset({"item-1"}),
            context_complete=True,
        )


def test_unknown_references_are_reported_deterministically() -> None:
    finding = AnalysisFinding(
        "finding-1",
        "A claim with mixed references.",
        ("unknown-z", "item-1", "unknown-a"),
    )

    with pytest.raises(
        AnalysisResponseValidationError,
        match=r"unknown-a, unknown-z$",
    ):
        validate_analysis_response(
            response(AnalysisResponseStatus.COMPLETE, finding),
            known_references=frozenset({"item-1"}),
            context_complete=True,
        )


def test_grounded_partial_findings_are_valid_for_insufficient_context() -> None:
    validate_analysis_response(
        response(
            AnalysisResponseStatus.INSUFFICIENT_CONTEXT,
            AnalysisFinding("finding-1", "A supported partial conclusion.", ("item-1",)),
        ),
        known_references=frozenset({"item-1"}),
        context_complete=False,
    )
