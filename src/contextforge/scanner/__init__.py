"""Project Scanner Core contracts."""

from contextforge.scanner.ignore import (
    DEFAULT_EXCLUSION_PATTERNS,
    IgnoreAction,
    IgnoreDecision,
    IgnorePolicy,
    IgnoreRule,
    IgnoreRuleSource,
)
from contextforge.scanner.models import (
    ArtifactAvailability,
    ArtifactClassification,
    ArtifactKind,
    ProjectArtifact,
    ProjectInventory,
    ScanRequest,
    ScanStatistics,
)
from contextforge.scanner.ports import ProjectScanner
from contextforge.scanner.traversal import (
    ProjectTraversal,
    TraversalEntry,
    TraversalEntryType,
    TraversalResult,
)

__all__ = [
    "DEFAULT_EXCLUSION_PATTERNS",
    "ArtifactAvailability",
    "ArtifactClassification",
    "ArtifactKind",
    "IgnoreAction",
    "IgnoreDecision",
    "IgnorePolicy",
    "IgnoreRule",
    "IgnoreRuleSource",
    "ProjectArtifact",
    "ProjectInventory",
    "ProjectScanner",
    "ProjectTraversal",
    "ScanRequest",
    "ScanStatistics",
    "TraversalEntry",
    "TraversalEntryType",
    "TraversalResult",
]
