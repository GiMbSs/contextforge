"""Contracts and results for external configuration sources."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Protocol

from contextforge.diagnostics import DiagnosticCollection, DiagnosticSeverity


@dataclass(frozen=True, slots=True)
class ConfigurationLoadResult:
    """Immutable outcome of loading one external configuration source."""

    values: Mapping[str, object]
    diagnostics: DiagnosticCollection = field(default_factory=DiagnosticCollection)

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))

    @property
    def succeeded(self) -> bool:
        """Whether loading produced no error or critical diagnostic."""
        return all(
            diagnostic.severity not in (DiagnosticSeverity.ERROR, DiagnosticSeverity.CRITICAL)
            for diagnostic in self.diagnostics
        )


class ConfigurationSourceAdapter(Protocol):
    """Port for reading configuration data from an external source."""

    def load(self, path: Path) -> ConfigurationLoadResult:
        """Load one explicitly selected configuration source."""
        ...
