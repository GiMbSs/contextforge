"""Provider-independent analysis response contract."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from contextforge.prompt.models import ResponseContract, ResponseFormat

ANALYSIS_RESPONSE_CONTRACT_ID = "analysis-response"
ANALYSIS_RESPONSE_CONTRACT_VERSION = "analysis-response-v1"


class AnalysisResponseStatus(StrEnum):
    """Completion state represented inside an analysis response."""

    COMPLETE = "complete"
    INSUFFICIENT_CONTEXT = "insufficient_context"


@dataclass(frozen=True, slots=True)
class AnalysisFinding:
    """One analysis conclusion with source evidence."""

    finding_id: str
    statement: str
    evidence_references: tuple[str, ...]
    confidence: float | None = None

    def __post_init__(self) -> None:
        if not self.finding_id.strip() or any(character.isspace() for character in self.finding_id):
            raise ValueError("finding_id must be a non-empty identifier")
        if not self.statement.strip():
            raise ValueError("statement must not be empty")
        references = tuple(self.evidence_references)
        if any(not reference.strip() for reference in references):
            raise ValueError("evidence_references must contain non-empty values")
        if len(set(references)) != len(references):
            raise ValueError("evidence_references must be unique")
        if self.confidence is not None:
            if not isinstance(self.confidence, (int, float)):
                raise TypeError("confidence must be numeric")
            if not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
                raise ValueError("confidence must be finite and between zero and one")
        object.__setattr__(self, "evidence_references", references)


@dataclass(frozen=True, slots=True)
class AnalysisResponse:
    """Structured non-patch response suitable for provider normalization."""

    status: AnalysisResponseStatus
    summary: str
    findings: tuple[AnalysisFinding, ...]
    assumptions: tuple[str, ...]
    limitations: tuple[str, ...]
    diagnostics: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()
    recommended_next_action: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, AnalysisResponseStatus):
            raise TypeError("status must be an AnalysisResponseStatus")
        if not self.summary.strip():
            raise ValueError("summary must not be empty")
        findings = tuple(self.findings)
        if any(not isinstance(finding, AnalysisFinding) for finding in findings):
            raise TypeError("findings must contain AnalysisFinding values")
        finding_ids = tuple(finding.finding_id for finding in findings)
        if len(set(finding_ids)) != len(finding_ids):
            raise ValueError("finding identifiers must be unique")
        normalized_collections: dict[str, tuple[str, ...]] = {}
        for field_name in ("assumptions", "limitations", "diagnostics", "uncertainties"):
            values = tuple(getattr(self, field_name))
            if any(not value.strip() for value in values):
                raise ValueError(f"{field_name} must contain non-empty values")
            normalized_collections[field_name] = values
        if (
            self.status is AnalysisResponseStatus.INSUFFICIENT_CONTEXT
            and not normalized_collections["limitations"]
            and not normalized_collections["diagnostics"]
        ):
            raise ValueError(
                "An insufficient-context response must explain a limitation or diagnostic"
            )
        if self.recommended_next_action is not None and not self.recommended_next_action.strip():
            raise ValueError("recommended_next_action must not be empty")
        object.__setattr__(self, "findings", findings)
        for field_name, values in normalized_collections.items():
            object.__setattr__(self, field_name, values)


def analysis_response_contract() -> ResponseContract:
    """Return the canonical non-patch analysis response contract."""
    return ResponseContract(
        contract_id=ANALYSIS_RESPONSE_CONTRACT_ID,
        version=ANALYSIS_RESPONSE_CONTRACT_VERSION,
        purpose="Return a structured analysis without modifying the project.",
        response_type="analysis",
        output_format=ResponseFormat.JSON,
        required_fields=(
            "status",
            "summary",
            "findings",
            "assumptions",
            "limitations",
            "diagnostics",
        ),
        prohibited_operations=(
            "claim_project_modification",
            "apply_patch",
            "execute_project",
        ),
        error_behavior=(
            "Return status insufficient_context with limitations or diagnostics "
            "when the supplied context cannot support the analysis."
        ),
        validation_instructions=(
            "Every finding must cite one or more supplied context references.",
            "Do not claim that project files were modified.",
            "Represent uncertainty and assumptions explicitly.",
        ),
        allow_commentary=False,
    )


class AnalysisResponseDecodeError(ValueError):
    """Provider content does not satisfy the analysis response contract."""


def decode_analysis_response(content: str) -> AnalysisResponse:
    """Decode and validate one JSON analysis response."""
    if not isinstance(content, str):
        raise TypeError("content must be a string")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        raise AnalysisResponseDecodeError("Analysis response is not valid JSON") from error
    if not isinstance(payload, dict):
        raise AnalysisResponseDecodeError("Analysis response must be a JSON object")

    required = {
        "status",
        "summary",
        "findings",
        "assumptions",
        "limitations",
        "diagnostics",
    }
    optional = {"uncertainties", "recommended_next_action"}
    if not required <= set(payload) or not set(payload) <= required | optional:
        raise AnalysisResponseDecodeError("Analysis response fields do not match the contract")

    status = payload["status"]
    summary = payload["summary"]
    findings = payload["findings"]
    if not isinstance(status, str) or not isinstance(summary, str):
        raise AnalysisResponseDecodeError("Analysis status and summary must be strings")
    if not isinstance(findings, list):
        raise AnalysisResponseDecodeError("Analysis findings must be an array")

    decoded_findings: list[AnalysisFinding] = []
    for finding in findings:
        if not isinstance(finding, dict) or not {
            "finding_id",
            "statement",
            "evidence_references",
        } <= set(finding) <= {
            "finding_id",
            "statement",
            "evidence_references",
            "confidence",
        }:
            raise AnalysisResponseDecodeError("Analysis finding fields do not match the contract")
        finding_id = finding["finding_id"]
        statement = finding["statement"]
        references = finding["evidence_references"]
        confidence = finding.get("confidence")
        if (
            not isinstance(finding_id, str)
            or not isinstance(statement, str)
            or not isinstance(references, list)
            or not all(isinstance(item, str) for item in references)
            or (
                confidence is not None
                and (isinstance(confidence, bool) or not isinstance(confidence, (int, float)))
            )
        ):
            raise AnalysisResponseDecodeError("Analysis finding values have invalid types")
        decoded_findings.append(
            AnalysisFinding(
                finding_id,
                statement,
                tuple(cast("list[str]", references)),
                cast("float | None", confidence),
            )
        )

    collections: dict[str, tuple[str, ...]] = {}
    for field_name in (
        "assumptions",
        "limitations",
        "diagnostics",
        "uncertainties",
    ):
        value = payload.get(field_name, [])
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise AnalysisResponseDecodeError(f"Analysis {field_name} must be an array of strings")
        collections[field_name] = tuple(cast("list[str]", value))
    next_action = payload.get("recommended_next_action")
    if next_action is not None and not isinstance(next_action, str):
        raise AnalysisResponseDecodeError("recommended_next_action must be a string")

    try:
        return AnalysisResponse(
            AnalysisResponseStatus(status),
            summary,
            tuple(decoded_findings),
            collections["assumptions"],
            collections["limitations"],
            collections["diagnostics"],
            collections["uncertainties"],
            next_action,
        )
    except (TypeError, ValueError) as error:
        raise AnalysisResponseDecodeError(str(error)) from error
