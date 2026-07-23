# Context Builder Specification

Document ID: CF-008

Status: Draft

Version: 0.1.0

Owner: ContextForge Architecture Board

Language: English

Normative: Yes

Depends On:

* CF-000 — AI-Native Specification
* CF-001 — Vision
* CF-002 — PRD
* CF-003 — Architecture
* CF-004 — Domain Model
* CF-007 — Context Retriever

---

# Abstract

The Context Builder is responsible for transforming a Retrieval Result into an immutable Context Bundle.

Unlike the Context Retriever, the Context Builder SHALL NOT decide relevance.

Its responsibility is limited to packaging, ordering, validating and preparing the selected context for prompt generation.

The Context Builder is therefore a transformation capability rather than a decision capability.

---

# Purpose

The Context Builder converts selected project information into a structured representation that can later be consumed by the Prompt Builder.

It SHALL guarantee that every Context Bundle:

* is deterministic,
* is complete according to the Retrieval Result,
* is immutable,
* preserves traceability,
* preserves ordering,
* preserves evidence,
* preserves source locations.

---

# Architectural Responsibility

The Context Builder answers exactly one question:

> How should the selected context be organized?

It SHALL NOT answer:

* What is relevant?
* What should be added?
* What should be removed?
* Which candidate is better?

Those decisions belong exclusively to the Context Retriever.

---

# Inputs

The Context Builder consumes:

* Retrieval Result
* Context Items
* Selection Rationales
* Context Budget
* Builder Configuration

It SHALL trust the Retrieval Result as authoritative.

---

# Outputs

The Context Builder produces:

* Context Bundle
* Bundle Metadata
* Bundle Diagnostics

---

# Context Bundle

A Context Bundle SHALL contain:

* Bundle Identifier
* Task Identifier
* Ordered Context Items
* Bundle Metadata
* Construction Diagnostics
* Estimated Size
* Context Statistics

The Context Bundle SHALL be immutable.

---

# Context Item Ordering

Ordering SHALL preserve semantic understanding.

The recommended canonical ordering is:

1. User supplied content
2. Explicitly referenced artifacts
3. Primary implementation
4. Supporting declarations
5. Related configuration
6. Related tests
7. Documentation
8. Supporting metadata

The ordering SHALL originate from the Retrieval Result whenever possible.

The Builder SHALL NOT reorder items based on subjective quality.

---

# Source Traceability

Every Context Item SHALL preserve:

* Artifact Identifier
* Source Location
* Selection Rationale
* Evidence
* Candidate Identifier

Traceability SHALL never be lost during bundle construction.

---

# Bundle Validation

Before finalization the Builder SHALL verify:

* every Context Item is valid;
* every Source Location exists;
* every Selection Rationale exists;
* every required reference is present;
* bundle ordering is valid;
* bundle size metadata is consistent.

Invalid bundles SHALL NOT be finalized.

---

# Bundle Metadata

Bundle Metadata SHOULD contain:

* Bundle Version
* Creation Timestamp
* Builder Version
* Retrieval Identifier
* Project Identifier
* Project Fingerprint
* Estimated Tokens
* Character Count
* Line Count
* Item Count

---

# Context Statistics

The Builder SHOULD calculate:

* Artifact count
* Excerpt count
* Symbol count
* Relationship count
* Documentation count
* Test count
* Configuration count
* Generated artifact count

These statistics SHALL be informational only.

---

# Size Estimation

The Builder SHALL preserve the estimated size calculated by the Retriever.

It MAY recompute statistics.

It SHALL NOT enlarge the selected context.

---

# Bundle Integrity

The Builder SHALL verify:

* no duplicated Context Items;
* no duplicated excerpts;
* no invalid references;
* no missing rationale;
* no orphan source locations.

---

# Immutability

After creation the Context Bundle SHALL become immutable.

Any modification SHALL require construction of a new bundle.

---

# Diagnostics

The Builder SHALL produce structured diagnostics.

Examples include:

* Missing Context Item
* Invalid Source Location
* Duplicate Item
* Invalid Ordering
* Missing Selection Rationale
* Invalid Bundle Metadata

---

# Failure Model

Terminal failures include:

* Invalid Retrieval Result
* Missing mandatory Context Item
* Invalid ordering
* Corrupted bundle state

Recoverable conditions include:

* Missing optional metadata
* Size estimation mismatch
* Non-critical statistics failure

---

# Determinism

Given identical:

* Retrieval Result
* Builder Configuration

The Builder SHALL produce semantically identical Context Bundles.

---

# Security

The Builder SHALL:

* preserve sensitive classifications;
* never remove security metadata;
* never reveal hidden diagnostics;
* never execute project content.

---

# Performance

The Builder SHALL operate in linear time relative to the number of Context Items whenever practical.

---

# Interaction with Prompt Builder

The Prompt Builder SHALL consume the Context Bundle exactly as produced.

The Prompt Builder SHALL NOT modify:

* ordering;
* traceability;
* evidence;
* context membership.

---

# Acceptance Criteria

AC-BUILD-001

Given a valid Retrieval Result,
the Builder SHALL produce one immutable Context Bundle.

---

AC-BUILD-002

The Builder SHALL NOT introduce new Context Items.

---

AC-BUILD-003

The Builder SHALL preserve ordering.

---

AC-BUILD-004

Every Context Item SHALL preserve traceability.

---

AC-BUILD-005

The Bundle SHALL preserve Retrieval Rationales.

---

AC-BUILD-006

Bundle construction SHALL be deterministic.

---

AC-BUILD-007

Duplicate Context Items SHALL NOT exist.

---

AC-BUILD-008

Security metadata SHALL be preserved.

---

AC-BUILD-009

Invalid bundles SHALL be rejected.

---

AC-BUILD-010

The resulting Context Bundle SHALL be immutable.

---

# Completion Statement

The Context Builder is complete when every Retrieval Result can be transformed into one deterministic, immutable, traceable and provider-independent Context Bundle without modifying retrieval decisions or introducing additional project information.
