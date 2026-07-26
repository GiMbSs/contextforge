"""Immutable global options parsed at the CLI boundary."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def _optional_text(value: str | None, field_name: str) -> None:
    if value is not None and not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _optional_path(value: Path | None, field_name: str) -> None:
    if value is not None and not isinstance(value, Path):
        raise TypeError(f"{field_name} must be a Path or None")


def _boolean(value: bool, field_name: str) -> None:
    if type(value) is not bool:
        raise TypeError(f"{field_name} must be a boolean")


@dataclass(frozen=True, slots=True)
class GlobalOptions:
    """Raw global CLI selections with no application-layer decisions."""

    project: Path | None = None
    config: Path | None = None
    profile: str | None = None
    provider: str | None = None
    model: str | None = None
    output_format: str | None = None
    non_interactive: bool = False
    verbose: bool = False
    quiet: bool = False
    debug: bool = False
    no_color: bool = False

    def __post_init__(self) -> None:
        _optional_path(self.project, "project")
        _optional_path(self.config, "config")
        _optional_text(self.profile, "profile")
        _optional_text(self.provider, "provider")
        _optional_text(self.model, "model")
        _optional_text(self.output_format, "output_format")
        _boolean(self.non_interactive, "non_interactive")
        _boolean(self.verbose, "verbose")
        _boolean(self.quiet, "quiet")
        _boolean(self.debug, "debug")
        _boolean(self.no_color, "no_color")
