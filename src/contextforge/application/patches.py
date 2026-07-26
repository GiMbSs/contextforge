"""Port and immutable contracts for patch application."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from contextforge.domain import ArtifactPath, PatchProposalId, ProposalFingerprint
from contextforge.patch.approval import ApprovalRecord
from contextforge.patch.models import PatchDiagnostic, PatchOperation, PatchProposal


@dataclass(frozen=True, slots=True)
class ApplicationPreviewChange:
    """One operation that an application adapter intends to perform."""

    path: ArtifactPath
    operation: PatchOperation
    destination_path: ArtifactPath | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.path, ArtifactPath):
            raise TypeError("path must be an ArtifactPath")
        if not isinstance(self.operation, PatchOperation):
            raise TypeError("operation must be a PatchOperation")
        if self.operation is PatchOperation.RENAME:
            if not isinstance(self.destination_path, ArtifactPath):
                raise TypeError("rename preview requires an ArtifactPath destination")
        elif self.destination_path is not None:
            raise ValueError("destination_path is only valid for rename previews")


@dataclass(frozen=True, slots=True)
class PatchApplicationPreview:
    """Read-only deterministic preview produced before any mutation."""

    proposal_id: PatchProposalId
    changes: tuple[ApplicationPreviewChange, ...]
    diagnostics: tuple[PatchDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.proposal_id, PatchProposalId):
            raise TypeError("proposal_id must be a PatchProposalId")
        changes = tuple(self.changes)
        if not changes:
            raise ValueError("changes must not be empty")
        if any(not isinstance(item, ApplicationPreviewChange) for item in changes):
            raise TypeError("changes must contain ApplicationPreviewChange values")
        diagnostics = tuple(self.diagnostics)
        if any(not isinstance(item, PatchDiagnostic) for item in diagnostics):
            raise TypeError("diagnostics must contain PatchDiagnostic values")
        object.__setattr__(
            self,
            "changes",
            tuple(sorted(changes, key=lambda item: (item.path, item.operation))),
        )
        object.__setattr__(self, "diagnostics", diagnostics)


class PatchApplicationStatus(StrEnum):
    """High-level outcome reported by a patch application adapter."""

    APPLIED = "applied"
    FAILED = "failed"
    PARTIALLY_APPLIED = "partially_applied"


@dataclass(frozen=True, slots=True)
class PatchApplicationResult:
    """Adapter-neutral outcome of an attempted application."""

    proposal_id: PatchProposalId
    status: PatchApplicationStatus
    diagnostics: tuple[PatchDiagnostic, ...] = ()
    applied_change_ids: tuple[str, ...] = ()
    unapplied_change_ids: tuple[str, ...] = ()
    rollback_verified: bool | None = None
    recovery_reference: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.proposal_id, PatchProposalId):
            raise TypeError("proposal_id must be a PatchProposalId")
        if not isinstance(self.status, PatchApplicationStatus):
            raise TypeError("status must be a PatchApplicationStatus")
        diagnostics = tuple(self.diagnostics)
        if any(not isinstance(item, PatchDiagnostic) for item in diagnostics):
            raise TypeError("diagnostics must contain PatchDiagnostic values")
        object.__setattr__(self, "diagnostics", diagnostics)
        applied = tuple(self.applied_change_ids)
        unapplied = tuple(self.unapplied_change_ids)
        for values, field_name in (
            (applied, "applied_change_ids"),
            (unapplied, "unapplied_change_ids"),
        ):
            if any(not isinstance(item, str) or not item.strip() for item in values):
                raise ValueError(f"{field_name} must contain non-empty text")
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must not contain duplicates")
        if set(applied) & set(unapplied):
            raise ValueError("applied and unapplied change identifiers must be disjoint")
        if type(self.rollback_verified) not in (bool, type(None)):
            raise TypeError("rollback_verified must be a boolean or None")
        if self.recovery_reference is not None and (
            not isinstance(self.recovery_reference, str) or not self.recovery_reference.strip()
        ):
            raise ValueError("recovery_reference must be non-empty text")
        if self.status is PatchApplicationStatus.PARTIALLY_APPLIED and (
            not applied or not unapplied
        ):
            raise ValueError("partial application requires applied and unapplied changes")
        if self.rollback_verified is True and applied:
            raise ValueError("verified rollback cannot report applied changes")
        object.__setattr__(self, "applied_change_ids", applied)
        object.__setattr__(self, "unapplied_change_ids", unapplied)


@runtime_checkable
class PatchApplication(Protocol):
    """Only architectural port authorized to request project-file mutation."""

    def preview_application(
        self,
        proposal: PatchProposal,
        proposal_fingerprint: ProposalFingerprint,
    ) -> PatchApplicationPreview:
        """Describe intended operations without mutating project state."""
        ...

    def apply_proposal(
        self,
        proposal: PatchProposal,
        proposal_fingerprint: ProposalFingerprint,
        approval: ApprovalRecord,
    ) -> PatchApplicationResult:
        """Apply an exactly approved proposal through an authorized adapter."""
        ...
