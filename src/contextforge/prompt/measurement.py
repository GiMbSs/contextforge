"""Complete prompt measurement and hard-limit enforcement."""

from __future__ import annotations

from dataclasses import dataclass

from contextforge.context import ContextBundle
from contextforge.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticCollection,
    DiagnosticSeverity,
)
from contextforge.prompt.assembly import PromptTemplateAssembly
from contextforge.prompt.models import PromptMeasurements

PROMPT_MEASUREMENT_VERSION = "prompt-measurement-v1"


@dataclass(frozen=True, slots=True)
class PromptLimits:
    """Hard request limits resolved before provider invocation."""

    maximum_bytes: int | None = None
    maximum_characters: int | None = None
    maximum_estimated_tokens: int | None = None
    provider_token_capacity: int | None = None

    def __post_init__(self) -> None:
        for field_name in self.__dataclass_fields__:
            value = getattr(self, field_name)
            if value is not None:
                if type(value) is not int:
                    raise TypeError(f"{field_name} must be an integer")
                if value < 1:
                    raise ValueError(f"{field_name} must be positive")


class PromptLimitExceededError(ValueError):
    """A complete prompt exceeded at least one effective hard limit."""

    def __init__(
        self,
        measurements: PromptMeasurements,
        diagnostics: DiagnosticCollection,
    ) -> None:
        super().__init__("Inference Request exceeds an effective prompt limit")
        self.measurements = measurements
        self.diagnostics = diagnostics


@dataclass(frozen=True, slots=True)
class PromptMeasurer:
    """Measure complete logical prompts using a conservative approximation."""

    version: str = PROMPT_MEASUREMENT_VERSION

    def measure(
        self,
        assembly: PromptTemplateAssembly,
        context_bundle: ContextBundle,
        limits: PromptLimits | None = None,
    ) -> PromptMeasurements:
        """Measure every prompt section and fail closed on overflow."""
        if not isinstance(assembly, PromptTemplateAssembly):
            raise TypeError("assembly must be a PromptTemplateAssembly")
        if not isinstance(context_bundle, ContextBundle):
            raise TypeError("context_bundle must be a ContextBundle")
        if limits is None:
            limits = PromptLimits()
        if not isinstance(limits, PromptLimits):
            raise TypeError("limits must be PromptLimits")

        complete_payload = "\n".join(
            "\n".join(
                (
                    f"<message section={message.section_id} role={message.role.value} "
                    f"trust={message.trust.value}>",
                    message.content,
                    "</message>",
                )
            )
            for message in assembly.messages
        )
        character_count = len(complete_payload)
        estimated_tokens = max(1, (character_count * 11 + 39) // 40)
        sections = {message.section_id: message.content for message in assembly.messages}
        artifact_ids = {
            item.selected_item.artifact_id
            for item in context_bundle.items
            if item.selected_item.artifact_id is not None
        }
        provider_capacity = limits.provider_token_capacity
        remaining_capacity = (
            max(provider_capacity - estimated_tokens, 0) if provider_capacity is not None else None
        )
        measurements = PromptMeasurements(
            byte_count=len(complete_payload.encode("utf-8")),
            character_count=character_count,
            line_count=complete_payload.count("\n") + 1,
            estimated_tokens=estimated_tokens,
            instruction_characters=(
                len(sections["system-operating-rules"]) + len(sections["context-usage-rules"])
            ),
            task_characters=len(sections["task-specification"]),
            context_characters=len(sections["serialized-context-bundle"]),
            contract_characters=len(sections["output-response-contract"]),
            context_item_count=len(context_bundle.items),
            source_artifact_count=len(artifact_ids),
            sensitive_item_count=sum(
                item.selected_item.sensitivity_classification == "sensitive"
                for item in context_bundle.items
            ),
            remaining_provider_capacity=remaining_capacity,
        )
        diagnostics = _limit_diagnostics(measurements, limits)
        if diagnostics:
            raise PromptLimitExceededError(
                measurements,
                DiagnosticCollection(tuple(diagnostics)),
            )
        return measurements


def _limit_diagnostics(
    measurements: PromptMeasurements,
    limits: PromptLimits,
) -> list[Diagnostic]:
    comparisons = (
        (measurements.byte_count, limits.maximum_bytes, "bytes"),
        (
            measurements.character_count,
            limits.maximum_characters,
            "characters",
        ),
        (
            measurements.estimated_tokens,
            limits.maximum_estimated_tokens,
            "estimated tokens",
        ),
        (
            measurements.estimated_tokens,
            limits.provider_token_capacity,
            "provider token capacity",
        ),
    )
    return [
        Diagnostic(
            DiagnosticCode("PROMPT_SIZE_EXCEEDED"),
            DiagnosticSeverity.ERROR,
            f"Complete prompt exceeds {label}: {actual} > {maximum}.",
            "prompt-builder",
            guidance=(
                "Request a smaller Context Bundle or select a provider with sufficient "
                "input capacity; mandatory content was not truncated."
            ),
            metadata=(("actual", actual), ("limit", maximum), ("measurement", label)),
        )
        for actual, maximum, label in comparisons
        if maximum is not None and actual > maximum
    ]
