"""ContextForge command-line entry point."""

import os
from pathlib import Path
from typing import Annotated

import typer

from contextforge import __version__
from contextforge.adapters.evaluation import (
    FilesystemEvaluationCaseExecutor,
    FilesystemEvaluationReportWriter,
    FilesystemEvaluationSuiteLoader,
)
from contextforge.adapters.project_commands import (
    CliExitCode,
    LocalProjectCommandGateway,
    render_result,
    resolve_cli_project,
)
from contextforge.cli.options import GlobalOptions
from contextforge.configuration import ProviderConfig
from contextforge.evaluation import (
    EvaluationRunner,
    MetricThreshold,
    evaluate_regression_gate,
    sanitize_report_text,
)

app = typer.Typer(
    name="contextforge",
    help="Build precise, traceable context for software-engineering tasks.",
    no_args_is_help=True,
    add_completion=False,
)
_gateway = LocalProjectCommandGateway()
context_app = typer.Typer(help="Inspect persisted Context Bundles.")
app.add_typer(context_app, name="context")
prompt_app = typer.Typer(help="Inspect safe persisted prompt representations.")
app.add_typer(prompt_app, name="prompt")
provider_app = typer.Typer(help="Inspect configured inference providers.")
app.add_typer(provider_app, name="provider")
patch_app = typer.Typer(help="Inspect persisted patch proposals.")
app.add_typer(patch_app, name="patch")
config_app = typer.Typer(help="Inspect and update effective configuration.")
app.add_typer(config_app, name="config")
execution_app = typer.Typer(help="Inspect, resume, and cancel persisted executions.")
app.add_typer(execution_app, name="execution")
lock_app = typer.Typer(help="Inspect and explicitly recover project locks.")
app.add_typer(lock_app, name="lock")


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


def _execution_command(
    ctx: typer.Context,
    operation: str,
    execution_id: str | None,
) -> None:
    options = ctx.ensure_object(GlobalOptions)
    root, failure = resolve_cli_project(options.project)
    if failure is not None:
        render_result(failure, output_format=options.output_format)
        raise typer.Exit(int(failure.exit_code))
    if root is None:
        raise typer.Exit(int(CliExitCode.PROJECT_RESOLUTION_FAILURE))
    result = _gateway.inspect_execution(root, operation, execution_id)
    render_result(result, output_format=options.output_format)
    if result.exit_code is not CliExitCode.SUCCESS:
        raise typer.Exit(int(result.exit_code))


@execution_app.command("show")
def execution_show(
    ctx: typer.Context,
    execution_id: Annotated[
        str | None,
        typer.Argument(help="Execution identifier; defaults to the latest."),
    ] = None,
) -> None:
    """Show a persisted execution and its stage outcomes."""
    _execution_command(ctx, "show", execution_id)


@execution_app.command("list")
def execution_list(ctx: typer.Context) -> None:
    """List persisted executions for the resolved project."""
    _execution_command(ctx, "list", None)


@execution_app.command("cancel")
def execution_cancel(
    ctx: typer.Context,
    execution_id: Annotated[
        str | None,
        typer.Argument(help="Execution identifier; defaults to the latest."),
    ] = None,
) -> None:
    """Cancel a persisted running execution."""
    _execution_command(ctx, "cancel", execution_id)


@execution_app.command("resume")
def execution_resume(
    ctx: typer.Context,
    execution_id: Annotated[
        str | None,
        typer.Argument(help="Execution identifier; defaults to the latest."),
    ] = None,
) -> None:
    """Reconstruct deterministic stages and stop before provider invocation."""
    _execution_command(ctx, "resume", execution_id)


@execution_app.command("invoke")
def execution_invoke(
    ctx: typer.Context,
    execution_id: Annotated[
        str | None,
        typer.Argument(help="Execution identifier; defaults to the latest."),
    ] = None,
    confirm: Annotated[
        bool,
        typer.Option("--confirm", help="Authorize one external provider invocation."),
    ] = False,
) -> None:
    """Explicitly invoke the provider once for a prepared execution."""
    options = ctx.ensure_object(GlobalOptions)
    root, failure = resolve_cli_project(options.project)
    if failure is not None:
        render_result(failure, output_format=options.output_format)
        raise typer.Exit(int(failure.exit_code))
    if root is None:
        raise typer.Exit(int(CliExitCode.PROJECT_RESOLUTION_FAILURE))
    result = _gateway.invoke_execution(
        root,
        execution_id,
        confirmed=confirm,
        explicit_config=options.config,
    )
    render_result(result, output_format=options.output_format)
    if result.exit_code is not CliExitCode.SUCCESS:
        raise typer.Exit(int(result.exit_code))


@execution_app.command("validate")
def execution_validate(
    ctx: typer.Context,
    execution_id: Annotated[
        str | None,
        typer.Argument(help="Execution identifier; defaults to the latest."),
    ] = None,
) -> None:
    """Validate a persisted response without invoking the provider."""
    options = ctx.ensure_object(GlobalOptions)
    root, failure = resolve_cli_project(options.project)
    if failure is not None:
        render_result(failure, output_format=options.output_format)
        raise typer.Exit(int(failure.exit_code))
    if root is None:
        raise typer.Exit(int(CliExitCode.PROJECT_RESOLUTION_FAILURE))
    result = _gateway.validate_execution(root, execution_id)
    render_result(result, output_format=options.output_format)
    if result.exit_code is not CliExitCode.SUCCESS:
        raise typer.Exit(int(result.exit_code))


@lock_app.command("show")
def lock_show(ctx: typer.Context) -> None:
    """Show non-secret metadata for the current project lock."""
    options = ctx.ensure_object(GlobalOptions)
    root, failure = resolve_cli_project(options.project)
    if failure is not None:
        render_result(failure, output_format=options.output_format)
        raise typer.Exit(int(failure.exit_code))
    if root is None:
        raise typer.Exit(int(CliExitCode.PROJECT_RESOLUTION_FAILURE))
    result = _gateway.manage_lock(root, "show")
    render_result(result, output_format=options.output_format)


@lock_app.command("recover")
def lock_recover(
    ctx: typer.Context,
    minimum_age_seconds: Annotated[
        int,
        typer.Option(
            "--minimum-age-seconds",
            min=1,
            help="Require the lock to be at least this old.",
        ),
    ] = 3600,
    force: Annotated[
        bool,
        typer.Option("--force", help="Confirm explicit abandoned-lock recovery."),
    ] = False,
) -> None:
    """Recover an old lock only after confirming its owner process is dead."""
    options = ctx.ensure_object(GlobalOptions)
    if not force:
        raise typer.BadParameter("--force is required for lock recovery")
    root, failure = resolve_cli_project(options.project)
    if failure is not None:
        render_result(failure, output_format=options.output_format)
        raise typer.Exit(int(failure.exit_code))
    if root is None:
        raise typer.Exit(int(CliExitCode.PROJECT_RESOLUTION_FAILURE))
    result = _gateway.manage_lock(
        root,
        "recover",
        minimum_age_seconds=minimum_age_seconds,
    )
    render_result(result, output_format=options.output_format)
    if result.exit_code is not CliExitCode.SUCCESS:
        raise typer.Exit(int(result.exit_code))


@app.command()
def scan(ctx: typer.Context) -> None:
    """Scan the resolved project through the scanner service."""
    _execute_project_command(ctx, "scan")


@app.command()
def index(ctx: typer.Context) -> None:
    """Build a project index from a current scan."""
    _execute_project_command(ctx, "index")


def _evaluation_loader(suite_path: Path) -> tuple[FilesystemEvaluationSuiteLoader, Path]:
    try:
        resolved = suite_path.resolve(strict=True)
    except OSError as error:
        raise ValueError("evaluation suite does not exist") from error
    if not resolved.is_file():
        raise ValueError("evaluation suite must be a regular file")
    for candidate in resolved.parents:
        if candidate.joinpath("projects").is_dir():
            return FilesystemEvaluationSuiteLoader(candidate), resolved.relative_to(candidate)
    raise ValueError("evaluation suite must be below a root containing projects/")


def _parse_thresholds(
    minimum_values: list[str] | None,
    maximum_values: list[str] | None,
) -> tuple[MetricThreshold, ...]:
    thresholds: list[MetricThreshold] = []
    for bound_name, values in (
        ("minimum", minimum_values),
        ("maximum", maximum_values),
    ):
        for value in values or ():
            metric_name, separator, serialized_bound = value.partition("=")
            if not separator or not metric_name.strip():
                raise ValueError(f"thresholds must use METRIC={bound_name.upper()}")
            try:
                bound = float(serialized_bound)
            except ValueError as error:
                raise ValueError(f"threshold {bound_name} must be numeric") from error
            thresholds.append(
                MetricThreshold(
                    metric_name.strip(),
                    minimum=bound if bound_name == "minimum" else None,
                    maximum=bound if bound_name == "maximum" else None,
                )
            )
    if len({item.metric_name for item in thresholds}) != len(thresholds):
        raise ValueError("threshold metric names must be unique")
    return tuple(thresholds)


@app.command()
def evaluate(
    suite: Annotated[Path, typer.Argument(help="Versioned evaluation suite JSON.")],
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            help="Output path stem for JSON and Markdown reports.",
        ),
    ] = Path(".contextforge/evaluations/latest"),
    case: Annotated[
        list[str] | None,
        typer.Option("--case", help="Run only this case identifier; repeatable."),
    ] = None,
    tag: Annotated[
        list[str] | None,
        typer.Option("--tag", help="Require this case tag; repeatable."),
    ] = None,
    minimum: Annotated[
        list[str] | None,
        typer.Option(
            "--minimum",
            help="Require a primary aggregate METRIC=MINIMUM; repeatable and opt-in.",
        ),
    ] = None,
    maximum: Annotated[
        list[str] | None,
        typer.Option(
            "--maximum",
            help="Require a primary aggregate METRIC=MAXIMUM; repeatable and opt-in.",
        ),
    ] = None,
    fail_on_case_error: Annotated[
        bool,
        typer.Option(
            "--fail-on-case-error",
            help="Exit with code 19 when any selected evaluation case fails.",
        ),
    ] = False,
) -> None:
    """Run a deterministic, read-only effectiveness evaluation."""
    try:
        loader, relative_suite = _evaluation_loader(suite)
        thresholds = _parse_thresholds(minimum, maximum)
        evaluation_suite = loader.load(relative_suite)
        result = EvaluationRunner(
            FilesystemEvaluationCaseExecutor(loader),
            configuration=(("mode", "offline"),),
            source_revision=os.environ.get("GITHUB_SHA"),
        ).run(
            evaluation_suite,
            case_ids=tuple(case or ()),
            tags=tuple(tag or ()),
        )
        output_parent = output.parent.resolve()
        output_parent.mkdir(parents=True, exist_ok=True)
        paths = FilesystemEvaluationReportWriter(output_parent).write(result, output.name)
    except (OSError, TypeError, ValueError) as error:
        typer.echo(f"Evaluation failed: {sanitize_report_text(str(error))}", err=True)
        raise typer.Exit(int(CliExitCode.EVALUATION_FAILURE)) from error

    typer.echo(
        f"Evaluation completed: {len(result.cases)} cases, "
        f"{sum(record.status.value == 'failed' for record in result.cases)} failed"
    )
    typer.echo(f"JSON report: {paths.json_path}")
    typer.echo(f"Markdown report: {paths.markdown_path}")
    failed_cases = tuple(record for record in result.cases if record.status.value == "failed")
    if fail_on_case_error and failed_cases:
        for record in failed_cases:
            typer.echo(
                f"Evaluation case failed: {record.case_id}: "
                f"{sanitize_report_text(record.error_message or 'Case execution failed')}",
                err=True,
            )
        raise typer.Exit(int(CliExitCode.EVALUATION_FAILURE))
    gate = evaluate_regression_gate(result, thresholds)
    if not gate.passed:
        for failure in gate.failures:
            actual = "missing" if failure.actual is None else f"{failure.actual:.6f}"
            if failure.minimum is not None:
                bound = f"minimum {failure.minimum:.6f}"
            else:
                assert failure.maximum is not None
                bound = f"maximum {failure.maximum:.6f}"
            typer.echo(
                f"Regression: {failure.metric_name}={actual} ({bound})",
                err=True,
            )
        raise typer.Exit(int(CliExitCode.EVALUATION_REGRESSION))


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
    """Execute one explicitly sourced analysis or patch-proposal task."""
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
    operation = _gateway.analyze if analysis_only else _gateway.propose
    result = operation(root, task_text, options.provider or "mock-provider", options.config)
    render_result(result, output_format=options.output_format)


def _inspect_context(
    ctx: typer.Context,
    operation: str,
    *,
    target: str | None = None,
    destination: Path | None = None,
) -> None:
    options = ctx.ensure_object(GlobalOptions)
    root, failure = resolve_cli_project(options.project)
    if failure is not None:
        render_result(failure, output_format=options.output_format)
        raise typer.Exit(int(failure.exit_code))
    if root is None:
        raise typer.Exit(int(CliExitCode.PROJECT_RESOLUTION_FAILURE))
    result = _gateway.inspect_context(
        root,
        operation,
        target=target,
        destination=destination,
    )
    render_result(result, output_format=options.output_format)
    if result.exit_code is not CliExitCode.SUCCESS:
        raise typer.Exit(int(result.exit_code))


@context_app.command("show")
def context_show(ctx: typer.Context) -> None:
    """Show the latest persisted Context Bundle summary."""
    _inspect_context(ctx, "show")


@context_app.command("list")
def context_list(ctx: typer.Context) -> None:
    """List items from the latest persisted Context Bundle."""
    _inspect_context(ctx, "list")


@context_app.command("explain")
def context_explain(
    ctx: typer.Context,
    target: Annotated[str, typer.Argument(help="Context item identifier or project path.")],
) -> None:
    """Explain persisted selection evidence for one context item."""
    _inspect_context(ctx, "explain", target=target)


@context_app.command("export")
def context_export(
    ctx: typer.Context,
    destination: Annotated[
        Path | None,
        typer.Option("--output", help="Explicit UTF-8 JSON destination."),
    ] = None,
) -> None:
    """Export the latest persisted Context Bundle."""
    _inspect_context(ctx, "export", destination=destination)


def _inspect_prompt(
    ctx: typer.Context,
    operation: str,
    *,
    destination: Path | None = None,
) -> None:
    options = ctx.ensure_object(GlobalOptions)
    root, failure = resolve_cli_project(options.project)
    if failure is not None:
        render_result(failure, output_format=options.output_format)
        raise typer.Exit(int(failure.exit_code))
    if root is None:
        raise typer.Exit(int(CliExitCode.PROJECT_RESOLUTION_FAILURE))
    result = _gateway.inspect_prompt(root, operation, destination=destination)
    render_result(result, output_format=options.output_format)
    if result.exit_code is not CliExitCode.SUCCESS:
        raise typer.Exit(int(result.exit_code))


@prompt_app.command("preview")
def prompt_preview(ctx: typer.Context) -> None:
    """Preview the latest persisted prompt with sensitive content redacted."""
    _inspect_prompt(ctx, "preview")


@prompt_app.command("measure")
def prompt_measure(ctx: typer.Context) -> None:
    """Show measurements for the latest persisted prompt."""
    _inspect_prompt(ctx, "measure")


@prompt_app.command("export")
def prompt_export(
    ctx: typer.Context,
    destination: Annotated[
        Path | None,
        typer.Option("--output", help="Explicit UTF-8 JSON destination."),
    ] = None,
) -> None:
    """Export the latest safe persisted prompt representation."""
    _inspect_prompt(ctx, "export", destination=destination)


def _inspect_provider(
    ctx: typer.Context,
    operation: str,
    provider_id: str | None = None,
) -> None:
    options = ctx.ensure_object(GlobalOptions)
    selected_id = provider_id or options.provider
    root, failure = resolve_cli_project(options.project)
    if failure is not None:
        render_result(failure, output_format=options.output_format)
        raise typer.Exit(int(failure.exit_code))
    config = _provider_config(options)
    result = _gateway.inspect_provider(
        operation,
        selected_id,
        root,
        options.config,
        config,
    )
    render_result(result, output_format=options.output_format)
    if result.exit_code is not CliExitCode.SUCCESS:
        raise typer.Exit(int(result.exit_code))


def _provider_config(options: GlobalOptions) -> ProviderConfig | None:
    """Override the effective provider configuration from the CLI selection."""
    if options.provider is None:
        return None
    return ProviderConfig(
        provider_id=options.provider,
        execution_mode="local",
    )


@provider_app.command("list")
def provider_list(ctx: typer.Context) -> None:
    """List configured providers and their capability summaries."""
    _inspect_provider(ctx, "list")


@provider_app.command("show")
def provider_show(
    ctx: typer.Context,
    provider_id: Annotated[str, typer.Argument(help="Configured provider identifier.")],
) -> None:
    """Show one provider configuration without credentials."""
    _inspect_provider(ctx, "show", provider_id)


@provider_app.command("health")
def provider_health(
    ctx: typer.Context,
    provider_id: Annotated[
        str | None,
        typer.Argument(help="Configured provider identifier."),
    ] = None,
) -> None:
    """Check provider health without transmitting project content."""
    _inspect_provider(ctx, "health", provider_id)


@provider_app.command("models")
def provider_models(
    ctx: typer.Context,
    provider_id: Annotated[
        str | None,
        typer.Argument(help="Configured provider identifier."),
    ] = None,
) -> None:
    """List available models without downloading any model."""
    _inspect_provider(ctx, "models", provider_id)


def _inspect_patch(
    ctx: typer.Context,
    operation: str,
    *,
    proposal_id: str | None = None,
    destination: Path | None = None,
) -> None:
    options = ctx.ensure_object(GlobalOptions)
    root, failure = resolve_cli_project(options.project)
    if failure is not None:
        render_result(failure, output_format=options.output_format)
        raise typer.Exit(int(failure.exit_code))
    if root is None:
        raise typer.Exit(int(CliExitCode.PROJECT_RESOLUTION_FAILURE))
    result = _gateway.inspect_patch(
        root,
        operation,
        proposal_id=proposal_id,
        destination=destination,
    )
    render_result(result, output_format=options.output_format)
    if result.exit_code is not CliExitCode.SUCCESS:
        raise typer.Exit(int(result.exit_code))


@patch_app.command("list")
def patch_list(ctx: typer.Context) -> None:
    """List persisted patch proposals."""
    _inspect_patch(ctx, "list")


@patch_app.command("show")
def patch_show(
    ctx: typer.Context,
    proposal_id: Annotated[
        str | None,
        typer.Argument(help="Proposal identifier; defaults to the latest."),
    ] = None,
) -> None:
    """Show one persisted patch proposal."""
    _inspect_patch(ctx, "show", proposal_id=proposal_id)


@patch_app.command("review")
def patch_review(
    ctx: typer.Context,
    proposal_id: Annotated[
        str | None,
        typer.Argument(help="Proposal identifier; defaults to the latest."),
    ] = None,
) -> None:
    """Review file changes and validation warnings before approval."""
    _inspect_patch(ctx, "review", proposal_id=proposal_id)


@patch_app.command("application")
def patch_application(
    ctx: typer.Context,
    proposal_id: Annotated[str, typer.Argument(help="Exact proposal identifier.")],
) -> None:
    """Inspect the durable application attempt and its current outcome."""
    _inspect_patch(ctx, "application", proposal_id=proposal_id)


@patch_app.command("export")
def patch_export(
    ctx: typer.Context,
    proposal_id: Annotated[
        str | None,
        typer.Argument(help="Proposal identifier; defaults to the latest."),
    ] = None,
    destination: Annotated[
        Path | None,
        typer.Option("--output", help="Explicit UTF-8 JSON destination."),
    ] = None,
) -> None:
    """Export one persisted patch proposal."""
    _inspect_patch(
        ctx,
        "export",
        proposal_id=proposal_id,
        destination=destination,
    )


def _authorize_patch(
    ctx: typer.Context,
    operation: str,
    proposal_id: str,
    *,
    approval_binding: str | None = None,
    reason: str | None = None,
) -> None:
    options = ctx.ensure_object(GlobalOptions)
    if options.non_interactive and operation != "approve":
        typer.echo(
            "CLI_PATCH_INTERACTIVE_REQUIRED: Interactive confirmation is required.",
            err=True,
        )
        raise typer.Exit(int(CliExitCode.GENERAL_FAILURE))
    if options.non_interactive and approval_binding is None:
        typer.echo(
            "CLI_PATCH_APPROVAL_BINDING_REQUIRED: "
            "--approve must contain the exact proposal identifier.",
            err=True,
        )
        raise typer.Exit(int(CliExitCode.GENERAL_FAILURE))
    if approval_binding is not None and approval_binding != proposal_id:
        typer.echo(
            "CLI_PATCH_APPROVAL_BINDING_MISMATCH: --approve does not match the selected proposal.",
            err=True,
        )
        raise typer.Exit(int(CliExitCode.GENERAL_FAILURE))
    if not options.non_interactive and approval_binding is not None:
        typer.echo(
            "CLI_PATCH_APPROVAL_MODE_INVALID: --approve is only accepted with --non-interactive.",
            err=True,
        )
        raise typer.Exit(int(CliExitCode.GENERAL_FAILURE))
    root, failure = resolve_cli_project(options.project)
    if failure is not None:
        render_result(failure, output_format=options.output_format)
        raise typer.Exit(int(failure.exit_code))
    if root is None:
        raise typer.Exit(int(CliExitCode.PROJECT_RESOLUTION_FAILURE))

    review_result = _gateway.inspect_patch(root, "review", proposal_id=proposal_id)
    if review_result.exit_code is not CliExitCode.SUCCESS:
        render_result(review_result, output_format=options.output_format)
        raise typer.Exit(int(review_result.exit_code))
    review = review_result.data["review"]
    if not isinstance(review, dict):
        raise typer.Exit(int(CliExitCode.GENERAL_FAILURE))
    warnings = review.get("warnings", [])
    operation_counts = review.get("operation_counts", {})
    if not options.non_interactive:
        typer.echo(f"Proposal: {proposal_id}")
        typer.echo(f"Project fingerprint: {review.get('project_fingerprint')}")
        typer.echo(f"Affected files: {len(review.get('affected_files', []))}")
        typer.echo(f"Operations: {operation_counts}")
        typer.echo(f"Warnings: {len(warnings)}")

    if options.non_interactive:
        confirmed = True
    elif operation == "approve":
        high_risk = any(
            isinstance(warning, dict) and "PROTECTED" in str(warning.get("code", ""))
            for warning in warnings
        ) or (
            isinstance(operation_counts, dict)
            and (
                int(operation_counts.get("delete", 0)) > 0
                or int(operation_counts.get("rename", 0)) > 0
            )
        )
        if high_risk:
            confirmation = typer.prompt(
                "High-risk proposal. Type the proposal identifier to approve"
            )
            confirmed = confirmation == proposal_id
        else:
            confirmed = typer.confirm("Approve this exact proposal?")
    else:
        confirmed = typer.confirm("Reject this exact proposal?")
    if not confirmed:
        typer.echo(
            "CLI_PATCH_CONFIRMATION_DECLINED: Proposal state was not changed.",
            err=True,
        )
        raise typer.Exit(int(CliExitCode.GENERAL_FAILURE))

    result = _gateway.authorize_patch(
        root,
        operation,
        proposal_id,
        approval_method=("non_interactive" if options.non_interactive else "interactive"),
        reason=reason,
    )
    render_result(result, output_format=options.output_format)
    if result.exit_code is not CliExitCode.SUCCESS:
        raise typer.Exit(int(result.exit_code))


@patch_app.command("approve")
def patch_approve(
    ctx: typer.Context,
    proposal_id: Annotated[str, typer.Argument(help="Exact proposal identifier.")],
    approval_binding: Annotated[
        str | None,
        typer.Option(
            "--approve",
            help="Repeat the exact proposal identifier in non-interactive mode.",
        ),
    ] = None,
) -> None:
    """Interactively approve one exact persisted proposal."""
    _authorize_patch(
        ctx,
        "approve",
        proposal_id,
        approval_binding=approval_binding,
    )


@patch_app.command("reject")
def patch_reject(
    ctx: typer.Context,
    proposal_id: Annotated[str, typer.Argument(help="Exact proposal identifier.")],
    reason: Annotated[
        str | None,
        typer.Option("--reason", help="Auditable rejection reason."),
    ] = None,
) -> None:
    """Interactively reject one exact persisted proposal."""
    _authorize_patch(ctx, "reject", proposal_id, reason=reason)


@patch_app.command("apply")
def patch_apply(
    ctx: typer.Context,
    proposal_id: Annotated[str, typer.Argument(help="Exact approved proposal identifier.")],
) -> None:
    """Apply an approved proposal through the authorized application service."""
    options = ctx.ensure_object(GlobalOptions)
    root, failure = resolve_cli_project(options.project)
    if failure is not None:
        render_result(failure, output_format=options.output_format)
        raise typer.Exit(int(failure.exit_code))
    if root is None:
        raise typer.Exit(int(CliExitCode.PROJECT_RESOLUTION_FAILURE))
    result = _gateway.apply_patch_proposal(root, proposal_id)
    render_result(result, output_format=options.output_format)
    if result.exit_code is not CliExitCode.SUCCESS:
        raise typer.Exit(int(result.exit_code))


@patch_app.command("reconcile")
def patch_reconcile(
    ctx: typer.Context,
    proposal_id: Annotated[str, typer.Argument(help="Exact proposal identifier.")],
    outcome: Annotated[
        str,
        typer.Option(
            "--outcome",
            help="Observed outcome: applied or rolled-back.",
        ),
    ],
    confirmation: Annotated[
        str,
        typer.Option(
            "--confirm",
            help="Repeat the exact proposal identifier.",
        ),
    ],
    recovery_reference: Annotated[
        str,
        typer.Option(
            "--recovery-reference",
            help="Auditable operator evidence or recovery reference.",
        ),
    ],
) -> None:
    """Resolve an unknown patch application outcome after manual inspection."""
    options = ctx.ensure_object(GlobalOptions)
    if confirmation != proposal_id:
        typer.echo(
            "CLI_PATCH_RECONCILIATION_CONFIRMATION_MISMATCH: "
            "--confirm does not match the selected proposal.",
            err=True,
        )
        raise typer.Exit(int(CliExitCode.INVALID_USAGE))
    normalized_outcome = outcome.replace("-", "_")
    if normalized_outcome not in ("applied", "rolled_back"):
        typer.echo(
            "CLI_PATCH_RECONCILIATION_OUTCOME_INVALID: --outcome must be applied or rolled-back.",
            err=True,
        )
        raise typer.Exit(int(CliExitCode.INVALID_USAGE))
    if not recovery_reference.strip():
        typer.echo(
            "CLI_PATCH_RECONCILIATION_REFERENCE_REQUIRED: --recovery-reference must not be empty.",
            err=True,
        )
        raise typer.Exit(int(CliExitCode.INVALID_USAGE))
    root, failure = resolve_cli_project(options.project)
    if failure is not None:
        render_result(failure, output_format=options.output_format)
        raise typer.Exit(int(failure.exit_code))
    if root is None:
        raise typer.Exit(int(CliExitCode.PROJECT_RESOLUTION_FAILURE))
    result = _gateway.reconcile_patch_application(
        root,
        proposal_id,
        outcome=normalized_outcome,
        recovery_reference=recovery_reference,
    )
    render_result(result, output_format=options.output_format)
    if result.exit_code is not CliExitCode.SUCCESS:
        raise typer.Exit(int(result.exit_code))


def _configure(
    ctx: typer.Context,
    operation: str,
    *,
    key: str | None = None,
    value: str | None = None,
    user_scope: bool = False,
) -> None:
    options = ctx.ensure_object(GlobalOptions)
    root, failure = resolve_cli_project(options.project)
    if failure is not None:
        render_result(failure, output_format=options.output_format)
        raise typer.Exit(int(failure.exit_code))
    if root is None:
        raise typer.Exit(int(CliExitCode.PROJECT_RESOLUTION_FAILURE))
    result = _gateway.configure(
        root,
        operation,
        key=key,
        value=value,
        explicit=options.config,
        user_scope=user_scope,
    )
    render_result(result, output_format=options.output_format)
    if result.exit_code is not CliExitCode.SUCCESS:
        raise typer.Exit(int(result.exit_code))


@config_app.command("show")
def config_show(ctx: typer.Context) -> None:
    """Show effective configuration with source attribution."""
    _configure(ctx, "show")


@config_app.command("get")
def config_get(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Canonical dotted configuration key.")],
) -> None:
    """Show one effective redacted configuration value."""
    _configure(ctx, "get", key=key)


@config_app.command("set")
def config_set(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Canonical dotted configuration key.")],
    value: Annotated[str, typer.Argument(help="TOML scalar or string value.")],
    user_scope: Annotated[
        bool,
        typer.Option("--user", help="Write user configuration instead of project configuration."),
    ] = False,
) -> None:
    """Atomically update one validated non-secret configuration value."""
    _configure(ctx, "set", key=key, value=value, user_scope=user_scope)


@config_app.command("validate")
def config_validate(ctx: typer.Context) -> None:
    """Validate configuration syntax, keys, and value types."""
    _configure(ctx, "validate")


@config_app.command("paths")
def config_paths(ctx: typer.Context) -> None:
    """Show configuration search paths."""
    _configure(ctx, "paths")


@app.command("diagnostics")
def diagnostics(ctx: typer.Context) -> None:
    """Report non-sensitive runtime and project readiness."""
    options = ctx.ensure_object(GlobalOptions)
    root, failure = resolve_cli_project(options.project)
    if failure is not None:
        render_result(failure, output_format=options.output_format)
        raise typer.Exit(int(failure.exit_code))
    if root is None:
        raise typer.Exit(int(CliExitCode.PROJECT_RESOLUTION_FAILURE))
    result = _gateway.diagnostics(root, explicit=options.config)
    render_result(result, output_format=options.output_format)
    if result.exit_code is not CliExitCode.SUCCESS:
        raise typer.Exit(int(result.exit_code))


def main() -> None:
    """Run the ContextForge CLI adapter."""
    app()
