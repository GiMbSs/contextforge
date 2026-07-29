"""CLI tests for persisted patch proposal review."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from contextforge.adapters.filesystem import patches as patch_adapter
from contextforge.adapters.patch_proposals import LocalPatchProposalStorage
from contextforge.adapters.project_commands import LocalProjectCommandGateway
from contextforge.cli.main import app
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
    PatchDiagnostic,
    PatchOperation,
    PatchProposal,
    PatchProposalLifecycle,
    PatchValidationState,
    PatchValidationSummary,
    ProposalLifecycleState,
    ProposedChange,
    fingerprint_patch_proposal,
)
from contextforge.project import ProjectRoot, ProjectRootSource

runner = CliRunner()
NOW = datetime(2026, 7, 26, tzinfo=UTC)


def _payload(result: object) -> dict[str, object]:
    return json.loads(result.stdout)["data"]  # type: ignore[attr-defined,no-any-return]


def _persist_proposal(project: Path) -> str:
    (project / ".contextforge").mkdir()
    root = ProjectRoot(project.resolve(), ProjectRootSource.EXPLICIT)
    project_fingerprint = ProjectFingerprint(
        str(LocalProjectCommandGateway().scan(root).data["project_fingerprint"])
    )
    proposal = PatchProposal(
        new_patch_proposal_id(),
        new_task_id(),
        new_inference_request_id(),
        new_inference_response_id(),
        project_fingerprint,
        (
            ProposedChange(
                "change-1",
                ArtifactPath("src/app.py"),
                PatchOperation.MODIFY,
                "Correct the return value.",
                patch_payload="@@ -1 +1 @@\n-old\n+new\n",
                assumptions=("Existing behavior is covered.",),
            ),
            ProposedChange(
                "change-2",
                ArtifactPath("tests/test_app.py"),
                PatchOperation.CREATE,
                "Add regression coverage.",
                patch_payload="def test_app():\n    assert True\n",
            ),
        ),
        PatchValidationSummary(
            PatchValidationState.VALID_WITH_WARNINGS,
            NOW,
            (
                PatchDiagnostic(
                    DiagnosticCode("PATCH_PATH_PROTECTED"),
                    DiagnosticSeverity.WARNING,
                    "Review protected path.",
                    "change-1",
                ),
            ),
        ),
        NOW,
        "Correct behavior and add coverage.",
    )
    fingerprint = fingerprint_patch_proposal(proposal)
    lifecycle = (
        PatchProposalLifecycle.proposed(
            proposal.proposal_id,
            fingerprint,
            NOW,
        )
        .transition(
            ProposalLifecycleState.VALIDATED,
            at=NOW,
            proposal_fingerprint=fingerprint,
        )
        .transition(
            ProposalLifecycleState.AWAITING_APPROVAL,
            at=NOW,
            proposal_fingerprint=fingerprint,
        )
    )
    LocalPatchProposalStorage(root).save(proposal, lifecycle)
    return str(proposal.proposal_id)


def _persist_applicable_proposal(project: Path, *, change_count: int = 1) -> str:
    (project / ".contextforge").mkdir(exist_ok=True)
    root = ProjectRoot(project.resolve(), ProjectRootSource.EXPLICIT)
    project_fingerprint = ProjectFingerprint(
        str(LocalProjectCommandGateway().scan(root).data["project_fingerprint"])
    )
    proposal = PatchProposal(
        new_patch_proposal_id(),
        new_task_id(),
        new_inference_request_id(),
        new_inference_response_id(),
        project_fingerprint,
        tuple(
            ProposedChange(
                f"change-{number}",
                ArtifactPath(f"created-{number}.txt"),
                PatchOperation.CREATE,
                "Create an approved file.",
                patch_payload=f"created {number}\n",
            )
            for number in range(1, change_count + 1)
        ),
        PatchValidationSummary(PatchValidationState.VALID, NOW),
        NOW,
        "Create approved files.",
    )
    fingerprint = fingerprint_patch_proposal(proposal)
    lifecycle = (
        PatchProposalLifecycle.proposed(proposal.proposal_id, fingerprint, NOW)
        .transition(
            ProposalLifecycleState.VALIDATED,
            at=NOW,
            proposal_fingerprint=fingerprint,
        )
        .transition(
            ProposalLifecycleState.AWAITING_APPROVAL,
            at=NOW,
            proposal_fingerprint=fingerprint,
        )
    )
    LocalPatchProposalStorage(root).save(proposal, lifecycle)
    return str(proposal.proposal_id)


def _approve_non_interactively(project: Path, proposal_id: str) -> None:
    result = runner.invoke(
        app,
        [
            "--project",
            str(project),
            "--non-interactive",
            "patch",
            "approve",
            proposal_id,
            "--approve",
            proposal_id,
        ],
    )
    assert result.exit_code == 0, (result.stdout, result.stderr, result.exception)


def test_patch_list_and_show_use_persisted_application_result(tmp_path: Path) -> None:
    proposal_id = _persist_proposal(tmp_path)

    listing = runner.invoke(
        app,
        ["--project", str(tmp_path), "--format", "json", "patch", "list"],
    )
    shown = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--format",
            "json",
            "patch",
            "show",
            proposal_id,
        ],
    )

    assert listing.exit_code == 0
    summary = _payload(listing)["proposals"][0]
    assert summary["proposal_id"] == proposal_id
    assert summary["change_count"] == 2
    assert summary["lifecycle_state"] == "awaiting_approval"
    assert _payload(shown)["proposal"]["proposal_id"] == proposal_id


def test_patch_review_prioritizes_operations_files_warnings_and_state(
    tmp_path: Path,
) -> None:
    proposal_id = _persist_proposal(tmp_path)

    result = runner.invoke(
        app,
        ["--project", str(tmp_path), "--format", "json", "patch", "review"],
    )

    assert result.exit_code == 0
    review = _payload(result)["review"]
    assert review["proposal_id"] == proposal_id
    assert review["affected_files"] == ["src/app.py", "tests/test_app.py"]
    assert review["operation_counts"] == {
        "create": 1,
        "delete": 0,
        "modify": 1,
        "rename": 0,
    }
    assert review["changes"][0]["added_lines"] == 1
    assert review["changes"][0]["removed_lines"] == 1
    assert review["validation_state"] == "valid_with_warnings"
    assert review["warnings"][0]["code"] == "PATCH_PATH_PROTECTED"


def test_patch_export_writes_explicit_destination(tmp_path: Path) -> None:
    proposal_id = _persist_proposal(tmp_path)
    destination = tmp_path / "exports" / "proposal.json"
    destination.parent.mkdir()

    result = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--format",
            "json",
            "patch",
            "export",
            proposal_id,
            "--output",
            str(destination),
        ],
    )

    assert result.exit_code == 0
    assert json.loads(destination.read_text(encoding="utf-8"))["proposal_id"] == proposal_id
    assert _payload(result)["destination"] == str(destination)


def test_patch_show_reports_missing_proposal(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--format",
            "json",
            "patch",
            "show",
            "proposal_missing",
        ],
    )

    assert result.exit_code == 1
    assert _payload(result) == {"status": "failed"}
    assert "CLI_PATCH_PROPOSAL_NOT_FOUND" in result.stderr


def test_patch_approve_requires_exact_typed_confirmation_for_high_risk(
    tmp_path: Path,
) -> None:
    proposal_id = _persist_proposal(tmp_path)

    declined = runner.invoke(
        app,
        ["--project", str(tmp_path), "patch", "approve", proposal_id],
        input="wrong-proposal\n",
    )
    approved = runner.invoke(
        app,
        ["--project", str(tmp_path), "patch", "approve", proposal_id],
        input=f"{proposal_id}\n",
    )

    assert declined.exit_code == 1
    assert "CLI_PATCH_CONFIRMATION_DECLINED" in declined.stderr
    assert approved.exit_code == 0, (
        approved.stdout,
        approved.stderr,
        approved.exception,
    )
    record = LocalPatchProposalStorage(
        ProjectRoot(tmp_path.resolve(), ProjectRootSource.EXPLICIT)
    ).load_record(proposal_id)
    assert record is not None
    lifecycle = record["lifecycle"]
    assert isinstance(lifecycle, dict)
    assert lifecycle["state"] == "approved"
    approvals = tuple((tmp_path / ".contextforge" / "approvals").glob("*.json"))
    assert len(approvals) == 1


def test_patch_reject_persists_reason_without_applying_files(tmp_path: Path) -> None:
    proposal_id = _persist_proposal(tmp_path)

    result = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "patch",
            "reject",
            proposal_id,
            "--reason",
            "Needs a smaller change.",
        ],
        input="y\n",
    )

    assert result.exit_code == 0
    record = LocalPatchProposalStorage(
        ProjectRoot(tmp_path.resolve(), ProjectRootSource.EXPLICIT)
    ).load_record(proposal_id)
    assert record is not None
    lifecycle = record["lifecycle"]
    rejection = record["rejection"]
    assert isinstance(lifecycle, dict)
    assert isinstance(rejection, dict)
    assert lifecycle["state"] == "rejected"
    assert rejection["reason"] == "Needs a smaller change."


def test_patch_approval_refuses_non_interactive_mode(tmp_path: Path) -> None:
    proposal_id = _persist_proposal(tmp_path)

    result = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--non-interactive",
            "patch",
            "approve",
            proposal_id,
        ],
    )

    assert result.exit_code == 1
    assert "CLI_PATCH_APPROVAL_BINDING_REQUIRED" in result.stderr


def test_non_interactive_approval_requires_exact_bound_identifier(
    tmp_path: Path,
) -> None:
    proposal_id = _persist_proposal(tmp_path)

    mismatch = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--non-interactive",
            "patch",
            "approve",
            proposal_id,
            "--approve",
            "patch_proposal_mismatch",
        ],
    )
    approved = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--non-interactive",
            "--format",
            "json",
            "patch",
            "approve",
            proposal_id,
            "--approve",
            proposal_id,
        ],
    )

    assert mismatch.exit_code == 1
    assert "CLI_PATCH_APPROVAL_BINDING_MISMATCH" in mismatch.stderr
    assert approved.exit_code == 0
    payload = _payload(approved)
    assert payload["method"] == "non_interactive"
    assert payload["proposal_id"] == proposal_id

    approvals = tuple((tmp_path / ".contextforge" / "approvals").glob("*.json"))
    assert len(approvals) == 1
    approval = json.loads(approvals[0].read_text(encoding="utf-8"))
    assert approval["method"] == "non_interactive"
    assert approval["proposal_id"] == proposal_id


def test_approval_binding_cannot_bypass_interactive_confirmation(
    tmp_path: Path,
) -> None:
    proposal_id = _persist_proposal(tmp_path)

    result = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "patch",
            "approve",
            proposal_id,
            "--approve",
            proposal_id,
        ],
    )

    assert result.exit_code == 1
    assert "CLI_PATCH_APPROVAL_MODE_INVALID" in result.stderr


def test_patch_apply_uses_approved_staged_application_and_persists_result(
    tmp_path: Path,
) -> None:
    proposal_id = _persist_applicable_proposal(tmp_path)
    _approve_non_interactively(tmp_path, proposal_id)

    result = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--format",
            "json",
            "patch",
            "apply",
            proposal_id,
        ],
    )

    assert result.exit_code == 0, (result.stdout, result.stderr, result.exception)
    assert (tmp_path / "created-1.txt").read_text(encoding="utf-8") == "created 1\n"
    payload = _payload(result)
    assert payload["status"] == "applied"
    assert payload["lifecycle_state"] == "applied"
    application = json.loads(
        (tmp_path / ".contextforge" / "applications" / f"{proposal_id}.json").read_text(
            encoding="utf-8"
        )
    )
    assert application["status"] == "applied"
    assert application["applied_change_ids"] == ["change-1"]


def test_patch_apply_requires_active_approval(tmp_path: Path) -> None:
    proposal_id = _persist_applicable_proposal(tmp_path)

    result = runner.invoke(
        app,
        ["--project", str(tmp_path), "patch", "apply", proposal_id],
    )

    assert result.exit_code == 11
    assert "CLI_PATCH_APPROVAL_REQUIRED" in result.stderr
    assert not (tmp_path / "created-1.txt").exists()


def test_patch_apply_rejects_stale_project_state(tmp_path: Path) -> None:
    proposal_id = _persist_applicable_proposal(tmp_path)
    _approve_non_interactively(tmp_path, proposal_id)
    (tmp_path / "unexpected.txt").write_text("changed\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["--project", str(tmp_path), "patch", "apply", proposal_id],
    )

    assert result.exit_code == 14
    assert "CLI_PATCH_STALE" in result.stderr
    assert not (tmp_path / "created-1.txt").exists()


def test_patch_apply_reports_partial_application_with_recovery_reference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal_id = _persist_applicable_proposal(tmp_path, change_count=2)
    _approve_non_interactively(tmp_path, proposal_id)
    original_apply = patch_adapter._apply_change

    def fail_second_change(
        root: Path,
        change: ProposedChange,
        staged_files: dict[str, Path],
    ) -> None:
        if change.change_id == "change-2":
            raise OSError("injected application failure")
        original_apply(root, change, staged_files)

    monkeypatch.setattr(patch_adapter, "_apply_change", fail_second_change)
    monkeypatch.setattr(patch_adapter, "_rollback_and_verify", lambda *_args: False)

    result = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--format",
            "json",
            "patch",
            "apply",
            proposal_id,
        ],
    )

    assert result.exit_code == 17
    payload = _payload(result)
    assert payload["status"] == "partially_applied"
    assert payload["applied_change_ids"] == ["change-1"]
    assert payload["unapplied_change_ids"] == ["change-2"]
    assert payload["recovery_reference"] is not None
