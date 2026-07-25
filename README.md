# ContextForge

**Less Context. Better Intelligence.**

ContextForge is an open-source context engineering engine for building small,
relevant, traceable context bundles for AI-assisted software development.

The project is in its implementation-foundation stage. The current package provides
the installable CLI skeleton and development quality controls; scanning, indexing,
retrieval, providers, and patching are not implemented yet.

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
python -m pip install -e ".[dev]"
```

## Local quality gate

```bash
ruff format --check . && ruff check . && mypy src/contextforge && pytest && python -m build
```

This command checks formatting, linting, strict typing, tests with coverage, and
package builds. The same checks run in continuous integration.

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
