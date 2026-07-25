# Security Policy

## Supported versions

ContextForge is pre-release software. Security fixes are applied to the latest
code on the default branch until stable release support windows are published.

## Reporting a vulnerability

Do not open a public issue, discussion, or pull request for a suspected
vulnerability.

Use GitHub's private vulnerability reporting for this repository:

1. Open the repository's **Security** tab.
2. Select **Advisories**.
3. Select **Report a vulnerability**.

Include:

- A concise description and potential impact.
- Affected version, commit, or component.
- Reproduction steps or a minimal proof of concept.
- Any known preconditions or mitigations.
- Whether the issue may expose project content, credentials, or filesystem data.

If private vulnerability reporting is unavailable, contact a repository maintainer
privately and ask for a secure reporting channel without including exploit details
in the initial message.

Maintainers should acknowledge a complete report within seven calendar days.
Investigation and disclosure timing depend on severity and remediation complexity.
Reporters will be credited when desired and safe to do so.

## Security scope

High-priority concerns include:

- Project-root escape or path traversal.
- Modification without proposal-bound approval.
- Secret leakage through diagnostics, logs, prompts, or provider requests.
- Execution of project or provider-generated content.
- Unauthorized remote transmission.
- Provider-output trust or validation bypass.
- Dependency or CI compromise.

Please report suspected vulnerabilities even when exploitability is uncertain.
