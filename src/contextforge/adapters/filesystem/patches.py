"""Staged local filesystem implementation of the Patch Application port."""

from __future__ import annotations

import json
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
                unapplied_change_ids=tuple(change.change_id for change in proposal.changes),
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
        applied_changes: list[ProposedChange] = []
        original_states: dict[ArtifactPath, bytes | None] = {}
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
                    unapplied_change_ids=tuple(change.change_id for change in proposal.changes),
                )

            original_states = _capture_original_states(root, proposal)
            for change in proposal.changes:
                _apply_change(root, change, staged_files)
                applied_changes.append(change)
        except OSError:
            applied_ids = tuple(change.change_id for change in applied_changes)
            unapplied_ids = tuple(
                change.change_id
                for change in proposal.changes
                if change.change_id not in set(applied_ids)
            )
            rollback_verified = _rollback_and_verify(
                root,
                applied_changes,
                original_states,
            )
            recovery_reference: str | None = None
            if rollback_verified:
                status = PatchApplicationStatus.FAILED
                applied_ids = ()
                unapplied_ids = tuple(change.change_id for change in proposal.changes)
            else:
                status = (
                    PatchApplicationStatus.PARTIALLY_APPLIED
                    if applied_ids and unapplied_ids
                    else PatchApplicationStatus.FAILED
                )
                recovery_reference = _preserve_recovery_information(
                    root,
                    proposal,
                    original_states,
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
                applied_change_ids=applied_ids,
                unapplied_change_ids=unapplied_ids,
                rollback_verified=rollback_verified,
                recovery_reference=recovery_reference,
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
            applied_change_ids=tuple(change.change_id for change in proposal.changes),
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


def _capture_original_states(
    root: Path,
    proposal: PatchProposal,
) -> dict[ArtifactPath, bytes | None]:
    paths = {
        path
        for change in proposal.changes
        for path in (change.path, change.destination_path)
        if path is not None
    }
    states: dict[ArtifactPath, bytes | None] = {}
    for path in paths:
        target = _safe_target(root, path)
        states[path] = target.read_bytes() if target.exists() else None
    return states


def _rollback_and_verify(
    root: Path,
    applied_changes: list[ProposedChange],
    original_states: dict[ArtifactPath, bytes | None],
) -> bool:
    try:
        affected = {
            path
            for change in applied_changes
            for path in (change.path, change.destination_path)
            if path is not None
        }
        for path in sorted(affected, reverse=True):
            target = _safe_target(root, path)
            original = original_states[path]
            if original is None:
                with suppress(FileNotFoundError):
                    target.unlink()
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(f".{target.name}.contextforge-rollback")
                temporary.write_bytes(original)
                os.replace(temporary, target)
        return all(
            (
                not _safe_target(root, path).exists()
                if content is None
                else _safe_target(root, path).read_bytes() == content
            )
            for path, content in original_states.items()
            if path in affected
        )
    except OSError:
        return False


def _preserve_recovery_information(
    root: Path,
    proposal: PatchProposal,
    original_states: dict[ArtifactPath, bytes | None],
) -> str:
    recovery = root / ".contextforge" / "recovery" / str(proposal.proposal_id)
    recovery.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}
    for path, content in sorted(original_states.items()):
        if content is None:
            manifest[str(path)] = "originally_absent"
            continue
        backup = recovery / "original" / Path(*path.parts)
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(content)
        manifest[str(path)] = str(backup.relative_to(recovery))
    (recovery / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return str(recovery.relative_to(root))


def _failure(
    proposal: PatchProposal,
    code: str,
    message: str,
) -> PatchApplicationResult:
    return PatchApplicationResult(
        proposal.proposal_id,
        PatchApplicationStatus.FAILED,
        (_diagnostic(code, message),),
        unapplied_change_ids=tuple(change.change_id for change in proposal.changes),
    )


def _diagnostic(code: str, message: str) -> PatchDiagnostic:
    return PatchDiagnostic(
        DiagnosticCode(code),
        DiagnosticSeverity.ERROR,
        message,
    )
