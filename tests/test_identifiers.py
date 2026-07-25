"""Tests for immutable domain identifiers from CF-014 increment I005."""

from collections.abc import Callable
from dataclasses import FrozenInstanceError

import pytest

from contextforge.domain import (
    ApprovalId,
    ContextBundleId,
    ExecutionId,
    IndexId,
    InferenceRequestId,
    InferenceResponseId,
    InventoryId,
    PatchProposalId,
    ProjectId,
    RetrievalId,
    TaskId,
    new_approval_id,
    new_context_bundle_id,
    new_execution_id,
    new_index_id,
    new_inference_request_id,
    new_inference_response_id,
    new_inventory_id,
    new_patch_proposal_id,
    new_project_id,
    new_retrieval_id,
    new_task_id,
)

IDENTIFIER_CASES = (
    (ProjectId, new_project_id),
    (ExecutionId, new_execution_id),
    (TaskId, new_task_id),
    (InventoryId, new_inventory_id),
    (IndexId, new_index_id),
    (RetrievalId, new_retrieval_id),
    (ContextBundleId, new_context_bundle_id),
    (InferenceRequestId, new_inference_request_id),
    (InferenceResponseId, new_inference_response_id),
    (PatchProposalId, new_patch_proposal_id),
    (ApprovalId, new_approval_id),
)


@pytest.mark.parametrize(("identifier_type", "factory"), IDENTIFIER_CASES)
def test_generated_identifier_round_trips_through_string(
    identifier_type: type,
    factory: Callable[[], object],
) -> None:
    identifier = factory()
    serialized = str(identifier)

    assert identifier_type.from_string(serialized) == identifier
    assert serialized.startswith(f"{identifier_type.prefix}_")


@pytest.mark.parametrize(("identifier_type", "_factory"), IDENTIFIER_CASES)
@pytest.mark.parametrize(
    "invalid_value",
    (
        "",
        " ",
        "missing-prefix",
        "project_",
        "project_0123456789ABCDEF0123456789ABCDEF",
        "project_0123456789abcdef0123456789abcde",
        "project_0123456789abcdef0123456789abcdef0",
        "project_0123456789abcdef0123456789abcdeg",
    ),
)
def test_invalid_identifier_is_rejected(
    identifier_type: type,
    _factory: Callable[[], object],
    invalid_value: str,
) -> None:
    with pytest.raises(ValueError):
        identifier_type(invalid_value)


def test_identifier_is_immutable() -> None:
    identifier = new_project_id()

    with pytest.raises(FrozenInstanceError):
        identifier.value = "project_0123456789abcdef0123456789abcdef"


def test_different_identifier_types_are_not_equal() -> None:
    value = "0" * 32

    assert ProjectId(f"project_{value}") != ExecutionId(f"execution_{value}")


def test_factories_generate_distinct_identifiers() -> None:
    assert new_project_id() != new_project_id()
