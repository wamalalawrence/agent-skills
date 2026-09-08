# Security Review — v0.38.0

This release adds a code path that **deletes** entries from directories the user owns, so it gets
an explicit review rather than an assurance. Recorded 2026-09-08 against the release branch.

Scope is narrow by design. v0.38.0 changes no authentication, no credential storage, and no trust
boundary around repository-supplied content; [the v0.37.0 review](security-review-v0.37.0.md)
still describes those, and its probes were re-run unchanged as part of this release's suites. What
is new here is exactly two things:

- `as_orphan_registrations` / `as_is_our_skill_registration` in [`lib/install.sh`](../lib/install.sh),
  which remove host registrations for skills the current release no longer ships.
- `agent_skills_resolve_skill_name` in [`scripts/task-context.sh`](../scripts/task-context.sh),
  which maps a deprecated skill name to the current one.

Method: threat-by-threat walkthrough with adversarial probes, plus the automated suites. Where a
claim is only reasoned about and not exercised, it says so.

## Summary

| Area | Verdict |
| --- | --- |
| Deleting a file the user owns | mitigated, probed — the predicate needs two independent conditions |
| Deleting through a link that points outside the install root | mitigated, probed |
| Deleting everything when the source tree is unreadable | mitigated, probed — fails closed |
| Path traversal through a skill directory name | mitigated, reasoned |
| Paths containing spaces or shell metacharacters | mitigated, probed |
| The alias table as an injection surface | mitigated, reasoned |
| Notice output leaking into a captured value | mitigated, probed |
| Everything else | unchanged from v0.37.0, re-probed by the existing suites |

## Deleting a file the user owns

This is the release's only genuinely new risk. The installer now removes entries from
`~/.claude/skills`, `~/.agents/skills`, and the rest — directories that belong to the user and
routinely hold their own work.

The predicate requires **both** halves, and each is checked independently:

1. `as_is_owned_link` — the entry is a symlink whose target lives inside `AGENT_SKILLS_HOME`. This
   is the same ownership test v0.37.0's `uninstall` already used, unchanged.
2. The link target's **parent directory** is exactly `<home>/skills` (or its realpath). A link into
   any other part of our install root is not a skill registration and is not pruned.

A directory the user created fails the first half — it is not a symlink at all. A symlink into the
user's own tree fails both. A file fails both.

Probed, in `scripts/test-global-install.sh`:

- `~/.claude/skills/tech-lead` as a **real directory** with the user's own `SKILL.md`. Result: the
  directory survives the upgrade, is not converted to a symlink, and its content is byte-identical
  afterwards.
- `~/.kiro/skills/tech-lead` as a **symlink into `~/my-skills/tech-lead`**. Result: the link
  survives, still points where it did, and the file at the far end is untouched.

Both cases use the name being retired, which is the worst case: the entry the pruner is actively
looking for.

## Deleting through a link that points outside the install root

`rm -f` on a symlink removes the link, not its target, so even a mistaken prune could not delete a
user's file through it. That is a property of `rm` rather than of this code, so it is stated as
reasoning; the probes above are what actually establish that the mistaken prune does not happen.

The pruner never opens, reads, or writes **through** an entry. It calls `readlink` and `rm -f`, and
nothing else.

## Deleting everything when the source tree is unreadable

The failure mode worth fearing: `as_top_level_skills` returns nothing — a moved clone, an unmounted
volume, a permissions change — and every registration then looks like an orphan. That would delete
the entire installation from every host directory in one run.

`as_orphan_registrations` returns early when the current skill list is empty, before it examines a
single entry. Fails closed.

Probed: the existing `H5B` case installs from a throwaway source copy, deletes the copy, and runs
`uninstall`. It still recognises its own registrations by literal target, and the unrelated user
skill survives. Re-running `install` in that state prunes nothing, because the skill list is empty.

## Path traversal through a skill directory name

`as_top_level_skills` enumerates `${source_dir}/skills/*` and takes `basename`, so a name is always
a single path component with no separator in it. The pruner compares that against `basename` of an
entry in the host directory, and `rm -f "${skills_dir}/${orphan}"` reassembles a path from those two
pieces. A `..` component cannot reach either side: `basename ".."` is `..`, but a directory named
`..` cannot exist, and a host-directory entry named `..` is not returned by the glob.

Reasoned, not probed. Creating the fixture would require a filesystem that permits a `..` entry.

## Paths containing spaces or shell metacharacters

Every sandbox in `scripts/test-global-install.sh` uses a `HOME` whose path contains a space,
including the sixteen new migration cases and the v0.37.0-shaped source tree at
`${H14}/v0.37.0 source`. Every expansion in the new code is quoted. `while IFS= read -r` is used
for the orphan loop rather than word splitting, so a skill name could contain a space without
splitting — no shipped skill does, but the loop does not assume it.

The one deliberate unquoted expansion is `for pair in ${AGENT_SKILLS_DEPRECATED_SKILLS}`, which is
word splitting a constant defined three lines above it in the same file. It is not user input.

## The alias table as an injection surface

`AGENT_SKILLS_DEPRECATED_SKILLS` is a literal in `scripts/task-context.sh`. It is not read from the
environment, from a config file, or from a repository. A malicious repo cannot add a row, so it
cannot redirect `--skill software-engineer` to something else.

The resolver only ever returns one of: a value from that literal table, or its own argument
unchanged. It does not `eval`, and it does not construct a path. A name it does not recognise is
returned verbatim and validated downstream exactly as before — probed by the "unknown skill name
passes through unchanged" case.

## Notice output leaking into a captured value

`agent_skills_resolve_skill_name` is called inside `$(...)` in both lifecycle scripts, so anything
it wrote to stdout beyond the resolved name would be captured as part of that name. The migration
notice goes to **stderr**.

Probed: `start-task --skill tech-lead` records `wamala` on the blackboard — not `wamala` with a
notice appended, and not `tech-lead`. The assertion that the blackboard does **not** contain
`tech-lead` is what makes that check meaningful in both directions.

## Everything else

No change. The v0.37.0 threats — secret leakage, filesystem permissions, symlink attacks,
repository-controlled profile references and credential routing, the tracked-file check under a
failing `git`, malicious `.agent-skills.yml`, malicious repo-resident knowledge, environment
poisoning, shell injection, credential exfiltration, profile confusion — are covered by code this
release does not touch, and their probes live in `scripts/test-global-install.sh` (119 assertions)
and `scripts/test-access-resolution.sh` (100 assertions). Both suites pass unchanged.

The rename itself moves no credential, changes no permission, and adds no network call. The
installer still asks for nothing.

## Probes shown failing

Per the checklist rule about probes that assert against a mechanism the code does not use,
`as_orphan_registrations` was stubbed to return nothing and the suite re-run. Four assertions
failed and pass with the mechanism restored; the experiment also exposed that two absence
assertions had been passing against a **dangling** link, because `test -e` follows symlinks. Both
now check `! -e` and `! -L`. Recorded in
[`eval-runs/v0.38.0/summary.md`](../eval-runs/v0.38.0/summary.md).

## Residual risks

- **A race between the ownership check and the `rm`.** Unchanged from v0.37.0 and the same
  reasoning applies: an attacker who can write into the user's host skills directory at that exact
  moment can already write the skills the agent loads, so this is not an escalation.
- **A user who deliberately named their own skill `tech-lead` and made it a symlink into
  `~/.agent-skills/skills/`.** Such an entry is indistinguishable from ours by construction, and it
  would be pruned. The control offered is that `install` names every registration it removes in its
  output, so the removal is visible rather than silent. It is not the default to prompt, because a
  routine upgrade that stops to ask about a link the installer itself wrote is worse for everyone
  who did not do this.
