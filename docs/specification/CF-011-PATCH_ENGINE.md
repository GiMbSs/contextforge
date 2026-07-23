# Patch Engine Specification

Document ID: CF-011

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
* CF-009 — Prompt Builder
* CF-010 — Provider Interface

---

# Abstract

The Patch Engine validates, interprets and materializes provider responses into deterministic Patch Proposals.

The Patch Engine SHALL NOT trust provider output.

Every response produced by an inference provider SHALL be treated as untrusted external data.

The Patch Engine is the only capability authorized to interpret provider-generated project modifications.

---

# Purpose

The Patch Engine transforms an Inference Response into one or more validated Patch Proposals.

Its responsibilities include:

* response validation
* contract validation
* patch parsing
* path validation
* operation validation
* conflict detection
* safety validation
* proposal generation
* diagnostics

It SHALL never modify project files.

---

# Architectural Responsibility

The Patch Engine answers:

> What changes is the provider proposing?

It SHALL NOT answer:

* Should these changes be accepted?
* Should they be written to disk?
* Should they be committed?

Approval belongs to the Application Orchestrator or an explicit Approval Policy.

Application belongs to a future Patch Applier capability.

---

# Scope

The Patch Engine SHALL support:

* Unified Diff
* Structured JSON Patch
* File Replacement
* Multi-file proposals
* Patch diagnostics
* Contract validation
* Conflict detection
* Immutable Patch Proposal generation

The MVP SHALL support Unified Diff and Structured JSON Patch.

---

# Inputs

The Patch Engine consumes:

* Inference Response
* Expected Response Contract
* Task Specification
* Project State Fingerprint
* Patch Engine Configuration

---

# Outputs

The Patch Engine produces:

* Patch Proposal
* Validation Result
* Patch Diagnostics

---

# Patch Proposal

A Patch Proposal SHALL contain:

* Proposal Identifier
* Task Identifier
* Request Identifier
* Response Identifier
* Project Fingerprint
* Proposed Changes
* Validation Summary
* Diagnostics
* Proposal Metadata

The proposal SHALL be immutable.

---

# Proposed Change

Each Proposed Change SHALL contain:

* project-relative path
* operation

Operations:

* create
* modify
* delete
* rename

Additionally:

* patch payload
* explanation
* assumptions

---

# Validation Pipeline

The canonical validation sequence SHALL be:

1. Validate response contract
2. Validate response structure
3. Parse patch
4. Validate operations
5. Validate paths
6. Validate duplicate operations
7. Validate conflicts
8. Validate project boundaries
9. Validate proposal consistency
10. Produce Patch Proposal

---

# Response Contract Validation

The provider response SHALL satisfy the Expected Response Contract.

Examples:

* required fields
* required operations
* mandatory explanations
* supported patch format

Missing mandatory fields SHALL invalidate the proposal.

---

# Path Validation

Every path SHALL:

* be project-relative
* remain inside Project Root
* be normalized
* avoid traversal sequences
* avoid absolute paths

Examples of prohibited paths:

```text
../../etc/passwd
C:\Windows
/home/user/project
```

---

# Operation Validation

Allowed operations:

* create
* modify
* delete
* rename

Unknown operations SHALL invalidate the proposal.

---

# Conflict Detection

The engine SHALL detect:

* duplicate file operations
* conflicting edits
* duplicate creations
* multiple deletes
* incompatible rename chains

Conflicts SHALL produce diagnostics.

---

# Proposal Integrity

The Patch Proposal SHALL satisfy:

* unique change identifiers
* valid operations
* normalized paths
* immutable payload
* deterministic ordering

---

# Patch Parsing

Supported parsers MAY include:

* Unified Diff Parser
* JSON Patch Parser
* Replacement Parser

Parser selection SHALL follow the Expected Response Contract.

---

# Unified Diff

The engine SHALL validate:

* file headers
* hunk headers
* operations
* consistency

Malformed diffs SHALL be rejected.

---

# Structured Patch

Structured patches SHALL contain:

* path
* operation
* content or patch
* explanation

Unknown fields MAY be ignored.

Missing mandatory fields SHALL invalidate the proposal.

---

# Replace Operation

Replacement payloads SHALL preserve:

* full content
* encoding
* operation type

---

# Duplicate Detection

The engine SHALL detect:

* identical changes
* repeated operations
* repeated paths

Duplicates SHALL NOT appear in the final proposal.

---

# Rename Validation

Rename SHALL validate:

* source exists
* destination valid
* no circular rename
* no overwrite unless authorized

---

# Delete Validation

Delete SHALL validate:

* target path
* duplicate delete
* protected files

---

# Create Validation

Create SHALL validate:

* destination path
* overwrite policy
* directory validity

---

# Protected Files

Configuration MAY define protected artifacts.

Examples:

* .git/
* .env
* secrets/
* credential stores

Unauthorized modifications SHALL invalidate the proposal.

---

# Response Integrity

The engine SHALL preserve:

* original response
* normalized proposal
* validation diagnostics

---

# Proposal Metadata

Metadata SHOULD include:

* creation timestamp
* parser version
* validation version
* proposal version

---

# Determinism

Given identical:

* response
* configuration

the engine SHALL produce semantically identical Patch Proposals.

---

# Diagnostics

Canonical diagnostics include:

* Invalid Contract
* Invalid Patch
* Invalid Path
* Duplicate Operation
* Unsupported Operation
* Conflict
* Protected File
* Invalid Rename
* Invalid Delete
* Invalid Create

---

# Failure Model

Terminal failures:

* invalid contract
* malformed patch
* unsupported format
* invalid project path

Recoverable:

* duplicate changes
* ignored optional metadata
* unsupported optional fields

---

# Security

The engine SHALL:

* distrust provider output
* reject project escape
* reject absolute paths
* preserve proposal traceability
* never execute provider code

---

# Immutability

Patch Proposals SHALL become immutable after validation.

---

# Traceability

Each Proposed Change SHALL preserve:

* originating response
* originating request
* task identifier
* provider metadata

---

# Acceptance Criteria

AC-PATCH-001

Valid responses SHALL produce one Patch Proposal.

---

AC-PATCH-002

Invalid responses SHALL NOT produce valid proposals.

---

AC-PATCH-003

Project escape SHALL be rejected.

---

AC-PATCH-004

Absolute paths SHALL be rejected.

---

AC-PATCH-005

Unsupported operations SHALL be rejected.

---

AC-PATCH-006

Duplicate changes SHALL NOT appear.

---

AC-PATCH-007

Protected files SHALL obey policy.

---

AC-PATCH-008

Patch validation SHALL be deterministic.

---

AC-PATCH-009

Patch Proposals SHALL be immutable.

---

AC-PATCH-010

The engine SHALL never modify project files.

---

# Completion Statement

The Patch Engine is complete when every provider response can be deterministically transformed into an immutable Patch Proposal that satisfies the Expected Response Contract, preserves project safety boundaries, rejects unauthorized modifications, and never alters project state directly.
