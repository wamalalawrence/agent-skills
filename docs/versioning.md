# Versioning

`agent-skills` is pre-1.0. The project uses semantic-version-shaped releases, but stability promises
are intentionally narrower before `v1.0.0`.

## Before `v1.0.0`

- Minor versions may change skill structure, configuration shape, handoff artifacts, and output
  contracts.
- Patch versions should focus on documentation, formatting, compatibility, examples, validation
  fixes, and non-breaking clarifications.
- Release notes in [CHANGELOG.md](../CHANGELOG.md) are the source of truth for what changed.

## After `v1.0.0`

- Breaking changes require a major version.
- Skill names and core output contracts should remain stable within a major version.
- Minor versions should add compatible capabilities.
- Patch versions should remain narrowly scoped to fixes and clarifications.

Until `v1.0.0`, pin the repository version or tag when you need repeatable behavior across teams or
automation.
