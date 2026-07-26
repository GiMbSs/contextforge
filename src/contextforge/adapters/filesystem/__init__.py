"""Local filesystem adapters."""

from contextforge.adapters.filesystem.local import LocalProjectTraversal
from contextforge.adapters.filesystem.patches import (
    LocalStagedPatchApplication,
    PreflightEvidenceProvider,
)
from contextforge.adapters.filesystem.scanner import LocalProjectScanner

__all__ = [
    "LocalProjectScanner",
    "LocalProjectTraversal",
    "LocalStagedPatchApplication",
    "PreflightEvidenceProvider",
]
