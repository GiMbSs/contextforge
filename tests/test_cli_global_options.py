"""Tests for I079 global CLI option parsing."""

import re
from pathlib import Path

from typer.testing import CliRunner

from contextforge.cli import GlobalOptions
from contextforge.cli.main import app

runner = CliRunner(env={"NO_COLOR": "1"})
ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def test_terminal_normalization_preserves_styled_option_text() -> None:
    styled = "\x1b[1m--\x1b[0m\x1b[36mproject\x1b[0m"

    assert ANSI_ESCAPE.sub("", styled) == "--project"


def test_global_options_are_immutable_raw_parser_output() -> None:
    options = GlobalOptions(
        project=Path("./relative-project"),
        config=Path("./config.toml"),
        profile="ci",
        provider="local",
        model="model-a",
        output_format="json",
        non_interactive=True,
        verbose=True,
        quiet=True,
        debug=True,
        no_color=True,
    )

    assert options.project == Path("./relative-project")
    assert options.config == Path("./config.toml")
    assert options.profile == "ci"
    assert options.provider == "local"
    assert options.model == "model-a"
    assert options.output_format == "json"
    assert options.non_interactive
    assert options.verbose
    assert options.quiet
    assert options.debug
    assert options.no_color


def test_help_exposes_every_global_option() -> None:
    result = runner.invoke(app, ["--help"], color=False)
    plain_help = ANSI_ESCAPE.sub("", result.stdout)

    assert result.exit_code == 0
    for option in (
        "--project",
        "--config",
        "--profile",
        "--provider",
        "--model",
        "--format",
        "--non-interactive",
        "--verbose",
        "--quiet",
        "--debug",
        "--no-color",
        "--version",
        "--help",
    ):
        assert option in plain_help


def test_all_global_options_are_accepted_without_business_resolution() -> None:
    result = runner.invoke(
        app,
        [
            "--project",
            "missing-project",
            "--config",
            "missing-config.toml",
            "--profile",
            "unknown-profile",
            "--provider",
            "unknown-provider",
            "--model",
            "unknown-model",
            "--format",
            "future-format",
            "--non-interactive",
            "--verbose",
            "--quiet",
            "--debug",
            "--no-color",
            "--version",
        ],
        color=False,
    )

    assert result.exit_code == 0
    assert result.stdout.strip() == "contextforge 0.1.1"
