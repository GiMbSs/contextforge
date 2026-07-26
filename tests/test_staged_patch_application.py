"""Tests for staged, locked local patch application."""

from datetime import UTC, datetime
from pathlib import Path

from contextforge.adapters.filesystem import LocalStagedPatchApplication
from contextforge.application import (
    ApplicationPreflightEvidence,
    PatchApplicationStatus,
)
from contextforge.domain import (
    ArtifactPath,
    FingerprintOrdering,
    fingerprint_content,
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
    PatchSourceArtifact,
    PatchSourceState,
    PatchValidationState,
    PatchValidationSummary,
    ProposedChange,
    fingerprint_patch_proposal,
)
from contextforge.project import ProjectRoot, ProjectRootSource

NOW = datetime(2026, 7, 26, tzinfo=UTC)
PROJECT_FINGERPRINT = fingerprint_project(
    ("staged-project",),
    ordering=FingerprintOrdering.ORDERED,
)


def _change(
    identifier: str,
    path: str,
    operation: PatchOperation,
    *,
    content: str | None = None,
    destination: str | None = None,
    old_content: str | None = None,
) -> ProposedChange:
    return ProposedChange(
        identifier,
        ArtifactPath(path),
        operation,
        "Apply staged change.",
        patch_payload=content,
        destination_path=(ArtifactPath(destination) if destination is not None else None),
        expected_old_fingerprint=(
            fingerprint_content(old_content) if old_content is not None else None
        ),
    )


def _setup(root: Path):
    existing = {
        "modify.txt": "old\n",
        "delete.txt": "delete\n",
        "rename.txt": "rename\n",
    }
    for relative, content in existing.items():
        (root / relative).write_text(content, encoding="utf-8")
    changes = (
        _change(
            "create",
            "nested/create.txt",
            PatchOperation.CREATE,
            content="created\n",
        ),
        _change(
            "delete",
            "delete.txt",
            PatchOperation.DELETE,
            old_content=existing["delete.txt"],
        ),
        _change(
            "modify",
            "modify.txt",
            PatchOperation.MODIFY,
            content="modified\n",
            old_content=existing["modify.txt"],
        ),
        _change(
            "rename",
            "rename.txt",
            PatchOperation.RENAME,
            destination="renamed.txt",
            old_content=existing["rename.txt"],
        ),
    )
    proposal = PatchProposal(
        new_patch_proposal_id(),
        new_task_id(),
        new_inference_request_id(),
        new_inference_response_id(),
        PROJECT_FINGERPRINT,
        changes,
        PatchValidationSummary(PatchValidationState.VALID, NOW),
        NOW,
    )
    proposal_fingerprint = fingerprint_patch_proposal(proposal)
    approval = ApprovalRecord(
        new_approval_id(),
        proposal.proposal_id,
        proposal_fingerprint,
        PROJECT_FINGERPRINT,
        NOW,
        ApprovalMethod.INTERACTIVE,
    )
    source_state = PatchSourceState(
        tuple(
            PatchSourceArtifact(
                ArtifactPath(relative),
                fingerprint_content(content),
            )
            for relative, content in existing.items()
        )
    )
    writable = tuple(
        path
        for change in changes
        for path in (change.path, change.destination_path)
        if path is not None
    )

    def evidence() -> ApplicationPreflightEvidence:
        return ApplicationPreflightEvidence(
            PROJECT_FINGERPRINT,
            source_state,
            writable,
            not (root / ".contextforge" / "mutation.lock").exists(),
        )

    adapter = LocalStagedPatchApplication(
        ProjectRoot(root, ProjectRootSource.EXPLICIT),
        evidence,
    )
    return adapter, proposal, proposal_fingerprint, approval


def test_preview_performs_no_filesystem_mutation(tmp_path: Path) -> None:
    adapter, proposal, fingerprint, _ = _setup(tmp_path)

    preview = adapter.preview_application(proposal, fingerprint)

    assert len(preview.changes) == 4
    assert not (tmp_path / ".contextforge").exists()
    assert not tuple(tmp_path.parent.glob(".contextforge-stage-*"))


def test_application_stages_locks_revalidates_and_applies(tmp_path: Path) -> None:
    adapter, proposal, fingerprint, approval = _setup(tmp_path)

    result = adapter.apply_proposal(proposal, fingerprint, approval)

    assert result.status is PatchApplicationStatus.APPLIED
    assert (tmp_path / "nested/create.txt").read_text(encoding="utf-8") == "created\n"
    assert (tmp_path / "modify.txt").read_text(encoding="utf-8") == "modified\n"
    assert not (tmp_path / "delete.txt").exists()
    assert not (tmp_path / "rename.txt").exists()
    assert (tmp_path / "renamed.txt").read_text(encoding="utf-8") == "rename\n"
    assert not (tmp_path / ".contextforge" / "mutation.lock").exists()
    assert not tuple(tmp_path.parent.glob(".contextforge-stage-*"))


def test_unavailable_lock_prevents_all_application(tmp_path: Path) -> None:
    adapter, proposal, fingerprint, approval = _setup(tmp_path)
    lock = tmp_path / ".contextforge" / "mutation.lock"
    lock.parent.mkdir()
    lock.write_text("held", encoding="utf-8")

    result = adapter.apply_proposal(proposal, fingerprint, approval)

    assert result.status is PatchApplicationStatus.FAILED
    assert (tmp_path / "modify.txt").read_text(encoding="utf-8") == "old\n"
    assert lock.read_text(encoding="utf-8") == "held"
