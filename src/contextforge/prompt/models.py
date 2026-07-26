"""Immutable, provider-independent inference request contracts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from contextforge.diagnostics import DiagnosticCollection
from contextforge.domain import (
    ContextBundleId,
    InferenceRequestId,
    ProjectFingerprint,
    ProjectId,
    TaskId,
)


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_identifier(value: str, field_name: str) -> None:
    _require_text(value, field_name)
    if any(character.isspace() for character in value):
        raise ValueError(f"{field_name} must not contain whitespace")


def _normalize_unique_text(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    normalized = tuple(values)
    if any(not isinstance(value, str) or not value.strip() for value in normalized):
        raise ValueError(f"{field_name} must contain non-empty strings")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must not contain duplicates")
    return normalized


class PromptRole(StrEnum):
    """Logical roles that provider adapters may translate."""

    SYSTEM = "system"
    USER = "user"


class PromptTrust(StrEnum):
    """Whether message content may carry authoritative instructions."""

    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"


class ResponseFormat(StrEnum):
    """Provider-independent response representation."""

    TEXT = "text"
    JSON = "json"
    UNIFIED_DIFF = "unified_diff"
    STRUCTURED_PATCH = "structured_patch"


@dataclass(frozen=True, slots=True)
class PromptMessage:
    """One ordered logical prompt section."""

    section_id: str
    order: int
    role: PromptRole
    trust: PromptTrust
    content: str

    def __post_init__(self) -> None:
        _require_identifier(self.section_id, "section_id")
        if type(self.order) is not int:
            raise TypeError("order must be an integer")
        if self.order < 0:
            raise ValueError("order must not be negative")
        if not isinstance(self.role, PromptRole):
            raise TypeError("role must be a PromptRole")
        if not isinstance(self.trust, PromptTrust):
            raise TypeError("trust must be a PromptTrust")
        _require_text(self.content, "content")
        if self.role is PromptRole.SYSTEM and self.trust is PromptTrust.UNTRUSTED:
            raise ValueError("Untrusted content must not use the system role")


@dataclass(frozen=True, slots=True)
class ResponseContract:
    """Explicit structure and constraints expected from inference."""

    contract_id: str
    version: str
    purpose: str
    response_type: str
    output_format: ResponseFormat
    required_fields: tuple[str, ...]
    prohibited_operations: tuple[str, ...]
    error_behavior: str
    validation_instructions: tuple[str, ...] = ()
    maximum_response_bytes: int | None = None
    allow_commentary: bool = False

    def __post_init__(self) -> None:
        _require_identifier(self.contract_id, "contract_id")
        _require_text(self.version, "version")
        _require_text(self.purpose, "purpose")
        _require_identifier(self.response_type, "response_type")
        if not isinstance(self.output_format, ResponseFormat):
            raise TypeError("output_format must be a ResponseFormat")
        required_fields = _normalize_unique_text(self.required_fields, "required_fields")
        if not required_fields:
            raise ValueError("required_fields must not be empty")
        prohibited_operations = _normalize_unique_text(
            self.prohibited_operations,
            "prohibited_operations",
        )
        _require_text(self.error_behavior, "error_behavior")
        validation_instructions = _normalize_unique_text(
            self.validation_instructions,
            "validation_instructions",
        )
        if self.maximum_response_bytes is not None:
            if type(self.maximum_response_bytes) is not int:
                raise TypeError("maximum_response_bytes must be an integer")
            if self.maximum_response_bytes < 1:
                raise ValueError("maximum_response_bytes must be positive")
        if type(self.allow_commentary) is not bool:
            raise TypeError("allow_commentary must be a boolean")
        object.__setattr__(self, "required_fields", required_fields)
        object.__setattr__(self, "prohibited_operations", prohibited_operations)
        object.__setattr__(self, "validation_instructions", validation_instructions)


@dataclass(frozen=True, slots=True)
class DeliveryRequirements:
    """Capabilities and authorization required before provider transport."""

    required_capabilities: tuple[str, ...] = ()
    remote_delivery_allowed: bool = False
    contains_sensitive_context: bool = False
    structured_output_required: bool = False
    maximum_input_bytes: int | None = None
    maximum_output_bytes: int | None = None

    def __post_init__(self) -> None:
        capabilities = _normalize_unique_text(
            self.required_capabilities,
            "required_capabilities",
        )
        for field_name in (
            "remote_delivery_allowed",
            "contains_sensitive_context",
            "structured_output_required",
        ):
            if type(getattr(self, field_name)) is not bool:
                raise TypeError(f"{field_name} must be a boolean")
        for field_name in ("maximum_input_bytes", "maximum_output_bytes"):
            value = getattr(self, field_name)
            if value is not None:
                if type(value) is not int:
                    raise TypeError(f"{field_name} must be an integer")
                if value < 1:
                    raise ValueError(f"{field_name} must be positive")
        object.__setattr__(self, "required_capabilities", capabilities)


@dataclass(frozen=True, slots=True)
class PromptMeasurements:
    """Deterministic request size and contribution measurements."""

    byte_count: int
    character_count: int
    line_count: int
    estimated_tokens: int
    instruction_characters: int
    task_characters: int
    context_characters: int
    contract_characters: int
    context_item_count: int
    source_artifact_count: int
    sensitive_item_count: int
    remaining_provider_capacity: int | None = None

    def __post_init__(self) -> None:
        for field_name in self.__dataclass_fields__:
            value = getattr(self, field_name)
            if value is not None:
                if type(value) is not int:
                    raise TypeError("Prompt measurements must be integers")
                if value < 0:
                    raise ValueError("Prompt measurements must not be negative")
        if self.context_characters > self.character_count:
            raise ValueError("context_characters must not exceed character_count")
        if self.sensitive_item_count > self.context_item_count:
            raise ValueError("sensitive_item_count must not exceed context_item_count")


@dataclass(frozen=True, slots=True)
class InferenceRequest:
    """Complete provider-independent input for one inference operation."""

    request_id: InferenceRequestId
    task_id: TaskId
    context_bundle_id: ContextBundleId
    project_id: ProjectId
    project_fingerprint: ProjectFingerprint
    prompt_template_version: str
    messages: tuple[PromptMessage, ...]
    response_contract: ResponseContract
    delivery_requirements: DeliveryRequirements
    measurements: PromptMeasurements
    diagnostics: DiagnosticCollection
    created_at: datetime
    correlation_metadata: tuple[tuple[str, str], ...] = ()
    model_preference: str | None = None
    maximum_output_tokens: int | None = None
    temperature: float | None = None
    stop_conditions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for value, expected_type, field_name in (
            (self.request_id, InferenceRequestId, "request_id"),
            (self.task_id, TaskId, "task_id"),
            (self.context_bundle_id, ContextBundleId, "context_bundle_id"),
            (self.project_id, ProjectId, "project_id"),
            (self.project_fingerprint, ProjectFingerprint, "project_fingerprint"),
        ):
            if not isinstance(value, expected_type):
                raise TypeError(f"{field_name} must be a {expected_type.__name__}")
        _require_text(self.prompt_template_version, "prompt_template_version")
        messages = tuple(self.messages)
        if not messages:
            raise ValueError("Inference Request must contain messages")
        if any(not isinstance(message, PromptMessage) for message in messages):
            raise TypeError("messages must contain PromptMessage values")
        if tuple(message.order for message in messages) != tuple(range(len(messages))):
            raise ValueError("messages must have contiguous zero-based order")
        section_ids = tuple(message.section_id for message in messages)
        if len(set(section_ids)) != len(section_ids):
            raise ValueError("message section identifiers must be unique")
        if not isinstance(self.response_contract, ResponseContract):
            raise TypeError("response_contract must be a ResponseContract")
        if not isinstance(self.delivery_requirements, DeliveryRequirements):
            raise TypeError("delivery_requirements must be DeliveryRequirements")
        if not isinstance(self.measurements, PromptMeasurements):
            raise TypeError("measurements must be PromptMeasurements")
        if not isinstance(self.diagnostics, DiagnosticCollection):
            raise TypeError("diagnostics must be a DiagnosticCollection")
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be a datetime")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")

        metadata = tuple(self.correlation_metadata)
        metadata_keys = tuple(key for key, _ in metadata)
        if any(not key.strip() or not value.strip() for key, value in metadata):
            raise ValueError("correlation_metadata must contain non-empty strings")
        if len(set(metadata_keys)) != len(metadata_keys):
            raise ValueError("correlation_metadata keys must be unique")
        if self.model_preference is not None:
            _require_text(self.model_preference, "model_preference")
        if self.maximum_output_tokens is not None:
            if type(self.maximum_output_tokens) is not int:
                raise TypeError("maximum_output_tokens must be an integer")
            if self.maximum_output_tokens < 1:
                raise ValueError("maximum_output_tokens must be positive")
        if self.temperature is not None:
            if not isinstance(self.temperature, (int, float)):
                raise TypeError("temperature must be numeric")
            if not math.isfinite(self.temperature) or self.temperature < 0:
                raise ValueError("temperature must be finite and non-negative")
        stop_conditions = _normalize_unique_text(self.stop_conditions, "stop_conditions")
        object.__setattr__(self, "messages", messages)
        object.__setattr__(self, "correlation_metadata", tuple(sorted(metadata)))
        object.__setattr__(self, "stop_conditions", stop_conditions)
