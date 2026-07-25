"""Typed configuration models without configuration loading."""

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
from contextforge.configuration.precedence import (
    CONFIGURATION_PRECEDENCE,
    ConfigurationSource,
    EffectiveConfiguration,
    EffectiveValue,
    resolve_configuration,
)
from contextforge.configuration.sources import (
    ConfigurationLoadResult,
    ConfigurationSourceAdapter,
)

__all__ = [
    "CONFIGURATION_PRECEDENCE",
    "CliConfig",
    "ConfigModel",
    "ConfigurationLoadResult",
    "ConfigurationSource",
    "ConfigurationSourceAdapter",
    "ContextConfig",
    "EffectiveConfiguration",
    "EffectiveValue",
    "IndexerConfig",
    "PatchConfig",
    "ProjectConfig",
    "PromptConfig",
    "ProviderConfig",
    "RetrieverConfig",
    "ScannerConfig",
    "SecretReference",
    "resolve_configuration",
]
