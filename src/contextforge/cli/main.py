"""ContextForge command-line entry point."""

from pathlib import Path
from typing import Annotated

import typer

from contextforge import __version__
from contextforge.adapters.project_commands import (
    CliExitCode,
    LocalProjectCommandGateway,
    render_result,
    resolve_cli_project,
)
from contextforge.cli.options import GlobalOptions

app = typer.Typer(
    name="contextforge",
    help="Build precise, traceable context for software-engineering tasks.",
    no_args_is_help=True,
    add_completion=False,
)
_gateway = LocalProjectCommandGateway()


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


def _execute_project_command(ctx: typer.Context, command: str, path: Path | None = None) -> None:
    options = ctx.ensure_object(GlobalOptions)
    root, failure = resolve_cli_project(path if path is not None else options.project)
    if failure is not None:
        render_result(failure, output_format=options.output_format)
        raise typer.Exit(int(failure.exit_code))
    if root is None:
        raise typer.Exit(int(CliExitCode.PROJECT_RESOLUTION_FAILURE))
    result = getattr(_gateway, command)(root)
    render_result(result, output_format=options.output_format)
    if result.exit_code is not CliExitCode.SUCCESS:
        raise typer.Exit(int(result.exit_code))


@app.command("init")
def initialize(
    ctx: typer.Context,
    path: Annotated[Path | None, typer.Argument(help="Project directory to initialize.")] = None,
) -> None:
    """Initialize ContextForge metadata in a project."""
    _execute_project_command(ctx, "initialize", path)


@app.command()
def status(ctx: typer.Context) -> None:
    """Display foundational ContextForge project state."""
    _execute_project_command(ctx, "status")


@app.command()
def scan(ctx: typer.Context) -> None:
    """Scan the resolved project through the scanner service."""
    _execute_project_command(ctx, "scan")


@app.command()
def index(ctx: typer.Context) -> None:
    """Build a project index from a current scan."""
    _execute_project_command(ctx, "index")


@app.command()
def run(
    ctx: typer.Context,
    task: Annotated[str | None, typer.Argument(help="Task instruction text.")] = None,
    stdin: Annotated[
        bool,
        typer.Option("--stdin", help="Read task instructions from standard input."),
    ] = False,
    task_file: Annotated[
        Path | None,
        typer.Option("--task-file", help="Read task instructions from a UTF-8 file."),
    ] = None,
    analysis_only: Annotated[
        bool,
        typer.Option("--analysis-only", help="Require the read-only analysis pipeline."),
    ] = False,
) -> None:
    """Execute one explicitly sourced analysis-only task."""
    if not analysis_only:
        raise typer.BadParameter("--analysis-only is required in this increment")
    selected = sum((task is not None, stdin, task_file is not None))
    if selected != 1:
        raise typer.BadParameter("exactly one of TASK, --stdin, or --task-file is required")
    if stdin:
        task_text = typer.get_text_stream("stdin").read()
    elif task_file is not None:
        try:
            task_text = task_file.read_text(encoding="utf-8")
        except OSError as error:
            raise typer.BadParameter(f"task file could not be read: {task_file}") from error
    else:
        task_text = task or ""
    task_text = task_text.strip()
    if not task_text:
        raise typer.BadParameter("task input must not be empty")

    options = ctx.ensure_object(GlobalOptions)
    root, failure = resolve_cli_project(options.project)
    if failure is not None:
        render_result(failure, output_format=options.output_format)
        raise typer.Exit(int(failure.exit_code))
    if root is None:
        raise typer.Exit(int(CliExitCode.PROJECT_RESOLUTION_FAILURE))
    result = _gateway.analyze(
        root,
        task_text,
        options.provider or "mock-provider",
    )
    render_result(result, output_format=options.output_format)


def main() -> None:
    """Run the ContextForge CLI adapter."""
    app()
