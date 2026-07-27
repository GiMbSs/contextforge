"""Package and CLI smoke tests for CF-014 increment I001."""

import subprocess
import sys

from typer.testing import CliRunner

import contextforge
from contextforge.cli.main import app

runner = CliRunner(env={"NO_COLOR": "1"})


def test_package_imports_and_exposes_version() -> None:
    assert contextforge.__version__ == "0.1.0"


def test_version_option_exits_successfully() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "contextforge 0.1.0"


def test_help_option_exits_successfully() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Build precise, traceable context" in result.stdout
    assert "--version" in result.stdout


def test_unknown_command_returns_usage_error() -> None:
    result = runner.invoke(app, ["unknown-command"])

    assert result.exit_code == 2
    assert "No such command" in result.output


def test_module_entry_point_exposes_version() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "contextforge", "--version"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert completed.stdout.strip() == "contextforge 0.1.0"
