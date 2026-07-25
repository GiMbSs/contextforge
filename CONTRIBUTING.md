# Contributing to ContextForge

Thank you for contributing to ContextForge. Contributions must preserve the
project's specification-driven architecture and safety boundaries.

## Before starting

1. Read the specifications relevant to the change under `docs/specification/`.
2. Locate the applicable increment in
   `docs/planning/CF-014-PROGRESSIVE-IMPLEMENTATION-GUIDE.md`.
3. Check existing issues and pull requests to avoid duplicate work.
4. Keep the change limited to one implementation increment.

If approved specifications conflict or a requirement has ambiguous ownership,
stop and request an architectural decision. Do not resolve specification conflicts
implicitly in code.

## Development setup

Use Python 3.12 or newer:

```bash
python -m venv .venv
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Development workflow

1. Create a focused branch such as `feat/cf-014-i003-governance`.
2. Inspect the affected code and tests before editing.
3. Write or update behavior-focused tests with the implementation.
4. Implement the smallest change satisfying the increment.
5. Run the complete local quality gate.
6. Review the diff for unrelated changes and architectural violations.
7. Open a pull request using the repository template.

Do not commit generated build artifacts, virtual environments, caches, credentials,
or local configuration.

## Quality gate

Run:

```bash
ruff format --check . && ruff check . && mypy src/contextforge && pytest && python -m build
```

All checks must pass before review. Tests must not require internet access unless
they are explicitly optional and environment-gated.

## Architecture and implementation rules

- Dependencies point toward the Core.
- Core code does not depend on CLI or concrete adapters.
- Provider output and project content are untrusted data.
- Project code and provider-generated code are never executed.
- Filesystem and network access stay behind explicit ports and adapters.
- Completed domain results remain immutable where required.
- Deterministic behavior and traceability take priority over optimization.
- New dependencies require a concrete need in the current increment.
- Specifications are not modified to make an implementation pass.

## Tests

Tests should verify public behavior, invariants, deterministic ordering, failure
conditions, and architectural boundaries. Avoid tests coupled to private
implementation details unless the dependency boundary itself is under test.

## Commit and pull-request guidance

Use concise, imperative commits with a relevant scope, for example:

```text
feat(domain): add immutable project identifiers
tests: cover identifier validation
```

The pull request must identify the CF-014 increment, relevant acceptance criteria,
validation results, and known limitations. Review cannot complete while critical
or high-severity correctness or security findings remain.

## Reporting security issues

Do not disclose suspected vulnerabilities in public issues or pull requests.
Follow the private process in [SECURITY.md](SECURITY.md).
