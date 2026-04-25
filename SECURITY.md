# Security Policy

## Supported Versions

This project is pre-1.0. Security fixes will target the latest published version unless a clear reason exists to document a workaround for older versions.

## Scope

Security concerns in scope include:

- Instructions that could cause accidental credential disclosure.
- Templates that encourage committing secrets or private configuration.
- Cache guidance that stores sensitive data unnecessarily.
- Skill instructions that create unsafe defaults for generated code or review workflows.

Generated code in downstream user repositories is not directly maintained here, but skill guidance that systematically encourages unsafe output is in scope.

## Reporting A Vulnerability

Use GitHub private vulnerability reporting if it is enabled for the repository.

If private reporting is not available yet, open a minimal public issue titled `Security contact request` without exploit details, secrets, or private data. The maintainer can then provide a private channel for details.

Please include:

- Affected file or skill.
- A concise description of the risk.
- Steps to reproduce or the exact instruction that creates the risk.
- Suggested mitigation, if known.

## Handling

The maintainer will review reports as capacity allows, prioritize confirmed risks, and publish a fix or mitigation note when appropriate.