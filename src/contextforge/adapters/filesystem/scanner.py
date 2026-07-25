"""Complete local Project Scanner adapter."""

from __future__ import annotations

from dataclasses import dataclass, field

from contextforge.adapters.filesystem.local import LocalProjectTraversal
from contextforge.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticCollection,
    DiagnosticLocation,
    DiagnosticSeverity,
)
from contextforge.scanner.classification import (
    MAX_CLASSIFICATION_SAMPLE_BYTES,
    ArtifactClassifier,
    DeterministicArtifactClassifier,
)
from contextforge.scanner.ignore import IgnorePolicy
from contextforge.scanner.inventory import (
    ClassifiedEntry,
    ProjectInventoryBuilder,
)
from contextforge.scanner.models import (
    ArtifactAvailability,
    ArtifactKind,
    ProjectInventory,
    ScanRequest,
)
from contextforge.scanner.traversal import (
    ProjectTraversal,
    TraversalEntry,
    TraversalEntryType,
)


def _diagnostic(
    code: str,
    message: str,
    entry: TraversalEntry,
    severity: DiagnosticSeverity,
) -> Diagnostic:
    return Diagnostic(
        code=DiagnosticCode(code),
        severity=severity,
        message=message,
        capability="scanner",
        location=DiagnosticLocation(entry.path.value),
    )


@dataclass(slots=True)
class LocalProjectScanner:
    """Compose safe traversal, bounded reads, classification, and inventory."""

    traversal: ProjectTraversal = field(default_factory=LocalProjectTraversal)
    classifier: ArtifactClassifier = field(default_factory=DeterministicArtifactClassifier)
    inventory_builder: ProjectInventoryBuilder = field(default_factory=ProjectInventoryBuilder)

    def scan(self, request: ScanRequest) -> ProjectInventory:
        """Produce one complete or explicitly incomplete Project Inventory."""
        if not isinstance(request, ScanRequest):
            raise TypeError("request must be a ScanRequest")
        ignore_policy = IgnorePolicy.from_inputs(request.configuration)
        traversal = self.traversal.traverse(
            request.project_root,
            request.configuration,
            ignore_policy,
        )
        diagnostics = list(traversal.diagnostics)
        classified: list[ClassifiedEntry] = []
        classification_complete = True

        for entry in traversal.entries:
            preliminary = self.classifier.classify(entry)
            sample = b""
            availability = ArtifactAvailability.INCLUDED

            if (
                entry.entry_type is TraversalEntryType.FILE
                and preliminary.kind is not ArtifactKind.BINARY
            ):
                if entry.size_bytes > request.configuration.max_file_size_bytes:
                    diagnostics.append(
                        _diagnostic(
                            "SCAN_FILE_TOO_LARGE",
                            "File exceeds the configured classification size limit.",
                            entry,
                            DiagnosticSeverity.WARNING,
                        )
                    )
                    availability = ArtifactAvailability.SKIPPED
                else:
                    try:
                        sample = self._read_bounded_sample(request, entry)
                    except OSError:
                        diagnostics.append(
                            _diagnostic(
                                "SCAN_PATH_UNREADABLE",
                                "File sample could not be read.",
                                entry,
                                DiagnosticSeverity.WARNING,
                            )
                        )
                        availability = ArtifactAvailability.UNREADABLE
                        classification_complete = False

            classification = self.classifier.classify(entry, sample)
            if classification.kind is ArtifactKind.BINARY:
                diagnostics.append(
                    _diagnostic(
                        "SCAN_BINARY_DETECTED",
                        "Artifact was classified as binary.",
                        entry,
                        DiagnosticSeverity.INFO,
                    )
                )
            classified.append(
                ClassifiedEntry(
                    entry=entry,
                    classification=classification,
                    availability=availability,
                )
            )

        merged_diagnostics = DiagnosticCollection(tuple(diagnostics))
        return self.inventory_builder.build(
            request,
            traversal,
            tuple(classified),
            ignore_policy,
            merged_diagnostics,
            classification_complete=classification_complete,
        )

    @staticmethod
    def _read_bounded_sample(request: ScanRequest, entry: TraversalEntry) -> bytes:
        root = request.project_root.path.resolve(strict=True)
        candidate = root.joinpath(*entry.path.parts).resolve(strict=True)
        try:
            candidate.relative_to(root)
        except ValueError as error:
            raise OSError("Artifact escaped the Project Root") from error
        with candidate.open("rb") as stream:
            return stream.read(MAX_CLASSIFICATION_SAMPLE_BYTES)
