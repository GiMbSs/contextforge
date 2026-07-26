"""Tests for the structured patch proposal response contract."""

from dataclasses import FrozenInstanceError

import pytest

from contextforge.domain import ArtifactPath
from contextforge.prompt import (
    PatchPayloadFormat,
    PatchResponseEnvelope,
    ProposedChangeOperation,
    ProposedFileChange,
    ResponseFormat,
    patch_response_contract,
)


def test_patch_contract_requires_a_structured_non_applying_envelope() -> None:
    contract = patch_response_contract()

    assert contract.output_format is ResponseFormat.STRUCTURED_PATCH
    assert contract.required_fields == (
        "response_type",
        "summary",
        "assumptions",
        "patch_format",
        "patch_payload",
        "affected_files",
        "warnings",
    )
    assert "claim_patch_applied" in contract.prohibited_operations
    assert "path_outside_project_root" in contract.prohibited_operations
    assert not contract.allow_commentary


def test_patch_envelope_retains_payload_and_declared_files() -> None:
    path = ArtifactPath("src/contextforge/app.py")
    change = ProposedFileChange(
        path,
        ProposedChangeOperation.MODIFY,
        "Handle the empty input explicitly.",
        "@@ -1 +1 @@\n-old\n+new",
        validation_notes=("Run unit tests.",),
    )
    envelope = PatchResponseEnvelope(
        "patch_proposal",
        "Handle empty input.",
        ("The public behavior should remain compatible.",),
        PatchPayloadFormat.UNIFIED_DIFF,
        "--- a/src/contextforge/app.py\n+++ b/src/contextforge/app.py",
        (path,),
        (),
        (change,),
    )

    assert envelope.affected_files == (path,)
    assert envelope.changes == (change,)
    with pytest.raises(FrozenInstanceError):
        envelope.summary = "changed"  # type: ignore[misc]


def test_patch_paths_are_project_relative_value_objects() -> None:
    with pytest.raises(ValueError, match="project-relative"):
        ArtifactPath("/etc/passwd")


def test_affected_files_must_match_structured_changes() -> None:
    change = ProposedFileChange(
        ArtifactPath("src/a.py"),
        ProposedChangeOperation.MODIFY,
        "Change A.",
        "patch",
    )

    with pytest.raises(ValueError, match="exactly match"):
        PatchResponseEnvelope(
            "patch_proposal",
            "Change A.",
            (),
            PatchPayloadFormat.STRUCTURED_CHANGES,
            '{"changes":[]}',
            (ArtifactPath("src/b.py"),),
            (),
            (change,),
        )


def test_delete_and_rename_do_not_accept_replacement_payloads() -> None:
    with pytest.raises(ValueError, match="must not include patch"):
        ProposedFileChange(
            ArtifactPath("obsolete.py"),
            ProposedChangeOperation.DELETE,
            "Remove obsolete module.",
            "unexpected content",
        )


def test_rename_requires_a_distinct_destination() -> None:
    path = ArtifactPath("old.py")

    with pytest.raises(ValueError, match="differ"):
        ProposedFileChange(
            path,
            ProposedChangeOperation.RENAME,
            "Use the canonical name.",
            destination_path=path,
        )
