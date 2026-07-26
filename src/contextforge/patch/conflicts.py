"""Deterministic conflict and consistency validation for patch changes."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from contextforge.diagnostics import DiagnosticCode, DiagnosticSeverity
from contextforge.domain import ArtifactPath, ProjectFingerprint
from contextforge.patch.models import PatchDiagnostic, PatchOperation, ProposedChange


@dataclass(frozen=True, slots=True)
class PatchConsistencyEvidence:
    """Trusted evidence used to validate proposal-level consistency."""

    affected_files: tuple[ArtifactPath, ...]
    expected_project_fingerprint: ProjectFingerprint
    source_project_fingerprint: ProjectFingerprint

    def __post_init__(self) -> None:
        affected_files = tuple(self.affected_files)
        if any(not isinstance(path, ArtifactPath) for path in affected_files):
            raise TypeError("affected_files must contain ArtifactPath values")
        if len(set(affected_files)) != len(affected_files):
            raise ValueError("affected_files must not contain duplicates")
        if not isinstance(self.expected_project_fingerprint, ProjectFingerprint):
            raise TypeError("expected_project_fingerprint must be a ProjectFingerprint")
        if not isinstance(self.source_project_fingerprint, ProjectFingerprint):
            raise TypeError("source_project_fingerprint must be a ProjectFingerprint")
        object.__setattr__(self, "affected_files", tuple(sorted(affected_files)))


class PatchConflictValidationError(ValueError):
    """Aggregate rejection of an inconsistent collection of changes."""

    def __init__(self, diagnostics: tuple[PatchDiagnostic, ...]) -> None:
        if not diagnostics:
            raise ValueError("diagnostics must not be empty")
        self.diagnostics = diagnostics
        super().__init__(diagnostics[0].message)


@dataclass(frozen=True, slots=True)
class PatchConflictValidator:
    """Detect conflicts without applying or interpreting patch payloads."""

    def validate(
        self,
        changes: tuple[ProposedChange, ...],
        evidence: PatchConsistencyEvidence,
    ) -> tuple[ProposedChange, ...]:
        """Return deterministically ordered changes or all detected diagnostics."""
        changes = tuple(changes)
        if not changes:
            raise ValueError("changes must not be empty")
        if any(not isinstance(change, ProposedChange) for change in changes):
            raise TypeError("changes must contain ProposedChange values")
        if not isinstance(evidence, PatchConsistencyEvidence):
            raise TypeError("evidence must be PatchConsistencyEvidence")

        diagnostics: list[PatchDiagnostic] = []
        diagnostics.extend(_duplicate_identifiers(changes))
        diagnostics.extend(_source_path_conflicts(changes))
        diagnostics.extend(_rename_destination_conflicts(changes))
        diagnostics.extend(_rename_cycles(changes))
        diagnostics.extend(_affected_file_mismatch(changes, evidence))
        diagnostics.extend(_project_fingerprint_mismatch(evidence))
        if diagnostics:
            raise PatchConflictValidationError(tuple(diagnostics))
        return tuple(sorted(changes, key=lambda change: (change.path, change.change_id)))


def _duplicate_identifiers(changes: tuple[ProposedChange, ...]) -> list[PatchDiagnostic]:
    by_identifier: dict[str, list[ProposedChange]] = defaultdict(list)
    for change in changes:
        by_identifier[change.change_id].append(change)
    return [
        _diagnostic(
            "PATCH_CONFLICT_DUPLICATE_CHANGE_ID",
            f"Change identifier '{identifier}' is used more than once.",
            grouped[0],
        )
        for identifier, grouped in sorted(by_identifier.items())
        if len(grouped) > 1
    ]


def _source_path_conflicts(changes: tuple[ProposedChange, ...]) -> list[PatchDiagnostic]:
    by_path: dict[ArtifactPath, list[ProposedChange]] = defaultdict(list)
    for change in changes:
        by_path[change.path].append(change)

    diagnostics: list[PatchDiagnostic] = []
    for path, grouped in sorted(by_path.items()):
        if len(grouped) < 2:
            continue
        operations = {change.operation for change in grouped}
        code = (
            "PATCH_CONFLICT_DUPLICATE_OPERATION"
            if len(operations) == 1
            else "PATCH_CONFLICT_INCOMPATIBLE_OPERATIONS"
        )
        diagnostics.append(
            _diagnostic(
                code,
                f"Path '{path}' has multiple incompatible proposed changes.",
                sorted(grouped, key=lambda change: change.change_id)[0],
            )
        )
    return diagnostics


def _rename_destination_conflicts(
    changes: tuple[ProposedChange, ...],
) -> list[PatchDiagnostic]:
    renames = tuple(change for change in changes if change.operation is PatchOperation.RENAME)
    by_destination: dict[ArtifactPath, list[ProposedChange]] = defaultdict(list)
    for change in renames:
        assert change.destination_path is not None
        by_destination[change.destination_path].append(change)

    diagnostics = [
        _diagnostic(
            "PATCH_CONFLICT_RENAME_DESTINATION",
            f"Multiple renames target '{destination}'.",
            sorted(grouped, key=lambda change: change.change_id)[0],
        )
        for destination, grouped in sorted(by_destination.items())
        if len(grouped) > 1
    ]
    rename_sources = {change.path for change in renames}
    for change in sorted(changes, key=lambda item: (item.path, item.change_id)):
        if change.operation is PatchOperation.RENAME or change.path not in by_destination:
            continue
        if change.path in rename_sources:
            continue
        diagnostics.append(
            _diagnostic(
                "PATCH_CONFLICT_RENAME_DESTINATION",
                f"Rename destination '{change.path}' is also changed directly.",
                change,
            )
        )
    return diagnostics


def _rename_cycles(changes: tuple[ProposedChange, ...]) -> list[PatchDiagnostic]:
    renames = {
        change.path: change for change in changes if change.operation is PatchOperation.RENAME
    }
    cycles: set[tuple[ArtifactPath, ...]] = set()
    for start in sorted(renames):
        path: ArtifactPath | None = start
        visited: list[ArtifactPath] = []
        positions: dict[ArtifactPath, int] = {}
        while path in renames and path not in positions:
            positions[path] = len(visited)
            visited.append(path)
            path = renames[path].destination_path
        if path in positions:
            cycle = visited[positions[path] :]
            rotations = tuple(tuple(cycle[index:] + cycle[:index]) for index in range(len(cycle)))
            cycles.add(min(rotations))
    return [
        _diagnostic(
            "PATCH_CONFLICT_RENAME_CYCLE",
            "Rename cycle detected: " + " -> ".join(str(path) for path in cycle) + ".",
            renames[cycle[0]],
        )
        for cycle in sorted(cycles)
    ]


def _affected_file_mismatch(
    changes: tuple[ProposedChange, ...],
    evidence: PatchConsistencyEvidence,
) -> list[PatchDiagnostic]:
    proposed_paths = {
        path
        for change in changes
        for path in (change.path, change.destination_path)
        if path is not None
    }
    if proposed_paths == set(evidence.affected_files):
        return []
    return [
        PatchDiagnostic(
            DiagnosticCode("PATCH_CONSISTENCY_AFFECTED_FILES_MISMATCH"),
            DiagnosticSeverity.ERROR,
            "Declared affected files do not match the proposed changes.",
        )
    ]


def _project_fingerprint_mismatch(
    evidence: PatchConsistencyEvidence,
) -> list[PatchDiagnostic]:
    if evidence.expected_project_fingerprint == evidence.source_project_fingerprint:
        return []
    return [
        PatchDiagnostic(
            DiagnosticCode("PATCH_CONSISTENCY_PROJECT_FINGERPRINT_MISMATCH"),
            DiagnosticSeverity.ERROR,
            "Expected project fingerprint does not match the proposal source state.",
        )
    ]


def _diagnostic(code: str, message: str, change: ProposedChange) -> PatchDiagnostic:
    return PatchDiagnostic(
        DiagnosticCode(code),
        DiagnosticSeverity.ERROR,
        message,
        change.change_id,
    )
