"""Strongly typed identifiers for ContextForge domain entities."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar, Self
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class _Identifier:
    """Immutable, validated textual identity shared by concrete identifier types."""

    value: str
    prefix: ClassVar[str]

    def __post_init__(self) -> None:
        pattern = rf"{re.escape(self.prefix)}_[0-9a-f]{{32}}"
        if re.fullmatch(pattern, self.value) is None:
            raise ValueError(
                f"{type(self).__name__} must match {self.prefix!r} followed by "
                "'_' and 32 lowercase hexadecimal characters"
            )

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, value: str) -> Self:
        """Deserialize and validate an identifier from its canonical string."""
        return cls(value)


@dataclass(frozen=True, slots=True)
class ProjectId(_Identifier):
    """Identity of an authorized ContextForge project."""

    prefix: ClassVar[str] = "project"


@dataclass(frozen=True, slots=True)
class ExecutionId(_Identifier):
    """Identity of one ContextForge workflow execution."""

    prefix: ClassVar[str] = "execution"


@dataclass(frozen=True, slots=True)
class InventoryId(_Identifier):
    """Identity of an immutable Project Inventory."""

    prefix: ClassVar[str] = "inventory"


@dataclass(frozen=True, slots=True)
class IndexId(_Identifier):
    """Identity of an immutable Project Index."""

    prefix: ClassVar[str] = "index"


@dataclass(frozen=True, slots=True)
class RetrievalId(_Identifier):
    """Identity of an immutable Retrieval Result."""

    prefix: ClassVar[str] = "retrieval"


@dataclass(frozen=True, slots=True)
class ContextBundleId(_Identifier):
    """Identity of an immutable Context Bundle."""

    prefix: ClassVar[str] = "context_bundle"


@dataclass(frozen=True, slots=True)
class InferenceRequestId(_Identifier):
    """Identity of an immutable Inference Request."""

    prefix: ClassVar[str] = "inference_request"


@dataclass(frozen=True, slots=True)
class InferenceResponseId(_Identifier):
    """Identity of an immutable Inference Response."""

    prefix: ClassVar[str] = "inference_response"


@dataclass(frozen=True, slots=True)
class PatchProposalId(_Identifier):
    """Identity of an immutable Patch Proposal."""

    prefix: ClassVar[str] = "patch_proposal"


@dataclass(frozen=True, slots=True)
class ApprovalId(_Identifier):
    """Identity of an explicit patch Approval Record."""

    prefix: ClassVar[str] = "approval"


def _new_identifier[IdentifierT: _Identifier](identifier_type: type[IdentifierT]) -> IdentifierT:
    return identifier_type(f"{identifier_type.prefix}_{uuid4().hex}")


def new_project_id() -> ProjectId:
    """Generate a new Project Identifier."""
    return _new_identifier(ProjectId)


def new_execution_id() -> ExecutionId:
    """Generate a new Execution Identifier."""
    return _new_identifier(ExecutionId)


def new_inventory_id() -> InventoryId:
    """Generate a new Inventory Identifier."""
    return _new_identifier(InventoryId)


def new_index_id() -> IndexId:
    """Generate a new Index Identifier."""
    return _new_identifier(IndexId)


def new_retrieval_id() -> RetrievalId:
    """Generate a new Retrieval Identifier."""
    return _new_identifier(RetrievalId)


def new_context_bundle_id() -> ContextBundleId:
    """Generate a new Context Bundle Identifier."""
    return _new_identifier(ContextBundleId)


def new_inference_request_id() -> InferenceRequestId:
    """Generate a new Inference Request Identifier."""
    return _new_identifier(InferenceRequestId)


def new_inference_response_id() -> InferenceResponseId:
    """Generate a new Inference Response Identifier."""
    return _new_identifier(InferenceResponseId)


def new_patch_proposal_id() -> PatchProposalId:
    """Generate a new Patch Proposal Identifier."""
    return _new_identifier(PatchProposalId)


def new_approval_id() -> ApprovalId:
    """Generate a new Approval Identifier."""
    return _new_identifier(ApprovalId)
