"""ContextForge command-line entry point."""

from pathlib import Path
from typing import Annotated

import typer

from contextforge import __version__
from contextforge.cli.options import GlobalOptions

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
    ctx: typer.Context,
    project: Annotated[
        Path | None,
        typer.Option(
            "--project",
            help="Use this project path without resolving it during parsing.",
        ),
    ] = None,
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Use this explicit configuration file."),
    ] = None,
    profile: Annotated[
        str | None,
        typer.Option("--profile", help="Select a named configuration profile."),
    ] = None,
    provider: Annotated[
        str | None,
        typer.Option("--provider", help="Select a configured provider identifier."),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option("--model", help="Select a provider model identifier."),
    ] = None,
    output_format: Annotated[
        str | None,
        typer.Option("--format", help="Select the requested output format."),
    ] = None,
    non_interactive: Annotated[
        bool,
        typer.Option(
            "--non-interactive",
            help="Disable interactive input.",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", help="Request verbose presentation."),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", help="Request minimal presentation."),
    ] = False,
    debug: Annotated[
        bool,
        typer.Option("--debug", help="Request debug diagnostics."),
    ] = False,
    no_color: Annotated[
        bool,
        typer.Option("--no-color", help="Disable terminal color output."),
    ] = False,
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
    """Parse global ContextForge command-line options."""
    ctx.obj = GlobalOptions(
        project=project,
        config=config,
        profile=profile,
        provider=provider,
        model=model,
        output_format=output_format,
        non_interactive=non_interactive,
        verbose=verbose,
        quiet=quiet,
        debug=debug,
        no_color=no_color,
    )


def main() -> None:
    """Run the ContextForge CLI adapter."""
    app()
