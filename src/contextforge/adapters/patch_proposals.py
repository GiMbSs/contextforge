"""Local persistence for reviewable patch proposals."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from contextforge.patch import (
    PatchProposal,
    PatchProposalLifecycle,
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
    try:
        loaded = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(loaded, dict):
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
