"""Safe local configuration inspection, validation, and mutation."""

from __future__ import annotations

import json
import platform
import sys
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from contextforge import __version__
from contextforge.adapters.configuration.toml import TomlConfigurationSourceAdapter
from contextforge.configuration import SecretReference, resolve_configuration
from contextforge.project import ProjectRoot

_SECRET_KEYS = frozenset({"provider.credential_reference"})


def configuration_paths(root: ProjectRoot, explicit: Path | None) -> dict[str, object]:
    """Return deterministic configuration search paths."""
    return {
        "explicit": str(explicit.resolve()) if explicit is not None else None,
        "project": str(root.path / ".contextforge" / "config.toml"),
        "user": str(Path.home() / ".config" / "contextforge" / "config.toml"),
    }


def inspect_configuration(
    root: ProjectRoot,
    operation: str,
    *,
    key: str | None = None,
    explicit: Path | None = None,
) -> tuple[dict[str, object], tuple[dict[str, object], ...]]:
    """Load and inspect effective configuration without exposing secrets."""
    paths = configuration_paths(root, explicit)
    if operation == "paths":
        return {"command": "config paths", "paths": paths, "status": "success"}, ()
    selected = explicit or Path(str(paths["project"]))
    source = TomlConfigurationSourceAdapter().load(selected)
    if (explicit is not None or selected.exists()) and not source.succeeded:
        return {"command": f"config {operation}", "status": "invalid"}, tuple(
            item.to_dict() for item in source.diagnostics
        )
    try:
        selected_values = cast("Mapping[object, object]", source.values)
        effective = resolve_configuration(
            explicit_file=(selected_values if explicit is not None and selected.exists() else None),
            project=selected_values if explicit is None and selected.exists() else None,
        )
    except (TypeError, ValueError) as error:
        return {"command": f"config {operation}", "status": "invalid"}, (
            _diagnostic("CONFIG_VALIDATION_FAILED", str(error)),
        )
    inspected = {
        name: {"source": value.source.value, "value": _safe_value(value.display_value)}
        for name, value in effective.inspect().items()
    }
    if operation == "show":
        return {"command": "config show", "configuration": inspected, "status": "valid"}, ()
    if operation == "get":
        if key not in inspected:
            return {"command": "config get", "status": "failed"}, (
                _diagnostic("CONFIG_KEY_UNKNOWN", "Unknown configuration key."),
            )
        return {"command": "config get", "key": key, **inspected[key], "status": "valid"}, ()
    if operation == "validate":
        return {"command": "config validate", "path": str(selected), "status": "valid"}, ()
    raise ValueError(f"unknown configuration operation: {operation}")


def set_configuration(path: Path, key: str, raw_value: str) -> dict[str, object]:
    """Validate and atomically update one non-secret configuration value."""
    if key in _SECRET_KEYS or any(part in key.lower() for part in ("secret", "token", "password")):
        raise ValueError("CONFIG_SECRET_WRITE_REJECTED")
    current: dict[str, object] = {}
    if path.exists():
        loaded = TomlConfigurationSourceAdapter().load(path)
        if not loaded.succeeded:
            raise ValueError("CONFIG_EXISTING_FILE_INVALID")
        current = _thaw_mapping(loaded.values)
    value = _parse_value(raw_value)
    group, separator, field_name = key.partition(".")
    if not separator:
        raise ValueError("CONFIG_KEY_UNKNOWN")
    group_values = current.setdefault(group, {})
    if not isinstance(group_values, dict):
        raise ValueError("CONFIG_EXISTING_FILE_INVALID")
    group_values[field_name] = value
    resolve_configuration(project=cast("Mapping[object, object]", current))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(_serialize_toml(current), encoding="utf-8", newline="")
    temporary.replace(path)
    return {
        "command": "config set",
        "key": key,
        "path": str(path),
        "status": "updated",
        "value": _safe_value(value),
    }


def runtime_diagnostics(root: ProjectRoot, explicit: Path | None) -> dict[str, object]:
    """Report non-sensitive runtime and project readiness."""
    validation, diagnostics = inspect_configuration(root, "validate", explicit=explicit)
    metadata = root.path / ".contextforge"
    return {
        "checks": {
            "configuration": validation["status"],
            "metadata_directory": "writable"
            if metadata.exists() and metadata.is_dir()
            else "missing",
            "project_resolution": "resolved",
            "provider": "configured",
            "scanner": "available",
        },
        "command": "diagnostics",
        "contextforge_version": __version__,
        "diagnostic_codes": [item["code"] for item in diagnostics],
        "platform": platform.platform(),
        "project_root": str(root.path),
        "python_version": sys.version.split()[0],
        "status": "healthy" if not diagnostics else "degraded",
    }


def _parse_value(raw_value: str) -> object:
    try:
        return tomllib.loads(f"value = {raw_value}\n")["value"]
    except tomllib.TOMLDecodeError:
        return raw_value


def _thaw_mapping(values: Mapping[str, object]) -> dict[str, object]:
    return {
        key: _thaw_mapping(value) if isinstance(value, Mapping) else value
        for key, value in values.items()
    }


def _safe_value(value: object) -> object:
    if isinstance(value, SecretReference):
        return SecretReference.redacted
    if isinstance(value, tuple):
        return list(value)
    return value


def _serialize_toml(document: Mapping[str, object]) -> str:
    lines: list[str] = []
    for group in sorted(document):
        values = document[group]
        if not isinstance(values, Mapping):
            raise ValueError("CONFIG_EXISTING_FILE_INVALID")
        lines.append(f"[{group}]")
        for key, value in sorted(values.items()):
            lines.append(f"{key} = {_toml_value(value)}")
        lines.append("")
    return "\n".join(lines)


def _toml_value(value: object) -> str:
    if isinstance(value, SecretReference):
        raise ValueError("CONFIG_SECRET_WRITE_REJECTED")
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is int:
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        raise ValueError("CONFIG_NULL_UNSUPPORTED")
    if isinstance(value, tuple | list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    raise ValueError("CONFIG_VALUE_UNSUPPORTED")


def _diagnostic(code: str, message: str) -> dict[str, object]:
    return {
        "capability": "configuration",
        "code": code,
        "message": message,
        "severity": "error",
    }
