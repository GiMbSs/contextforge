# Provider Interface Specification

Document ID: CF-010
Status: Draft
Version: 0.1.0
Owner: ContextForge Architecture Board
Language: English
Audience:

* Engineers
* Contributors
* Product Owners
* AI Agents
* Provider Adapter Maintainers

Normative: Yes

Depends On:

* CF-000 — AI-Native Specification
* CF-001 — Vision
* CF-002 — Product Requirements Document
* CF-003 — System Architecture
* CF-004 — Domain Model
* CF-009 — Prompt Builder Specification

Related ADRs:

* ADR-0001 — Context-First Architecture
* ADR-0002 — Hexagonal Architecture
* ADR-0003 — Dependency Rule
* ADR-0004 — Feature-Based Module Organization

---

# Abstract

This document defines the Provider Interface capability of ContextForge.

The Provider Interface establishes a provider-independent contract for executing an immutable Inference Request through an external inference implementation.

It isolates the ContextForge Core from:

* Provider SDKs.
* HTTP APIs.
* Local inference servers.
* Authentication mechanisms.
* Transport protocols.
* Model-specific request formats.
* Provider-specific response formats.
* Provider-specific failure semantics.

The Provider Interface SHALL NOT:

* Select project context.
* Build prompts.
* Modify task instructions.
* Interpret task relevance.
* Validate source-code patches semantically.
* Apply project changes.
* Execute arbitrary tools on behalf of the inference model.
* Permit a provider to alter ContextForge authorization boundaries.

---

# Purpose

The Provider Interface enables ContextForge to execute inference through interchangeable local or remote providers without coupling Core domain logic to a specific model, API, SDK, or transport.

Its primary responsibilities are:

* Define the Provider Port.
* Define provider capabilities.
* Define provider configuration.
* Translate an Inference Request through adapters.
* Invoke inference.
* Normalize provider responses.
* Normalize provider failures.
* Capture usage and execution metadata.
* Preserve request and response correlation.
* Enforce provider-level safety and delivery policy.
* Return an immutable Inference Response.

---

# Architectural Responsibility

The Provider Interface answers:

> How is an authorized Inference Request executed by an inference provider?

It SHALL NOT answer:

* Which project artifacts are relevant?
* How the Context Bundle is constructed?
* How the prompt is authored?
* Whether the provider output is correct?
* Whether a patch is safe to apply?
* Whether a proposed change is approved?

Provider selection policy belongs to the Application Orchestrator.

Prompt construction belongs to the Prompt Builder.

Response validation and patch interpretation belong to the Patch Engine.

---

# Scope

The Provider Interface SHALL support:

* Local inference providers.
* Remote inference providers.
* Text-based inference.
* Structured-response inference.
* Provider capability discovery.
* Request translation.
* Response normalization.
* Timeout handling.
* Cancellation.
* Retry policy integration.
* Usage accounting.
* Provider diagnostics.
* Deterministic configuration resolution.
* Model identification.
* Request correlation.
* Provider health checks.
* Optional streaming abstraction.

The MVP SHALL support at least one local provider adapter.

The recommended initial adapter is an Ollama-compatible local provider.

---

# Out of Scope

The Provider Interface SHALL NOT:

* Build or rank context.
* Generate prompts.
* Parse project files.
* Validate source-code syntax as part of provider execution.
* Apply patches.
* Run project tests.
* Execute provider-generated shell commands.
* Implement autonomous tool loops.
* Maintain conversation memory.
* Orchestrate multiple agents.
* Train or fine-tune models.
* Download models automatically without explicit authorization.
* Manage GPU drivers.
* Manage provider infrastructure.
* Guarantee provider output correctness.
* Automatically send sensitive context to remote systems.
* Automatically switch to a remote provider when a local provider fails.

---

# Capability Boundary

The Provider Interface consumes:

* Inference Request.
* Provider Selection.
* Provider Configuration.
* Provider Capability Profile.
* Provider Delivery Policy.
* Execution correlation metadata.
* Cancellation signal when supported.

The Provider Interface produces:

* Inference Response.
* Provider Metadata.
* Usage Metadata.
* Provider Diagnostics.
* Execution Measurements.
* Provider Failure when unsuccessful.

---

# Primary Contract

The Provider Port SHALL expose a logical operation equivalent to:

```text
infer(
    inference_request,
    provider_configuration,
    execution_context
) -> Inference Response
```

It MAY additionally expose:

```text
get_capabilities() -> Provider Capability Profile
health_check() -> Provider Health
cancel(request_identifier) -> Cancellation Result
stream(...) -> Provider Response Stream
```

The Core SHALL depend only on the Provider Port.

Provider Adapters SHALL implement the port.

---

# Provider Port

The Provider Port SHALL define provider-independent inference behavior.

The contract SHALL:

* Accept an immutable Inference Request.
* Preserve request identity.
* Enforce provider configuration.
* Return one normalized Inference Response.
* Translate provider-specific failures.
* Avoid leaking provider SDK types into the Core.
* Avoid modifying task or context semantics.
* Preserve correlation metadata.

---

# Inputs

## Inference Request

The Provider Interface SHALL accept the immutable Inference Request produced by the Prompt Builder.

The request SHALL contain:

* Inference Request Identifier.
* Task Identifier.
* Context Bundle Identifier.
* Logical prompt sections.
* Expected Response Contract.
* Required provider capabilities.
* Security metadata.
* Size measurements.
* Correlation metadata.

The adapter SHALL reject a request that is structurally invalid or incompatible with the selected provider.

---

## Provider Selection

Provider Selection SHALL identify:

* Provider Identifier.
* Adapter Identifier.
* Model Identifier.
* Execution Mode.
* Optional endpoint profile.
* Optional fallback policy reference.

Execution Mode SHALL distinguish at least:

* Local.
* Remote.

The Provider Interface SHALL NOT infer that a provider is local solely from its hostname.

Execution Mode SHALL be explicit configuration.

---

## Provider Configuration

Provider Configuration MAY define:

* Provider Identifier.
* Adapter Identifier.
* Endpoint.
* Model Identifier.
* Authentication reference.
* Connection timeout.
* Request timeout.
* Idle timeout.
* Retry policy.
* Maximum input size.
* Maximum output size.
* Temperature.
* Top-p.
* Seed.
* Stop sequences.
* Structured-output mode.
* Streaming mode.
* TLS behavior.
* Proxy behavior.
* Additional provider options.

Configuration values that affect inference semantics SHALL be preserved in Provider Metadata.

Secrets SHALL be referenced through a secure configuration mechanism rather than embedded in domain objects when practical.

---

## Execution Context

Execution Context MAY contain:

* Execution Identifier.
* Stage Identifier.
* Correlation Identifier.
* Cancellation signal.
* Deadline.
* Trace metadata.
* User authorization metadata.
* Provider-delivery authorization.
* Retry attempt number.

Execution Context SHALL NOT contain project content that is absent from the Inference Request.

---

# Outputs

## Inference Response

A successful invocation SHALL return one immutable Inference Response containing:

* Inference Response Identifier.
* Inference Request Identifier.
* Task Identifier.
* Provider Identifier.
* Adapter Identifier.
* Model Identifier.
* Response content.
* Response format.
* Provider Metadata.
* Usage Metadata.
* Execution Measurements.
* Finish state.
* Response diagnostics.
* Creation timestamp.

It MAY contain:

* Structured response object.
* Raw provider response reference.
* Provider request identifier.
* Model revision.
* Safety classification.
* Stop reason.
* Partial-output status.
* Streaming aggregation metadata.

---

## Response Content

Response Content SHALL preserve the provider's returned semantic content.

It MAY be represented as:

* Text.
* Structured object.
* Structured text.
* Patch envelope.
* Analysis envelope.
* Insufficient-context envelope.

The Provider Adapter MAY normalize transport encoding.

It SHALL NOT silently rewrite substantive output.

---

## Response Format

Canonical response formats MAY include:

* Plain Text.
* JSON Text.
* Structured Object.
* Patch Envelope.
* Analysis Envelope.
* Unknown.

The response format SHALL describe representation, not correctness.

A response marked as JSON is not necessarily valid against the Expected Response Contract.

Contract validation belongs to a later validation capability.

---

# Provider Metadata

Provider Metadata SHALL include:

* Provider Identifier.
* Adapter Identifier.
* Adapter Version.
* Model Identifier.
* Execution Mode.
* Provider request identifier when available.
* Invocation timestamp.
* Completion timestamp.
* Effective inference options.
* Capability profile identifier.
* Retry attempt count.

It MAY include:

* Model revision.
* Provider endpoint profile.
* Server version.
* Quantization.
* Device information.
* Backend information.
* Provider-specific finish reason.

Sensitive endpoint credentials SHALL NOT be included.

---

# Usage Metadata

Usage Metadata MAY include:

* Input token count.
* Output token count.
* Total token count.
* Prompt evaluation duration.
* Generation duration.
* Queue duration.
* Tokens per second.
* Input bytes.
* Output bytes.
* Estimated monetary cost.
* Cache usage.
* Context-window utilization.

Unavailable fields SHALL remain absent or explicitly unknown.

The adapter SHALL NOT fabricate usage values.

Estimated values SHALL be marked as estimates.

---

# Execution Measurements

Execution Measurements SHOULD include:

* Total invocation duration.
* Connection duration.
* Request serialization duration.
* Provider processing duration.
* Response deserialization duration.
* Retry count.
* Stream time to first item when applicable.
* Stream completion duration when applicable.

Measurements SHALL not alter the response content.

---

# Finish State

An Inference Response SHALL have one finish state:

* Completed.
* Completed with warnings.
* Partial.
* Cancelled.
* Timed Out.
* Failed.

A completed transport operation does not imply a valid response contract.

A partial response SHALL preserve the partial content and the reason for incompleteness.

---

# Provider Capability Profile

A Provider Capability Profile SHALL describe the capabilities of one adapter and provider configuration.

It SHALL include:

* Capability Profile Identifier.
* Provider Identifier.
* Adapter Identifier.
* Adapter Version.
* Supported request modes.
* Supported response modes.
* Maximum input size when known.
* Maximum output size when known.
* System-role support.
* Multiple-message support.
* Structured-output support.
* JSON-schema support.
* Streaming support.
* Cancellation support.
* Seed support.
* Tool-call support.
* Local or remote execution classification.

It MAY include:

* Supported media types.
* Supported model families.
* Native tokenization support.
* Context caching support.
* Batch support.
* Deterministic-generation support.
* Health-check support.

---

# Capability Validation

Before invocation, the Provider Adapter SHALL validate that the selected provider supports all mandatory request requirements.

Examples include:

* Required message-role representation.
* Required structured-output mode.
* Required input size.
* Required output size.
* Required local execution.
* Required cancellation support.
* Required deterministic seed behavior.

Missing mandatory capability SHALL prevent invocation.

Missing optional capability MAY produce a warning and documented adaptation.

---

# Capability Discovery

Capabilities MAY be obtained through:

* Static adapter declaration.
* Provider metadata endpoint.
* Local server introspection.
* Model registry.
* Explicit configuration.
* Cached capability profile.

Dynamically discovered capability data SHALL be validated and versioned when practical.

A capability profile SHALL not be trusted solely because the provider claims support.

Adapter-level compatibility tests SHOULD verify important capabilities.

---

# Provider Identifier

A Provider Identifier SHALL identify the inference service family or configured provider instance.

Examples MAY include:

* `ollama-local`
* `openai-remote`
* `anthropic-remote`
* `custom-http`
* `mock-provider`

Provider identifiers SHALL be stable within one ContextForge installation.

They SHALL not contain secrets.

---

# Adapter Identifier

An Adapter Identifier SHALL identify the implementation translating between the Provider Port and a concrete provider protocol.

Examples MAY include:

* `ollama-http`
* `openai-responses`
* `anthropic-messages`
* `mock-deterministic`

Adapter identity SHALL be distinct from model identity.

---

# Model Identifier

A Model Identifier SHALL identify the configured inference model.

Examples MAY include:

* Model name.
* Model tag.
* Model version.
* Deployment name.
* Endpoint-specific model alias.

The adapter SHALL preserve the model identifier actually used when available.

A requested model and an effective model SHALL be distinguished when the provider substitutes models.

---

# Local Provider

A Local Provider executes inference within an explicitly authorized local environment.

Local classification MAY affect:

* Sensitive-content eligibility.
* Privacy policy.
* Network policy.
* Authentication policy.
* Cost accounting.
* Availability assumptions.

A local provider SHALL NOT automatically be treated as trusted.

Local provider output remains untrusted external computation.

---

# Remote Provider

A Remote Provider transmits the Inference Request outside the authorized local execution boundary.

Before remote invocation, the Provider Interface SHALL verify:

* Remote delivery is authorized.
* Context sensitivity policy permits transmission.
* Endpoint policy permits transmission.
* Authentication configuration is available.
* TLS policy is satisfied.
* Request size is supported.

A prohibited remote request SHALL fail before transmission.

---

# Delivery Policy

Provider Delivery Policy SHALL determine whether an Inference Request may be delivered to a selected provider.

Policy MAY consider:

* Local or remote execution mode.
* Sensitive Context Items.
* Project classification.
* User authorization.
* Provider allowlist.
* Geographic or organizational restrictions.
* Endpoint security.
* Model policy.
* Data-retention policy.
* Request logging behavior.

Delivery Policy SHALL be evaluated before network transmission.

---

# Provider Selection

Provider selection belongs to the Application Orchestrator or an explicit Provider Selection Service.

Selection MAY consider:

* User choice.
* Required capabilities.
* Locality requirement.
* Context size.
* Model availability.
* Cost policy.
* Latency policy.
* Privacy policy.
* Project configuration.
* Operation Type.

The Provider Adapter SHALL NOT select itself as a fallback without orchestration authorization.

---

# Fallback Policy

Fallback between providers MAY be supported.

Fallback SHALL:

* Be explicitly configured.
* Preserve user authorization.
* Re-evaluate delivery policy.
* Re-evaluate capabilities.
* Preserve request semantics.
* Record each attempted provider.
* Avoid sending sensitive content to a less trusted provider.
* Produce diagnostics.

Automatic local-to-remote fallback SHOULD be disabled by default.

---

# Request Translation

The Provider Adapter SHALL translate the Core Inference Request into a provider-specific request payload.

Translation MAY include:

* Mapping logical message roles.
* Flattening prompt sections.
* Mapping structured-output schema.
* Mapping output limits.
* Mapping sampling options.
* Mapping stop sequences.
* Mapping model identifiers.
* Applying authentication.
* Applying endpoint configuration.

Translation SHALL preserve:

* Instruction hierarchy.
* Context ordering.
* Context boundaries.
* Expected Response Contract.
* Task semantics.
* Security metadata requirements.

---

# Translation Restrictions

The Provider Adapter SHALL NOT:

* Add project-derived content.
* Remove mandatory prompt sections.
* Modify the Original Instruction.
* Re-rank Context Items.
* Expand context.
* Weaken security instructions.
* Change permitted patch paths.
* Replace the Expected Response Contract.
* Add provider marketing or unrelated instructions.
* Add hidden tools or autonomous capabilities.

---

# Message Mapping

When a provider supports system and user messages, the adapter SHOULD preserve the Prompt Builder logical role mapping.

When a provider supports only one prompt string, the adapter MAY flatten sections deterministically.

Flattening SHALL preserve:

* Section order.
* Explicit labels.
* Context delimiters.
* Response Contract.
* Instruction hierarchy.

---

# Structured Output Mapping

When a provider supports structured output, the adapter MAY map the Expected Response Contract into:

* JSON schema.
* Provider-native structured-output configuration.
* Grammar constraints.
* Response format settings.

The adapter SHALL preserve the provider-neutral contract as authoritative.

Provider-native constraints SHALL not silently reduce required fields.

---

# Sampling Parameters

Sampling parameters MAY include:

* Temperature.
* Top-p.
* Top-k.
* Seed.
* Repetition penalty.
* Frequency penalty.
* Presence penalty.

Unsupported parameters SHALL:

* Be omitted when optional.
* Produce a warning when requested.
* Cause failure when mandatory.

The adapter SHALL report effective parameters when available.

---

# Deterministic Inference

ContextForge MAY request deterministic or low-variance inference.

A deterministic request MAY require:

* Fixed seed.
* Temperature zero or equivalent.
* Stable model revision.
* Stable adapter version.
* Stable prompt.
* Provider support.

The Provider Interface SHALL NOT guarantee bit-identical output unless the provider explicitly guarantees it and tests confirm it.

Deterministic intent and actual determinism SHALL remain distinct.

---

# Input Size Validation

Before invocation, the adapter SHALL validate that the request fits the effective provider input limit.

Effective limit MAY depend on:

* Model context window.
* Provider API limit.
* Structured-output overhead.
* Reserved output capacity.
* Provider-specific tokenization.

The adapter SHALL not silently truncate the Inference Request.

---

# Output Limit

The adapter SHOULD configure an output limit appropriate for the Expected Response Contract.

The limit SHALL be sufficient for the expected patch or analysis when practical.

If the provider cannot support the required output size, invocation SHALL fail before execution when determinable.

---

# Authentication

Remote Provider Adapters MAY require authentication.

Authentication SHALL:

* Be obtained through a secure configuration source.
* Avoid embedding credentials in domain objects.
* Avoid logging credentials.
* Avoid returning credentials in diagnostics.
* Support rotation without Core changes.

Authentication failure SHALL be normalized as a Provider Failure.

---

# Transport Security

Remote provider transport SHOULD require TLS.

An adapter SHALL reject insecure transport when policy prohibits it.

Certificate validation SHALL be enabled by default.

Disabling certificate validation SHALL require explicit configuration and SHOULD produce a high-severity warning.

---

# Network Policy

The Provider Interface SHALL respect network policy.

Policy MAY restrict:

* Remote endpoints.
* Ports.
* Proxy use.
* Redirects.
* DNS resolution.
* Private-network destinations.
* Public-network destinations.
* Provider allowlists.
* Provider deny lists.

Unexpected redirects SHOULD be rejected unless explicitly authorized.

---

# Endpoint Validation

Before remote invocation, an adapter SHOULD validate:

* Endpoint scheme.
* Endpoint host.
* Endpoint port.
* Allowlist compliance.
* Redirect policy.
* TLS requirement.
* Authentication compatibility.

Endpoint configuration SHALL not be accepted from untrusted project content.

---

# Invocation

Provider invocation SHALL:

1. Validate the Inference Request.
2. Validate Provider Configuration.
3. Validate capabilities.
4. Validate delivery policy.
5. Translate the request.
6. Start execution measurements.
7. Invoke the provider.
8. Receive the provider response.
9. Normalize the response.
10. Record usage and metadata.
11. Finalize the immutable Inference Response.

---

# Timeout Model

The Provider Interface SHOULD distinguish:

* Connection timeout.
* Request timeout.
* Idle timeout.
* Overall deadline.

Timeout behavior SHALL be deterministic and configurable.

A timeout SHALL produce a normalized failure or partial response according to the provider state.

---

# Cancellation

Cancellation MAY be supported.

When supported, the adapter SHALL:

* Accept a cancellation signal.
* Stop consuming provider output.
* Attempt provider-side cancellation when available.
* Avoid treating cancelled output as complete.
* Preserve partial output when policy allows.
* Return cancellation metadata.

Cancellation support SHALL be declared in the Capability Profile.

---

# Retry Policy

Retry behavior MAY be supported for transient provider failures.

Retry policy SHALL define:

* Maximum attempts.
* Initial delay.
* Maximum delay.
* Backoff strategy.
* Retryable failure categories.
* Non-retryable failure categories.
* Jitter policy.
* Overall deadline interaction.

Retries SHALL preserve the same Inference Request semantics.

---

# Retry Safety

The Provider Interface SHALL NOT retry automatically when:

* Delivery authorization may have changed.
* The request was partially accepted with uncertain execution state and duplication is unsafe.
* The failure is authentication-related.
* The failure is a permanent capability mismatch.
* The request is invalid.
* The provider rejected content by policy.
* The user cancelled execution.

Inference is generally idempotent from ContextForge's project-state perspective because providers cannot apply patches directly.

However, usage cost and provider logging MAY be duplicated.

---

# Retry Metadata

Every retry attempt SHALL record:

* Attempt number.
* Provider Identifier.
* Model Identifier.
* Start and completion time.
* Failure category.
* Retry decision.

The final Inference Response or Provider Failure SHALL summarize all attempts.

---

# Streaming

Streaming MAY be supported.

The Core streaming abstraction SHOULD expose normalized events such as:

* Stream Started.
* Content Delta.
* Structured Data Delta.
* Usage Update.
* Provider Warning.
* Stream Completed.
* Stream Failed.
* Stream Cancelled.

Provider-specific event types SHALL remain inside the adapter.

---

# Streaming Semantics

Streaming SHALL NOT change response-contract requirements.

Partial chunks SHALL not be considered valid final responses.

The adapter SHALL aggregate stream content into one final Inference Response when completion succeeds.

A stream failure MAY return partial output when policy permits.

---

# Time to First Token

For streaming providers, the adapter MAY measure time to first content event.

This measurement SHALL not be fabricated when unavailable.

---

# Provider Response Normalization

The adapter SHALL normalize provider output into the Core Inference Response.

Normalization MAY include:

* Text extraction.
* Structured-object extraction.
* Usage extraction.
* Finish-reason mapping.
* Model identifier extraction.
* Provider request identifier extraction.
* Safety metadata extraction.
* Stream aggregation.

Normalization SHALL not perform patch validation.

---

# Raw Provider Response

A raw provider response MAY be retained through an adapter-owned reference for debugging.

Raw response retention SHALL be optional.

It SHALL consider:

* Sensitive context.
* Provider-returned sensitive data.
* Storage policy.
* Retention policy.
* Access control.
* Debug mode.
* Data minimization.

The Core SHALL not require raw provider SDK objects.

---

# Response Correlation

Every response SHALL correlate to exactly one Inference Request.

The adapter SHALL preserve:

* Inference Request Identifier.
* Task Identifier.
* Execution Identifier when supplied.
* Provider request identifier when available.

A response that cannot be correlated SHALL be rejected.

---

# Provider Finish Reasons

Provider-specific finish reasons SHALL be mapped to normalized categories such as:

* Natural Completion.
* Output Limit Reached.
* Stop Sequence.
* Content Filter.
* Tool Call Requested.
* Provider Cancellation.
* Client Cancellation.
* Timeout.
* Provider Error.
* Unknown.

The original provider finish reason MAY be preserved in Provider Metadata.

---

# Tool Calls

Provider-native tool calls are outside the initial MVP.

If a provider returns a tool call unexpectedly:

* The adapter SHALL NOT execute it.
* The response SHALL be marked incomplete or unsupported.
* A diagnostic SHALL be produced.
* Tool arguments SHALL be treated as untrusted provider output.

Future tool support SHALL require a separate specification.

---

# Content Filters

A provider MAY reject or truncate content through a safety or content filter.

The adapter SHALL:

* Preserve the provider's normalized filter state.
* Avoid fabricating omitted content.
* Mark the response incomplete or failed.
* Produce a diagnostic.
* Preserve provider metadata when allowed.

Provider content filtering SHALL not alter ContextForge security policy.

---

# Provider Health

The Provider Interface MAY expose a Provider Health contract.

Canonical health states are:

* Healthy.
* Degraded.
* Unavailable.
* Misconfigured.
* Unknown.

Health information MAY include:

* Connectivity.
* Authentication state.
* Model availability.
* Capability availability.
* Server version.
* Recent error state.

Health checks SHALL avoid transmitting project content.

---

# Model Availability

A provider adapter MAY validate model availability before invocation.

Model availability checks SHOULD distinguish:

* Model available.
* Model unavailable.
* Model downloading.
* Model access denied.
* Model identifier unknown.
* Availability unknown.

Automatic model download SHALL require explicit authorization.

---

# Local Model Management

Model installation, download, deletion, and update are outside the Provider Port inference contract.

A local provider integration MAY expose separate administrative capabilities in the future.

Inference invocation SHALL not implicitly install or replace a model.

---

# Provider Failure

A failed provider operation SHALL return or raise a normalized Provider Failure.

A Provider Failure SHALL contain:

* Failure Identifier.
* Inference Request Identifier.
* Provider Identifier.
* Adapter Identifier.
* Model Identifier when known.
* Failure category.
* Message.
* Retryability.
* Attempt metadata.
* Diagnostics.
* Timestamp.

It MAY contain:

* Provider status code.
* Provider error code.
* Sanitized provider message.
* Partial output reference.
* Provider request identifier.

---

# Failure Categories

Canonical Provider Failure categories SHALL include:

* Configuration Invalid.
* Capability Missing.
* Delivery Prohibited.
* Authentication Failed.
* Authorization Failed.
* Endpoint Invalid.
* Connection Failed.
* Timeout.
* Rate Limited.
* Provider Unavailable.
* Model Unavailable.
* Input Too Large.
* Output Limit Invalid.
* Request Rejected.
* Content Filtered.
* Response Invalid.
* Stream Interrupted.
* Cancelled.
* Internal Adapter Error.
* Unknown Provider Error.

---

# Retryability

Retryability SHALL be explicit.

Typical retryable failures MAY include:

* Temporary connection failure.
* Rate limiting with retry guidance.
* Provider unavailable.
* Temporary timeout.
* Interrupted stream.

Typical non-retryable failures MAY include:

* Invalid configuration.
* Invalid authentication.
* Delivery prohibited.
* Missing mandatory capability.
* Input too large.
* Unsupported model.
* Invalid request.
* Security-policy rejection.

Retryability remains adapter- and policy-dependent.

---

# Error Sanitization

Provider errors MAY contain:

* Endpoint URLs.
* Request payloads.
* Credentials.
* Project content.
* Provider internals.
* Stack traces.

The adapter SHALL sanitize errors before exposing them to ordinary diagnostics.

Sensitive raw errors MAY be retained only under explicit secure debug policy.

---

# Diagnostics

The Provider Interface SHALL produce structured diagnostics.

Each diagnostic SHALL include:

* Diagnostic code.
* Severity.
* Message.
* Provider Identifier when applicable.
* Adapter Identifier when applicable.
* Inference Request Identifier when applicable.
* Retryability indication.
* Recoverability indication.

Diagnostics SHALL not expose credentials or full prompt content.

---

# Canonical Diagnostic Codes

The MVP SHOULD define at least:

| Code                                | Meaning                                          |
| ----------------------------------- | ------------------------------------------------ |
| `PROVIDER_REQUEST_INVALID`          | Inference Request is invalid                     |
| `PROVIDER_CONFIG_INVALID`           | Provider Configuration is invalid                |
| `PROVIDER_NOT_FOUND`                | Requested provider is unavailable                |
| `PROVIDER_ADAPTER_NOT_FOUND`        | Requested adapter is unavailable                 |
| `PROVIDER_MODEL_NOT_FOUND`          | Requested model is unavailable                   |
| `PROVIDER_CAPABILITY_MISSING`       | Required capability is unsupported               |
| `PROVIDER_DELIVERY_PROHIBITED`      | Delivery policy rejected the provider            |
| `PROVIDER_AUTH_FAILED`              | Authentication failed                            |
| `PROVIDER_AUTHORIZATION_FAILED`     | Provider authorization failed                    |
| `PROVIDER_ENDPOINT_INVALID`         | Endpoint configuration is invalid                |
| `PROVIDER_CONNECTION_FAILED`        | Connection to provider failed                    |
| `PROVIDER_TIMEOUT`                  | Provider invocation timed out                    |
| `PROVIDER_RATE_LIMITED`             | Provider rate limit was reached                  |
| `PROVIDER_UNAVAILABLE`              | Provider is temporarily unavailable              |
| `PROVIDER_INPUT_TOO_LARGE`          | Request exceeds provider input capacity          |
| `PROVIDER_OUTPUT_LIMIT_UNSUPPORTED` | Required output size is unsupported              |
| `PROVIDER_REQUEST_REJECTED`         | Provider rejected the request                    |
| `PROVIDER_CONTENT_FILTERED`         | Provider filtered request or response content    |
| `PROVIDER_RESPONSE_EMPTY`           | Provider returned no usable response content     |
| `PROVIDER_RESPONSE_UNSUPPORTED`     | Provider response type is unsupported            |
| `PROVIDER_STREAM_INTERRUPTED`       | Streaming response ended unexpectedly            |
| `PROVIDER_CANCELLED`                | Invocation was cancelled                         |
| `PROVIDER_RETRY_SCHEDULED`          | A retry was authorized                           |
| `PROVIDER_RETRY_EXHAUSTED`          | All permitted retry attempts failed              |
| `PROVIDER_USAGE_UNAVAILABLE`        | Usage metadata was unavailable                   |
| `PROVIDER_RAW_RESPONSE_REDACTED`    | Raw response was not retained for policy reasons |
| `PROVIDER_INTERNAL_ERROR`           | Adapter encountered an internal failure          |

Published diagnostic codes SHALL remain stable.

---

# Failure Model

The Provider Interface SHALL distinguish terminal failures from recoverable conditions.

## Terminal Failures

Examples include:

* Invalid Inference Request.
* Invalid Provider Configuration.
* Provider Adapter unavailable.
* Missing mandatory capability.
* Delivery prohibited.
* Authentication failure.
* Input size incompatibility.
* Invalid endpoint.
* Unsupported model with no authorized alternative.
* Response cannot be correlated.
* Internal adapter consistency failure.

A terminal failure SHALL prevent production of a successful Inference Response.

---

## Recoverable Conditions

Examples include:

* Temporary provider unavailability.
* Rate limiting.
* Transient connection failure.
* Retryable timeout.
* Optional usage metadata unavailable.
* Optional provider metadata unavailable.
* Exact token accounting unavailable.
* Provider completed with warnings.
* Partial response retained after interruption.

Recoverable conditions SHALL be represented through diagnostics and response status.

---

# Response Validation Boundary

The Provider Interface SHALL perform transport-level and representation-level validation.

It MAY validate:

* Response existence.
* Correlation.
* Supported encoding.
* Supported response type.
* Required provider envelope fields.
* Basic structured-data decoding.

It SHALL NOT determine:

* Whether the patch is safe.
* Whether target paths are authorized.
* Whether source changes are syntactically valid.
* Whether the response satisfies project requirements.
* Whether the provider fabricated project facts.

Those responsibilities belong to downstream validation.

---

# Inference Response Immutability

A finalized Inference Response SHALL be immutable.

Any transformation, validation result, or parsed patch SHALL produce a separate domain object.

The raw normalized provider content SHALL remain available according to retention policy.

---

# Provider Request Identity

Provider-side request identifiers SHALL remain distinct from ContextForge Inference Request Identifiers.

The adapter SHALL preserve both when available.

A provider request identifier SHALL not replace internal correlation identity.

---

# Determinism

Given identical:

* Inference Request.
* Provider Configuration.
* Model revision.
* Sampling parameters.
* Adapter version.
* Provider backend behavior.

The adapter SHOULD produce equivalent provider requests.

The Provider Interface SHALL not claim deterministic provider responses unless the provider supports and guarantees them.

Request translation SHALL remain deterministic.

---

# Configuration Fingerprint

The invocation result SHOULD preserve a fingerprint of provider configuration values affecting:

* Provider selection.
* Model selection.
* Prompt translation.
* Sampling.
* Output limits.
* Structured-output behavior.
* Retry behavior.
* Delivery policy.
* Endpoint profile.

Credentials and secret values SHALL not be included in the fingerprint.

---

# Security Requirements

The Provider Interface SHALL:

* Treat provider output as untrusted.
* Treat project content as confidential.
* Enforce delivery policy before transmission.
* Avoid logging complete requests by default.
* Avoid logging credentials.
* Use secure transport when required.
* Reject unauthorized endpoints.
* Prevent automatic tool execution.
* Prevent implicit model installation.
* Preserve request correlation.
* Sanitize provider errors.
* Avoid provider-driven changes to authorization.
* Prevent remote fallback without authorization.

---

# Prompt Injection Boundary

The Provider Interface SHALL not interpret source content or provider output as instructions to ContextForge.

Provider output MAY attempt to:

* Request tool execution.
* Request additional files.
* Override project limits.
* Change provider configuration.
* Exfiltrate secrets.
* Instruct ContextForge to apply changes automatically.

The adapter SHALL treat all such output as untrusted response content.

---

# Privacy Requirements

For remote providers, the Provider Interface SHALL make transmission explicit and policy-controlled.

The system SHOULD support user inspection of:

* Selected provider.
* Execution mode.
* Model.
* Approximate request size.
* Sensitive-content status.
* Endpoint profile.

Provider request retention behavior SHOULD be represented in configuration or provider metadata when known.

---

# Data Minimization

The Provider Interface SHALL transmit only the supplied Inference Request and required transport metadata.

It SHALL NOT transmit:

* Entire project repositories.
* Unselected artifacts.
* Local environment variables.
* Internal filesystem roots.
* Credentials unrelated to the provider.
* Hidden ContextForge state.
* Previous prompts unless explicitly included.

---

# Logging

Provider logs SHOULD include:

* Inference Request Identifier.
* Provider Identifier.
* Adapter Identifier.
* Model Identifier.
* Execution Mode.
* Invocation duration.
* Finish state.
* Retry count.
* Diagnostic codes.
* Token or usage counts when available.

Logs SHALL exclude:

* Authentication secrets.
* Complete prompt content by default.
* Complete provider response content by default.
* Sensitive project excerpts.
* Raw HTTP headers containing credentials.

---

# Persistence

Persistence of Inference Responses is optional.

When enabled, persistence SHALL consider:

* Project confidentiality.
* Provider-returned sensitive data.
* Retention duration.
* Encryption.
* Access control.
* Deletion policy.
* Audit requirements.

The MVP SHALL not require persistent storage of provider requests or responses.

---

# Cost Accounting

Remote provider adapters MAY calculate or estimate invocation cost.

Cost data SHALL distinguish:

* Provider-reported cost.
* Locally calculated cost.
* Estimated cost.
* Unknown cost.

Cost estimation SHALL not be treated as billing authority.

Local providers MAY report resource usage without monetary cost.

---

# Provider Registry

A Provider Registry MAY maintain available Provider Adapter implementations.

A registry entry SHALL include:

* Provider Identifier.
* Adapter Identifier.
* Adapter Version.
* Factory or construction reference.
* Supported configuration schema.
* Static capabilities.
* Execution Mode support.

The registry SHALL not instantiate arbitrary project-defined code.

---

# Adapter Registration

Adapter registration MAY occur through:

* Built-in registration.
* Application startup configuration.
* Explicit trusted extension configuration.
* Packaging entry points in a future release.

The MVP SHALL prefer built-in explicit registration.

Arbitrary runtime loading from the scanned project SHALL be prohibited.

---

# Mock Provider

The implementation SHOULD include a deterministic Mock Provider Adapter.

The Mock Provider SHALL support:

* Predictable responses.
* Configurable failures.
* Configurable timeouts.
* Configurable usage metadata.
* Structured-output fixtures.
* Streaming fixtures when streaming is implemented.

The Mock Provider SHALL be used for tests without network access.

---

# Ollama-Compatible Provider

The initial local adapter SHOULD support an Ollama-compatible inference service.

The adapter SHOULD support:

* Configured local endpoint.
* Model selection.
* Text generation.
* Chat-style generation when available.
* Structured JSON mode when available.
* Input and output measurements when provided.
* Timeout handling.
* Model availability check.
* Local execution classification.

The adapter SHALL not assume all Ollama-compatible implementations expose identical capabilities.

Capability detection or explicit configuration SHALL be used.

---

# Ollama Endpoint Policy

A default local Ollama endpoint MAY be configured.

The adapter SHALL:

* Validate the endpoint.
* Avoid assuming loopback means secure.
* Avoid exposing the endpoint as a remote provider without explicit configuration.
* Avoid automatic model pulls.
* Preserve actual model metadata when available.

---

# Remote Provider Adapters

Remote adapters MAY be introduced after the local MVP.

Every remote adapter SHALL provide:

* Explicit remote classification.
* Authentication configuration.
* TLS policy.
* Capability profile.
* Delivery-policy integration.
* Error sanitization.
* Usage metadata normalization.
* Provider-specific request translation.

Remote adapters SHALL not alter Core contracts.

---

# Rate Limiting

A Provider Adapter MAY encounter provider rate limits.

Rate-limit handling SHOULD preserve:

* Provider response code.
* Sanitized message.
* Retry-after guidance.
* Retryability.
* Attempt count.

The adapter SHALL not retry beyond configured policy.

---

# Concurrency

The Provider Interface MAY support concurrent inference requests.

Concurrency SHALL:

* Preserve request isolation.
* Preserve response correlation.
* Respect provider concurrency limits.
* Respect cancellation.
* Avoid sharing mutable request state.
* Avoid credential leakage between providers.

Provider-specific client reuse MAY be used when thread-safe.

---

# Resource Management

Provider Adapters SHALL manage:

* Network connections.
* Response streams.
* Client sessions.
* Temporary buffers.
* Cancellation resources.
* Local process handles when applicable.

Resources SHALL be released after completion, failure, timeout, or cancellation.

---

# Backpressure

Streaming adapters SHOULD support backpressure or bounded buffering.

Unbounded response buffering SHALL be avoided.

Backpressure behavior SHALL not silently drop content.

---

# Health and Readiness

The Application Orchestrator MAY validate provider readiness before invoking inference.

Readiness checks SHOULD be lightweight and SHALL not replace actual invocation error handling.

A healthy provider MAY still reject a specific request.

---

# Interaction with Prompt Builder

The Provider Interface SHALL rely on the Prompt Builder for:

* Prompt semantics.
* Instruction hierarchy.
* Context membership.
* Context ordering.
* Response Contract.
* Request size metadata.
* Security metadata.

The Provider Adapter SHALL NOT rebuild the prompt from project data.

---

# Interaction with Application Orchestrator

The Application Orchestrator SHALL:

* Select the provider.
* Supply Provider Configuration.
* Supply delivery authorization.
* Handle fallback policy.
* Record provider execution stages.
* Decide whether retry is permitted.
* Route successful responses to downstream validation.
* Stop execution on terminal provider failure.

The Provider Interface SHALL not control the complete Execution lifecycle.

---

# Interaction with Patch Engine

The Provider Interface SHALL return the provider output without patch interpretation.

The Patch Engine SHALL receive:

* Inference Response.
* Associated Expected Response Contract.
* Task Constraints.
* Project State information.
* Authorized path policy.

The Provider Interface SHALL not apply or approve proposed changes.

---

# Interaction with CLI

The CLI MAY expose:

* Available providers.
* Provider health.
* Provider capabilities.
* Selected model.
* Local or remote execution mode.
* Invocation status.
* Usage measurements.
* Retry information.
* Provider diagnostics.

The CLI SHALL not implement provider transport directly.

---

# Interaction with Configuration

Provider configuration resolution SHALL occur before invocation.

The Provider Adapter SHALL receive effective configuration.

It SHALL not search project files for credentials unless an explicit trusted configuration capability authorizes that behavior.

Project content SHALL not override provider security settings.

---

# Observability

The Provider Interface SHOULD expose enough information to explain:

* Which provider was selected.
* Which model was used.
* Whether execution was local or remote.
* Which capabilities were required.
* Which capabilities were missing.
* How request translation occurred at a high level.
* How long inference required.
* Whether retries occurred.
* Why invocation failed.
* Whether usage metadata is exact or estimated.
* Whether the response is complete.

Observability SHALL not require external telemetry.

---

# Performance Requirements

The Provider Interface SHALL avoid unnecessary request or response copies.

It SHOULD:

* Reuse provider clients safely.
* Support streaming where beneficial.
* Apply bounded buffering.
* Enforce deadlines.
* Avoid repeated prompt serialization.
* Record accurate duration measurements.
* Avoid blocking unrelated invocations.

Provider latency is external and SHALL not be represented as Core processing latency.

---

# Extensibility

The Provider Interface MAY support controlled extension through:

* Provider Adapters.
* Capability resolvers.
* Request translators.
* Response normalizers.
* Tokenizers.
* Usage calculators.
* Delivery-policy evaluators.
* Health-check implementations.

Extensions SHALL:

* Implement the Provider Port.
* Declare identifiers and versions.
* Avoid Core domain dependencies on SDK types.
* Preserve request semantics.
* Preserve response correlation.
* Respect delivery policy.
* Avoid arbitrary tool execution.
* Avoid project traversal.
* Avoid project modification.
* Sanitize failures.

---

# Implementation Organization

The source capability SHOULD be organized under:

```text
src/contextforge/provider/
```

Expected internal concepts MAY include:

```text
models
ports
services
registry
capabilities
configuration
policy
diagnostics
exceptions
```

Concrete adapters SHOULD be organized outside the Core capability, for example:

```text
src/contextforge/adapters/providers/
```

Possible adapters MAY include:

```text
ollama
mock
openai
anthropic
custom_http
```

The Core provider module SHALL NOT import provider SDKs.

---

# Dependency Rules

The Provider Port MAY depend on:

* Core domain models.
* Inference Request contracts.
* Provider-independent configuration abstractions.
* Provider-independent diagnostics.

Concrete Provider Adapters MAY depend on:

* Provider SDKs.
* HTTP clients.
* Serialization libraries.
* Operating-system APIs when necessary.

Provider SDK dependencies SHALL point toward adapters, never toward the Core.

---

# Traceability

| Requirement Area      | Provider Interface Responsibility                     |
| --------------------- | ----------------------------------------------------- |
| Provider independence | Isolate Core from provider SDKs and protocols         |
| Local inference       | Support an Ollama-compatible local adapter            |
| Remote inference      | Support policy-controlled remote adapters             |
| Security              | Enforce delivery authorization and transport policy   |
| Privacy               | Minimize transmitted project information              |
| Reliability           | Normalize timeout, retry, cancellation, and failures  |
| Explainability        | Preserve provider, model, usage, and attempt metadata |
| Determinism           | Preserve deterministic request translation            |
| Extensibility         | Support interchangeable Provider Adapters             |
| Patch safety          | Return output without applying or approving changes   |

---

# Acceptance Criteria

## AC-PROVIDER-001 — Provider-Independent Invocation

Given a valid Inference Request and compatible Provider Adapter, the Provider Port SHALL return one normalized Inference Response.

---

## AC-PROVIDER-002 — Core Isolation

Core domain modules SHALL not depend on provider SDK types, transport payloads, or provider-specific exceptions.

---

## AC-PROVIDER-003 — Request Preservation

The Provider Adapter SHALL preserve task instructions, Context Item ordering, context boundaries, and Expected Response Contract semantics.

---

## AC-PROVIDER-004 — No Context Expansion

The Provider Adapter SHALL NOT add project-derived content absent from the Inference Request.

---

## AC-PROVIDER-005 — Capability Validation

The adapter SHALL reject invocation when a mandatory provider capability is unavailable.

---

## AC-PROVIDER-006 — Delivery Policy

A remote invocation prohibited by delivery policy SHALL fail before request transmission.

---

## AC-PROVIDER-007 — Sensitive Context Protection

Sensitive context SHALL not be sent to a provider whose execution mode or policy does not permit it.

---

## AC-PROVIDER-008 — Model Identification

Every successful Inference Response SHALL identify the requested or effective model when available.

---

## AC-PROVIDER-009 — Response Correlation

Every Inference Response SHALL correlate to exactly one Inference Request.

---

## AC-PROVIDER-010 — Failure Normalization

Provider-specific failures SHALL be translated into provider-independent failure categories.

---

## AC-PROVIDER-011 — Error Sanitization

Ordinary diagnostics SHALL not expose credentials, complete prompt content, or sensitive project excerpts.

---

## AC-PROVIDER-012 — Timeout Handling

A provider timeout SHALL produce a normalized timeout failure or explicitly partial response.

---

## AC-PROVIDER-013 — Cancellation Handling

When cancellation is supported, a cancelled invocation SHALL not be reported as completed.

---

## AC-PROVIDER-014 — Retry Boundaries

Automatic retries SHALL occur only for configured retryable failures and within the authorized retry policy.

---

## AC-PROVIDER-015 — No Silent Truncation

The Provider Adapter SHALL not silently truncate the Inference Request to fit provider limits.

---

## AC-PROVIDER-016 — Output Preservation

The Provider Adapter SHALL not silently rewrite substantive provider output.

---

## AC-PROVIDER-017 — Structured Output Mapping

When structured output is required and supported, the adapter SHALL map the Expected Response Contract without reducing mandatory requirements.

---

## AC-PROVIDER-018 — Tool Call Safety

Unexpected provider tool calls SHALL not be executed.

---

## AC-PROVIDER-019 — Usage Integrity

Unavailable usage metadata SHALL remain unknown rather than being fabricated.

---

## AC-PROVIDER-020 — Local Provider MVP

The MVP SHALL include at least one functional local Provider Adapter.

---

## AC-PROVIDER-021 — Mock Provider

The test suite SHALL include a deterministic Mock Provider Adapter.

---

## AC-PROVIDER-022 — Immutable Response

A finalized Inference Response SHALL be immutable.

---

## AC-PROVIDER-023 — Patch Engine Readiness

The Inference Response SHALL contain sufficient normalized content, correlation, response-format metadata, and provider metadata for downstream validation without re-invoking the provider.

---

## AC-PROVIDER-024 — No Project Modification

The Provider Interface SHALL complete inference without modifying project artifacts.

---

# Test Categories

The Provider Interface SHALL be verified through:

* Unit tests for provider configuration validation.
* Unit tests for capability validation.
* Unit tests for delivery policy.
* Unit tests for request translation.
* Unit tests for response normalization.
* Unit tests for failure mapping.
* Unit tests for error sanitization.
* Unit tests for timeout handling.
* Unit tests for retry policy.
* Unit tests for cancellation.
* Unit tests for response correlation.
* Unit tests for usage normalization.
* Unit tests for structured-output mapping.
* Integration tests with a Mock Provider.
* Integration tests with an Ollama-compatible provider.
* Streaming tests when streaming is implemented.
* Input-size compatibility tests.
* Sensitive-context rejection tests.
* Remote-provider authorization tests.
* TLS-policy tests.
* Rate-limit tests.
* Empty-response tests.
* Partial-response tests.
* Unexpected-tool-call tests.
* Concurrent-request isolation tests.
* Resource-cleanup tests.
* Deterministic translation tests.

Tests SHALL not require internet access for the mandatory test suite.

Remote-provider integration tests MAY be optional and environment-gated.

---

# Reference Provider Fixtures

The test suite SHOULD include:

* Successful plain-text response.
* Successful structured response.
* Local provider invocation.
* Remote provider rejected by policy.
* Missing model.
* Provider unavailable.
* Connection timeout.
* Request timeout.
* Rate-limited response.
* Authentication failure.
* Input too large.
* Empty response.
* Invalid response encoding.
* Partial streaming response.
* Cancelled streaming response.
* Provider content-filter response.
* Unexpected tool-call response.
* Missing usage metadata.
* Estimated usage metadata.
* Retry succeeds on second attempt.
* Retry exhaustion.
* Sensitive Context Bundle with local provider.
* Sensitive Context Bundle with prohibited remote provider.
* Provider substitutes the requested model.
* Structured-output capability unavailable.
* Mock deterministic response.

---

# Validation Criteria

This specification SHALL be considered satisfied when:

* An immutable Inference Request can be executed through a provider-independent port.
* Core modules remain free of provider SDK dependencies.
* At least one local adapter is available.
* Provider capabilities are validated before invocation.
* Remote delivery is policy-controlled.
* Sensitive content remains protected.
* Request semantics and context ordering remain preserved.
* Provider-specific responses and failures are normalized.
* Usage and execution metadata remain honest and traceable.
* Timeouts, retries, cancellation, and partial responses are explicit.
* Provider output remains untrusted and unapplied.
* The Patch Engine can consume the normalized response without provider-specific logic.

---

# Completion Statement

The Provider Interface is complete when ContextForge can execute an immutable Inference Request through interchangeable local or remote inference providers while preserving request semantics, enforcing delivery policy, isolating provider-specific dependencies, normalizing responses and failures, and returning an immutable Inference Response without interpreting or applying project changes.
