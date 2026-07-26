"""Application-layer ports and orchestration contracts."""

from contextforge.application.initialization import (
    ProjectInitialization,
    ProjectInitializationPort,
    ProjectInitializationResult,
)
from contextforge.application.messages import (
    ApplicationCommand,
    ApplicationQuery,
    ApplyPatchProposal,
    ApprovePatchProposal,
    BuildProjectIndex,
    CheckProviderHealth,
    ExecuteTask,
    GetContextBundle,
    GetEffectiveConfiguration,
    GetPatchProposal,
    GetProjectStatus,
    GetPromptPreview,
    InitializeProject,
    ListProviders,
    RejectPatchProposal,
    ScanProject,
)
from contextforge.application.patches import (
    ApplicationPreviewChange,
    PatchApplication,
    PatchApplicationPreview,
    PatchApplicationResult,
    PatchApplicationStatus,
)
from contextforge.application.preflight import (
    ApplicationPreflightEvidence,
    ApplicationPreflightResult,
    PatchApplicationPreflight,
)

__all__ = [
    "ApplicationCommand",
    "ApplicationPreflightEvidence",
    "ApplicationPreflightResult",
    "ApplicationPreviewChange",
    "ApplicationQuery",
    "ApplyPatchProposal",
    "ApprovePatchProposal",
    "BuildProjectIndex",
    "CheckProviderHealth",
    "ExecuteTask",
    "GetContextBundle",
    "GetEffectiveConfiguration",
    "GetPatchProposal",
    "GetProjectStatus",
    "GetPromptPreview",
    "InitializeProject",
    "ListProviders",
    "PatchApplication",
    "PatchApplicationPreflight",
    "PatchApplicationPreview",
    "PatchApplicationResult",
    "PatchApplicationStatus",
    "ProjectInitialization",
    "ProjectInitializationPort",
    "ProjectInitializationResult",
    "RejectPatchProposal",
    "ScanProject",
]
