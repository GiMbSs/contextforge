"""TOML configuration source adapter using the Python standard library."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

from contextforge.configuration.models import SecretReference
from contextforge.configuration.sources import ConfigurationLoadResult
from contextforge.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticCollection,
    DiagnosticLocation,
    DiagnosticSeverity,
)

_CAPABILITY = "configuration"


def _diagnostic(
    code: str,
    message: str,
    path: Path,
    *,
    line: int | None = None,
    column: int | None = None,
) -> Diagnostic:
    return Diagnostic(
        code=DiagnosticCode(code),
        severity=DiagnosticSeverity.ERROR,
        message=message,
        capability=_CAPABILITY,
        location=DiagnosticLocation(str(path), line=line, column=column),
    )


def _freeze_value(value: object, *, path: tuple[str, ...]) -> object:
    if isinstance(value, dict):
        return MappingProxyType(
            {key: _freeze_value(item, path=(*path, key)) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze_value(item, path=path) for item in value)
    if path == ("provider", "credential_reference") and isinstance(value, str):
        return SecretReference(value)
    return value


def _freeze_document(document: dict[str, object]) -> Mapping[str, object]:
    return MappingProxyType(
        {key: _freeze_value(value, path=(key,)) for key, value in document.items()}
    )


class TomlConfigurationSourceAdapter:
    """Read one explicit UTF-8 TOML file as inert configuration data."""

    def load(self, path: Path) -> ConfigurationLoadResult:
        """Load TOML or return a stable structured diagnostic."""
        try:
            content = path.read_bytes()
        except FileNotFoundError:
            diagnostic = _diagnostic(
                "CONFIG_FILE_NOT_FOUND",
                "Configuration file was not found.",
                path,
            )
            return ConfigurationLoadResult({}, DiagnosticCollection((diagnostic,)))
        except OSError:
            diagnostic = _diagnostic(
                "CONFIG_FILE_UNREADABLE",
                "Configuration file could not be read.",
                path,
            )
            return ConfigurationLoadResult({}, DiagnosticCollection((diagnostic,)))

        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            diagnostic = _diagnostic(
                "CONFIG_FILE_INVALID_UTF8",
                "Configuration file is not valid UTF-8.",
                path,
            )
            return ConfigurationLoadResult({}, DiagnosticCollection((diagnostic,)))

        try:
            document = tomllib.loads(text)
        except tomllib.TOMLDecodeError as error:
            line = getattr(error, "lineno", None)
            column = getattr(error, "colno", None)
            diagnostic = _diagnostic(
                "CONFIG_TOML_PARSE_ERROR",
                "Configuration file contains invalid TOML.",
                path,
                line=line if isinstance(line, int) else None,
                column=column if isinstance(line, int) and isinstance(column, int) else None,
            )
            return ConfigurationLoadResult({}, DiagnosticCollection((diagnostic,)))

        return ConfigurationLoadResult(_freeze_document(document))
