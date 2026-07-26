"""Policy-aware validation of untrusted patch paths."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import NoReturn

from contextforge.diagnostics import DiagnosticCode, DiagnosticSeverity
from contextforge.domain import ArtifactPath, ProjectPath
from contextforge.patch.models import PatchDiagnostic, PatchOperation

_WINDOWS_DEVICE = re.compile(
    r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ProtectedPathPolicy:
    """Explicit lexical areas unavailable to provider-proposed changes."""

    protected_paths: tuple[ProjectPath, ...] = (
        ProjectPath(".git"),
        ProjectPath(".env"),
        ProjectPath("secrets"),
    )
    forbid_protected_paths: bool = True

    def __post_init__(self) -> None:
        paths = tuple(self.protected_paths)
        if any(not isinstance(path, ProjectPath) for path in paths):
            raise TypeError("protected_paths must contain ProjectPath values")
        if len(set(paths)) != len(paths):
            raise ValueError("protected_paths must not contain duplicates")
        if type(self.forbid_protected_paths) is not bool:
            raise TypeError("forbid_protected_paths must be a boolean")
        object.__setattr__(self, "protected_paths", tuple(sorted(paths)))


@dataclass(frozen=True, slots=True)
class ValidatedPatchPaths:
    """Canonical source and optional rename destination."""

    source: ArtifactPath
    destination: ArtifactPath | None = None


class PatchPathValidationError(ValueError):
    """Normalized rejection of one unsafe patch path."""

    def __init__(self, diagnostics: tuple[PatchDiagnostic, ...]) -> None:
        if not diagnostics:
            raise ValueError("diagnostics must not be empty")
        self.diagnostics = diagnostics
        super().__init__(diagnostics[0].message)


@dataclass(frozen=True, slots=True)
class PatchPathValidator:
    """Validate paths lexically without touching the filesystem."""

    policy: ProtectedPathPolicy = ProtectedPathPolicy()

    def __post_init__(self) -> None:
        if not isinstance(self.policy, ProtectedPathPolicy):
            raise TypeError("policy must be a ProtectedPathPolicy")

    def validate(
        self,
        source: str,
        operation: PatchOperation,
        destination: str | None = None,
    ) -> ValidatedPatchPaths:
        """Normalize paths and enforce operation and protection invariants."""
        if not isinstance(operation, PatchOperation):
            raise TypeError("operation must be a PatchOperation")
        source_path = self._validate_one(source, "source")
        destination_path = (
            self._validate_one(destination, "destination") if destination is not None else None
        )
        if operation is PatchOperation.RENAME:
            if destination_path is None:
                _reject(
                    "PATCH_PATH_INVALID_RENAME",
                    "Rename requires both source and destination paths.",
                )
            if source_path == destination_path:
                _reject(
                    "PATCH_PATH_INVALID_RENAME",
                    "Rename source and destination must differ.",
                )
        elif destination_path is not None:
            _reject(
                "PATCH_PATH_INVALID_RENAME",
                "Only rename operations may declare a destination path.",
            )
        return ValidatedPatchPaths(source_path, destination_path)

    def _validate_one(self, value: str, label: str) -> ArtifactPath:
        if not isinstance(value, str):
            _reject(
                "PATCH_PATH_INVALID",
                f"Patch {label} path must be text.",
            )
        _reject_unsupported_device_path(value)
        try:
            path = ArtifactPath(value)
        except ValueError:
            _reject(
                "PATCH_PATH_OUTSIDE_PROJECT",
                f"Patch {label} path must remain project-relative.",
            )
        if self.policy.forbid_protected_paths and any(
            _is_within(path, protected) for protected in self.policy.protected_paths
        ):
            _reject(
                "PATCH_PATH_PROTECTED",
                f"Patch {label} path is inside a protected area.",
            )
        return path


def _reject_unsupported_device_path(value: str) -> None:
    normalized = value.replace("\\", "/")
    if normalized.startswith(("//", "/?/", "/./")):
        _reject(
            "PATCH_PATH_UNSUPPORTED_DEVICE",
            "UNC and device paths are not supported.",
        )
    for segment in normalized.split("/"):
        if ":" in segment or _WINDOWS_DEVICE.fullmatch(segment.rstrip(" .")):
            _reject(
                "PATCH_PATH_UNSUPPORTED_DEVICE",
                "Windows drive, stream and device paths are not supported.",
            )


def _is_within(path: ArtifactPath, protected: ProjectPath) -> bool:
    protected_parts = protected.parts
    return path.parts[: len(protected_parts)] == protected_parts


def _reject(code: str, message: str) -> NoReturn:
    raise PatchPathValidationError(
        (
            PatchDiagnostic(
                DiagnosticCode(code),
                DiagnosticSeverity.ERROR,
                message,
            ),
        )
    )
