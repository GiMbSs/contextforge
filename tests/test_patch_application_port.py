"""Tests for the Patch Application architectural port."""

from contextforge.application import (
    ApplicationPreviewChange,
    PatchApplication,
    PatchApplicationPreview,
    PatchApplicationResult,
    PatchApplicationStatus,
)
from contextforge.domain import (
    ArtifactPath,
    ProposalFingerprint,
    new_patch_proposal_id,
)
from contextforge.patch import (
    ApprovalRecord,
    PatchOperation,
    PatchProposal,
)


class FakePatchApplication:
    """Test adapter proving the port can be substituted without filesystem access."""

    def preview_application(
        self,
        proposal: PatchProposal,
        proposal_fingerprint: ProposalFingerprint,
    ) -> PatchApplicationPreview:
        del proposal_fingerprint
        return PatchApplicationPreview(
            proposal.proposal_id,
            tuple(
                ApplicationPreviewChange(
                    change.path,
                    change.operation,
                    change.destination_path,
                )
                for change in proposal.changes
            ),
        )

    def apply_proposal(
        self,
        proposal: PatchProposal,
        proposal_fingerprint: ProposalFingerprint,
        approval: ApprovalRecord,
    ) -> PatchApplicationResult:
        approval.validate_binding(
            proposal_id=proposal.proposal_id,
            proposal_fingerprint=proposal_fingerprint,
            project_fingerprint=proposal.project_fingerprint,
        )
        return PatchApplicationResult(
            proposal.proposal_id,
            PatchApplicationStatus.APPLIED,
        )


def test_fake_adapter_satisfies_runtime_port() -> None:
    assert isinstance(FakePatchApplication(), PatchApplication)


def test_preview_change_preserves_rename_destination() -> None:
    change = ApplicationPreviewChange(
        ArtifactPath("old.py"),
        PatchOperation.RENAME,
        ArtifactPath("new.py"),
    )

    assert change.destination_path == ArtifactPath("new.py")


def test_result_exposes_explicit_partial_status() -> None:
    result = PatchApplicationResult(
        new_patch_proposal_id(),
        PatchApplicationStatus.PARTIALLY_APPLIED,
    )

    assert result.status is PatchApplicationStatus.PARTIALLY_APPLIED
