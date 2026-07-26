"""Tests for immediate, mutation-free patch application preflight."""

from datetime import UTC, datetime

from contextforge.application import (
    ApplicationPreflightEvidence,
    PatchApplicationPreflight,
)
from contextforge.domain import (
    ArtifactPath,
    ContentFingerprint,
    ProjectFingerprint,
    new_approval_id,
    new_inference_request_id,
    new_inference_response_id,
    new_patch_proposal_id,
    new_task_id,
)
from contextforge.patch import (
    ApprovalMethod,
    ApprovalRecord,
    PatchOperation,
    PatchProposal,
    PatchSourceArtifact,
    PatchSourceState,
    PatchValidationState,
    PatchValidationSummary,
    ProposedChange,
    fingerprint_patch_proposal,
)

NOW = datetime(2026, 7, 26, tzinfo=UTC)
PROJECT = ProjectFingerprint("project_sha256_" + "a" * 64)
CONTENT = ContentFingerprint("content_sha256_" + "b" * 64)


def _proposal() -> PatchProposal:
    return PatchProposal(
        new_patch_proposal_id(),
        new_task_id(),
        new_inference_request_id(),
        new_inference_response_id(),
        PROJECT,
        (
            ProposedChange(
                "change-1",
                ArtifactPath("app.py"),
                PatchOperation.MODIFY,
                "Update.",
                patch_payload="new\n",
                expected_old_fingerprint=CONTENT,
            ),
        ),
        PatchValidationSummary(PatchValidationState.VALID, NOW),
        NOW,
    )


def _approval(proposal: PatchProposal) -> ApprovalRecord:
    return ApprovalRecord(
        new_approval_id(),
        proposal.proposal_id,
        fingerprint_patch_proposal(proposal),
        PROJECT,
        NOW,
        ApprovalMethod.INTERACTIVE,
    )


def _evidence(
    *,
    project: ProjectFingerprint = PROJECT,
    writable: tuple[str, ...] = ("app.py",),
    locked: bool = True,
    source: bool = True,
) -> ApplicationPreflightEvidence:
    return ApplicationPreflightEvidence(
        project,
        PatchSourceState((PatchSourceArtifact(ArtifactPath("app.py"), CONTENT),) if source else ()),
        tuple(ArtifactPath(path) for path in writable),
        locked,
    )


def test_exact_approved_current_state_is_ready() -> None:
    proposal = _proposal()

    result = PatchApplicationPreflight().validate(
        proposal,
        fingerprint_patch_proposal(proposal),
        _approval(proposal),
        _evidence(),
    )

    assert result.ready
    assert result.diagnostics == ()


def test_preflight_accumulates_mutable_precondition_failures() -> None:
    proposal = _proposal()
    changed_project = ProjectFingerprint("project_sha256_" + "c" * 64)

    result = PatchApplicationPreflight().validate(
        proposal,
        fingerprint_patch_proposal(proposal),
        _approval(proposal),
        _evidence(
            project=changed_project,
            writable=(),
            locked=False,
            source=False,
        ),
    )

    assert not result.ready
    assert {str(item.code) for item in result.diagnostics} == {
        "PATCH_PREFLIGHT_PROJECT_FINGERPRINT_MISMATCH",
        "PATCH_PREFLIGHT_APPROVAL_MISMATCH",
        "PATCH_OPERATION_MODIFY_MISSING_SOURCE",
        "PATCH_PREFLIGHT_PERMISSION_DENIED",
        "PATCH_PREFLIGHT_LOCK_UNAVAILABLE",
    }


def test_untrusted_proposal_fingerprint_is_recomputed() -> None:
    proposal = _proposal()
    wrong = type(fingerprint_patch_proposal(proposal))("proposal_sha256_" + "d" * 64)

    result = PatchApplicationPreflight().validate(
        proposal,
        wrong,
        _approval(proposal),
        _evidence(),
    )

    assert str(result.diagnostics[0].code) == ("PATCH_PREFLIGHT_PROPOSAL_FINGERPRINT_MISMATCH")
