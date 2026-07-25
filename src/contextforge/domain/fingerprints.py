"""Deterministic fingerprints for semantic ContextForge state."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, Self


class FingerprintOrdering(StrEnum):
    """Declare whether collection order contributes to semantic identity."""

    ORDERED = "ordered"
    UNORDERED = "unordered"


class LineEndingPolicy(StrEnum):
    """Declare how text line endings contribute to semantic identity."""

    NORMALIZE_LF = "normalize_lf"
    PRESERVE = "preserve"


@dataclass(frozen=True, slots=True)
class _Fingerprint:
    """Immutable SHA-256 fingerprint with a domain-specific prefix."""

    value: str
    prefix: ClassVar[str]

    def __post_init__(self) -> None:
        pattern = rf"{re.escape(self.prefix)}_sha256_[0-9a-f]{{64}}"
        if re.fullmatch(pattern, self.value) is None:
            raise ValueError(
                f"{type(self).__name__} must contain its type prefix, 'sha256', "
                "and 64 lowercase hexadecimal characters"
            )

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, value: str) -> Self:
        """Deserialize and validate a fingerprint from its canonical string."""
        return cls(value)


@dataclass(frozen=True, slots=True)
class ContentFingerprint(_Fingerprint):
    """Fingerprint of normalized textual content."""

    prefix: ClassVar[str] = "content"


@dataclass(frozen=True, slots=True)
class ProjectFingerprint(_Fingerprint):
    """Fingerprint of semantic project state."""

    prefix: ClassVar[str] = "project"


@dataclass(frozen=True, slots=True)
class ConfigurationFingerprint(_Fingerprint):
    """Fingerprint of effective semantic configuration."""

    prefix: ClassVar[str] = "configuration"


@dataclass(frozen=True, slots=True)
class ProposalFingerprint(_Fingerprint):
    """Fingerprint of immutable proposed changes."""

    prefix: ClassVar[str] = "proposal"


def _normalize_text(value: str, line_endings: LineEndingPolicy) -> str:
    normalized = unicodedata.normalize("NFC", value)
    if line_endings is LineEndingPolicy.NORMALIZE_LF:
        return normalized.replace("\r\n", "\n").replace("\r", "\n")
    return normalized


def _digest[FingerprintT: _Fingerprint](
    fingerprint_type: type[FingerprintT],
    values: tuple[str, ...],
    *,
    ordering: FingerprintOrdering,
    line_endings: LineEndingPolicy,
) -> FingerprintT:
    normalized_values = tuple(_normalize_text(value, line_endings) for value in values)
    if ordering is FingerprintOrdering.UNORDERED:
        normalized_values = tuple(sorted(normalized_values))

    payload = {
        "fingerprint_schema": "contextforge-v1",
        "fingerprint_type": fingerprint_type.prefix,
        "line_endings": line_endings.value,
        "ordering": ordering.value,
        "values": normalized_values,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    return fingerprint_type(f"{fingerprint_type.prefix}_sha256_{digest}")


def fingerprint_content(
    content: str,
    *,
    line_endings: LineEndingPolicy = LineEndingPolicy.NORMALIZE_LF,
) -> ContentFingerprint:
    """Fingerprint text using explicit Unicode, UTF-8, and line-ending rules."""
    return _digest(
        ContentFingerprint,
        (content,),
        ordering=FingerprintOrdering.ORDERED,
        line_endings=line_endings,
    )


def fingerprint_project(
    components: tuple[str, ...],
    *,
    ordering: FingerprintOrdering,
    line_endings: LineEndingPolicy = LineEndingPolicy.NORMALIZE_LF,
) -> ProjectFingerprint:
    """Fingerprint semantic project components with explicit ordering semantics."""
    return _digest(
        ProjectFingerprint,
        components,
        ordering=ordering,
        line_endings=line_endings,
    )


def fingerprint_configuration(
    components: tuple[str, ...],
    *,
    ordering: FingerprintOrdering,
    line_endings: LineEndingPolicy = LineEndingPolicy.NORMALIZE_LF,
) -> ConfigurationFingerprint:
    """Fingerprint effective configuration components."""
    return _digest(
        ConfigurationFingerprint,
        components,
        ordering=ordering,
        line_endings=line_endings,
    )


def fingerprint_proposal(
    components: tuple[str, ...],
    *,
    ordering: FingerprintOrdering,
    line_endings: LineEndingPolicy = LineEndingPolicy.NORMALIZE_LF,
) -> ProposalFingerprint:
    """Fingerprint immutable proposal components."""
    return _digest(
        ProposalFingerprint,
        components,
        ordering=ordering,
        line_endings=line_endings,
    )
