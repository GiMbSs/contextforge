"""Immutable diagnostic models with deterministic serialization."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum

type DiagnosticMetadataValue = str | int | float | bool | None
type DiagnosticMetadata = tuple[tuple[str, DiagnosticMetadataValue], ...]

_REDACTED = "[REDACTED]"
_SENSITIVE_KEY_PARTS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "credential",
        "password",
        "private_key",
        "secret",
    }
)
_SENSITIVE_TOKEN_KEYS = frozenset(
    {
        "access_token",
        "auth_token",
        "refresh_token",
        "token",
    }
)
_SENSITIVE_KEY_BOUNDARIES = (
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "password",
    "private_key",
    "secret",
)
_AUTHORIZATION_PATTERN = re.compile(
    r"\bauthorization\s*([:=])\s*(?:bearer\s+)?[^\s,;]+",
    flags=re.IGNORECASE,
)
_BEARER_PATTERN = re.compile(
    r"\bbearer\s+[A-Za-z0-9._~+/=-]+",
    flags=re.IGNORECASE,
)
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"\b(password|token|secret|api[_-]?key|credential)\s*([:=])\s*"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)",
    flags=re.IGNORECASE,
)


class DiagnosticSeverity(StrEnum):
    """Stable diagnostic severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True, order=True)
class DiagnosticCode:
    """Stable machine-readable diagnostic code."""

    value: str

    def __post_init__(self) -> None:
        if re.fullmatch(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+", self.value) is None:
            raise ValueError("DiagnosticCode must contain uppercase underscore-separated segments")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class DiagnosticLocation:
    """Optional source or entity location related to a diagnostic."""

    reference: str
    line: int | None = None
    column: int | None = None

    def __post_init__(self) -> None:
        if not self.reference.strip():
            raise ValueError("DiagnosticLocation reference must not be empty")
        if self.line is not None and self.line < 1:
            raise ValueError("DiagnosticLocation line must be positive")
        if self.column is not None and self.column < 1:
            raise ValueError("DiagnosticLocation column must be positive")
        if self.column is not None and self.line is None:
            raise ValueError("DiagnosticLocation column requires a line")

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic serialization-ready representation."""
        return {
            "column": self.column,
            "line": self.line,
            "reference": self.reference,
        }


def _is_sensitive_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")
    if normalized in _SENSITIVE_KEY_PARTS or normalized in _SENSITIVE_TOKEN_KEYS:
        return True
    return any(
        normalized.startswith(f"{part}_") or normalized.endswith(f"_{part}")
        for part in _SENSITIVE_KEY_BOUNDARIES
    )


def _redact_text(value: str) -> str:
    redacted = _AUTHORIZATION_PATTERN.sub(
        lambda match: f"authorization{match.group(1)}{_REDACTED}",
        value,
    )
    redacted = _BEARER_PATTERN.sub(f"Bearer {_REDACTED}", redacted)
    return _SECRET_ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{_REDACTED}",
        redacted,
    )


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """Information produced by one ContextForge capability."""

    code: DiagnosticCode
    severity: DiagnosticSeverity
    message: str
    capability: str
    location: DiagnosticLocation | None = None
    guidance: str | None = None
    technical_details: str | None = None
    metadata: DiagnosticMetadata = ()

    def __post_init__(self) -> None:
        if not self.message.strip():
            raise ValueError("Diagnostic message must not be empty")
        if not self.capability.strip():
            raise ValueError("Diagnostic capability must not be empty")

        sanitized_metadata: list[tuple[str, DiagnosticMetadataValue]] = []
        seen_keys: set[str] = set()
        for key, value in self.metadata:
            normalized_key = key.strip()
            if not normalized_key:
                raise ValueError("Diagnostic metadata keys must not be empty")
            if normalized_key in seen_keys:
                raise ValueError(f"Duplicate Diagnostic metadata key: {normalized_key}")
            seen_keys.add(normalized_key)
            sanitized_value = _REDACTED if _is_sensitive_key(normalized_key) else value
            sanitized_metadata.append((normalized_key, sanitized_value))

        object.__setattr__(self, "message", _redact_text(self.message))
        object.__setattr__(
            self,
            "guidance",
            _redact_text(self.guidance) if self.guidance is not None else None,
        )
        object.__setattr__(
            self,
            "technical_details",
            _redact_text(self.technical_details) if self.technical_details is not None else None,
        )
        object.__setattr__(self, "metadata", tuple(sorted(sanitized_metadata)))

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic serialization-ready representation."""
        return {
            "capability": self.capability,
            "code": str(self.code),
            "guidance": self.guidance,
            "location": self.location.to_dict() if self.location is not None else None,
            "message": self.message,
            "metadata": dict(self.metadata),
            "severity": self.severity.value,
            "technical_details": self.technical_details,
        }

    def to_json(self) -> str:
        """Serialize deterministically as compact UTF-8-compatible JSON text."""
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )


_SEVERITY_ORDER = {
    DiagnosticSeverity.CRITICAL: 0,
    DiagnosticSeverity.ERROR: 1,
    DiagnosticSeverity.WARNING: 2,
    DiagnosticSeverity.INFO: 3,
}


def _diagnostic_sort_key(diagnostic: Diagnostic) -> tuple[object, ...]:
    location = diagnostic.location
    return (
        _SEVERITY_ORDER[diagnostic.severity],
        str(diagnostic.code),
        location.reference if location is not None else "",
        location.line if location is not None and location.line is not None else 0,
        location.column if location is not None and location.column is not None else 0,
        diagnostic.message,
        diagnostic.capability,
        diagnostic.to_json(),
    )


@dataclass(frozen=True, slots=True)
class DiagnosticCollection:
    """Immutable collection with stable severity-first ordering."""

    diagnostics: tuple[Diagnostic, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "diagnostics", tuple(sorted(self.diagnostics, key=_diagnostic_sort_key))
        )

    def __iter__(self) -> Iterator[Diagnostic]:
        return iter(self.diagnostics)

    def __len__(self) -> int:
        return len(self.diagnostics)

    def with_diagnostic(self, diagnostic: Diagnostic) -> DiagnosticCollection:
        """Return a new collection containing an additional diagnostic."""
        return DiagnosticCollection((*self.diagnostics, diagnostic))

    def to_json(self) -> str:
        """Serialize the ordered collection deterministically."""
        return json.dumps(
            [diagnostic.to_dict() for diagnostic in self.diagnostics],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
