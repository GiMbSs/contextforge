"""Patch proposal domain boundary."""

from contextforge.patch.envelope import (
    ProviderResponseEnvelopeValidator,
    ResponseEnvelopeValidationError,
    ValidatedResponseEnvelope,
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
from contextforge.patch.paths import (
    PatchPathValidationError,
    PatchPathValidator,
    ProtectedPathPolicy,
    ValidatedPatchPaths,
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
    "PatchApprovalState",
    "PatchDiagnostic",
    "PatchOperation",
    "PatchPathValidationError",
    "PatchPathValidator",
    "PatchProposal",
    "PatchValidationState",
    "PatchValidationSummary",
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
]
