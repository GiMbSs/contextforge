"""Explicit immutable lifecycle for patch proposals."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from contextforge.domain import PatchProposalId, ProposalFingerprint


class ProposalLifecycleState(StrEnum):
    """Canonical review and application states of one proposal."""

    PROPOSED = "proposed"
    VALIDATED = "validated"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    STALE = "stale"
    APPLIED = "applied"
    APPLICATION_FAILED = "application_failed"


_ALLOWED_TRANSITIONS: dict[ProposalLifecycleState, frozenset[ProposalLifecycleState]] = {
    ProposalLifecycleState.PROPOSED: frozenset(
        {ProposalLifecycleState.VALIDATED, ProposalLifecycleState.STALE}
    ),
    ProposalLifecycleState.VALIDATED: frozenset(
        {ProposalLifecycleState.AWAITING_APPROVAL, ProposalLifecycleState.STALE}
    ),
    ProposalLifecycleState.AWAITING_APPROVAL: frozenset(
        {
            ProposalLifecycleState.APPROVED,
            ProposalLifecycleState.REJECTED,
            ProposalLifecycleState.STALE,
        }
    ),
    ProposalLifecycleState.APPROVED: frozenset(
        {
            ProposalLifecycleState.APPLIED,
            ProposalLifecycleState.APPLICATION_FAILED,
            ProposalLifecycleState.STALE,
        }
    ),
    ProposalLifecycleState.APPLICATION_FAILED: frozenset(
        {ProposalLifecycleState.APPROVED, ProposalLifecycleState.STALE}
    ),
    ProposalLifecycleState.REJECTED: frozenset(),
    ProposalLifecycleState.STALE: frozenset(),
    ProposalLifecycleState.APPLIED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class PatchProposalLifecycle:
    """Current lifecycle state bound to exact immutable proposal content."""

    proposal_id: PatchProposalId
    proposal_fingerprint: ProposalFingerprint
    state: ProposalLifecycleState
    transitioned_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.proposal_id, PatchProposalId):
            raise TypeError("proposal_id must be a PatchProposalId")
        if not isinstance(self.proposal_fingerprint, ProposalFingerprint):
            raise TypeError("proposal_fingerprint must be a ProposalFingerprint")
        if not isinstance(self.state, ProposalLifecycleState):
            raise TypeError("state must be a ProposalLifecycleState")
        _require_aware(self.transitioned_at)

    @classmethod
    def proposed(
        cls,
        proposal_id: PatchProposalId,
        proposal_fingerprint: ProposalFingerprint,
        at: datetime,
    ) -> PatchProposalLifecycle:
        """Start an explicit lifecycle for newly materialized proposal content."""
        return cls(
            proposal_id,
            proposal_fingerprint,
            ProposalLifecycleState.PROPOSED,
            at,
        )

    def transition(
        self,
        target: ProposalLifecycleState,
        *,
        at: datetime,
        proposal_fingerprint: ProposalFingerprint,
    ) -> PatchProposalLifecycle:
        """Apply one allowed transition for the exact bound proposal content."""
        if not isinstance(target, ProposalLifecycleState):
            raise TypeError("target must be a ProposalLifecycleState")
        if not isinstance(proposal_fingerprint, ProposalFingerprint):
            raise TypeError("proposal_fingerprint must be a ProposalFingerprint")
        _require_aware(at)
        if at < self.transitioned_at:
            raise ValueError("transition timestamp must not move backwards")
        if proposal_fingerprint != self.proposal_fingerprint:
            raise ValueError("changed proposal content requires invalidation as stale")
        if target not in _ALLOWED_TRANSITIONS[self.state]:
            raise ValueError(f"transition from {self.state} to {target} is not allowed")
        return replace(self, state=target, transitioned_at=at)

    def invalidate_if_changed(
        self,
        proposal_fingerprint: ProposalFingerprint,
        *,
        at: datetime,
    ) -> PatchProposalLifecycle:
        """Invalidate reusable state when proposal content no longer matches."""
        if not isinstance(proposal_fingerprint, ProposalFingerprint):
            raise TypeError("proposal_fingerprint must be a ProposalFingerprint")
        _require_aware(at)
        if at < self.transitioned_at:
            raise ValueError("transition timestamp must not move backwards")
        if proposal_fingerprint == self.proposal_fingerprint:
            return self
        if self.state in (
            ProposalLifecycleState.REJECTED,
            ProposalLifecycleState.STALE,
            ProposalLifecycleState.APPLIED,
        ):
            return self
        return replace(self, state=ProposalLifecycleState.STALE, transitioned_at=at)


def _require_aware(value: datetime) -> None:
    if not isinstance(value, datetime):
        raise TypeError("transitioned_at must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("transitioned_at must be timezone-aware")
