"""Tests for immutable, exactly bound patch approval records."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from contextforge.domain import (
    ProjectFingerprint,
    ProposalFingerprint,
    new_approval_id,
    new_patch_proposal_id,
)
from contextforge.patch import (
    ApprovalBindingError,
    ApprovalMethod,
    ApprovalRecord,
)

NOW = datetime(2026, 7, 26, tzinfo=UTC)
PROPOSAL_FINGERPRINT = ProposalFingerprint("proposal_sha256_" + "a" * 64)
PROJECT_FINGERPRINT = ProjectFingerprint("project_sha256_" + "b" * 64)


def _record() -> ApprovalRecord:
    return ApprovalRecord(
        new_approval_id(),
        new_patch_proposal_id(),
        PROPOSAL_FINGERPRINT,
        PROJECT_FINGERPRINT,
        NOW,
        ApprovalMethod.INTERACTIVE,
        "developer@example.test",
        ("PATCH_WARNING_GENERATED_FILE",),
    )


def test_approval_record_is_immutable_and_auditable() -> None:
    record = _record()

    assert record.method is ApprovalMethod.INTERACTIVE
    assert record.acknowledged_warnings == ("PATCH_WARNING_GENERATED_FILE",)
    with pytest.raises(FrozenInstanceError):
        record.approving_principal = "other"  # type: ignore[misc]


def test_exact_binding_is_accepted() -> None:
    record = _record()

    record.validate_binding(
        proposal_id=record.proposal_id,
        proposal_fingerprint=record.proposal_fingerprint,
        project_fingerprint=record.project_fingerprint,
    )


def test_proposal_identifier_mismatch_is_rejected() -> None:
    record = _record()

    with pytest.raises(ApprovalBindingError, match="another proposal"):
        record.validate_binding(
            proposal_id=new_patch_proposal_id(),
            proposal_fingerprint=record.proposal_fingerprint,
            project_fingerprint=record.project_fingerprint,
        )


def test_proposal_fingerprint_mismatch_is_rejected() -> None:
    record = _record()

    with pytest.raises(ApprovalBindingError, match="proposal fingerprint"):
        record.validate_binding(
            proposal_id=record.proposal_id,
            proposal_fingerprint=ProposalFingerprint("proposal_sha256_" + "c" * 64),
            project_fingerprint=record.project_fingerprint,
        )


def test_project_state_mismatch_is_rejected() -> None:
    record = _record()

    with pytest.raises(ApprovalBindingError, match="project state"):
        record.validate_binding(
            proposal_id=record.proposal_id,
            proposal_fingerprint=record.proposal_fingerprint,
            project_fingerprint=ProjectFingerprint("project_sha256_" + "d" * 64),
        )


def test_acknowledged_warnings_are_unique_and_deterministic() -> None:
    record = _record()
    with pytest.raises(ValueError, match="duplicates"):
        ApprovalRecord(
            record.approval_id,
            record.proposal_id,
            record.proposal_fingerprint,
            record.project_fingerprint,
            NOW,
            ApprovalMethod.API,
            acknowledged_warnings=("warning", "warning"),
        )
