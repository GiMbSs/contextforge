"""Staged local filesystem implementation of the Patch Application port."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, replace
from pathlib import Path

from contextforge.application import (
    ApplicationPreflightEvidence,
    ApplicationPreviewChange,
    PatchApplicationPreflight,
    PatchApplicationPreview,
    PatchApplicationResult,
    PatchApplicationStatus,
)
from contextforge.diagnostics import DiagnosticCode, DiagnosticSeverity
from contextforge.domain import ArtifactPath, ProposalFingerprint
from contextforge.patch import (
    ApprovalRecord,
    PatchDiagnostic,
    PatchOperation,
    PatchProposal,
    ProposedChange,
)
from contextforge.project import ProjectRoot

type PreflightEvidenceProvider = Callable[[], ApplicationPreflightEvidence]


@dataclass(frozen=True, slots=True)
class LocalStagedPatchApplication:
    """Stage final content, lock, revalidate, then mutate through atomic replaces."""

    project_root: ProjectRoot
    evidence_provider: PreflightEvidenceProvider

    def __post_init__(self) -> None:
        if not isinstance(self.project_root, ProjectRoot):
            raise TypeError("project_root must be a ProjectRoot")
        if not callable(self.evidence_provider):
            raise TypeError("evidence_provider must be callable")

    def preview_application(
        self,
        proposal: PatchProposal,
        proposal_fingerprint: ProposalFingerprint,
    ) -> PatchApplicationPreview:
        """Describe the exact operations without reading or writing project files."""
        if not isinstance(proposal, PatchProposal):
            raise TypeError("proposal must be a PatchProposal")
        if not isinstance(proposal_fingerprint, ProposalFingerprint):
            raise TypeError("proposal_fingerprint must be a ProposalFingerprint")
        return PatchApplicationPreview(
            proposal.proposal_id,
            tuple(
                ApplicationPreviewChange(
                    change.path,
                    change.operation,
                    change.destination_path,
                )
                for change in proposal.changes
            ),
        )

    def apply_proposal(
        self,
        proposal: PatchProposal,
        proposal_fingerprint: ProposalFingerprint,
        approval: ApprovalRecord,
    ) -> PatchApplicationResult:
        """Apply staged final content after two successful preflight validations."""
        preflight = PatchApplicationPreflight()
        initial = preflight.validate(
            proposal,
            proposal_fingerprint,
            approval,
            self.evidence_provider(),
        )
        if not initial.ready:
            return PatchApplicationResult(
                proposal.proposal_id,
                PatchApplicationStatus.FAILED,
                initial.diagnostics,
            )

        root = self.project_root.path.resolve(strict=True)
        stage = Path(
            tempfile.mkdtemp(
                prefix=".contextforge-stage-",
                dir=root.parent,
            )
        )
        lock_path = root / ".contextforge" / "mutation.lock"
        lock_descriptor: int | None = None
        applied = 0
        try:
            staged_files = _stage_final_files(stage, proposal)
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                lock_descriptor = os.open(
                    lock_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
            except FileExistsError:
                return _failure(
                    proposal,
                    "PATCH_APPLICATION_LOCK_UNAVAILABLE",
                    "Project mutation lock could not be acquired.",
                )

            current = replace(self.evidence_provider(), lock_available=True)
            final_preflight = preflight.validate(
                proposal,
                proposal_fingerprint,
                approval,
                current,
            )
            if not final_preflight.ready:
                return PatchApplicationResult(
                    proposal.proposal_id,
                    PatchApplicationStatus.FAILED,
                    final_preflight.diagnostics,
                )

            for change in proposal.changes:
                _apply_change(root, change, staged_files)
                applied += 1
        except OSError:
            status = (
                PatchApplicationStatus.PARTIALLY_APPLIED
                if applied
                else PatchApplicationStatus.FAILED
            )
            return PatchApplicationResult(
                proposal.proposal_id,
                status,
                (
                    _diagnostic(
                        "PATCH_APPLICATION_FILESYSTEM_FAILURE",
                        "Filesystem application failed before all changes completed.",
                    ),
                ),
            )
        finally:
            if lock_descriptor is not None:
                os.close(lock_descriptor)
                with suppress(FileNotFoundError):
                    lock_path.unlink()
            shutil.rmtree(stage, ignore_errors=True)

        return PatchApplicationResult(
            proposal.proposal_id,
            PatchApplicationStatus.APPLIED,
        )


def _stage_final_files(
    stage: Path,
    proposal: PatchProposal,
) -> dict[str, Path]:
    staged: dict[str, Path] = {}
    for change in proposal.changes:
        if change.operation not in (PatchOperation.CREATE, PatchOperation.MODIFY):
            continue
        assert change.patch_payload is not None
        staged_path = stage.joinpath(*change.path.parts)
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        staged_path.write_text(change.patch_payload, encoding="utf-8", newline="")
        staged[change.change_id] = staged_path
    return staged


def _apply_change(
    root: Path,
    change: ProposedChange,
    staged_files: dict[str, Path],
) -> None:
    source = _safe_target(root, change.path)
    if change.operation in (PatchOperation.CREATE, PatchOperation.MODIFY):
        source.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staged_files[change.change_id], source)
    elif change.operation is PatchOperation.DELETE:
        source.unlink()
    else:
        assert change.destination_path is not None
        destination = _safe_target(root, change.destination_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, destination)


def _safe_target(root: Path, path: ArtifactPath) -> Path:
    target = root.joinpath(*path.parts)
    ancestor = target
    while not ancestor.exists():
        if ancestor == root:
            break
        ancestor = ancestor.parent
    resolved_ancestor = ancestor.resolve(strict=True)
    try:
        resolved_ancestor.relative_to(root)
    except ValueError as error:
        raise OSError("patch path resolved outside project root") from error
    return target


def _failure(
    proposal: PatchProposal,
    code: str,
    message: str,
) -> PatchApplicationResult:
    return PatchApplicationResult(
        proposal.proposal_id,
        PatchApplicationStatus.FAILED,
        (_diagnostic(code, message),),
    )


def _diagnostic(code: str, message: str) -> PatchDiagnostic:
    return PatchDiagnostic(
        DiagnosticCode(code),
        DiagnosticSeverity.ERROR,
        message,
    )
