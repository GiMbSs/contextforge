"""ContextForge command-line entry point.

Increment I001 intentionally exposes only the application identity, help output,
and version information. Domain behavior belongs to later increments.
"""

from typing import Annotated

import typer

from contextforge import __version__

app = typer.Typer(
    name="contextforge",
    help="Build precise, traceable context for software-engineering tasks.",
    no_args_is_help=True,
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    """Print the package version and terminate successfully."""
    if value:
        typer.echo(f"contextforge {__version__}")
        raise typer.Exit(code=0)


@app.callback()
def root(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the installed ContextForge version and exit.",
        ),
    ] = False,
) -> None:
    """ContextForge command-line interface."""


def main() -> None:
    """Run the ContextForge CLI adapter."""
    app()
