"""Tests for CF-014 increment I013 TOML configuration loading."""

from pathlib import Path

import pytest

from contextforge.adapters.configuration import TomlConfigurationSourceAdapter
from contextforge.configuration import (
    ConfigurationSource,
    SecretReference,
    resolve_configuration,
)


@pytest.fixture
def adapter() -> TomlConfigurationSourceAdapter:
    return TomlConfigurationSourceAdapter()


def test_loads_project_toml_as_immutable_data(
    tmp_path: Path,
    adapter: TomlConfigurationSourceAdapter,
) -> None:
    config_path = tmp_path / "project.toml"
    config_path.write_text(
        """
[scanner]
exclude_patterns = ["build", ".git"]
max_depth = 4

[provider]
model_id = "qwen2.5-coder"
credential_reference = "env:CONTEXTFORGE_API_KEY"
""".strip(),
        encoding="utf-8",
    )

    result = adapter.load(config_path)

    assert result.succeeded
    scanner = result.values["scanner"]
    provider = result.values["provider"]
    assert scanner["exclude_patterns"] == ("build", ".git")  # type: ignore[index]
    assert isinstance(provider["credential_reference"], SecretReference)  # type: ignore[index]
    with pytest.raises(TypeError):
        scanner["max_depth"] = 2  # type: ignore[index]


def test_loaded_project_and_user_values_integrate_with_precedence(
    tmp_path: Path,
    adapter: TomlConfigurationSourceAdapter,
) -> None:
    user_path = tmp_path / "user.toml"
    project_path = tmp_path / "project.toml"
    user_path.write_text("[retriever]\nmax_results = 5\n", encoding="utf-8")
    project_path.write_text("[retriever]\nmax_results = 8\n", encoding="utf-8")

    user = adapter.load(user_path)
    project = adapter.load(project_path)
    effective = resolve_configuration(user=user.values, project=project.values)

    assert effective.config.retriever.max_results == 8
    assert effective.source_for("retriever.max_results") is ConfigurationSource.PROJECT


def test_missing_file_produces_stable_diagnostic(
    tmp_path: Path,
    adapter: TomlConfigurationSourceAdapter,
) -> None:
    result = adapter.load(tmp_path / "missing.toml")

    assert not result.succeeded
    assert result.values == {}
    diagnostic = next(iter(result.diagnostics))
    assert str(diagnostic.code) == "CONFIG_FILE_NOT_FOUND"
    assert diagnostic.location is not None


def test_unreadable_source_produces_stable_diagnostic(
    tmp_path: Path,
    adapter: TomlConfigurationSourceAdapter,
) -> None:
    result = adapter.load(tmp_path)

    assert not result.succeeded
    assert str(next(iter(result.diagnostics)).code) == "CONFIG_FILE_UNREADABLE"


def test_invalid_utf8_produces_stable_diagnostic(
    tmp_path: Path,
    adapter: TomlConfigurationSourceAdapter,
) -> None:
    config_path = tmp_path / "invalid.toml"
    config_path.write_bytes(b"\xff\xfe")

    result = adapter.load(config_path)

    assert not result.succeeded
    assert str(next(iter(result.diagnostics)).code) == "CONFIG_FILE_INVALID_UTF8"


def test_malformed_toml_produces_stable_secret_safe_diagnostic(
    tmp_path: Path,
    adapter: TomlConfigurationSourceAdapter,
) -> None:
    config_path = tmp_path / "malformed.toml"
    secret = "never-expose-this"
    config_path.write_text(
        f'[provider]\ncredential_reference = "{secret}" trailing',
        encoding="utf-8",
    )

    result = adapter.load(config_path)

    assert not result.succeeded
    diagnostic = next(iter(result.diagnostics))
    assert str(diagnostic.code) == "CONFIG_TOML_PARSE_ERROR"
    assert secret not in diagnostic.to_json()


def test_toml_content_is_never_executed(
    tmp_path: Path,
    adapter: TomlConfigurationSourceAdapter,
) -> None:
    marker = tmp_path / "executed"
    config_path = tmp_path / "inert.toml"
    marker_text = marker.as_posix()
    config_path.write_text(
        f'[provider]\nmodel_id = "__import__(\\"pathlib\\").Path(\\"{marker_text}\\").touch()"',
        encoding="utf-8",
    )

    result = adapter.load(config_path)

    assert result.succeeded
    assert not marker.exists()
    assert result.values["provider"]["model_id"].startswith("__import__")  # type: ignore[index,union-attr]
