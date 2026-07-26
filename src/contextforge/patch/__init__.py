"""Patch proposal domain boundary."""

from contextforge.patch.approval import (
    ApprovalBindingError,
    ApprovalMethod,
    ApprovalRecord,
)
from contextforge.patch.conflicts import (
    PatchConflictValidationError,
    PatchConflictValidator,
    PatchConsistencyEvidence,
)
from contextforge.patch.envelope import (
    ProviderResponseEnvelopeValidator,
    ResponseEnvelopeValidationError,
    ValidatedResponseEnvelope,
)
from contextforge.patch.lifecycle import (
    PatchProposalLifecycle,
    ProposalLifecycleState,
)
from contextforge.patch.models import (
    PatchApprovalState,
    PatchDiagnostic,
    PatchOperation,
    PatchProposal,
    PatchValidationState,
    PatchValidationSummary,
    ProposedChange,
)
from contextforge.patch.operations import (
    OperationValidationPolicy,
    PatchOperationValidationError,
    PatchOperationValidator,
    PatchSourceArtifact,
    PatchSourceState,
)
from contextforge.patch.paths import (
    PatchPathValidationError,
    PatchPathValidator,
    ProtectedPathPolicy,
    ValidatedPatchPaths,
)
from contextforge.patch.proposal import (
    PatchProposalMaterialization,
    PatchProposalMaterializer,
    fingerprint_patch_proposal,
)
from contextforge.patch.structured import (
    StructuredPatchParseError,
    StructuredPatchParser,
)
from contextforge.patch.unified import (
    UnifiedDiff,
    UnifiedDiffHunk,
    UnifiedDiffLine,
    UnifiedDiffLineKind,
    UnifiedDiffParseError,
    UnifiedDiffParser,
    UnifiedFilePatch,
)

__all__ = [
    "ApprovalBindingError",
    "ApprovalMethod",
    "ApprovalRecord",
    "OperationValidationPolicy",
    "PatchApprovalState",
    "PatchConflictValidationError",
    "PatchConflictValidator",
    "PatchConsistencyEvidence",
    "PatchDiagnostic",
    "PatchOperation",
    "PatchOperationValidationError",
    "PatchOperationValidator",
    "PatchPathValidationError",
    "PatchPathValidator",
    "PatchProposal",
    "PatchProposalLifecycle",
    "PatchProposalMaterialization",
    "PatchProposalMaterializer",
    "PatchSourceArtifact",
    "PatchSourceState",
    "PatchValidationState",
    "PatchValidationSummary",
    "ProposalLifecycleState",
    "ProposedChange",
    "ProtectedPathPolicy",
    "ProviderResponseEnvelopeValidator",
    "ResponseEnvelopeValidationError",
    "StructuredPatchParseError",
    "StructuredPatchParser",
    "UnifiedDiff",
    "UnifiedDiffHunk",
    "UnifiedDiffLine",
    "UnifiedDiffLineKind",
    "UnifiedDiffParseError",
    "UnifiedDiffParser",
    "UnifiedFilePatch",
    "ValidatedPatchPaths",
    "ValidatedResponseEnvelope",
    "fingerprint_patch_proposal",
]
