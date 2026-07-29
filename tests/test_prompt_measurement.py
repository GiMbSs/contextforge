"""Tests for complete prompt measurement and hard limits."""

from datetime import UTC, datetime

import pytest

from contextforge.context import (
    ContextBundle,
    ContextBundleSerializer,
    ContextCoverage,
    ContextItem,
    ContextSection,
    ContextSectionKind,
    ContextStatistics,
)
from contextforge.diagnostics import DiagnosticCollection
from contextforge.domain import (
    FingerprintOrdering,
    fingerprint_project,
    new_artifact_id,
    new_context_bundle_id,
    new_project_id,
    new_retrieval_id,
    new_task_id,
)
from contextforge.domain.tasks import RequestedOutput, TaskKind, TaskSpecification
from contextforge.prompt import (
    PromptLimitExceededError,
    PromptLimits,
    PromptMeasurer,
    PromptTemplateAssembler,
    PromptTemplateAssembly,
    analysis_response_contract,
    estimate_text_tokens,
)
from contextforge.retrieval import (
    CandidateType,
    RetrievalEvidence,
    SelectedContextItem,
    SelectionDecision,
    SelectionRationale,
    SelectionReason,
)


def _setup() -> tuple[ContextBundle, PromptTemplateAssembly]:
    task = TaskSpecification(
        new_task_id(),
        "Explain main.",
        TaskKind.EXPLAIN,
        RequestedOutput.ANALYSIS,
    )
    artifact_id = new_artifact_id()
    rationale = SelectionRationale(
        "candidate-main",
        SelectionDecision.SELECTED,
        SelectionReason.EXPLICIT_PATH_REFERENCE,
        (RetrievalEvidence("explicit", "task", "main.py"),),
    )
    selected = SelectedContextItem(
        "item-main",
        "candidate-main",
        artifact_id,
        "artifact:main",
        CandidateType.FULL_ARTIFACT,
        rationale,
        sensitivity_classification="sensitive",
    )
    item = ContextItem(selected, "artifact:main", "print('olá')\n")
    bundle = ContextBundle(
        new_context_bundle_id(),
        task.task_id,
        new_retrieval_id(),
        new_project_id(),
        fingerprint_project(("project",), ordering=FingerprintOrdering.ORDERED),
        (item,),
        ("item-main",),
        (
            ContextSection(
                "section-main",
                ContextSectionKind.EXPLICIT_REFERENCE,
                "Main",
                ("item-main",),
                0,
            ),
        ),
        ContextStatistics(
            item_count=1,
            artifact_count=1,
            character_count=len(item.content),
            byte_count=len(item.content.encode()),
            line_count=2,
        ),
        ContextCoverage(),
        DiagnosticCollection(),
        "1",
        "builder-v1",
        datetime(2026, 7, 26, tzinfo=UTC),
    )
    assembly = PromptTemplateAssembler().assemble(
        task,
        bundle,
        ContextBundleSerializer().serialize(bundle),
        analysis_response_contract(),
    )
    return bundle, assembly


def test_measurer_accounts_for_complete_prompt_and_contributions() -> None:
    bundle, assembly = _setup()

    measurements = PromptMeasurer().measure(assembly, bundle)

    assert measurements.byte_count > measurements.character_count
    assert measurements.instruction_characters > 0
    assert measurements.task_characters > 0
    assert measurements.context_characters > 0
    assert measurements.contract_characters > 0
    assert measurements.context_item_count == 1
    assert measurements.source_artifact_count == 1
    assert measurements.sensitive_item_count == 1


def test_remaining_provider_capacity_is_reported() -> None:
    bundle, assembly = _setup()
    baseline = PromptMeasurer().measure(assembly, bundle)
    capacity = baseline.estimated_tokens + 25

    measurements = PromptMeasurer().measure(
        assembly,
        bundle,
        PromptLimits(provider_token_capacity=capacity),
    )

    assert measurements.remaining_provider_capacity == 25


def test_oversized_request_fails_with_actionable_diagnostic() -> None:
    bundle, assembly = _setup()

    with pytest.raises(PromptLimitExceededError) as captured:
        PromptMeasurer().measure(
            assembly,
            bundle,
            PromptLimits(maximum_bytes=1),
        )

    diagnostic = next(iter(captured.value.diagnostics))
    assert str(diagnostic.code) == "PROMPT_SIZE_EXCEEDED"
    assert "Complete prompt" in diagnostic.message
    assert diagnostic.guidance is not None
    assert "not truncated" in diagnostic.guidance


def test_strictest_limits_are_all_evaluated() -> None:
    bundle, assembly = _setup()

    with pytest.raises(PromptLimitExceededError) as captured:
        PromptMeasurer().measure(
            assembly,
            bundle,
            PromptLimits(
                maximum_bytes=1,
                maximum_characters=1,
                maximum_estimated_tokens=1,
                provider_token_capacity=1,
            ),
        )

    assert len(captured.value.diagnostics) == 4


def test_canonical_token_estimator_has_explicit_empty_semantics() -> None:
    assert estimate_text_tokens("") == 0
    assert estimate_text_tokens("abcd") == 2

    with pytest.raises(TypeError, match="string"):
        estimate_text_tokens(1)  # type: ignore[arg-type]
