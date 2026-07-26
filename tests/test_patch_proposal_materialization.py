"""Tests for immutable patch proposal materialization."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from contextforge.domain import (
    ArtifactPath,
    ContentFingerprint,
    ProjectFingerprint,
    new_inference_request_id,
    new_inference_response_id,
    new_patch_proposal_id,
    new_task_id,
)
from contextforge.patch import (
    PatchConsistencyEvidence,
    PatchOperation,
    PatchProposalMaterializer,
    PatchSourceArtifact,
    PatchSourceState,
    ProposedChange,
)

NOW = datetime(2026, 7, 26, tzinfo=UTC)
PROJECT_FINGERPRINT = ProjectFingerprint("project_sha256_" + "a" * 64)
CONTENT_FINGERPRINT = ContentFingerprint("content_sha256_" + "b" * 64)


def _change(
    *,
    path: str = "src/app.py",
    expected: ContentFingerprint | None = CONTENT_FINGERPRINT,
) -> ProposedChange:
    return ProposedChange(
        "change-1",
        ArtifactPath(path),
        PatchOperation.MODIFY,
        "Correct behavior.",
        patch_payload="updated\n",
        expected_old_fingerprint=expected,
    )


def _materialize(
    change: ProposedChange,
    *,
    source_paths: tuple[str, ...] = ("src/app.py",),
    affected_files: tuple[str, ...] = ("src/app.py",),
):
    source = PatchSourceState(
        tuple(PatchSourceArtifact(ArtifactPath(path), CONTENT_FINGERPRINT) for path in source_paths)
    )
    consistency = PatchConsistencyEvidence(
        tuple(ArtifactPath(path) for path in affected_files),
        PROJECT_FINGERPRINT,
        PROJECT_FINGERPRINT,
    )
    identifiers = (
        new_patch_proposal_id(),
        new_task_id(),
        new_inference_request_id(),
        new_inference_response_id(),
    )
    result = PatchProposalMaterializer().materialize(
        proposal_id=identifiers[0],
        task_id=identifiers[1],
        request_id=identifiers[2],
        response_id=identifiers[3],
        changes=(change,),
        source_state=source,
        consistency=consistency,
        created_at=NOW,
        summary="Correct behavior.",
    )
    return result, identifiers


def test_valid_input_produces_fully_traceable_immutable_proposal() -> None:
    result, identifiers = _materialize(_change())

    assert result.is_applicable
    assert result.diagnostics == ()
    proposal = result.proposal
    assert proposal is not None
    assert (
        proposal.proposal_id,
        proposal.task_id,
        proposal.request_id,
        proposal.response_id,
    ) == identifiers
    assert proposal.project_fingerprint == PROJECT_FINGERPRINT
    assert proposal.validation.validated_at == NOW
    with pytest.raises(FrozenInstanceError):
        proposal.summary = "mutated"  # type: ignore[misc]


def test_invalid_operation_produces_diagnostics_and_no_proposal() -> None:
    result, _ = _materialize(_change(), source_paths=())

    assert not result.is_applicable
    assert result.proposal is None
    assert tuple(str(item.code) for item in result.diagnostics) == (
        "PATCH_OPERATION_MODIFY_MISSING_SOURCE",
    )


def test_all_validation_diagnostics_are_returned_without_partial_proposal() -> None:
    result, _ = _materialize(
        _change(path=".env"),
        source_paths=(),
        affected_files=("different.py",),
    )

    assert result.proposal is None
    assert {str(item.code) for item in result.diagnostics} == {
        "PATCH_PATH_PROTECTED",
        "PATCH_OPERATION_MODIFY_MISSING_SOURCE",
        "PATCH_CONSISTENCY_AFFECTED_FILES_MISMATCH",
    }
    assert result.diagnostics[0].change_id == "change-1"


def test_fingerprint_mismatch_prevents_materialization() -> None:
    result, _ = _materialize(
        _change(
            expected=ContentFingerprint("content_sha256_" + "c" * 64),
        )
    )

    assert result.proposal is None
    assert str(result.diagnostics[0].code) == "PATCH_OPERATION_FINGERPRINT_MISMATCH"
