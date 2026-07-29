# Known Limitations

This page documents known limitations of ContextForge 0.1.1.

## Provider support

- The default provider is a local mock provider that returns deterministic,
  synthetic insufficient-context results. It is suitable for pipeline testing
  and offline workflows, not for substantive code analysis.
- Ollama is supported via the `contextforge[providers]` extra and can run in
  local or remote mode. Live integration against a running Ollama server is not
  validated in CI.
- Other providers (OpenAI, Anthropic, LM Studio, vLLM) are supported by the
  provider adapter interface but are not validated in CI.
- Provider health checks do not transmit project content; they only verify
  reachability and credentials.

## Patch application

- Patch application modifies the local filesystem. Always review proposals with
  `contextforge patch review` before approving.
- Binary files and files outside the resolved project root are never modified.
- Directory creation and deletion operations require interactive confirmation
  unless `--non-interactive --approve <proposal_id>` is supplied.

## Execution scope

- `run --analysis-only` produces a read-only report. Omitting the flag produces
  a validated proposal and stops at explicit approval; it never applies the
  proposal automatically.
- No streaming responses are implemented; results are returned synchronously.

## Configuration

- Secrets must be provided through environment variables or external secret
  stores. The configuration file stores only non-secret values and references.
- The configuration schema is validated at runtime; unknown keys are rejected.

## Performance

- Performance baselines are calibrated for small-to-medium projects on modern
  hardware. Very large repositories may exceed default baselines and should use
  incremental scanning or subset selection.

## Evaluation scope

- The reviewed offline benchmark contains 12 small Python cases. It covers
  explicit paths and symbols, dependency chains, configuration, ambiguity,
  test-to-production navigation, budget pressure, and insufficient evidence.
- The benchmark does not yet measure live-provider answer quality or large,
  multilingual repositories. Its analysis metrics evaluate evidence selection,
  not the semantic quality of a remote model's prose.

## Platform notes

- Windows: long path support may require enabling the system-wide setting for
  paths longer than 260 characters.
- macOS and Linux: no known platform-specific limitations.

## Documentation

- API-level documentation is minimal; the public surface is the CLI. Internal
  modules may change without notice until a stable API is declared.
