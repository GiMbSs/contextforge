# Context Retriever Specification

Document ID: CF-007
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
* CF-006 — Project Indexer Specification

Related ADRs:

* ADR-0001 — Context-First Architecture
* ADR-0002 — Hexagonal Architecture
* ADR-0003 — Dependency Rule
* ADR-0004 — Feature-Based Module Organization

---

# Abstract

This document defines the Context Retriever capability of ContextForge.

The Context Retriever determines which project artifacts, structural units, symbols, relationships, and text regions are relevant to a Task Specification.

It is the primary decision capability of ContextForge.

Its central responsibility is to answer:

> What is the smallest relevant set of project information required to perform this task?

The Context Retriever SHALL produce a deterministic and explainable Retrieval Result.

It SHALL NOT:

* Discover project files.
* Build the Project Index.
* Format provider prompts.
* Invoke inference providers.
* Generate source code.
* Apply patches.
* Modify project artifacts.

---

# Purpose

The Context Retriever transforms a Task Specification and Project Index into a task-specific relevance decision.

Its primary responsibilities are:

* Interpret explicit task references.
* Generate retrieval candidates.
* Evaluate candidate relevance.
* Traverse relevant project relationships.
* Select context within a Context Budget.
* Preserve selection rationale.
* Report ambiguity and coverage limitations.
* Produce an immutable Retrieval Result.

---

# Architectural Role

The Context Retriever is the architectural center of ContextForge.

The Project Scanner answers:

> What exists?

The Project Indexer answers:

> How is the project organized?

The Context Retriever answers:

> What is relevant to this task?

The Context Builder answers:

> How is the selected information packaged?

The Context Retriever SHALL own task-specific context selection decisions.

No other capability SHALL independently introduce project-derived content into a Context Bundle.

---

# Scope

The Context Retriever SHALL support:

* Task-aware artifact selection.
* Explicit path and symbol resolution.
* Lexical retrieval.
* Structural retrieval.
* Relationship traversal.
* Relevance scoring.
* Candidate ranking.
* Context-budget enforcement.
* Duplicate suppression.
* Context diversity.
* Selection rationale.
* Coverage diagnostics.
* Deterministic retrieval.

The initial MVP SHALL support retrieval without requiring embeddings or generative inference.

---

# Out of Scope

The Context Retriever SHALL NOT:

* Perform project traversal.
* Parse source files directly.
* Extract symbols.
* Build dependency graphs.
* Modify the Project Index.
* Generate prompts.
* Invoke an inference provider.
* Generate patches.
* Apply project changes.
* Execute project code.
* Install dependencies.
* Perform internet searches.
* Require a vector database.
* Require an LLM for task classification.
* Guarantee complete semantic understanding of arbitrary code.

---

# Capability Boundary

The Context Retriever consumes:

* Task Specification.
* Project Index.
* Retrieval Configuration.
* Context Budget.
* Optional user-provided artifact references.
* Optional retrieval history from the same Execution.

The Context Retriever produces:

* Retrieval Result.
* Selected Context Items.
* Selection Rationales.
* Ranked Retrieval Candidates.
* Retrieval Diagnostics.
* Retrieval Measurements.

---

# Primary Contract

The Context Retriever SHALL expose a logical operation equivalent to:

```text
retrieve(task_specification, project_index, configuration) -> Retrieval Result
```

The operation SHALL either:

1. Produce a completed Retrieval Result; or
2. Return a defined retrieval failure.

A Retrieval Result MAY contain warnings or incomplete coverage while remaining valid.

---

# Inputs

## Task Specification

The Task Specification SHALL provide:

* Task Identifier.
* Original Instruction.
* Operation Type when available.
* Explicit artifact references.
* Explicit symbol references.
* Task Constraints.
* Expected outcome when available.
* Context Budget.
* Provider constraints when relevant.

The Original Instruction SHALL remain available to retrieval strategies.

The retriever SHALL NOT silently alter user intent.

---

## Project Index

The Project Index SHALL provide read-only access to:

* Indexed Artifact Records.
* Structural Units.
* Symbols.
* Artifact Relationships.
* Searchable Text Units.
* Deterministic summaries.
* Index diagnostics.
* Index status.
* Project State Fingerprint.

The retriever SHALL reject an incompatible or structurally invalid Project Index.

---

## Retrieval Configuration

Retrieval Configuration MAY define:

* Enabled retrieval strategies.
* Strategy precedence.
* Strategy weights.
* Maximum graph traversal depth.
* Maximum candidate count.
* Maximum selected artifact count.
* Maximum selected excerpt count.
* Minimum relevance threshold.
* Duplicate threshold.
* Generated-artifact policy.
* Test-artifact policy.
* Documentation policy.
* Sensitive-artifact policy.
* Ambiguity behavior.
* Coverage behavior.
* Context Budget.
* Determinism controls.

Configuration SHALL NOT permit selection of content prohibited by security policy.

---

# Outputs

## Retrieval Result

A successful retrieval operation SHALL produce one immutable Retrieval Result containing:

* Retrieval Identifier.
* Task Identifier.
* Project Index Identifier.
* Project State Fingerprint.
* Retrieval strategy versions.
* Ranked candidates.
* Selected Context Items.
* Selection Rationales.
* Applied Context Budget.
* Retrieval Diagnostics.
* Retrieval Measurements.
* Retrieval status.
* Creation timestamp.

The result SHALL distinguish:

* Selected candidates.
* Excluded candidates.
* Deferred candidates.
* Unresolved explicit references.
* Budget-excluded candidates.
* Security-excluded candidates.

---

## Retrieval Measurements

Retrieval Measurements SHOULD include:

* Number of candidates generated.
* Number of candidates evaluated.
* Number of artifacts selected.
* Number of excerpts selected.
* Number of symbols selected.
* Number of relationships traversed.
* Number of candidates excluded by budget.
* Number of duplicates suppressed.
* Estimated selected token count.
* Retrieval duration.
* Strategy contribution counts.

Measurements SHALL NOT determine relevance by themselves.

---

# Retrieval Status

A Retrieval Result SHALL have one status:

* Complete.
* Complete with warnings.
* Incomplete.
* Failed.

A complete result indicates that the retriever found sufficient context according to available evidence and configured policy.

An incomplete result indicates that material context may be missing.

A failed retrieval SHALL NOT produce an authoritative selection.

---

# Retrieval Principles

## RP-001 — Minimum Sufficiency

The retriever SHALL prefer the smallest context set that remains sufficient for the task.

---

## RP-002 — Explicit References First

Artifacts and symbols explicitly referenced by the user SHALL receive priority, subject to security and validity constraints.

---

## RP-003 — Evidence-Based Selection

Every selected Context Item SHALL have one or more explicit reasons for inclusion.

---

## RP-004 — Deterministic Before Semantic

Deterministic structural and lexical signals SHALL be used before optional probabilistic or semantic mechanisms.

---

## RP-005 — Relationship Awareness

Selection SHALL consider relevant relationships between artifacts and symbols.

---

## RP-006 — Budget Compliance

The final selection SHALL respect the active Context Budget.

---

## RP-007 — No Hidden Expansion

The retriever SHALL NOT silently include unrelated project content.

---

## RP-008 — Explainable Exclusion

Material candidates excluded despite apparent relevance SHOULD preserve an exclusion reason.

---

## RP-009 — Source Authority

Source code, configuration, tests, and documentation SHALL retain distinct evidentiary roles.

---

## RP-010 — Security Precedence

Security restrictions SHALL override relevance.

---

# Retrieval Process

The canonical retrieval process SHALL be:

1. Validate inputs.
2. Normalize task search terms.
3. Resolve explicit artifact references.
4. Resolve explicit symbol references.
5. Generate lexical candidates.
6. Generate structural candidates.
7. Expand candidates through relationships.
8. Apply policy filters.
9. Score candidates.
10. Suppress duplicates.
11. Enforce diversity.
12. Select candidates under the Context Budget.
13. Evaluate coverage.
14. Produce Selection Rationales.
15. Finalize the Retrieval Result.

---

# Input Validation

Before retrieval begins, the retriever SHALL validate:

* Task Identifier.
* Original Instruction presence.
* Project Index compatibility.
* Project Identifier consistency.
* Context Budget validity.
* Retrieval Configuration validity.
* Unique index identities.
* Valid Source Locations.
* Index status.

A failed Project Index SHALL NOT be used.

An incomplete Project Index MAY be used only when workflow policy permits it.

---

# Task Term Extraction

The retriever SHALL derive searchable task terms from the Task Specification.

Task terms MAY include:

* Explicit file paths.
* File names.
* Directory names.
* Symbol names.
* Qualified names.
* Error messages.
* Configuration keys.
* Route names.
* Service names.
* Dependency names.
* Framework names.
* Natural-language operation terms.

Term extraction SHALL preserve the Original Instruction.

---

# Term Normalization

Search terms MAY be normalized through:

* Unicode normalization.
* Case normalization for comparison.
* Path normalization.
* Identifier splitting.
* Camel-case splitting.
* Snake-case splitting.
* Kebab-case splitting.
* Qualified-name splitting.
* Punctuation normalization.

The original term SHALL remain available for exact matching.

Normalization SHALL NOT introduce new task requirements.

---

# Stop Terms

The retriever MAY ignore low-information natural-language terms during lexical matching.

Examples MAY include:

* Common articles.
* Generic verbs.
* Common task scaffolding words.
* Non-specific programming terms.

Explicit file names, symbols, errors, paths, and configuration keys SHALL NOT be removed as stop terms.

---

# Explicit Artifact References

The retriever SHALL attempt to resolve every explicit artifact reference.

References MAY include:

* Exact project-relative paths.
* Partial paths.
* File names.
* Directory names.
* User-mentioned configuration files.
* User-mentioned test files.

Resolution states SHALL include:

* Exact.
* Unique Partial.
* Ambiguous.
* Not Found.
* Prohibited.

Exact valid references SHALL receive the highest initial relevance priority.

---

# Explicit Symbol References

The retriever SHALL attempt to resolve explicit symbol references against the Project Index.

References MAY include:

* Simple symbol name.
* Qualified symbol name.
* Class and method combination.
* Module and symbol combination.
* Signature fragment.
* Error stack reference.

Resolution states SHALL include:

* Exact.
* Unique Normalized.
* Ambiguous.
* Not Found.
* Prohibited.

Ambiguous references SHALL preserve all material candidates until disambiguation or budget selection.

---

# Error and Diagnostic References

Task instructions MAY include:

* Exception names.
* Error messages.
* Stack traces.
* File and line references.
* Compiler diagnostics.
* Test failures.

The retriever SHOULD extract:

* Referenced artifacts.
* Referenced source locations.
* Referenced symbols.
* Error-specific terms.

Exact stack-trace file and line references SHALL receive high priority when valid.

---

# Candidate Model

A Retrieval Candidate represents one possible context inclusion.

A candidate SHALL contain:

* Candidate Identifier.
* Candidate type.
* Source reference.
* Candidate content reference.
* Evidence.
* Eligibility state.
* Estimated size.

It MAY contain:

* Relevance Score.
* Rank.
* Related candidates.
* Strategy contributions.
* Exclusion reason.
* Selection Rationale.
* Sensitivity classification.

---

# Candidate Types

Canonical candidate types MAY include:

* Full Artifact.
* Structural Unit.
* Symbol Definition.
* Source Excerpt.
* Configuration Block.
* Documentation Section.
* Manifest Section.
* Test Artifact.
* Related Declaration.
* Dependency Record.
* Relationship Summary.
* Project Summary.
* User-Provided Content.

---

# Candidate Generation Strategies

The MVP SHALL support deterministic candidate generation through:

* Explicit Reference Strategy.
* Path Match Strategy.
* Symbol Match Strategy.
* Lexical Text Strategy.
* Structural Relationship Strategy.
* Dependency Strategy.
* Test Relationship Strategy.
* Configuration Relationship Strategy.
* Locality Strategy.

Optional future strategies MAY include:

* Semantic embedding retrieval.
* Historical retrieval.
* Learned ranking.
* Provider-assisted retrieval.

Optional strategies SHALL NOT replace deterministic evidence.

---

# Explicit Reference Strategy

The Explicit Reference Strategy SHALL generate candidates from user-provided paths, symbols, and source locations.

Exact valid references SHALL receive priority over inferred references.

The strategy SHALL preserve:

* Original reference.
* Resolution method.
* Resolution state.
* Resolved candidate.
* Ambiguity information.

---

# Path Match Strategy

The Path Match Strategy MAY evaluate:

* Exact project-relative path.
* File name.
* Directory name.
* Path segment.
* Extension.
* Normalized path tokens.

Path matches SHALL preserve match specificity.

An exact path match SHALL rank above a generic directory-token match.

---

# Symbol Match Strategy

The Symbol Match Strategy MAY evaluate:

* Exact symbol name.
* Qualified name.
* Normalized identifier tokens.
* Signature text.
* Parent symbol.
* Declaring artifact.
* Symbol kind.

Exact qualified-name matches SHOULD rank highest.

Common short symbol names SHALL require additional evidence to avoid broad retrieval.

---

# Lexical Text Strategy

The Lexical Text Strategy MAY search:

* Searchable Text Units.
* Symbol signatures.
* Documentation headings.
* Configuration keys.
* Manifest entries.
* Deterministic summaries.

It MAY use:

* Exact phrase matching.
* Token matching.
* Term frequency.
* Field weighting.
* Identifier matching.
* Error-message matching.

The strategy SHALL preserve matched terms as Evidence.

---

# Structural Relationship Strategy

The Structural Relationship Strategy MAY expand candidates using relationships such as:

* Contains.
* Defines.
* Imports.
* References.
* Calls.
* Extends.
* Implements.
* Configures.
* Tests.
* Documents.

Expansion SHALL be bounded by:

* Relationship type.
* Traversal depth.
* Candidate count.
* Context Budget.
* Relevance decay.

---

# Dependency Strategy

The Dependency Strategy MAY select:

* Imported internal modules.
* Importing artifacts.
* Package manifests.
* Dependency configuration.
* Referenced service definitions.
* Build declarations.

External dependency source code SHALL NOT be selected unless it is part of the authorized Project Index.

---

# Test Relationship Strategy

For modification, fix, and refactor tasks, the retriever SHOULD consider related tests.

Test candidates MAY be discovered through:

* Explicit task reference.
* Imports.
* Test relationships.
* Naming conventions.
* Shared symbols.
* Directory conventions.
* Framework metadata.

Tests SHALL not automatically displace primary implementation artifacts.

---

# Configuration Relationship Strategy

The retriever SHOULD consider configuration artifacts when the task involves:

* Application startup.
* Dependency injection.
* Build behavior.
* Deployment.
* Routing.
* Environment variables.
* Containers.
* Services.
* Package configuration.
* Framework settings.

Configuration candidates SHALL require evidence connecting them to the task.

---

# Locality Strategy

The Locality Strategy MAY consider content near:

* Explicit source locations.
* Matched symbols.
* Error lines.
* Selected Structural Units.

Locality expansion MAY include:

* Parent declaration.
* Adjacent declarations.
* Surrounding lines.
* Containing class.
* Containing module.
* Closely related configuration block.

Locality expansion SHALL remain bounded.

---

# Candidate Eligibility

A candidate is eligible only when:

* Its source belongs to the Project Index.
* Its source path remains inside the Project Root.
* Its content is available.
* Its sensitivity policy permits selection.
* Its artifact type is allowed.
* Its estimated size is valid.
* It is not prohibited by a Task Constraint.
* It has sufficient Evidence under active policy.

---

# Policy Filtering

Policy filtering SHALL occur before final selection.

Filters MAY include:

* Security restrictions.
* Sensitive-content restrictions.
* Generated-artifact restrictions.
* Binary-content restrictions.
* Artifact-kind restrictions.
* Task Constraint restrictions.
* Provider restrictions.
* Maximum artifact-size restrictions.
* Index completeness restrictions.

A prohibited candidate SHALL NOT be selected regardless of relevance score.

---

# Sensitive Content Policy

Sensitive candidates SHALL preserve their classification.

Selection policy SHALL distinguish:

* Local-provider eligibility.
* Remote-provider eligibility.
* User-authorized eligibility.
* Prohibited eligibility.

A candidate prohibited for the configured provider SHALL be excluded before Context Bundle construction.

The exclusion SHALL produce a rationale or diagnostic when material.

---

# Generated Artifact Policy

Generated artifacts MAY be:

* Excluded.
* Deprioritized.
* Selected when explicitly referenced.
* Selected when no authoritative source alternative exists.

Generated content SHOULD rank below authoritative source content unless the task specifically concerns generated output.

---

# Documentation Policy

Documentation MAY be selected when:

* Explicitly referenced.
* It defines required behavior.
* It contains setup or architectural context.
* It explains an interface involved in the task.
* It provides constraints not present in code.

Documentation SHALL not automatically override source code when implementation behavior differs.

The discrepancy MAY be reported as a diagnostic.

---

# Test Artifact Policy

Test artifacts MAY be prioritized for:

* Fix tasks.
* Regression tasks.
* Test failures.
* Behavior-preservation tasks.
* Refactoring tasks.
* Explicit test requests.

For documentation-only tasks, tests MAY be deprioritized unless directly relevant.

---

# Relevance Evaluation

Candidate relevance SHALL be based on explicit Evidence.

Relevance factors MAY include:

* Exact user reference.
* Exact path match.
* Exact symbol match.
* Error-location match.
* Lexical match.
* Structural relationship.
* Dependency relationship.
* Test relationship.
* Configuration relationship.
* Source locality.
* Artifact authority.
* Task operation type.
* Candidate size.
* Relationship distance.

---

# Relevance Score

A Relevance Score MAY be numerical, ordinal, or composite.

The score SHALL:

* Be comparable within one retrieval execution.
* Preserve contributing strategies.
* Avoid claiming universal probability.
* Remain reproducible for unchanged inputs.
* Not override mandatory policy exclusions.

A score MAY contain:

* Base relevance.
* Explicit-reference bonus.
* Relationship bonus.
* Authority bonus.
* Ambiguity penalty.
* Distance penalty.
* Size penalty.
* Generated-content penalty.

---

# Score Normalization

When multiple strategies produce different scoring ranges, the retriever SHALL normalize or otherwise make strategy contributions comparable.

Normalization SHALL be deterministic.

The final Selection Rationale SHOULD expose the primary contributing factors rather than only the final score.

---

# Strategy Combination

Multiple strategy contributions MAY be combined for one candidate.

A candidate supported by independent evidence SHOULD rank above a candidate supported by one weak signal.

The retriever SHALL avoid uncontrolled score inflation from duplicate equivalent signals.

Equivalent evidence SHALL be deduplicated before score combination.

---

# Relationship Distance

Relationship-expanded candidates SHOULD receive decreasing relevance as traversal distance increases.

The decay policy SHALL be deterministic.

Explicit references SHALL not be penalized merely because graph distance is high.

Maximum traversal depth SHALL be configurable and bounded.

---

# Artifact Authority

The retriever MAY apply authority ordering.

A typical ordering MAY be:

1. Explicitly referenced artifact.
2. Primary implementation source.
3. Directly related configuration.
4. Directly related test.
5. Interface or declaration.
6. Documentation.
7. Generated artifact.
8. Heuristic-only candidate.

Authority ordering SHALL remain task-dependent.

For a documentation task, documentation MAY become primary.

---

# Task Operation Influence

Operation Type MAY influence retrieval policy.

Examples:

| Operation Type | Typical Retrieval Emphasis                                    |
| -------------- | ------------------------------------------------------------- |
| Analyze        | Primary artifact, dependencies, documentation                 |
| Explain        | Target symbol, callers, dependencies, nearby documentation    |
| Modify         | Target implementation, declarations, tests, configuration     |
| Fix            | Error location, implementation, callers, tests                |
| Refactor       | Target implementation, interfaces, callers, tests             |
| Add            | Neighboring patterns, interfaces, configuration, tests        |
| Remove         | Target definition, references, dependents, tests              |
| Test           | Target behavior, existing tests, fixtures, test configuration |
| Document       | Target API, implementation, existing documentation            |

This table is guidance, not a substitute for Evidence.

---

# Duplicate Suppression

The retriever SHALL suppress redundant candidates.

Redundancy MAY arise from:

* Same Structural Unit discovered by multiple strategies.
* Overlapping excerpts.
* Symbol definition duplicated by a full artifact.
* Identical generated and source content.
* Repeated relationship paths.
* Duplicate text units.

Suppression SHALL preserve the combined Evidence.

---

# Overlap Handling

When two candidates overlap materially, the retriever SHOULD:

1. Prefer the more semantically complete unit.
2. Prefer the smaller sufficient unit.
3. Merge adjacent compatible excerpts when beneficial.
4. Avoid repeated content.
5. Preserve all relevant rationales.

A full artifact SHALL not automatically replace a smaller relevant excerpt when the excerpt is sufficient.

---

# Context Diversity

The selected context SHOULD include complementary information rather than many near-identical candidates.

Diversity MAY consider:

* Artifact path.
* Candidate type.
* Relationship role.
* Source versus test.
* Implementation versus configuration.
* Definition versus usage.
* Primary versus supporting context.

Diversity SHALL NOT force inclusion of irrelevant content.

---

# Context Budget

The retriever SHALL enforce the active Context Budget.

The budget MAY include:

* Maximum estimated tokens.
* Maximum characters.
* Maximum bytes.
* Maximum artifacts.
* Maximum excerpts.
* Maximum individual item size.

The strictest applicable limit SHALL prevail.

---

# Budget Estimation

Each candidate SHALL have an estimated context size before final selection.

Estimation MAY use:

* Character count.
* Byte count.
* Line count.
* Provider-neutral token approximation.
* Provider-specific token estimator when isolated behind a capability contract.

The estimation strategy SHALL be recorded when practical.

---

# Budget Allocation

The retriever MAY reserve budget categories for:

* Explicit references.
* Primary implementation.
* Related declarations.
* Tests.
* Configuration.
* Supporting documentation.
* Relationship summaries.

Reserved categories SHALL not require full allocation.

Unused reserved capacity MAY be reassigned to other relevant candidates.

---

# Budget Selection

Final budget selection SHOULD follow a constrained ranking process.

The process SHALL:

* Include mandatory eligible references first.
* Preserve task-critical context.
* Exclude redundant content.
* Prefer smaller sufficient units.
* Respect item and total limits.
* Record candidates omitted due to budget.

The retriever SHALL NOT exceed a hard Context Budget.

---

# Mandatory Candidates

A candidate MAY be classified as mandatory when it is:

* An exact explicit user reference.
* The exact error location.
* Required by a Task Constraint.
* Necessary to interpret another selected candidate.
* Required by security or validation policy.

Mandatory status SHALL not override security prohibitions.

When mandatory eligible candidates exceed the Context Budget, the Retrieval Result SHALL be incomplete or failed according to policy.

---

# Context Compression

The retriever MAY reduce candidate size through deterministic selection of:

* Relevant Structural Units.
* Relevant excerpts.
* Symbol signatures.
* Relationship summaries.
* File summaries.

The retriever SHALL NOT perform lossy generative summarization in the MVP.

Compression SHALL preserve source traceability.

---

# Full Artifact Selection

A full artifact MAY be selected when:

* It is small.
* Most of its content is relevant.
* Structural extraction is unavailable.
* The task explicitly requests full-file analysis.
* Fragmentation would remove necessary context.
* The artifact is a concise configuration or manifest.

Large artifacts SHOULD be represented through selected units or excerpts.

---

# Excerpt Selection

A source excerpt SHALL:

* Reference one Artifact Identifier.
* Preserve Source Location.
* Include sufficient surrounding context.
* Avoid arbitrary truncation of small semantic units.
* Remain within configured size limits.

An excerpt MAY include:

* Declaration header.
* Complete small function.
* Complete configuration section.
* Relevant neighboring lines.
* Parent structural context.

---

# Dependency Closure

The retriever MAY include a bounded dependency closure for selected candidates.

The closure MAY include:

* Required declarations.
* Imported internal modules.
* Base classes.
* Implemented interfaces.
* Direct callers.
* Direct callees.
* Related configuration.
* Tests.

Dependency closure SHALL stop when:

* Relevance falls below threshold.
* Maximum depth is reached.
* Budget is exhausted.
* A relationship is unresolved.
* A policy restriction applies.

---

# Bidirectional Traversal

Relationship traversal MAY occur:

* Forward from a selected artifact to dependencies.
* Backward from a selected symbol to references or callers.

Backward traversal SHOULD be more restricted because it may generate large candidate sets.

The retriever SHALL bound high-fan-out relationships.

---

# High-Fan-Out Relationships

Symbols or artifacts with many relationships MAY create excessive candidates.

The retriever SHALL support controls such as:

* Maximum related candidates.
* Relationship-type filtering.
* Relevance threshold.
* Locality restriction.
* Sampling prohibition for mandatory completeness tasks.
* Summary representation.

The retriever SHALL report when relevant candidates are omitted because of fan-out limits.

---

# Ambiguity Handling

Ambiguity MAY arise from:

* Multiple files with the same name.
* Multiple symbols with the same name.
* Unresolved imports.
* Conflicting documentation.
* Multiple plausible task targets.
* Incomplete Project Index.

The retriever SHALL preserve ambiguity explicitly.

It SHALL NOT silently choose an arbitrary candidate.

---

# Ambiguous Explicit References

When an explicit reference resolves to multiple material candidates, the retriever MAY:

* Select all candidates when budget permits.
* Use additional task evidence to rank them.
* Mark the result as complete with warnings.
* Mark the result as incomplete.
* Request disambiguation through the Application Orchestrator when workflow policy supports it.

The Context Retriever itself SHALL NOT interact directly with the user.

---

# Coverage Evaluation

After selection, the retriever SHALL evaluate whether the selected context adequately covers the task.

Coverage MAY include:

* Target coverage.
* Dependency coverage.
* Interface coverage.
* Test coverage.
* Configuration coverage.
* Constraint coverage.
* Error-location coverage.

Coverage evaluation SHALL remain explainable.

---

# Coverage State

Canonical coverage states are:

* Sufficient.
* Sufficient with warnings.
* Potentially insufficient.
* Insufficient.

A Retrieval Result with insufficient coverage SHALL be incomplete or failed according to workflow policy.

---

# Coverage Warnings

Coverage warnings MAY include:

* Explicit artifact not found.
* Explicit symbol unresolved.
* Related tests not found.
* Dependency unresolved.
* Index incomplete.
* Budget excluded relevant content.
* Sensitive content prohibited.
* High-fan-out traversal limited.
* Unsupported language.
* Conflicting project evidence.

---

# Selection Rationale

Every selected Context Item SHALL contain a Selection Rationale.

A Selection Rationale SHALL identify:

* Selection decision.
* Primary reason.
* Supporting Evidence.
* Candidate type.
* Source reference.

It MAY include:

* Relevance Score.
* Rank.
* Strategy contributions.
* Relationship path.
* Explicit task term.
* Budget decision.
* Authority classification.

---

# Canonical Selection Reasons

The MVP SHOULD define stable reason codes including:

| Code                         | Meaning                                                   |
| ---------------------------- | --------------------------------------------------------- |
| `EXPLICIT_PATH_REFERENCE`    | User explicitly referenced the artifact path              |
| `EXPLICIT_SYMBOL_REFERENCE`  | User explicitly referenced the symbol                     |
| `ERROR_LOCATION_REFERENCE`   | Candidate matches an error or stack location              |
| `EXACT_PATH_MATCH`           | Candidate path exactly matches a task term                |
| `PARTIAL_PATH_MATCH`         | Candidate path partially matches a task term              |
| `EXACT_SYMBOL_MATCH`         | Candidate symbol exactly matches a task term              |
| `LEXICAL_CONTENT_MATCH`      | Candidate content matches task terms                      |
| `DECLARATION_RELATIONSHIP`   | Candidate declares a selected symbol                      |
| `DEPENDENCY_RELATIONSHIP`    | Candidate is a direct dependency                          |
| `REFERENCE_RELATIONSHIP`     | Candidate references or is referenced by a selected item  |
| `CALL_RELATIONSHIP`          | Candidate is connected through a call relationship        |
| `INHERITANCE_RELATIONSHIP`   | Candidate is related through inheritance                  |
| `TEST_RELATIONSHIP`          | Candidate is a related test                               |
| `CONFIGURATION_RELATIONSHIP` | Candidate configures selected behavior                    |
| `DOCUMENTATION_RELATIONSHIP` | Candidate documents selected behavior                     |
| `SOURCE_LOCALITY`            | Candidate is structurally adjacent to a relevant location |
| `REQUIRED_CONTEXT`           | Candidate is required to understand another selected item |
| `USER_PROVIDED_CONTEXT`      | Context was supplied directly by the user                 |

Published reason codes SHALL remain stable.

---

# Exclusion Reasons

Material excluded candidates SHOULD preserve exclusion reasons.

Canonical exclusion reasons MAY include:

* Below relevance threshold.
* Duplicate content.
* Redundant overlap.
* Context Budget exceeded.
* Security prohibited.
* Sensitive content prohibited.
* Generated artifact deprioritized.
* Task Constraint prohibited.
* Unsupported content.
* Unavailable content.
* Excessive relationship distance.
* High-fan-out limit.
* Lower-authority duplicate.
* Deferred due to ambiguity.

---

# Retrieval Diagnostics

The retriever SHALL produce structured diagnostics.

Each diagnostic SHALL include:

* Diagnostic code.
* Severity.
* Message.
* Related candidate or task reference when applicable.
* Producing capability.
* Recoverability indication.

Diagnostics SHALL NOT expose sensitive content unnecessarily.

---

# Canonical Diagnostic Codes

The MVP SHOULD define at least:

| Code                                | Meaning                                       |
| ----------------------------------- | --------------------------------------------- |
| `RETRIEVAL_TASK_INVALID`            | Task Specification is invalid                 |
| `RETRIEVAL_INDEX_INVALID`           | Project Index is invalid                      |
| `RETRIEVAL_INDEX_INCOMPLETE`        | Project Index is incomplete                   |
| `RETRIEVAL_REFERENCE_NOT_FOUND`     | Explicit reference could not be resolved      |
| `RETRIEVAL_REFERENCE_AMBIGUOUS`     | Explicit reference resolves ambiguously       |
| `RETRIEVAL_REFERENCE_PROHIBITED`    | Explicit reference is prohibited by policy    |
| `RETRIEVAL_NO_CANDIDATES`           | No eligible candidates were generated         |
| `RETRIEVAL_NO_RELEVANT_CONTEXT`     | No candidate met relevance requirements       |
| `RETRIEVAL_BUDGET_EXCEEDED`         | Required candidates exceed the Context Budget |
| `RETRIEVAL_CANDIDATE_OMITTED`       | Relevant candidate was omitted by budget      |
| `RETRIEVAL_RELATIONSHIP_LIMIT`      | Relationship traversal limit was reached      |
| `RETRIEVAL_HIGH_FAN_OUT`            | Relationship expansion was limited by fan-out |
| `RETRIEVAL_SENSITIVE_EXCLUDED`      | Sensitive content was excluded                |
| `RETRIEVAL_GENERATED_DEPRIORITIZED` | Generated content was deprioritized           |
| `RETRIEVAL_COVERAGE_WARNING`        | Context coverage may be incomplete            |
| `RETRIEVAL_INSUFFICIENT_CONTEXT`    | Context is insufficient for the task          |
| `RETRIEVAL_LIMIT_REACHED`           | A retrieval resource limit was reached        |
| `RETRIEVAL_INCOMPLETE`              | Retrieval Result is incomplete                |

Published diagnostic codes SHALL remain stable.

---

# Failure Model

The Context Retriever SHALL distinguish terminal failures from recoverable retrieval conditions.

## Terminal Failures

Examples include:

* Invalid Task Specification.
* Invalid Project Index.
* Incompatible Project and Task references.
* Invalid Context Budget.
* Invalid Retrieval Configuration.
* Internal candidate identity conflict.
* Security-policy violation in required processing.
* No relevant context when workflow policy requires context.
* Mandatory candidates cannot fit within the Context Budget.

A terminal failure SHALL prevent creation of a successful Retrieval Result.

---

## Recoverable Conditions

Examples include:

* One explicit reference not found.
* Ambiguous symbol reference.
* Incomplete Project Index.
* Related tests not found.
* Unresolved dependency.
* Relevant candidate omitted by budget.
* Sensitive candidate prohibited.
* High-fan-out relationship limited.
* Unsupported artifact content.
* Coverage warning.

Recoverable conditions SHALL be represented through diagnostics and result status.

---

# Determinism

Given the same:

* Task Specification.
* Project Index.
* Retrieval Configuration.
* Context Budget.
* Strategy versions.
* Security policy.

The retriever SHOULD produce semantically equivalent Retrieval Results.

The following SHALL NOT alter semantic output:

* Candidate generation order.
* Thread scheduling.
* Hash-map iteration order.
* Temporary object identity.
* Execution timestamp.

Ties SHALL be resolved through deterministic tie-breaking.

---

# Tie-Breaking

When candidates have equivalent relevance, the recommended tie-breaking order is:

1. Explicit reference status.
2. Evidence strength.
3. Artifact authority.
4. Shorter relationship distance.
5. Smaller sufficient candidate size.
6. Normalized project-relative path.
7. Source Location.
8. Candidate Identifier.

Tie-breaking SHALL NOT rely on nondeterministic runtime ordering.

---

# Immutability

A finalized Retrieval Result SHALL be immutable.

Ranked candidates, selected items, rationales, diagnostics, and measurements SHALL not change after finalization.

A retrieval retry SHALL produce a new Retrieval Identifier.

---

# Retrieval Identity

A Retrieval Identifier SHOULD correlate with:

* Task Identifier.
* Project Index Identifier.
* Retrieval Configuration fingerprint.
* Context Budget.
* Strategy versions.

Different semantic retrieval inputs SHALL NOT produce the same identity unless identity policy explicitly permits content-addressed equivalence.

---

# Configuration Fingerprint

The Retrieval Result SHOULD preserve a fingerprint of configuration values affecting:

* Candidate generation.
* Strategy weighting.
* Filtering.
* Scoring.
* Relationship traversal.
* Duplicate suppression.
* Diversity.
* Budget selection.
* Coverage evaluation.

Observability-only settings MAY be excluded.

---

# Query Interface Usage

The Context Retriever SHALL use Project Index query contracts.

It MAY perform operations equivalent to:

```text
find_artifact(reference)
find_symbols(reference, filters)
find_text(terms, filters)
find_structural_units(criteria)
find_relationships(source_or_target, filters)
```

The retriever SHALL NOT modify the Project Index through these operations.

---

# No Direct File Traversal

The Context Retriever SHALL NOT independently traverse the Project Root.

When selected content is stored by reference, content access SHALL occur through an authorized read contract associated with indexed artifacts.

The retriever SHALL NOT discover unindexed project artifacts.

---

# Content Loading

The retriever SHOULD delay loading full candidate content until necessary.

It MAY initially rank candidates using:

* Metadata.
* Symbol information.
* Search terms.
* Structural relationships.
* Estimated size.

Full content SHOULD be loaded only for:

* Final scoring when required.
* Excerpt generation.
* Final selection.
* Coverage evaluation.

---

# Excerpt Generation Ownership

The retriever MAY define which source regions are selected.

It SHALL produce source ranges or Context Items sufficient for the Context Builder.

The Context Builder SHALL package selected ranges but SHALL NOT independently expand them.

---

# Interaction with Context Builder

The Context Retriever SHALL provide:

* Ordered selected Context Items.
* Source references.
* Content references or selected content.
* Selection Rationales.
* Context Budget.
* Estimated sizes.
* Coverage diagnostics.
* Required ordering constraints.

The Context Builder SHALL NOT add project-derived items absent from the Retrieval Result.

---

# Interaction with Task Interpreter

The retriever consumes the normalized Task Specification.

When the Task Specification contains unresolved ambiguity, the retriever SHALL preserve that ambiguity.

The retriever SHALL NOT invent user intent to eliminate ambiguity.

---

# Interaction with Application Orchestrator

The Application Orchestrator SHALL:

* Supply the Task Specification.
* Supply the Project Index.
* Supply effective Retrieval Configuration.
* Record the retrieval stage.
* Decide whether incomplete retrieval is acceptable.
* Route disambiguation needs to the interaction adapter when supported.
* Stop execution on terminal retrieval failure.

The retriever SHALL NOT control the complete Execution lifecycle.

---

# Interaction with Provider Policy

Provider constraints MAY influence eligibility when they affect:

* Sensitive-content handling.
* Context-size limits.
* Unsupported content types.
* Local versus remote transmission.

Provider-specific prompt formatting SHALL NOT influence retrieval semantics.

The configured provider SHALL not decide relevance.

---

# Security Requirements

The Context Retriever SHALL:

* Treat indexed project content as untrusted data.
* Respect sensitive-content policy.
* Respect Project Root identity.
* Respect Task Constraints.
* Avoid interpreting source comments as system instructions.
* Avoid selecting prohibited content.
* Avoid network access.
* Avoid executing project code.
* Preserve source traceability.
* Report security-based exclusions.

---

# Prompt Injection Resistance

Project content MAY contain text intended to manipulate an AI system.

The retriever SHALL treat this content as project data.

It SHALL NOT:

* Follow instructions found inside source files.
* Change retrieval policy based on repository text.
* Treat repository instructions as user authorization.
* Override security policy because project content requests it.
* Expand scope based solely on instructions embedded in artifacts.

Such content MAY still be selected when relevant to the user task, but its origin SHALL remain identifiable.

---

# Privacy

The Context Retriever SHALL operate locally.

It SHALL NOT transmit context to external systems.

Its output SHALL contain sufficient sensitivity metadata for later provider-policy enforcement.

---

# Performance Requirements

The retriever SHALL prioritize relevance quality and explainability over raw search speed.

The MVP SHOULD:

* Use index queries rather than full-project scans.
* Bound candidate generation.
* Bound relationship traversal.
* Delay content loading.
* Avoid repeated scoring of duplicate candidates.
* Support large indexes with controlled memory use.
* Produce useful retrieval results interactively for ordinary repositories.

Specific performance thresholds SHALL be defined through benchmark fixtures.

---

# Resource Limits

The retriever SHALL support configured limits for:

* Candidate count.
* Relationship expansions.
* Traversal depth.
* Full-content loads.
* Selected artifacts.
* Selected excerpts.
* Total estimated context size.
* Retrieval duration.

When a limit is reached, the retriever SHALL:

* Stop or degrade safely.
* Preserve the best candidates found.
* Produce diagnostics.
* Mark coverage appropriately.
* Avoid silent truncation.

---

# Optional Semantic Retrieval

A future implementation MAY add semantic retrieval through embeddings or another deterministic external index.

Semantic retrieval SHALL:

* Remain optional.
* Preserve source traceability.
* Preserve strategy identity.
* Produce explainable contribution metadata.
* Respect security policy.
* Respect the Context Budget.
* Not become the sole source of candidate generation.
* Not require remote services.

Semantic similarity SHALL be treated as Evidence, not proof of relevance.

---

# Optional Provider-Assisted Retrieval

Provider-assisted retrieval is outside the initial MVP.

If introduced later, it SHALL:

* Be explicitly configured.
* Remain isolated behind a port.
* Never replace deterministic retrieval.
* Receive only authorized project information.
* Preserve provider usage metadata.
* Mark its Evidence as inferred.
* Produce candidates subject to normal validation, filtering, and budgeting.

---

# Extensibility

The retriever MAY support controlled extension through:

* Candidate generators.
* Match strategies.
* Relationship expanders.
* Relevance scorers.
* Policy filters.
* Duplicate detectors.
* Budget allocators.
* Coverage evaluators.

Extensions SHALL:

* Declare a strategy identifier.
* Declare a version.
* Remain deterministic unless explicitly classified otherwise.
* Preserve Evidence.
* Respect security policy.
* Respect the Context Budget.
* Avoid provider-specific coupling.
* Avoid direct project traversal.
* Avoid project code execution.

The MVP SHALL NOT require arbitrary third-party runtime plugin loading.

---

# Observability

The retriever SHOULD expose sufficient information to explain:

* Which terms were extracted from the task.
* Which explicit references were resolved.
* Which strategies generated each candidate.
* Why each selected item was included.
* Why material candidates were excluded.
* Which relationships were traversed.
* Whether the Context Budget constrained selection.
* Whether coverage is sufficient.
* Whether sensitive content was excluded.
* How long retrieval required.

Observability SHALL NOT require external telemetry.

---

# Implementation Organization

The source capability SHOULD be organized under:

```text
src/contextforge/retrieval/
```

Expected internal concepts MAY include:

```text
models
ports
services
strategies
scoring
filters
budget
coverage
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

| Requirement Area       | Context Retriever Responsibility                        |
| ---------------------- | ------------------------------------------------------- |
| Context minimization   | Select the smallest sufficient context set              |
| Task relevance         | Rank project information against the Task Specification |
| Explainability         | Preserve Selection Rationales and Evidence              |
| Token efficiency       | Enforce Context Budget                                  |
| Provider independence  | Select context without provider-specific behavior       |
| Deterministic analysis | Use stable retrieval strategies and tie-breaking        |
| Security               | Enforce sensitive-content and project policies          |
| Modularity             | Operate through Project Index query contracts           |
| Extensibility          | Support controlled retrieval strategies                 |
| Quality                | Evaluate context coverage and ambiguity                 |

---

# Acceptance Criteria

## AC-RETRIEVE-001 — Valid Retrieval

Given a valid Task Specification and compatible Project Index, the retriever SHALL produce a Retrieval Result.

---

## AC-RETRIEVE-002 — Explicit Path Priority

Given an exact valid artifact path explicitly referenced by the user, the corresponding artifact or relevant region SHALL receive highest-priority consideration.

---

## AC-RETRIEVE-003 — Explicit Symbol Resolution

Given an exact indexed symbol explicitly referenced by the user, the retriever SHALL resolve and select its definition when eligible.

---

## AC-RETRIEVE-004 — Missing Reference Visibility

Given an explicit reference that cannot be resolved, the retriever SHALL produce a diagnostic and SHALL NOT invent a target.

---

## AC-RETRIEVE-005 — Ambiguity Preservation

Given multiple equally plausible explicit-reference targets, the retriever SHALL preserve the ambiguity rather than silently choosing nondeterministically.

---

## AC-RETRIEVE-006 — Evidence Requirement

Every selected Context Item SHALL have at least one Selection Rationale supported by Evidence.

---

## AC-RETRIEVE-007 — Budget Compliance

The selected context SHALL NOT exceed the hard Context Budget.

---

## AC-RETRIEVE-008 — Mandatory Budget Failure

Given mandatory eligible candidates that exceed the Context Budget, the retriever SHALL report incomplete or failed retrieval according to policy.

---

## AC-RETRIEVE-009 — Duplicate Suppression

Given the same source region discovered by multiple strategies, the retriever SHALL avoid duplicate context while preserving combined Evidence.

---

## AC-RETRIEVE-010 — Relationship Expansion

Given a directly related indexed dependency, declaration, test, or configuration artifact, the retriever SHALL consider it according to active relationship policy.

---

## AC-RETRIEVE-011 — Bounded Traversal

Relationship traversal SHALL respect configured depth, fan-out, candidate, and budget limits.

---

## AC-RETRIEVE-012 — Security Precedence

Given a highly relevant candidate prohibited by security policy, the retriever SHALL exclude it.

---

## AC-RETRIEVE-013 — Sensitive Provider Policy

Given sensitive content prohibited for the configured provider mode, the retriever SHALL not select it for provider delivery.

---

## AC-RETRIEVE-014 — Generated Artifact Handling

Generated artifacts SHALL follow configured exclusion or deprioritization policy and SHALL not outrank authoritative source without task-specific Evidence.

---

## AC-RETRIEVE-015 — Test Retrieval

Given a modification or fix task with directly related indexed tests, the retriever SHOULD include the tests when the Context Budget permits.

---

## AC-RETRIEVE-016 — Deterministic Ranking

Given equivalent inputs, candidate ranking and tie-breaking SHALL be semantically stable.

---

## AC-RETRIEVE-017 — Minimum Sufficiency

Given a small relevant Structural Unit and a much larger containing artifact, the retriever SHOULD prefer the smaller unit when it provides sufficient context.

---

## AC-RETRIEVE-018 — No Hidden Content

Every project-derived Context Item selected for the Retrieval Result SHALL correspond to an indexed candidate and explicit selection decision.

---

## AC-RETRIEVE-019 — Coverage Evaluation

Every completed Retrieval Result SHALL include a context-coverage state.

---

## AC-RETRIEVE-020 — Incomplete Index Awareness

Given an incomplete Project Index, the retriever SHALL preserve that limitation in diagnostics and coverage evaluation.

---

## AC-RETRIEVE-021 — No Project Execution

The retriever SHALL complete context selection without executing, importing, compiling, or evaluating project code.

---

## AC-RETRIEVE-022 — Injection Resistance

Natural-language instructions contained in project artifacts SHALL not alter retrieval policy or authorization.

---

## AC-RETRIEVE-023 — Result Immutability

A finalized Retrieval Result SHALL be immutable.

---

## AC-RETRIEVE-024 — Builder Readiness

The Retrieval Result SHALL contain sufficient ordered context references, rationales, size metadata, and coverage information for the Context Builder to construct a Context Bundle without performing new retrieval.

---

# Test Categories

The Context Retriever SHALL be verified through:

* Unit tests for term extraction.
* Unit tests for explicit path resolution.
* Unit tests for symbol resolution.
* Unit tests for lexical matching.
* Unit tests for relationship expansion.
* Unit tests for score combination.
* Unit tests for duplicate suppression.
* Unit tests for overlap handling.
* Unit tests for Context Budget enforcement.
* Unit tests for deterministic tie-breaking.
* Unit tests for coverage evaluation.
* Unit tests for sensitive-content filtering.
* Integration tests with Project Index fixtures.
* Ambiguity tests.
* High-fan-out graph tests.
* Incomplete-index tests.
* Unsupported-language tests.
* Generated-artifact tests.
* Test-relation retrieval tests.
* Configuration-relation retrieval tests.
* Prompt-injection resistance tests.
* Large-index performance tests.
* Determinism tests.

Tests SHALL NOT require network access.

---

# Reference Retrieval Fixtures

The test suite SHOULD include tasks and indexes covering:

* Exact file path reference.
* Partial file name reference.
* Exact symbol reference.
* Ambiguous symbol reference.
* Missing file reference.
* Stack-trace location.
* Error-message match.
* Implementation and related tests.
* Interface and implementation relationship.
* Base class and subclass relationship.
* Caller and callee relationship.
* Configuration-driven behavior.
* Build or container configuration.
* Documentation-only task.
* Generated and authoritative source duplicates.
* Sensitive artifact with local provider.
* Sensitive artifact with remote provider.
* Incomplete Project Index.
* High-fan-out utility symbol.
* Very small Context Budget.
* Multiple equally scored candidates.
* Large source file with one relevant function.
* Source containing prompt-injection-like instructions.

---

# Validation Criteria

This specification SHALL be considered satisfied when:

* A Task Specification and Project Index can be transformed into an immutable Retrieval Result.
* Explicit references receive priority.
* Ambiguity remains visible.
* Candidate generation is bounded and deterministic.
* Relevance decisions preserve Evidence.
* Relationship traversal is controlled.
* Duplicate and overlapping content are reduced.
* Sensitive and prohibited content are excluded.
* The Context Budget is strictly enforced.
* Selected context is minimal but sufficient.
* Coverage limitations are reported.
* No other capability is required to repeat task-specific retrieval.
* The Context Builder can package the selection without introducing additional project content.

---

# Completion Statement

The Context Retriever is complete when ContextForge can deterministically identify, rank, filter, explain, and select the smallest sufficient set of indexed project information required for a Task Specification while respecting security policy, ambiguity, relationship boundaries, and the active Context Budget.
