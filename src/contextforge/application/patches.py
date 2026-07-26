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

    def __post_init__(self) -> None:
        if not isinstance(self.proposal_id, PatchProposalId):
            raise TypeError("proposal_id must be a PatchProposalId")
        if not isinstance(self.status, PatchApplicationStatus):
            raise TypeError("status must be a PatchApplicationStatus")
        diagnostics = tuple(self.diagnostics)
        if any(not isinstance(item, PatchDiagnostic) for item in diagnostics):
            raise TypeError("diagnostics must contain PatchDiagnostic values")
        object.__setattr__(self, "diagnostics", diagnostics)


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
