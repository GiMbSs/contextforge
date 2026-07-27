# Release Notes

## ContextForge 0.1.0

**Release date:** 2026-07-26

ContextForge 0.1.0 is the first installable release of the context engineering
engine. It provides a local-first, analysis-only workflow for building precise,
traceable LLM context from a software project without transmitting source code
to external services.

### What is included

- `contextforge` CLI installed from PyPI-ready wheel and source distribution.
- Project initialization and state inspection.
- Scanner, indexer, and analysis-only task execution.
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
python -m build
```

### Known limitations

See [known-limitations.md](known-limitations.md).

### Compatibility

See [compatibility-matrix.md](compatibility-matrix.md).

### Checksums

Release checksums are produced by `scripts/build-release.py` and stored in
`dist/contextforge-0.1.0.checksums.txt`.
