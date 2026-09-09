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

## Release channels

| Channel | Contains | Offered to |
| --- | --- | --- |
| `stable` | Releases with no pre-release suffix. | Everyone, by default. |
| `rc` | Release candidates (`1.0.0-rc.1`) **and** stable releases. | Machines that opted in with `--channel rc`. |

`stable` never offers a pre-release, so a release candidate cannot reach a machine that did not ask
for one. `rc` is deliberately a superset: a machine tracking release candidates must still be
offered the stable release that supersedes the last candidate, or it would be pinned to
pre-releases forever.

Pre-release versions sort below their release and above the previous one, so `0.43.0` <
`1.0.0-rc.1` < `1.0.0`.

## Exit codes

These are a public contract. Scripts and CI branch on them, so they are frozen at `1.0.0`. Adding a
new code afterwards is allowed; changing the meaning of an existing one is not.

| Code | Name | Meaning | What to do |
| --- | --- | --- | --- |
| `0` | ok | The command succeeded. | — |
| `2` | usage-error | The invocation was wrong, or the request is not possible. | Fix the command. |
| `3` | authentication-required | The release source needs credentials this machine does not have. | Authenticate to git, then retry. |
| `4` | network-failure | The release source could not be reached. | Retry later. |
| `5` | integrity-failure | A payload was not what it claimed to be. | Do **not** retry blindly: either a corrupt download or an attack. |
| `6` | installation-failure | The machine could not be changed. | The previous release is still active. |
| `7` | verification-failure | The installation is in a bad state. | Run `agent-skills doctor`. |
| `10` | update-available | Informational, from `check-updates`. Not a failure. | Run `agent-skills update`. |

Each answers a different operator question, because "it failed" is not actionable and a single code
forces log-scraping. In particular, `3` and `4` are separate on purpose: one is fixed by
authenticating, the other by waiting.

They are defined in [`lib/asrelease/exits.py`](../lib/asrelease/exits.py) and asserted by
`scripts/test-release-engine.py`, so a renumbering cannot pass silently.

`agent-skills guard check-command` has its own, older set — `0` allow, `10` ask, `20` deny — which
predates this table and is unaffected by it.

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
| _(none)_ | | | |

`tech-lead` to `wamala` is the only entry this table has held. It was added in `v0.38.0` and removed
in `v0.41.0`, three minor releases later, exactly as scheduled. From `v0.41.0` the old name is not
recognised anywhere: `--skill tech-lead` passes through as an unknown skill name rather than being
silently translated.

The aliases live in `AGENT_SKILLS_DEPRECATED_SKILLS` in
[`scripts/task-context.sh`](../scripts/task-context.sh). Adding a row is a commitment to carry it
for three minor releases; removing one on schedule is part of that release's checklist.

Until `v1.0.0`, pin the repository version or tag when you need repeatable behavior across teams or
automation.
