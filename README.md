# ContextForge

**Less Context. Better Intelligence.**

ContextForge is an open-source context engineering engine for building small,
relevant, traceable context bundles for AI-assisted software development.

The current MVP provides an installable CLI with project scanning, Python-aware
indexing, evidence-ranked retrieval, bounded Context Bundles, provider
integration, grounded analysis responses, and approval-gated patch application.
Its deterministic evaluation suite measures retrieval effectiveness offline.

## Requirements

- Python 3.12 or newer
- Git

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

## Development setup

Install the development toolchain:

```bash
python -m pip install -e ".[dev,providers]"
```

## Local quality gate

```bash
ruff format --check . && ruff check . && mypy src/contextforge && pytest
python scripts/build-release.py
```

These commands check formatting, linting, strict typing, tests with coverage, and
package builds. The same checks run in continuous integration.

Run the reviewed effectiveness gate:

```bash
contextforge evaluate tests/fixtures/evaluation/suites/core.json \
  --fail-on-case-error \
  --minimum complete-evidence=0.875 \
  --minimum context-precision=1.0 \
  --minimum ndcg=0.8 \
  --minimum required-artifact-recall=0.875 \
  --maximum context-irrelevant-ratio=0.0 \
  --output .contextforge/evaluations/core
```

## Project structure

```text
docs/specification/  Authoritative product and architecture specifications
docs/planning/       Progressive implementation plan
src/contextforge/    Python package
tests/               Automated tests
```

Implementation follows the small increments in
`docs/planning/CF-014-PROGRESSIVE-IMPLEMENTATION-GUIDE.md`. Each change should
implement only one increment and preserve the architectural boundaries in CF-003.

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md) for the contribution workflow and
[SECURITY.md](SECURITY.md) for private vulnerability reporting. Participation is
governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## License

ContextForge is licensed under the [MIT License](LICENSE).
