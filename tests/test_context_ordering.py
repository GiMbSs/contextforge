"""Tests for deterministic Context Bundle ordering."""

from contextforge.context import ContextItem, ContextItemOrderer, ContextOrderingTier
from contextforge.retrieval import (
    CandidateType,
    RetrievalEvidence,
    SelectedContextItem,
    SelectionDecision,
    SelectionRationale,
    SelectionReason,
)


def _item(
    item_id: str,
    candidate_type: CandidateType,
    reason: SelectionReason,
    *,
    rank: int | None = None,
    dependency_path: tuple[str, ...] = (),
    reference: str | None = None,
) -> SelectedContextItem:
    candidate_id = f"candidate-{item_id}"
    rationale = SelectionRationale(
        candidate_id,
        SelectionDecision.SELECTED,
        reason,
        (RetrievalEvidence("semantic", "retrieval", item_id),),
        rank=rank,
    )
    return SelectedContextItem(
        item_id,
        candidate_id,
        None,
        reference or f"content:{item_id}",
        candidate_type,
        rationale,
        dependency_path=dependency_path,
    )


def test_orderer_applies_normative_semantic_tiers() -> None:
    supplementary = _item(
        "supplementary",
        CandidateType.DOCUMENTATION_SECTION,
        SelectionReason.LEXICAL_CONTENT_MATCH,
    )
    dependency = _item(
        "dependency",
        CandidateType.SYMBOL_DEFINITION,
        SelectionReason.DEPENDENCY_RELATIONSHIP,
        dependency_path=("relationship-1",),
    )
    structural = _item(
        "structural",
        CandidateType.RELATED_DECLARATION,
        SelectionReason.DECLARATION_RELATIONSHIP,
    )
    primary = _item(
        "primary",
        CandidateType.SYMBOL_DEFINITION,
        SelectionReason.REQUIRED_CONTEXT,
    )
    direct = _item(
        "direct",
        CandidateType.DOCUMENTATION_SECTION,
        SelectionReason.EXPLICIT_PATH_REFERENCE,
    )

    ordered = ContextItemOrderer().order_selected(
        (supplementary, dependency, structural, primary, direct)
    )

    assert tuple(item.context_item_id for item in ordered) == (
        "direct",
        "primary",
        "structural",
        "dependency",
        "supplementary",
    )


def test_direct_retrieval_semantics_override_candidate_form() -> None:
    item = _item(
        "direct-symbol",
        CandidateType.SYMBOL_DEFINITION,
        SelectionReason.EXPLICIT_SYMBOL_REFERENCE,
        dependency_path=("relationship-1",),
    )

    assert ContextItemOrderer().tier(item) is ContextOrderingTier.DIRECT_REFERENCE


def test_rank_is_the_first_tie_breaker_within_a_tier() -> None:
    lower_rank = _item(
        "second-reference",
        CandidateType.FULL_ARTIFACT,
        SelectionReason.REQUIRED_CONTEXT,
        rank=1,
        reference="z.py",
    )
    higher_rank = _item(
        "first-reference",
        CandidateType.FULL_ARTIFACT,
        SelectionReason.REQUIRED_CONTEXT,
        rank=2,
        reference="a.py",
    )

    ordered = ContextItemOrderer().order_selected((higher_rank, lower_rank))

    assert tuple(item.context_item_id for item in ordered) == (
        "second-reference",
        "first-reference",
    )


def test_stable_tie_breaking_is_independent_of_input_order() -> None:
    alpha = _item(
        "alpha",
        CandidateType.PROJECT_SUMMARY,
        SelectionReason.REQUIRED_CONTEXT,
        reference="A.py",
    )
    beta = _item(
        "beta",
        CandidateType.PROJECT_SUMMARY,
        SelectionReason.REQUIRED_CONTEXT,
        reference="b.py",
    )
    orderer = ContextItemOrderer()

    forward = orderer.order_selected((alpha, beta))
    reverse = orderer.order_selected((beta, alpha))

    assert forward == reverse == (alpha, beta)


def test_materialized_items_follow_the_same_retrieval_order() -> None:
    supplementary = ContextItem(
        _item(
            "supplementary",
            CandidateType.DOCUMENTATION_SECTION,
            SelectionReason.LEXICAL_CONTENT_MATCH,
        ),
        "documentation",
        "docs",
    )
    direct = ContextItem(
        _item(
            "direct",
            CandidateType.SOURCE_EXCERPT,
            SelectionReason.ERROR_LOCATION_REFERENCE,
        ),
        "source",
        "code",
    )

    ordered = ContextItemOrderer().order_materialized((supplementary, direct))

    assert tuple(item.context_item_id for item in ordered) == ("direct", "supplementary")
