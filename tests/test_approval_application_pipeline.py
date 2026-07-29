"""Tests for explicit approval and application orchestration."""

from datetime import UTC, datetime

import pytest

from contextforge.application import (
    ApplyPatchProposal,
    ApprovePatchProposal,
    PatchApplicationOutcomeUnknownError,
    PatchApplicationPreview,
    PatchApplicationResult,
    PatchApplicationStatus,
    PatchApprovalApplicationPipeline,
    PatchApprovalBindingError,
    PatchApprovalNotFoundError,
    RejectPatchProposal,
    StaleProjectStateError,
)
from contextforge.domain import (
    ArtifactPath,
    FingerprintOrdering,
    fingerprint_project,
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
    PatchProposalLifecycle,
    PatchValidationState,
    PatchValidationSummary,
    ProposalLifecycleState,
    ProposedChange,
    fingerprint_patch_proposal,
)

NOW = datetime(2026, 7, 26, tzinfo=UTC)
PROJECT = fingerprint_project(("approval-pipeline",), ordering=FingerprintOrdering.ORDERED)
STALE_PROJECT = fingerprint_project(("stale",), ordering=FingerprintOrdering.ORDERED)


def _workflow():
    proposal = PatchProposal(
        new_patch_proposal_id(),
        new_task_id(),
        new_inference_request_id(),
        new_inference_response_id(),
        PROJECT,
        (
            ProposedChange(
                "change-1",
                ArtifactPath("example.txt"),
                PatchOperation.CREATE,
                "Create example.",
                patch_payload="content\n",
            ),
        ),
        PatchValidationSummary(PatchValidationState.VALID, NOW),
        NOW,
    )
    fingerprint = fingerprint_patch_proposal(proposal)
    lifecycle = PatchProposalLifecycle.proposed(proposal.proposal_id, fingerprint, NOW)
    lifecycle = lifecycle.transition(
        ProposalLifecycleState.VALIDATED,
        at=NOW,
        proposal_fingerprint=fingerprint,
    ).transition(
        ProposalLifecycleState.AWAITING_APPROVAL,
        at=NOW,
        proposal_fingerprint=fingerprint,
    )
    return proposal, lifecycle


class MemoryStorage:
    def __init__(self, proposal, lifecycle):
        self.proposal = proposal
        self.lifecycle = lifecycle
        self.approvals = {}
        self.application_results = []
        self.events = []
        self.rejections = []
        self.application_attempt = None

    def load_proposal(self, proposal_id):
        return self.proposal if proposal_id == self.proposal.proposal_id else None

    def load_lifecycle(self, proposal_id):
        return self.lifecycle if proposal_id == self.proposal.proposal_id else None

    def save_lifecycle(self, lifecycle):
        self.lifecycle = lifecycle
        self.events.append(f"lifecycle:{lifecycle.state.value}")

    def save_approval(self, approval):
        self.approvals[approval.approval_id] = approval
        self.events.append("approval")

    def save_rejection(self, proposal_id, reason, rejected_at):
        self.rejections.append((proposal_id, reason, rejected_at))
        self.events.append("rejection")

    def load_approval(self, approval_id):
        return self.approvals.get(approval_id)

    def application_attempt_started(self, proposal_id):
        return self.application_attempt is not None and self.application_attempt[0] == proposal_id

    def begin_application_attempt(
        self,
        proposal_id,
        approval_id,
        proposal_fingerprint,
        started_at,
    ):
        self.application_attempt = (
            proposal_id,
            approval_id,
            proposal_fingerprint,
            started_at,
        )
        self.events.append("application-attempt")

    def save_application_result(self, result):
        self.application_results.append(result)
        self.application_attempt = None
        self.events.append("application-result")


class ProjectState:
    def __init__(self, fingerprint=PROJECT):
        self.current = fingerprint

    def fingerprint(self, proposal):
        return self.current


class RecordingApplication:
    def __init__(self, events):
        self.events = events
        self.calls = []

    def preview_application(self, proposal, proposal_fingerprint):
        return PatchApplicationPreview(proposal.proposal_id, ())

    def apply_proposal(self, proposal, proposal_fingerprint, approval):
        self.calls.append((proposal, proposal_fingerprint, approval))
        self.events.append("apply")
        return PatchApplicationResult(
            proposal.proposal_id,
            PatchApplicationStatus.APPLIED,
            applied_change_ids=("change-1",),
        )


def _pipeline(project=PROJECT):
    proposal, lifecycle = _workflow()
    storage = MemoryStorage(proposal, lifecycle)
    application = RecordingApplication(storage.events)
    pipeline = PatchApprovalApplicationPipeline(
        storage=storage,
        project_state=ProjectState(project),
        application=application,
        clock=lambda: NOW,
    )
    return pipeline, storage, application, proposal


def test_approval_is_explicitly_recorded_before_application() -> None:
    pipeline, storage, application, proposal = _pipeline()

    approved = pipeline.approve(
        ApprovePatchProposal(
            proposal.proposal_id,
            ApprovalMethod.INTERACTIVE,
            "developer@example.test",
        )
    )

    assert approved.lifecycle.state is ProposalLifecycleState.APPROVED
    assert application.calls == []
    assert storage.events == ["approval", "lifecycle:approved"]

    applied = pipeline.apply(
        ApplyPatchProposal(proposal.proposal_id, approved.approval.approval_id)
    )

    assert applied.lifecycle.state is ProposalLifecycleState.APPLIED
    assert storage.events == [
        "approval",
        "lifecycle:approved",
        "application-attempt",
        "apply",
        "application-result",
        "lifecycle:applied",
    ]


def test_unknown_application_outcome_is_never_retried() -> None:
    pipeline, storage, application, proposal = _pipeline()
    approved = pipeline.approve(ApprovePatchProposal(proposal.proposal_id, ApprovalMethod.API))
    storage.application_attempt = (
        proposal.proposal_id,
        approved.approval.approval_id,
        approved.approval.proposal_fingerprint,
        NOW,
    )

    with pytest.raises(PatchApplicationOutcomeUnknownError):
        pipeline.apply(
            ApplyPatchProposal(
                proposal.proposal_id,
                approved.approval.approval_id,
            )
        )

    assert application.calls == []


def test_rejection_records_reason_and_terminal_lifecycle() -> None:
    pipeline, storage, application, proposal = _pipeline()

    rejected = pipeline.reject(
        RejectPatchProposal(proposal.proposal_id, "Requires a narrower patch.")
    )

    assert rejected.lifecycle.state is ProposalLifecycleState.REJECTED
    assert rejected.reason == "Requires a narrower patch."
    assert storage.rejections == [(proposal.proposal_id, "Requires a narrower patch.", NOW)]
    assert storage.events == ["rejection", "lifecycle:rejected"]
    assert application.calls == []


def test_apply_does_not_infer_approval_from_application_intent() -> None:
    pipeline, _, application, proposal = _pipeline()
    pipeline.approve(ApprovePatchProposal(proposal.proposal_id, ApprovalMethod.API))

    with pytest.raises(PatchApprovalNotFoundError):
        pipeline.apply(ApplyPatchProposal(proposal.proposal_id, new_approval_id()))

    assert application.calls == []


def test_stale_project_is_persisted_and_rejected_before_approval() -> None:
    pipeline, storage, application, proposal = _pipeline(STALE_PROJECT)

    with pytest.raises(StaleProjectStateError):
        pipeline.approve(ApprovePatchProposal(proposal.proposal_id, ApprovalMethod.INTERACTIVE))

    assert storage.lifecycle.state is ProposalLifecycleState.STALE
    assert not storage.approvals
    assert application.calls == []


def test_approval_for_another_exact_proposal_cannot_be_applied() -> None:
    pipeline, storage, application, proposal = _pipeline()
    approved = pipeline.approve(ApprovePatchProposal(proposal.proposal_id, ApprovalMethod.API))
    wrong = ApprovalRecord(
        approved.approval.approval_id,
        new_patch_proposal_id(),
        approved.approval.proposal_fingerprint,
        approved.approval.project_fingerprint,
        NOW,
        ApprovalMethod.API,
    )
    storage.approvals[wrong.approval_id] = wrong

    with pytest.raises(PatchApprovalBindingError):
        pipeline.apply(ApplyPatchProposal(proposal.proposal_id, wrong.approval_id))

    assert application.calls == []
