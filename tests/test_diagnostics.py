"""Tests for structured diagnostics from CF-014 increment I007."""

from dataclasses import FrozenInstanceError

import pytest

from contextforge.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticCollection,
    DiagnosticLocation,
    DiagnosticSeverity,
)


def make_diagnostic(
    code: str = "SCAN_ROOT_NOT_FOUND",
    severity: DiagnosticSeverity = DiagnosticSeverity.ERROR,
    message: str = "Project root was not found.",
    *,
    location: DiagnosticLocation | None = None,
    metadata: tuple[tuple[str, str], ...] = (),
) -> Diagnostic:
    return Diagnostic(
        code=DiagnosticCode(code),
        severity=severity,
        message=message,
        capability="scanner",
        location=location,
        metadata=metadata,
    )


def test_diagnostic_serializes_deterministically() -> None:
    first = make_diagnostic(
        location=DiagnosticLocation("src/contextforge/main.py", line=4, column=2),
        metadata=(("zeta", "last"), ("alpha", "first")),
    )
    second = make_diagnostic(
        location=DiagnosticLocation("src/contextforge/main.py", line=4, column=2),
        metadata=(("alpha", "first"), ("zeta", "last")),
    )

    assert first == second
    assert first.to_json() == second.to_json()
    assert first.to_json() == (
        '{"capability":"scanner","code":"SCAN_ROOT_NOT_FOUND","guidance":null,'
        '"location":{"column":2,"line":4,"reference":"src/contextforge/main.py"},'
        '"message":"Project root was not found.","metadata":{"alpha":"first","zeta":"last"},'
        '"severity":"error","technical_details":null}'
    )


@pytest.mark.parametrize(
    "metadata_key",
    (
        "api-key",
        "authorization",
        "credential_value",
        "database_password",
        "private_key",
        "secret",
        "token",
    ),
)
def test_sensitive_metadata_values_are_redacted(metadata_key: str) -> None:
    diagnostic = make_diagnostic(metadata=((metadata_key, "do-not-expose"),))

    assert "do-not-expose" not in diagnostic.to_json()
    assert diagnostic.metadata == ((metadata_key, "[REDACTED]"),)


def test_non_secret_token_measurement_is_preserved() -> None:
    diagnostic = make_diagnostic(metadata=(("input_token_count", "42"),))

    assert diagnostic.metadata == (("input_token_count", "42"),)


@pytest.mark.parametrize(
    ("message", "secret"),
    (
        ("password=hunter2", "hunter2"),
        ("token: abc.def", "abc.def"),
        ("Authorization: Bearer abc123", "abc123"),
        ("request used Bearer abc123", "abc123"),
        ('api_key="private-value"', "private-value"),
    ),
)
def test_common_inline_secrets_are_redacted(message: str, secret: str) -> None:
    diagnostic = make_diagnostic(message=message)

    assert secret not in diagnostic.message
    assert "[REDACTED]" in diagnostic.message


def test_guidance_and_technical_details_are_redacted() -> None:
    diagnostic = Diagnostic(
        code=DiagnosticCode("PROVIDER_AUTH_FAILED"),
        severity=DiagnosticSeverity.ERROR,
        message="Provider authentication failed.",
        capability="provider",
        guidance="Replace password=old-password.",
        technical_details="Authorization: Bearer provider-token",
    )

    assert "old-password" not in diagnostic.to_json()
    assert "provider-token" not in diagnostic.to_json()


def test_collection_order_is_deterministic() -> None:
    info = make_diagnostic("SCAN_LANGUAGE_UNKNOWN", DiagnosticSeverity.INFO, "Unknown language.")
    warning = make_diagnostic(
        "SCAN_PATH_UNREADABLE",
        DiagnosticSeverity.WARNING,
        "Path is unreadable.",
    )
    error = make_diagnostic()
    critical = make_diagnostic(
        "SCAN_PATH_OUTSIDE_ROOT",
        DiagnosticSeverity.CRITICAL,
        "Path escapes project root.",
    )

    collection = DiagnosticCollection((info, error, critical, warning))

    assert tuple(item.severity for item in collection) == (
        DiagnosticSeverity.CRITICAL,
        DiagnosticSeverity.ERROR,
        DiagnosticSeverity.WARNING,
        DiagnosticSeverity.INFO,
    )
    assert collection.to_json() == DiagnosticCollection((warning, critical, info, error)).to_json()


def test_collection_addition_returns_new_value() -> None:
    original = DiagnosticCollection()
    updated = original.with_diagnostic(make_diagnostic())

    assert len(original) == 0
    assert len(updated) == 1


@pytest.mark.parametrize(
    "invalid_code",
    ("", "scan_error", "SCAN", "SCAN-ERROR", "_SCAN_ERROR", "SCAN__ERROR"),
)
def test_invalid_diagnostic_code_is_rejected(invalid_code: str) -> None:
    with pytest.raises(ValueError):
        DiagnosticCode(invalid_code)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    (
        ({"reference": ""}, "reference"),
        ({"reference": "file.py", "line": 0}, "line"),
        ({"reference": "file.py", "column": 0}, "column"),
        ({"reference": "file.py", "column": 1}, "requires a line"),
    ),
)
def test_invalid_location_is_rejected(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        DiagnosticLocation(**kwargs)


def test_duplicate_metadata_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        make_diagnostic(metadata=(("path", "one"), ("path", "two")))


def test_empty_metadata_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        make_diagnostic(metadata=((" ", "value"),))


def test_diagnostic_is_immutable() -> None:
    diagnostic = make_diagnostic()

    with pytest.raises(FrozenInstanceError):
        diagnostic.message = "changed"
