"""Immutable commands and queries accepted by the application layer."""

from __future__ import annotations

from dataclasses import dataclass

from contextforge.domain import (
    ApprovalId,
    ContextBundleId,
    InventoryId,
    PatchProposalId,
    ProjectId,
    TaskId,
    TaskSpecification,
)
from contextforge.patch import ApprovalMethod
from contextforge.project import ProjectRoot


def _require_type(value: object, expected: type[object], field_name: str) -> None:
    if not isinstance(value, expected):
        raise TypeError(f"{field_name} must be a {expected.__name__}")


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


@dataclass(frozen=True, slots=True)
class InitializeProject:
    """Initialize ContextForge metadata in an authorized project root."""

    project_root: ProjectRoot
    create_config: bool = False

    def __post_init__(self) -> None:
        _require_type(self.project_root, ProjectRoot, "project_root")
        if type(self.create_config) is not bool:
            raise TypeError("create_config must be a boolean")


@dataclass(frozen=True, slots=True)
class ScanProject:
    """Create a current inventory for an identified project."""

    project_id: ProjectId
    project_root: ProjectRoot

    def __post_init__(self) -> None:
        _require_type(self.project_id, ProjectId, "project_id")
        _require_type(self.project_root, ProjectRoot, "project_root")


@dataclass(frozen=True, slots=True)
class BuildProjectIndex:
    """Build an index from an existing immutable inventory."""

    project_id: ProjectId
    inventory_id: InventoryId

    def __post_init__(self) -> None:
        _require_type(self.project_id, ProjectId, "project_id")
        _require_type(self.inventory_id, InventoryId, "inventory_id")


@dataclass(frozen=True, slots=True)
class ExecuteTask:
    """Execute a normalized task against an identified project."""

    project_id: ProjectId
    task: TaskSpecification
    provider_id: str

    def __post_init__(self) -> None:
        _require_type(self.project_id, ProjectId, "project_id")
        _require_type(self.task, TaskSpecification, "task")
        _require_text(self.provider_id, "provider_id")


@dataclass(frozen=True, slots=True)
class ApprovePatchProposal:
    """Record explicit approval intent for one patch proposal."""

    proposal_id: PatchProposalId
    method: ApprovalMethod
    approving_principal: str | None = None
    acknowledged_warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_type(self.proposal_id, PatchProposalId, "proposal_id")
        _require_type(self.method, ApprovalMethod, "method")
        if self.approving_principal is not None:
            _require_text(self.approving_principal, "approving_principal")
        warnings = tuple(self.acknowledged_warnings)
        if any(not isinstance(item, str) or not item.strip() for item in warnings):
            raise ValueError("acknowledged_warnings must contain non-empty strings")
        if len(warnings) != len(set(warnings)):
            raise ValueError("acknowledged_warnings must not contain duplicates")
        object.__setattr__(self, "acknowledged_warnings", tuple(sorted(warnings)))


@dataclass(frozen=True, slots=True)
class RejectPatchProposal:
    """Reject a patch proposal with an auditable reason."""

    proposal_id: PatchProposalId
    reason: str

    def __post_init__(self) -> None:
        _require_type(self.proposal_id, PatchProposalId, "proposal_id")
        _require_text(self.reason, "reason")


@dataclass(frozen=True, slots=True)
class ApplyPatchProposal:
    """Apply an approved patch proposal."""

    proposal_id: PatchProposalId
    approval_id: ApprovalId

    def __post_init__(self) -> None:
        _require_type(self.proposal_id, PatchProposalId, "proposal_id")
        _require_type(self.approval_id, ApprovalId, "approval_id")


@dataclass(frozen=True, slots=True)
class GetProjectStatus:
    """Request the current status of a project."""

    project_id: ProjectId

    def __post_init__(self) -> None:
        _require_type(self.project_id, ProjectId, "project_id")


@dataclass(frozen=True, slots=True)
class GetContextBundle:
    """Request a context bundle by stable identity."""

    bundle_id: ContextBundleId

    def __post_init__(self) -> None:
        _require_type(self.bundle_id, ContextBundleId, "bundle_id")


@dataclass(frozen=True, slots=True)
class GetPromptPreview:
    """Request the prompt preview associated with a task."""

    task_id: TaskId

    def __post_init__(self) -> None:
        _require_type(self.task_id, TaskId, "task_id")


@dataclass(frozen=True, slots=True)
class ListProviders:
    """Request all configured provider summaries."""


@dataclass(frozen=True, slots=True)
class CheckProviderHealth:
    """Request a health check for one configured provider."""

    provider_id: str

    def __post_init__(self) -> None:
        _require_text(self.provider_id, "provider_id")


@dataclass(frozen=True, slots=True)
class GetPatchProposal:
    """Request a patch proposal by stable identity."""

    proposal_id: PatchProposalId

    def __post_init__(self) -> None:
        _require_type(self.proposal_id, PatchProposalId, "proposal_id")


@dataclass(frozen=True, slots=True)
class GetEffectiveConfiguration:
    """Request resolved configuration for an authorized project root."""

    project_root: ProjectRoot

    def __post_init__(self) -> None:
        _require_type(self.project_root, ProjectRoot, "project_root")


type ApplicationCommand = (
    InitializeProject
    | ScanProject
    | BuildProjectIndex
    | ExecuteTask
    | ApprovePatchProposal
    | RejectPatchProposal
    | ApplyPatchProposal
)

type ApplicationQuery = (
    GetProjectStatus
    | GetContextBundle
    | GetPromptPreview
    | ListProviders
    | CheckProviderHealth
    | GetPatchProposal
    | GetEffectiveConfiguration
)
