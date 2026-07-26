"""Property-based invariants for high-risk deterministic boundaries."""

import json
import string
from xml.etree import ElementTree

from hypothesis import given
from hypothesis import strategies as st

from contextforge.context.serialization import _text_element
from contextforge.domain import (
    ArtifactPath,
    FingerprintOrdering,
    ProjectFingerprint,
    fingerprint_project,
)
from contextforge.patch import (
    PatchConflictValidator,
    PatchConsistencyEvidence,
    PatchOperation,
    ProposedChange,
    StructuredPatchParser,
    ValidatedResponseEnvelope,
)
from contextforge.prompt import PatchPayloadFormat
from contextforge.retrieval import (
    CandidateBudgetEstimate,
    CandidateEligibility,
    CandidateOutcome,
    CandidateScore,
    CandidateType,
    ContextBudget,
    ContextBudgetPlanner,
    RetrievalCandidate,
    RetrievalEvidence,
    RetrievalScoringModel,
    ScoreComponent,
    ScoreContribution,
)

SAFE_SEGMENT = st.text(
    alphabet=string.ascii_letters + string.digits + "-_",
    min_size=1,
    max_size=12,
).filter(lambda value: value not in {".", ".."})
SAFE_PATH = st.lists(SAFE_SEGMENT, min_size=1, max_size=5).map("/".join)


@given(st.lists(SAFE_SEGMENT, min_size=1, max_size=5))
def test_path_normalization_is_idempotent(segments: list[str]) -> None:
    mixed = "/./".join(segments).replace("/", "\\", 1)
    first = ArtifactPath(mixed)

    assert ArtifactPath(str(first)) == first
    assert first.parts == tuple(segments)


@given(st.lists(st.text(max_size=30), max_size=20))
def test_unordered_fingerprint_is_stable_under_reversal(values: list[str]) -> None:
    first = fingerprint_project(values, ordering=FingerprintOrdering.UNORDERED)
    second = fingerprint_project(reversed(values), ordering=FingerprintOrdering.UNORDERED)

    assert first == second


@given(
    st.text(
        alphabet=st.characters(
            blacklist_categories=("Cc", "Cs"),
            whitelist_characters="\t\n",
        ),
        max_size=200,
    )
)
def test_untrusted_xml_text_round_trips_without_structure_injection(content: str) -> None:
    root = ElementTree.Element("root")
    _text_element(root, "content", content)

    reparsed = ElementTree.fromstring(ElementTree.tostring(root, encoding="unicode"))

    assert reparsed.findtext("content", default="") == content
    assert len(reparsed.findall("content")) == 1


def _candidate(identifier: str, weight: float) -> RetrievalCandidate:
    return RetrievalCandidate(
        identifier,
        CandidateType.SOURCE_EXCERPT,
        identifier,
        f"content:{identifier}",
        (RetrievalEvidence("lexical-match", "property", identifier, weight),),
        CandidateEligibility.ELIGIBLE,
        CandidateOutcome.EXCLUDED,
        10,
        1,
    )


@given(st.lists(st.integers(min_value=0, max_value=100), min_size=1, max_size=20))
def test_retrieval_ordering_is_independent_of_input_order(weights: list[int]) -> None:
    candidates = tuple(
        _candidate(f"candidate_{index:03d}", weight / 100) for index, weight in enumerate(weights)
    )
    model = RetrievalScoringModel()

    forward = model.score(candidates)
    reverse = model.score(tuple(reversed(candidates)))

    assert tuple(score.candidate_id for score in forward.scores) == tuple(
        score.candidate_id for score in reverse.scores
    )


def _score(identifier: str, rank: int) -> CandidateScore:
    return CandidateScore(
        identifier,
        tuple(ScoreContribution(component, 0.0, 1.0, 0.0, 0) for component in ScoreComponent),
        0.0,
        0.0,
        rank,
    )


@given(
    limit=st.integers(min_value=1, max_value=500),
    sizes=st.lists(st.integers(min_value=0, max_value=100), max_size=15),
)
def test_budget_usage_never_exceeds_hard_byte_limit(limit: int, sizes: list[int]) -> None:
    candidates = tuple(_candidate(f"candidate_{index:03d}", 1.0) for index, _ in enumerate(sizes))
    candidates = tuple(
        RetrievalCandidate(
            candidate.candidate_id,
            candidate.candidate_type,
            candidate.source_reference,
            candidate.content_reference,
            candidate.evidence,
            candidate.eligibility,
            candidate.outcome,
            size,
            candidate.estimated_tokens,
        )
        for candidate, size in zip(candidates, sizes, strict=True)
    )
    result = ContextBudgetPlanner().select(
        candidates,
        tuple(_score(candidate.candidate_id, rank) for rank, candidate in enumerate(candidates, 1)),
        ContextBudget(max_bytes=limit),
        estimates=tuple(
            CandidateBudgetEstimate(candidate.candidate_id, 0) for candidate in candidates
        ),
    )

    assert result.usage.bytes <= limit
    assert set(result.selected_candidate_ids) <= {
        candidate.candidate_id for candidate in candidates
    }


@given(path=SAFE_PATH, content=st.text(max_size=200))
def test_structured_create_patch_preserves_generated_content(path: str, content: str) -> None:
    change = {
        "change_id": "change-1",
        "explanation": "Create generated content.",
        "new_content": content,
        "operation": "create",
        "path": path,
    }
    outer = {
        "affected_files": [path],
        "assumptions": [],
        "changes": [change],
        "patch_format": "structured_changes",
        "patch_payload": json.dumps({"changes": [change]}),
        "response_type": "patch_proposal",
        "summary": "Create file.",
        "warnings": [],
    }
    envelope = ValidatedResponseEnvelope(
        "contract",
        "v1",
        json.dumps(outer),
        "patch_proposal",
        PatchPayloadFormat.STRUCTURED_CHANGES,
        (ArtifactPath(path),),
    )

    (parsed,) = StructuredPatchParser().parse(envelope)

    assert parsed.path == ArtifactPath(path)
    assert parsed.patch_payload == content


@given(st.lists(SAFE_PATH, min_size=1, max_size=15, unique=True))
def test_proposal_consistency_returns_canonical_path_order(paths: list[str]) -> None:
    changes = tuple(
        ProposedChange(
            f"change-{index}",
            ArtifactPath(path),
            PatchOperation.CREATE,
            "Create file.",
            patch_payload="content",
        )
        for index, path in enumerate(reversed(paths))
    )
    fingerprint = ProjectFingerprint("project_sha256_" + "a" * 64)
    evidence = PatchConsistencyEvidence(
        tuple(ArtifactPath(path) for path in paths),
        fingerprint,
        fingerprint,
    )

    ordered = PatchConflictValidator().validate(changes, evidence)

    assert tuple(str(change.path) for change in ordered) == tuple(
        sorted(str(ArtifactPath(path)) for path in paths)
    )
