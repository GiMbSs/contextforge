# ContextForge — Progressive Implementation Guide

**Document ID:** CF-014  
**Repository path:** `docs/planning/CF-014-PROGRESSIVE-IMPLEMENTATION-GUIDE.md`  
**Status:** Draft  
**Version:** 0.1.0  
**Baseline:** CF-000 through CF-013  
**Purpose:** Guide implementation through small, verifiable increments that minimize architectural drift, context overload, unsafe code generation and rework.

---

## 1. How to use this guide

This document defines the recommended implementation sequence for ContextForge.

Each increment is intentionally small. An increment should normally be completed in one focused branch or pull request.

The implementation agent SHALL receive only:

1. The current increment.
2. The directly relevant specifications.
3. Existing code from the affected modules.
4. Existing tests for the affected modules.
5. The repository conventions.

The implementation agent SHOULD NOT receive the entire repository context unless the task genuinely requires it.

The implementation process for every increment is:

```text
Read specification
    ↓
Inspect affected code
    ↓
Write or update tests
    ↓
Implement smallest valid change
    ↓
Run local quality gates
    ↓
Review architecture boundaries
    ↓
Commit only the completed increment
```

Do not begin the next increment while the current increment has failing tests, unresolved diagnostics, undocumented deviations or incomplete acceptance criteria.

---

## 2. Mandatory implementation rules

### 2.1 One responsibility per increment

Each increment SHALL implement one clearly bounded responsibility.

Avoid tasks such as:

> Implement Scanner, Indexer and Retriever.

Prefer tasks such as:

> Implement normalized project-relative paths and reject absolute paths or parent traversal.

### 2.2 Tests are part of the implementation

An increment is incomplete without tests.

Tests SHALL verify behavior, not internal implementation details, except where architectural boundaries are the behavior being protected.

### 2.3 No hidden specification changes

When the implementation reveals an ambiguity or conflict:

1. Stop expanding the implementation.
2. Record the ambiguity.
3. Resolve it through an amendment or ADR.
4. Continue only after the decision is explicit.

### 2.4 No speculative abstractions

Do not build extension systems, plugin frameworks or generalized abstractions before the current MVP requires them.

Create an interface only when at least one of the following is true:

- The specification requires a port.
- Two concrete implementations already exist or are immediately planned.
- The interface protects a defined architectural boundary.
- Tests require substituting an external dependency.

### 2.5 No direct filesystem mutation from Core

Core capability modules SHALL NOT directly create, modify, rename or delete project files.

Filesystem access must be isolated behind ports and adapters.

### 2.6 Provider output is always untrusted

Provider output SHALL never be:

- executed;
- imported;
- evaluated;
- passed to a shell;
- applied without validation;
- treated as authoritative project state.

### 2.7 Determinism before optimization

The first implementation SHALL prioritize:

1. Correctness.
2. Determinism.
3. Traceability.
4. Testability.
5. Performance.

Optimization begins only after a measurable baseline exists.

---

## 3. Branch and commit strategy

Recommended branch naming:

```text
feat/cf-014-i001-package-skeleton
feat/cf-014-i012-project-path
fix/cf-014-i034-symlink-boundary
```

Recommended commit format:

```text
feat(domain): add project identifiers and fingerprints

tests: cover deterministic fingerprint generation

Refs: CF-004, CF-014-I006
```

Each pull request SHOULD contain:

- one increment;
- the relevant specification references;
- implementation summary;
- test evidence;
- known limitations;
- explicit note confirming no unrelated refactor.

---

## 4. Global quality gate

Before completing any increment, run the project-equivalent commands for:

```bash
ruff format --check .
ruff check .
pytest
mypy src/contextforge
python -m build
```

The exact tooling may change, but the gate SHALL include:

- formatting;
- linting;
- static typing;
- automated tests;
- package build verification.

---

# Stage A — Repository and Tooling Foundation

## I001 — Create the Python package skeleton

**Goal**

Create an installable package with a working CLI entry point and no domain behavior.

**Create**

```text
pyproject.toml
src/contextforge/__init__.py
src/contextforge/__main__.py
src/contextforge/cli/__init__.py
src/contextforge/cli/main.py
tests/test_package.py
```

**Required behavior**

```bash
python -m contextforge --version
contextforge --version
contextforge --help
```

**Tests**

- Package imports successfully.
- Version command exits with code `0`.
- Help command exits with code `0`.
- Unknown command exits with CLI usage error.

**Do not implement yet**

- configuration;
- scanning;
- indexing;
- provider integration;
- patching.

**Completion gate**

A clean virtual environment can install the project and execute the CLI stub.

---

## I002 — Configure formatting, linting and typing

**Goal**

Establish automated quality controls before domain code grows.

**Configure**

- Ruff formatter.
- Ruff linter.
- MyPy or Pyright.
- Pytest.
- Coverage.

**Tests and checks**

- Source and tests are included in linting.
- Strict typing is enabled at least for `domain` and `application` packages.
- Build artifacts and fixtures are excluded intentionally.

**Completion gate**

One documented command executes all local checks.

---

## I003 — Create repository governance files

**Goal**

Document how code enters the repository.

**Create or complete**

```text
README.md
CONTRIBUTING.md
SECURITY.md
CODE_OF_CONDUCT.md
CHANGELOG.md
LICENSE
.github/PULL_REQUEST_TEMPLATE.md
.github/workflows/ci.yml
```

**Completion gate**

A contributor can understand setup, test execution, contribution flow and security reporting without external instructions.

---

## I004 — Add architecture dependency tests

**Goal**

Prevent architectural erosion from the first implementation cycle.

**Rules to enforce**

- `domain` imports no application, CLI or adapter modules.
- `application` imports domain and ports, but no concrete adapters.
- `cli` may import application interfaces, not capability internals.
- provider Core contracts import no HTTP client or SDK.
- patch validation imports no filesystem applier.

**Completion gate**

A deliberately forbidden import causes a test failure.

---

# Stage B — Shared Domain Primitives

## I005 — Implement immutable identifiers

**Goal**

Create explicit identifiers for project artifacts and execution lineage.

**Initial identifiers**

```text
ProjectId
ExecutionId
InventoryId
IndexId
RetrievalId
ContextBundleId
InferenceRequestId
InferenceResponseId
PatchProposalId
ApprovalId
```

**Rules**

- Immutable.
- String serializable.
- Strongly typed.
- Validated on construction.
- Generated through dedicated factory functions.

**Tests**

- Valid identifiers round-trip through serialization.
- Invalid empty or malformed identifiers fail.
- Different identifier classes are not interchangeable in typed code.

---

## I006 — Implement deterministic fingerprints

**Goal**

Represent semantic project and artifact state without timestamps.

**Implement**

```text
ContentFingerprint
ProjectFingerprint
ConfigurationFingerprint
ProposalFingerprint
```

**Rules**

- Use a stable cryptographic hash.
- Normalize input encoding.
- Exclude non-semantic runtime metadata.
- Preserve ordered versus unordered semantics explicitly.

**Tests**

- Same semantic input produces the same fingerprint.
- Order changes only affect fingerprints when order is semantically meaningful.
- Line-ending policy is explicit and tested.

---

## I007 — Implement diagnostics

**Goal**

Create a common failure and warning language.

**Implement**

```text
Diagnostic
DiagnosticCode
DiagnosticSeverity
DiagnosticLocation
DiagnosticCollection
```

**Required severities**

```text
INFO
WARNING
ERROR
CRITICAL
```

**Rules**

- Stable diagnostic codes.
- Human-readable message.
- Optional structured metadata.
- No secret leakage.
- Immutable after construction.

**Tests**

- Diagnostics serialize deterministically.
- Sensitive values are redacted.
- Ordering is deterministic.

---

## I008 — Implement versioned serialization envelopes

**Goal**

Provide stable persisted artifact envelopes.

**Envelope fields**

```text
schema_name
schema_version
artifact_id
created_at
producer_version
payload
metadata
```

**Rules**

- Current writer version is explicit.
- Unsupported major versions fail clearly.
- Datetimes use UTC ISO 8601.
- Payload serialization is deterministic.

**Tests**

- Round-trip current version.
- Reject unsupported major version.
- Preserve Unicode.
- Reject malformed envelopes.

---

## I009 — Implement Task Specification

**Goal**

Represent the user's task without semantic rewriting.

**Fields**

```text
task_id
task_text
task_kind
requested_output
constraints
metadata
```

**Rules**

- Empty task text is invalid.
- Original task text is preserved.
- Task normalization may trim terminal-only surrounding whitespace.

**Tests**

- Multiline and Unicode tasks.
- Empty tasks rejected.
- Original content preserved after serialization.

---

## I010 — Implement Project and Execution models

**Goal**

Establish project identity and execution correlation.

**Models**

```text
ProjectIdentity
ProjectState
Execution
ExecutionStage
ExecutionStatus
```

**Required execution stages**

```text
RESOLVE
SCAN
INDEX
RETRIEVE
BUILD_CONTEXT
BUILD_PROMPT
INVOKE_PROVIDER
VALIDATE_RESPONSE
BUILD_PROPOSAL
AWAIT_APPROVAL
APPLY
COMPLETE
```

**Tests**

- Valid stage transitions.
- Invalid backward or skipped transitions rejected when policy forbids them.
- Failed and cancelled states are terminal.

---

# Stage C — Configuration

## I011 — Implement configuration models

**Goal**

Define typed configuration without loading files yet.

**Initial configuration groups**

```text
ProjectConfig
ScannerConfig
IndexerConfig
RetrieverConfig
ContextConfig
PromptConfig
ProviderConfig
PatchConfig
CliConfig
```

**Rules**

- Defaults are explicit.
- Unknown keys can be reported.
- Secrets are represented as references or protected values.

---

## I012 — Implement configuration precedence

**Goal**

Resolve effective configuration in the approved order.

**Precedence**

1. CLI arguments.
2. Explicit config file.
3. Named profile.
4. Project config.
5. User config.
6. Environment.
7. Defaults.

**Tests**

- Every precedence boundary.
- Missing optional sources.
- Invalid type.
- Secret redaction.
- Source attribution for effective values.

---

## I013 — Implement configuration file loading

**Goal**

Load project and user TOML configuration.

**Rules**

- Configuration is data, never executable code.
- Parse errors produce stable diagnostics.
- File loading occurs through a configuration source adapter.

**Completion gate**

`contextforge config show` can later display a fully attributed effective configuration without exposing credentials.

---

# Stage D — Project Paths and Scanner Foundation

## I014 — Implement normalized project-relative paths

**Goal**

Create the canonical path representation used throughout Core.

**Implement**

```text
ProjectPath
ArtifactPath
```

**Rules**

- Internal separator is `/`.
- Absolute paths are invalid.
- Parent traversal is invalid.
- Empty path policy is explicit.
- Windows drive and UNC paths are rejected as project-relative paths.
- Unicode is supported.

**Tests**

- POSIX and Windows input forms.
- `..` traversal.
- repeated separators.
- dot segments.
- Unicode.
- reserved edge cases.

---

## I015 — Implement project root resolution

**Goal**

Resolve the project root through the approved precedence.

**Rules**

1. Explicit `--project`.
2. Nearest parent with `.contextforge` metadata.
3. Current working directory if valid.
4. Diagnostic failure.

**Tests**

- Explicit path.
- Nested working directory.
- No project found.
- Symlinked working directory.

---

## I016 — Define Project Scanner port and models

**Goal**

Define Scanner contracts before traversal logic.

**Models**

```text
ScanRequest
ProjectArtifact
ArtifactKind
ArtifactClassification
ProjectInventory
ScanStatistics
```

**Artifact classifications**

```text
SOURCE
TEST
CONFIGURATION
DOCUMENTATION
GENERATED
BINARY
SENSITIVE
UNKNOWN
```

**Completion gate**

A fake Scanner can produce a valid Project Inventory without touching disk.

---

## I017 — Implement ignore policy

**Goal**

Determine which project entries are eligible for discovery.

**Initial inputs**

- built-in ignores;
- `.gitignore`-compatible project rules where supported;
- ContextForge configuration rules;
- explicit include overrides only when policy allows.

**Tests**

- `.git` ignored.
- virtual environments ignored.
- build outputs ignored.
- nested rule behavior.
- deterministic rule precedence.

---

## I018 — Implement safe filesystem traversal

**Goal**

Discover entries without escaping the project root.

**Rules**

- Do not follow symlinks by default.
- Detect symlink escapes.
- Handle permission failures as diagnostics.
- Do not load full file contents unnecessarily.
- Return deterministic path ordering.

**Security tests**

- symlink to parent;
- symlink to external directory;
- cyclic symlink;
- unreadable directory;
- deep nesting.

---

## I019 — Implement artifact classification

**Goal**

Classify discovered files using deterministic rules.

**Signals**

- path;
- extension;
- filename;
- binary detection;
- generated-file patterns;
- sensitive-file patterns.

**Rules**

Classification SHALL not require provider inference.

**Tests**

- Python source.
- tests.
- README/docs.
- `.env` and secret-like files.
- lockfiles.
- binaries.
- generated bundles.

---

## I020 — Build Project Inventory

**Goal**

Produce the first complete Scanner artifact.

**Inventory fields**

- project identity;
- inventory identifier;
- project fingerprint;
- artifacts;
- classifications;
- content metadata;
- scan statistics;
- diagnostics;
- scanner version.

**Completion gate**

The same fixture repository produces a semantically identical inventory across repeated runs.

---

## I021 — Implement incremental scanning

**Goal**

Reuse unchanged artifact metadata.

**Rules**

- Content changes invalidate artifact fingerprint.
- Metadata-only changes follow explicit policy.
- Deleted files disappear from the new inventory.
- Renames are not guessed unless reliable evidence exists.

**Tests**

- unchanged file reuse;
- modified file;
- deleted file;
- added file;
- line ending changes;
- timestamp-only changes.

---

# Stage E — Project Indexer

## I022 — Define Indexer port and models

**Goal**

Define index contracts independently of parsing libraries.

**Models**

```text
IndexRequest
ProjectIndex
IndexedArtifact
Symbol
SymbolKind
Relationship
RelationshipKind
SearchUnit
SourceLocation
```

**Completion gate**

A fake Indexer can produce and persist a valid Project Index.

---

## I023 — Implement generic text indexing

**Goal**

Provide useful indexing for unsupported text formats.

**Behavior**

- Divide text into deterministic search units.
- Preserve path and line ranges.
- Avoid splitting in the middle of invalid byte sequences.
- Apply configurable size limits.

**Tests**

- short text;
- long text;
- Unicode;
- empty file;
- large line;
- unsupported encoding diagnostic.

---

## I024 — Implement Python AST parsing

**Goal**

Extract Python structural knowledge using the standard library AST.

**Extract initially**

- modules;
- classes;
- functions;
- async functions;
- imports;
- imported names;
- decorators;
- source locations.

**Do not implement yet**

- full semantic type inference;
- cross-module name resolution;
- runtime import execution.

---

## I025 — Build Python symbols

**Goal**

Convert AST nodes into normalized Symbol objects.

**Tests**

- nested classes/functions;
- decorators;
- async functions;
- duplicate names in different scopes;
- syntax errors;
- Unicode identifiers.

---

## I026 — Build relationships

**Initial relationships**

```text
CONTAINS
IMPORTS
DEFINES
REFERENCES
DEPENDS_ON
```

Start only with relationships supported by deterministic evidence.

Do not infer semantic relationships from naming similarity.

---

## I027 — Build searchable units from Python

**Goal**

Create retrieval units that are useful but bounded.

**Potential units**

- module summary;
- class definition;
- function definition;
- import block;
- relevant source span.

**Rules**

Every unit SHALL preserve source location and content fingerprint.

---

## I028 — Build and persist Project Index

**Goal**

Produce the complete Indexer artifact.

**Completion gate**

- deterministic output;
- unsupported artifacts represented honestly;
- syntax errors reported without aborting unrelated files;
- index can be reloaded and queried.

---

## I029 — Implement incremental indexing

**Goal**

Re-index only artifacts whose relevant content changed.

**Tests**

- unchanged reuse;
- one-file change;
- deletion;
- parser version change;
- index schema change.

---

# Stage F — Retriever

## I030 — Define Retrieval contracts

**Models**

```text
RetrievalRequest
RetrievalCandidate
RetrievalEvidence
SelectionRationale
SelectedContextItem
RetrievalResult
RetrievalStatistics
```

**Completion gate**

Retriever output can represent selected, rejected and truncated candidates with explanations.

---

## I031 — Implement task query normalization

**Goal**

Extract deterministic search signals from Task Specification.

**Signals**

- explicit paths;
- filenames;
- symbols;
- quoted identifiers;
- language-neutral keywords;
- operation hints such as fix, create, rename or explain.

Do not use an LLM in the first implementation.

---

## I032 — Implement explicit-reference strategy

**Goal**

Select directly named files, symbols and paths with high priority.

**Tests**

- exact path;
- filename only;
- symbol reference;
- ambiguous filename;
- missing explicit reference diagnostic.

---

## I033 — Implement lexical search strategy

**Goal**

Rank search units using deterministic text relevance.

Initial implementation may use:

- token overlap;
- normalized term frequency;
- exact phrase bonus;
- path/name bonus.

Avoid embedding dependencies in the first implementation.

---

## I034 — Implement structural strategy

**Goal**

Use symbols and containment to retrieve structurally relevant units.

Examples:

- task names a class;
- include its defining module;
- include containing scope;
- include imports required to understand the definition.

---

## I035 — Implement dependency traversal

**Goal**

Expand candidates through explicit Project Index relationships.

**Rules**

- bounded depth;
- cycle detection;
- deterministic traversal order;
- per-relationship weight;
- traceable traversal path.

---

## I036 — Implement scoring model

**Goal**

Combine retrieval evidence into a stable score.

**Score components should remain inspectable**

```text
explicit_reference
path_match
symbol_match
lexical_relevance
structural_relevance
dependency_distance
artifact_priority
sensitivity_penalty
generated_penalty
```

**Rules**

- No opaque aggregate without component breakdown.
- Stable tie-breaking.
- Configuration validation for weights.

---

## I037 — Implement eligibility and security filters

**Goal**

Remove or restrict candidates before budgeting.

**Policies**

- sensitive content;
- binary content;
- generated content;
- ignored content;
- unsupported content;
- explicit user authorization.

**Completion gate**

A sensitive artifact cannot enter a remote-delivery bundle without policy authorization.

---

## I038 — Implement context budgeting

**Goal**

Select the highest-value eligible context within a bounded budget.

**Initial budget dimensions**

- bytes;
- characters;
- estimated tokens;
- maximum item count.

**Rules**

- deterministic ordering;
- no silent overflow;
- record excluded candidates and reasons;
- reserve capacity for instructions and response contract.

---

## I039 — Implement dependency closure policy

**Goal**

Add required supporting items without uncontrolled expansion.

Examples:

- include interface with implementation;
- include imported type definition;
- include configuration used by selected module.

**Rules**

- closure additions have explicit rationales;
- closure obeys security policy;
- closure obeys hard budget or produces an incomplete-context diagnostic.

---

## I040 — Produce Retrieval Result

**Completion gate**

Every selected item includes:

- rank;
- score breakdown;
- source identity;
- selection rationale;
- evidence;
- size estimate;
- sensitivity classification;
- dependency path when applicable.

---

# Stage G — Context Builder

## I041 — Define Context Bundle models

**Models**

```text
ContextBundle
ContextItem
ContextSection
ContextStatistics
ContextCoverage
```

**Rule**

The Builder SHALL NOT add items not selected by Retrieval Result.

---

## I042 — Implement context item materialization

**Goal**

Load only selected source spans through a read-only content port.

**Rules**

- verify source fingerprint;
- detect stale content;
- preserve path and line ranges;
- normalize encoding safely;
- no unrestricted whole-repository loading.

---

## I043 — Implement deterministic ordering

**Initial order**

1. directly referenced items;
2. primary definitions;
3. structural support;
4. dependencies;
5. supplementary context.

Ordering SHALL follow Retrieval Result semantics and stable tie-breaking.

---

## I044 — Implement Context Bundle validation

**Validate**

- membership equality with selected retrieval items;
- no duplicate source spans;
- source fingerprints;
- budget compliance;
- sensitivity annotations;
- complete traceability.

---

## I045 — Implement context serialization

**Goal**

Serialize Context Bundle independently of provider transport.

Use explicit boundaries such as:

```text
<context_item>
  <path>...</path>
  <location>...</location>
  <content>...</content>
</context_item>
```

The exact format may be Markdown/XML-like or structured messages, but project content must remain clearly untrusted.

---

# Stage H — Prompt Builder

## I046 — Define Inference Request and response contracts

**Models**

```text
InferenceRequest
PromptMessage
ResponseContract
DeliveryRequirements
PromptMeasurements
```

**Rules**

- provider-independent;
- immutable;
- task and context references retained;
- expected output format explicit.

---

## I047 — Implement analysis response contract

**Goal**

Support non-patch analysis tasks first.

**Required response structure**

- summary;
- findings;
- assumptions;
- diagnostics or limitations.

This increment allows provider testing before patch generation.

---

## I048 — Implement patch response contract

**Goal**

Define the provider output expected by Patch Engine.

Prefer a structured envelope containing:

- response type;
- summary;
- assumptions;
- patch format;
- patch payload;
- affected files;
- warnings.

Do not rely only on free-form prose.

---

## I049 — Implement prompt template assembly

**Sections**

1. system operating rules;
2. task specification;
3. context usage rules;
4. serialized Context Bundle;
5. output response contract.

**Security rule**

Repository content cannot override system operating rules.

---

## I050 — Implement prompt measurement

**Measurements**

- bytes;
- characters;
- estimated tokens;
- task contribution;
- context contribution;
- contract contribution;
- remaining provider capacity.

**Completion gate**

Oversized requests fail before provider invocation with actionable diagnostics.

---

# Stage I — Provider Interface

## I051 — Define Provider Port

**Operations**

```text
get_capabilities
health_check
list_models
invoke
cancel
```

Not every adapter must support every optional operation. Capability discovery must report this honestly.

---

## I052 — Implement Provider Capability Profile

**Capabilities**

- context limit;
- structured output support;
- streaming support;
- cancellation support;
- usage reporting;
- local or remote execution mode;
- supported request features.

---

## I053 — Implement deterministic Mock Provider

**Required scenarios**

- successful analysis;
- successful structured patch;
- malformed response;
- timeout;
- cancellation;
- retryable failure;
- non-retryable failure;
- partial stream;
- unexpected tool call;
- missing usage data.

All mandatory tests SHALL use this provider where real inference is unnecessary.

---

## I054 — Implement provider delivery policy

**Goal**

Authorize or reject an Inference Request before transport.

**Evaluate**

- local versus remote provider;
- sensitive context;
- configured policy;
- request size;
- provider capability compatibility;
- explicit user authorization.

---

## I055 — Implement Ollama-compatible adapter health and models

**Goal**

Add connection, health and model discovery before inference.

**Tests**

Use mocked HTTP transport for mandatory tests.

---

## I056 — Implement Ollama-compatible invocation

**Rules**

- explicit timeout;
- no implicit remote fallback;
- preserve request identifier;
- sanitize transport errors;
- do not execute tool calls;
- normalize missing usage data as unavailable.

---

## I057 — Normalize Inference Response

**Model**

```text
InferenceResponse
ProviderUsage
ProviderFinishReason
ProviderDiagnostics
```

**Rules**

- preserve raw response only under retention policy;
- never fabricate usage;
- distinguish timeout, cancellation and malformed output;
- immutable after normalization.

---

# Stage J — Patch Engine

## I058 — Define Patch Proposal models

**Models**

```text
PatchProposal
ProposedChange
PatchOperation
PatchValidationSummary
PatchDiagnostic
```

**Operations**

```text
CREATE
MODIFY
DELETE
RENAME
```

---

## I059 — Validate provider response envelope

**Goal**

Reject outputs that do not match the declared Response Contract.

**Tests**

- invalid JSON;
- missing fields;
- wrong response type;
- unknown patch format;
- inconsistent affected files;
- mixed prose and invalid payload.

---

## I060 — Implement structured patch parser

**Goal**

Parse the safest machine-readable patch format first.

**Validate**

- operation type;
- target path;
- source path for rename;
- expected old fingerprint;
- new content;
- duplicate operations.

---

## I061 — Implement unified diff parser

**Goal**

Support unified diffs without applying them.

**Handle**

- multiple files;
- multiple hunks;
- create/delete markers;
- newline-at-end-of-file markers;
- malformed headers;
- path normalization.

Use a proven parsing library only if its behavior is isolated and thoroughly tested.

---

## I062 — Implement path validation

**Reject**

- absolute paths;
- parent traversal;
- project-root escape;
- invalid rename source/target;
- unsupported device or UNC paths;
- paths inside protected areas when policy forbids them.

---

## I063 — Implement operation validation

**Rules**

- create target must not exist unless overwrite policy explicitly allows it;
- modify target must exist;
- delete target must exist;
- rename source must exist;
- rename target must not conflict;
- expected fingerprints must match proposal source state.

---

## I064 — Implement conflict and consistency validation

**Detect**

- duplicate changes;
- modify and delete same file;
- conflicting renames;
- rename cycles;
- create under deleted directory when modeled;
- affected-file list mismatch;
- inconsistent project fingerprint.

---

## I065 — Produce immutable Patch Proposal

**Completion gate**

A valid provider response produces a fully traceable proposal, while invalid output produces diagnostics and no applicable proposal.

Patch Engine SHALL perform zero project-file writes.

---

# Stage K — Approval and Safe Application

## I066 — Implement proposal lifecycle

**States**

```text
PROPOSED
VALIDATED
AWAITING_APPROVAL
APPROVED
REJECTED
STALE
APPLIED
APPLICATION_FAILED
```

**Rules**

- transitions are explicit;
- rejected proposals cannot be silently reused;
- changed proposal content invalidates approval.

---

## I067 — Implement Approval Record

**Fields**

- approval identifier;
- proposal identifier;
- proposal fingerprint;
- project fingerprint;
- approval timestamp;
- approval method;
- approving principal when available;
- acknowledged warnings.

**Tests**

- proposal mismatch;
- fingerprint mismatch;
- project-state mismatch;
- expired approval if future policy adds expiration.

---

## I068 — Define Patch Application port

**Operations**

```text
preview_application
apply_proposal
```

**Rule**

CLI and Patch Engine cannot write files directly.

---

## I069 — Implement application preflight

**Validate immediately before mutation**

- project fingerprint;
- proposal fingerprint;
- approval binding;
- source file fingerprints;
- path policy;
- permissions;
- protected-file policy;
- lock availability.

---

## I070 — Implement staged filesystem application

**Recommended flow**

1. Create isolated staging area.
2. Materialize proposed final files.
3. Validate staged outputs.
4. Acquire project mutation lock.
5. Revalidate preconditions.
6. Replace files atomically where platform permits.
7. Record Application Result.
8. Release lock.

**Do not execute generated code.**

---

## I071 — Implement rollback and partial-failure reporting

**Rules**

- Never claim rollback unless verified.
- Report applied and unapplied changes.
- Preserve recovery information.
- Return nonzero status for partial application.

---

# Stage L — Application Orchestrator

## I072 — Define application commands and queries

**Commands**

```text
InitializeProject
ScanProject
BuildProjectIndex
ExecuteTask
ApprovePatchProposal
RejectPatchProposal
ApplyPatchProposal
```

**Queries**

```text
GetProjectStatus
GetContextBundle
GetPromptPreview
ListProviders
CheckProviderHealth
GetPatchProposal
GetEffectiveConfiguration
```

---

## I073 — Implement project initialization use case

**Behavior**

- create `.contextforge` safely;
- create minimal config when requested;
- do not modify application source;
- do not invoke provider.

---

## I074 — Implement scan and index use cases

**Rules**

- application layer coordinates ports;
- scanner and indexer remain independently testable;
- compatible existing artifacts may be reused;
- diagnostics are preserved.

---

## I075 — Implement analysis-only execution pipeline

**Pipeline**

```text
Task
→ Inventory
→ Index
→ Retrieval Result
→ Context Bundle
→ Inference Request
→ Provider
→ Analysis Result
```

This is the first complete end-to-end execution and SHALL be implemented before patch application is exposed.

---

## I076 — Implement patch proposal execution pipeline

**Pipeline**

```text
Task
→ Context pipeline
→ Patch Response Contract
→ Provider
→ Inference Response
→ Patch Engine
→ Patch Proposal
→ Awaiting Approval
```

No application occurs in this increment.

---

## I077 — Implement approval and application orchestration

**Rules**

- exact proposal selection required;
- stale project state rejected;
- approval recorded before apply;
- Application Result persisted;
- approval cannot be inferred from `--apply` alone.

---

## I078 — Implement cancellation and stage diagnostics

**Behavior**

- cancellation propagates through provider invocation where supported;
- completed stages remain inspectable;
- cancelled execution is not reported as success;
- locks and temporary resources are released.

---

# Stage M — CLI

## I079 — Implement global CLI options

**Options**

```text
--project
--config
--profile
--provider
--model
--format
--non-interactive
--verbose
--quiet
--debug
--no-color
--version
--help
```

**Rule**

Parsing only. Business decisions belong to application services.

---

## I080 — Implement `init`, `status`, `scan` and `index`

**Tests**

- human-readable output;
- JSON output;
- stdout/stderr separation;
- stable exit codes;
- project resolution failures.

---

## I081 — Implement `run --analysis-only`

**Input modes**

```text
contextforge run "task"
contextforge run --stdin
contextforge run --task-file task.md
```

Exactly one task source SHALL be accepted.

---

## I082 — Implement context inspection commands

**Commands**

```text
contextforge context show
contextforge context list
contextforge context explain
contextforge context export
```

Use persisted application results. Do not rerun retrieval implicitly unless explicitly designed.

---

## I083 — Implement prompt inspection commands

**Commands**

```text
contextforge prompt preview
contextforge prompt measure
contextforge prompt export
```

Sensitive content is redacted according to policy.

---

## I084 — Implement provider commands

**Commands**

```text
contextforge provider list
contextforge provider show
contextforge provider health
contextforge provider models
```

Health checks SHALL not transmit project content.

---

## I085 — Implement patch review commands

**Commands**

```text
contextforge patch list
contextforge patch show
contextforge patch review
contextforge patch export
```

Review output must identify operations, affected files, warnings, validation state and project fingerprint.

---

## I086 — Implement interactive approval and rejection

**Commands**

```text
contextforge patch approve <proposal-id>
contextforge patch reject <proposal-id>
```

High-risk proposals may require typing the proposal identifier.

---

## I087 — Implement non-interactive approval

**Rule**

A generic `--yes` SHALL NOT authorize mutation.

Require exact binding such as:

```text
--approve <proposal-id>
```

and verify proposal and project fingerprints through the application service.

---

## I088 — Implement patch application command

**Command**

```text
contextforge patch apply <proposal-id>
```

**Exit behavior**

- success;
- approval required;
- stale proposal;
- application conflict;
- partial application;
- security rejection.

---

## I089 — Implement config and diagnostics commands

**Commands**

```text
contextforge config show
contextforge config get
contextforge config set
contextforge config validate
contextforge config paths
contextforge diagnostics
```

Secret values remain redacted.

---

## I090 — Stabilize JSON schemas and exit codes

**Goal**

Make the CLI safe for scripting.

**Required JSON envelope**

```json
{
  "schema_version": "1.0",
  "status": "success",
  "data": {},
  "diagnostics": []
}
```

All documented exit codes from CF-012 SHALL have tests.

---

# Stage N — Hardening

## I091 — Build adversarial path test corpus

Include:

- parent traversal;
- absolute POSIX paths;
- Windows drive paths;
- UNC paths;
- alternate separators;
- Unicode normalization variants;
- symlink escapes;
- rename cycles;
- protected directories.

---

## I092 — Build malicious provider-response corpus

Include:

- valid prose with invalid patch;
- code-fenced shell commands;
- path traversal;
- absolute file paths;
- duplicate operations;
- oversized payload;
- malformed JSON;
- conflicting affected-file metadata;
- tool-call structures;
- prompt-injection echoes.

---

## I093 — Add property-based tests

Priority targets:

- path normalization;
- fingerprint stability;
- serialization round-trip;
- retrieval ordering;
- budget invariants;
- patch parsing;
- proposal consistency.

---

## I094 — Add performance baselines

Measure at least:

- scan time by artifact count;
- incremental scan reuse;
- Python index time;
- incremental index reuse;
- retrieval latency;
- context assembly latency;
- prompt size computation;
- patch validation time.

Do not define arbitrary optimization targets before collecting baseline data.

---

## I095 — Add cross-platform test matrix

Test where available:

- Linux;
- Windows;
- macOS;
- Python versions supported by the package.

Prioritize path, encoding, atomic replacement, locking and CLI behavior.

---

## I096 — Complete privacy and logging review

Verify that logs do not contain by default:

- complete task text;
- complete prompt;
- sensitive context;
- credentials;
- full provider output;
- unredacted environment values.

---

# Stage O — Release Preparation

## I097 — Write the user guide

Cover:

- installation;
- project initialization;
- configuration;
- local provider setup;
- scan and index;
- analysis task;
- patch proposal;
- review and approval;
- safe application;
- troubleshooting.

---

## I098 — Write the contributor guide

Cover:

- architecture boundaries;
- package structure;
- local setup;
- test strategy;
- specification traceability;
- ADR workflow;
- adding a parser;
- adding a provider adapter;
- adding a diagnostic code.

---

## I099 — Build release artifacts

Produce:

- wheel;
- source distribution;
- checksums;
- changelog;
- release notes;
- known limitations;
- compatibility matrix.

---

## I100 — Execute the canonical MVP acceptance scenario

Use a fixture or controlled repository and demonstrate:

```text
1. Initialize project.
2. Scan project.
3. Build index.
4. Submit analysis task.
5. Inspect retrieved context.
6. Inspect prompt measurements.
7. Invoke local provider.
8. Generate validated Patch Proposal.
9. Review proposal.
10. Approve exact proposal.
11. Apply proposal safely.
12. Verify resulting project fingerprint.
13. Confirm traceability and diagnostics.
```

The acceptance package SHALL include command transcript, test evidence, resulting artifacts and known limitations.

---

# 5. Recommended LLM task prompt template

Use the following template for each implementation increment.

```text
You are implementing ContextForge increment <INCREMENT_ID>.

Read only these authoritative documents:
- <SPECIFICATION_FILES>
- CF-014 section <INCREMENT_ID>

Goal:
<GOAL>

Affected files:
<FILES_OR_MODULES>

Required behavior:
<REQUIREMENTS>

Required tests:
<TESTS>

Architectural constraints:
- Do not modify unrelated modules.
- Do not introduce dependencies from Core to adapters or CLI.
- Do not execute project or provider-generated code.
- Preserve deterministic behavior.
- Preserve stable diagnostics and traceability.
- Do not weaken security checks to make tests pass.

Before coding:
1. Inspect the current affected files.
2. State any conflict with the authoritative specification.
3. Identify the smallest implementation change.

After coding:
1. Run the focused tests.
2. Run formatting, linting and typing for affected modules.
3. Summarize files changed.
4. Map the implementation to acceptance criteria.
5. List remaining limitations without hiding failures.
```

---

# 6. Recommended review prompt template

```text
Review ContextForge increment <INCREMENT_ID> as a strict software architect and security reviewer.

Authoritative references:
- <SPECIFICATION_FILES>
- CF-014 section <INCREMENT_ID>

Review for:
1. Correctness against requirements.
2. Missing edge cases.
3. Architectural dependency violations.
4. Hidden filesystem or network side effects.
5. Nondeterminism.
6. Secret or sensitive-data leakage.
7. Unsafe handling of provider or project content.
8. Incomplete tests.
9. Misleading success or error states.
10. Unnecessary abstractions or unrelated changes.

Return findings ordered by severity and cite the affected files and lines.
Do not approve the increment while any critical or high-severity finding remains.
```

---

# 7. Stop conditions

Implementation SHALL stop and request an architectural decision when:

- two approved specifications conflict;
- an acceptance criterion cannot be tested objectively;
- a required domain object has ambiguous ownership;
- a Core capability appears to require a concrete adapter dependency;
- provider output would need to be trusted to proceed;
- safe atomic application cannot be guaranteed on a supported platform;
- a requested feature is outside the approved MVP;
- a change would invalidate an approved document without amendment.

---

# 8. Milestone checkpoints

## M0 — Foundation ready

Complete through I004.

## M1 — Shared contracts stable

Complete through I013.

## M2 — Project knowledge complete

Complete through I029.

## M3 — Deterministic context pipeline complete

Complete through I050.

At this point, ContextForge can scan, index, retrieve, build context and build prompts without any real provider.

## M4 — Local inference boundary complete

Complete through I057.

## M5 — Safe proposal lifecycle complete

Complete through I071.

## M6 — End-to-end CLI complete

Complete through I090.

## M7 — MVP release candidate

Complete through I100.

---

# 9. Final implementation principle

The safest implementation sequence is not the sequence that produces the most code quickly.

It is the sequence that establishes a verified contract before each new layer depends on it.

ContextForge should therefore be built as:

```text
Small increment
    ↓
Objective tests
    ↓
Architectural review
    ↓
Stable contract
    ↓
Next increment
```

The project is ready to advance only when the current increment is demonstrably correct, traceable and safe.
