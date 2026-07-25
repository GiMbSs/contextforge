"""Canonical project-relative path value objects."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Self

_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


def _normalize_project_path(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("Project-relative path must be a string")
    if "\x00" in value:
        raise ValueError("Project-relative path must not contain NUL")
    if value.startswith(("/", "\\")):
        raise ValueError("Absolute and UNC paths are not project-relative")
    if _WINDOWS_DRIVE.match(value):
        raise ValueError("Windows drive paths are not project-relative")

    normalized = unicodedata.normalize("NFC", value).replace("\\", "/")
    segments: list[str] = []
    for segment in normalized.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            raise ValueError("Parent traversal is not allowed in project-relative paths")
        segments.append(segment)
    return "/".join(segments)


@dataclass(frozen=True, slots=True, order=True)
class ProjectPath:
    """Canonical relative path within a project; empty means project root."""

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _normalize_project_path(self.value))

    def __str__(self) -> str:
        return self.value

    @property
    def is_root(self) -> bool:
        """Whether this path denotes the project root itself."""
        return not self.value

    @property
    def parts(self) -> tuple[str, ...]:
        """Return canonical path segments."""
        return tuple(self.value.split("/")) if self.value else ()

    @classmethod
    def from_string(cls, value: str) -> Self:
        """Construct and normalize a path from external text."""
        return cls(value)


@dataclass(frozen=True, slots=True, order=True)
class ArtifactPath:
    """Canonical non-empty relative path identifying a project artifact."""

    value: str

    def __post_init__(self) -> None:
        normalized = _normalize_project_path(self.value)
        if not normalized:
            raise ValueError("Artifact path must not be empty")
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value

    @property
    def parts(self) -> tuple[str, ...]:
        """Return canonical artifact path segments."""
        return tuple(self.value.split("/"))

    @classmethod
    def from_string(cls, value: str) -> Self:
        """Construct and normalize an artifact path from external text."""
        return cls(value)
