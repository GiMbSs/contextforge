"""Validation of patch operations against an immutable source state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn

from contextforge.diagnostics import DiagnosticCode, DiagnosticSeverity
from contextforge.domain import ArtifactPath, ContentFingerprint
from contextforge.patch.models import PatchDiagnostic, PatchOperation, ProposedChange


@dataclass(frozen=True, slots=True)
class PatchSourceArtifact:
    """Minimal source-state evidence required to validate one operation."""

    path: ArtifactPath
    content_fingerprint: ContentFingerprint | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.path, ArtifactPath):
            raise TypeError("path must be an ArtifactPath")
        if self.content_fingerprint is not None and not isinstance(
            self.content_fingerprint, ContentFingerprint
        ):
            raise TypeError("content_fingerprint must be a ContentFingerprint")


@dataclass(frozen=True, slots=True)
class PatchSourceState:
    """Deterministic project state supplied by a trusted upstream capability."""

    artifacts: tuple[PatchSourceArtifact, ...] = ()

    def __post_init__(self) -> None:
        artifacts = tuple(self.artifacts)
        if any(not isinstance(item, PatchSourceArtifact) for item in artifacts):
            raise TypeError("artifacts must contain PatchSourceArtifact values")
        if len({item.path for item in artifacts}) != len(artifacts):
            raise ValueError("source artifact paths must be unique")
        object.__setattr__(self, "artifacts", tuple(sorted(artifacts, key=lambda item: item.path)))

    def artifact_at(self, path: ArtifactPath) -> PatchSourceArtifact | None:
        """Return trusted source evidence for a path, if it exists."""
        return next((item for item in self.artifacts if item.path == path), None)


@dataclass(frozen=True, slots=True)
class OperationValidationPolicy:
    """Explicit exceptions to the default operation preconditions."""

    allow_create_overwrite: bool = False

    def __post_init__(self) -> None:
        if type(self.allow_create_overwrite) is not bool:
            raise TypeError("allow_create_overwrite must be a boolean")


class PatchOperationValidationError(ValueError):
    """Normalized rejection of an operation inconsistent with source state."""

    def __init__(self, diagnostics: tuple[PatchDiagnostic, ...]) -> None:
        if not diagnostics:
            raise ValueError("diagnostics must not be empty")
        self.diagnostics = diagnostics
        super().__init__(diagnostics[0].message)


@dataclass(frozen=True, slots=True)
class PatchOperationValidator:
    """Validate one proposed change without reading or mutating the filesystem."""

    policy: OperationValidationPolicy = OperationValidationPolicy()

    def __post_init__(self) -> None:
        if not isinstance(self.policy, OperationValidationPolicy):
            raise TypeError("policy must be an OperationValidationPolicy")

    def validate(self, change: ProposedChange, source: PatchSourceState) -> ProposedChange:
        """Return the unchanged proposal when all operation preconditions hold."""
        if not isinstance(change, ProposedChange):
            raise TypeError("change must be a ProposedChange")
        if not isinstance(source, PatchSourceState):
            raise TypeError("source must be a PatchSourceState")

        current = source.artifact_at(change.path)
        if change.operation is PatchOperation.CREATE:
            if current is not None and not self.policy.allow_create_overwrite:
                self._reject(
                    "PATCH_OPERATION_CREATE_EXISTS",
                    "Create target already exists in the proposal source state.",
                    change,
                )
            return change

        if current is None:
            self._reject(
                f"PATCH_OPERATION_{change.operation.value.upper()}_MISSING_SOURCE",
                f"{change.operation.value.capitalize()} source does not exist "
                "in the proposal source state.",
                change,
            )

        if change.operation is PatchOperation.RENAME:
            assert change.destination_path is not None
            if source.artifact_at(change.destination_path) is not None:
                self._reject(
                    "PATCH_OPERATION_RENAME_TARGET_EXISTS",
                    "Rename destination already exists in the proposal source state.",
                    change,
                )

        if (
            change.expected_old_fingerprint is not None
            and change.expected_old_fingerprint != current.content_fingerprint
        ):
            self._reject(
                "PATCH_OPERATION_FINGERPRINT_MISMATCH",
                "Expected old fingerprint does not match the proposal source state.",
                change,
            )
        return change

    @staticmethod
    def _reject(code: str, message: str, change: ProposedChange) -> NoReturn:
        raise PatchOperationValidationError(
            (
                PatchDiagnostic(
                    DiagnosticCode(code),
                    DiagnosticSeverity.ERROR,
                    message,
                    change.change_id,
                ),
            )
        )
