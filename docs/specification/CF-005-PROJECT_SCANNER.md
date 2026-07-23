# Project Scanner Specification

Document ID: CF-005
Status: Draft
Version: 0.1.0
Owner: ContextForge Architecture Board
Language: English
Audience:

* Engineers
* Contributors
* Product Owners
* AI Agents

Normative: Yes

Depends On:

* CF-000 — AI-Native Specification
* CF-001 — Vision
* CF-002 — Product Requirements Document
* CF-003 — System Architecture
* CF-004 — Domain Model

Related ADRs:

* ADR-0001 — Context-First Architecture
* ADR-0002 — Hexagonal Architecture
* ADR-0003 — Dependency Rule
* ADR-0004 — Feature-Based Module Organization

---

# Abstract

This document defines the Project Scanner capability of ContextForge.

The Project Scanner discovers eligible artifacts inside an authorized Project Root and produces an immutable Project Inventory.

The scanner SHALL perform deterministic discovery only.

It SHALL NOT:

* Interpret user intent.
* Rank artifact relevance.
* Build project knowledge.
* Construct context.
* Invoke inference providers.
* Modify project files.

---

# Purpose

The Project Scanner establishes the authoritative view of what exists inside a project before indexing and retrieval begin.

Its primary responsibilities are:

* Validate the Project Root.
* Traverse eligible project paths.
* Apply exclusion rules.
* Classify discovered artifacts.
* Collect discovery metadata.
* Detect supported and unsupported artifacts.
* Produce a Project Inventory.
* Report discovery diagnostics.

---

# Scope

The Project Scanner SHALL support:

* Local project discovery.
* Directory traversal.
* File and directory identification.
* Path normalization.
* Exclusion-rule evaluation.
* Basic content classification.
* Basic language detection.
* Metadata collection.
* Discovery diagnostics.
* Deterministic inventory generation.

The MVP scanner SHALL operate on one Project Root per scan operation.

---

# Out of Scope

The Project Scanner SHALL NOT:

* Parse source-code syntax trees.
* Extract symbols.
* Resolve imports.
* Build dependency graphs.
* Calculate task relevance.
* Generate embeddings.
* Read provider configuration.
* Generate prompts.
* Apply patches.
* Execute project code.
* Follow arbitrary external links.
* Modify exclusion files.
* Perform distributed scanning.
* Scan remote repositories directly.

A remote repository MAY be scanned only after another component or user makes it available through an authorized local Project Root.

---

# Capability Boundary

The Project Scanner consumes:

* Project.
* Project Root.
* Exclusion Rules.
* Scanner Configuration.

The Project Scanner produces:

* Project Inventory.
* Project Artifacts.
* Discovery Diagnostics.
* Discovery Measurements.

The Project Scanner accesses project content exclusively through the Project Source Port.

---

# Primary Contract

The Project Scanner SHALL expose a logical operation equivalent to:

```text
scan(project, configuration) -> Project Inventory
```

The operation SHALL either:

1. Return a completed Project Inventory; or
2. Return a defined discovery failure.

A partially completed inventory MAY be included with a recoverable failure when explicitly supported by the caller.

---

# Inputs

## Project

The Project SHALL identify:

* Project Identifier.
* Authorized Project Root.
* Project Metadata when available.
* Project-level exclusion rules.

The scanner SHALL reject a Project with an invalid Project Root.

---

## Scanner Configuration

Scanner Configuration MAY define:

* Maximum traversal depth.
* Maximum artifact count.
* Maximum individual file size.
* Whether hidden files are eligible.
* Whether symbolic links are eligible.
* Whether generated files are eligible.
* Whether binary files are listed.
* Default exclusion rules.
* Additional inclusion rules.
* Additional exclusion rules.
* Language detection behavior.
* Failure behavior for unreadable paths.

Configuration SHALL NOT permit traversal outside the Project Root.

---

## Exclusion Rules

Exclusion Rules MAY originate from:

* ContextForge defaults.
* Project configuration.
* Version control ignore files.
* User configuration.
* Security policy.

Each rule SHALL preserve its source and priority.

---

# Outputs

## Project Inventory

A successful scan SHALL produce one immutable Project Inventory containing:

* Project Identifier.
* Inventory Identifier.
* Project State Fingerprint.
* Discovered Project Artifacts.
* Applied Exclusion Rules.
* Discovery Diagnostics.
* Discovery Measurements.
* Discovery timestamp.
* Scanner version.

The inventory SHALL distinguish between:

* Included artifacts.
* Excluded artifacts when retained for diagnostics.
* Unsupported artifacts.
* Unreadable artifacts.
* Skipped artifacts.

---

## Discovery Measurements

Discovery Measurements SHOULD include:

* Number of directories visited.
* Number of artifacts discovered.
* Number of artifacts included.
* Number of artifacts excluded.
* Number of unsupported artifacts.
* Number of unreadable paths.
* Total discovered byte size.
* Scan duration.

Measurements SHALL NOT alter discovery decisions.

---

# Project Root Validation

Before traversal begins, the scanner SHALL validate the Project Root.

The Project Root SHALL:

* Exist.
* Resolve to a directory.
* Be accessible for reading.
* Be normalized.
* Resolve to an absolute path.
* Remain stable during initial validation.

The scanner SHALL reject:

* Missing roots.
* Regular files supplied as roots.
* Unauthorized roots.
* Roots that cannot be normalized.
* Roots whose resolved location violates a configured security boundary.

---

# Path Model

All discovered paths SHALL have two representations:

1. Resolved absolute path for adapter-level access.
2. Normalized project-relative path for Core domain use.

Core Project Artifacts SHALL store project-relative paths.

Absolute paths SHALL NOT be required outside boundary adapters except where explicitly necessary for diagnostics.

A project-relative path SHALL:

* Use a canonical separator representation.
* Not begin with a root separator.
* Not contain unresolved parent traversal.
* Resolve inside the Project Root.

---

# Path Containment

For every path considered during scanning, the scanner SHALL verify that the resolved path remains inside the authorized Project Root.

The following SHALL be rejected or skipped:

* Parent-directory traversal outside the root.
* Symbolic links resolving outside the root.
* Mount or junction behavior that escapes the root.
* Invalid path normalization.
* Adapter results that do not preserve containment.

Containment checks SHALL occur after path resolution.

String-prefix comparison alone SHALL NOT be considered sufficient containment validation.

---

# Traversal

The scanner SHALL traverse the Project Root deterministically.

Traversal order SHALL be stable for the same project state and configuration.

The recommended canonical order is:

1. Normalize directory entries.
2. Sort entries by normalized project-relative path.
3. Evaluate exclusion rules.
4. Classify each entry.
5. Traverse eligible directories.
6. Record eligible artifacts.

Parallel traversal MAY be used only if final inventory ordering remains deterministic.

---

# Traversal Depth

The root directory SHALL have depth zero.

If a maximum depth is configured:

* Entries at or below the maximum depth MAY be included.
* Directories beyond the maximum depth SHALL NOT be traversed.
* A diagnostic SHOULD indicate depth-based exclusion.

A missing maximum depth SHALL mean traversal is not limited by depth, subject to other limits.

---

# Artifact Limits

The scanner MAY enforce configured limits for:

* Total artifact count.
* Total discovered byte size.
* Maximum file size.
* Maximum directory entries.
* Scan duration.

When a mandatory limit is exceeded, the scanner SHALL:

1. Stop safely or skip the affected artifact according to configuration.
2. Produce a diagnostic.
3. Mark the inventory as incomplete when applicable.
4. Avoid silently omitting eligible artifacts.

---

# Exclusion Evaluation

Exclusion evaluation SHALL occur before reading file content whenever path metadata is sufficient.

An exclusion decision SHALL retain:

* Rule source.
* Matched rule.
* Decision.
* Target path.
* Priority.

The scanner SHALL support directory exclusions that prevent descendant traversal.

---

# Exclusion Precedence

Rules SHALL be evaluated in a deterministic precedence order.

The canonical precedence is:

1. Mandatory security restrictions.
2. Explicit user exclusions.
3. Explicit user inclusions.
4. Project-specific ContextForge rules.
5. Version control ignore rules.
6. ContextForge default exclusions.
7. Default inclusion.

A higher-precedence mandatory security exclusion SHALL NOT be overridden.

Within the same precedence level, the last applicable rule MAY take priority when the rule format supports ordered overrides.

---

# Default Exclusions

The MVP SHOULD provide safe default exclusions for common non-source or high-volume paths.

Examples MAY include:

* Version control metadata.
* Dependency caches.
* Virtual environments.
* Build output.
* Distribution output.
* Coverage output.
* Tool caches.
* Temporary directories.
* IDE metadata.
* Operating system metadata.

Canonical examples include:

```text
.git/
.hg/
.svn/
node_modules/
vendor/
.venv/
venv/
env/
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
coverage/
dist/
build/
target/
out/
.cache/
.idea/
.vscode/
```

Default exclusions SHALL be configurable.

The presence of a name in this list SHALL NOT override an explicit higher-priority inclusion unless prohibited by security policy.

---

# Hidden Artifacts

Hidden artifact behavior SHALL be configurable.

When hidden artifacts are enabled, mandatory security and exclusion rules SHALL still apply.

Hidden status SHALL NOT automatically imply sensitivity or exclusion.

---

# Symbolic Links

The default MVP behavior SHOULD be to skip symbolic links.

If symbolic-link traversal is enabled:

* The target SHALL be resolved before traversal.
* The target SHALL remain inside the Project Root.
* Link cycles SHALL be detected.
* The scanner SHALL avoid duplicate traversal of the same resolved target.
* The artifact SHALL retain link metadata.

A symbolic link resolving outside the Project Root SHALL NOT be traversed.

---

# Cycle Detection

Traversal SHALL protect against cycles caused by:

* Symbolic links.
* Junctions.
* Mount behavior.
* Adapter anomalies.

Cycle detection MAY use:

* Resolved canonical paths.
* File-system identifiers.
* Adapter-provided stable identities.

A detected cycle SHALL produce a diagnostic and SHALL NOT cause scan failure unless configured otherwise.

---

# File Classification

Each discovered file SHALL receive an Artifact Kind and Content Classification.

Classification SHALL be deterministic for the same file state and configuration.

Classification MAY use:

* Project-relative path.
* File name.
* Extension.
* File metadata.
* Limited content inspection.
* Known manifest names.
* Known build-file names.
* Known generated-file patterns.

Classification SHALL NOT require inference.

---

# Artifact Kind Detection

The scanner SHOULD recognize at least:

* Source files.
* Test files.
* Configuration files.
* Documentation files.
* Manifest files.
* Build files.
* Generated files.
* Binary files.
* Unknown files.

Classification MAY be refined by later language-specific components.

The scanner SHALL NOT interpret this classification as task relevance.

---

# Test Artifact Detection

A file MAY be classified as a test artifact using deterministic evidence such as:

* Conventional test directory.
* Conventional test file name.
* Conventional test suffix or prefix.
* Language-specific test convention.

Test classification SHALL preserve any detected language classification.

---

# Configuration Artifact Detection

Configuration artifacts MAY be identified through:

* Known file names.
* Known extensions.
* Known configuration directories.
* Project-level configuration.

Examples MAY include:

* `pyproject.toml`
* `package.json`
* `docker-compose.yml`
* `Dockerfile`
* `.editorconfig`
* `tsconfig.json`
* `Cargo.toml`

This list SHALL be extensible without changing Core scanner semantics.

---

# Manifest Detection

Manifest artifacts MAY include files that describe:

* Dependencies.
* Packages.
* Build metadata.
* Workspace structure.
* Project metadata.

Manifest detection SHALL remain deterministic and provider-independent.

---

# Generated Artifact Detection

Generated status MAY be determined from:

* Excluded output directories.
* File headers.
* Known generated naming patterns.
* Project configuration.
* Language-specific conventions.

Generated status SHALL preserve its Evidence.

A generated artifact MAY be listed while remaining ineligible for indexing.

---

# Binary Detection

The scanner SHALL classify likely binary files without requiring full file reads.

Binary detection MAY use:

* Known binary extensions.
* MIME-like metadata provided by the adapter.
* Presence of binary control bytes in a bounded sample.
* Decoding failure under supported text encodings.
* Project configuration.

Binary detection SHALL use bounded inspection.

Binary files SHALL NOT be read as ordinary source text.

---

# Text Encoding

The scanner SHOULD support UTF-8 text.

It MAY detect:

* UTF-8 with byte-order mark.
* UTF-16 variants.
* Other configured encodings.

Unsupported or ambiguous encoding SHALL produce a diagnostic.

The scanner SHALL NOT silently replace undecodable content when classification accuracy would be affected.

Full encoding normalization belongs outside the scanner unless required by a later specification.

---

# Language Detection

The scanner MAY assign a detected language to text artifacts.

Language detection SHOULD use deterministic evidence in this order:

1. Explicit project configuration.
2. Canonical file name.
3. File extension.
4. Interpreter or language declaration.
5. Bounded content heuristic.
6. Unknown.

Language detection SHALL preserve its Evidence when practical.

The scanner SHALL NOT parse language syntax to validate the detected language.

---

# Supported Language Registry

The scanner SHALL obtain supported-language information through an internal contract or configuration.

A language registry MAY define:

* Language identifier.
* Recognized extensions.
* Recognized canonical file names.
* Whether indexing is supported.
* Whether text retrieval is supported.

The scanner SHALL distinguish:

* Detected language.
* Supported language.
* Indexable artifact.

A detected language MAY be unsupported by the active installation.

---

# File Metadata

For each included file, the scanner SHOULD collect:

* Project-relative path.
* Artifact Kind.
* Content Classification.
* File size.
* Modification timestamp when available.
* Detected language.
* Encoding when detected.
* Generated status.
* Link status.
* Readability state.

The scanner MAY collect:

* Content hash.
* Line count.
* Bounded content signature.

Expensive metadata SHALL be configurable.

---

# Content Hashing

Content hashing MAY be used to:

* Produce a Project State Fingerprint.
* Detect changed artifacts.
* Support incremental indexing.
* Detect duplicate content.

Hashing behavior SHALL define:

* Hash algorithm.
* Whether all eligible files are hashed.
* Maximum file size for hashing.
* Failure behavior.

The selected hash algorithm SHALL be stable and documented.

Cryptographic security SHALL NOT be assumed unless explicitly required.

---

# Project State Fingerprint

The scanner SHALL produce or contribute to a Project State Fingerprint.

The fingerprint SHOULD reflect:

* Included artifact paths.
* Relevant artifact metadata.
* Content hashes when enabled.
* Effective scanner configuration.
* Effective exclusion rules.
* Scanner format version.

The fingerprint SHALL change when a relevant scanned project state changes.

The fingerprint SHALL NOT depend on traversal timing or nondeterministic ordering.

---

# Inventory Ordering

Project Artifacts in the final inventory SHALL be ordered deterministically.

The canonical ordering SHALL be normalized project-relative path order.

Directories MAY precede files only if this behavior is explicitly defined and stable.

Consumers SHALL NOT depend on operating-system directory enumeration order.

---

# Read Strategy

The scanner SHALL minimize file-content reads.

It SHOULD use this sequence:

1. Read path metadata.
2. Apply path-based exclusions.
3. Apply file-size rules.
4. Perform bounded classification reads when necessary.
5. Read full content only when explicitly required by scanner configuration.

Full source content retrieval is not a primary scanner responsibility.

---

# Large Files

A file exceeding the configured maximum file size SHALL:

* Remain represented in the inventory when configured.
* Be marked as oversized.
* Avoid full content reads.
* Be ineligible for ordinary indexing unless another policy allows it.
* Produce a diagnostic when relevant.

The scanner SHALL NOT fail the entire project solely because one oversized file exists unless strict mode is enabled.

---

# Unreadable Paths

An unreadable path SHALL produce a discovery diagnostic.

Configuration SHALL define whether unreadable paths:

* Fail the scan.
* Produce a partial inventory.
* Are skipped with warnings.

The default MVP behavior SHOULD be:

* Fail when the Project Root is unreadable.
* Warn and skip unreadable descendant artifacts.
* Mark the inventory as incomplete.

---

# Changing Project State

The project MAY change while scanning.

The scanner SHOULD detect material inconsistencies when practical, including:

* Artifact removed before metadata collection.
* Artifact changed during hashing.
* Directory changed during traversal.
* Root replaced during scan.

The scanner MAY:

* Retry the affected artifact.
* Skip the artifact with a diagnostic.
* Mark the inventory as potentially inconsistent.
* Fail in strict mode.

The scanner SHALL NOT claim a fully consistent snapshot unless the underlying adapter guarantees one.

---

# Discovery Status

A Project Inventory SHALL have one discovery status:

* Complete.
* Complete with warnings.
* Incomplete.
* Failed.

A failed scan MAY return diagnostics without returning an authoritative inventory.

An incomplete inventory SHALL NOT be treated as equivalent to a complete inventory.

---

# Diagnostics

The scanner SHALL produce structured diagnostics.

Each diagnostic SHALL include:

* Diagnostic code.
* Severity.
* Message.
* Related project-relative path when applicable.
* Producing capability.
* Recoverability indication when applicable.

Scanner diagnostic severities are:

* Information.
* Warning.
* Error.

---

# Canonical Diagnostic Codes

The MVP SHOULD define at least:

| Code                         | Meaning                                         |
| ---------------------------- | ----------------------------------------------- |
| `SCAN_ROOT_NOT_FOUND`        | Project Root does not exist                     |
| `SCAN_ROOT_NOT_DIRECTORY`    | Project Root is not a directory                 |
| `SCAN_ROOT_UNREADABLE`       | Project Root cannot be read                     |
| `SCAN_PATH_OUTSIDE_ROOT`     | Resolved path escapes the Project Root          |
| `SCAN_PATH_UNREADABLE`       | Descendant path cannot be read                  |
| `SCAN_SYMLINK_SKIPPED`       | Symbolic link was skipped                       |
| `SCAN_SYMLINK_OUTSIDE_ROOT`  | Symbolic link resolves outside the Project Root |
| `SCAN_CYCLE_DETECTED`        | Traversal cycle was detected                    |
| `SCAN_MAX_DEPTH_REACHED`     | Maximum traversal depth was reached             |
| `SCAN_MAX_ARTIFACTS_REACHED` | Maximum artifact count was reached              |
| `SCAN_FILE_TOO_LARGE`        | File exceeds configured size limit              |
| `SCAN_BINARY_DETECTED`       | File was classified as binary                   |
| `SCAN_ENCODING_UNSUPPORTED`  | Text encoding is unsupported                    |
| `SCAN_LANGUAGE_UNKNOWN`      | Language could not be detected                  |
| `SCAN_LANGUAGE_UNSUPPORTED`  | Detected language is unsupported                |
| `SCAN_PROJECT_CHANGED`       | Project changed during scanning                 |
| `SCAN_INVENTORY_INCOMPLETE`  | Inventory is incomplete                         |

Diagnostic codes SHALL remain stable after publication.

---

# Failure Model

The scanner SHALL distinguish between recoverable discovery conditions and terminal failures.

## Terminal Failures

Examples include:

* Invalid Project Root.
* Unauthorized Project Root.
* Root path escapes an allowed security boundary.
* Scanner configuration is invalid.
* Project Source Port is unavailable.
* Mandatory artifact limit is exceeded in strict mode.

A terminal failure SHALL prevent creation of a successful Project Inventory.

---

## Recoverable Conditions

Examples include:

* Unreadable descendant file.
* Unsupported encoding.
* Unsupported language.
* Oversized file.
* Skipped symbolic link.
* Detected cycle.
* Excluded path.
* Binary artifact.
* Project mutation affecting one artifact.

Recoverable conditions SHALL be represented through diagnostics.

---

# Determinism

Given the same:

* Project state.
* Project Root.
* Scanner Configuration.
* Exclusion Rules.
* Language Registry.
* Scanner version.

The scanner SHOULD produce semantically equivalent Project Inventories.

The following SHALL NOT affect semantic output:

* File-system enumeration order.
* Thread scheduling.
* Scan start time, except timestamp metadata.
* Diagnostic ordering caused solely by concurrency.

---

# Performance Requirements

The scanner SHALL prioritize correctness and containment over raw traversal speed.

The MVP scanner SHOULD:

* Avoid reading excluded file contents.
* Use bounded inspection for classification.
* Avoid loading the entire project into memory.
* Support streaming traversal internally.
* Preserve deterministic output.
* Remain responsive on ordinary software repositories.

Specific performance thresholds SHALL be established through benchmark fixtures rather than embedded in this specification.

---

# Memory Requirements

The scanner SHALL NOT require all file contents to remain in memory.

The implementation MAY accumulate artifact metadata before producing the immutable inventory.

For large projects, the scanner SHOULD support bounded-memory traversal.

---

# Security Requirements

The scanner SHALL:

* Treat project content as untrusted.
* Avoid executing project files.
* Avoid importing project modules.
* Reject path traversal.
* Enforce Project Root containment.
* Avoid following external symbolic links.
* Avoid exposing file content in diagnostics by default.
* Avoid logging secrets discovered during classification.
* Apply mandatory security exclusions.

The scanner SHALL NOT use source-code execution as a detection mechanism.

---

# Sensitive Artifact Detection

The scanner MAY classify artifacts as sensitive using deterministic path or content indicators.

Examples MAY include:

* Environment files.
* Private keys.
* Credential files.
* Token files.
* Secret configuration.
* Cloud credentials.

Sensitive detection SHALL:

* Preserve Evidence.
* Avoid exposing secret values.
* Be configurable.
* Support mandatory patterns.

Sensitive classification SHALL NOT automatically delete or modify an artifact.

---

# Adapter Contract

The Project Source Port used by the scanner SHALL support logical operations equivalent to:

* Validate root.
* Resolve path.
* List directory.
* Read metadata.
* Read bounded content.
* Read complete content when authorized.
* Identify link.
* Resolve link.
* Obtain stable file identity when available.

The Core scanner SHALL NOT depend on operating-system-specific path APIs.

The adapter SHALL translate native errors into defined boundary failures.

---

# Interaction with Project Indexer

The Project Scanner SHALL provide the Project Inventory to the Project Indexer.

The Project Indexer SHALL rely on the scanner for:

* Artifact identity.
* Project-relative paths.
* Basic classification.
* Language detection.
* Availability state.
* Exclusion decisions.
* Project State Fingerprint.

The Project Indexer MAY refine metadata but SHALL NOT silently reintroduce scanner-excluded artifacts.

---

# Interaction with Application Orchestrator

The Application Orchestrator SHALL:

* Provide the Project and Scanner Configuration.
* Receive the Project Inventory or discovery failure.
* Record the discovery stage result.
* Prevent indexing when discovery fails.
* Decide whether an incomplete inventory is acceptable under workflow policy.

The scanner SHALL NOT control the complete execution lifecycle.

---

# Interaction with Configuration

Configuration resolution SHALL occur before scanning begins.

The scanner SHALL receive effective configuration.

It SHALL NOT be responsible for:

* Searching arbitrary global configuration locations.
* Resolving provider configuration.
* Prompting the user interactively.
* Modifying configuration files.

The scanner MAY report configuration contradictions.

---

# Incremental Discovery

The domain SHALL permit future incremental scanning.

The MVP MAY support incremental discovery using:

* Previous Project Inventory.
* Previous Project State Fingerprint.
* File metadata.
* Content hashes.

Incremental behavior SHALL produce an inventory semantically equivalent to a complete scan for the same project state.

Incremental discovery SHALL NOT be required for initial MVP acceptance unless defined by the implementation plan.

---

# Concurrency

The scanner MAY use concurrency for metadata collection or classification.

Concurrency SHALL NOT:

* Violate path containment.
* Change rule precedence.
* Change final artifact ordering.
* Cause duplicate artifacts.
* Produce nondeterministic identities.
* Hide individual failures.

Concurrency is an implementation choice, not a domain requirement.

---

# Extension Points

The scanner MAY support extension through controlled registries for:

* Language detection rules.
* Artifact-kind classifiers.
* Sensitive-file detectors.
* Generated-file detectors.
* Default exclusion patterns.

Extensions SHALL:

* Be deterministic.
* Declare priority.
* Avoid project code execution.
* Preserve scanner invariants.
* Avoid provider dependencies.

The MVP SHALL NOT require third-party runtime plugin loading.

---

# Observability

The scanner SHOULD expose measurements and diagnostics sufficient to explain:

* Which paths were scanned.
* Which paths were excluded.
* Why paths were excluded.
* How artifacts were classified.
* Whether limits were reached.
* Whether the inventory is complete.
* How long scanning required.

Observability SHALL NOT require external telemetry services.

---

# Privacy

The scanner SHALL avoid transmitting project information outside the local process.

The scanner itself SHALL NOT invoke network services.

File paths and project metadata SHALL remain local unless another explicitly authorized capability uses them.

---

# Traceability

| Requirement Area             | Scanner Responsibility                           |
| ---------------------------- | ------------------------------------------------ |
| Project analysis             | Discover project structure                       |
| Supported artifacts          | Detect artifact type and language                |
| Project indexing preparation | Produce normalized Project Inventory             |
| Offline operation            | Use local Project Source Adapter                 |
| Deterministic analysis       | Apply deterministic traversal and classification |
| Explainability               | Preserve exclusion and classification evidence   |
| Security                     | Enforce Project Root containment                 |
| Modularity                   | Operate through Project Source Port              |
| Cross-platform support       | Use normalized Core paths and adapters           |

---

# Acceptance Criteria

The Project Scanner SHALL satisfy all of the following acceptance criteria.

## AC-SCAN-001 — Valid Project Discovery

Given an accessible supported Project Root, the scanner SHALL produce a Project Inventory.

---

## AC-SCAN-002 — Deterministic Paths

Given an unchanged project and unchanged configuration, discovered project-relative paths SHALL be semantically identical across scans.

---

## AC-SCAN-003 — Root Containment

Given a path or symbolic link that resolves outside the Project Root, the scanner SHALL reject or skip it and produce a diagnostic.

---

## AC-SCAN-004 — Exclusion Enforcement

Given an applicable exclusion rule, the scanner SHALL exclude the matching artifact or directory according to rule precedence.

---

## AC-SCAN-005 — Directory Pruning

Given an excluded directory, the scanner SHALL NOT traverse its descendants unless a valid higher-priority inclusion rule requires traversal.

---

## AC-SCAN-006 — Artifact Classification

Given a recognized source, test, configuration, documentation, manifest, build, generated, or binary artifact, the scanner SHALL assign the appropriate classification using deterministic rules.

---

## AC-SCAN-007 — Unsupported Language

Given a text artifact with a detected but unsupported language, the scanner SHALL retain or skip it according to configuration and produce an appropriate diagnostic.

---

## AC-SCAN-008 — Binary Safety

Given a binary file, the scanner SHALL NOT treat its full content as ordinary source text.

---

## AC-SCAN-009 — Unreadable Descendant

Given an unreadable descendant artifact under non-strict behavior, the scanner SHALL continue safely, mark the inventory appropriately, and produce a diagnostic.

---

## AC-SCAN-010 — Invalid Root

Given a missing, unreadable, unauthorized, or non-directory Project Root, the scanner SHALL fail without producing a successful inventory.

---

## AC-SCAN-011 — Stable Ordering

Given a completed scan, Project Artifacts SHALL be ordered deterministically by normalized project-relative path.

---

## AC-SCAN-012 — Limit Reporting

Given a configured limit that is reached, the scanner SHALL not silently omit artifacts and SHALL report the limit through diagnostics and inventory status.

---

## AC-SCAN-013 — No Project Execution

The scanner SHALL complete discovery without executing, importing, compiling, or evaluating project code.

---

## AC-SCAN-014 — Inventory Immutability

A completed Project Inventory SHALL be immutable.

---

## AC-SCAN-015 — Indexer Readiness

A complete Project Inventory SHALL contain sufficient normalized artifact information for the Project Indexer to begin indexing without repeating directory discovery.

---

# Test Categories

The Project Scanner SHALL be verified through:

* Unit tests for rule precedence.
* Unit tests for path normalization.
* Unit tests for classification.
* Unit tests for language detection.
* Unit tests for limit behavior.
* Integration tests with temporary project trees.
* Security tests for path traversal.
* Security tests for external symbolic links.
* Determinism tests.
* Large-project fixture tests.
* Cross-platform path tests.
* Fault-injection tests for unreadable or changing artifacts.

Tests SHALL NOT depend on network access.

---

# Reference Project Fixtures

The test suite SHOULD include fixtures containing:

* Small single-language project.
* Multi-language project.
* Nested project structure.
* Hidden files.
* Excluded dependency directories.
* Generated files.
* Binary files.
* Oversized files.
* Unsupported-language files.
* Invalid encodings.
* Internal symbolic links.
* External symbolic links.
* Symbolic-link cycle.
* Unreadable paths where supported.
* Project mutation during scanning.
* Conflicting exclusion and inclusion rules.

---

# Validation Criteria

This specification SHALL be considered satisfied when:

* The Project Root is validated before traversal.
* All discovered artifacts remain within the root.
* Traversal is deterministic.
* Exclusion precedence is deterministic.
* Artifact metadata is normalized.
* Basic classification is deterministic.
* Project content is never executed.
* Binary and unsupported content are handled safely.
* Discovery diagnostics are structured.
* Inventory completeness is explicit.
* The resulting Project Inventory is immutable and ready for indexing.

---

# Completion Statement

The Project Scanner is complete when ContextForge can deterministically and safely discover an authorized local software project, apply exclusion and security rules, classify project artifacts, report discovery conditions, and produce an immutable Project Inventory suitable for the Project Indexer.
