"""CLI tests for persisted patch proposal review."""

import json
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

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
    summary = json.loads(listing.stdout)["proposals"][0]
    assert summary["proposal_id"] == proposal_id
    assert summary["change_count"] == 2
    assert summary["lifecycle_state"] == "awaiting_approval"
    assert json.loads(shown.stdout)["proposal"]["proposal_id"] == proposal_id


def test_patch_review_prioritizes_operations_files_warnings_and_state(
    tmp_path: Path,
) -> None:
    proposal_id = _persist_proposal(tmp_path)

    result = runner.invoke(
        app,
        ["--project", str(tmp_path), "--format", "json", "patch", "review"],
    )

    assert result.exit_code == 0
    review = json.loads(result.stdout)["review"]
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
    assert json.loads(result.stdout)["destination"] == str(destination)


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
    assert json.loads(result.stdout) == {"status": "failed"}
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
    payload = json.loads(approved.stdout)
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
