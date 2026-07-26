"""Tests for CF-014 increment I037 eligibility and security filters."""

from __future__ import annotations

from datetime import UTC, datetime

from contextforge.domain import (
    ArtifactPath,
    ProjectFingerprint,
    new_artifact_id,
    new_index_id,
    new_inventory_id,
    new_project_id,
)
from contextforge.indexer import IndexedArtifact, IndexingState, ProjectIndex
from contextforge.retrieval import (
    ArtifactEligibilityRecord,
    CandidateEligibility,
    CandidateEligibilityFilter,
    CandidateOutcome,
    CandidateType,
    EligibilityPolicy,
    GeneratedArtifactPolicy,
    ProviderDeliveryMode,
    RetrievalCandidate,
    RetrievalEvidence,
)

FINGERPRINT = ProjectFingerprint("project_sha256_" + "5" * 64)


def setup() -> tuple[ProjectIndex, IndexedArtifact, RetrievalCandidate]:
    artifact = IndexedArtifact(
        new_artifact_id(),
        IndexingState.FULLY_INDEXED,
        "test",
        "1",
        FINGERPRINT,
        path=ArtifactPath("secret.py"),
    )
    index = ProjectIndex(
        new_index_id(),
        new_project_id(),
        new_inventory_id(),
        FINGERPRINT,
        "1",
        "test",
        (artifact,),
        datetime(2026, 7, 26, tzinfo=UTC),
    )
    candidate = RetrievalCandidate(
        "candidate_secret",
        CandidateType.FULL_ARTIFACT,
        "secret.py",
        f"artifact:{artifact.artifact_id}",
        (RetrievalEvidence("test", "test", "match", 1.0),),
        CandidateEligibility.ELIGIBLE,
        CandidateOutcome.SELECTED,
        10,
        artifact_id=artifact.artifact_id,
    )
    return index, artifact, candidate


def test_sensitive_candidate_is_prohibited_for_remote_delivery() -> None:
    index, artifact, candidate = setup()
    policy = EligibilityPolicy(provider_mode=ProviderDeliveryMode.REMOTE)

    result = CandidateEligibilityFilter(policy).filter(
        (candidate,),
        index,
        (ArtifactEligibilityRecord(artifact.artifact_id, sensitive=True),),
    )

    assert result.candidates[0].eligibility is CandidateEligibility.PROHIBITED
    assert result.candidates[0].outcome is CandidateOutcome.EXCLUDED
    assert [str(item.code) for item in result.diagnostics] == ["RETRIEVAL_SENSITIVE_EXCLUDED"]


def test_explicit_authorization_allows_sensitive_remote_candidate() -> None:
    index, artifact, candidate = setup()
    policy = EligibilityPolicy(
        ProviderDeliveryMode.REMOTE,
        authorized_sensitive_artifact_ids=(artifact.artifact_id,),
    )

    result = CandidateEligibilityFilter(policy).filter(
        (candidate,),
        index,
        (ArtifactEligibilityRecord(artifact.artifact_id, sensitive=True),),
    )

    assert result.candidates[0].eligibility is CandidateEligibility.ELIGIBLE
    assert result.candidates[0].outcome is CandidateOutcome.SELECTED
    assert "explicitly authorized" in result.candidates[0].evidence[-1].detail


def test_sensitive_candidate_can_remain_local_when_policy_allows() -> None:
    index, artifact, candidate = setup()

    result = CandidateEligibilityFilter().filter(
        (candidate,),
        index,
        (ArtifactEligibilityRecord(artifact.artifact_id, sensitive=True),),
    )

    assert result.candidates == (candidate,)


def test_binary_ignored_unsupported_or_unavailable_content_is_unavailable() -> None:
    for field_name in ("binary", "ignored", "unsupported"):
        index, artifact, candidate = setup()
        record = ArtifactEligibilityRecord(
            artifact.artifact_id,
            **{field_name: True},
        )
        result = CandidateEligibilityFilter().filter((candidate,), index, (record,))
        assert result.candidates[0].eligibility is CandidateEligibility.UNAVAILABLE


def test_generated_policy_can_exclude_or_deprioritize() -> None:
    index, artifact, candidate = setup()
    record = ArtifactEligibilityRecord(artifact.artifact_id, generated=True)
    excluded = CandidateEligibilityFilter(
        EligibilityPolicy(generated_policy=GeneratedArtifactPolicy.EXCLUDE)
    ).filter((candidate,), index, (record,))
    deprioritized = CandidateEligibilityFilter().filter(
        (candidate,),
        index,
        (record,),
    )

    assert excluded.candidates[0].eligibility is CandidateEligibility.INELIGIBLE
    assert deprioritized.candidates[0].eligibility is CandidateEligibility.ELIGIBLE
    assert deprioritized.candidates[0].evidence[-1].evidence_type == ("generated-artifact-penalty")


def test_candidate_outside_active_index_is_unavailable() -> None:
    index, _, candidate = setup()
    candidate = RetrievalCandidate(
        candidate.candidate_id,
        candidate.candidate_type,
        candidate.source_reference,
        candidate.content_reference,
        candidate.evidence,
        candidate.eligibility,
        candidate.outcome,
        candidate.estimated_bytes,
        artifact_id=new_artifact_id(),
    )

    result = CandidateEligibilityFilter().filter((candidate,), index)

    assert result.candidates[0].eligibility is CandidateEligibility.UNAVAILABLE
