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
from contextforge.patch.structured import (
    StructuredPatchParseError,
    StructuredPatchParser,
)

__all__ = [
    "PatchApprovalState",
    "PatchDiagnostic",
    "PatchOperation",
    "PatchProposal",
    "PatchValidationState",
    "PatchValidationSummary",
    "ProposedChange",
    "ProviderResponseEnvelopeValidator",
    "ResponseEnvelopeValidationError",
    "StructuredPatchParseError",
    "StructuredPatchParser",
    "ValidatedResponseEnvelope",
]
