"""Immutable typed configuration groups with explicit defaults."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, fields
from typing import ClassVar, cast


@dataclass(frozen=True, slots=True)
class ConfigModel:
    """Base behavior shared by configuration groups."""

    @classmethod
    def known_keys(cls) -> frozenset[str]:
        """Return the keys accepted by this configuration model."""
        return frozenset(item.name for item in fields(cls))

    @classmethod
    def unknown_keys(cls, keys: Mapping[object, object] | Iterable[object]) -> tuple[str, ...]:
        """Return deterministic unknown string keys from a mapping or iterable."""
        candidate_keys = tuple(keys.keys() if isinstance(keys, Mapping) else keys)
        if not all(isinstance(key, str) for key in candidate_keys):
            raise TypeError("configuration keys must be strings")
        string_keys = cast("tuple[str, ...]", candidate_keys)
        return tuple(sorted(set(string_keys) - cls.known_keys()))


@dataclass(frozen=True, slots=True, repr=False)
class SecretReference:
    """Reference to a secret held by an external protected source."""

    reference: str
    redacted: ClassVar[str] = "<secret-reference>"

    def __post_init__(self) -> None:
        if not isinstance(self.reference, str):
            raise TypeError("reference must be a string")
        if not self.reference.strip():
            raise ValueError("Secret reference must not be empty")

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.redacted!r})"

    def __str__(self) -> str:
        return self.redacted


@dataclass(frozen=True, slots=True)
class ScannerConfig(ConfigModel):
    """Project discovery limits and safe traversal behavior."""

    exclude_patterns: tuple[str, ...] = ()
    use_default_exclusions: bool = True
    follow_symlinks: bool = False
    max_file_size_bytes: int = 1_000_000
    max_depth: int | None = None

    def __post_init__(self) -> None:
        patterns = tuple(self.exclude_patterns)
        if any(not isinstance(pattern, str) or not pattern.strip() for pattern in patterns):
            raise ValueError("Scanner exclusion patterns must be non-empty strings")
        if self.max_file_size_bytes <= 0:
            raise ValueError("max_file_size_bytes must be positive")
        if self.max_depth is not None and self.max_depth < 0:
            raise ValueError("max_depth must not be negative")
        object.__setattr__(self, "exclude_patterns", patterns)


@dataclass(frozen=True, slots=True)
class IndexerConfig(ConfigModel):
    """Project indexing behavior."""

    enabled: bool = True
    cache_enabled: bool = True


@dataclass(frozen=True, slots=True)
class RetrieverConfig(ConfigModel):
    """Limits applied to task-specific retrieval."""

    max_results: int = 20

    def __post_init__(self) -> None:
        if self.max_results <= 0:
            raise ValueError("max_results must be positive")


@dataclass(frozen=True, slots=True)
class ContextConfig(ConfigModel):
    """Limits for building immutable context bundles."""

    max_tokens: int = 16_000

    def __post_init__(self) -> None:
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")


@dataclass(frozen=True, slots=True)
class PromptConfig(ConfigModel):
    """Provider-independent prompt construction behavior."""

    require_structured_output: bool = True
    max_input_tokens: int = 32_000

    def __post_init__(self) -> None:
        if self.max_input_tokens <= 0:
            raise ValueError("max_input_tokens must be positive")


@dataclass(frozen=True, slots=True)
class ProviderConfig(ConfigModel):
    """Provider selection containing references rather than credential values."""

    provider_id: str = "ollama"
    model_id: str | None = None
    credential_reference: SecretReference | None = field(default=None, repr=False)
    allow_remote: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.provider_id, str):
            raise TypeError("provider_id must be a string")
        if not self.provider_id.strip():
            raise ValueError("provider_id must not be empty")
        if self.model_id is not None and (
            not isinstance(self.model_id, str) or not self.model_id.strip()
        ):
            raise ValueError("model_id must be a non-empty string when provided")
        if self.credential_reference is not None and not isinstance(
            self.credential_reference, SecretReference
        ):
            raise TypeError("credential_reference must be a SecretReference")


@dataclass(frozen=True, slots=True)
class PatchConfig(ConfigModel):
    """Safe patch proposal and application policy."""

    require_approval: bool = True
    allow_file_creation: bool = True
    allow_file_deletion: bool = False


@dataclass(frozen=True, slots=True)
class CliConfig(ConfigModel):
    """Terminal interaction defaults."""

    non_interactive: bool = False
    machine_readable: bool = False


@dataclass(frozen=True, slots=True)
class ProjectConfig(ConfigModel):
    """Complete typed project configuration composed from capability groups."""

    scanner: ScannerConfig = field(default_factory=ScannerConfig)
    indexer: IndexerConfig = field(default_factory=IndexerConfig)
    retriever: RetrieverConfig = field(default_factory=RetrieverConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    prompt: PromptConfig = field(default_factory=PromptConfig)
    provider: ProviderConfig = field(default_factory=ProviderConfig)
    patch: PatchConfig = field(default_factory=PatchConfig)
    cli: CliConfig = field(default_factory=CliConfig)
