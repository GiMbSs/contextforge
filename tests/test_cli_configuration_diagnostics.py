"""CLI coverage for configuration and runtime diagnostics commands."""

import json
from pathlib import Path

from typer.testing import CliRunner

from contextforge.cli.main import app

runner = CliRunner()


def _payload(result: object) -> dict[str, object]:
    return json.loads(result.stdout)["data"]  # type: ignore[attr-defined,no-any-return]


def test_config_show_and_get_include_attribution_and_redact_secrets(
    tmp_path: Path,
) -> None:
    config = tmp_path / "selected.toml"
    config.write_text(
        '[provider]\nprovider_id = "custom"\ncredential_reference = "env:API_TOKEN"\n',
        encoding="utf-8",
    )

    shown = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--config",
            str(config),
            "--format",
            "json",
            "config",
            "show",
        ],
    )
    selected = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--config",
            str(config),
            "--format",
            "json",
            "config",
            "get",
            "provider.credential_reference",
        ],
    )

    assert shown.exit_code == 0
    configuration = _payload(shown)["configuration"]
    assert configuration["provider.provider_id"] == {
        "source": "explicit_file",
        "value": "custom",
    }
    assert "env:API_TOKEN" not in shown.stdout
    assert _payload(selected)["value"] == "<secret-reference>"


def test_config_set_atomically_updates_project_scope_and_validates_type(
    tmp_path: Path,
) -> None:
    updated = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--format",
            "json",
            "config",
            "set",
            "retriever.max_results",
            "7",
        ],
    )
    invalid = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "config",
            "set",
            "retriever.max_results",
            "many",
        ],
    )

    assert updated.exit_code == 0
    destination = tmp_path / ".contextforge" / "config.toml"
    assert "max_results = 7" in destination.read_text(encoding="utf-8")
    assert invalid.exit_code == 3
    assert "CONFIG_WRITE_FAILED" in invalid.stderr
    assert not destination.with_suffix(".toml.tmp").exists()


def test_config_set_rejects_secret_material(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "config",
            "set",
            "provider.credential_reference",
            "plaintext-secret",
        ],
    )

    assert result.exit_code == 3
    assert "CONFIG_SECRET_WRITE_REJECTED" in result.stderr
    assert "plaintext-secret" not in result.stdout
    assert "plaintext-secret" not in result.stderr


def test_config_validate_reports_parse_failure_and_paths_are_explicit(
    tmp_path: Path,
) -> None:
    config = tmp_path / "broken.toml"
    config.write_text("[scanner\n", encoding="utf-8")

    invalid = runner.invoke(
        app,
        [
            "--project",
            str(tmp_path),
            "--config",
            str(config),
            "config",
            "validate",
        ],
    )
    paths = runner.invoke(
        app,
        ["--project", str(tmp_path), "--format", "json", "config", "paths"],
    )

    assert invalid.exit_code == 3
    assert "CONFIG_TOML_PARSE_ERROR" in invalid.stderr
    project_path = Path(_payload(paths)["paths"]["project"])  # type: ignore[index,arg-type]
    assert project_path.parts[-2:] == (".contextforge", "config.toml")


def test_diagnostics_reports_runtime_without_project_or_secret_content(
    tmp_path: Path,
) -> None:
    result = runner.invoke(
        app,
        ["--project", str(tmp_path), "--format", "json", "diagnostics"],
    )

    assert result.exit_code == 0
    payload = _payload(result)
    assert payload["command"] == "diagnostics"
    assert payload["checks"]["project_resolution"] == "resolved"
    assert payload["python_version"]
    assert payload["contextforge_version"]
