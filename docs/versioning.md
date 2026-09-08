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

## Deprecated Skill Names

A skill rename produces exactly one skill directory and one discoverable skill name. The old name
is never kept as a second copy: two discoverable front doors drift apart, and the drift is
invisible until someone invokes the stale one.

What the old name gets instead is a bounded alias in the lifecycle CLI. `agent-skills start-task`
and `agent-skills finish-task` accept it for `--skill`, resolve it to the current name, and print
one line saying so. Nothing else recognises it: the host registries expose only the current name,
and an existing global installation has its old registration removed on the next
`agent-skills install`.

| Deprecated | Current | Since | Removed in |
| --- | --- | --- | --- |
| `tech-lead` | `wamala` | `v0.38.0` | `v0.41.0` |

The aliases live in `AGENT_SKILLS_DEPRECATED_SKILLS` in
[`scripts/task-context.sh`](../scripts/task-context.sh). Adding a row is a commitment to carry it
for three minor releases; removing one on schedule is part of that release's checklist.

Until `v1.0.0`, pin the repository version or tag when you need repeatable behavior across teams or
automation.
