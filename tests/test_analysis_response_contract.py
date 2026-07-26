"""Tests for the non-patch analysis response contract."""

import json
from dataclasses import FrozenInstanceError

import pytest

from contextforge.prompt import (
    AnalysisFinding,
    AnalysisResponse,
    AnalysisResponseDecodeError,
    AnalysisResponseStatus,
    ResponseFormat,
    analysis_response_contract,
    decode_analysis_response,
)


def test_analysis_contract_is_explicit_structured_and_non_mutating() -> None:
    contract = analysis_response_contract()

    assert contract.output_format is ResponseFormat.JSON
    assert contract.required_fields == (
        "status",
        "summary",
        "findings",
        "assumptions",
        "limitations",
        "diagnostics",
    )
    assert {"claim_project_modification", "apply_patch"} <= set(contract.prohibited_operations)
    assert not contract.allow_commentary


def test_analysis_response_retains_findings_assumptions_and_limitations() -> None:
    finding = AnalysisFinding(
        "finding-1",
        "The command delegates to the application layer.",
        ("item-main",),
        0.9,
    )
    response = AnalysisResponse(
        AnalysisResponseStatus.COMPLETE,
        "The command is a thin adapter.",
        (finding,),
        ("The selected entry point is current.",),
        ("Runtime behavior was not executed.",),
    )

    assert response.findings[0].evidence_references == ("item-main",)
    assert response.assumptions
    assert response.limitations
    with pytest.raises(FrozenInstanceError):
        response.summary = "changed"  # type: ignore[misc]


def test_insufficient_context_is_a_structured_response() -> None:
    response = AnalysisResponse(
        AnalysisResponseStatus.INSUFFICIENT_CONTEXT,
        "The behavior cannot be determined.",
        (),
        (),
        ("The called implementation is absent from the Context Bundle.",),
        diagnostics=("MISSING_IMPLEMENTATION",),
        recommended_next_action="Retrieve the referenced implementation.",
    )

    assert response.status is AnalysisResponseStatus.INSUFFICIENT_CONTEXT
    assert response.diagnostics == ("MISSING_IMPLEMENTATION",)


def test_insufficient_context_requires_an_explanation() -> None:
    with pytest.raises(ValueError, match="limitation or diagnostic"):
        AnalysisResponse(
            AnalysisResponseStatus.INSUFFICIENT_CONTEXT,
            "Not enough context.",
            (),
            (),
            (),
        )


def test_analysis_findings_reject_invalid_confidence() -> None:
    with pytest.raises(ValueError, match="between zero and one"):
        AnalysisFinding("finding-1", "Statement", (), 1.1)


def test_analysis_response_decoder_validates_nested_findings() -> None:
    response = decode_analysis_response(
        json.dumps(
            {
                "status": "complete",
                "summary": "Validated analysis.",
                "findings": [
                    {
                        "finding_id": "finding-1",
                        "statement": "The application delegates through a port.",
                        "evidence_references": ["item-1"],
                        "confidence": 0.8,
                    }
                ],
                "assumptions": [],
                "limitations": ["The project was not executed."],
                "diagnostics": [],
            }
        )
    )

    assert response.findings[0].evidence_references == ("item-1",)
    assert response.findings[0].confidence == 0.8


@pytest.mark.parametrize(
    "content",
    [
        "not-json",
        "[]",
        '{"status":"complete"}',
        (
            '{"status":"complete","summary":"x","findings":[],"assumptions":[],'
            '"limitations":[],"diagnostics":[],"unexpected":true}'
        ),
    ],
)
def test_analysis_response_decoder_rejects_content_outside_contract(
    content: str,
) -> None:
    with pytest.raises(AnalysisResponseDecodeError):
        decode_analysis_response(content)
