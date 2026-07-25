"""Tests for Task Specification from CF-014 increment I009."""

from dataclasses import FrozenInstanceError

import pytest

from contextforge.domain import (
    RequestedOutput,
    TaskKind,
    TaskSpecification,
    new_task_id,
)


def make_task(
    task_text: str = "Explain the context retrieval pipeline.",
    *,
    constraints: tuple[str, ...] = (),
    metadata: tuple[tuple[str, object], ...] = (),
) -> TaskSpecification:
    return TaskSpecification(
        task_id=new_task_id(),
        task_text=task_text,
        task_kind=TaskKind.EXPLAIN,
        requested_output=RequestedOutput.ANALYSIS,
        constraints=constraints,
        metadata=metadata,
    )


def test_multiline_unicode_task_is_preserved_exactly() -> None:
    task_text = "  Explique o símbolo `ContextBundle`.\n\nNão altere arquivos. 🚀  \n"

    task = make_task(task_text)

    assert task.task_text == task_text


@pytest.mark.parametrize("task_text", ("", " ", "\n\t"))
def test_empty_task_text_is_rejected(task_text: str) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        make_task(task_text)


def test_task_round_trips_without_rewriting_original_text() -> None:
    original = make_task(
        "  Corrija `café.py`.\r\nPreserve a API pública.  ",
        constraints=("Modify only café.py", "Avoid new dependencies"),
        metadata=(("origin", "terminal"), ("attempt", 1)),
    )

    restored = TaskSpecification.from_dict(original.to_dict())

    assert restored == original
    assert restored.task_text == original.task_text
    assert restored.to_dict() == original.to_dict()


def test_metadata_serialization_is_deterministic() -> None:
    task_id = new_task_id()
    first = TaskSpecification(
        task_id=task_id,
        task_text="Analyze the project.",
        task_kind=TaskKind.ANALYZE,
        requested_output=RequestedOutput.STRUCTURED_DIAGNOSTIC,
        metadata=(("zeta", 2), ("alpha", 1)),
    )
    second = TaskSpecification(
        task_id=task_id,
        task_text="Analyze the project.",
        task_kind=TaskKind.ANALYZE,
        requested_output=RequestedOutput.STRUCTURED_DIAGNOSTIC,
        metadata=(("alpha", 1), ("zeta", 2)),
    )

    assert first.to_dict() == second.to_dict()


def test_task_entity_equality_uses_task_identity() -> None:
    task_id = new_task_id()
    first = TaskSpecification(
        task_id=task_id,
        task_text="Original text.",
        task_kind=TaskKind.UNKNOWN,
        requested_output=RequestedOutput.ANALYSIS,
    )
    second = TaskSpecification(
        task_id=task_id,
        task_text="Different representation.",
        task_kind=TaskKind.MODIFY,
        requested_output=RequestedOutput.PATCH_PROPOSAL,
    )

    assert first == second
    assert hash(first) == hash(second)


def test_different_task_identities_are_not_equal() -> None:
    assert make_task() != make_task()


@pytest.mark.parametrize("constraint", ("", " ", "\n"))
def test_empty_constraint_is_rejected(constraint: str) -> None:
    with pytest.raises(ValueError, match="constraints must not be empty"):
        make_task(constraints=(constraint,))


def test_duplicate_metadata_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        make_task(metadata=(("source", "cli"), ("source", "file")))


def test_non_finite_metadata_is_rejected() -> None:
    with pytest.raises(ValueError, match="finite"):
        make_task(metadata=(("score", float("nan")),))


def test_mutable_metadata_value_is_rejected() -> None:
    with pytest.raises(ValueError, match="scalar"):
        make_task(metadata=(("nested", {"mutable": True}),))


def test_direct_construction_rejects_untyped_kind() -> None:
    with pytest.raises(TypeError, match="TaskKind"):
        TaskSpecification(
            task_id=new_task_id(),
            task_text="Analyze.",
            task_kind="analyze",
            requested_output=RequestedOutput.ANALYSIS,
        )


@pytest.mark.parametrize(
    "serialized",
    (
        {},
        {
            "constraints": "not-a-list",
            "metadata": {},
            "requested_output": "analysis",
            "task_id": "task_0123456789abcdef0123456789abcdef",
            "task_kind": "analyze",
            "task_text": "Analyze.",
        },
        {
            "constraints": [],
            "metadata": [],
            "requested_output": "analysis",
            "task_id": "task_0123456789abcdef0123456789abcdef",
            "task_kind": "analyze",
            "task_text": "Analyze.",
        },
    ),
)
def test_malformed_serialized_task_is_rejected(serialized: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        TaskSpecification.from_dict(serialized)


def test_task_specification_is_immutable() -> None:
    task = make_task()

    with pytest.raises(FrozenInstanceError):
        task.task_text = "Changed."
