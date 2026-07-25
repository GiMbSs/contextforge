"""Deterministic project ignore policy without filesystem access."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from fnmatch import fnmatchcase

from contextforge.configuration import ScannerConfig
from contextforge.domain import ArtifactPath, ProjectPath


class IgnoreRuleSource(StrEnum):
    """Canonical exclusion precedence sources, highest first."""

    MANDATORY_SECURITY = "mandatory_security"
    USER_EXCLUSION = "user_exclusion"
    USER_INCLUSION = "user_inclusion"
    PROJECT = "project"
    VERSION_CONTROL = "version_control"
    DEFAULT = "default"


class IgnoreAction(StrEnum):
    """Eligibility action produced by an ignore rule."""

    INCLUDE = "include"
    EXCLUDE = "exclude"


_SOURCE_PRECEDENCE = {source: precedence for precedence, source in enumerate(IgnoreRuleSource)}

DEFAULT_EXCLUSION_PATTERNS: tuple[str, ...] = (
    ".git/",
    ".hg/",
    ".svn/",
    "node_modules/",
    "vendor/",
    ".venv/",
    "venv/",
    "env/",
    "__pycache__/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    "coverage/",
    "dist/",
    "build/",
    "target/",
    "out/",
    ".cache/",
    ".idea/",
    ".vscode/",
)


def _normalize_pattern(pattern: str) -> tuple[str, bool, bool]:
    if not isinstance(pattern, str):
        raise TypeError("Ignore pattern must be a string")
    normalized = pattern.strip()
    if not normalized:
        raise ValueError("Ignore pattern must not be empty")
    if "\x00" in normalized:
        raise ValueError("Ignore pattern must not contain NUL")
    if re.match(r"^[A-Za-z]:", normalized) or normalized.startswith(("//", "\\\\")):
        raise ValueError("Ignore pattern must be project-relative")

    directory_only = normalized.endswith(("/", "\\"))
    anchored = normalized.startswith(("/", "\\"))
    normalized = normalized.replace("\\", "/").strip("/")
    segments = normalized.split("/")
    if any(segment == ".." for segment in segments):
        raise ValueError("Ignore pattern must not contain parent traversal")
    normalized = "/".join(segment for segment in segments if segment not in ("", "."))
    if not normalized:
        raise ValueError("Ignore pattern must contain a matchable segment")
    return normalized, directory_only, anchored


def _match_segments(
    pattern_segments: tuple[str, ...],
    path_segments: tuple[str, ...],
) -> bool:
    if not pattern_segments:
        return not path_segments
    pattern = pattern_segments[0]
    if pattern == "**":
        return _match_segments(pattern_segments[1:], path_segments) or (
            bool(path_segments) and _match_segments(pattern_segments, path_segments[1:])
        )
    return (
        bool(path_segments)
        and fnmatchcase(path_segments[0], pattern)
        and _match_segments(pattern_segments[1:], path_segments[1:])
    )


@dataclass(frozen=True, slots=True)
class IgnoreRule:
    """One normalized ordered eligibility rule."""

    pattern: str
    source: IgnoreRuleSource
    action: IgnoreAction
    base_path: ProjectPath = field(default_factory=lambda: ProjectPath(""))
    directory_only: bool = False
    anchored: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.source, IgnoreRuleSource):
            raise TypeError("source must be an IgnoreRuleSource")
        if not isinstance(self.action, IgnoreAction):
            raise TypeError("action must be an IgnoreAction")
        if not isinstance(self.base_path, ProjectPath):
            raise TypeError("base_path must be a ProjectPath")
        pattern, inferred_directory, inferred_anchored = _normalize_pattern(self.pattern)
        object.__setattr__(self, "pattern", pattern)
        object.__setattr__(self, "directory_only", self.directory_only or inferred_directory)
        object.__setattr__(self, "anchored", self.anchored or inferred_anchored)

        if (
            self.source is IgnoreRuleSource.MANDATORY_SECURITY
            and self.action is not IgnoreAction.EXCLUDE
        ):
            raise ValueError("Mandatory security rules must exclude")
        if (
            self.source is IgnoreRuleSource.USER_EXCLUSION
            and self.action is not IgnoreAction.EXCLUDE
        ):
            raise ValueError("User exclusion rules must exclude")
        if (
            self.source is IgnoreRuleSource.USER_INCLUSION
            and self.action is not IgnoreAction.INCLUDE
        ):
            raise ValueError("User inclusion rules must include")

    @classmethod
    def from_gitignore(
        cls,
        pattern: str,
        *,
        base_path: ProjectPath | None = None,
    ) -> IgnoreRule | None:
        """Translate one supported gitignore-style line into a rule."""
        stripped = pattern.strip()
        if not stripped or stripped.startswith("#"):
            return None
        action = IgnoreAction.INCLUDE if stripped.startswith("!") else IgnoreAction.EXCLUDE
        normalized = stripped[1:] if action is IgnoreAction.INCLUDE else stripped
        return cls(
            normalized,
            IgnoreRuleSource.VERSION_CONTROL,
            action,
            ProjectPath("") if base_path is None else base_path,
        )

    def matches(self, path: ArtifactPath, *, is_directory: bool) -> bool:
        """Whether this rule applies to a canonical artifact path."""
        if not isinstance(path, ArtifactPath):
            raise TypeError("path must be an ArtifactPath")
        base_parts = self.base_path.parts
        if path.parts[: len(base_parts)] != base_parts:
            return False
        relative_parts = path.parts[len(base_parts) :]
        if not relative_parts:
            return False

        pattern_parts = tuple(self.pattern.split("/"))
        if "/" not in self.pattern and not self.anchored:
            limit = len(relative_parts) if is_directory else len(relative_parts) - 1
            directory_parts = relative_parts[:limit]
            if self.directory_only:
                return any(fnmatchcase(part, self.pattern) for part in directory_parts)
            return any(fnmatchcase(part, self.pattern) for part in relative_parts)

        candidates = (
            tuple(relative_parts[:index])
            for index in range(1, len(relative_parts) + (1 if is_directory else 0))
        )
        if self.directory_only:
            return any(_match_segments(pattern_parts, candidate) for candidate in candidates)
        return _match_segments(pattern_parts, relative_parts)


@dataclass(frozen=True, slots=True)
class IgnoreDecision:
    """Explainable eligibility result for one project artifact."""

    path: ArtifactPath
    action: IgnoreAction
    matched_rule: IgnoreRule | None = None

    @property
    def is_excluded(self) -> bool:
        """Whether the artifact is ineligible for discovery."""
        return self.action is IgnoreAction.EXCLUDE


@dataclass(frozen=True, slots=True)
class IgnorePolicy:
    """Ordered deterministic collection of project ignore rules."""

    rules: tuple[IgnoreRule, ...]
    allow_include_overrides: bool = True

    def __post_init__(self) -> None:
        rules = tuple(self.rules)
        if any(not isinstance(rule, IgnoreRule) for rule in rules):
            raise TypeError("rules must contain only IgnoreRule values")
        object.__setattr__(self, "rules", rules)

    @classmethod
    def from_inputs(
        cls,
        configuration: ScannerConfig,
        *,
        mandatory_exclusions: tuple[str, ...] = (),
        user_exclusions: tuple[str, ...] = (),
        user_inclusions: tuple[str, ...] = (),
        version_control_rules: tuple[IgnoreRule, ...] = (),
        allow_include_overrides: bool = True,
    ) -> IgnorePolicy:
        """Build a policy from already-loaded rule sources."""
        if not isinstance(configuration, ScannerConfig):
            raise TypeError("configuration must be a ScannerConfig")
        rules = [
            *(
                IgnoreRule(pattern, IgnoreRuleSource.MANDATORY_SECURITY, IgnoreAction.EXCLUDE)
                for pattern in mandatory_exclusions
            ),
            *(
                IgnoreRule(pattern, IgnoreRuleSource.USER_EXCLUSION, IgnoreAction.EXCLUDE)
                for pattern in user_exclusions
            ),
            *(
                IgnoreRule(pattern, IgnoreRuleSource.USER_INCLUSION, IgnoreAction.INCLUDE)
                for pattern in user_inclusions
            ),
            *(
                IgnoreRule(pattern, IgnoreRuleSource.PROJECT, IgnoreAction.EXCLUDE)
                for pattern in configuration.exclude_patterns
            ),
            *version_control_rules,
        ]
        if configuration.use_default_exclusions:
            rules.extend(
                IgnoreRule(pattern, IgnoreRuleSource.DEFAULT, IgnoreAction.EXCLUDE)
                for pattern in DEFAULT_EXCLUSION_PATTERNS
            )
        return cls(tuple(rules), allow_include_overrides)

    def evaluate(self, path: ArtifactPath, *, is_directory: bool = False) -> IgnoreDecision:
        """Return the highest-precedence, last-applicable decision."""
        matches = [
            (index, rule)
            for index, rule in enumerate(self.rules)
            if (self.allow_include_overrides or rule.action is IgnoreAction.EXCLUDE)
            and rule.matches(path, is_directory=is_directory)
        ]
        if not matches:
            return IgnoreDecision(path, IgnoreAction.INCLUDE)

        winning_precedence = min(_SOURCE_PRECEDENCE[rule.source] for _, rule in matches)
        winning_rule = max(
            (
                (index, rule)
                for index, rule in matches
                if _SOURCE_PRECEDENCE[rule.source] == winning_precedence
            ),
            key=lambda item: item[0],
        )[1]
        return IgnoreDecision(path, winning_rule.action, winning_rule)

    def can_prune(self, decision: IgnoreDecision) -> bool:
        """Whether an excluded directory can be skipped without hiding an override."""
        if not decision.is_excluded or decision.matched_rule is None:
            return False
        winning_rule = decision.matched_rule
        matching_indices = tuple(
            index for index, rule in enumerate(self.rules) if rule is winning_rule
        )
        if not matching_indices:
            return False
        winning_index = matching_indices[-1]
        winning_precedence = _SOURCE_PRECEDENCE[winning_rule.source]
        for index, rule in enumerate(self.rules):
            if rule.action is not IgnoreAction.INCLUDE or not self.allow_include_overrides:
                continue
            precedence = _SOURCE_PRECEDENCE[rule.source]
            if precedence < winning_precedence or (
                precedence == winning_precedence and index > winning_index
            ):
                return False
        return True
