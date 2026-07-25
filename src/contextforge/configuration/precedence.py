"""Pure configuration precedence resolution with source attribution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from enum import StrEnum
from types import UnionType
from typing import Any, get_args, get_origin, get_type_hints

from contextforge.configuration.models import (
    CliConfig,
    ConfigModel,
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


class ConfigurationSource(StrEnum):
    """Sources ordered by the normative configuration precedence."""

    CLI = "cli"
    EXPLICIT_FILE = "explicit_file"
    NAMED_PROFILE = "named_profile"
    PROJECT = "project"
    USER = "user"
    ENVIRONMENT = "environment"
    DEFAULT = "default"


CONFIGURATION_PRECEDENCE: tuple[ConfigurationSource, ...] = (
    ConfigurationSource.CLI,
    ConfigurationSource.EXPLICIT_FILE,
    ConfigurationSource.NAMED_PROFILE,
    ConfigurationSource.PROJECT,
    ConfigurationSource.USER,
    ConfigurationSource.ENVIRONMENT,
    ConfigurationSource.DEFAULT,
)

_GROUP_TYPES: dict[str, type[ConfigModel]] = {
    "scanner": ScannerConfig,
    "indexer": IndexerConfig,
    "retriever": RetrieverConfig,
    "context": ContextConfig,
    "prompt": PromptConfig,
    "provider": ProviderConfig,
    "patch": PatchConfig,
    "cli": CliConfig,
}


@dataclass(frozen=True, slots=True)
class EffectiveValue:
    """One effective configuration value and its winning source."""

    value: object
    source: ConfigurationSource

    @property
    def display_value(self) -> object:
        """Return a representation safe for configuration inspection."""
        if isinstance(self.value, SecretReference):
            return SecretReference.redacted
        return self.value


@dataclass(frozen=True, slots=True)
class EffectiveConfiguration:
    """Resolved typed configuration plus field-level source attribution."""

    config: ProjectConfig
    attribution: tuple[tuple[str, ConfigurationSource], ...]

    def source_for(self, key: str) -> ConfigurationSource:
        """Return the winning source for a canonical dotted key."""
        sources = dict(self.attribution)
        try:
            return sources[key]
        except KeyError as error:
            raise KeyError(f"Unknown configuration key: {key}") from error

    def inspect(self) -> dict[str, EffectiveValue]:
        """Return effective values with attribution and secret redaction support."""
        values = _flatten_project_config(self.config)
        sources = dict(self.attribution)
        return {
            key: EffectiveValue(value=value, source=sources[key])
            for key, value in sorted(values.items())
        }


def _flatten_mapping(
    values: Mapping[object, object],
    *,
    prefix: str = "",
) -> dict[str, object]:
    flattened: dict[str, object] = {}
    for raw_key, value in values.items():
        if not isinstance(raw_key, str):
            raise TypeError("Configuration keys must be strings")
        key = raw_key.strip()
        if not key:
            raise ValueError("Configuration keys must not be empty")
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, Mapping):
            nested = _flatten_mapping(value, prefix=path)
            duplicate_keys = flattened.keys() & nested.keys()
            if duplicate_keys:
                duplicate = min(duplicate_keys)
                raise ValueError(f"Duplicate configuration key: {duplicate}")
            flattened.update(nested)
        elif path in flattened:
            raise ValueError(f"Duplicate configuration key: {path}")
        else:
            flattened[path] = value
    return flattened


def _flatten_project_config(config: ProjectConfig) -> dict[str, object]:
    flattened: dict[str, object] = {}
    for group_field in fields(config):
        group = getattr(config, group_field.name)
        for value_field in fields(group):
            flattened[f"{group_field.name}.{value_field.name}"] = getattr(group, value_field.name)
    return flattened


def _configuration_schema() -> dict[str, object]:
    schema: dict[str, object] = {}
    for group_name, group_type in _GROUP_TYPES.items():
        for key, annotation in get_type_hints(group_type).items():
            schema[f"{group_name}.{key}"] = annotation
    return schema


def _matches_type(value: object, annotation: object) -> bool:
    if annotation is Any:
        return True
    origin = get_origin(annotation)
    if origin in (UnionType,):
        return any(_matches_type(value, member) for member in get_args(annotation))
    if origin is tuple:
        arguments = get_args(annotation)
        if not isinstance(value, tuple):
            return False
        if len(arguments) == 2 and arguments[1] is Ellipsis:
            return all(_matches_type(item, arguments[0]) for item in value)
        return len(value) == len(arguments) and all(
            _matches_type(item, expected) for item, expected in zip(value, arguments, strict=True)
        )
    if annotation is None or annotation is type(None):
        return value is None
    if annotation is bool:
        return type(value) is bool
    if annotation is int:
        return type(value) is int
    return isinstance(value, annotation)  # type: ignore[arg-type]


def _validate_values(values: Mapping[str, object]) -> None:
    schema = _configuration_schema()
    unknown = tuple(sorted(values.keys() - schema.keys()))
    if unknown:
        raise ValueError(f"Unknown configuration key: {unknown[0]}")
    for key, value in values.items():
        if not _matches_type(value, schema[key]):
            raise TypeError(f"Invalid value type for configuration key: {key}")


def _build_project_config(
    values: Mapping[str, object],
    defaults: ProjectConfig,
) -> ProjectConfig:
    groups: dict[str, ConfigModel] = {}
    for group_name in _GROUP_TYPES:
        group = getattr(defaults, group_name)
        overrides = {
            key.removeprefix(f"{group_name}."): value
            for key, value in values.items()
            if key.startswith(f"{group_name}.")
        }
        groups[group_name] = replace(group, **overrides)
    return ProjectConfig(**groups)  # type: ignore[arg-type]


def resolve_configuration(
    *,
    cli: Mapping[object, object] | None = None,
    explicit_file: Mapping[object, object] | None = None,
    named_profile: Mapping[object, object] | None = None,
    project: Mapping[object, object] | None = None,
    user: Mapping[object, object] | None = None,
    environment: Mapping[object, object] | None = None,
    defaults: ProjectConfig | None = None,
) -> EffectiveConfiguration:
    """Resolve mappings according to the normative precedence order."""
    base = defaults or ProjectConfig()
    effective_values = _flatten_project_config(base)
    attribution = {key: ConfigurationSource.DEFAULT for key in effective_values}
    sources = {
        ConfigurationSource.ENVIRONMENT: environment,
        ConfigurationSource.USER: user,
        ConfigurationSource.PROJECT: project,
        ConfigurationSource.NAMED_PROFILE: named_profile,
        ConfigurationSource.EXPLICIT_FILE: explicit_file,
        ConfigurationSource.CLI: cli,
    }

    for source in reversed(CONFIGURATION_PRECEDENCE[:-1]):
        source_values = sources[source]
        if source_values is None:
            continue
        flattened = _flatten_mapping(source_values)
        _validate_values(flattened)
        effective_values.update(flattened)
        attribution.update(dict.fromkeys(flattened, source))

    _validate_values(effective_values)
    config = _build_project_config(effective_values, base)
    return EffectiveConfiguration(
        config=config,
        attribution=tuple(sorted(attribution.items())),
    )
