"""Immutable domain models for reviewable patch proposals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from contextforge.diagnostics import DiagnosticCode, DiagnosticSeverity
from contextforge.domain import (
    ArtifactPath,
    InferenceRequestId,
    InferenceResponseId,
    PatchProposalId,
    ProjectFingerprint,
    TaskId,
)


class PatchOperation(StrEnum):
    """Canonical operation proposed for one project artifact."""

    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"
    RENAME = "rename"


class PatchValidationState(StrEnum):
    """Aggregate validation outcome for a patch proposal."""

    VALID = "valid"
    INVALID = "invalid"
    VALID_WITH_WARNINGS = "valid_with_warnings"


class PatchApprovalState(StrEnum):
    """Explicit review state; proposals always begin pending."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class PatchDiagnostic:
    """One normalized patch validation observation."""

    code: DiagnosticCode
    severity: DiagnosticSeverity
    message: str
    change_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, DiagnosticCode):
            raise TypeError("code must be a DiagnosticCode")
        if not isinstance(self.severity, DiagnosticSeverity):
            raise TypeError("severity must be a DiagnosticSeverity")
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError("message must not be empty")
        if self.change_id is not None and not self.change_id.strip():
            raise ValueError("change_id must not be empty")


@dataclass(frozen=True, slots=True)
class ProposedChange:
    """One immutable requested modification to a project artifact."""

    change_id: str
    path: ArtifactPath
    operation: PatchOperation
    explanation: str
    patch_payload: str | None = None
    destination_path: ArtifactPath | None = None
    assumptions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.change_id, str) or not self.change_id.strip():
            raise ValueError("change_id must not be empty")
        if not isinstance(self.path, ArtifactPath):
            raise TypeError("path must be an ArtifactPath")
        if not isinstance(self.operation, PatchOperation):
            raise TypeError("operation must be a PatchOperation")
        if not isinstance(self.explanation, str) or not self.explanation.strip():
            raise ValueError("explanation must not be empty")
        if self.operation in (PatchOperation.CREATE, PatchOperation.MODIFY):
            if not self.patch_payload:
                raise ValueError("create and modify operations require patch_payload")
        elif self.patch_payload is not None:
            raise ValueError("delete and rename operations must not include patch_payload")
        if self.operation is PatchOperation.RENAME:
            if self.destination_path is None:
                raise ValueError("rename operations require destination_path")
            if self.destination_path == self.path:
                raise ValueError("rename destination must differ from source")
        elif self.destination_path is not None:
            raise ValueError("destination_path is only valid for rename operations")
        assumptions = tuple(self.assumptions)
        if any(not item.strip() for item in assumptions):
            raise ValueError("assumptions must contain non-empty values")
        object.__setattr__(self, "assumptions", assumptions)


@dataclass(frozen=True, slots=True)
class PatchValidationSummary:
    """Deterministic aggregate of patch diagnostics."""

    state: PatchValidationState
    validated_at: datetime
    diagnostics: tuple[PatchDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.state, PatchValidationState):
            raise TypeError("state must be a PatchValidationState")
        if self.validated_at.tzinfo is None or self.validated_at.utcoffset() is None:
            raise ValueError("validated_at must be timezone-aware")
        diagnostics = tuple(self.diagnostics)
        if any(not isinstance(item, PatchDiagnostic) for item in diagnostics):
            raise TypeError("diagnostics must contain PatchDiagnostic values")
        has_errors = any(item.severity is DiagnosticSeverity.ERROR for item in diagnostics)
        if has_errors != (self.state is PatchValidationState.INVALID):
            raise ValueError("invalid state must exactly reflect error diagnostics")
        object.__setattr__(self, "diagnostics", diagnostics)


@dataclass(frozen=True, slots=True)
class PatchProposal:
    """Traceable immutable collection of validated proposed changes."""

    proposal_id: PatchProposalId
    task_id: TaskId
    request_id: InferenceRequestId
    response_id: InferenceResponseId
    project_fingerprint: ProjectFingerprint
    changes: tuple[ProposedChange, ...]
    validation: PatchValidationSummary
    created_at: datetime
    summary: str | None = None
    approval_state: PatchApprovalState = PatchApprovalState.PENDING

    def __post_init__(self) -> None:
        expected_types = (
            (self.proposal_id, PatchProposalId, "proposal_id"),
            (self.task_id, TaskId, "task_id"),
            (self.request_id, InferenceRequestId, "request_id"),
            (self.response_id, InferenceResponseId, "response_id"),
            (self.project_fingerprint, ProjectFingerprint, "project_fingerprint"),
            (self.validation, PatchValidationSummary, "validation"),
        )
        for value, expected, field_name in expected_types:
            if not isinstance(value, expected):
                raise TypeError(f"{field_name} must be {expected.__name__}")
        changes = tuple(self.changes)
        if not changes:
            raise ValueError("changes must not be empty")
        if any(not isinstance(item, ProposedChange) for item in changes):
            raise TypeError("changes must contain ProposedChange values")
        change_ids = tuple(item.change_id for item in changes)
        if len(set(change_ids)) != len(change_ids):
            raise ValueError("change identifiers must be unique")
        paths = tuple(item.path for item in changes)
        if len(set(paths)) != len(paths):
            raise ValueError("target paths must be unique")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        if self.summary is not None and not self.summary.strip():
            raise ValueError("summary must not be empty")
        if not isinstance(self.approval_state, PatchApprovalState):
            raise TypeError("approval_state must be a PatchApprovalState")
        if self.approval_state is not PatchApprovalState.PENDING:
            raise ValueError("new patch proposals must begin pending")
        object.__setattr__(self, "changes", changes)
