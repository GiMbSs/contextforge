# Project Indexer Specification

Document ID: CF-006
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
* CF-005 — Project Scanner Specification

Related ADRs:

* ADR-0001 — Context-First Architecture
* ADR-0002 — Hexagonal Architecture
* ADR-0003 — Dependency Rule
* ADR-0004 — Feature-Based Module Organization

---

# Abstract

This document defines the Project Indexer capability of ContextForge.

The Project Indexer transforms a Project Inventory and eligible project content into a structured, immutable Project Index.

The Project Index SHALL represent deterministic project knowledge suitable for retrieval, including:

* Artifact metadata.
* Structural units.
* Symbols.
* Imports.
* References.
* Dependency relationships.
* Searchable text units.
* Index diagnostics.

The Project Indexer SHALL NOT:

* Interpret task relevance.
* Select context for a user request.
* Generate prompts.
* Invoke inference providers.
* Generate patches.
* Modify project artifacts.

---

# Purpose

The Project Indexer converts project discovery data into structured knowledge that can be efficiently queried by the Context Retriever.

Its primary responsibilities are:

* Validate Project Inventory compatibility.
* Read eligible artifact content.
* Select an indexing strategy.
* Extract deterministic structural information.
* Normalize symbols and relationships.
* Create searchable index units.
* Preserve source traceability.
* Produce an immutable Project Index.
* Report indexing diagnostics.

---

# Scope

The Project Indexer SHALL support:

* Indexing eligible text artifacts.
* Artifact-level metadata indexing.
* Language-aware structural extraction.
* Symbol extraction where supported.
* Import and dependency extraction where supported.
* Source-location preservation.
* Searchable text-unit generation.
* Project-level relationship generation.
* Index versioning.
* Project-state compatibility checks.
* Structured diagnostics.
* Deterministic output.

The MVP SHALL support complete index generation from a Project Inventory.

Incremental indexing MAY be implemented when it preserves semantic equivalence with complete indexing.

---

# Out of Scope

The Project Indexer SHALL NOT:

* Traverse the project independently.
* Reintroduce scanner-excluded artifacts.
* Infer task-specific relevance.
* Build a Context Bundle.
* Invoke an LLM for routine indexing.
* Execute source code.
* Install project dependencies.
* Compile the project.
* Run project tests.
* Modify project artifacts.
* Resolve dynamic runtime behavior.
* Guarantee complete semantic understanding.
* Require a vector database.
* Require a persistent database server.
* Require network access.

---

# Capability Boundary

The Project Indexer consumes:

* Project Inventory.
* Project State Fingerprint.
* Indexer Configuration.
* Supported Language Registry.
* Eligible artifact content through the Project Source Port.
* Previous Project Index when incremental indexing is enabled.

The Project Indexer produces:

* Project Index.
* Indexed Artifact Records.
* Structural Units.
* Symbols.
* Artifact Relationships.
* Searchable Text Units.
* Index Diagnostics.
* Index Measurements.

---

# Primary Contract

The Project Indexer SHALL expose a logical operation equivalent to:

```text
index(project_inventory, configuration) -> Project Index
```

An incremental implementation MAY additionally expose:

```text
update(previous_index, project_inventory, configuration) -> Project Index
```

The operation SHALL either:

1. Produce a completed Project Index; or
2. Return a defined indexing failure.

A partially completed Project Index MAY be returned only when explicitly identified as incomplete and accepted by workflow policy.

---

# Inputs

## Project Inventory

The Project Inventory SHALL provide:

* Project Identifier.
* Inventory Identifier.
* Project State Fingerprint.
* Discovered Project Artifacts.
* Artifact classifications.
* Detected languages.
* Availability states.
* Discovery diagnostics.
* Effective exclusion decisions.

The indexer SHALL reject an inventory that:

* Does not identify a Project.
* Has an invalid Project State Fingerprint.
* Contains invalid project-relative paths.
* Violates Project Root containment.
* Is incompatible with the supported inventory format.

---

## Indexer Configuration

Indexer Configuration MAY define:

* Enabled languages.
* Enabled index strategies.
* Maximum indexed artifact size.
* Maximum structural unit size.
* Maximum artifact count.
* Maximum total indexed content.
* Whether symbols are extracted.
* Whether imports are extracted.
* Whether references are extracted.
* Whether documentation text is indexed.
* Whether comments are indexed.
* Whether generated artifacts are indexed.
* Whether test artifacts are indexed.
* Whether unsupported text is indexed generically.
* Whether content hashes are retained.
* Failure behavior.
* Incremental indexing behavior.

Configuration SHALL NOT permit indexing scanner-excluded artifacts unless a new authorized scan produces an inventory that includes them.

---

## Supported Language Registry

The Supported Language Registry SHALL describe available indexing strategies.

A language entry MAY define:

* Canonical language identifier.
* Recognized artifact types.
* Parser availability.
* Symbol extraction support.
* Import extraction support.
* Reference extraction support.
* Generic text fallback support.
* Index strategy version.

Language registry entries SHALL be deterministic and provider-independent.

---

# Outputs

## Project Index

A successful indexing operation SHALL produce one immutable Project Index containing:

* Project Identifier.
* Index Identifier.
* Source Inventory Identifier.
* Project State Fingerprint.
* Index format version.
* Indexer version.
* Indexed Artifact Records.
* Structural Units.
* Symbols.
* Artifact Relationships.
* Searchable Text Units.
* Index Diagnostics.
* Index Measurements.
* Index status.
* Creation timestamp.

A Project Index SHALL distinguish:

* Fully indexed artifacts.
* Partially indexed artifacts.
* Metadata-only artifacts.
* Skipped artifacts.
* Unsupported artifacts.
* Failed artifacts.

---

## Index Measurements

Index Measurements SHOULD include:

* Number of inventory artifacts evaluated.
* Number of artifacts indexed.
* Number of artifacts skipped.
* Number of artifacts indexed as metadata only.
* Number of symbols extracted.
* Number of relationships extracted.
* Number of searchable text units generated.
* Total indexed bytes.
* Total indexed lines.
* Index duration.
* Number of parsing failures.
* Number of fallback operations.

Measurements SHALL NOT alter index semantics.

---

# Index Status

A Project Index SHALL have one status:

* Complete.
* Complete with warnings.
* Incomplete.
* Failed.

A failed indexing operation SHALL NOT produce an authoritative Project Index.

An incomplete index SHALL retain explicit diagnostics describing missing knowledge.

The Context Retriever SHALL be able to determine whether an index is incomplete.

---

# Inventory Compatibility

Before indexing begins, the Project Indexer SHALL validate that:

* The inventory format is supported.
* The Project Identifier is valid.
* The Project State Fingerprint is present.
* Artifact paths are normalized.
* Artifact identities are unique.
* Eligible artifacts remain associated with the same Project.
* Required scanner metadata is available.

The indexer SHALL NOT independently repair structurally invalid inventory data without reporting the inconsistency.

---

# Project State Validation

The indexer SHALL verify that artifact content corresponds to the Project Inventory when practical.

Validation MAY use:

* Artifact content hash.
* Modification timestamp.
* File size.
* Stable file identity.
* Project State Fingerprint.

When an artifact has materially changed since scanning, the indexer SHALL:

1. Avoid silently indexing content under stale metadata.
2. Produce a diagnostic.
3. Skip, retry, or fail according to configuration.
4. Mark the Project Index as incomplete when necessary.

The indexer SHALL NOT claim compatibility with a project state it did not index.

---

# Artifact Eligibility

An artifact is eligible for indexing when:

* It is included in the Project Inventory.
* Its path is valid.
* Its availability state permits reading.
* Its content classification permits indexing.
* Its size is within configured limits.
* Its language or artifact type has a supported strategy or allowed fallback.
* It is not prohibited by security policy.

Eligibility SHALL be determined before full content parsing.

---

# Default Eligibility

The MVP SHOULD consider the following eligible by default:

* Supported source files.
* Supported test files.
* Relevant configuration files.
* Relevant manifests.
* Build files.
* Text documentation files.

The following SHOULD be ineligible by default:

* Binary artifacts.
* Excluded artifacts.
* Unreadable artifacts.
* Oversized artifacts.
* Sensitive artifacts prohibited by policy.
* Generated artifacts excluded by configuration.
* Unsupported encodings without fallback.

---

# Sensitive Artifacts

Sensitive artifacts MAY be indexed locally when authorized.

Sensitive artifact content SHALL:

* Remain classified as sensitive.
* Preserve the source of classification.
* Not be exposed to remote-provider workflows without explicit permission.
* Avoid appearing in ordinary diagnostics.
* Avoid being duplicated unnecessarily.

The Project Index SHALL preserve sensitivity metadata for retrieval and provider-policy enforcement.

---

# Index Strategy Selection

Each eligible artifact SHALL be assigned one indexing strategy.

Canonical strategy categories are:

* Language-aware structural indexing.
* Structured configuration indexing.
* Documentation indexing.
* Generic text indexing.
* Metadata-only indexing.
* Skip.

Strategy selection SHALL use deterministic evidence such as:

* Artifact Kind.
* Detected language.
* File name.
* Extension.
* Content Classification.
* Registry capabilities.
* Indexer Configuration.

---

# Strategy Precedence

The recommended strategy precedence is:

1. Mandatory security restriction.
2. Explicit project configuration.
3. Language-aware structural strategy.
4. Structured configuration strategy.
5. Documentation strategy.
6. Generic text strategy.
7. Metadata-only strategy.
8. Skip.

A lower-precedence strategy SHALL NOT override an applicable security restriction.

---

# Language-Aware Structural Indexing

A language-aware strategy MAY extract:

* Modules.
* Namespaces.
* Classes.
* Interfaces.
* Functions.
* Methods.
* Properties.
* Variables.
* Constants.
* Types.
* Imports.
* Exports.
* Inheritance relationships.
* Interface implementation relationships.
* Call relationships.
* Documentation associations.

The strategy SHALL preserve source locations.

The strategy SHALL NOT execute or import project code.

---

# Structured Configuration Indexing

Structured configuration indexing MAY support formats such as:

* JSON.
* YAML.
* TOML.
* INI.
* XML.
* Environment-style key-value files.
* Dockerfiles.
* Compose files.
* Package manifests.
* Build manifests.

A structured configuration strategy MAY extract:

* Keys.
* Sections.
* Dependency declarations.
* Service declarations.
* Build stages.
* Scripts.
* Entry points.
* Environment-variable names.
* File references.

Secret values SHALL NOT be duplicated into diagnostics or summaries.

---

# Documentation Indexing

Documentation indexing MAY extract:

* Headings.
* Sections.
* Code blocks.
* Links.
* Referenced paths.
* Referenced symbols.
* Paragraph units.
* Lists.
* Metadata headers.

Documentation content SHALL retain source-location traceability when practical.

The indexer SHALL distinguish documentation text from source code.

---

# Generic Text Indexing

Generic text indexing SHALL be available for eligible text artifacts without a specialized strategy when enabled.

It MAY produce:

* Line-based units.
* Paragraph-based units.
* Size-bounded text chunks.
* Basic headings.
* Basic key-value structures.

Generic text indexing SHALL NOT fabricate symbols or semantic relationships.

---

# Metadata-Only Indexing

An artifact MAY be represented as metadata only when:

* Content cannot be safely read.
* Content is unsupported.
* Content exceeds indexing limits.
* Policy prohibits content indexing.
* The artifact is still structurally relevant.

A metadata-only record MAY preserve:

* Artifact Identifier.
* Path.
* Artifact Kind.
* Size.
* Language.
* Content Classification.
* Hash.
* Availability state.
* Diagnostic references.

---

# Indexed Artifact Record

An Indexed Artifact Record represents the indexing result for one Project Artifact.

It SHALL contain:

* Artifact Identifier.
* Indexing state.
* Index strategy.
* Artifact metadata reference.
* Source Project State Fingerprint.
* Strategy version.

It MAY contain:

* Content hash.
* Structural Unit references.
* Symbol references.
* Relationship references.
* Searchable Text Unit references.
* Diagnostics.
* Measurements.

Canonical indexing states are:

* Fully Indexed.
* Partially Indexed.
* Metadata Only.
* Skipped.
* Failed.

---

# Structural Unit

A Structural Unit represents a meaningful region of an artifact.

It SHALL contain:

* Structural Unit Identifier.
* Artifact Identifier.
* Unit kind.
* Source Location.
* Content or content reference.
* Parent reference when applicable.

It MAY contain:

* Name.
* Qualified name.
* Child references.
* Symbol references.
* Relationship references.
* Content hash.
* Search metadata.
* Sensitivity metadata.

Canonical unit kinds MAY include:

* File.
* Module.
* Namespace.
* Class.
* Interface.
* Function.
* Method.
* Section.
* Configuration Block.
* Manifest Section.
* Documentation Section.
* Text Block.

---

# Structural Unit Boundaries

Structural Units SHALL:

* Remain inside one Project Artifact.
* Preserve exact source ordering.
* Not contain invalid overlapping boundaries unless the structure is hierarchical.
* Retain parent-child relationships when nested.
* Be reproducible for unchanged source content and strategy version.

A unit MAY contain nested child units.

---

# Structural Unit Size

A strategy MAY split a large structural region into bounded units.

Splitting SHALL:

* Preserve source order.
* Preserve parent identity.
* Avoid splitting small semantic units unnecessarily.
* Retain source-location traceability.
* Avoid changing symbol ownership.

Configured size limits SHOULD be treated as boundaries rather than targets.

---

# Symbol Extraction

A Symbol SHALL be extracted only when supported by deterministic evidence.

Every Symbol SHALL contain:

* Symbol Identifier.
* Symbol name.
* Symbol kind.
* Declaring Artifact Identifier.
* Source Location.

A Symbol MAY contain:

* Qualified name.
* Signature.
* Visibility.
* Parent Symbol Identifier.
* Structural Unit Identifier.
* Documentation reference.
* Language metadata.

---

# Symbol Identity

Symbol identity SHOULD remain stable while the symbol's semantic identity and location remain unchanged.

A Symbol Identifier MAY be derived from:

* Project Identifier.
* Artifact Identifier.
* Qualified name.
* Symbol kind.
* Source-location discriminator.
* Strategy version.

A symbol identifier SHALL NOT depend on the current inference provider.

Duplicate Symbol Identifiers within one Project Index SHALL be rejected.

---

# Symbol Naming

The indexer SHALL preserve:

* Declared symbol name.
* Qualified symbol name when available.
* Language-specific case.
* Source spelling.

The indexer MAY additionally create normalized search forms.

Normalized forms SHALL NOT replace the authoritative declared name.

---

# Anonymous Symbols

A language strategy MAY index anonymous structural elements.

Anonymous symbols SHALL use:

* Stable generated identity.
* Explicit anonymous classification.
* Source Location.
* Parent context.

Generated labels SHALL NOT be presented as declared source names.

---

# Import Extraction

An Import Relationship represents a statically declared dependency from one artifact or symbol to another module, package, or artifact.

Import extraction SHALL preserve:

* Import source.
* Imported target text.
* Source Location.
* Import kind.
* Resolution state.

Canonical resolution states are:

* Resolved Internally.
* Resolved Externally.
* Unresolved.
* Ambiguous.

---

# Import Resolution

The indexer MAY resolve imports using deterministic project information such as:

* Relative path rules.
* Language module rules.
* Package manifests.
* Workspace configuration.
* Source roots.
* Alias configuration.

The indexer SHALL NOT:

* Install dependencies.
* Access package registries.
* Execute build systems.
* Import modules dynamically.

Unresolved imports SHALL remain represented when useful.

---

# Dependency Relationships

The indexer MAY create dependency relationships between:

* Artifacts.
* Modules.
* Packages.
* Services.
* Configuration sections.
* Build targets.

A dependency relationship SHALL preserve its Evidence and resolution state.

A dependency SHALL NOT be treated as internal when resolution is uncertain.

---

# Reference Extraction

Reference extraction MAY identify deterministic references to:

* Symbols.
* Files.
* Modules.
* Configuration keys.
* Routes.
* Services.
* Environment-variable names.

Reference extraction SHALL distinguish:

* Declared references.
* Resolved references.
* Unresolved textual references.
* Ambiguous references.

A generic text match SHALL NOT be represented as a confirmed semantic reference.

---

# Call Relationships

A language strategy MAY extract static call relationships.

A call relationship SHALL preserve:

* Calling symbol or unit.
* Called target text.
* Source Location.
* Resolution state.
* Evidence.

Dynamic dispatch SHALL NOT be represented as definitively resolved unless the indexing strategy can establish it deterministically.

---

# Inheritance and Implementation

The indexer MAY extract:

* Class inheritance.
* Interface implementation.
* Type extension.
* Trait or mixin inclusion.

Relationships SHALL preserve:

* Declaring symbol.
* Target name.
* Resolved target when available.
* Source Location.
* Evidence.

---

# Test Relationships

The indexer MAY create relationships between tests and production artifacts.

Evidence MAY include:

* Imports.
* Naming conventions.
* Explicit references.
* Framework conventions.
* Directory structure.

A naming heuristic SHALL be classified as heuristic evidence rather than a confirmed reference.

---

# Configuration Relationships

The indexer MAY relate configuration artifacts to:

* Source modules.
* Services.
* Build targets.
* Environment-variable names.
* Container definitions.
* Entry points.
* Scripts.

Relationships SHALL preserve deterministic Evidence.

---

# Searchable Text Unit

A Searchable Text Unit represents a bounded text region available to retrieval.

It SHALL contain:

* Search Unit Identifier.
* Artifact Identifier.
* Source Location.
* Text content or content reference.
* Search Unit kind.
* Ordering information.

It MAY contain:

* Symbol references.
* Structural Unit reference.
* Normalized terms.
* Language.
* Artifact Kind.
* Sensitivity classification.
* Content hash.
* Estimated token size.

---

# Search Unit Kinds

Canonical Search Unit kinds MAY include:

* Symbol Definition.
* Source Block.
* Configuration Block.
* Documentation Section.
* Manifest Section.
* File Summary.
* Generic Text Block.
* Comment Block.
* Metadata Record.

The Project Indexer SHALL NOT assign task relevance to Searchable Text Units.

---

# Text Normalization

The indexer MAY create normalized search representations.

Normalization MAY include:

* Unicode normalization.
* Line-ending normalization.
* Case-normalized search terms.
* Identifier tokenization.
* Path tokenization.
* Camel-case splitting.
* Snake-case splitting.
* Qualified-name tokenization.

The authoritative source content SHALL remain distinguishable from normalized search data.

Normalization SHALL NOT alter source locations.

---

# Comments and Documentation Strings

Indexer Configuration SHALL determine whether comments and documentation strings are indexed.

When indexed, they SHOULD remain associated with:

* Declaring symbol.
* Structural Unit.
* Source Location.
* Artifact Identifier.

Comments SHALL NOT automatically be treated as authoritative behavior.

---

# File Summaries

The indexer MAY produce deterministic file summaries.

A deterministic file summary MAY include:

* Artifact path.
* Artifact Kind.
* Language.
* Top-level symbols.
* Imports.
* Exports.
* Structural Unit count.
* Relationship count.

A file summary SHALL NOT use generative inference in the MVP.

The summary SHALL not contain interpretations unsupported by indexed evidence.

---

# Project-Level Summary

The indexer MAY produce a deterministic Project Summary containing:

* Languages.
* Artifact counts.
* Major directories.
* Known manifests.
* Known entry points.
* Detected services.
* Dependency-file references.
* Test structure.
* Configuration structure.

Project-level summaries SHALL be derived only from indexed evidence.

---

# Entry Point Detection

The indexer MAY identify probable project entry points using deterministic rules.

Evidence MAY include:

* Manifest declarations.
* Framework conventions.
* Executable file names.
* Main functions.
* Build configuration.
* Container commands.
* Script declarations.

Entry-point confidence SHALL reflect evidence strength.

A probable entry point SHALL NOT be represented as confirmed without sufficient evidence.

---

# Relationship Graph

The Project Index MAY expose project knowledge as a graph.

Graph nodes MAY include:

* Project Artifacts.
* Structural Units.
* Symbols.
* External modules.
* Configuration elements.

Graph edges MAY include:

* Contains.
* Defines.
* Imports.
* References.
* Calls.
* Extends.
* Implements.
* Tests.
* Configures.
* Documents.

The graph SHALL preserve node identity and relationship Evidence.

The domain SHALL NOT require a graph database.

---

# Search Index

The Project Index SHALL provide sufficient data for deterministic lexical and structural search.

The MVP MAY support:

* Exact path lookup.
* File-name lookup.
* Symbol-name lookup.
* Qualified-name lookup.
* Exact text search.
* Token search.
* Structural Unit lookup.
* Relationship traversal.
* Artifact Kind filtering.
* Language filtering.

Semantic vector search MAY be added later but SHALL NOT be required for the initial MVP.

---

# Index Query Boundary

The Project Index MAY expose a read-only query contract equivalent to:

```text
find_artifact(path_or_identifier)
find_symbols(name, filters)
find_text(query, filters)
find_relationships(source_or_target, filters)
find_structural_units(criteria)
```

Query operations SHALL NOT modify the Project Index.

Task-specific ranking belongs to the Context Retriever.

---

# Index Serialization

The Project Index SHALL remain independent from serialization format.

An adapter MAY serialize an index as:

* JSON.
* MessagePack.
* SQLite records.
* Local binary format.
* Other versioned storage.

Serialized representations SHALL include:

* Index format version.
* Project Identifier.
* Project State Fingerprint.
* Indexer version.
* Strategy versions.

An incompatible serialized index SHALL be rejected or migrated explicitly.

---

# Index Persistence

Index persistence is optional for the initial MVP.

When persistence is implemented, it SHALL support:

* Index compatibility validation.
* Safe replacement.
* Corruption detection.
* Project identity validation.
* Project State Fingerprint validation.
* Index format version validation.

A persisted index SHALL NOT be treated as current solely because it exists.

---

# Cache Semantics

A cached Project Index MAY be reused only when:

* Project Identifier matches.
* Project State Fingerprint matches.
* Effective Indexer Configuration matches.
* Required strategy versions match.
* Index format version is supported.
* Security policy remains compatible.

A mismatched cache SHALL be rebuilt or updated.

---

# Incremental Indexing

Incremental indexing MAY reuse unchanged Indexed Artifact Records.

The implementation SHALL determine artifact changes through deterministic data such as:

* Content hash.
* Artifact identity.
* File size.
* Modification timestamp.
* Inventory change set.

Incremental indexing SHALL:

* Remove records for deleted artifacts.
* Add records for new artifacts.
* Replace records for changed artifacts.
* Preserve valid records for unchanged artifacts.
* Recompute affected relationships.
* Produce output semantically equivalent to a complete index.

---

# Relationship Invalidation

When an artifact changes, the indexer SHALL invalidate:

* Symbols declared by the artifact.
* Structural Units owned by the artifact.
* Outgoing relationships from the artifact.
* Resolved incoming relationships affected by changed identities.
* Searchable Text Units owned by the artifact.

The indexer MAY selectively recompute unaffected relationships when correctness is preserved.

---

# Determinism

Given the same:

* Project Inventory.
* Artifact content.
* Project State Fingerprint.
* Indexer Configuration.
* Language Registry.
* Strategy versions.
* Indexer version.

The indexer SHOULD produce semantically equivalent Project Indexes.

The following SHALL NOT alter semantic output:

* Artifact processing order.
* Thread scheduling.
* Operating-system enumeration behavior.
* Temporary memory addresses.
* Index generation timestamp.

---

# Ordering

The Project Index SHALL define deterministic ordering for serialized and inspectable collections.

The recommended ordering is:

* Artifacts by normalized project-relative path.
* Structural Units by artifact path and Source Location.
* Symbols by artifact path, Source Location, and canonical name.
* Relationships by source identity, relationship kind, and target identity.
* Searchable Text Units by artifact path and Source Location.
* Diagnostics by artifact path, severity, and code.

Consumers SHALL NOT interpret ordering as relevance unless explicitly documented.

---

# Immutability

A completed Project Index SHALL be immutable.

An incremental update SHALL produce a new Project Index identity.

Existing index objects SHALL NOT be silently modified while being used by a Retrieval operation.

---

# Index Identity

An Index Identifier SHOULD be derived from or correlated with:

* Project Identifier.
* Project State Fingerprint.
* Index format version.
* Indexer version.
* Effective configuration fingerprint.
* Strategy-version fingerprint.

Two indexes with different semantic inputs SHALL NOT share the same identity.

---

# Configuration Fingerprint

The Project Index SHOULD preserve a fingerprint of the effective Indexer Configuration.

The fingerprint SHOULD include configuration values that affect:

* Artifact eligibility.
* Parsing.
* Structural Unit generation.
* Symbol extraction.
* Relationship extraction.
* Searchable Text Unit generation.
* Sensitive-content treatment.

Observability-only configuration MAY be excluded.

---

# Parser Requirements

Language-aware parsers SHALL:

* Operate without executing project code.
* Return deterministic structural information.
* Preserve source positions.
* Report syntax or parsing failures.
* Support bounded resource use.
* Avoid network access.
* Avoid project dependency installation.

Parsers MAY be:

* Standard-library parsers.
* External parsing libraries.
* Tree-sitter-based parsers.
* Custom deterministic parsers.

Parser selection is an implementation decision constrained by this specification.

---

# Parser Failure

When a language-aware parser fails, the indexer SHALL follow configured fallback behavior.

Permitted outcomes include:

* Retry with another compatible parser.
* Use generic text indexing.
* Use metadata-only indexing.
* Skip the artifact.
* Fail the indexing operation in strict mode.

A fallback SHALL produce a diagnostic.

The indexer SHALL NOT silently claim full structural indexing after parser failure.

---

# Malformed Source Files

A malformed source artifact MAY still be partially indexed when the parser supports error recovery.

Partial indexing SHALL:

* Be marked as partial.
* Preserve parser diagnostics.
* Avoid fabricating missing structures.
* Indicate uncertain or recovered regions.

---

# Unsupported Languages

An artifact with an unsupported language MAY be:

* Indexed as generic text.
* Indexed as metadata only.
* Skipped.

The selected behavior SHALL be controlled by configuration.

An unsupported language SHALL NOT fail the entire project by default.

---

# Unknown Languages

An artifact with an unknown language MAY still be indexed through:

* Documentation strategy.
* Structured configuration strategy.
* Generic text strategy.
* Metadata-only strategy.

Unknown language and unsupported language SHALL remain distinct conditions.

---

# Binary Artifacts

Binary artifacts SHALL NOT be structurally parsed as ordinary text.

The Project Index MAY retain binary metadata such as:

* Path.
* Artifact Kind.
* Size.
* Content hash.
* Detected format.
* Relationship references.

Binary content extraction is outside MVP scope unless explicitly supported by a later specification.

---

# Generated Artifacts

Generated artifacts SHALL preserve generated classification.

When generated artifacts are indexed, the Project Index SHALL permit the Context Retriever to filter or deprioritize them.

The indexer SHALL NOT infer that generated content is authoritative source content.

---

# Duplicate Content

The indexer MAY detect duplicate artifact content through hashes.

Duplicate detection MAY support:

* Storage optimization.
* Diagnostics.
* Retrieval diversity.
* Generated-file analysis.

Duplicate artifacts SHALL retain separate artifact identities and paths.

Content duplication SHALL NOT merge domain entities automatically.

---

# Large Artifacts

Artifacts exceeding configured indexing size limits SHALL:

* Be represented as metadata only or partially indexed.
* Produce a diagnostic.
* Avoid unbounded memory consumption.
* Preserve artifact identity.
* Remain distinguishable from unsupported artifacts.

A large artifact SHALL NOT fail the entire project unless strict mode requires it.

---

# Bounded Resource Use

The indexer SHALL support bounded use of:

* Memory.
* Parser time.
* Artifact size.
* Structural Unit size.
* Relationship count.
* Searchable Text Unit count.
* Total indexed content.

When a resource limit is reached, the indexer SHALL:

* Stop or degrade safely.
* Produce diagnostics.
* Mark affected records.
* Mark the index incomplete when material knowledge is omitted.

---

# Security Requirements

The Project Indexer SHALL:

* Treat project content as untrusted.
* Avoid executing source code.
* Avoid loading project modules.
* Avoid invoking project-defined build hooks.
* Validate all source references against Project Inventory.
* Respect Project Root containment.
* Preserve sensitive-content classification.
* Avoid logging secret values.
* Avoid network access.
* Reject malformed serialized indexes from untrusted sources.

---

# Injection Resistance

Source-code comments, documentation, strings, and configuration values MAY contain instructions directed at an AI system.

The indexer SHALL treat such content only as project data.

It SHALL NOT:

* Execute embedded instructions.
* Change indexing behavior based on natural-language commands found in project content.
* Reclassify project content as system instructions.
* Invoke external tools because project content requests it.

Instruction-separation policy SHALL be preserved for later Prompt Builder processing.

---

# Diagnostics

The indexer SHALL produce structured diagnostics.

Each diagnostic SHALL include:

* Diagnostic code.
* Severity.
* Message.
* Related Artifact Identifier when applicable.
* Related Source Location when applicable.
* Index strategy.
* Recoverability indication.

Diagnostics SHALL NOT expose full sensitive content.

---

# Canonical Diagnostic Codes

The MVP SHOULD define at least:

| Code                            | Meaning                                       |
| ------------------------------- | --------------------------------------------- |
| `INDEX_INVENTORY_INVALID`       | Project Inventory is structurally invalid     |
| `INDEX_INVENTORY_UNSUPPORTED`   | Inventory format is unsupported               |
| `INDEX_PROJECT_STATE_CHANGED`   | Artifact state differs from inventory         |
| `INDEX_ARTIFACT_UNREADABLE`     | Artifact content cannot be read               |
| `INDEX_ARTIFACT_TOO_LARGE`      | Artifact exceeds configured indexing limit    |
| `INDEX_ARTIFACT_SKIPPED`        | Artifact was intentionally skipped            |
| `INDEX_LANGUAGE_UNSUPPORTED`    | No language-aware strategy is available       |
| `INDEX_LANGUAGE_UNKNOWN`        | Artifact language is unknown                  |
| `INDEX_ENCODING_UNSUPPORTED`    | Artifact encoding is unsupported              |
| `INDEX_PARSE_FAILED`            | Language-aware parsing failed                 |
| `INDEX_PARSE_PARTIAL`           | Artifact was only partially parsed            |
| `INDEX_FALLBACK_GENERIC_TEXT`   | Generic text fallback was used                |
| `INDEX_FALLBACK_METADATA_ONLY`  | Metadata-only fallback was used               |
| `INDEX_SYMBOL_DUPLICATE`        | Duplicate symbol identity was detected        |
| `INDEX_RELATIONSHIP_UNRESOLVED` | A relationship target could not be resolved   |
| `INDEX_RELATIONSHIP_AMBIGUOUS`  | A relationship has multiple candidate targets |
| `INDEX_LIMIT_REACHED`           | An indexing resource limit was reached        |
| `INDEX_CACHE_INCOMPATIBLE`      | Persisted index is incompatible               |
| `INDEX_CACHE_CORRUPTED`         | Persisted index failed integrity validation   |
| `INDEX_INCOMPLETE`              | Project Index is incomplete                   |

Published diagnostic codes SHALL remain stable.

---

# Failure Model

The Project Indexer SHALL distinguish terminal failures from recoverable indexing conditions.

## Terminal Failures

Examples include:

* Invalid Project Inventory.
* Unsupported mandatory index format.
* Project Source Port unavailable.
* Invalid Indexer Configuration.
* Security-boundary violation.
* Corrupted mandatory cache with no rebuild path.
* Mandatory resource limit exceeded in strict mode.
* Failure to construct an internally consistent Project Index.

A terminal failure SHALL prevent production of a successful Project Index.

---

## Recoverable Conditions

Examples include:

* Unsupported artifact language.
* Parser failure for one artifact.
* Unresolved import.
* Ambiguous reference.
* Oversized artifact.
* Unsupported encoding.
* Artifact changed after scanning.
* Generic text fallback.
* Metadata-only fallback.
* Partial parser recovery.

Recoverable conditions SHALL be represented through diagnostics.

---

# Consistency Requirements

A completed Project Index SHALL satisfy:

* Every Indexed Artifact Record references an inventory artifact.
* Every Structural Unit references one indexed artifact.
* Every Symbol references a valid artifact and Source Location.
* Every resolved relationship references valid index identities.
* Every Searchable Text Unit references a valid artifact.
* Every Source Location remains inside its artifact.
* Artifact identities are unique.
* Symbol identities are unique.
* Structural Unit identities are unique.
* Relationship identities are unique.
* Search Unit identities are unique.

---

# Source Traceability

Every indexed content unit SHALL be traceable to its source.

Traceability SHALL identify at least:

* Project Identifier.
* Artifact Identifier.
* Project-relative path through artifact lookup.
* Source Location when content-specific.
* Index strategy.
* Strategy version.

Derived summaries and relationships SHALL preserve Evidence.

---

# Interaction with Project Scanner

The Project Indexer SHALL rely on the scanner for:

* Project boundary validation.
* Project-relative paths.
* Artifact identity.
* Basic classification.
* Detected language.
* Content classification.
* Availability state.
* Exclusion decisions.
* Sensitivity indicators.
* Project State Fingerprint.

The indexer SHALL NOT:

* Perform independent directory traversal.
* Override mandatory scanner exclusions.
* Assume omitted paths exist.
* Convert an excluded artifact into an indexed artifact.

---

# Interaction with Context Retriever

The Project Indexer SHALL provide the Context Retriever with read-only access to:

* Artifact records.
* Structural Units.
* Symbols.
* Relationships.
* Searchable Text Units.
* Deterministic summaries.
* Index diagnostics.
* Index completeness status.

The Project Indexer SHALL NOT:

* Rank artifacts against a Task Specification.
* Select final context.
* Apply a Context Budget.
* Generate Selection Rationales for task-specific choices.

---

# Interaction with Application Orchestrator

The Application Orchestrator SHALL:

* Supply the Project Inventory.
* Supply effective Indexer Configuration.
* Decide whether to reuse, update, or rebuild a persisted index.
* Record the indexing stage.
* Reject incompatible indexes.
* Decide whether an incomplete index is acceptable under workflow policy.

The indexer SHALL NOT control the full Execution lifecycle.

---

# Interaction with Persistence Adapters

When persistence is enabled, an Index Storage Port MAY support logical operations equivalent to:

```text
load(project_identifier)
save(project_index)
remove(index_identifier)
```

The storage adapter SHALL:

* Preserve version metadata.
* Preserve index identity.
* Detect corrupted data when practical.
* Avoid exposing partially written indexes as complete.
* Translate storage-specific failures.

Index persistence SHALL remain optional.

---

# Atomic Index Replacement

When a persisted index is updated, the replacement SHOULD be atomic.

A new index SHALL be fully validated before replacing the previous valid index.

A failed update SHALL NOT destroy a previously valid compatible index unless explicitly requested.

---

# Observability

The indexer SHOULD expose information sufficient to explain:

* Which artifacts were indexed.
* Which strategy processed each artifact.
* Which artifacts used fallback behavior.
* Which symbols were extracted.
* Which relationships were unresolved.
* Whether the index is complete.
* Which limits were reached.
* Whether a cached index was reused.
* How long indexing required.

Observability SHALL NOT require external telemetry.

---

# Privacy

The Project Indexer SHALL operate locally.

It SHALL NOT transmit project content to inference providers or external services.

Persisted index content SHALL inherit the sensitivity and confidentiality requirements of the source project.

---

# Extensibility

The indexer MAY support controlled extension through:

* Language strategies.
* Configuration parsers.
* Manifest parsers.
* Documentation parsers.
* Symbol extractors.
* Relationship resolvers.
* Search-unit generators.

Extensions SHALL:

* Declare supported artifact types.
* Declare strategy version.
* Remain deterministic.
* Avoid network access.
* Avoid project code execution.
* Preserve source traceability.
* Preserve Core domain semantics.
* Respect Project Root and sensitivity policies.

The MVP SHALL NOT require arbitrary third-party runtime plugin loading.

---

# Implementation Organization

The source capability SHOULD be organized under:

```text
src/contextforge/indexer/
```

Expected internal concepts MAY include:

```text
models
ports
services
strategies
registry
diagnostics
exceptions
```

Physical filenames and classes are implementation decisions.

The module SHALL NOT depend on:

```text
cli
provider adapters
patch adapters
```

---

# Traceability

| Requirement Area       | Project Indexer Responsibility                   |
| ---------------------- | ------------------------------------------------ |
| Project analysis       | Build deterministic structural project knowledge |
| Context efficiency     | Provide searchable units and relationships       |
| Provider independence  | Index without provider behavior                  |
| Offline operation      | Operate locally without network access           |
| Deterministic analysis | Use stable strategies and identities             |
| Explainability         | Preserve source Evidence and diagnostics         |
| Modularity             | Use language strategies and explicit ports       |
| Security               | Avoid execution and preserve sensitivity         |
| Extensibility          | Support controlled indexing strategies           |
| Performance            | Support bounded and incremental indexing         |

---

# Acceptance Criteria

## AC-INDEX-001 — Valid Inventory Indexing

Given a valid complete Project Inventory with supported artifacts, the indexer SHALL produce a Project Index.

---

## AC-INDEX-002 — Inventory Traceability

Every Indexed Artifact Record SHALL reference exactly one artifact from the source Project Inventory.

---

## AC-INDEX-003 — Scanner Exclusion Preservation

Given an artifact excluded by the Project Scanner, the Project Indexer SHALL NOT index it.

---

## AC-INDEX-004 — Stable Artifact Identity

Given unchanged project content, configuration, and strategy versions, indexed artifact identities SHALL remain semantically stable.

---

## AC-INDEX-005 — Structural Extraction

Given a valid artifact in a supported language, the indexer SHALL extract the structures supported by the registered language strategy.

---

## AC-INDEX-006 — Source Location Preservation

Every content-specific Symbol, Structural Unit, Relationship Evidence, and Searchable Text Unit SHALL preserve a valid source location when available.

---

## AC-INDEX-007 — No Project Execution

The indexer SHALL process project content without importing, executing, compiling, or evaluating project code.

---

## AC-INDEX-008 — Parser Failure Isolation

Given one malformed artifact under non-strict behavior, the indexer SHALL report the failure and continue indexing other eligible artifacts.

---

## AC-INDEX-009 — Generic Text Fallback

Given an eligible unsupported text artifact and enabled fallback, the indexer SHALL produce generic Searchable Text Units without fabricating structural semantics.

---

## AC-INDEX-010 — Binary Safety

Given a binary artifact, the indexer SHALL NOT process it as ordinary source text.

---

## AC-INDEX-011 — Relationship Evidence

Every extracted Artifact Relationship SHALL preserve the evidence and resolution state that produced it.

---

## AC-INDEX-012 — Unresolved Imports

Given an import that cannot be resolved deterministically, the indexer SHALL preserve it as unresolved rather than inventing a target.

---

## AC-INDEX-013 — Deterministic Ordering

Given equivalent indexing inputs, inspectable index collections SHALL use deterministic ordering.

---

## AC-INDEX-014 — Index Immutability

A completed Project Index SHALL be immutable.

---

## AC-INDEX-015 — Project State Mismatch

Given artifact content that materially differs from its inventory state, the indexer SHALL not silently index it as compatible.

---

## AC-INDEX-016 — Incremental Equivalence

When incremental indexing is implemented, the resulting index SHALL be semantically equivalent to a complete index for the same project state.

---

## AC-INDEX-017 — Cache Compatibility

A persisted Project Index SHALL be reused only when project identity, project state, configuration, format, and strategy versions are compatible.

---

## AC-INDEX-018 — Sensitive Metadata Preservation

Given a sensitive Project Artifact, the Project Index SHALL preserve its sensitivity classification.

---

## AC-INDEX-019 — Search Readiness

A complete Project Index SHALL support artifact, symbol, text, structural, and relationship lookup sufficient for Context Retrieval.

---

## AC-INDEX-020 — Incomplete Index Visibility

When material artifacts cannot be indexed, the resulting index SHALL be marked incomplete or complete with warnings according to impact.

---

# Test Categories

The Project Indexer SHALL be verified through:

* Unit tests for strategy selection.
* Unit tests for artifact eligibility.
* Unit tests for symbol identity.
* Unit tests for Structural Unit boundaries.
* Unit tests for import resolution.
* Unit tests for relationship resolution.
* Unit tests for search-unit generation.
* Unit tests for configuration fingerprints.
* Parser adapter tests.
* Integration tests using Project Inventory fixtures.
* Determinism tests.
* Incremental-equivalence tests.
* Cache-compatibility tests.
* Corrupted-cache tests.
* Large-artifact tests.
* Malformed-source tests.
* Unsupported-language tests.
* Sensitive-artifact tests.
* Resource-limit tests.
* Cross-platform path tests.
* Injection-resistance tests.

Tests SHALL NOT require network access.

---

# Reference Project Fixtures

The test suite SHOULD include:

* Small Python project.
* Small JavaScript or TypeScript project.
* Multi-language project.
* Project with nested modules.
* Project with source and tests.
* Project with configuration manifests.
* Project with documentation.
* Project with unresolved imports.
* Project with ambiguous imports.
* Project with malformed source.
* Project with unsupported text files.
* Project with binary files.
* Project with generated files.
* Project with sensitive configuration.
* Project with duplicate content.
* Project with oversized artifacts.
* Project changed after scanning.
* Previous index with unchanged files.
* Previous index with added, modified, renamed, and deleted files.
* Corrupted persisted index.
* Source containing prompt-injection-like instructions.

---

# Validation Criteria

This specification SHALL be considered satisfied when:

* A valid Project Inventory can be transformed into an immutable Project Index.
* Scanner boundaries and exclusions remain preserved.
* Eligible artifacts are processed through deterministic strategies.
* Structural knowledge remains traceable to source artifacts.
* Unsupported or malformed artifacts degrade safely.
* Project content is never executed.
* Project-state mismatches are visible.
* Symbols and relationships retain stable identities and Evidence.
* Searchable Text Units support retrieval without task-specific ranking.
* Index reuse requires explicit compatibility.
* Incremental indexing, when present, matches full-index semantics.
* The Context Retriever can query project knowledge without rescanning or reparsing the project.

---

# Completion Statement

The Project Indexer is complete when ContextForge can transform an immutable Project Inventory into deterministic, source-traceable, provider-independent project knowledge that supports artifact lookup, structural lookup, symbol lookup, relationship traversal, and text retrieval without executing project code or making task-specific relevance decisions.
