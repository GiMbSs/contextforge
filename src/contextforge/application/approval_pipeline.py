"""Explicit approval and authorized patch application orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from contextforge.application.messages import ApplyPatchProposal, ApprovePatchProposal
from contextforge.application.patches import (
    PatchApplication,
    PatchApplicationResult,
    PatchApplicationStatus,
)
from contextforge.domain import (
    ApprovalId,
    PatchProposalId,
    ProjectFingerprint,
    ProposalFingerprint,
    new_approval_id,
)
from contextforge.patch import (
    ApprovalBindingError,
    ApprovalRecord,
    PatchProposal,
    PatchProposalLifecycle,
    ProposalLifecycleState,
    fingerprint_patch_proposal,
)


class PatchWorkflowStorage(Protocol):
    """Load and persist the durable records of a patch workflow."""

    def load_proposal(self, proposal_id: PatchProposalId) -> PatchProposal | None:
        """Load one exact proposal by identifier."""
        ...

    def load_lifecycle(self, proposal_id: PatchProposalId) -> PatchProposalLifecycle | None:
        """Load the current lifecycle for one proposal."""
        ...

    def save_lifecycle(self, lifecycle: PatchProposalLifecycle) -> None:
        """Persist a lifecycle transition."""
        ...

    def save_approval(self, approval: ApprovalRecord) -> None:
        """Persist explicit approval before any application attempt."""
        ...

    def load_approval(self, approval_id: ApprovalId) -> ApprovalRecord | None:
        """Load approval evidence by its exact identifier."""
        ...

    def save_application_result(self, result: PatchApplicationResult) -> None:
        """Persist the outcome of every application attempt."""
        ...


class CurrentProjectState(Protocol):
    """Calculate trusted project state immediately before authorization."""

    def fingerprint(self, proposal: PatchProposal) -> ProjectFingerprint:
        """Return the current fingerprint for the proposal's project."""
        ...


class PatchWorkflowError(RuntimeError):
    """Base failure for approval and application orchestration."""


class PatchProposalNotFoundError(PatchWorkflowError):
    """The explicitly selected proposal does not exist."""


class PatchApprovalNotFoundError(PatchWorkflowError):
    """The explicitly selected approval does not exist."""


class PatchWorkflowStateError(PatchWorkflowError):
    """The requested operation is invalid for the current lifecycle."""


class StaleProjectStateError(PatchWorkflowError):
    """The project changed since proposal materialization."""


class PatchApprovalBindingError(PatchWorkflowError):
    """Approval is not bound to the exact selected proposal and state."""


@dataclass(frozen=True, slots=True)
class PatchApprovalResult:
    """Durable approval and its resulting lifecycle."""

    approval: ApprovalRecord
    lifecycle: PatchProposalLifecycle


@dataclass(frozen=True, slots=True)
class PatchApplyResult:
    """Persisted application outcome and its resulting lifecycle."""

    application: PatchApplicationResult
    lifecycle: PatchProposalLifecycle


class PatchApprovalApplicationPipeline:
    """Record explicit approval before authorizing a patch application."""

    def __init__(
        self,
        *,
        storage: PatchWorkflowStorage,
        project_state: CurrentProjectState,
        application: PatchApplication,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._storage = storage
        self._project_state = project_state
        self._application = application
        self._clock = clock

    def approve(self, command: ApprovePatchProposal) -> PatchApprovalResult:
        """Record explicit, proposal-bound approval without applying changes."""
        if not isinstance(command, ApprovePatchProposal):
            raise TypeError("command must be an ApprovePatchProposal")
        proposal, lifecycle = self._load_workflow(command.proposal_id)
        self._require_state(lifecycle, ProposalLifecycleState.AWAITING_APPROVAL)
        proposal_fingerprint = fingerprint_patch_proposal(proposal)
        current_project = self._require_current_project(
            proposal,
            lifecycle,
            proposal_fingerprint,
        )
        approval = ApprovalRecord(
            new_approval_id(),
            proposal.proposal_id,
            proposal_fingerprint,
            current_project,
            self._clock(),
            command.method,
            command.approving_principal,
            command.acknowledged_warnings,
        )
        approved = lifecycle.transition(
            ProposalLifecycleState.APPROVED,
            at=self._clock(),
            proposal_fingerprint=proposal_fingerprint,
        )
        self._storage.save_approval(approval)
        self._storage.save_lifecycle(approved)
        return PatchApprovalResult(approval, approved)

    def apply(self, command: ApplyPatchProposal) -> PatchApplyResult:
        """Apply only an exact proposal with separately persisted approval."""
        if not isinstance(command, ApplyPatchProposal):
            raise TypeError("command must be an ApplyPatchProposal")
        proposal, lifecycle = self._load_workflow(command.proposal_id)
        self._require_state(lifecycle, ProposalLifecycleState.APPROVED)
        approval = self._storage.load_approval(command.approval_id)
        if approval is None:
            raise PatchApprovalNotFoundError(str(command.approval_id))

        proposal_fingerprint = fingerprint_patch_proposal(proposal)
        current_project = self._require_current_project(
            proposal,
            lifecycle,
            proposal_fingerprint,
        )
        try:
            approval.validate_binding(
                proposal_id=command.proposal_id,
                proposal_fingerprint=proposal_fingerprint,
                project_fingerprint=current_project,
            )
        except ApprovalBindingError as error:
            raise PatchApprovalBindingError(str(error)) from error

        application = self._application.apply_proposal(
            proposal,
            proposal_fingerprint,
            approval,
        )
        self._storage.save_application_result(application)
        target = (
            ProposalLifecycleState.APPLIED
            if application.status is PatchApplicationStatus.APPLIED
            else ProposalLifecycleState.APPLICATION_FAILED
        )
        completed = lifecycle.transition(
            target,
            at=self._clock(),
            proposal_fingerprint=proposal_fingerprint,
        )
        self._storage.save_lifecycle(completed)
        return PatchApplyResult(application, completed)

    def _load_workflow(
        self,
        proposal_id: PatchProposalId,
    ) -> tuple[PatchProposal, PatchProposalLifecycle]:
        proposal = self._storage.load_proposal(proposal_id)
        lifecycle = self._storage.load_lifecycle(proposal_id)
        if proposal is None or lifecycle is None:
            raise PatchProposalNotFoundError(str(proposal_id))
        return proposal, lifecycle

    @staticmethod
    def _require_state(
        lifecycle: PatchProposalLifecycle,
        expected: ProposalLifecycleState,
    ) -> None:
        if lifecycle.state is not expected:
            raise PatchWorkflowStateError(
                f"proposal must be {expected.value}, not {lifecycle.state.value}"
            )

    def _require_current_project(
        self,
        proposal: PatchProposal,
        lifecycle: PatchProposalLifecycle,
        proposal_fingerprint: ProposalFingerprint,
    ) -> ProjectFingerprint:
        current = self._project_state.fingerprint(proposal)
        if current != proposal.project_fingerprint:
            stale = lifecycle.transition(
                ProposalLifecycleState.STALE,
                at=self._clock(),
                proposal_fingerprint=proposal_fingerprint,
            )
            self._storage.save_lifecycle(stale)
            raise StaleProjectStateError("project state changed after proposal creation")
        return current
