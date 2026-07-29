# CF-016 — Codex CLI bridge

## Goal

Expose ContextForge to Codex CLI as a local, read-only context service. Codex remains
responsible for reasoning, editing, and command execution; ContextForge scans, indexes,
selects, budgets, and explains the project evidence relevant to a task.

The integration must reduce irrelevant input without hiding why an artifact was selected.
It must not invoke a second model or duplicate Codex provider calls.

## User flow

1. The user opens Codex in an initialized ContextForge project.
2. Codex receives a software-engineering task.
3. For non-trivial repository questions, Codex calls the ContextForge MCP tool with the
   task text and an explicit context budget.
4. ContextForge returns a compact context packet containing selected excerpts, source
   paths, selection evidence, coverage, diagnostics, and token estimates.
5. Codex uses the packet as an orientation layer and reads additional files only when the
   packet reports incomplete coverage or the task requires verification.

ContextForge is a bridge, not an authority boundary: project instructions and Codex
approval rules continue to govern actions.

## Architecture

```text
Codex CLI
   |
   | MCP over stdio (read-only tools)
   v
ContextForge MCP adapter
   |
   v
PrepareContext application use case
   |
   +--> scanner --> indexer --> retriever --> ContextBundle builder
   |
   v
CompactContextPacket
```

The application use case and packet are transport-neutral. The CLI and MCP adapters
serialize the same contract; neither adapter implements retrieval policy.

## Delivery stages

### Stage 1 — Stable context packet

Add a use case that prepares context directly from a task and returns a JSON-safe,
versioned packet. It shall:

- accept a resolved project root, task text, and bounded item/byte budget;
- scan and index through existing application boundaries;
- include selected content required by the consumer, not only persisted summaries;
- include paths, source references, rationale, evidence, coverage, diagnostics, and
  estimated context tokens;
- expose no provider invocation or mutation operation;
- fail closed for invalid project roots, empty tasks, invalid budgets, or invalid bundles.

Expose the use case through a deterministic CLI command suitable for scripts.

### Stage 2 — MCP stdio adapter

Add `contextforge mcp serve` with one initial tool:

- `contextforge_build_context`

Inputs:

- `task` (required string);
- `project_root` (optional absolute or working-directory-relative path);
- `max_items` and `max_bytes` (optional bounded integers).

The server shall implement MCP initialization, tool discovery, and tool invocation over
standard input/output. Protocol messages go to stdout; diagnostics go to stderr.

The initial implementation should keep the base installation small. If a maintained MCP
SDK becomes a runtime dependency, it must be justified by protocol coverage that the
minimal adapter cannot safely provide.

### Stage 3 — Codex installation and diagnostics

Add commands that print or register the local stdio server configuration and verify:

- the ContextForge executable is available;
- the project resolves and is initialized;
- the server starts and lists its tool;
- a sample context request completes without modifying the repository.

The equivalent Codex registration is:

```console
codex mcp add contextforge -- contextforge mcp serve
```

Project instructions should ask Codex to use the tool for repository-wide or
dependency-sensitive tasks, while allowing direct inspection for trivial or already
localized changes.

### Stage 4 — End-to-end efficacy evaluation

Measure the bridge with fixed task fixtures:

- required-artifact recall;
- required-evidence recall;
- context estimated tokens;
- corpus estimated tokens;
- token reduction ratio;
- tool latency;
- fallback reads needed after the packet.

A reduction claim passes only when required evidence remains above the configured gate.
Estimated token reduction must be reported as an estimate, not provider-billed usage.

## Security and operational constraints

- All bridge tools are read-only.
- The resolved root confines all source reads.
- Existing ignore and sensitivity policies remain effective.
- Context content is returned only in explicit tool results and is not logged by default.
- Budgets have conservative defaults and hard upper bounds.
- MCP errors use stable public codes and do not expose secrets or internal tracebacks.
- No automatic provider invocation, patch generation, approval, or application is exposed.

## Validation and commit boundaries

Each delivery stage is validated and committed independently:

1. architecture and acceptance contract;
2. context packet plus unit/CLI tests;
3. MCP adapter plus protocol tests;
4. Codex setup plus end-to-end smoke test;
5. efficacy fixture, report, and regression thresholds.

