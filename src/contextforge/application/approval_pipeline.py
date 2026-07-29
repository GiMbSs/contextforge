"""Explicit approval and authorized patch application orchestration."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from contextforge.application.messages import (
    ApplyPatchProposal,
    ApprovePatchProposal,
    RejectPatchProposal,
)
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

    def save_rejection(
        self,
        proposal_id: PatchProposalId,
        reason: str,
        rejected_at: datetime,
    ) -> None:
        """Persist the auditable reason for an explicit rejection."""
        ...

    def load_approval(self, approval_id: ApprovalId) -> ApprovalRecord | None:
        """Load approval evidence by its exact identifier."""
        ...

    def application_attempt_started(self, proposal_id: PatchProposalId) -> bool:
        """Whether an application attempt was durably submitted."""
        ...

    def load_application_attempt(
        self,
        proposal_id: PatchProposalId,
    ) -> Mapping[str, object] | None:
        """Load application evidence for manual reconciliation."""
        ...

    def begin_application_attempt(
        self,
        proposal_id: PatchProposalId,
        approval_id: ApprovalId,
        proposal_fingerprint: ProposalFingerprint,
        started_at: datetime,
    ) -> None:
        """Persist application intent before project mutation starts."""
        ...

    def save_application_result(self, result: PatchApplicationResult) -> None:
        """Persist the outcome of every application attempt."""
        ...

    def save_application_reconciliation(
        self,
        result: PatchApplicationResult,
        outcome: PatchApplicationReconciliationOutcome,
        reconciled_at: datetime,
    ) -> None:
        """Persist a manually attested outcome without losing its provenance."""
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


class PatchApplicationOutcomeUnknownError(PatchWorkflowError):
    """An earlier application was submitted without a durable outcome."""


class PatchApplicationReconciliationOutcome(StrEnum):
    """Operator-attested resolution of an interrupted application."""

    APPLIED = "applied"
    ROLLED_BACK = "rolled_back"


@dataclass(frozen=True, slots=True)
class ReconcilePatchApplication:
    """Resolve one unknown application outcome with explicit recovery evidence."""

    proposal_id: PatchProposalId
    approval_id: ApprovalId
    outcome: PatchApplicationReconciliationOutcome
    recovery_reference: str

    def __post_init__(self) -> None:
        if not isinstance(self.proposal_id, PatchProposalId):
            raise TypeError("proposal_id must be a PatchProposalId")
        if not isinstance(self.approval_id, ApprovalId):
            raise TypeError("approval_id must be an ApprovalId")
        if not isinstance(self.outcome, PatchApplicationReconciliationOutcome):
            raise TypeError("outcome must be a PatchApplicationReconciliationOutcome")
        if not isinstance(self.recovery_reference, str) or not self.recovery_reference.strip():
            raise ValueError("recovery_reference must be non-empty text")


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


@dataclass(frozen=True, slots=True)
class PatchApplicationReconciliationResult:
    """Persisted operator resolution and resulting proposal lifecycle."""

    application: PatchApplicationResult
    outcome: PatchApplicationReconciliationOutcome
    lifecycle: PatchProposalLifecycle


@dataclass(frozen=True, slots=True)
class PatchRejectionResult:
    """Durable rejection reason and its resulting lifecycle."""

    reason: str
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

    def reject(self, command: RejectPatchProposal) -> PatchRejectionResult:
        """Record an explicit rejection without applying project changes."""
        if not isinstance(command, RejectPatchProposal):
            raise TypeError("command must be a RejectPatchProposal")
        proposal, lifecycle = self._load_workflow(command.proposal_id)
        self._require_state(lifecycle, ProposalLifecycleState.AWAITING_APPROVAL)
        proposal_fingerprint = fingerprint_patch_proposal(proposal)
        rejected_at = self._clock()
        rejected = lifecycle.transition(
            ProposalLifecycleState.REJECTED,
            at=rejected_at,
            proposal_fingerprint=proposal_fingerprint,
        )
        self._storage.save_rejection(
            proposal.proposal_id,
            command.reason,
            rejected_at,
        )
        self._storage.save_lifecycle(rejected)
        return PatchRejectionResult(command.reason, rejected)

    def apply(self, command: ApplyPatchProposal) -> PatchApplyResult:
        """Apply only an exact proposal with separately persisted approval."""
        if not isinstance(command, ApplyPatchProposal):
            raise TypeError("command must be an ApplyPatchProposal")
        proposal, lifecycle = self._load_workflow(command.proposal_id)
        self._require_state(lifecycle, ProposalLifecycleState.APPROVED)
        approval = self._storage.load_approval(command.approval_id)
        if approval is None:
            raise PatchApprovalNotFoundError(str(command.approval_id))
        if self._storage.application_attempt_started(proposal.proposal_id):
            raise PatchApplicationOutcomeUnknownError(
                "A previous patch application outcome is unknown"
            )

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

        self._storage.begin_application_attempt(
            proposal.proposal_id,
            approval.approval_id,
            proposal_fingerprint,
            self._clock(),
        )
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

    def reconcile(
        self,
        command: ReconcilePatchApplication,
    ) -> PatchApplicationReconciliationResult:
        """Resolve a submitted attempt only from explicit operator evidence."""
        if not isinstance(command, ReconcilePatchApplication):
            raise TypeError("command must be a ReconcilePatchApplication")
        proposal, lifecycle = self._load_workflow(command.proposal_id)
        if lifecycle.state is not ProposalLifecycleState.APPROVED and not (
            lifecycle.state is ProposalLifecycleState.APPLIED
            and command.outcome is PatchApplicationReconciliationOutcome.APPLIED
        ):
            raise PatchWorkflowStateError(
                f"Expected approved lifecycle, found {lifecycle.state.value}"
            )
        attempt = self._storage.load_application_attempt(command.proposal_id)
        if attempt is None or attempt.get("attempt_status") not in {
            "submitted",
            "reconciled",
        }:
            raise PatchWorkflowStateError(
                "Proposal has no unknown application outcome to reconcile"
            )
        if (
            attempt.get("attempt_status") == "reconciled"
            and attempt.get("resolution") != command.outcome.value
        ):
            raise PatchWorkflowStateError(
                "Application attempt was already reconciled with another outcome"
            )
        if attempt.get("approval_id") != str(command.approval_id):
            raise PatchApprovalBindingError("Application attempt is bound to another approval")
        proposal_fingerprint = fingerprint_patch_proposal(proposal)
        if attempt.get("proposal_fingerprint") != str(proposal_fingerprint):
            raise PatchApprovalBindingError(
                "Application attempt proposal fingerprint does not match"
            )
        change_ids = tuple(change.change_id for change in proposal.changes)
        applied = command.outcome is PatchApplicationReconciliationOutcome.APPLIED
        application = PatchApplicationResult(
            proposal.proposal_id,
            (PatchApplicationStatus.APPLIED if applied else PatchApplicationStatus.FAILED),
            applied_change_ids=change_ids if applied else (),
            unapplied_change_ids=() if applied else change_ids,
            rollback_verified=True if not applied else None,
            recovery_reference=command.recovery_reference,
        )
        reconciled_at = self._clock()
        if attempt.get("attempt_status") == "submitted":
            self._storage.save_application_reconciliation(
                application,
                command.outcome,
                reconciled_at,
            )
        if applied and lifecycle.state is ProposalLifecycleState.APPROVED:
            lifecycle = lifecycle.transition(
                ProposalLifecycleState.APPLIED,
                at=reconciled_at,
                proposal_fingerprint=proposal_fingerprint,
            )
            self._storage.save_lifecycle(lifecycle)
        return PatchApplicationReconciliationResult(
            application,
            command.outcome,
            lifecycle,
        )

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
