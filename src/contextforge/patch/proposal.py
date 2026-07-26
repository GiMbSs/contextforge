"""Materialization of fully validated immutable patch proposals."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

from contextforge.domain import (
    FingerprintOrdering,
    InferenceRequestId,
    InferenceResponseId,
    PatchProposalId,
    ProposalFingerprint,
    TaskId,
    fingerprint_proposal,
)
from contextforge.patch.conflicts import (
    PatchConflictValidationError,
    PatchConflictValidator,
    PatchConsistencyEvidence,
)
from contextforge.patch.models import (
    PatchDiagnostic,
    PatchProposal,
    PatchValidationState,
    PatchValidationSummary,
    ProposedChange,
)
from contextforge.patch.operations import (
    OperationValidationPolicy,
    PatchOperationValidationError,
    PatchOperationValidator,
    PatchSourceState,
)
from contextforge.patch.paths import (
    PatchPathValidationError,
    PatchPathValidator,
    ProtectedPathPolicy,
)


@dataclass(frozen=True, slots=True)
class PatchProposalMaterialization:
    """Exclusive outcome: one applicable proposal or rejection diagnostics."""

    proposal: PatchProposal | None = None
    diagnostics: tuple[PatchDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        diagnostics = tuple(self.diagnostics)
        if any(not isinstance(item, PatchDiagnostic) for item in diagnostics):
            raise TypeError("diagnostics must contain PatchDiagnostic values")
        if (self.proposal is None) == (not diagnostics):
            raise ValueError("result must contain exactly a proposal or diagnostics")
        if self.proposal is not None and not isinstance(self.proposal, PatchProposal):
            raise TypeError("proposal must be a PatchProposal")
        object.__setattr__(self, "diagnostics", diagnostics)

    @property
    def is_applicable(self) -> bool:
        """Whether validation produced a proposal eligible for review."""
        return self.proposal is not None


@dataclass(frozen=True, slots=True)
class PatchProposalMaterializer:
    """Compose patch validators and materialize only an entirely valid proposal."""

    protected_path_policy: ProtectedPathPolicy = field(default_factory=ProtectedPathPolicy)
    operation_policy: OperationValidationPolicy = field(default_factory=OperationValidationPolicy)

    def __post_init__(self) -> None:
        if not isinstance(self.protected_path_policy, ProtectedPathPolicy):
            raise TypeError("protected_path_policy must be a ProtectedPathPolicy")
        if not isinstance(self.operation_policy, OperationValidationPolicy):
            raise TypeError("operation_policy must be an OperationValidationPolicy")

    def materialize(
        self,
        *,
        proposal_id: PatchProposalId,
        task_id: TaskId,
        request_id: InferenceRequestId,
        response_id: InferenceResponseId,
        changes: tuple[ProposedChange, ...],
        source_state: PatchSourceState,
        consistency: PatchConsistencyEvidence,
        created_at: datetime,
        summary: str | None = None,
    ) -> PatchProposalMaterialization:
        """Run the safety pipeline and return no proposal if any check fails."""
        _validate_traceability(
            proposal_id,
            task_id,
            request_id,
            response_id,
            source_state,
            consistency,
            created_at,
        )
        changes = tuple(changes)
        if not changes:
            raise ValueError("changes must not be empty")
        if any(not isinstance(change, ProposedChange) for change in changes):
            raise TypeError("changes must contain ProposedChange values")

        diagnostics: list[PatchDiagnostic] = []
        path_validator = PatchPathValidator(self.protected_path_policy)
        operation_validator = PatchOperationValidator(self.operation_policy)
        for change in changes:
            try:
                path_validator.validate(
                    str(change.path),
                    change.operation,
                    (str(change.destination_path) if change.destination_path is not None else None),
                )
            except PatchPathValidationError as error:
                diagnostics.extend(_with_change_id(error.diagnostics, change.change_id))
            try:
                operation_validator.validate(change, source_state)
            except PatchOperationValidationError as error:
                diagnostics.extend(error.diagnostics)

        try:
            ordered_changes = PatchConflictValidator().validate(changes, consistency)
        except PatchConflictValidationError as error:
            diagnostics.extend(error.diagnostics)
            ordered_changes = changes

        if diagnostics:
            return PatchProposalMaterialization(diagnostics=tuple(diagnostics))

        validation = PatchValidationSummary(
            PatchValidationState.VALID,
            created_at,
        )
        return PatchProposalMaterialization(
            proposal=PatchProposal(
                proposal_id,
                task_id,
                request_id,
                response_id,
                consistency.source_project_fingerprint,
                ordered_changes,
                validation,
                created_at,
                summary,
            )
        )


def _validate_traceability(
    proposal_id: PatchProposalId,
    task_id: TaskId,
    request_id: InferenceRequestId,
    response_id: InferenceResponseId,
    source_state: PatchSourceState,
    consistency: PatchConsistencyEvidence,
    created_at: datetime,
) -> None:
    expected_types = (
        (proposal_id, PatchProposalId, "proposal_id"),
        (task_id, TaskId, "task_id"),
        (request_id, InferenceRequestId, "request_id"),
        (response_id, InferenceResponseId, "response_id"),
        (source_state, PatchSourceState, "source_state"),
        (consistency, PatchConsistencyEvidence, "consistency"),
    )
    for value, expected, field_name in expected_types:
        if not isinstance(value, expected):
            raise TypeError(f"{field_name} must be {expected.__name__}")
    if not isinstance(created_at, datetime):
        raise TypeError("created_at must be a datetime")
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("created_at must be timezone-aware")


def _with_change_id(
    diagnostics: tuple[PatchDiagnostic, ...],
    change_id: str,
) -> tuple[PatchDiagnostic, ...]:
    return tuple(
        PatchDiagnostic(
            item.code,
            item.severity,
            item.message,
            change_id,
        )
        for item in diagnostics
    )


def fingerprint_patch_proposal(proposal: PatchProposal) -> ProposalFingerprint:
    """Fingerprint all immutable proposal content used by approval binding."""
    if not isinstance(proposal, PatchProposal):
        raise TypeError("proposal must be a PatchProposal")
    change_components = tuple(
        json.dumps(
            {
                "assumptions": change.assumptions,
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
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        for change in proposal.changes
    )
    return fingerprint_proposal(
        (
            str(proposal.proposal_id),
            str(proposal.task_id),
            str(proposal.request_id),
            str(proposal.response_id),
            str(proposal.project_fingerprint),
            proposal.summary or "",
            *change_components,
        ),
        ordering=FingerprintOrdering.ORDERED,
    )
