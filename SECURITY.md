# Security

`agent-skills` is proprietary, solo-maintained software. This page describes how security is treated in
the project and how to report a problem.

## How the project approaches security

The design assumes that most of what an agent reads is outside the operator's control — a
repository file, a ticket, a log line, a chat message, a database value, a tool response — and
that any of it may be written to steer the agent. Three mechanisms hold that line, and each has a
recorded threat-by-threat review under `docs/security-review-<version>.md`:

- **External content is evidence, not instruction.** Recorded and retrieved text is treated as a
  claim to verify, never as a command to follow. See
  [destructive-action safety](docs/destructive-action-safety.md).
- **[Execution Guard](docs/execution-guard.md)** is a deterministic check that runs before a
  shell command or tool call executes, where a host provides an interception point. It has a
  hard-deny floor that no configuration layer can lower.
- **[Access resolution](docs/access-resolution.md)** keeps credentials out of agent context,
  prefers an already-authenticated tool over a stored secret, and never lets a file inside a
  repository choose which identity is used.

None of these makes a machine safe on its own, and
[known limitations](docs/known-limitations.md) states plainly what validation in this repository
cannot prove.

## What a report should cover

A useful report identifies a way the project's own guidance or mechanisms produce an unsafe
outcome — for example a skill instruction, template, or default that leads an agent to disclose a
credential, commit a secret, weaken a safety control, or act on untrusted content as if it were
an instruction; or a flaw in the installer, release verification, Access Resolver, Execution
Guard, or Engineering Tool Capability Framework.

Generated code in a downstream repository is not maintained here, but skill guidance that
systematically steers agents toward unsafe output is in scope.

Please include the affected file or command, what happens, the smallest way to reproduce it, and
a suggested fix if you have one. Do not put real secrets, tokens, or customer data in the report.

## Reporting

Use GitHub private vulnerability reporting on the repository. If it is not enabled, open a
minimal issue titled `Security contact request` with no exploit detail, and a private channel
will be arranged.

## Handling

Reports are reviewed as capacity allows. Confirmed issues are prioritised by impact, fixed, and
recorded in `CHANGELOG.md`; where a fix changes a security boundary, the change is added to the
release's security review and pinned with a test so it cannot regress silently.
