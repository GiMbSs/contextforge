"""Tests for CF-014 increment I017 deterministic ignore policy."""

import pytest

from contextforge.configuration import ScannerConfig
from contextforge.domain import ArtifactPath, ProjectPath
from contextforge.scanner import (
    IgnoreAction,
    IgnorePolicy,
    IgnoreRule,
    IgnoreRuleSource,
)


@pytest.mark.parametrize(
    "path",
    [
        ".git/config",
        "packages/app/.git/HEAD",
        ".venv/Lib/site-packages/module.py",
        "packages/app/venv/bin/python",
        "node_modules/package/index.js",
        "build/output.whl",
        "dist/contextforge.tar.gz",
        "target/debug/contextforge",
    ],
)
def test_safe_defaults_ignore_metadata_dependencies_and_build_outputs(path: str) -> None:
    decision = IgnorePolicy.from_inputs(ScannerConfig()).evaluate(ArtifactPath(path))

    assert decision.is_excluded
    assert decision.matched_rule is not None
    assert decision.matched_rule.source is IgnoreRuleSource.DEFAULT


def test_defaults_can_be_disabled_explicitly() -> None:
    policy = IgnorePolicy.from_inputs(ScannerConfig(use_default_exclusions=False))

    assert not policy.evaluate(ArtifactPath(".git/config")).is_excluded


def test_nested_rule_applies_only_below_its_base_path() -> None:
    nested_rule = IgnoreRule(
        "generated/",
        IgnoreRuleSource.VERSION_CONTROL,
        IgnoreAction.EXCLUDE,
        base_path=ProjectPath("packages/app"),
    )
    policy = IgnorePolicy((nested_rule,))

    assert policy.evaluate(ArtifactPath("packages/app/generated/output.py")).is_excluded
    assert not policy.evaluate(ArtifactPath("packages/other/generated/output.py")).is_excluded


def test_last_applicable_version_control_rule_wins() -> None:
    exclude = IgnoreRule.from_gitignore("*.log")
    include = IgnoreRule.from_gitignore("!keep.log")
    assert exclude is not None
    assert include is not None
    policy = IgnorePolicy((exclude, include))

    assert policy.evaluate(ArtifactPath("logs/error.log")).is_excluded
    decision = policy.evaluate(ArtifactPath("logs/keep.log"))
    assert not decision.is_excluded
    assert decision.matched_rule == include


def test_comments_and_blank_gitignore_lines_are_ignored() -> None:
    assert IgnoreRule.from_gitignore("") is None
    assert IgnoreRule.from_gitignore("  # generated files") is None


def test_mandatory_security_exclusion_cannot_be_overridden() -> None:
    mandatory = IgnoreRule(
        "secrets/",
        IgnoreRuleSource.MANDATORY_SECURITY,
        IgnoreAction.EXCLUDE,
    )
    include = IgnoreRule(
        "secrets/public.txt",
        IgnoreRuleSource.USER_INCLUSION,
        IgnoreAction.INCLUDE,
    )
    policy = IgnorePolicy((mandatory, include))

    decision = policy.evaluate(ArtifactPath("secrets/public.txt"))

    assert decision.is_excluded
    assert decision.matched_rule == mandatory


def test_explicit_include_overrides_lower_precedence_default() -> None:
    policy = IgnorePolicy.from_inputs(
        ScannerConfig(),
        user_inclusions=("build/keep.txt",),
    )

    decision = policy.evaluate(ArtifactPath("build/keep.txt"))

    assert not decision.is_excluded
    assert decision.matched_rule is not None
    assert decision.matched_rule.source is IgnoreRuleSource.USER_INCLUSION


def test_explicit_exclusion_has_priority_over_explicit_inclusion() -> None:
    policy = IgnorePolicy.from_inputs(
        ScannerConfig(use_default_exclusions=False),
        user_exclusions=("private/**",),
        user_inclusions=("private/public.txt",),
    )

    decision = policy.evaluate(ArtifactPath("private/public.txt"))

    assert decision.is_excluded
    assert decision.matched_rule is not None
    assert decision.matched_rule.source is IgnoreRuleSource.USER_EXCLUSION


def test_include_override_can_be_disabled_by_policy() -> None:
    policy = IgnorePolicy.from_inputs(
        ScannerConfig(),
        user_inclusions=("build/keep.txt",),
        allow_include_overrides=False,
    )

    assert policy.evaluate(ArtifactPath("build/keep.txt")).is_excluded


def test_project_configuration_overrides_version_control_rule() -> None:
    vcs_include = IgnoreRule.from_gitignore("!generated/output.py")
    assert vcs_include is not None
    policy = IgnorePolicy.from_inputs(
        ScannerConfig(
            exclude_patterns=("generated/**",),
            use_default_exclusions=False,
        ),
        version_control_rules=(vcs_include,),
    )

    decision = policy.evaluate(ArtifactPath("generated/output.py"))

    assert decision.is_excluded
    assert decision.matched_rule is not None
    assert decision.matched_rule.source is IgnoreRuleSource.PROJECT


def test_directory_rule_matches_directory_and_descendants() -> None:
    rule = IgnoreRule(
        "cache/",
        IgnoreRuleSource.PROJECT,
        IgnoreAction.EXCLUDE,
    )
    policy = IgnorePolicy((rule,))

    assert policy.evaluate(ArtifactPath("cache"), is_directory=True).is_excluded
    assert policy.evaluate(ArtifactPath("cache/data.bin")).is_excluded
    assert policy.evaluate(ArtifactPath("src/cache/data.bin")).is_excluded


def test_double_star_matches_nested_segments() -> None:
    rule = IgnoreRule(
        "reports/**/raw/*.json",
        IgnoreRuleSource.PROJECT,
        IgnoreAction.EXCLUDE,
    )
    policy = IgnorePolicy((rule,))

    assert policy.evaluate(ArtifactPath("reports/raw/data.json")).is_excluded
    assert policy.evaluate(ArtifactPath("reports/2026/july/raw/data.json")).is_excluded
    assert not policy.evaluate(ArtifactPath("reports/2026/july/data.json")).is_excluded


def test_invalid_patterns_are_rejected() -> None:
    with pytest.raises(ValueError, match="parent traversal"):
        IgnoreRule("../outside", IgnoreRuleSource.PROJECT, IgnoreAction.EXCLUDE)
    with pytest.raises(ValueError, match="project-relative"):
        IgnoreRule("C:/absolute", IgnoreRuleSource.PROJECT, IgnoreAction.EXCLUDE)


def test_rule_order_is_deterministic() -> None:
    first = IgnoreRule.from_gitignore("*.tmp")
    last = IgnoreRule.from_gitignore("!keep.tmp")
    assert first is not None
    assert last is not None

    for _ in range(5):
        decision = IgnorePolicy((first, last)).evaluate(ArtifactPath("keep.tmp"))
        assert decision.matched_rule == last
