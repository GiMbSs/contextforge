"""Tests for normative Context Bundle validation."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime

from contextforge.context import (
    ContextBundle,
    ContextBundleValidator,
    ContextCoverage,
    ContextItem,
    ContextSection,
    ContextSectionKind,
    ContextStatistics,
)
from contextforge.diagnostics import DiagnosticCollection
from contextforge.domain import (
    ArtifactPath,
    FingerprintOrdering,
    fingerprint_project,
    new_artifact_id,
    new_context_bundle_id,
    new_index_id,
    new_project_id,
    new_retrieval_id,
    new_task_id,
)
from contextforge.indexer import SourceLocation
from contextforge.retrieval import (
    CandidateEligibility,
    CandidateOutcome,
    CandidateType,
    ContextBudget,
    RetrievalCandidate,
    RetrievalEvidence,
    RetrievalResult,
    RetrievalStatistics,
    RetrievalStatus,
    SelectedContextItem,
    SelectionDecision,
    SelectionRationale,
    SelectionReason,
)

NOW = datetime(2026, 7, 26, tzinfo=UTC)


def _setup(
    *,
    budget: ContextBudget | None = None,
    sensitivity: str = "standard",
) -> tuple[ContextBundle, RetrievalResult]:
    content = "alpha"
    fingerprint = f"sha256:{hashlib.sha256(content.encode()).hexdigest()}"
    artifact_id = new_artifact_id()
    task_id = new_task_id()
    retrieval_id = new_retrieval_id()
    project_fingerprint = fingerprint_project(("project",), ordering=FingerprintOrdering.ORDERED)
    evidence = (RetrievalEvidence("explicit", "task", "alpha"),)
    rationale = SelectionRationale(
        "candidate-alpha",
        SelectionDecision.SELECTED,
        SelectionReason.EXPLICIT_PATH_REFERENCE,
        evidence,
        rank=1,
    )
    candidate = RetrievalCandidate(
        "candidate-alpha",
        CandidateType.SOURCE_EXCERPT,
        "src/alpha.py",
        "artifact:alpha",
        evidence,
        CandidateEligibility.ELIGIBLE,
        CandidateOutcome.SELECTED,
        len(content),
        2,
        artifact_id,
        SourceLocation(artifact_id, 1, 1, 1, 5),
        rationale,
    )
    selected = SelectedContextItem(
        "item-alpha",
        candidate.candidate_id,
        artifact_id,
        candidate.content_reference,
        candidate.candidate_type,
        rationale,
        candidate.location,
        2,
        fingerprint,
        estimated_bytes=len(content),
        estimated_characters=len(content),
        sensitivity_classification=sensitivity,
    )
    applied_budget = budget or ContextBudget(max_bytes=10, max_items=1)
    result = RetrievalResult(
        retrieval_id,
        task_id,
        new_index_id(),
        project_fingerprint,
        ("retrieval-v1",),
        (candidate,),
        (selected,),
        (rationale,),
        applied_budget,
        DiagnosticCollection(),
        RetrievalStatistics(
            candidates_generated=1,
            candidates_evaluated=1,
            excerpts_selected=1,
            estimated_selected_tokens=2,
        ),
        RetrievalStatus.COMPLETE,
        NOW,
    )
    item = ContextItem(
        selected,
        selected.content_reference,
        content,
        ArtifactPath("src/alpha.py"),
        fingerprint,
    )
    bundle = ContextBundle(
        new_context_bundle_id(),
        task_id,
        retrieval_id,
        new_project_id(),
        project_fingerprint,
        (item,),
        (item.context_item_id,),
        (
            ContextSection(
                "section-primary",
                ContextSectionKind.PRIMARY_IMPLEMENTATION,
                "Primary",
                (item.context_item_id,),
                0,
            ),
        ),
        ContextStatistics(
            item_count=1,
            excerpt_count=1,
            character_count=5,
            byte_count=5,
            line_count=1,
            estimated_tokens=2,
        ),
        ContextCoverage(),
        DiagnosticCollection(),
        "1",
        "builder-v1",
        NOW,
    )
    return bundle, result


def _codes(bundle: ContextBundle, result: RetrievalResult) -> list[str]:
    validation = ContextBundleValidator().validate(bundle, result)
    return [str(diagnostic.code) for diagnostic in validation.diagnostics]


def test_valid_bundle_has_no_validation_diagnostics() -> None:
    bundle, result = _setup()

    validation = ContextBundleValidator().validate(bundle, result)

    assert validation.is_valid
    assert tuple(validation.diagnostics) == ()


def test_validator_detects_membership_and_traceability_mismatch() -> None:
    bundle, result = _setup()
    changed_rationale = replace(
        result.rationales[0],
        candidate_id="candidate-beta",
    )
    changed_candidate = replace(
        result.candidates[0],
        candidate_id="candidate-beta",
        rationale=changed_rationale,
    )
    changed_selected = replace(
        result.selected_items[0],
        context_item_id="item-beta",
        candidate_id="candidate-beta",
        rationale=changed_rationale,
    )
    mismatched_result = replace(
        result,
        candidates=(changed_candidate,),
        selected_items=(changed_selected,),
        rationales=(changed_rationale,),
    )

    codes = _codes(bundle, mismatched_result)

    assert "CONTEXT_MEMBERSHIP_MISMATCH" in codes


def test_validator_detects_duplicate_source_spans() -> None:
    bundle, result = _setup()
    duplicate = replace(
        bundle.items[0],
        selected_item=replace(
            bundle.items[0].selected_item,
            context_item_id="item-duplicate",
            candidate_id="candidate-duplicate",
            rationale=replace(
                bundle.items[0].selected_item.rationale,
                candidate_id="candidate-duplicate",
            ),
        ),
    )
    duplicated_bundle = replace(
        bundle,
        items=(*bundle.items, duplicate),
        source_selected_item_ids=("item-alpha", "item-duplicate"),
        sections=(
            replace(
                bundle.sections[0],
                item_ids=("item-alpha", "item-duplicate"),
            ),
        ),
        statistics=replace(
            bundle.statistics,
            item_count=2,
            character_count=10,
            byte_count=10,
            line_count=2,
        ),
    )

    assert "CONTEXT_DUPLICATE_SOURCE_SPAN" in _codes(duplicated_bundle, result)


def test_validator_requires_matching_verified_fingerprint() -> None:
    bundle, result = _setup()
    unverified = replace(bundle.items[0], verified_source_fingerprint=None)
    changed = replace(bundle, items=(unverified,))

    assert "CONTEXT_SOURCE_FINGERPRINT_MISMATCH" in _codes(changed, result)


def test_validator_enforces_all_budget_dimensions() -> None:
    bundle, result = _setup(budget=ContextBudget(max_bytes=4, max_item_bytes=4))

    codes = _codes(bundle, result)

    assert "CONTEXT_BUDGET_EXCEEDED" in codes
    assert "CONTEXT_ITEM_BUDGET_EXCEEDED" in codes


def test_validator_requires_sensitivity_annotation() -> None:
    bundle, result = _setup(sensitivity="unclassified")

    assert "CONTEXT_SENSITIVITY_MISSING" in _codes(bundle, result)
