"""Tests for CF-014 increment I012 configuration precedence."""

import pytest

from contextforge.configuration import (
    CONFIGURATION_PRECEDENCE,
    ConfigurationSource,
    ProjectConfig,
    ProviderConfig,
    SecretReference,
    resolve_configuration,
)


def test_configuration_precedence_has_normative_order() -> None:
    assert CONFIGURATION_PRECEDENCE == (
        ConfigurationSource.CLI,
        ConfigurationSource.EXPLICIT_FILE,
        ConfigurationSource.NAMED_PROFILE,
        ConfigurationSource.PROJECT,
        ConfigurationSource.USER,
        ConfigurationSource.ENVIRONMENT,
        ConfigurationSource.DEFAULT,
    )


@pytest.mark.parametrize(
    ("higher_name", "lower_name", "expected_source"),
    [
        ("cli", "explicit_file", ConfigurationSource.CLI),
        ("explicit_file", "named_profile", ConfigurationSource.EXPLICIT_FILE),
        ("named_profile", "project", ConfigurationSource.NAMED_PROFILE),
        ("project", "user", ConfigurationSource.PROJECT),
        ("user", "environment", ConfigurationSource.USER),
    ],
)
def test_every_precedence_boundary(
    higher_name: str,
    lower_name: str,
    expected_source: ConfigurationSource,
) -> None:
    sources = {
        higher_name: {"retriever.max_results": 10},
        lower_name: {"retriever.max_results": 5},
    }

    effective = resolve_configuration(**sources)  # type: ignore[arg-type]

    assert effective.config.retriever.max_results == 10
    assert effective.source_for("retriever.max_results") is expected_source


def test_environment_overrides_defaults() -> None:
    effective = resolve_configuration(environment={"retriever.max_results": 7})

    assert effective.config.retriever.max_results == 7
    assert effective.source_for("retriever.max_results") is ConfigurationSource.ENVIRONMENT
    assert effective.source_for("scanner.follow_symlinks") is ConfigurationSource.DEFAULT


def test_missing_optional_sources_use_defaults() -> None:
    effective = resolve_configuration()

    assert effective.config == ProjectConfig()
    assert set(dict(effective.attribution).values()) == {ConfigurationSource.DEFAULT}


def test_nested_and_dotted_mappings_are_supported() -> None:
    effective = resolve_configuration(
        project={"scanner": {"max_depth": 4}},
        cli={"provider.model_id": "qwen2.5-coder"},
    )

    assert effective.config.scanner.max_depth == 4
    assert effective.config.provider.model_id == "qwen2.5-coder"


def test_invalid_value_type_is_rejected() -> None:
    with pytest.raises(TypeError, match=r"retriever\.max_results"):
        resolve_configuration(cli={"retriever.max_results": "many"})
    with pytest.raises(TypeError, match=r"scanner\.follow_symlinks"):
        resolve_configuration(cli={"scanner.follow_symlinks": 1})


def test_unknown_configuration_key_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"scanner\.mystery"):
        resolve_configuration(project={"scanner": {"mystery": True}})


def test_effective_secret_is_redacted_and_attributed() -> None:
    secret = SecretReference("env:CONTEXTFORGE_API_KEY")
    effective = resolve_configuration(environment={"provider.credential_reference": secret})

    inspected = effective.inspect()["provider.credential_reference"]
    assert inspected.display_value == "<secret-reference>"
    assert inspected.source is ConfigurationSource.ENVIRONMENT
    assert "CONTEXTFORGE_API_KEY" not in repr(inspected)
    assert "CONTEXTFORGE_API_KEY" not in repr(effective)


def test_custom_defaults_retain_default_attribution() -> None:
    defaults = ProjectConfig(provider=ProviderConfig(provider_id="mock-provider"))

    effective = resolve_configuration(defaults=defaults)

    assert effective.config.provider.provider_id == "mock-provider"
    assert effective.source_for("provider.provider_id") is ConfigurationSource.DEFAULT


def test_unknown_source_lookup_is_rejected() -> None:
    with pytest.raises(KeyError, match="Unknown configuration key"):
        resolve_configuration().source_for("not.a.key")
