"""Local persistence for reviewable patch proposals."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from contextforge.application import PatchApplicationResult
from contextforge.diagnostics import DiagnosticCode, DiagnosticSeverity
from contextforge.domain import (
    ApprovalId,
    ArtifactPath,
    ContentFingerprint,
    InferenceRequestId,
    InferenceResponseId,
    PatchProposalId,
    ProjectFingerprint,
    ProposalFingerprint,
    TaskId,
)
from contextforge.patch import (
    ApprovalMethod,
    ApprovalRecord,
    PatchApprovalState,
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
from contextforge.project import ProjectRoot


@dataclass(frozen=True, slots=True)
class LocalPatchProposalStorage:
    """Persist application-produced proposals and lifecycles atomically."""

    root: ProjectRoot

    def save(
        self,
        proposal: PatchProposal,
        lifecycle: PatchProposalLifecycle,
    ) -> None:
        """Save one exact proposal and its bound lifecycle."""
        if proposal.proposal_id != lifecycle.proposal_id:
            raise ValueError("proposal and lifecycle identifiers must match")
        if fingerprint_patch_proposal(proposal) != lifecycle.proposal_fingerprint:
            raise ValueError("lifecycle must be bound to the exact proposal")
        directory = self._directory
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / f"{proposal.proposal_id}.json"
        temporary = directory / f"{proposal.proposal_id}.json.tmp"
        temporary.write_text(
            json.dumps(
                _proposal_record(proposal, lifecycle),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(destination)

    def list_records(self) -> tuple[dict[str, object], ...]:
        """Load valid persisted records in deterministic newest-first order."""
        records = tuple(
            record
            for source in sorted(self._directory.glob("*.json"))
            if (record := _read_record(source)) is not None
        )
        return tuple(
            sorted(
                records,
                key=lambda item: (
                    str(item.get("created_at", "")),
                    str(item.get("proposal_id", "")),
                ),
                reverse=True,
            )
        )

    def load_record(self, proposal_id: str | None = None) -> dict[str, object] | None:
        """Load an exact proposal, or the latest proposal when omitted."""
        if proposal_id is None:
            records = self.list_records()
            return records[0] if records else None
        if "/" in proposal_id or "\\" in proposal_id:
            return None
        return _read_record(self._directory / f"{proposal_id}.json")

    def load_proposal(self, proposal_id: PatchProposalId) -> PatchProposal | None:
        """Rehydrate one persisted immutable proposal."""
        record = self.load_record(str(proposal_id))
        return _load_proposal(record) if record is not None else None

    def load_lifecycle(
        self,
        proposal_id: PatchProposalId,
    ) -> PatchProposalLifecycle | None:
        """Rehydrate the current lifecycle bound to a proposal."""
        record = self.load_record(str(proposal_id))
        return _load_lifecycle(record) if record is not None else None

    def save_lifecycle(self, lifecycle: PatchProposalLifecycle) -> None:
        """Atomically update the lifecycle of an existing proposal."""
        record = self.load_record(str(lifecycle.proposal_id))
        if record is None:
            raise ValueError("proposal is unavailable")
        record["lifecycle"] = {
            "proposal_fingerprint": str(lifecycle.proposal_fingerprint),
            "state": lifecycle.state.value,
            "transitioned_at": lifecycle.transitioned_at.isoformat(),
        }
        self._write_record(lifecycle.proposal_id, record)

    def save_approval(self, approval: ApprovalRecord) -> None:
        """Persist explicit approval evidence atomically."""
        directory = self.root.path / ".contextforge" / "approvals"
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / f"{approval.approval_id}.json"
        temporary = directory / f"{approval.approval_id}.json.tmp"
        payload = {
            "acknowledged_warnings": list(approval.acknowledged_warnings),
            "approval_id": str(approval.approval_id),
            "approved_at": approval.approved_at.isoformat(),
            "approving_principal": approval.approving_principal,
            "method": approval.method.value,
            "project_fingerprint": str(approval.project_fingerprint),
            "proposal_fingerprint": str(approval.proposal_fingerprint),
            "proposal_id": str(approval.proposal_id),
        }
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(destination)

    def load_approval(self, approval_id: ApprovalId) -> ApprovalRecord | None:
        """Load exact persisted approval evidence."""
        source = self.root.path / ".contextforge" / "approvals" / f"{approval_id}.json"
        record = _read_json_object(source)
        if record is None:
            return None
        try:
            raw_warnings = record.get("acknowledged_warnings", [])
            if not isinstance(raw_warnings, list):
                return None
            return ApprovalRecord(
                ApprovalId(str(record["approval_id"])),
                PatchProposalId(str(record["proposal_id"])),
                ProposalFingerprint(str(record["proposal_fingerprint"])),
                ProjectFingerprint(str(record["project_fingerprint"])),
                datetime.fromisoformat(str(record["approved_at"])),
                ApprovalMethod(str(record["method"])),
                (
                    str(record["approving_principal"])
                    if record.get("approving_principal") is not None
                    else None
                ),
                tuple(str(item) for item in raw_warnings),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def save_rejection(
        self,
        proposal_id: PatchProposalId,
        reason: str,
        rejected_at: datetime,
    ) -> None:
        """Persist explicit rejection evidence with the proposal."""
        record = self.load_record(str(proposal_id))
        if record is None:
            raise ValueError("proposal is unavailable")
        record["rejection"] = {
            "reason": reason,
            "rejected_at": rejected_at.isoformat(),
        }
        self._write_record(proposal_id, record)

    def save_application_result(self, result: PatchApplicationResult) -> None:
        """Reserve the workflow port; application persistence arrives in I088."""
        del result
        raise NotImplementedError("patch application is not implemented")

    def _write_record(
        self,
        proposal_id: PatchProposalId,
        record: dict[str, object],
    ) -> None:
        destination = self._directory / f"{proposal_id}.json"
        temporary = self._directory / f"{proposal_id}.json.tmp"
        temporary.write_text(
            json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(destination)

    @property
    def _directory(self) -> Path:
        return self.root.path / ".contextforge" / "proposals"


def _proposal_record(
    proposal: PatchProposal,
    lifecycle: PatchProposalLifecycle,
) -> dict[str, object]:
    return {
        "approval_state": proposal.approval_state.value,
        "changes": [
            {
                "assumptions": list(change.assumptions),
                "change_id": change.change_id,
                "destination_path": (
                    str(change.destination_path) if change.destination_path is not None else None
                ),
                "expected_old_fingerprint": (
                    str(change.expected_old_fingerprint)
                    if change.expected_old_fingerprint is not None
                    else None
                ),
                "explanation": change.explanation,
                "operation": change.operation.value,
                "patch_payload": change.patch_payload,
                "path": str(change.path),
            }
            for change in proposal.changes
        ],
        "created_at": proposal.created_at.isoformat(),
        "lifecycle": {
            "proposal_fingerprint": str(lifecycle.proposal_fingerprint),
            "state": lifecycle.state.value,
            "transitioned_at": lifecycle.transitioned_at.isoformat(),
        },
        "project_fingerprint": str(proposal.project_fingerprint),
        "proposal_id": str(proposal.proposal_id),
        "request_id": str(proposal.request_id),
        "response_id": str(proposal.response_id),
        "summary": proposal.summary,
        "task_id": str(proposal.task_id),
        "validation": {
            "diagnostics": [
                {
                    "change_id": diagnostic.change_id,
                    "code": str(diagnostic.code),
                    "message": diagnostic.message,
                    "severity": diagnostic.severity.value,
                }
                for diagnostic in proposal.validation.diagnostics
            ],
            "state": proposal.validation.state.value,
            "validated_at": proposal.validation.validated_at.isoformat(),
        },
    }


def _read_record(source: Path) -> dict[str, object] | None:
    loaded = _read_json_object(source)
    if loaded is None:
        return None
    required = {
        "changes",
        "created_at",
        "lifecycle",
        "project_fingerprint",
        "proposal_id",
        "validation",
    }
    return loaded if required <= loaded.keys() else None


def _read_json_object(source: Path) -> dict[str, object] | None:
    try:
        loaded = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(loaded, dict):
        return None
    return loaded


def _load_proposal(record: dict[str, object]) -> PatchProposal | None:
    try:
        raw_validation = record["validation"]
        raw_changes = record["changes"]
        if not isinstance(raw_validation, dict) or not isinstance(raw_changes, list):
            return None
        raw_diagnostics = raw_validation.get("diagnostics", [])
        if not isinstance(raw_diagnostics, list):
            return None
        diagnostics = tuple(
            PatchDiagnostic(
                DiagnosticCode(str(item["code"])),
                DiagnosticSeverity(str(item["severity"])),
                str(item["message"]),
                str(item["change_id"]) if item.get("change_id") is not None else None,
            )
            for item in raw_diagnostics
            if isinstance(item, dict)
        )
        changes = tuple(_load_change(item) for item in raw_changes if isinstance(item, dict))
        return PatchProposal(
            PatchProposalId(str(record["proposal_id"])),
            TaskId(str(record["task_id"])),
            InferenceRequestId(str(record["request_id"])),
            InferenceResponseId(str(record["response_id"])),
            ProjectFingerprint(str(record["project_fingerprint"])),
            changes,
            PatchValidationSummary(
                PatchValidationState(str(raw_validation["state"])),
                datetime.fromisoformat(str(raw_validation["validated_at"])),
                diagnostics,
            ),
            datetime.fromisoformat(str(record["created_at"])),
            str(record["summary"]) if record.get("summary") is not None else None,
            PatchApprovalState.PENDING,
        )
    except (KeyError, TypeError, ValueError):
        return None


def _load_change(record: dict[str, object]) -> ProposedChange:
    expected = record.get("expected_old_fingerprint")
    destination = record.get("destination_path")
    assumptions = record.get("assumptions", ())
    if not isinstance(assumptions, list):
        raise TypeError("persisted assumptions are invalid")
    return ProposedChange(
        str(record["change_id"]),
        ArtifactPath(str(record["path"])),
        PatchOperation(str(record["operation"])),
        str(record["explanation"]),
        str(record["patch_payload"]) if record.get("patch_payload") is not None else None,
        ArtifactPath(str(destination)) if destination is not None else None,
        tuple(str(item) for item in assumptions),
        ContentFingerprint(str(expected)) if expected is not None else None,
    )


def _load_lifecycle(record: dict[str, object]) -> PatchProposalLifecycle | None:
    raw = record.get("lifecycle")
    if not isinstance(raw, dict):
        return None
    try:
        return PatchProposalLifecycle(
            PatchProposalId(str(record["proposal_id"])),
            ProposalFingerprint(str(raw["proposal_fingerprint"])),
            ProposalLifecycleState(str(raw["state"])),
            datetime.fromisoformat(str(raw["transitioned_at"])),
        )
    except (KeyError, TypeError, ValueError):
        return None
