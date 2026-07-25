"""Tests for CF-014 increment I011 typed configuration models."""

from collections.abc import Callable
from dataclasses import FrozenInstanceError

import pytest

from contextforge.configuration import (
    CliConfig,
    ContextConfig,
    IndexerConfig,
    PatchConfig,
    ProjectConfig,
    PromptConfig,
    ProviderConfig,
    RetrieverConfig,
    ScannerConfig,
    SecretReference,
)


def test_project_configuration_has_explicit_typed_defaults() -> None:
    config = ProjectConfig()

    assert config == ProjectConfig(
        scanner=ScannerConfig(),
        indexer=IndexerConfig(),
        retriever=RetrieverConfig(),
        context=ContextConfig(),
        prompt=PromptConfig(),
        provider=ProviderConfig(),
        patch=PatchConfig(),
        cli=CliConfig(),
    )
    assert config.scanner.follow_symlinks is False
    assert config.provider.allow_remote is False
    assert config.patch.require_approval is True


def test_project_configuration_default_groups_are_independent() -> None:
    first = ProjectConfig()
    second = ProjectConfig()

    assert first.scanner is not second.scanner
    assert first.provider is not second.provider


def test_unknown_keys_are_reported_deterministically() -> None:
    assert ScannerConfig.unknown_keys({"follow_symlinks": False, "mystery": 1, "another": 2}) == (
        "another",
        "mystery",
    )
    assert ScannerConfig.known_keys() == frozenset(
        {"exclude_patterns", "follow_symlinks", "max_depth", "max_file_size_bytes"}
    )


def test_unknown_key_reporting_rejects_non_string_keys() -> None:
    with pytest.raises(TypeError, match="strings"):
        ScannerConfig.unknown_keys({"follow_symlinks", 1})


def test_secret_reference_never_displays_reference_value() -> None:
    secret = SecretReference("env:CONTEXTFORGE_API_KEY")
    provider = ProviderConfig(credential_reference=secret)

    assert str(secret) == "<secret-reference>"
    assert "CONTEXTFORGE_API_KEY" not in repr(secret)
    assert "CONTEXTFORGE_API_KEY" not in repr(provider)


def test_secret_reference_rejects_empty_reference() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        SecretReference(" ")


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ScannerConfig(max_file_size_bytes=0),
        lambda: ScannerConfig(max_depth=-1),
        lambda: RetrieverConfig(max_results=0),
        lambda: ContextConfig(max_tokens=0),
        lambda: PromptConfig(max_input_tokens=0),
    ],
)
def test_positive_configuration_limits_are_validated(factory: Callable[[], object]) -> None:
    with pytest.raises(ValueError, match=r"positive|negative"):
        factory()


def test_scanner_exclusion_patterns_are_normalized_to_tuple() -> None:
    config = ScannerConfig(exclude_patterns=["build", ".git"])  # type: ignore[arg-type]

    assert config.exclude_patterns == ("build", ".git")


def test_provider_identifiers_are_validated() -> None:
    with pytest.raises(ValueError, match="provider_id"):
        ProviderConfig(provider_id=" ")
    with pytest.raises(ValueError, match="model_id"):
        ProviderConfig(model_id="")


def test_configuration_models_are_immutable() -> None:
    config = ProjectConfig()

    with pytest.raises(FrozenInstanceError):
        config.cli = CliConfig(non_interactive=True)  # type: ignore[misc]
