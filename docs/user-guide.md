# ContextForge User Guide

This guide covers the day-to-day use of ContextForge from installation through
safe patch application.

## Requirements

- Python 3.12 or newer
- Git
- A local Ollama installation (optional, for inference)

## Installation

Create and activate a virtual environment, then install the package:

```bash
python -m venv .venv
python -m pip install --upgrade pip
python -m pip install -e .
```

Verify the CLI:

```bash
python -m contextforge --help
python -m contextforge --version
contextforge --version
```

## Project initialization

ContextForge stores per-project metadata under `.contextforge/`. Initialize it
from the project root:

```bash
contextforge init
```

To initialize a different directory:

```bash
contextforge init /path/to/project
```

## Configuration

Configuration is resolved in the following order, highest priority first:

1. CLI arguments
2. Explicit `--config` file
3. Named `--profile`
4. `.contextforge/config.toml` in the project
5. `~/.config/contextforge/config.toml` user config
6. Environment variables
7. Built-in defaults

Edit `.contextforge/config.toml` to change project behavior:

```toml
[scanner]
exclude_patterns = [".venv/", "dist/", "*.log"]

[provider]
provider_id = "ollama"
model_id = "qwen2.5-coder:7b"
endpoint = "http://localhost:11434"
execution_mode = "local"
timeout_seconds = 30.0
```

Secrets must be referenced, never written as plain text:

```toml
[provider]
credential_reference = "env:CONTEXTFORGE_API_KEY"
```

Show the effective configuration:

```bash
contextforge config show
```

Secret values are redacted in the output.

## Local provider setup

ContextForge can talk to an Ollama-compatible local server.

1. Install [Ollama](https://ollama.com).
2. Install the optional providers extra:

   ```bash
   pip install 'contextforge[providers]'
   ```

3. Pull a model:

   ```bash
   ollama pull qwen2.5-coder:7b
   ```

4. Configure the project to use Ollama:

   ```toml
   [provider]
   provider_id = "ollama"
   model_id = "qwen2.5-coder:7b"
   ```

5. Verify connectivity:

   ```bash
   contextforge provider health
   contextforge provider models
   ```

## Remote provider setup

Ollama can also run on a remote host. Set the endpoint explicitly and mark the
execution mode as remote:

```toml
[provider]
provider_id = "ollama"
model_id = "qwen2.5-coder:7b"
endpoint = "https://ollama.internal.example.com"
execution_mode = "remote"
allow_remote = true
```

Remote delivery requires explicit authorization and may be restricted by the
delivery policy. Do not send sensitive project context to a remote provider
unless your policy explicitly allows it.

## Scan and index

Build the project inventory:

```bash
contextforge scan
```

Build the searchable index from the latest inventory:

```bash
contextforge index
```

Immutable, versioned inventory and index snapshots are persisted under
`.contextforge/state/`; the current snapshot is selected by an atomic pointer.
Both commands report diagnostics, and re-running them reuses unchanged
artifacts automatically. Context and prompt records produced by `run` remain
under `.contextforge/executions/`.

Each `run` also persists its execution snapshot and immutable stage outcomes.
The normalized task specification is stored as an immutable `task.json` record
inside the execution directory so deterministic recovery can reconstruct the
original request after a process restart. Because this record contains the
original task text, protect `.contextforge/executions/` with the same access
controls as the project source.
`contextforge status` reports the latest execution identifier, workflow, stage,
and terminal status. Analysis workflows complete after response validation;
proposal-generation workflows are durably recorded at `await_approval`.
Approval and application reopen the correlated execution by task identity:
approval advances it to `apply`, rejection cancels it, and successful
application completes it. Patch application holds an exclusive project lock;
a concurrent application fails with a project-state conflict instead of
mutating files concurrently.

List, inspect, or cancel persisted executions:

```bash
contextforge execution list
contextforge execution show
contextforge execution show execution_0123456789abcdef0123456789abcdef
contextforge execution resume execution_0123456789abcdef0123456789abcdef
contextforge execution invoke execution_0123456789abcdef0123456789abcdef --confirm
contextforge execution validate execution_0123456789abcdef0123456789abcdef
contextforge execution cancel execution_0123456789abcdef0123456789abcdef
```

Execution output includes a conservative recovery assessment. Deterministic
stages before provider invocation are `resumable`; approval and application
boundaries are `awaiting_action`; stages with externally observable effects
require `manual_review_required`; and completed or cancelled executions are
`terminal`. ContextForge never automatically replays a provider call or project
mutation whose outcome may already be externally visible.
Legacy executions without a persisted task are classified as
`manual_review_required`.

`execution resume` reconstructs the current scan, index, retrieval, Context
Bundle, and prompt as needed, then pauses at `invoke_provider`. It does not call
the configured provider. Continuing beyond that boundary requires a separate
future action because a previous provider outcome cannot be inferred safely
after a process interruption.

`execution invoke --confirm` authorizes exactly one external provider call.
ContextForge writes a durable `submitted` record before transport and persists
the normalized response before advancing to `validate_response`. If transport
fails or the process stops after submission, the outcome remains unknown and
the command will not retry it automatically. Provider response content is
stored inside the execution directory for later validation, so
`.contextforge/executions/` may contain sensitive project-derived data even
though `execution show` exposes only response metadata.

`execution validate` routes the already persisted response according to the
execution workflow. Analysis responses are checked for successful provider
completion and evidence references are bound to the Context Bundle used for the
invocation before an immutable `result.json` completes the execution. Patch
responses are restored with their original request correlation, rejected if the
project fingerprint changed, materialized as a durable proposal, and advanced
to `await_approval`. Invalid responses fail the execution closed, and validation
never invokes the provider again.

Approving that proposal advances its exact originating execution to `apply`;
successful application completes the same execution. The binding uses the
persisted proposal identifier, so rerunning a task cannot redirect approval or
application to another execution.

If a process stops after approval, rejection, or application was persisted but
before the execution snapshot advanced, run `execution resume`. ContextForge
reconciles the execution from the proposal lifecycle without invoking the
provider or applying files again. Repeating `patch approve`, `patch reject`, or
`patch apply` returns the already persisted outcome instead of duplicating the
operation.

Immediately before project mutation, ContextForge persists an application
attempt with `submitted` state. A completed adapter result replaces it with a
`completed` record. If the process stops between those points, the outcome is
reported as unknown and neither `patch apply` nor `execution resume` will retry
the mutation automatically.

Inspect the exact durable application record before resolving it:

```bash
contextforge patch application <proposal-id>
```

After manually inspecting the project and any recovery artifacts, reconcile the
attempt with an auditable reference. Repeat the exact proposal identifier in
`--confirm`; this prevents resolving a different proposal accidentally:

```bash
contextforge patch reconcile <proposal-id> \
  --outcome applied \
  --confirm <proposal-id> \
  --recovery-reference incident-42
```

Use `--outcome rolled-back` only after verifying that every project mutation
was reverted. The proposal remains approved and may then be applied again, but
the normal project-fingerprint and approval-binding checks still run before the
new attempt. A reconciled `applied` outcome completes the proposal and its
originating execution without applying files again. Reconciliation records
retain the original submission data, declared resolution, timestamp, and
recovery reference.

Inspect the project lock:

```bash
contextforge lock show
```

Locks are never removed merely because they are old. If a process terminated
without releasing its lock, recovery must be explicit and succeeds only when
the minimum age has elapsed and the recorded process is confirmed absent:

```bash
contextforge lock recover --force --minimum-age-seconds 3600
```

## Analysis task

Run a read-only analysis task:

```bash
contextforge scan
contextforge index
contextforge run --analysis-only "Explain the retrieval pipeline"
```

The task text is preserved exactly as written. ContextForge selects relevant
context, builds a prompt, invokes the provider, and prints an analysis result.
No files are modified.

The default provider is the deterministic offline mock. To use Ollama, set
`provider_id = "ollama"` in `.contextforge/config.toml` or pass
`--provider ollama` to `contextforge provider` inspection commands.

## Patch proposal

To request a patch proposal, omit `--analysis-only`:

```bash
contextforge run "Add validation to the ProjectPath constructor"
```

This produces a `PatchProposal` that must be reviewed and approved before any
file is changed. The proposal lists affected files, operations, warnings, and
the project fingerprint at the time it was generated.

## Review and approval

List pending proposals:

```bash
contextforge patch list
```

Show proposal details:

```bash
contextforge patch show <proposal-id>
```

Review the output carefully. Only approve if the proposal fingerprint and
project fingerprint still match:

```bash
contextforge patch approve <proposal-id>
```

Reject a proposal:

```bash
contextforge patch reject <proposal-id>
```

## Safe application

Apply an approved proposal:

```bash
contextforge patch apply <proposal-id>
```

ContextForge performs a staged application: it builds the final files in an
isolated area, validates them, acquires a mutation lock, revalidates
preconditions, and replaces files atomically where the platform allows. If
anything fails, the operation reports which changes were applied and which were
not.

## Inspecting context and prompts

After an execution you can inspect what was sent to the provider:

```bash
contextforge context list
contextforge context show <item-id>
contextforge prompt preview
contextforge prompt measure
```

Sensitive context is redacted in these outputs.

## Evaluating context quality

Run a versioned suite offline and write stable JSON and Markdown reports:

```bash
contextforge evaluate tests/fixtures/evaluation/suites/core.json \
  --output .contextforge/evaluations/latest
```

Use repeatable `--case` and `--tag` options to select a smoke subset. Individual
case failures are recorded in both reports and do not abort later cases. Add
`--fail-on-case-error` in automation to write the complete reports and then exit
with code `19` if any selected case failed.

Regression thresholds are opt-in:

```bash
contextforge evaluate tests/fixtures/evaluation/suites/core.json \
  --case direct-path \
  --fail-on-case-error \
  --minimum required-artifact-recall=1.0 \
  --output .contextforge/evaluations/latest
```

A failed threshold exits with code `20`; suite, configuration, output, or
opted-in case failures exit with code `19`. Evaluation does not invoke a provider by default.
Patch-oriented fixtures are copied to a temporary directory before execution.

## Diagnostics and troubleshooting

Run the full local quality gate:

```bash
ruff format --check . && ruff check . && mypy src/contextforge && pytest && python -m build
```

Common issues:

| Symptom | Likely cause | Resolution |
|---|---|---|
| `PROJECT_RESOLUTION_FAILURE` | Not inside an initialized project | Run `contextforge init` |
| `PROVIDER_UNAVAILABLE` | Ollama is not running | Start Ollama and check `provider health` |
| `APPROVAL_REQUIRED` | Proposal fingerprint changed | Review and approve the exact proposal |
| `STALE_PROPOSAL` | Project state changed after proposal | Regenerate the proposal |
| Sensitive context rejected | `allow_sensitive_remote` is false | Use a local provider or authorize explicitly |

Report security vulnerabilities privately as described in `SECURITY.md`.
