"""Local filesystem adapters."""

from contextforge.adapters.filesystem.initialization import LocalProjectInitialization
from contextforge.adapters.filesystem.local import LocalProjectTraversal
from contextforge.adapters.filesystem.patches import (
    LocalStagedPatchApplication,
    PreflightEvidenceProvider,
)
from contextforge.adapters.filesystem.scanner import LocalProjectScanner
from contextforge.adapters.filesystem.state import (
    FilesystemIndexStorage,
    FilesystemInventoryStorage,
    ProjectStateStorageError,
)

__all__ = [
    "FilesystemIndexStorage",
    "FilesystemInventoryStorage",
    "LocalProjectInitialization",
    "LocalProjectScanner",
    "LocalProjectTraversal",
    "LocalStagedPatchApplication",
    "PreflightEvidenceProvider",
    "ProjectStateStorageError",
]
