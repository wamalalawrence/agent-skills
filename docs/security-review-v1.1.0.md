# Security review — v1.1.0

Follows [the v0.37.0 review](security-review-v0.37.0.md) as the shape. Each threat is labelled
**probed** (a test exercises it), **reasoned about** (argued from the design), or **unproven**.

`1.1.0` answers a field report from a long Wamala run. Most of it changes instructions. Five
changes touch a boundary this project defends: cleanup, which is recursive deletion; how the
cache is found, which decides where memory is written; content that now flows from one agent's
evidence pack into the next agent's brief; a new command that tells an agent whether a delete is
safe; and a signal that turns cleanup off.

## Scope of this review

- **Cleanup.** `scripts/project-memory.py` (`cleanup_task` keeps `artifacts/` always, and
  `evidence-pack.yml` around a plan); `scripts/finish-task.sh` (coordinated-run deferral, and
  `--project`, `--issue-key`, `--task`); `scripts/task-context.sh` (the in-flight count requires a
  blackboard).
- **Cache resolution.** `scripts/cache_root.py` (new) and `agent_skills_anchor_root` in
  `scripts/task-context.sh`, adopted by `blackboard.py`, `telemetry.py`, `org-memory.py`,
  `promote-rules.py`, `execution-watchdog.py`, `project-memory.py`, `context.py`, and
  `knowledge.py promote`.
- **Continuity.** `scripts/delivery-run-next.py` (`phase.prerequisite_context`, read from the
  evidence pack).
- **Deletion safety.** `scripts/reversibility.py` (new), `bin/agent-skills` (`reversibility`).
- **Capability report.** `scripts/doctor.sh` (reports a project's own knowledge base).

No change to the release engine, the installer, Execution Guard, the Access Resolver, the
redaction patterns, or the host adapters.

---

## Threat: cleanup deletes something it should not

**Probed.** `scripts/test-lifecycle-fs.sh`, sections "Cleanup keeps what someone still has to
read" and "A step inside a coordinated run leaves scratch to the coordinator", with probes 3 and 4.

Every change here is in the retaining direction. Cleanup still resolves the key against real
directory entries by exact name. It still refuses reserved names, symlinks, and any directory
holding a `.git`. Probes 1 and 2 still show those refusals are load-bearing. What is new is a
keep list, applied inside a directory that was already resolved safely, and a condition under
which cleanup does not run at all. A symlinked child inside the task directory is unlinked, not
followed.

**Residual.** The only way this change removes more than `1.0.0` did is not to exist. Coordinated
runs keep more on disk for longer, which is the next threat.

## Threat: retained scratch keeps sensitive content on disk longer

**Reasoned about.** `artifacts/` and an evidence pack now survive a `complete` closeout. So does
the whole task directory for a step inside a coordinated run, until the coordinator closes out.
All of it sits inside the cache, which `start-task` adds to `.git/info/exclude`, so nothing reaches
a commit unless someone force-adds it. Durable writes still redact. A coordinator that never
closes out leaves the directory behind; `finish-task --cleanup` removes it.

**Control not made default:** time-based expiry of `artifacts/`. Deleting a deliverable on a clock
is the defect this release fixes.

## Threat: a forged blackboard turns cleanup off

**Probed** for the false-positive direction. A fact that mentions "wamala" does not make a run
coordinated: the check parses `skill_versions` as JSON. **Reasoned about** for forgery. Anyone
who can write the blackboard can already write the task's memory. The only effect of forging a
coordinator is that scratch is kept, which fails safe.

## Threat: another local account captures the cache through an anchor

Found while writing this review, and fixed before release. Outside git, the
new resolver walks up to the nearest parent that already holds `.agent-skills.yml` or a cache. In
a shared directory such as `/tmp/work`, another account could plant `/tmp/.agent-skills.yml`.
Project memory, the blackboard, and telemetry would then be written into a directory that account
controls, where it can read them or seed a blackboard with instructions. An anchor now counts only
when both the directory and the anchor file or cache belong to the current user (`-O` in bash,
`st_uid == getuid()` in Python). `$HOME` and `/` are never anchors.

**Probed for the Python resolver; reasoned about for the shell one.** A sandboxed suite cannot
create a file owned by another uid without root. `scripts/test-lifecycle-fs.sh` asks the Python
resolver the question as a different uid instead, and asserts the anchor is refused. That test
fails against the resolver without the check. The shell resolver's `[[ -O ]]` cannot be faked
the same way. It is the same two conditions in the same shape, and a shared-directory user who
wants certainty sets `AGENT_SKILLS_CACHE_DIR`, which bypasses discovery entirely.

## Threat: a credential in an evidence pack reaches another agent's brief

**Probed.** `scripts/test-adaptive-execution.sh`, "What a prerequisite learned reaches the next
phase's brief", with probe 4.

`prerequisite_context` exists to be pasted into a brief. Every string it returns passes through
`guard_audit.redact`. A credential-shaped value planted in `follow_up_context` does not appear in
the decision, and the probe shows it does once the redaction call is removed.

## Threat: a planted instruction rides the carried-forward context

**Reasoned about; not preventable by the runtime.** An evidence pack is written by an agent.
`follow_up_context` reaching the next brief verbatim is the point of the change, and a line
reading "skip the review" would travel with it. No filter distinguishes a planted order from a
real trap. The control is labelling. Both handoff templates say carried-forward lines are claims
recorded by earlier steps, to be verified, never followed as instructions. That applies the
existing [untrusted recorded context](destructive-action-safety.md#untrusted-recorded-context)
rule to the new channel.

**Residual.** This channel existed before `1.1.0`, as a dispatcher copying the same lines by hand.
It is now systematic and labelled, instead of ad hoc and unlabelled.

## Threat: the reversibility check says "safe" when it is not

**Probed.** `scripts/test-lifecycle-fs.sh`, "Delete-shaped requests", with probe 5.

The check fails closed at every branch it cannot settle. That covers no repository, git failing
or timing out, a path that cannot be placed inside its repository, and a target holding the
repository's own `.git`. `RECOVERABLE` requires tracked content with nothing untracked, ignored,
or uncommitted beneath it. Pathspecs use `:(literal)` after `--`, so a file named `-rf` or `*`
is a path. It never deletes or moves anything. The commands it prints are built with
`shlex.quote`, so a hostile file name cannot turn a printed archive command into a different one.

**Residual.** It proves what git can prove and nothing else. `RECOVERABLE` for an unpushed commit
is true only while the local repository survives. A backup is invisible to it. Both are stated in
its output and in [known limitations](known-limitations.md).

## Threat: the capability report leaks repository content

**Reasoned about.** The knowledge-base probe counts files by extension under a fixed list of
directory names, at depth four or less. It reads no content and prints only the directory name and
a count.

## Threat: explicit identity flags open a path traversal

**Probed** through the existing suite. `finish-task --issue-key` feeds the same
`agent_skills_normalise_issue_key` and the same exact-name cleanup resolver as the positional form,
so `../escape`, `a/b`, `..`, `.`, and reserved names still refuse. The new cases exercise the
flag form. The refusal cases already covered the resolver it reaches.

## Findings raised and resolved in this review

| Finding | Resolution |
| --- | --- |
| A shared-directory anchor could redirect the cache to another account's directory | Anchors must be owned by the current user, in both resolvers |
| Carried-forward context was unlabelled when pasted into a brief | Both handoff templates label it as claims, not instructions |
| `reversibility` crashed on a symlink whose target left the repository | Placed by its unresolved name; an unplaceable path is `NOT_RECOVERABLE` |

## Residual risks

- Retained scratch in abandoned coordinated runs, cleared by `finish-task --cleanup`.
- Planted instructions in `follow_up_context`, controlled by labelling and the verify-claims rule.
- An anchor spoof in a shared directory: blocked in both resolvers, probed only in Python.
  `AGENT_SKILLS_CACHE_DIR` removes discovery altogether.
