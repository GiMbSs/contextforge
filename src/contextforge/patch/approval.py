"""Immutable approval records bound to exact proposal and project state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from contextforge.domain import (
    ApprovalId,
    PatchProposalId,
    ProjectFingerprint,
    ProposalFingerprint,
)


class ApprovalMethod(StrEnum):
    """Auditable mechanism through which approval was granted."""

    INTERACTIVE = "interactive"
    NON_INTERACTIVE = "non_interactive"
    POLICY = "policy"
    API = "api"


@dataclass(frozen=True, slots=True)
class ApprovalRecord:
    """Approval evidence bound to immutable proposal and project fingerprints."""

    approval_id: ApprovalId
    proposal_id: PatchProposalId
    proposal_fingerprint: ProposalFingerprint
    project_fingerprint: ProjectFingerprint
    approved_at: datetime
    method: ApprovalMethod
    approving_principal: str | None = None
    acknowledged_warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        expected_types = (
            (self.approval_id, ApprovalId, "approval_id"),
            (self.proposal_id, PatchProposalId, "proposal_id"),
            (self.proposal_fingerprint, ProposalFingerprint, "proposal_fingerprint"),
            (self.project_fingerprint, ProjectFingerprint, "project_fingerprint"),
        )
        for value, expected, field_name in expected_types:
            if not isinstance(value, expected):
                raise TypeError(f"{field_name} must be {expected.__name__}")
        if not isinstance(self.approved_at, datetime):
            raise TypeError("approved_at must be a datetime")
        if self.approved_at.tzinfo is None or self.approved_at.utcoffset() is None:
            raise ValueError("approved_at must be timezone-aware")
        if not isinstance(self.method, ApprovalMethod):
            raise TypeError("method must be an ApprovalMethod")
        if self.approving_principal is not None and (
            not isinstance(self.approving_principal, str) or not self.approving_principal.strip()
        ):
            raise ValueError("approving_principal must be non-empty text")
        warnings = tuple(self.acknowledged_warnings)
        if any(not isinstance(item, str) or not item.strip() for item in warnings):
            raise ValueError("acknowledged_warnings must contain non-empty text")
        if len(set(warnings)) != len(warnings):
            raise ValueError("acknowledged_warnings must not contain duplicates")
        object.__setattr__(self, "acknowledged_warnings", tuple(sorted(warnings)))

    def validate_binding(
        self,
        *,
        proposal_id: PatchProposalId,
        proposal_fingerprint: ProposalFingerprint,
        project_fingerprint: ProjectFingerprint,
    ) -> None:
        """Reject reuse for another proposal, content revision, or project state."""
        if not isinstance(proposal_id, PatchProposalId):
            raise TypeError("proposal_id must be a PatchProposalId")
        if not isinstance(proposal_fingerprint, ProposalFingerprint):
            raise TypeError("proposal_fingerprint must be a ProposalFingerprint")
        if not isinstance(project_fingerprint, ProjectFingerprint):
            raise TypeError("project_fingerprint must be a ProjectFingerprint")
        if proposal_id != self.proposal_id:
            raise ApprovalBindingError("approval is bound to another proposal")
        if proposal_fingerprint != self.proposal_fingerprint:
            raise ApprovalBindingError("approval proposal fingerprint does not match")
        if project_fingerprint != self.project_fingerprint:
            raise ApprovalBindingError("approval project state does not match")


class ApprovalBindingError(ValueError):
    """Approval cannot authorize the supplied proposal and project state."""
