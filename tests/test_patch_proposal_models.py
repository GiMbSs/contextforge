"""Tests for immutable patch proposal domain models."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from contextforge.diagnostics import DiagnosticCode, DiagnosticSeverity
from contextforge.domain import (
    ArtifactPath,
    ProjectFingerprint,
    new_inference_request_id,
    new_inference_response_id,
    new_patch_proposal_id,
    new_task_id,
)
from contextforge.patch import (
    PatchApprovalState,
    PatchDiagnostic,
    PatchOperation,
    PatchProposal,
    PatchValidationState,
    PatchValidationSummary,
    ProposedChange,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _change() -> ProposedChange:
    return ProposedChange(
        "change-1",
        ArtifactPath("src/app.py"),
        PatchOperation.MODIFY,
        "Correct behavior.",
        "@@ -1 +1 @@\n-old\n+new",
    )


def _validation() -> PatchValidationSummary:
    return PatchValidationSummary(PatchValidationState.VALID, NOW)


def test_patch_proposal_is_traceable_pending_and_immutable() -> None:
    proposal = PatchProposal(
        new_patch_proposal_id(),
        new_task_id(),
        new_inference_request_id(),
        new_inference_response_id(),
        ProjectFingerprint("project_sha256_" + "a" * 64),
        (_change(),),
        _validation(),
        NOW,
        "Correct behavior.",
    )

    assert proposal.approval_state is PatchApprovalState.PENDING
    with pytest.raises(FrozenInstanceError):
        proposal.summary = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("operation", tuple(PatchOperation))
def test_all_canonical_operations_are_represented(operation: PatchOperation) -> None:
    kwargs: dict[str, object] = {}
    if operation in (PatchOperation.CREATE, PatchOperation.MODIFY):
        kwargs["patch_payload"] = "content"
    if operation is PatchOperation.RENAME:
        kwargs["destination_path"] = ArtifactPath("renamed.py")

    change = ProposedChange(
        "change-1",
        ArtifactPath("file.py"),
        operation,
        "Explain.",
        **kwargs,  # type: ignore[arg-type]
    )

    assert change.operation is operation


def test_validation_state_reflects_error_diagnostics() -> None:
    diagnostic = PatchDiagnostic(
        DiagnosticCode("PATCH_INVALID_PATH"),
        DiagnosticSeverity.ERROR,
        "Path is invalid.",
        "change-1",
    )

    summary = PatchValidationSummary(
        PatchValidationState.INVALID,
        NOW,
        (diagnostic,),
    )

    assert summary.state is PatchValidationState.INVALID


def test_duplicate_change_identifiers_are_rejected() -> None:
    change = _change()

    with pytest.raises(ValueError, match="identifiers must be unique"):
        PatchProposal(
            new_patch_proposal_id(),
            new_task_id(),
            new_inference_request_id(),
            new_inference_response_id(),
            ProjectFingerprint("project_sha256_" + "a" * 64),
            (change, change),
            _validation(),
            NOW,
        )


def test_rename_requires_a_distinct_destination() -> None:
    path = ArtifactPath("file.py")

    with pytest.raises(ValueError, match="differ"):
        ProposedChange(
            "change-1",
            path,
            PatchOperation.RENAME,
            "Rename.",
            destination_path=path,
        )
