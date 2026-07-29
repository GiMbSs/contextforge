"""Versioned JSON envelope and published exit-code contract."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from contextforge.adapters.project_commands import CliExitCode
from contextforge.cli.main import app

runner = CliRunner()


@pytest.mark.parametrize(
    ("member", "value"),
    [
        ("SUCCESS", 0),
        ("GENERAL_FAILURE", 1),
        ("INVALID_USAGE", 2),
        ("CONFIGURATION_FAILURE", 3),
        ("PROJECT_RESOLUTION_FAILURE", 4),
        ("SCAN_FAILURE", 5),
        ("INDEX_FAILURE", 6),
        ("RETRIEVAL_FAILURE", 7),
        ("PROMPT_FAILURE", 8),
        ("PROVIDER_FAILURE", 9),
        ("PATCH_VALIDATION_FAILURE", 10),
        ("APPROVAL_REQUIRED", 11),
        ("PATCH_REJECTED", 12),
        ("PATCH_APPLICATION_FAILURE", 13),
        ("PROJECT_STATE_CONFLICT", 14),
        ("SECURITY_POLICY_REJECTION", 15),
        ("OPERATION_CANCELLED", 16),
        ("PARTIAL_RESULT", 17),
        ("UNSUPPORTED_CAPABILITY", 18),
    ],
)
def test_documented_exit_codes_are_stable(member: str, value: int) -> None:
    assert int(CliExitCode[member]) == value


def test_success_json_uses_exact_versioned_envelope(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["--project", str(tmp_path), "--format", "json", "status"],
    )

    assert result.exit_code == 0
    envelope = json.loads(result.stdout)
    assert tuple(sorted(envelope)) == (
        "data",
        "diagnostics",
        "schema_version",
        "status",
    )
    assert envelope["schema_version"] == "1.0"
    assert envelope["status"] == "success"
    assert envelope["diagnostics"] == []
    assert envelope["data"]["command"] == "status"


def test_failure_json_preserves_structured_diagnostics_and_stderr(
    tmp_path: Path,
) -> None:
    result = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path / "missing"),
            "--format",
            "json",
            "status",
        ],
    )

    assert result.exit_code == 4
    envelope = json.loads(result.stdout)
    assert envelope["schema_version"] == "1.0"
    assert envelope["status"] == "failed"
    assert envelope["data"] == {"status": "failed"}
    assert envelope["diagnostics"][0]["code"] == "CLI_PROJECT_NOT_FOUND"
    assert "CLI_PROJECT_NOT_FOUND" in result.stderr
