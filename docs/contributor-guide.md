# ContextForge Contributor Guide

This guide is for anyone who wants to extend, fix, or review ContextForge.

## Architecture boundaries

ContextForge is organized in layers. Each layer has strict import rules that
are enforced by `tests/test_architecture.py`.

| Layer | Responsibility | May import |
|---|---|---|
| `domain` | Immutable value objects, identifiers, paths, tasks | Nothing inside ContextForge |
| `application` | Use cases, orchestration, ports | `domain` and abstract ports |
| `adapters` | Concrete implementations of ports | `application` interfaces and `domain` |
| `cli` | Argument parsing and presentation | `application` interfaces only |
| `provider` | Provider-agnostic inference contracts | No HTTP client or SDK |
| `patch` | Patch validation and lifecycle | No filesystem applier |

Core rule: domain and application code must not depend on concrete adapters or
the CLI.

## Package structure

```text
src/contextforge/
  adapters/          Concrete implementations (filesystem, providers, config)
  application/       Use cases and execution control
  cli/               Typer entry points
  configuration/     Typed configuration models and precedence
  context/           Context bundle building and validation
  diagnostics/       Immutable diagnostics with redaction
  domain/            Value objects, identifiers, fingerprints, paths
  indexer/           Project indexing and Python AST extraction
  patch/             Patch proposal models, validation, lifecycle
  project/           Project root resolution
  prompt/            Prompt template assembly and measurement
  provider/          Provider-agnostic inference contracts
  retrieval/         Context retrieval strategies and budgeting
  scanner/           Project scanning, classification, ignore rules
  shared/            Cross-cutting serialization helpers

tests/               Automated tests mirroring the modules above
docs/specification/  Authoritative design documents
docs/planning/       Incremental implementation plan
```

## Local setup

```bash
python -m venv .venv
python -m pip install --upgrade pip
python -m pip install -e ".[dev,providers]"
```

Run the full quality gate:

```bash
ruff format --check . && ruff check . && mypy src/contextforge && pytest && python -m build
```

## Test strategy

- Every public behavior must have an automated test.
- Tests should verify behavior, not internal implementation details, unless the
  test explicitly protects an architectural boundary.
- Security tests live next to feature tests: `tests/test_adversarial_path_corpus.py`,
  `tests/test_malicious_provider_response_corpus.py`, `tests/test_privacy_logging.py`.
- Use `pytest` fixtures and parametrize liberally for edge cases.
- Do not weaken security checks to make a test pass.

## Specification traceability

Every significant change should reference a specification document in
`docs/specification/` and the relevant increment in
`docs/planning/CF-014-PROGRESSIVE-IMPLEMENTATION-GUIDE.md`. Use commit messages
like:

```text
feat(scanner): add safe symlink traversal

Refs: CF-005, CF-014-I018
```

## ADR workflow

When an implementation reveals a conflict or ambiguity:

1. Stop expanding the implementation.
2. Record the ambiguity in a new ADR under `docs/adr/`.
3. Resolve it through an amendment or ADR decision.
4. Continue only after the decision is explicit.

Do not hide specification changes inside implementation commits.

## Adding a parser

1. Define the new artifact parser as a port in `indexer/ports.py`.
2. Implement the parser in `indexer/`, keeping it independent of filesystem
   access.
3. Add tests in `tests/test_<parser>_*.py`.
4. Update the indexer to register the parser and handle unsupported artifacts
   honestly.
5. Run the full quality gate.

## Adding a provider adapter

1. Define the provider contract in `provider/ports.py` and `provider/models.py`.
2. Implement the adapter under `adapters/providers/`. It may use an HTTP client
   but the `provider` package must not import it.
3. Add tests with mocked transport for discovery, health, and invocation.
4. Ensure provider output is never executed, imported, or treated as
   authoritative.
5. Add the adapter to the provider list used by the CLI.

## Adding a diagnostic code

1. Add a stable, uppercase, underscore-separated code string to
   `diagnostics/models.py` or the relevant capability.
2. Document the code in the relevant capability documentation.
3. Add a test that exercises the diagnostic, including redaction of any
   sensitive data.
4. Do not reuse an existing code for a different condition.

## Review checklist

Before submitting changes:

- [ ] Quality gate passes locally.
- [ ] Tests cover new behavior and edge cases.
- [ ] No forbidden imports are introduced.
- [ ] No direct filesystem mutation from `domain` or `application`.
- [ ] Provider output is treated as untrusted.
- [ ] Secrets are represented as `SecretReference`, never plain strings.
- [ ] Diagnostics redact sensitive data.
- [ ] Documentation and commit messages reference the right specifications.

## Evaluation benchmark changes

The deterministic smoke evaluation runs in CI for Python 3.12 on Linux. Run it
locally with:

```bash
contextforge evaluate tests/fixtures/evaluation/suites/core.json \
  --case direct-path \
  --fail-on-case-error \
  --minimum required-artifact-recall=1.0 \
  --output .contextforge/evaluations/latest
```

Changes to suite judgments, fixture fingerprints, selected smoke cases, or
thresholds are benchmark changes. Keep those changes visible in the pull
request, explain the new baseline, and obtain review rather than weakening a
threshold solely to make CI pass.

The reviewed aggregate values and thresholds are versioned in
`tests/fixtures/evaluation/baselines/core-1.1.json`. Regenerate the suite twice,
confirm matching configuration fingerprints and aggregate metrics, and review
the resulting quality change before updating that file.

## Security

Report vulnerabilities privately as described in `SECURITY.md`. Never commit
secrets, API keys, or credentials.
