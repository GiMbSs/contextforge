# Command-Line Interface Specification

Document ID: CF-012
Status: Draft
Version: 0.1.0
Owner: ContextForge Architecture Board
Language: English
Audience:

* Engineers
* Contributors
* Product Owners
* AI Agents
* CLI Maintainers

Normative: Yes

Depends On:

* CF-000 — AI-Native Specification
* CF-001 — Vision
* CF-002 — Product Requirements Document
* CF-003 — System Architecture
* CF-004 — Domain Model
* CF-005 — Project Scanner Specification
* CF-006 — Project Indexer Specification
* CF-007 — Context Retriever Specification
* CF-008 — Context Builder Specification
* CF-009 — Prompt Builder Specification
* CF-010 — Provider Interface Specification
* CF-011 — Patch Engine Specification

Related ADRs:

* ADR-0001 — Context-First Architecture
* ADR-0002 — Hexagonal Architecture
* ADR-0003 — Dependency Rule
* ADR-0004 — Feature-Based Module Organization

---

# Abstract

This document defines the Command-Line Interface capability of ContextForge.

The CLI is the primary user-facing adapter for the MVP.

It exposes ContextForge operations without containing domain logic.

The CLI SHALL translate command-line input into application commands, invoke the Application Orchestrator, display results, collect explicit user approval, and return stable process exit codes.

The CLI SHALL NOT:

* Scan projects directly.
* Build indexes directly.
* Decide relevant context.
* Construct prompts.
* Invoke inference providers directly.
* Parse provider patches independently.
* Apply unapproved changes.
* Reimplement application policies.
* Contain provider-specific business logic.
* Bypass Core validation.

---

# Purpose

The CLI provides a predictable, scriptable, inspectable, and safe interface for ContextForge.

Its primary responsibilities are:

* Parse commands and arguments.
* Resolve the target project.
* Load user-facing configuration.
* Submit application commands.
* Display execution progress.
* Display diagnostics.
* Display retrieved context summaries.
* Display prompt previews.
* Display provider execution information.
* Display Patch Proposals.
* Collect explicit approval before patch application.
* Return stable machine-readable exit states.
* Support non-interactive automation without weakening safety controls.

---

# Architectural Responsibility

The CLI answers:

> How does a user interact with ContextForge from a terminal?

It SHALL NOT answer:

* Which context is relevant?
* Which artifact should be indexed?
* Whether provider output is valid?
* Whether an unsafe path is permitted?
* How a patch is parsed?
* Whether provider delivery is authorized?

Those decisions belong to Core capabilities and application policies.

---

# Scope

The CLI SHALL support:

* Project initialization.
* Project inspection.
* Project scanning.
* Project indexing.
* Task execution.
* Context inspection.
* Prompt preview.
* Provider listing and health inspection.
* Patch Proposal review.
* Explicit patch approval.
* Patch rejection.
* Patch application through an authorized application service.
* Diagnostic output.
* Human-readable output.
* Machine-readable output.
* Non-interactive operation.
* Stable exit codes.
* Configuration inspection.
* Version information.

The MVP SHALL be terminal-based.

---

# Out of Scope

The CLI SHALL NOT provide:

* Graphical user interface.
* Full-screen terminal UI.
* IDE integration.
* Autonomous multi-step agents.
* Background daemon mode.
* Web server mode.
* Collaborative review workflows.
* Hosted project synchronization.
* Cloud account management.
* Repository hosting integration.
* Automatic Git commits.
* Automatic remote pushes.
* Automatic provider fallback without policy.
* Implicit patch approval.
* Arbitrary shell execution.
* Interactive source-code editing.

---

# Capability Boundary

The CLI consumes:

* Command-line arguments.
* Standard input.
* Environment configuration.
* ContextForge configuration files.
* Interactive user responses.
* Application service results.

The CLI produces:

* Application commands.
* Human-readable terminal output.
* Machine-readable structured output.
* Explicit approval or rejection commands.
* Process exit codes.

---

# Primary Interface

The executable name SHALL be:

```text
contextforge
```

A shorter alias MAY be provided:

```text
cf
```

The canonical interface SHALL remain `contextforge`.

---

# Command Structure

The canonical command form SHALL be:

```text
contextforge <command> [subcommand] [options] [arguments]
```

Commands SHALL use lowercase kebab-case.

Examples:

```text
contextforge init
contextforge scan
contextforge index
contextforge run "Fix the startup error"
contextforge context show
contextforge patch review
contextforge patch apply
contextforge provider list
```

---

# Global Options

The CLI SHOULD support:

```text
--project <path>
--config <path>
--profile <name>
--provider <identifier>
--model <identifier>
--format <format>
--non-interactive
--verbose
--quiet
--debug
--no-color
--version
--help
```

Global options SHALL be accepted before or after the main command when the parsing framework permits it consistently.

---

# Project Resolution

The CLI SHALL resolve the project root through the following precedence:

1. Explicit `--project`.
2. Nearest parent directory containing ContextForge project metadata.
3. Current working directory when valid.
4. Failure with a project-resolution diagnostic.

Project resolution SHALL be deterministic.

The CLI SHALL display the resolved project root in verbose mode.

---

# Project Metadata

ContextForge project metadata SHOULD be stored in a dedicated project directory:

```text
.contextforge/
```

The directory MAY contain:

```text
config.toml
inventory/
index/
executions/
proposals/
cache/
logs/
```

Sensitive content SHALL not be stored there by default unless policy explicitly permits it.

---

# Configuration Precedence

Effective configuration SHALL be resolved through this precedence:

1. Explicit command-line options.
2. Explicit `--config` file.
3. Named profile.
4. Project configuration.
5. User configuration.
6. Environment variables.
7. Built-in defaults.

Higher-precedence values override lower-precedence values.

The CLI SHALL provide a way to inspect effective configuration.

Secrets SHALL be redacted in displayed configuration.

---

# Configuration Locations

Default configuration locations MAY include:

Project configuration:

```text
<project-root>/.contextforge/config.toml
```

User configuration:

```text
~/.config/contextforge/config.toml
```

Platform-specific equivalents MAY be supported.

The CLI SHALL not require project configuration for basic operation when defaults are sufficient.

---

# Environment Variables

Environment variables SHOULD use the prefix:

```text
CONTEXTFORGE_
```

Examples MAY include:

```text
CONTEXTFORGE_PROVIDER
CONTEXTFORGE_MODEL
CONTEXTFORGE_CONFIG
CONTEXTFORGE_LOG_LEVEL
CONTEXTFORGE_NON_INTERACTIVE
```

Credentials SHALL use provider-specific secure environment variables or secret references.

The CLI SHALL not print credential values.

---

# Output Modes

The CLI SHALL support at least:

* Human-readable text.
* JSON.

It MAY later support:

* JSON Lines.
* YAML.
* Markdown.

The selected output mode SHALL not change application semantics.

---

# Human-Readable Output

Human-readable output SHOULD:

* Use concise headings.
* Distinguish success, warning, and failure.
* Display project-relative paths.
* Display actionable diagnostics.
* Avoid excessive internal identifiers.
* Avoid raw stack traces unless debug mode is enabled.
* Preserve terminal readability without requiring color.

Color SHALL be optional.

---

# Machine-Readable Output

JSON output SHALL:

* Be valid JSON.
* Contain no unrelated terminal prose on standard output.
* Use stable top-level fields.
* Include execution status.
* Include diagnostics.
* Include relevant identifiers.
* Exclude secrets.
* Remain versioned.

Progress information in machine-readable mode SHOULD be sent to standard error or emitted as structured events when explicitly requested.

---

# Standard Output and Standard Error

The CLI SHALL use:

* Standard output for requested command results.
* Standard error for diagnostics, warnings, progress, and debug information.

In JSON mode, standard output SHALL remain parseable.

---

# Exit Codes

The CLI SHALL define stable exit codes.

Recommended codes are:

| Code | Meaning                      |
| ---: | ---------------------------- |
|    0 | Success                      |
|    1 | General application failure  |
|    2 | Invalid CLI usage            |
|    3 | Configuration failure        |
|    4 | Project resolution failure   |
|    5 | Scan failure                 |
|    6 | Index failure                |
|    7 | Retrieval failure            |
|    8 | Prompt construction failure  |
|    9 | Provider failure             |
|   10 | Patch validation failure     |
|   11 | Approval required            |
|   12 | Patch rejected               |
|   13 | Patch application failure    |
|   14 | Project state conflict       |
|   15 | Security policy rejection    |
|   16 | Operation cancelled          |
|   17 | Partial or incomplete result |
|   18 | Unsupported capability       |

Exit-code meanings SHALL remain backward-compatible after publication.

---

# Command Categories

The CLI SHOULD group commands into:

* Project commands.
* Analysis pipeline commands.
* Provider commands.
* Context inspection commands.
* Patch commands.
* Configuration commands.
* Diagnostic commands.

---

# `init` Command

The `init` command initializes ContextForge metadata for a project.

Canonical form:

```text
contextforge init [path]
```

It MAY:

* Resolve or create the project metadata directory.
* Create a default configuration file.
* Record project identity.
* Create ignored runtime directories.
* Suggest version-control ignore entries.

It SHALL NOT:

* Modify application source files.
* Install project dependencies.
* Invoke a provider.
* Run inference.

---

# `init` Options

Suggested options:

```text
--force
--minimal
--provider <identifier>
--model <identifier>
--no-gitignore
```

`--force` SHALL not overwrite existing configuration silently.

Existing files SHALL require explicit overwrite behavior.

---

# `status` Command

The `status` command displays ContextForge project state.

Canonical form:

```text
contextforge status
```

It SHOULD display:

* Project root.
* Project identifier.
* Scanner state.
* Inventory state.
* Index state.
* Project fingerprint.
* Last execution.
* Pending Patch Proposal.
* Selected provider.
* Provider health when requested.
* Configuration profile.

---

# `scan` Command

The `scan` command requests project discovery through the Application Orchestrator.

Canonical form:

```text
contextforge scan
```

Options MAY include:

```text
--full
--incremental
--include-generated
--show-artifacts
--dry-run
```

The CLI SHALL not implement traversal itself.

---

# Scan Output

Scan output SHOULD include:

* Scan status.
* Artifact count.
* Directory count.
* Ignored count.
* Binary artifact count.
* Generated artifact count.
* Sensitive artifact count.
* Diagnostics.
* Project fingerprint.
* Scan duration.

Detailed artifact output SHALL require an explicit option.

---

# `index` Command

The `index` command requests Project Index construction.

Canonical form:

```text
contextforge index
```

Options MAY include:

```text
--full
--incremental
--rebuild
--show-summary
--dry-run
```

The command SHALL use the current compatible Project Inventory or request scanning through orchestration policy.

---

# Index Output

Index output SHOULD include:

* Index status.
* Indexed artifact count.
* Symbol count.
* Relationship count.
* Search unit count.
* Unsupported artifact count.
* Failed parser count.
* Diagnostics.
* Index Identifier.
* Project fingerprint.
* Index duration.

---

# `run` Command

The `run` command executes the ContextForge task pipeline.

Canonical form:

```text
contextforge run "<task>"
```

The task MAY alternatively be supplied through:

```text
--task-file <path>
--stdin
```

Exactly one task source SHOULD be required.

---

# Run Pipeline

The canonical `run` pipeline SHALL be:

1. Resolve the project.
2. Resolve effective configuration.
3. Build the Task Specification.
4. Ensure a compatible Project Inventory.
5. Ensure a compatible Project Index.
6. Execute context retrieval.
7. Build the Context Bundle.
8. Build the Inference Request.
9. Validate provider delivery.
10. Invoke the provider.
11. Validate the provider response.
12. Produce a Patch Proposal or analysis result.
13. Display the result.
14. Request approval when patch application is requested.
15. Apply only after explicit authorization.

The CLI SHALL invoke this pipeline through the Application Orchestrator.

---

# `run` Options

Suggested options include:

```text
--task-file <path>
--stdin
--analysis-only
--patch
--apply
--dry-run
--provider <identifier>
--model <identifier>
--max-context <size>
--show-context
--show-prompt
--save-execution
--non-interactive
```

`--apply` SHALL not imply automatic approval in an interactive execution without a confirmation step.

In non-interactive mode, patch application SHALL require an explicit approval mechanism defined by this specification.

---

# Task Input

The CLI SHALL preserve the user's task text.

Task input SHALL not be silently rewritten.

The CLI MAY normalize line endings and surrounding terminal whitespace.

Empty task input SHALL be rejected.

---

# Multiline Tasks

Multiline tasks SHOULD be supported through:

```text
contextforge run --stdin
```

or:

```text
contextforge run --task-file task.md
```

Task files SHALL be treated as user instructions, not project artifacts.

---

# Analysis-Only Execution

The `--analysis-only` option SHALL require an analysis response contract.

In analysis-only mode:

* No Patch Proposal SHALL be required.
* Patch application SHALL be unavailable.
* Provider claims of file modification SHALL remain non-authoritative.
* The result SHALL be displayed as analysis.

---

# Patch Execution

When patch output is requested, the CLI SHALL display:

* Proposal Identifier.
* Summary.
* Proposed files.
* Operations.
* Validation state.
* Warnings.
* Project fingerprint.
* Approval state.

The CLI SHALL not present an invalid provider response as an applicable patch.

---

# `context` Command Group

The context command group SHALL provide inspection without modifying retrieval decisions.

Suggested subcommands:

```text
contextforge context show
contextforge context list
contextforge context explain
contextforge context export
```

---

# `context show`

Canonical form:

```text
contextforge context show
```

It SHOULD display the latest Context Bundle summary.

Options MAY include:

```text
--execution <identifier>
--full
--metadata
--format json
```

Sensitive content SHALL follow display policy.

---

# `context list`

Canonical form:

```text
contextforge context list
```

It SHOULD list:

* Context Item order.
* Project-relative path.
* Item type.
* Source location.
* Estimated size.
* Primary Selection Rationale.
* Sensitivity classification when permitted.

---

# `context explain`

Canonical form:

```text
contextforge context explain <item-or-path>
```

It SHOULD display:

* Why the item was selected.
* Evidence.
* Strategy contributions.
* Relationship path.
* Rank.
* Budget effect.
* Relevant diagnostics.

The CLI SHALL obtain this information from the Retrieval Result.

---

# `context export`

Canonical form:

```text
contextforge context export
```

It MAY export a Context Bundle representation for inspection.

Export SHALL:

* Preserve traceability.
* Preserve ordering.
* Respect sensitive-content policy.
* Avoid implying that the exported bundle is a provider request.
* Require explicit destination or standard output.

---

# `prompt` Command Group

Suggested subcommands:

```text
contextforge prompt preview
contextforge prompt measure
contextforge prompt export
```

The CLI SHALL not rebuild prompts itself.

---

# `prompt preview`

Canonical form:

```text
contextforge prompt preview
```

It SHALL request a safe preview representation from the Prompt Builder or application service.

The preview SHOULD display:

* Logical sections.
* Context boundaries.
* Response Contract.
* Estimated size.
* Provider capability requirements.
* Incomplete-context warnings.

Sensitive data SHALL follow preview policy.

---

# `prompt measure`

Canonical form:

```text
contextforge prompt measure
```

It SHOULD display:

* Character count.
* Byte count.
* Estimated token count.
* Context contribution.
* Instruction contribution.
* Response-contract contribution.
* Effective provider limit.
* Remaining capacity.

---

# `provider` Command Group

Suggested subcommands:

```text
contextforge provider list
contextforge provider show
contextforge provider health
contextforge provider models
```

The CLI SHALL access providers through application services and Provider Ports.

---

# `provider list`

Canonical form:

```text
contextforge provider list
```

It SHOULD display:

* Provider Identifier.
* Adapter Identifier.
* Execution Mode.
* Health state.
* Default model.
* Structured-output support.
* Input-size limit when known.

---

# `provider show`

Canonical form:

```text
contextforge provider show <provider>
```

It SHOULD display:

* Provider configuration summary.
* Adapter version.
* Capability profile.
* Execution Mode.
* Endpoint profile without credentials.
* Supported models when available.
* Delivery-policy status.

---

# `provider health`

Canonical form:

```text
contextforge provider health [provider]
```

Health checks SHALL not transmit project content.

The command SHALL distinguish:

* Healthy.
* Degraded.
* Unavailable.
* Misconfigured.
* Unknown.

---

# `provider models`

Canonical form:

```text
contextforge provider models [provider]
```

It MAY list available models when the adapter supports model discovery.

The command SHALL not automatically download models.

---

# `patch` Command Group

The patch command group SHALL manage Patch Proposal inspection and explicit authorization.

Suggested subcommands:

```text
contextforge patch list
contextforge patch show
contextforge patch review
contextforge patch approve
contextforge patch reject
contextforge patch apply
contextforge patch export
```

---

# Patch Lifecycle

The CLI SHALL represent patch states including:

* Proposed.
* Validated.
* Awaiting Approval.
* Approved.
* Rejected.
* Stale.
* Applied.
* Application Failed.

The CLI SHALL not alter lifecycle states without an application command.

---

# `patch list`

Canonical form:

```text
contextforge patch list
```

It SHOULD display:

* Proposal Identifier.
* Task summary.
* Creation time.
* Validation state.
* Approval state.
* Project fingerprint.
* Number of changes.

---

# `patch show`

Canonical form:

```text
contextforge patch show [proposal]
```

It SHOULD display:

* Summary.
* Proposed operations.
* Project-relative paths.
* Diff or replacement content.
* Assumptions.
* Validation notes.
* Diagnostics.
* Provider and model metadata when permitted.

---

# `patch review`

Canonical form:

```text
contextforge patch review [proposal]
```

The review output SHOULD prioritize:

* File-by-file changes.
* Added lines.
* Removed lines.
* Created files.
* Deleted files.
* Renames.
* Protected-file warnings.
* Project-state conflicts.
* Validation status.

Review SHALL occur before approval.

---

# Explicit Approval Principle

No Patch Proposal SHALL be applied without explicit approval.

Approval SHALL be:

* Intentional.
* Traceable.
* Bound to one Proposal Identifier.
* Bound to one Project State Fingerprint.
* Bound to one effective set of proposed changes.
* Invalidated when the proposal changes.

A generic confirmation from a previous execution SHALL not authorize a new proposal.

---

# `patch approve`

Canonical form:

```text
contextforge patch approve <proposal>
```

Interactive approval SHALL require a clear confirmation.

The prompt SHOULD identify:

* Proposal Identifier.
* Number of affected files.
* Create, modify, delete, and rename counts.
* Protected-file warnings.
* Project fingerprint.

The user SHALL confirm the exact proposal.

---

# Confirmation Text

A high-risk proposal MAY require typed confirmation.

Examples include:

```text
Type the proposal identifier to approve:
```

or:

```text
Type APPLY to approve these changes:
```

Simple yes/no confirmation MAY be used for ordinary validated proposals.

---

# Non-Interactive Approval

In non-interactive mode, approval SHALL require an explicit option such as:

```text
--approve <proposal-identifier>
```

or:

```text
--approval-file <path>
```

A generic `--yes` option SHALL NOT be sufficient for patch application unless it is cryptographically or semantically bound to the exact proposal.

Environment variables SHALL not be accepted as implicit broad approval by default.

---

# Approval Record

An Approval Record SHALL include:

* Approval Identifier.
* Proposal Identifier.
* Project Fingerprint.
* Approving principal or execution context when available.
* Approval timestamp.
* Approval method.
* Proposal content fingerprint.
* Applicable warnings acknowledged.

The CLI SHALL display approval success only after the application service records it.

---

# `patch reject`

Canonical form:

```text
contextforge patch reject <proposal>
```

Rejection MAY include a reason:

```text
--reason "<reason>"
```

A rejected proposal SHALL not be applied unless a new explicit approval lifecycle is created according to policy.

---

# `patch apply`

Canonical form:

```text
contextforge patch apply <proposal>
```

Patch application SHALL require:

* A valid Patch Proposal.
* An active Approval Record.
* Matching Proposal Identifier.
* Matching proposal fingerprint.
* Matching Project State Fingerprint.
* Satisfied protected-file policy.
* Authorized application capability.

The CLI SHALL not write files directly.

---

# Patch Application Boundary

The Patch Engine defined by CF-011 validates and materializes Patch Proposals but does not modify files.

Therefore, patch application SHALL occur through a distinct authorized application service or adapter.

The CLI SHALL invoke that service.

The application service SHALL:

* Revalidate project state.
* Apply changes atomically when practical.
* Produce an Application Result.
* Preserve rollback information when policy requires it.
* Report partial application explicitly.
* Never execute provider-generated code as part of application.

---

# Stale Proposal Handling

A Patch Proposal SHALL be considered stale when the current Project State Fingerprint differs from the proposal fingerprint.

A stale proposal SHALL not be applied automatically.

The CLI SHALL display a project-state conflict.

Permitted recovery MAY include:

* Regenerate the proposal.
* Revalidate against the current state through an explicit workflow.
* Reject the proposal.
* Inspect changes manually.

---

# Dry Run

Commands capable of changing state SHOULD support:

```text
--dry-run
```

Dry-run mode SHALL:

* Perform validation.
* Display intended effects.
* Avoid project-file modification.
* Avoid recording final approval as consumed.
* Avoid claiming successful application.

---

# Atomic Application

When practical, patch application SHOULD be atomic.

If all changes cannot be applied safely, the application service SHOULD avoid modifying the project.

When partial application occurs, the CLI SHALL:

* Return a nonzero exit code.
* Identify applied and unapplied changes.
* Display recovery instructions.
* Preserve diagnostics.
* Avoid claiming rollback succeeded unless verified.

---

# Backup Policy

Patch application MAY support backups.

Suggested options:

```text
--backup
--backup-dir <path>
--no-backup
```

Backup policy belongs to the application service.

The CLI SHALL expose the effective policy.

Backups SHALL not include unrelated project files.

---

# Version-Control Awareness

The CLI MAY inspect version-control state through an authorized adapter.

It MAY display:

* Modified files.
* Untracked files.
* Current branch.
* Dirty working tree.
* Patch overlap with existing changes.

The CLI SHALL not require Git for the MVP.

It SHALL not automatically commit or push.

---

# Dirty Working Tree

When version-control integration is available, a dirty working tree MAY produce a warning.

Patch application policy MAY:

* Permit application.
* Require explicit acknowledgement.
* Reject overlapping changes.
* Require backup.

The CLI SHALL not discard user changes.

---

# `config` Command Group

Suggested subcommands:

```text
contextforge config show
contextforge config get
contextforge config set
contextforge config validate
contextforge config paths
```

---

# `config show`

Canonical form:

```text
contextforge config show
```

It SHOULD display effective configuration with source attribution.

Example source categories:

* Command line.
* Environment.
* Project.
* User.
* Default.

Secrets SHALL be redacted.

---

# `config get`

Canonical form:

```text
contextforge config get <key>
```

Secret values SHALL not be printed unless a dedicated secure command and policy explicitly permit it.

---

# `config set`

Canonical form:

```text
contextforge config set <key> <value>
```

The target configuration scope SHOULD be explicit:

```text
--project
--user
```

Configuration writes SHALL:

* Validate the key.
* Validate the value.
* Preserve file integrity.
* Avoid writing secrets accidentally.
* Use atomic replacement when practical.

---

# `config validate`

Canonical form:

```text
contextforge config validate
```

It SHOULD validate:

* Syntax.
* Known keys.
* Value types.
* Provider references.
* Model references when available.
* Security policy.
* Conflicting options.

---

# `diagnostics` Command

Canonical form:

```text
contextforge diagnostics
```

It SHOULD display:

* ContextForge version.
* Runtime version.
* Platform.
* Project resolution.
* Configuration validity.
* Provider health.
* Scanner availability.
* Index status.
* Writable metadata directories.
* Relevant diagnostic codes.

It SHALL not disclose secrets.

---

# `version` Command

The following SHALL be supported:

```text
contextforge --version
contextforge version
```

Output SHOULD include:

* CLI version.
* Core version.
* Specification compatibility version.
* Optional adapter versions.

Machine-readable version output SHOULD be available.

---

# Help System

Every command and subcommand SHALL support:

```text
--help
```

Help output SHALL include:

* Purpose.
* Usage.
* Arguments.
* Options.
* Safety implications.
* Examples.
* Exit-code behavior when relevant.

Help text SHALL not require internet access.

---

# Interactive Mode

Interactive behavior MAY be used for:

* Missing task input.
* Provider selection.
* Model selection.
* Patch review.
* Approval.
* Rejection reason.
* Conflict handling.

Interactive prompts SHALL not conceal defaults that alter security or project state.

---

# Non-Interactive Mode

The CLI SHALL support:

```text
--non-interactive
```

In non-interactive mode:

* Missing required input SHALL fail.
* Ambiguous provider selection SHALL fail.
* Approval SHALL require explicit proposal-bound authorization.
* Confirmation prompts SHALL not be displayed.
* Machine-readable output SHOULD be preferred.
* No unsafe default SHALL be assumed.

---

# Cancellation

The CLI SHOULD handle user interruption signals.

On cancellation, it SHALL:

* Request cancellation from the Application Orchestrator.
* Stop terminal progress rendering.
* Avoid reporting completion.
* Preserve partial execution diagnostics.
* Return the cancellation exit code.

Repeated interruption MAY force process termination according to platform conventions.

---

# Progress Reporting

Long-running operations MAY display progress.

Progress SHOULD identify high-level stages:

* Scanning.
* Indexing.
* Retrieving.
* Building context.
* Building prompt.
* Invoking provider.
* Validating response.
* Preparing proposal.
* Applying patch.

The CLI SHALL not fabricate progress percentages when progress cannot be measured reliably.

---

# Quiet Mode

`--quiet` SHALL suppress nonessential output.

It SHALL not suppress:

* Fatal errors.
* Security warnings affecting execution.
* Approval requirements.
* Machine-readable requested result.

---

# Verbose Mode

`--verbose` MAY display:

* Resolved project path.
* Configuration sources.
* Stage transitions.
* Candidate and context counts.
* Provider metadata.
* Timing information.
* Retry information.

It SHALL not display secrets or complete prompts by default.

---

# Debug Mode

`--debug` MAY expose:

* Internal stack traces.
* Detailed diagnostic context.
* Adapter error details.
* Serialization information.

Debug output SHALL still redact credentials and prohibited sensitive content.

Debug mode SHALL not weaken security policy.

---

# Color and Terminal Detection

Color output MAY be enabled when:

* Standard output is an interactive terminal.
* `NO_COLOR` is not set.
* `--no-color` is not supplied.

Color SHALL not be required to interpret output.

Machine-readable output SHALL not contain terminal color codes.

---

# Paging

Large human-readable output MAY use a pager.

Paging SHALL:

* Be disabled in non-interactive mode.
* Be disabled for machine-readable output.
* Respect explicit configuration.
* Avoid executing untrusted pager commands from project content.

---

# Diff Display

Patch review SHOULD support readable diffs.

Diff output MAY include:

* Line numbers.
* File headers.
* Hunk headers.
* Added and removed lines.
* Syntax-aware presentation when safe.

The CLI SHALL preserve the actual proposed patch content.

Presentation enhancements SHALL not modify proposal semantics.

---

# Sensitive Output

The CLI SHALL enforce display policy for:

* Secrets.
* Sensitive Context Items.
* Prompt previews.
* Provider responses.
* Patch content.
* Environment-derived values.

Sensitive content SHOULD be hidden by default in broad inspection commands.

Explicit secure reveal behavior MAY be added later.

---

# Diagnostics Model

The CLI SHALL display structured diagnostics produced by application and domain capabilities.

It SHALL preserve:

* Diagnostic code.
* Severity.
* Message.
* Related path or stage when permitted.
* Recoverability.
* Suggested action when available.

The CLI SHALL not replace diagnostic codes with vague prose.

---

# Diagnostic Severity

Canonical severities are:

* Info.
* Warning.
* Error.
* Critical.

Severity presentation SHALL remain consistent across commands.

---

# Error Presentation

For ordinary human-readable failures, the CLI SHOULD display:

1. Concise failure summary.
2. Diagnostic code.
3. Relevant project-relative path or stage.
4. Corrective action when available.
5. Debug guidance when appropriate.

Raw stack traces SHALL be hidden unless debug mode is active.

---

# Application Command Mapping

Each CLI operation SHALL map to an application-layer command or query.

Examples include:

```text
InitializeProject
GetProjectStatus
ScanProject
BuildProjectIndex
ExecuteTask
GetContextBundle
GetPromptPreview
ListProviders
CheckProviderHealth
GetPatchProposal
ApprovePatchProposal
RejectPatchProposal
ApplyPatchProposal
GetEffectiveConfiguration
ValidateConfiguration
```

The CLI SHALL not invoke domain services through ad hoc internal calls that bypass the application layer.

---

# Command and Query Separation

State-changing operations SHOULD be modeled as commands.

Read-only operations SHOULD be modeled as queries.

Queries SHALL not mutate project state.

Examples:

Commands:

* ScanProject.
* BuildProjectIndex.
* ExecuteTask.
* ApprovePatchProposal.
* RejectPatchProposal.
* ApplyPatchProposal.

Queries:

* GetProjectStatus.
* GetContextBundle.
* GetPromptPreview.
* ListProviders.
* GetPatchProposal.

---

# Execution Identity

Task executions SHALL have an Execution Identifier.

The CLI SHOULD display it after task submission.

Users SHOULD be able to reference prior executions:

```text
contextforge context show --execution <identifier>
contextforge patch list --execution <identifier>
```

Internal identifiers SHALL not replace understandable command output.

---

# Latest-Result Resolution

Commands MAY use the latest applicable execution or proposal when no identifier is supplied.

This behavior SHALL:

* Be deterministic.
* Be clearly displayed.
* Fail when multiple equally applicable results exist.
* Never approve or apply an ambiguous proposal.

Explicit identifiers are REQUIRED for non-interactive approval and application.

---

# Persistence Interaction

The CLI MAY access persisted execution references only through application services.

It SHALL not directly edit:

* Project Index files.
* Retrieval Results.
* Context Bundles.
* Inference Requests.
* Provider responses.
* Patch Proposals.
* Approval Records.

---

# Reproducibility

The CLI SHOULD support exporting enough execution metadata to reproduce a task attempt.

This MAY include:

* Task Specification.
* Project fingerprint.
* Configuration fingerprint.
* Index Identifier.
* Retrieval Identifier.
* Context Bundle Identifier.
* Prompt Template Version.
* Provider and model.
* Patch Proposal Identifier.

Secrets and sensitive content SHALL remain protected.

---

# Shell Completion

The CLI MAY provide shell completion for:

* Bash.
* Zsh.
* Fish.
* PowerShell.

Completion scripts SHALL not execute project code.

Dynamic provider or model completion SHOULD avoid expensive or networked operations unless explicitly invoked.

---

# Platform Support

The CLI SHOULD support:

* Linux.
* macOS.
* Windows.

Path presentation SHALL use normalized project-relative paths.

Platform-specific filesystem behavior SHALL not weaken project-boundary validation.

---

# Encoding

The CLI SHALL support UTF-8 input and output.

Invalid terminal encoding SHALL produce a clear diagnostic or safe replacement behavior.

Patch content SHALL preserve source encoding according to the application service and Patch Proposal metadata.

---

# Signal and Process Behavior

The CLI SHALL return control to the shell after:

* Success.
* Failure.
* Cancellation.
* Approval requirement.
* Rejection.
* Partial execution.

It SHALL not leave orphan provider streams or application locks when clean shutdown is possible.

---

# Locking

Project operations MAY require locks.

The CLI SHOULD display:

* Lock owner when available.
* Operation holding the lock.
* Lock creation time.
* Recovery guidance for stale locks.

The CLI SHALL not force-remove a lock without explicit authorization.

---

# Concurrent Executions

The CLI MAY allow concurrent read-only queries.

Concurrent state-changing operations SHALL respect application locking and project-state policy.

Two simultaneous patch applications to the same project SHALL not proceed without conflict control.

---

# Security Requirements

The CLI SHALL:

* Avoid executing provider-generated commands.
* Avoid evaluating project configuration as code.
* Avoid exposing secrets.
* Require explicit patch approval.
* Bind approval to an exact proposal.
* Respect project boundaries.
* Respect provider delivery policy.
* Avoid implicit remote fallback.
* Avoid unsafe shell interpolation.
* Avoid accepting project content as CLI configuration authority.
* Avoid direct project modification outside authorized services.
* Preserve security diagnostics.

---

# Shell Injection Resistance

Arguments, paths, task text, provider output, and project content SHALL be treated as data.

The CLI SHALL NOT construct shell commands through unsafe string interpolation.

When external processes are authorized by a separate capability, argument-vector invocation SHALL be preferred.

Provider-generated text SHALL never be executed as a shell command by the CLI.

---

# Path Safety

CLI-supplied paths SHALL be normalized and validated.

The CLI SHALL not assume that a path is safe because it came from the user.

Project paths, configuration paths, export paths, and approval files SHALL follow their applicable policies.

---

# Approval File

A future non-interactive approval file MAY contain:

* Proposal Identifier.
* Proposal fingerprint.
* Project fingerprint.
* Approval timestamp.
* Approving principal.
* Signature or integrity proof.

Plain text containing only `yes` or `approve` SHALL not be sufficient.

---

# Privacy Requirements

The CLI SHALL make remote inference visible.

Before first remote invocation in an interactive context, policy MAY require displaying:

* Provider.
* Model.
* Remote execution mode.
* Context size.
* Sensitive-content state.
* Data-retention warning when known.

User acknowledgement SHALL not override prohibited delivery policy.

---

# Logging

CLI logging SHOULD include:

* Command.
* Execution Identifier.
* Stage.
* Duration.
* Result status.
* Diagnostic codes.

Logs SHALL not include:

* Full task text by default.
* Full prompt content.
* Credentials.
* Sensitive Context Items.
* Full provider output.
* Unredacted configuration secrets.

---

# Telemetry

External telemetry SHALL be disabled by default in the MVP.

If telemetry is introduced later, it SHALL:

* Be explicit.
* Be configurable.
* Avoid project content.
* Avoid task content.
* Avoid prompt content.
* Avoid provider responses.
* Document collected fields.

---

# Performance Requirements

The CLI SHOULD add minimal overhead to domain operations.

It SHALL:

* Avoid loading entire persisted artifacts when summaries are sufficient.
* Stream large display output when practical.
* Avoid duplicate serialization.
* Avoid blocking progress rendering.
* Preserve responsive cancellation.
* Avoid unnecessary provider health checks during unrelated commands.

---

# Accessibility

Human-readable output SHOULD:

* Avoid relying only on color.
* Use clear language.
* Support screen-reader-friendly plain text.
* Avoid excessive animated output.
* Respect `--no-color`.
* Remain understandable when redirected to a file.

---

# Localization

The MVP MAY use English for command names and diagnostic codes.

Human-readable messages MAY support localization later.

Command names, configuration keys, diagnostic codes, and machine-readable field names SHOULD remain stable and language-neutral.

---

# Backward Compatibility

Published command names, option meanings, output schemas, and exit codes SHALL follow semantic versioning.

Breaking CLI changes SHALL require a major version change or a documented migration period.

Experimental commands SHALL be clearly marked.

---

# Deprecation

Deprecated commands or options SHOULD:

* Continue functioning for a defined period.
* Emit a warning.
* Identify the replacement.
* Avoid changing behavior silently.
* Be removed only in a compatible major release.

---

# Machine-Readable Schema Versioning

JSON output SHALL include a schema version.

Example:

```json
{
  "schema_version": "1.0",
  "status": "success",
  "data": {},
  "diagnostics": []
}
```

Breaking output-schema changes SHALL update the major schema version.

---

# Canonical Diagnostic Codes

The CLI SHOULD define at least:

| Code                                 | Meaning                                               |
| ------------------------------------ | ----------------------------------------------------- |
| `CLI_USAGE_INVALID`                  | Command-line usage is invalid                         |
| `CLI_COMMAND_UNKNOWN`                | Command is unknown                                    |
| `CLI_OPTION_INVALID`                 | An option is invalid                                  |
| `CLI_ARGUMENT_MISSING`               | A required argument is missing                        |
| `CLI_INPUT_EMPTY`                    | Required standard input or task input is empty        |
| `CLI_PROJECT_NOT_FOUND`              | Project root could not be resolved                    |
| `CLI_CONFIG_INVALID`                 | Effective configuration is invalid                    |
| `CLI_CONFIG_WRITE_FAILED`            | Configuration could not be written                    |
| `CLI_OUTPUT_FAILED`                  | Requested output could not be rendered                |
| `CLI_FORMAT_UNSUPPORTED`             | Output format is unsupported                          |
| `CLI_NON_INTERACTIVE_INPUT_REQUIRED` | Required input is unavailable in non-interactive mode |
| `CLI_APPROVAL_REQUIRED`              | Patch application requires approval                   |
| `CLI_APPROVAL_INVALID`               | Approval does not match the proposal                  |
| `CLI_PROPOSAL_AMBIGUOUS`             | Proposal selection is ambiguous                       |
| `CLI_PROPOSAL_NOT_FOUND`             | Requested Patch Proposal was not found                |
| `CLI_PROPOSAL_STALE`                 | Proposal project fingerprint is stale                 |
| `CLI_OPERATION_CANCELLED`            | Operation was cancelled                               |
| `CLI_LOCK_CONFLICT`                  | Another operation holds a conflicting lock            |
| `CLI_SENSITIVE_OUTPUT_REDACTED`      | Sensitive output was redacted                         |
| `CLI_INTERNAL_ERROR`                 | An unexpected CLI adapter failure occurred            |

Published diagnostic codes SHALL remain stable.

---

# Failure Model

The CLI SHALL distinguish:

* CLI usage failures.
* Configuration failures.
* Application failures.
* Domain validation failures.
* Provider failures.
* Approval failures.
* Application failures.
* Cancellation.
* Partial completion.

The CLI SHALL preserve underlying diagnostic codes.

It SHALL not collapse every failure into one generic error.

---

# Terminal Failures

Examples include:

* Invalid command usage.
* Project cannot be resolved.
* Configuration is invalid.
* Required non-interactive input is absent.
* Provider is unavailable with no authorized alternative.
* Patch Proposal is invalid.
* Approval is missing or mismatched.
* Proposal is stale.
* Patch application fails.
* Security policy rejects the operation.

Terminal failures SHALL return a nonzero exit code.

---

# Recoverable Conditions

Examples include:

* Index completed with warnings.
* Retrieval is incomplete but inspection is permitted.
* Optional provider usage metadata is unavailable.
* Prompt preview redacts sensitive content.
* Patch Proposal requires approval.
* Provider health is degraded.
* Optional output metadata cannot be displayed.

Recoverable conditions SHALL remain visible.

---

# Determinism

Given identical:

* CLI arguments.
* Standard input.
* Environment configuration.
* Project state.
* Effective configuration.
* Application service results.

The CLI SHOULD produce semantically equivalent output and the same exit code.

Terminal width and color capability MAY affect presentation but SHALL not affect semantics.

---

# Testability

The CLI SHALL be testable without real network access or real provider invocation.

Tests SHOULD inject:

* Mock application services.
* Mock provider results.
* Mock project states.
* Mock terminal capabilities.
* Mock standard input.
* Mock approval responses.

CLI tests SHALL not duplicate domain tests unnecessarily.

---

# Test Categories

The CLI SHALL be verified through:

* Command parsing tests.
* Global-option tests.
* Project-resolution tests.
* Configuration-precedence tests.
* Human-output snapshot tests.
* JSON-output schema tests.
* Standard-output and standard-error separation tests.
* Exit-code tests.
* Non-interactive behavior tests.
* Cancellation tests.
* Progress-rendering tests.
* Sensitive-output redaction tests.
* Context inspection tests.
* Prompt preview tests.
* Provider listing tests.
* Provider health tests.
* Patch review tests.
* Approval binding tests.
* Stale-proposal tests.
* Patch application delegation tests.
* Dry-run tests.
* Shell-injection resistance tests.
* Cross-platform path tests.
* UTF-8 tests.
* Lock-conflict tests.
* Backward-compatibility tests.

Mandatory tests SHALL not require internet access.

---

# Reference CLI Fixtures

The test suite SHOULD include:

* Empty project.
* Valid initialized project.
* Project without configuration.
* Invalid project configuration.
* Successful scan.
* Scan with warnings.
* Successful index.
* Index parser warnings.
* Analysis-only task.
* Valid patch task.
* Invalid provider response.
* Provider timeout.
* Remote provider rejected by policy.
* Prompt too large.
* Incomplete retrieval.
* Patch Proposal awaiting approval.
* Approved proposal.
* Rejected proposal.
* Stale proposal.
* Protected-file proposal.
* Dirty working tree.
* Non-interactive execution without approval.
* Non-interactive execution with exact proposal approval.
* JSON output.
* Quiet mode.
* Verbose mode.
* Debug mode.
* User cancellation.
* Concurrent project lock.
* Sensitive prompt preview.
* Windows path input.
* Unicode project path.

---

# Implementation Organization

The CLI adapter SHOULD be organized under:

```text
src/contextforge/cli/
```

Expected internal concepts MAY include:

```text
commands
arguments
rendering
formatters
prompts
progress
exit_codes
configuration
diagnostics
exceptions
```

The CLI SHALL depend on application ports and stable domain result models.

It SHALL NOT import concrete scanner, provider, patch parser, or filesystem adapter internals directly.

---

# Dependency Rules

The CLI MAY depend on:

* Application-layer commands and queries.
* Provider-independent domain models.
* Diagnostic models.
* Configuration interfaces.
* Terminal rendering libraries.

The CLI SHALL NOT contain dependencies pointing from Core modules back toward the CLI.

Core modules SHALL remain unaware of terminal concepts.

---

# Interaction with Application Orchestrator

The CLI SHALL use the Application Orchestrator for complete task execution.

The Orchestrator SHALL:

* Coordinate pipeline stages.
* Resolve stage dependencies.
* Enforce workflow policy.
* Manage Execution state.
* Route diagnostics.
* Enforce approval state.
* Delegate patch application.
* Return stable results.

The CLI SHALL only present and request those operations.

---

# Interaction with Scanner and Indexer

The CLI SHALL invoke scanning and indexing through application services.

It MAY display summaries and diagnostics.

It SHALL not:

* Traverse directories.
* Parse files.
* Build relationships.
* Write index storage directly.

---

# Interaction with Retriever and Context Builder

The CLI MAY inspect:

* Retrieval Result.
* Selection Rationales.
* Context Bundle.
* Context measurements.
* Coverage state.

It SHALL not modify candidate ranking, selection, or ordering.

---

# Interaction with Prompt Builder

The CLI MAY request:

* Prompt Preview.
* Prompt Measurements.
* Response Contract display.
* Template metadata.

It SHALL not concatenate prompt sections or alter context serialization.

---

# Interaction with Provider Interface

The CLI MAY select a configured provider or model through user input.

It SHALL not:

* Build provider API payloads.
* Handle authentication directly.
* Parse provider transport errors independently.
* Bypass delivery policy.
* Invoke provider SDKs.

---

# Interaction with Patch Engine

The CLI SHALL display Patch Proposals and validation results produced by the Patch Engine.

It SHALL not:

* Parse raw provider patches.
* Normalize paths.
* Resolve patch conflicts.
* Mark invalid changes as valid.
* Modify proposal content.

---

# Interaction with Patch Application

The CLI SHALL invoke an authorized patch application command.

It SHALL not write, rename, or delete project files directly.

Application results SHALL identify:

* Applied changes.
* Failed changes.
* Backup information.
* Rollback state.
* Updated Project State Fingerprint.
* Diagnostics.

---

# Observability

The CLI SHOULD expose enough information for users to understand:

* Which project is active.
* Which pipeline stage is running.
* Which provider and model are selected.
* Whether execution is local or remote.
* Which context was selected.
* Why context was selected.
* Whether context is incomplete.
* What patch is proposed.
* Whether the proposal is validated.
* Whether approval is required.
* Why an operation failed.
* Whether project state changed.

Observability SHALL not reveal secrets.

---

# Traceability

| Requirement Area      | CLI Responsibility                                             |
| --------------------- | -------------------------------------------------------------- |
| User interaction      | Expose ContextForge through stable terminal commands           |
| Safety                | Require proposal-bound approval before application             |
| Modularity            | Delegate all domain decisions to application and Core services |
| Transparency          | Display context, prompt, provider, and patch metadata          |
| Automation            | Provide non-interactive and JSON modes                         |
| Reliability           | Return stable exit codes and preserve diagnostics              |
| Security              | Redact secrets and avoid executing untrusted content           |
| Provider independence | Avoid provider-specific transport logic                        |
| Patch integrity       | Review and approve immutable Patch Proposals                   |
| Reproducibility       | Expose execution identifiers and fingerprints                  |

---

# Acceptance Criteria

## AC-CLI-001 — Executable Availability

The application SHALL expose the canonical `contextforge` executable.

---

## AC-CLI-002 — Help Availability

Every command and subcommand SHALL support help output.

---

## AC-CLI-003 — Project Resolution

The CLI SHALL deterministically resolve the active project or fail with a specific diagnostic.

---

## AC-CLI-004 — Configuration Precedence

Effective configuration SHALL follow the documented precedence order.

---

## AC-CLI-005 — Domain Delegation

The CLI SHALL invoke application-layer commands and SHALL not reimplement Core domain logic.

---

## AC-CLI-006 — Scan Delegation

The `scan` command SHALL request scanning through the application layer.

---

## AC-CLI-007 — Index Delegation

The `index` command SHALL request indexing through the application layer.

---

## AC-CLI-008 — Task Execution

The `run` command SHALL execute the pipeline through the Application Orchestrator.

---

## AC-CLI-009 — Original Task Preservation

The CLI SHALL preserve user task input without semantic rewriting.

---

## AC-CLI-010 — Context Inspection

The CLI SHALL provide a way to inspect selected Context Items and Selection Rationales.

---

## AC-CLI-011 — Prompt Inspection

The CLI SHALL provide a safe prompt preview and request-size inspection.

---

## AC-CLI-012 — Provider Inspection

The CLI SHALL provide provider listing and health inspection without transmitting project content.

---

## AC-CLI-013 — Patch Review

The CLI SHALL display validated Patch Proposal content before approval.

---

## AC-CLI-014 — Explicit Approval

No Patch Proposal SHALL be applied without explicit proposal-bound approval.

---

## AC-CLI-015 — Non-Interactive Safety

Non-interactive patch application SHALL require exact proposal-bound authorization.

---

## AC-CLI-016 — Stale Proposal Rejection

A proposal whose Project State Fingerprint no longer matches SHALL not be applied automatically.

---

## AC-CLI-017 — Application Delegation

The CLI SHALL not modify project files directly.

---

## AC-CLI-018 — Machine-Readable Output

The CLI SHALL support valid versioned JSON output.

---

## AC-CLI-019 — Output Separation

In machine-readable mode, requested result data SHALL remain parseable on standard output.

---

## AC-CLI-020 — Stable Exit Codes

The CLI SHALL return documented stable exit codes.

---

## AC-CLI-021 — Secret Protection

CLI output, diagnostics, logs, and configuration inspection SHALL not expose credentials.

---

## AC-CLI-022 — Cancellation

User cancellation SHALL not be reported as successful completion.

---

## AC-CLI-023 — No Shell Execution

The CLI SHALL never execute provider-generated text as shell commands.

---

## AC-CLI-024 — Dry Run

State-changing commands supporting dry-run SHALL not modify project files.

---

## AC-CLI-025 — Diagnostic Preservation

The CLI SHALL preserve structured diagnostic codes produced by underlying capabilities.

---

## AC-CLI-026 — Cross-Platform Paths

Project-relative path presentation and validation SHALL work consistently across supported platforms.

---

## AC-CLI-027 — Sensitive Preview Policy

Context and prompt previews SHALL respect sensitive-content display policy.

---

## AC-CLI-028 — Approval Traceability

Every successful approval SHALL produce an Approval Record bound to the proposal and project fingerprints.

---

## AC-CLI-029 — Partial Application Visibility

A partial patch application SHALL return a nonzero exit code and identify affected changes.

---

## AC-CLI-030 — MVP Completeness

The MVP CLI SHALL expose the complete pipeline from project scanning through Patch Proposal review and explicit application authorization.

---

# Validation Criteria

This specification SHALL be considered satisfied when:

* Users can initialize and inspect a ContextForge project.
* Users can scan and index a project.
* Users can submit a task.
* Users can inspect retrieved context.
* Users can inspect the generated prompt.
* Users can select and inspect providers.
* Users can receive analysis or a validated Patch Proposal.
* Users can review proposed file changes.
* No patch can be applied without explicit proposal-bound approval.
* Non-interactive execution remains safe and scriptable.
* JSON output and exit codes remain stable.
* The CLI contains no duplicated domain logic.
* The CLI never modifies project files directly.
* All operations preserve diagnostics, traceability, and project-state identity.

---

# Completion Statement

The ContextForge CLI is complete when a user can safely and predictably operate the full ContextForge workflow from a terminal—from project discovery and indexing through context inspection, inference execution, Patch Proposal review, explicit approval, and authorized application—without the CLI containing domain logic, provider transport logic, patch parsing logic, or implicit authorization.
