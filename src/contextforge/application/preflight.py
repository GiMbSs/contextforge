"""Immediate, mutation-free patch application preflight."""

from __future__ import annotations

from dataclasses import dataclass, field

from contextforge.diagnostics import DiagnosticCode, DiagnosticSeverity
from contextforge.domain import ArtifactPath, ProjectFingerprint, ProposalFingerprint
from contextforge.patch import (
    ApprovalBindingError,
    ApprovalRecord,
    PatchDiagnostic,
    PatchOperationValidationError,
    PatchOperationValidator,
    PatchPathValidationError,
    PatchPathValidator,
    PatchProposal,
    PatchSourceState,
    ProtectedPathPolicy,
    fingerprint_patch_proposal,
)


@dataclass(frozen=True, slots=True)
class ApplicationPreflightEvidence:
    """Trusted current-state evidence collected immediately before mutation."""

    project_fingerprint: ProjectFingerprint
    source_state: PatchSourceState
    writable_paths: tuple[ArtifactPath, ...]
    lock_available: bool

    def __post_init__(self) -> None:
        if not isinstance(self.project_fingerprint, ProjectFingerprint):
            raise TypeError("project_fingerprint must be a ProjectFingerprint")
        if not isinstance(self.source_state, PatchSourceState):
            raise TypeError("source_state must be a PatchSourceState")
        paths = tuple(self.writable_paths)
        if any(not isinstance(path, ArtifactPath) for path in paths):
            raise TypeError("writable_paths must contain ArtifactPath values")
        if len(set(paths)) != len(paths):
            raise ValueError("writable_paths must not contain duplicates")
        if type(self.lock_available) is not bool:
            raise TypeError("lock_available must be a boolean")
        object.__setattr__(self, "writable_paths", tuple(sorted(paths)))


@dataclass(frozen=True, slots=True)
class ApplicationPreflightResult:
    """Deterministic readiness outcome with all discovered diagnostics."""

    diagnostics: tuple[PatchDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        diagnostics = tuple(self.diagnostics)
        if any(not isinstance(item, PatchDiagnostic) for item in diagnostics):
            raise TypeError("diagnostics must contain PatchDiagnostic values")
        object.__setattr__(self, "diagnostics", diagnostics)

    @property
    def ready(self) -> bool:
        """Whether mutation may proceed."""
        return not self.diagnostics


@dataclass(frozen=True, slots=True)
class PatchApplicationPreflight:
    """Revalidate every mutable precondition immediately before application."""

    path_policy: ProtectedPathPolicy = field(default_factory=ProtectedPathPolicy)

    def __post_init__(self) -> None:
        if not isinstance(self.path_policy, ProtectedPathPolicy):
            raise TypeError("path_policy must be a ProtectedPathPolicy")

    def validate(
        self,
        proposal: PatchProposal,
        proposal_fingerprint: ProposalFingerprint,
        approval: ApprovalRecord,
        evidence: ApplicationPreflightEvidence,
    ) -> ApplicationPreflightResult:
        """Return all preflight failures without mutating project state."""
        if not isinstance(proposal, PatchProposal):
            raise TypeError("proposal must be a PatchProposal")
        if not isinstance(proposal_fingerprint, ProposalFingerprint):
            raise TypeError("proposal_fingerprint must be a ProposalFingerprint")
        if not isinstance(approval, ApprovalRecord):
            raise TypeError("approval must be an ApprovalRecord")
        if not isinstance(evidence, ApplicationPreflightEvidence):
            raise TypeError("evidence must be ApplicationPreflightEvidence")

        diagnostics: list[PatchDiagnostic] = []
        actual_proposal_fingerprint = fingerprint_patch_proposal(proposal)
        if proposal_fingerprint != actual_proposal_fingerprint:
            diagnostics.append(
                _diagnostic(
                    "PATCH_PREFLIGHT_PROPOSAL_FINGERPRINT_MISMATCH",
                    "Proposal fingerprint does not match immutable proposal content.",
                )
            )
        if proposal.project_fingerprint != evidence.project_fingerprint:
            diagnostics.append(
                _diagnostic(
                    "PATCH_PREFLIGHT_PROJECT_FINGERPRINT_MISMATCH",
                    "Project state changed after proposal validation.",
                )
            )
        try:
            approval.validate_binding(
                proposal_id=proposal.proposal_id,
                proposal_fingerprint=actual_proposal_fingerprint,
                project_fingerprint=evidence.project_fingerprint,
            )
        except ApprovalBindingError as error:
            diagnostics.append(_diagnostic("PATCH_PREFLIGHT_APPROVAL_MISMATCH", str(error)))

        path_validator = PatchPathValidator(self.path_policy)
        operation_validator = PatchOperationValidator()
        writable = set(evidence.writable_paths)
        for change in proposal.changes:
            try:
                path_validator.validate(
                    str(change.path),
                    change.operation,
                    (str(change.destination_path) if change.destination_path is not None else None),
                )
            except PatchPathValidationError as error:
                diagnostics.extend(_bind(error.diagnostics, change.change_id))
            try:
                operation_validator.validate(change, evidence.source_state)
            except PatchOperationValidationError as error:
                diagnostics.extend(error.diagnostics)
            required_paths = {change.path}
            if change.destination_path is not None:
                required_paths.add(change.destination_path)
            if not required_paths <= writable:
                diagnostics.append(
                    _diagnostic(
                        "PATCH_PREFLIGHT_PERMISSION_DENIED",
                        "Required project path is not writable.",
                        change.change_id,
                    )
                )
        if not evidence.lock_available:
            diagnostics.append(
                _diagnostic(
                    "PATCH_PREFLIGHT_LOCK_UNAVAILABLE",
                    "Project mutation lock is unavailable.",
                )
            )
        return ApplicationPreflightResult(tuple(diagnostics))


def _diagnostic(
    code: str,
    message: str,
    change_id: str | None = None,
) -> PatchDiagnostic:
    return PatchDiagnostic(
        DiagnosticCode(code),
        DiagnosticSeverity.ERROR,
        message,
        change_id,
    )


def _bind(
    diagnostics: tuple[PatchDiagnostic, ...],
    change_id: str,
) -> tuple[PatchDiagnostic, ...]:
    return tuple(
        PatchDiagnostic(item.code, item.severity, item.message, change_id) for item in diagnostics
    )
