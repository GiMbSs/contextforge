"""Structured patch proposal response contract."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from contextforge.domain import ArtifactPath
from contextforge.prompt.models import ResponseContract, ResponseFormat

PATCH_RESPONSE_CONTRACT_ID = "patch-proposal-response"
PATCH_RESPONSE_CONTRACT_VERSION = "patch-proposal-response-v1"


class PatchPayloadFormat(StrEnum):
    """Supported provider-independent patch payload representations."""

    UNIFIED_DIFF = "unified_diff"
    STRUCTURED_CHANGES = "structured_changes"


class ProposedChangeOperation(StrEnum):
    """Operations a structured patch proposal may describe."""

    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"
    RENAME = "rename"


@dataclass(frozen=True, slots=True)
class ProposedFileChange:
    """One declared file operation within a patch response."""

    path: ArtifactPath
    operation: ProposedChangeOperation
    explanation: str
    patch: str | None = None
    destination_path: ArtifactPath | None = None
    validation_notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.path, ArtifactPath):
            raise TypeError("path must be an ArtifactPath")
        if not isinstance(self.operation, ProposedChangeOperation):
            raise TypeError("operation must be a ProposedChangeOperation")
        if not self.explanation.strip():
            raise ValueError("explanation must not be empty")
        if self.operation in (
            ProposedChangeOperation.CREATE,
            ProposedChangeOperation.MODIFY,
        ):
            if self.patch is None or not self.patch:
                raise ValueError("create and modify operations require patch content")
        elif self.patch is not None:
            raise ValueError("delete and rename operations must not include patch content")
        if self.operation is ProposedChangeOperation.RENAME:
            if self.destination_path is None:
                raise ValueError("rename operation requires destination_path")
            if self.destination_path == self.path:
                raise ValueError("rename destination must differ from source")
        elif self.destination_path is not None:
            raise ValueError("destination_path is only valid for rename operations")
        notes = tuple(self.validation_notes)
        if any(not note.strip() for note in notes):
            raise ValueError("validation_notes must contain non-empty values")
        object.__setattr__(self, "validation_notes", notes)


@dataclass(frozen=True, slots=True)
class PatchResponseEnvelope:
    """Versioned structured output expected by the future Patch Engine."""

    response_type: str
    summary: str
    assumptions: tuple[str, ...]
    patch_format: PatchPayloadFormat
    patch_payload: str
    affected_files: tuple[ArtifactPath, ...]
    warnings: tuple[str, ...]
    changes: tuple[ProposedFileChange, ...] = ()

    def __post_init__(self) -> None:
        if self.response_type != "patch_proposal":
            raise ValueError("response_type must be patch_proposal")
        if not self.summary.strip():
            raise ValueError("summary must not be empty")
        for field_name in ("assumptions", "warnings"):
            values = tuple(getattr(self, field_name))
            if any(not value.strip() for value in values):
                raise ValueError(f"{field_name} must contain non-empty values")
            object.__setattr__(self, field_name, values)
        if not isinstance(self.patch_format, PatchPayloadFormat):
            raise TypeError("patch_format must be a PatchPayloadFormat")
        if not self.patch_payload:
            raise ValueError("patch_payload must not be empty")
        affected_files = tuple(self.affected_files)
        if not affected_files:
            raise ValueError("affected_files must not be empty")
        if any(not isinstance(path, ArtifactPath) for path in affected_files):
            raise TypeError("affected_files must contain ArtifactPath values")
        if len(set(affected_files)) != len(affected_files):
            raise ValueError("affected_files must not contain duplicates")
        changes = tuple(self.changes)
        if any(not isinstance(change, ProposedFileChange) for change in changes):
            raise TypeError("changes must contain ProposedFileChange values")
        declared_paths = {
            path
            for change in changes
            for path in (change.path, change.destination_path)
            if path is not None
        }
        if changes and declared_paths != set(affected_files):
            raise ValueError("affected_files must exactly match structured changes")
        object.__setattr__(self, "affected_files", affected_files)
        object.__setattr__(self, "changes", changes)


def patch_response_contract() -> ResponseContract:
    """Return the canonical structured patch proposal response contract."""
    return ResponseContract(
        contract_id=PATCH_RESPONSE_CONTRACT_ID,
        version=PATCH_RESPONSE_CONTRACT_VERSION,
        purpose="Return a patch proposal for later validation; do not apply it.",
        response_type="patch_proposal",
        output_format=ResponseFormat.STRUCTURED_PATCH,
        required_fields=(
            "response_type",
            "summary",
            "assumptions",
            "patch_format",
            "patch_payload",
            "affected_files",
            "warnings",
        ),
        prohibited_operations=(
            "absolute_path",
            "path_outside_project_root",
            "hidden_file_modification",
            "undeclared_binary_modification",
            "claim_patch_applied",
            "execute_project",
        ),
        error_behavior=(
            "Return a structured insufficient-context response instead of inventing "
            "files or changes."
        ),
        validation_instructions=(
            "Use only canonical project-relative paths.",
            "Declare every affected file.",
            "Do not include prose outside the structured envelope.",
            "Do not claim that the proposal was applied.",
        ),
        allow_commentary=False,
    )
