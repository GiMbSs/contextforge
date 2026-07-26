"""CLI tests for provider inspection commands."""

import json

from typer.testing import CliRunner

from contextforge.cli.main import app

runner = CliRunner()


def _payload(result: object) -> dict[str, object]:
    return json.loads(result.stdout)["data"]  # type: ignore[attr-defined,no-any-return]


def test_provider_list_reports_configured_capabilities_and_health() -> None:
    result = runner.invoke(app, ["--format", "json", "provider", "list"])

    assert result.exit_code == 0
    providers = _payload(result)["providers"]
    assert providers == [
        {
            "adapter_id": "mock-deterministic",
            "context_limit_tokens": 32768,
            "default_model": "mock-model",
            "execution_mode": "local",
            "health": "healthy",
            "provider_id": "mock-provider",
            "structured_output_supported": True,
        }
    ]


def test_provider_show_omits_credentials_and_reports_capability_profile() -> None:
    result = runner.invoke(
        app,
        ["--format", "json", "provider", "show", "mock-provider"],
    )

    assert result.exit_code == 0
    payload = _payload(result)
    assert payload["configuration"] == {
        "credentials_exposed": False,
        "default_model": "mock-model",
        "endpoint": None,
        "provider_id": "mock-provider",
    }
    assert payload["capabilities"]["adapter_version"] == "1"
    assert payload["delivery_policy_status"] == "local_only"


def test_provider_health_does_not_require_project_or_transmit_content() -> None:
    result = runner.invoke(app, ["--format", "json", "provider", "health"])

    assert result.exit_code == 0
    payload = _payload(result)
    assert payload["health"] == "healthy"
    assert payload["project_content_transmitted"] is False
    assert payload["provider_id"] == "mock-provider"


def test_provider_models_only_lists_available_models() -> None:
    result = runner.invoke(app, ["--format", "json", "provider", "models"])

    assert result.exit_code == 0
    payload = _payload(result)
    assert payload["download_triggered"] is False
    assert payload["models"] == [
        {
            "display_name": "ContextForge deterministic mock",
            "metadata": {},
            "model_id": "mock-model",
        }
    ]


def test_unknown_provider_has_stable_failure() -> None:
    result = runner.invoke(
        app,
        ["--format", "json", "provider", "health", "missing-provider"],
    )

    assert result.exit_code == 9
    assert _payload(result) == {"status": "failed"}
    assert "CLI_PROVIDER_NOT_FOUND" in result.stderr


def test_global_provider_option_selects_optional_provider_commands() -> None:
    result = runner.invoke(
        app,
        ["--provider", "mock-provider", "--format", "json", "provider", "models"],
    )

    assert result.exit_code == 0
    assert _payload(result)["provider_id"] == "mock-provider"
