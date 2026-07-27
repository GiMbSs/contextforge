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
2. Pull a model:

   ```bash
   ollama pull qwen2.5-coder:7b
   ```

3. Verify connectivity:

   ```bash
   contextforge provider health
   contextforge provider models
   ```

## Scan and index

Build the project inventory:

```bash
contextforge scan
```

Build the searchable index from the latest inventory:

```bash
contextforge index
```

Both commands persist their results under `.contextforge/executions/` and
report diagnostics. Re-running them reuses unchanged artifacts automatically.

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

## Patch proposal

To request a patch proposal, omit `--analysis-only` once the patch pipeline is
available in your build:

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
