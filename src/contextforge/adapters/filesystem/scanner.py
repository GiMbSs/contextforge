"""Complete local Project Scanner adapter."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from contextforge.adapters.filesystem.local import LocalProjectTraversal
from contextforge.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticCollection,
    DiagnosticLocation,
    DiagnosticSeverity,
)
from contextforge.domain import ArtifactFingerprint
from contextforge.scanner.classification import (
    MAX_CLASSIFICATION_SAMPLE_BYTES,
    ArtifactClassifier,
    ClassificationResult,
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
    ProjectArtifact,
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

    def scan(
        self,
        request: ScanRequest,
        previous_inventory: ProjectInventory | None = None,
    ) -> ProjectInventory:
        """Produce one complete or explicitly incomplete Project Inventory."""
        if not isinstance(request, ScanRequest):
            raise TypeError("request must be a ScanRequest")
        if previous_inventory is not None:
            if not isinstance(previous_inventory, ProjectInventory):
                raise TypeError("previous_inventory must be a ProjectInventory")
            if previous_inventory.project_id != request.project_id:
                raise ValueError("Previous Inventory belongs to another project")
        ignore_policy = IgnorePolicy.from_inputs(request.configuration)
        traversal = self.traversal.traverse(
            request.project_root,
            request.configuration,
            ignore_policy,
        )
        diagnostics = list(traversal.diagnostics)
        classified: list[ClassifiedEntry] = []
        classification_complete = True
        artifacts_reused = 0
        previous_by_path = (
            {artifact.path: artifact for artifact in previous_inventory.artifacts}
            if previous_inventory is not None
            else {}
        )

        for entry in traversal.entries:
            sample = b""
            content_fingerprint: str | None = None
            availability = ArtifactAvailability.INCLUDED

            if entry.entry_type is TraversalEntryType.FILE:
                try:
                    sample, content_fingerprint = self._read_content_state(
                        request,
                        entry,
                    )
                except OSError:
                    diagnostics.append(
                        _diagnostic(
                            "SCAN_PATH_UNREADABLE",
                            "File content could not be fingerprinted.",
                            entry,
                            DiagnosticSeverity.WARNING,
                        )
                    )
                    availability = ArtifactAvailability.UNREADABLE
                    classification_complete = False
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
                    sample = b""

            fingerprint = self._artifact_fingerprint(
                entry,
                content_fingerprint,
                include_timestamp=request.configuration.invalidate_on_timestamp_change,
            )
            previous = previous_by_path.get(entry.path)
            reusable = (
                previous is not None
                and previous.fingerprint == fingerprint
                and (
                    entry.entry_type is not TraversalEntryType.FILE
                    or content_fingerprint is not None
                )
                and previous_inventory is not None
                and previous_inventory.scanner_version == self.inventory_builder.scanner_version
            )
            if reusable and previous is not None:
                classification = self._reused_classification(previous)
                artifacts_reused += 1
            else:
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
                    fingerprint=fingerprint,
                    content_fingerprint=content_fingerprint,
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
            artifacts_reused=artifacts_reused,
        )

    @staticmethod
    def _read_content_state(
        request: ScanRequest,
        entry: TraversalEntry,
    ) -> tuple[bytes, str]:
        root = request.project_root.path.resolve(strict=True)
        candidate = root.joinpath(*entry.path.parts).resolve(strict=True)
        try:
            candidate.relative_to(root)
        except ValueError as error:
            raise OSError("Artifact escaped the Project Root") from error
        digest = hashlib.sha256()
        sample = bytearray()
        with candidate.open("rb") as stream:
            while chunk := stream.read(65_536):
                digest.update(chunk)
                remaining = MAX_CLASSIFICATION_SAMPLE_BYTES - len(sample)
                if remaining > 0:
                    sample.extend(chunk[:remaining])
        return bytes(sample), f"sha256:{digest.hexdigest()}"

    @staticmethod
    def _artifact_fingerprint(
        entry: TraversalEntry,
        content_fingerprint: str | None,
        *,
        include_timestamp: bool,
    ) -> ArtifactFingerprint:
        digest = hashlib.sha256()
        components = (
            f"path={entry.path.value}",
            f"entry_type={entry.entry_type.value}",
            f"content={content_fingerprint or 'none'}",
            (
                f"modified_time_ns={entry.modified_time_ns}"
                if include_timestamp
                else "modified_time_ns=ignored"
            ),
        )
        digest.update("\n".join(components).encode("utf-8"))
        return ArtifactFingerprint(f"artifact_sha256_{digest.hexdigest()}")

    @staticmethod
    def _reused_classification(artifact: ProjectArtifact) -> ClassificationResult:
        metadata = dict(artifact.metadata)
        evidence_value = metadata.get("classification_evidence", "")
        evidence = (
            tuple(str(evidence_value).split("|")) if evidence_value else ("classification:reused",)
        )
        language_value = metadata.get("detected_language")
        encoding_value = metadata.get("encoding")
        return ClassificationResult(
            kind=artifact.kind,
            classifications=artifact.classifications,
            detected_language=(language_value if isinstance(language_value, str) else None),
            encoding=encoding_value if isinstance(encoding_value, str) else None,
            evidence=evidence,
        )
