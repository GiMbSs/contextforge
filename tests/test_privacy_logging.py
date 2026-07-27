"""Privacy and logging review for CF-014 increment I096.

These tests verify that production code does not emit complete task text,
full prompts, sensitive context, credentials, full provider output, or
unredacted environment values through common logging or printing channels.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from contextforge.diagnostics import Diagnostic, DiagnosticCode, DiagnosticSeverity
from contextforge.domain.tasks import RequestedOutput, TaskKind, TaskSpecification
from contextforge.provider import (
    InferenceResponseNormalizer,
    ProviderDiagnostics,
    ProviderExecutionMeasurements,
    ProviderFinishReason,
    ProviderFinishState,
    ProviderResponseFormat,
    ProviderResponseMetadata,
    ProviderResponseObservation,
    RawResponseRetentionPolicy,
)

SOURCE_ROOT = Path(__file__).parents[1] / "src" / "contextforge"


def _production_modules() -> list[Path]:
    return sorted(SOURCE_ROOT.rglob("*.py"))


def _uses_logging_or_print(source: str) -> bool:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "logging":
                    return True
        elif isinstance(node, ast.ImportFrom):
            if node.module == "logging":
                return True
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "print":
                return True
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and (func.value.id == "logging" or func.attr == "print")
            ):
                return True
    return False


@pytest.mark.parametrize("source_file", _production_modules(), ids=lambda p: p.name)
def test_production_module_does_not_use_logging_or_print(source_file: Path) -> None:
    """Direct logging and printing are not used in production code.

    All diagnostic output and user-facing reporting must pass through the
    redacted Diagnostic and CLI rendering paths so that secrets cannot leak
    through unstructured log channels.
    """
    source = source_file.read_text(encoding="utf-8")
    assert not _uses_logging_or_print(source)


def _sensitive_task_text() -> str:
    return (
        "Analyze the project. The database password=secret-db-pass-123 and "
        "the api_key=sk-live-abcdef123456."
    )


def _task_with_secret() -> TaskSpecification:
    from contextforge.domain import new_task_id

    return TaskSpecification(
        task_id=new_task_id(),
        task_text=_sensitive_task_text(),
        task_kind=TaskKind.ANALYZE,
        requested_output=RequestedOutput.ANALYSIS,
    )


def test_diagnostic_message_redacts_inline_secrets_from_task_text() -> None:
    """If task text is accidentally embedded in a diagnostic, secrets are redacted.

    Task text itself should not be placed in diagnostic messages; this test guards
    the case where a capability accidentally includes it and relies on the secret
    redaction layer as a backstop.
    """
    task = _task_with_secret()
    diagnostic = Diagnostic(
        DiagnosticCode("PRIVACY_REVIEW_EXAMPLE"),
        DiagnosticSeverity.WARNING,
        f"Task {task.task_id} requested: {task.task_text}",
        "privacy-review",
    )

    assert "secret-db-pass-123" not in diagnostic.message
    assert "sk-live-abcdef123456" not in diagnostic.message
    assert "[REDACTED]" in diagnostic.message


def test_diagnostic_technical_details_redact_inline_secrets() -> None:
    """Technical details redact common secret-bearing patterns."""
    diagnostic = Diagnostic(
        DiagnosticCode("PRIVACY_TECHNICAL_DETAILS"),
        DiagnosticSeverity.INFO,
        "Information",
        "privacy-review",
        technical_details="Authorization: Bearer eyJleGFtcGxlIjp0cnVl",
    )

    assert "eyJleGFtcGxlIjp0cnVl" not in diagnostic.technical_details
    assert "[REDACTED]" in diagnostic.technical_details


def test_provider_raw_response_is_discarded_when_retention_is_never() -> None:
    """Provider output bytes are not retained when the policy forbids it."""
    from datetime import UTC, datetime

    from contextforge.domain import new_inference_request_id, new_inference_response_id, new_task_id

    observation = ProviderResponseObservation(
        response_id=new_inference_response_id(),
        request_id=new_inference_request_id(),
        task_id=new_task_id(),
        content='{"answer":"ok"}',
        response_format=ProviderResponseFormat.JSON_TEXT,
        metadata=ProviderResponseMetadata(
            "provider",
            "adapter",
            "1",
            "model",
            "profile",
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 1, tzinfo=UTC),
        ),
        usage=None,
        measurements=ProviderExecutionMeasurements(1),
        finish_state=ProviderFinishState.COMPLETED,
        finish_reason=ProviderFinishReason.NATURAL_COMPLETION,
        diagnostics=ProviderDiagnostics(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        raw_response=b'{"answer":"ok", "usage": {"prompt_tokens": 100}}',
    )

    response = InferenceResponseNormalizer().normalize(
        observation, RawResponseRetentionPolicy.NEVER
    )

    assert response.raw_response is None
