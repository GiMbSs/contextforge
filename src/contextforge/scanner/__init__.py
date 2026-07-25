"""Project Scanner Core contracts."""

from contextforge.scanner.classification import (
    MAX_CLASSIFICATION_SAMPLE_BYTES,
    ArtifactClassifier,
    ClassificationResult,
    DeterministicArtifactClassifier,
)
from contextforge.scanner.ignore import (
    DEFAULT_EXCLUSION_PATTERNS,
    IgnoreAction,
    IgnoreDecision,
    IgnorePolicy,
    IgnoreRule,
    IgnoreRuleSource,
)
from contextforge.scanner.inventory import (
    SCANNER_VERSION,
    ClassifiedEntry,
    ProjectInventoryBuilder,
)
from contextforge.scanner.models import (
    ArtifactAvailability,
    ArtifactClassification,
    ArtifactKind,
    DiscoveryStatus,
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
    "MAX_CLASSIFICATION_SAMPLE_BYTES",
    "SCANNER_VERSION",
    "ArtifactAvailability",
    "ArtifactClassification",
    "ArtifactClassifier",
    "ArtifactKind",
    "ClassificationResult",
    "ClassifiedEntry",
    "DeterministicArtifactClassifier",
    "DiscoveryStatus",
    "IgnoreAction",
    "IgnoreDecision",
    "IgnorePolicy",
    "IgnoreRule",
    "IgnoreRuleSource",
    "ProjectArtifact",
    "ProjectInventory",
    "ProjectInventoryBuilder",
    "ProjectScanner",
    "ProjectTraversal",
    "ScanRequest",
    "ScanStatistics",
    "TraversalEntry",
    "TraversalEntryType",
    "TraversalResult",
]
