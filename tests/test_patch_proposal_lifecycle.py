"""Tests for explicit immutable patch proposal lifecycle transitions."""

from datetime import UTC, datetime, timedelta

import pytest

from contextforge.domain import ProposalFingerprint, new_patch_proposal_id
from contextforge.patch import PatchProposalLifecycle, ProposalLifecycleState

NOW = datetime(2026, 7, 26, tzinfo=UTC)
FINGERPRINT = ProposalFingerprint("proposal_sha256_" + "a" * 64)
CHANGED = ProposalFingerprint("proposal_sha256_" + "b" * 64)


def _lifecycle() -> PatchProposalLifecycle:
    return PatchProposalLifecycle.proposed(new_patch_proposal_id(), FINGERPRINT, NOW)


def _transition(
    lifecycle: PatchProposalLifecycle,
    state: ProposalLifecycleState,
) -> PatchProposalLifecycle:
    return lifecycle.transition(
        state,
        at=lifecycle.transitioned_at + timedelta(seconds=1),
        proposal_fingerprint=FINGERPRINT,
    )


def test_happy_path_uses_only_explicit_transitions() -> None:
    lifecycle = _lifecycle()
    for state in (
        ProposalLifecycleState.VALIDATED,
        ProposalLifecycleState.AWAITING_APPROVAL,
        ProposalLifecycleState.APPROVED,
        ProposalLifecycleState.APPLIED,
    ):
        lifecycle = _transition(lifecycle, state)

    assert lifecycle.state is ProposalLifecycleState.APPLIED


def test_rejected_proposal_cannot_be_reused() -> None:
    lifecycle = _transition(_lifecycle(), ProposalLifecycleState.VALIDATED)
    lifecycle = _transition(lifecycle, ProposalLifecycleState.AWAITING_APPROVAL)
    lifecycle = _transition(lifecycle, ProposalLifecycleState.REJECTED)

    with pytest.raises(ValueError, match="not allowed"):
        _transition(lifecycle, ProposalLifecycleState.APPROVED)


def test_changed_content_invalidates_awaiting_approval() -> None:
    lifecycle = _transition(_lifecycle(), ProposalLifecycleState.VALIDATED)
    lifecycle = _transition(lifecycle, ProposalLifecycleState.AWAITING_APPROVAL)

    stale = lifecycle.invalidate_if_changed(
        CHANGED,
        at=lifecycle.transitioned_at + timedelta(seconds=1),
    )

    assert stale.state is ProposalLifecycleState.STALE


def test_changed_content_cannot_preserve_an_approval_transition() -> None:
    lifecycle = _transition(_lifecycle(), ProposalLifecycleState.VALIDATED)
    lifecycle = _transition(lifecycle, ProposalLifecycleState.AWAITING_APPROVAL)

    with pytest.raises(ValueError, match="invalidation"):
        lifecycle.transition(
            ProposalLifecycleState.APPROVED,
            at=lifecycle.transitioned_at + timedelta(seconds=1),
            proposal_fingerprint=CHANGED,
        )


@pytest.mark.parametrize(
    "terminal",
    (
        ProposalLifecycleState.REJECTED,
        ProposalLifecycleState.STALE,
        ProposalLifecycleState.APPLIED,
    ),
)
def test_terminal_states_have_no_outgoing_transitions(
    terminal: ProposalLifecycleState,
) -> None:
    lifecycle = _lifecycle()
    if terminal is ProposalLifecycleState.REJECTED:
        lifecycle = _transition(lifecycle, ProposalLifecycleState.VALIDATED)
        lifecycle = _transition(lifecycle, ProposalLifecycleState.AWAITING_APPROVAL)
        lifecycle = _transition(lifecycle, terminal)
    elif terminal is ProposalLifecycleState.STALE:
        lifecycle = _transition(lifecycle, terminal)
    else:
        lifecycle = _transition(lifecycle, ProposalLifecycleState.VALIDATED)
        lifecycle = _transition(lifecycle, ProposalLifecycleState.AWAITING_APPROVAL)
        lifecycle = _transition(lifecycle, ProposalLifecycleState.APPROVED)
        lifecycle = _transition(lifecycle, terminal)

    with pytest.raises(ValueError, match="not allowed"):
        _transition(lifecycle, ProposalLifecycleState.VALIDATED)


def test_application_failure_requires_explicit_retry_transition() -> None:
    lifecycle = _transition(_lifecycle(), ProposalLifecycleState.VALIDATED)
    lifecycle = _transition(lifecycle, ProposalLifecycleState.AWAITING_APPROVAL)
    lifecycle = _transition(lifecycle, ProposalLifecycleState.APPROVED)
    failed = _transition(lifecycle, ProposalLifecycleState.APPLICATION_FAILED)

    retried = _transition(failed, ProposalLifecycleState.APPROVED)

    assert retried.state is ProposalLifecycleState.APPROVED
