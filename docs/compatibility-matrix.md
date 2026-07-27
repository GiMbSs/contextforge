# Compatibility Matrix

This matrix records the supported runtime combinations for ContextForge 0.1.0.

## Python versions

| Python | Supported | CI tested | Notes |
|--------|-----------|-----------|-------|
| 3.12   | Yes       | Yes       | Primary development target |
| 3.13   | Yes       | Yes       | Latest stable Python |
| 3.11   | No        | No        | Requires Python 3.12 or newer |
| 3.10   | No        | No        | Requires Python 3.12 or newer |

## Operating systems

| OS        | Supported | CI tested | Notes |
|-----------|-----------|-----------|-------|
| Ubuntu    | Yes       | Yes       | Latest LTS runner |
| Windows   | Yes       | Yes       | Windows Server runner |
| macOS     | Yes       | Yes       | macOS latest runner |

## CLI shells

| Shell     | Supported | Notes |
|-----------|-----------|-------|
| bash      | Yes       | Used in Linux/macOS documentation |
| zsh       | Yes       | Compatible with bash examples |
| PowerShell| Yes       | Native Windows shell |
| cmd.exe   | Yes       | Limited; PowerShell recommended |

## Package formats

| Format                  | Supported | Produced by CI / build script |
|-------------------------|-----------|-------------------------------|
| Wheel (`py3-none-any`)  | Yes       | Yes                           |
| Source distribution     | Yes       | Yes                           |
| Checksums (SHA-256)     | Yes       | Yes                           |

## Dependencies

| Package | Minimum version | Notes |
|---------|-----------------|-------|
| typer   | 0.12            | CLI framework |
| build   | 1.2 (dev)       | PEP 517 builds |
| ruff    | 0.9 (dev)       | Formatting and linting |
| mypy    | 1.15 (dev)      | Type checking |
| pytest  | 8.3 (dev)       | Test runner |
| pytest-cov | 6.0 (dev)    | Coverage plugin |
| hypothesis | 6.100 (dev)  | Property-based testing |

## Provider adapters

| Provider | Status | Notes |
|----------|--------|-------|
| mock-provider | Supported | Default, offline, deterministic |
| OpenAI   | Not included | Adapter interface ready; no CI validation |
| Anthropic | Not included | Adapter interface ready; no CI validation |
| LM Studio | Not included | Local HTTP endpoint; no CI validation |
| Ollama   | Not included | Local HTTP endpoint; no CI validation |
| vLLM     | Not included | Local HTTP endpoint; no CI validation |

## Versioning notes

- ContextForge uses [Semantic Versioning](https://semver.org/).
- The public API surface is the CLI command set and documented configuration
  schema. Internal Python modules may change in minor versions while the CLI
  remains stable.
- Breaking CLI changes are reserved for major versions.
