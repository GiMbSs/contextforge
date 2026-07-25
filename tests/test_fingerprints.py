"""Tests for deterministic fingerprints from CF-014 increment I006."""

from dataclasses import FrozenInstanceError

import pytest

from contextforge.domain import (
    ConfigurationFingerprint,
    ContentFingerprint,
    FingerprintOrdering,
    LineEndingPolicy,
    ProjectFingerprint,
    ProposalFingerprint,
    fingerprint_configuration,
    fingerprint_content,
    fingerprint_project,
    fingerprint_proposal,
)


def test_same_semantic_content_has_same_fingerprint() -> None:
    first = fingerprint_content("ContextForge")
    second = fingerprint_content("ContextForge")

    assert first == second


def test_content_uses_canonical_unicode_and_utf8_encoding() -> None:
    composed = fingerprint_content("Contexto: café")
    decomposed = fingerprint_content("Contexto: cafe\u0301")

    assert composed == decomposed


def test_normalized_line_endings_are_semantically_equal() -> None:
    lf = fingerprint_content("first\nsecond\n")
    crlf = fingerprint_content("first\r\nsecond\r\n")
    cr = fingerprint_content("first\rsecond\r")

    assert lf == crlf == cr


def test_preserved_line_endings_affect_fingerprint() -> None:
    lf = fingerprint_content("first\nsecond\n", line_endings=LineEndingPolicy.PRESERVE)
    crlf = fingerprint_content("first\r\nsecond\r\n", line_endings=LineEndingPolicy.PRESERVE)

    assert lf != crlf


def test_order_changes_ordered_fingerprint() -> None:
    first = fingerprint_project(("src/a.py", "src/b.py"), ordering=FingerprintOrdering.ORDERED)
    reversed_order = fingerprint_project(
        ("src/b.py", "src/a.py"),
        ordering=FingerprintOrdering.ORDERED,
    )

    assert first != reversed_order


def test_order_does_not_change_unordered_fingerprint() -> None:
    first = fingerprint_project(("src/a.py", "src/b.py"), ordering=FingerprintOrdering.UNORDERED)
    reversed_order = fingerprint_project(
        ("src/b.py", "src/a.py"),
        ordering=FingerprintOrdering.UNORDERED,
    )

    assert first == reversed_order


def test_ordering_semantics_are_part_of_fingerprint() -> None:
    ordered = fingerprint_project(("src/a.py",), ordering=FingerprintOrdering.ORDERED)
    unordered = fingerprint_project(("src/a.py",), ordering=FingerprintOrdering.UNORDERED)

    assert ordered != unordered


def test_unordered_fingerprint_preserves_duplicate_values() -> None:
    one_value = fingerprint_configuration(("key=value",), ordering=FingerprintOrdering.UNORDERED)
    duplicate_value = fingerprint_configuration(
        ("key=value", "key=value"),
        ordering=FingerprintOrdering.UNORDERED,
    )

    assert one_value != duplicate_value


def test_component_boundaries_are_unambiguous() -> None:
    first = fingerprint_proposal(("ab", "c"), ordering=FingerprintOrdering.ORDERED)
    second = fingerprint_proposal(("a", "bc"), ordering=FingerprintOrdering.ORDERED)

    assert first != second


@pytest.mark.parametrize(
    ("fingerprint_type", "factory"),
    (
        (ContentFingerprint, lambda: fingerprint_content("content")),
        (
            ProjectFingerprint,
            lambda: fingerprint_project(("project",), ordering=FingerprintOrdering.ORDERED),
        ),
        (
            ConfigurationFingerprint,
            lambda: fingerprint_configuration(
                ("configuration",),
                ordering=FingerprintOrdering.UNORDERED,
            ),
        ),
        (
            ProposalFingerprint,
            lambda: fingerprint_proposal(("proposal",), ordering=FingerprintOrdering.ORDERED),
        ),
    ),
)
def test_fingerprint_round_trips_through_string(fingerprint_type: type, factory: object) -> None:
    fingerprint = factory()

    assert fingerprint_type.from_string(str(fingerprint)) == fingerprint


@pytest.mark.parametrize(
    "invalid_value",
    (
        "",
        "content_sha256_",
        "content_sha256_0",
        f"content_sha256_{'A' * 64}",
        f"content_sha256_{'0' * 63}",
        f"content_sha256_{'0' * 65}",
        f"content_md5_{'0' * 64}",
    ),
)
def test_invalid_fingerprint_is_rejected(invalid_value: str) -> None:
    with pytest.raises(ValueError):
        ContentFingerprint(invalid_value)


def test_fingerprint_is_immutable() -> None:
    fingerprint = fingerprint_content("content")

    with pytest.raises(FrozenInstanceError):
        fingerprint.value = f"content_sha256_{'0' * 64}"


def test_different_fingerprint_types_are_not_equal() -> None:
    digest = "0" * 64

    assert ContentFingerprint(f"content_sha256_{digest}") != ProjectFingerprint(
        f"project_sha256_{digest}"
    )
