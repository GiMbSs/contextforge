"""Eligibility and security filtering before retrieval budgeting."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum

from contextforge.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticCollection,
    DiagnosticLocation,
    DiagnosticSeverity,
)
from contextforge.domain import ArtifactId
from contextforge.indexer import ProjectIndex
from contextforge.retrieval.models import (
    CandidateEligibility,
    CandidateOutcome,
    RetrievalCandidate,
    RetrievalEvidence,
    SelectionDecision,
    SelectionRationale,
    SelectionReason,
)

ELIGIBILITY_FILTER_VERSION = "eligibility-filter-v1"


class ProviderDeliveryMode(StrEnum):
    """Whether selected content remains local or is delivered remotely."""

    LOCAL = "local"
    REMOTE = "remote"


class GeneratedArtifactPolicy(StrEnum):
    """Configured handling of generated artifacts."""

    EXCLUDE = "exclude"
    DEPRIORITIZE = "deprioritize"
    ALLOW = "allow"


@dataclass(frozen=True, slots=True)
class ArtifactEligibilityRecord:
    """Security-relevant classifications retained outside candidate content."""

    artifact_id: ArtifactId
    sensitive: bool = False
    binary: bool = False
    generated: bool = False
    ignored: bool = False
    unsupported: bool = False
    content_available: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_id, ArtifactId):
            raise TypeError("artifact_id must be an ArtifactId")
        for name in (
            "sensitive",
            "binary",
            "generated",
            "ignored",
            "unsupported",
            "content_available",
        ):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be a boolean")


@dataclass(frozen=True, slots=True)
class EligibilityPolicy:
    """Provider-aware immutable candidate policy."""

    provider_mode: ProviderDeliveryMode = ProviderDeliveryMode.LOCAL
    allow_sensitive_local: bool = True
    authorized_sensitive_artifact_ids: tuple[ArtifactId, ...] = ()
    generated_policy: GeneratedArtifactPolicy = GeneratedArtifactPolicy.DEPRIORITIZE

    def __post_init__(self) -> None:
        if not isinstance(self.provider_mode, ProviderDeliveryMode):
            raise TypeError("provider_mode must be a ProviderDeliveryMode")
        if type(self.allow_sensitive_local) is not bool:
            raise TypeError("allow_sensitive_local must be a boolean")
        authorized = tuple(self.authorized_sensitive_artifact_ids)
        if any(not isinstance(item, ArtifactId) for item in authorized):
            raise TypeError("authorized_sensitive_artifact_ids must contain ArtifactId values")
        if len(set(authorized)) != len(authorized):
            raise ValueError("authorized_sensitive_artifact_ids must not contain duplicates")
        if not isinstance(self.generated_policy, GeneratedArtifactPolicy):
            raise TypeError("generated_policy must be a GeneratedArtifactPolicy")
        object.__setattr__(self, "authorized_sensitive_artifact_ids", authorized)


@dataclass(frozen=True, slots=True)
class EligibilityFilterResult:
    """Policy-filtered candidates and observable diagnostics."""

    candidates: tuple[RetrievalCandidate, ...]
    diagnostics: DiagnosticCollection
    filter_version: str = ELIGIBILITY_FILTER_VERSION


def _evidence(detail: str) -> RetrievalEvidence:
    return RetrievalEvidence("eligibility-policy", ELIGIBILITY_FILTER_VERSION, detail)


def _excluded(
    candidate: RetrievalCandidate,
    eligibility: CandidateEligibility,
    reason: SelectionReason,
    detail: str,
) -> RetrievalCandidate:
    evidence = (*candidate.evidence, _evidence(detail))
    rationale = SelectionRationale(
        candidate.candidate_id,
        SelectionDecision.EXCLUDED,
        reason,
        evidence,
        explanation=detail,
    )
    return replace(
        candidate,
        evidence=evidence,
        eligibility=eligibility,
        outcome=CandidateOutcome.EXCLUDED,
        rationale=rationale,
    )


def _diagnostic(code: str, candidate: RetrievalCandidate, message: str) -> Diagnostic:
    return Diagnostic(
        DiagnosticCode(code),
        DiagnosticSeverity.WARNING,
        message,
        "context-retriever",
        DiagnosticLocation(candidate.source_reference),
        metadata=(("candidate_id", candidate.candidate_id),),
    )


@dataclass(frozen=True, slots=True)
class CandidateEligibilityFilter:
    """Apply security and artifact policies without reading candidate content."""

    policy: EligibilityPolicy = field(default_factory=EligibilityPolicy)
    version: str = ELIGIBILITY_FILTER_VERSION

    def filter(
        self,
        candidates: tuple[RetrievalCandidate, ...],
        project_index: ProjectIndex,
        records: tuple[ArtifactEligibilityRecord, ...] = (),
    ) -> EligibilityFilterResult:
        """Return candidates with policy decisions applied before budgeting."""
        if any(not isinstance(candidate, RetrievalCandidate) for candidate in candidates):
            raise TypeError("candidates must contain RetrievalCandidate values")
        if not isinstance(project_index, ProjectIndex):
            raise TypeError("project_index must be a ProjectIndex")
        if any(not isinstance(record, ArtifactEligibilityRecord) for record in records):
            raise TypeError("records must contain ArtifactEligibilityRecord values")
        by_artifact = {record.artifact_id: record for record in records}
        if len(by_artifact) != len(records):
            raise ValueError("records must not contain duplicate artifact identifiers")
        indexed_ids = {artifact.artifact_id for artifact in project_index.indexed_artifacts}
        authorized = set(self.policy.authorized_sensitive_artifact_ids)
        filtered = []
        diagnostics = []

        for candidate in candidates:
            artifact_id = candidate.artifact_id
            if artifact_id is not None and artifact_id not in indexed_ids:
                filtered.append(
                    _excluded(
                        candidate,
                        CandidateEligibility.UNAVAILABLE,
                        SelectionReason.CONTENT_UNAVAILABLE,
                        "Candidate source does not belong to the active Project Index.",
                    )
                )
                continue
            record = by_artifact.get(artifact_id) if artifact_id is not None else None
            if record is None:
                filtered.append(candidate)
                continue

            sensitive_allowed = artifact_id in authorized or (
                self.policy.provider_mode is ProviderDeliveryMode.LOCAL
                and self.policy.allow_sensitive_local
            )
            if record.sensitive and not sensitive_allowed:
                filtered.append(
                    _excluded(
                        candidate,
                        CandidateEligibility.PROHIBITED,
                        SelectionReason.SECURITY_PROHIBITED,
                        "Sensitive content is prohibited for the active provider policy.",
                    )
                )
                diagnostics.append(
                    _diagnostic(
                        "RETRIEVAL_SENSITIVE_EXCLUDED",
                        candidate,
                        "Sensitive candidate was excluded from provider delivery.",
                    )
                )
            elif (
                record.binary
                or record.ignored
                or record.unsupported
                or not record.content_available
            ):
                filtered.append(
                    _excluded(
                        candidate,
                        CandidateEligibility.UNAVAILABLE,
                        SelectionReason.ARTIFACT_POLICY_EXCLUDED,
                        "Artifact content is unavailable under the active artifact policy.",
                    )
                )
            elif (
                record.generated and self.policy.generated_policy is GeneratedArtifactPolicy.EXCLUDE
            ):
                filtered.append(
                    _excluded(
                        candidate,
                        CandidateEligibility.INELIGIBLE,
                        SelectionReason.ARTIFACT_POLICY_EXCLUDED,
                        "Generated artifact is excluded by policy.",
                    )
                )
            elif (
                record.generated
                and self.policy.generated_policy is GeneratedArtifactPolicy.DEPRIORITIZE
            ):
                generated_evidence = RetrievalEvidence(
                    "generated-artifact-penalty",
                    self.version,
                    "Generated artifact is eligible with reduced priority.",
                    1.0,
                )
                filtered.append(
                    replace(
                        candidate,
                        evidence=(*candidate.evidence, generated_evidence),
                    )
                )
                diagnostics.append(
                    _diagnostic(
                        "RETRIEVAL_GENERATED_DEPRIORITIZED",
                        candidate,
                        "Generated candidate was retained with reduced priority.",
                    )
                )
            else:
                authorization_evidence = (
                    (_evidence("Sensitive content explicitly authorized by the user."),)
                    if record.sensitive and artifact_id in authorized
                    else ()
                )
                filtered.append(
                    replace(
                        candidate,
                        evidence=(*candidate.evidence, *authorization_evidence),
                    )
                )

        return EligibilityFilterResult(
            tuple(filtered),
            DiagnosticCollection(tuple(diagnostics)),
            self.version,
        )
