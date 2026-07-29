"""CLI tests for init, status, scan, and index."""

import json
from pathlib import Path

from typer.testing import CliRunner

from contextforge.adapters.project_commands import (
    LocalProjectCommandGateway,
    _LocalPatchSourceStates,
)
from contextforge.cli.main import app
from contextforge.domain import ArtifactPath, fingerprint_content
from contextforge.project import ProjectRoot, ProjectRootSource

runner = CliRunner()


def _payload(result: object) -> dict[str, object]:
    envelope = json.loads(result.stdout)  # type: ignore[attr-defined]
    assert envelope["schema_version"] == "1.0"
    return envelope["data"]


def test_init_and_status_have_human_readable_output(tmp_path: Path) -> None:
    initialized = runner.invoke(app, ["init", str(tmp_path)])
    status = runner.invoke(app, ["--project", str(tmp_path), "status"])

    assert initialized.exit_code == 0
    assert "Status: initialized" in initialized.stdout
    assert initialized.stderr == ""
    assert status.exit_code == 0
    assert "Status: ready" in status.stdout


def test_scan_json_is_parseable_and_diagnostics_stay_on_stderr(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("def main():\n    return 0\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["--project", str(tmp_path), "--format", "json", "scan"],
    )

    assert result.exit_code == 0
    payload = _payload(result)
    assert payload["command"] == "scan"
    assert payload["artifact_count"] >= 1
    assert result.stderr == ""


def test_index_json_reports_structured_counts(tmp_path: Path) -> None:
    (tmp_path / "module.py").write_text("class Example:\n    pass\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["--project", str(tmp_path), "--format", "json", "index"],
    )

    assert result.exit_code == 0
    payload = _payload(result)
    assert payload["command"] == "index"
    assert payload["symbols"] >= 1
    assert payload["index_id"].startswith("index_")


def test_project_resolution_failure_has_stable_exit_and_stderr(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["--project", str(tmp_path / "missing"), "--format", "json", "status"],
    )

    assert result.exit_code == 4
    assert _payload(result) == {"status": "failed"}
    assert "CLI_PROJECT_NOT_FOUND" in result.stderr


def test_patch_source_state_binds_text_artifacts_to_content_fingerprint(
    tmp_path: Path,
) -> None:
    content = "value = 1\n"
    (tmp_path / "module.py").write_text(content, encoding="utf-8")
    root = ProjectRoot(tmp_path.resolve(), ProjectRootSource.EXPLICIT)
    inventory = LocalProjectCommandGateway()._scan(root)

    state = _LocalPatchSourceStates(root.path).load(inventory)

    artifact = state.artifact_at(ArtifactPath("module.py"))
    assert artifact is not None
    assert artifact.content_fingerprint == fingerprint_content(content)
