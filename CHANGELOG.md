# Changelog

All notable changes to ContextForge will be documented in this file.

The project follows [Semantic Versioning](https://semver.org/). Changes under
development are recorded in the Unreleased section.

## [Unreleased]

- Added filesystem-backed retrieval and context construction to CLI execution.
- Added end-to-end patch-proposal generation through `contextforge run`.
- Added project-scoped execution history and conservative recovery
  classification.
- Persisted immutable task specifications with execution identity binding for
  restart-safe reconstruction.
- Added safe deterministic execution resumption that stops before provider
  invocation.
- Added explicitly confirmed, single-attempt provider invocation with durable
  submitted and received states.
- Stopped echoing complete task text in default command output.

## [0.1.0] - 2026-07-26

### Added

- Installable Python package (`contextforge`) with a `contextforge` CLI entry
  point.
- Core CLI commands: `init`, `status`, `scan`, `index`, `run --analysis-only`,
  `context`, `prompt`, `provider`, `patch`, `config`, and `diagnostics`.
- Project resolution, safe configuration management, and provider inspection.
- Analysis-only task pipeline with mock-provider support for local execution.
- Patch proposal lifecycle: review, approve, reject, and apply with interactive
  and non-interactive approval safeguards.
- Cross-platform CI pipeline for Ubuntu, Windows, and macOS with Python 3.12
  and 3.13.
- Code quality gate: Ruff, MyPy, Pytest, coverage, and package-build checks.
- Performance baseline tests for scanner, indexing, and analysis tasks.
- Privacy and logging tests enforcing no production logging, redacted
  diagnostics, and raw-response discard policies.
- User guide and contributor guide.
- Release artifact script with wheel, source distribution, and checksum
  generation.

### Security

- Credentials and secrets are redacted from configuration and diagnostics.
- Raw LLM responses are discarded when `RawResponseRetentionPolicy.NEVER` is
  configured.
- Patch approval requires explicit binding in non-interactive mode.

## [0.0.1] - 2026-07-23

### Added

- Initial ContextForge specifications and progressive implementation guide.
