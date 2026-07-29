# Release Notes

## ContextForge 0.1.1

**Release date:** 2026-07-29

ContextForge 0.1.1 consolidates the implemented MVP with measurable retrieval
quality, grounded analysis validation, and reproducible offline release
artifacts.

### Improvements

- Signals insufficient evidence instead of presenting lexical fallback as
  complete context.
- Resolves internal Python relationships across files and uses them as
  traceable structural ranking evidence.
- Expands the reviewed offline benchmark from 8 to 12 cases, covering
  test-to-production navigation, deep dependency chains, and homonymous
  symbols.
- Rejects unsupported completion claims, findings without evidence, and
  references outside the supplied Context Bundle.
- Supports inclusive `--maximum` evaluation bounds and enforces a zero
  irrelevant-context ratio in the reviewed `core` 1.2 gate.
- Builds wheel and source archives without network-dependent isolation and
  normalizes archive metadata for reproducible hashes.
- Updates CI and product documentation to match the implemented behavior.

### Validation

- Canonical 13-step MVP acceptance scenario revalidated.
- Reviewed evaluation suite: 12 cases, 0 execution failures.
- Full automated suite: 1,165 passed and 8 platform-dependent symlink tests
  skipped during release preparation.

Release checksums are stored in
`dist/contextforge-0.1.1.checksums.txt`.

## ContextForge 0.1.0

**Release date:** 2026-07-26

ContextForge 0.1.0 is the first installable release of the context engineering
engine. It provides local-first analysis and approval-gated patch-proposal
workflows for building precise, traceable LLM context from a software project.

### What is included

- `contextforge` CLI installed from PyPI-ready wheel and source distribution.
- Project initialization and state inspection.
- Scanner, indexer, analysis, and approval-gated patch-proposal execution.
- Durable, versioned inventory and index snapshots with incremental reuse across
  separate CLI executions.
- Durable execution lifecycle snapshots and immutable per-stage diagnostics,
  with identity-bound task specifications and distinct analysis and patch
  workflow paths.
- Cross-process patch lifecycle continuation and ownership-verified exclusive
  locking during project mutation.
- CLI history, inspection, cancellation, and recovery classification for
  persisted executions, plus conservative explicit recovery for old locks
  whose owner process is confirmed absent.
- Deterministic execution resumption through prompt reconstruction, with a hard
  stop before any provider invocation.
- Explicit provider invocation with confirmation, durable response capture, and
  fail-closed handling of unknown outcomes.
- Offline analysis-response validation with evidence-bound result persistence.
- Offline patch-response validation with project-fingerprint checks and durable
  proposal materialization before explicit approval.
- Crash-safe reconciliation between persisted proposal lifecycles and execution
  stages, with idempotent repeated approval, rejection, and application.
- Durable patch-application submission journaling that prevents unsafe replay
  after an interrupted mutation with an unknown outcome.
- Explicit application-journal inspection and proposal-bound reconciliation
  with retained recovery evidence before completion or safe retry.
- Local mock provider for repeatable, offline runs.
- Ollama-compatible provider adapter (local and remote) via the `providers` extra.
- Provider inspection and health checks (no project content transmitted).
- Patch proposal review with interactive and non-interactive approval.
- Configuration management with secret redaction and source attribution.
- Diagnostics command that reports only non-sensitive runtime readiness.
- Comprehensive test suite with coverage, performance baselines, privacy checks,
  and cross-platform CI.

### Installation

```bash
pip install contextforge-0.1.0-py3-none-any.whl
```

For Ollama support, install the `providers` extra:

```bash
pip install 'contextforge[providers]'
```

For development, install from source with the `dev` extra:

```bash
pip install -e ".[dev,providers]"
```

### Quick start

```bash
contextforge init ./my-project
contextforge --project ./my-project scan
contextforge --project ./my-project index
contextforge --project ./my-project run --analysis-only "Summarize the project"
contextforge --project ./my-project diagnostics
```

See [user-guide.md](user-guide.md) for the full workflow and
[contributor-guide.md](contributor-guide.md) for development conventions.

### Verification

Run the quality gate used in CI:

```bash
ruff format --check .
ruff check .
mypy src/contextforge
pytest
python scripts/build-release.py
```

### Known limitations

See [known-limitations.md](known-limitations.md).

### Compatibility

See [compatibility-matrix.md](compatibility-matrix.md).

### Checksums

Release checksums are produced by `scripts/build-release.py` and stored in
`dist/contextforge-0.1.0.checksums.txt`.
