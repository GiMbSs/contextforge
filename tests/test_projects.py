"""Tests for project identity and immutable project state."""

from dataclasses import FrozenInstanceError

import pytest

from contextforge.domain import (
    ProjectFingerprint,
    ProjectIdentity,
    ProjectState,
    new_project_id,
)


def test_project_identity_uses_stable_identifier_for_equality() -> None:
    project_id = new_project_id()

    first = ProjectIdentity(project_id, "ContextForge")
    renamed = ProjectIdentity(project_id, "ContextForge Core")

    assert first == renamed
    assert hash(first) == hash(renamed)


def test_project_identity_rejects_empty_display_name() -> None:
    with pytest.raises(ValueError, match="display name"):
        ProjectIdentity(new_project_id(), "  ")


def test_project_state_is_immutable() -> None:
    state = ProjectState(
        ProjectIdentity(new_project_id(), "ContextForge"),
        ProjectFingerprint(f"project_sha256_{'0' * 64}"),
    )

    with pytest.raises(FrozenInstanceError):
        state.fingerprint = ProjectFingerprint(  # type: ignore[misc]
            f"project_sha256_{'1' * 64}"
        )
