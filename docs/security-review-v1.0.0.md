# Security review — v1.0.0 (stable)

Follows [the v0.37.0 review](security-review-v0.37.0.md) as the shape. Each threat is labelled
**probed** (a test exercises it), **reasoned about** (argued from the design), or **unproven**.

This release answers a pre-1.0 architecture review that probed the memory tiers, the lifecycle,
and the dispatcher with inputs no suite had sent. Of its sixteen findings, three sit on a security
boundary: a credential-retention hole in the committed knowledge tier, a lost-update path that
also masked the caller's own errors, and a trust boundary — agent claim to recorded completion —
that had no mechanism behind it. The rest are integrity findings, and integrity of recorded
knowledge is a security property here because every future agent reads it.

## Scope of this review

`v1.0.0` changes:

- **Knowledge base.** `scripts/knowledge.py` — the serialisation boundary in `Lesson.write`,
  observation identity, the `disputed` state, idempotent decay, recency ordering, rendered-length
  budgeting, and the lock around every mutation.
- **Durable writes.** `scripts/durable.py` — `LockTimeout`, narrowed exception scope,
  quarantine of unreadable JSON, `AGENT_SKILLS_LOCK_TIMEOUT_SECONDS`.
- **Lifecycle.** `scripts/finish-task.sh` (`--if-open`, the closed marker, the delivery-evidence
  signal), `scripts/start-task.sh` (one startup budget), `scripts/project-memory.py` and
  `scripts/org-memory.py` (`read --budget-chars`), the three hook templates.
- **Delivery.** `scripts/dod-check.py` (new), `bin/agent-skills` (`dod-check`),
  `scripts/delivery-run-next.py` (target normalisation and containment),
  `scripts/outcome-recorder.py` (provenance from stores on disk), `scripts/context.py`
  (span marking).
- **Instructions.** The definition-of-done schema, the RED rule at every site, Wamala's
  dispatch verification, the evidence-discipline reference.

No change to the release engine, the installer, the Execution Guard, the Access Resolver, the
redaction patterns, or the host adapters. The threat model is the union of the prior reviews plus
the surface below.

---

## Threat: a credential reaches the committed knowledge base through the evidence field

**Probed.** `scripts/test-secret-boundary.sh` — the evidence case through `add`, `confirm`, and
`contradict`, plus a probe that replaces the redactor with the identity function and asserts the
value then lands.

This one was live. `add_lesson` redacted `trigger` and `action` and merged `evidence` verbatim.
A closeout that cited a run by its connection string, or an agent that pasted a token into the
locator, published it: the lesson file is committed, pushed, and read by every later agent. The
normal one-line recall does not print the evidence field, which is why nobody saw it, and why it
is a persistence leak rather than a display one.

**Control.** Every string and list-of-strings field in a lesson's front matter, and the body,
passes through `redact` in `Lesson.write` — the one place a lesson is serialised — and every input
is cleaned before it is compared for identity. Two layers on purpose: the write boundary catches a
hand-edited file that goes through the tool later; the input cleaning is what makes the
observation-identity comparison operate on the value that will actually be stored, so a
token-bearing locator cannot be submitted twice and read as two distinct observations.

**Asserted.** `SHORT` and `LONG` fixtures do not appear anywhere under the lesson directory after
the three operations; the surrounding locator text does.

---

## Threat: a lost update on a lesson or a project note, and a masked error

**Probed.** `scripts/test-knowledge.sh` — a helper holds the lesson's lock while a confirm is
started; the confirm must not have written while the lock was held and must land after it is
released. A second case holds the lock past a one-second timeout and asserts the confirm exits
non-zero with "could not lock" and writes nothing. A third raises `OSError` inside the locked body
and asserts the same `OSError` reaches the caller.

`adjust_confidence` and the existing-lesson branch of `add_lesson` read, modified, and wrote with
no lock; `append_note` used a plain `write_text`. The review synchronised two processes into the
window and lost a confirmation. The shared helper made it worse in two ways: a lock that timed out
yielded `False` and ran the body anyway — no caller checked — and its `except OSError` wrapped the
`yield`, so a body failure re-entered the generator and surfaced as `RuntimeError: generator
didn't stop after throw()`, with the original cause gone.

**Control.** Every knowledge mutation holds the lesson's (or `project.md`'s) advisory lock for the
whole read-modify-write. `locked` guards only acquisition; contention past the deadline raises
`LockTimeout` before the body runs, and the four CLIs that use it print "nothing was written,
retry" and exit 1. A filesystem that cannot lock (`ENOLCK`, `EOPNOTSUPP`) is reported once to
stderr and proceeds, because there is nothing to wait for.

**Reasoned about.** The lock is advisory and per file. A writer that bypasses the tool and edits a
lesson by hand is not serialised against it, which is the same property `project-memory` and the
installer already accept. The kernel releases the lock when the descriptor closes, so a killed
process leaves nothing wedged.

---

## Threat: corruption evidence is overwritten

**Probed.** `scripts/test-knowledge.sh` — a half-written `memory.json` is moved to
`memory.json.corrupt-<timestamp>`, its content preserved, and the update proceeds from the
default; a missing file starts from the default with no quarantine file.

`update_json` replaced unreadable content with `default` in place. That kept the tier usable —
the reason it was written that way — and destroyed the only evidence of what had gone wrong, which
for a tier that other processes write concurrently is the evidence you want most.

**Control.** Missing and corrupt are distinguished (`FileNotFoundError` versus `ValueError`); a
corrupt store is renamed beside itself and reported on stderr.

---

## Threat: a claim of completion is recorded as completion

**Probed.** `scripts/test-knowledge.sh` — a `complete` closeout with no artifact is recorded with
`verified_delivery=no` and prints `NOT verified`; a closeout with a verifiable
`definition-of-done.json` is recorded `verified_delivery=yes`. Nine `dod-check` cases: a pass
without an execution record, a pass on another revision, a `fail` without a waiver, a waiver signed
by `agent`, a waiver with a named authority, RED without its assertion, the pre-1.0 boolean shape,
a bug fix with RED and GREEN, and a `false` classification needing no waiver.

`finish-task --status complete` with a summary and nothing else emitted `completed`. Wamala treated
"the artifact exists and is populated" as done. The definition of done was a bag of booleans whose
one rule — waive every `false` — applied equally to a failed build and to a classification that
happened to be `false`, so waivers were routine. No verifier existed.

**Control.** A closeout is still recorded — it must be, for blocked work and recovery — but it now
says whether the task's evidence artifact exists and verifies, and telemetry carries the answer.
`dod-check` validates the artifact as evidence: results are `pass | fail | not_run |
not_applicable`; a pass names its command, working directory, revision, and exit code and must
match `head_sha`; a `fail` or `not_run` needs a waiver whose authority is `user`, `reviewer`,
`project-policy`, or `ticket`; classifications are never waived. `code-reviewer` runs it itself
rather than reading the engineer's line.

**Reasoned about — and the honest limit.** The agent that writes the artifact can also write the
log it cites, so a verified definition of done is an auditable claim, not an attestation. What
changed is that the claim now has a shape that can be checked and a place where a false one shows:
a pass without a record, or on the wrong revision, is refused mechanically. Protected CI running
the same checks on the same revision remains the stronger boundary, and this release does not
pretend otherwise; [known limitations](known-limitations.md#memory-and-evidence) says so.

---

## Threat: repeated submission manufactures a trusted rule

**Probed.** `scripts/test-knowledge.sh` — five submissions of the same evidence leave a lesson at
0.5 with one confirmation; new evidence raises it; a re-add with a different action writes nothing;
`confirm` without `--evidence` is refused and with recorded evidence is idempotent. A probe removes
the identity check and asserts confirmations then inflate.

A retried closeout, a hook that fired twice, or an agent that ran `finish-task` again after a
typo, each raised confidence and the confirmation count. Five identical adds produced 0.9, five
confirmations, one unique piece of evidence — a "project constraint" from one observation. And a
re-add whose action differed kept the old action and reinforced it, so a wrong lesson could be
strengthened by an attempt to correct it.

**Control.** Evidence is the observation identity. Confidence and confirmations move only when a
locator not already recorded is supplied; a changed proposition is reported as a conflict and
writes nothing.

**Reasoned about.** Two task keys that are really one observation — the same run recorded under a
ticket key and its PR URL — still count twice. The runtime can enforce shape, not truth; the
pull-request review that adds the lesson remains the control for that.

---

## Threat: a disproved lesson keeps steering agents

**Probed.** `scripts/test-knowledge.sh` — `contradict` leaves `verified_at` unchanged, marks the
lesson `disputed` at one contradiction against one confirmation, withholds it from `read`, reports
the withholding, and a further distinct confirmation reactivates it. A probe makes `contradict`
refresh `verified_at` and asserts the date then moves.

`contradict` set `verified_at` to today. A lesson an agent had just shown to be wrong looked
freshly verified to the next one and stayed in recall at nearly full weight.

**Control.** Separate `last_confirmed_at`, `last_contradicted_at`, `last_decay_at`, and a `status`
derived from the counts. Only `active` lessons are recalled; `doctor` reports the disputed ones
with their counts.

---

## Threat: two dispatched agents write the same files

**Probed.** `scripts/test-adaptive-execution.sh` — a directory beside a file inside it, a
dot-segment alias, an escaping target, an absolute target, disjoint siblings that still group, and
a named resource in a different case. The probe now removes the containment check.

`parallel_group` intersected the raw target strings. `src/api` and `src/api/handler.ts` were
disjoint by that test and the two phases were dispatched together into one working tree.

**Control.** Targets are normalised with `posixpath.normpath`; a path overlaps by containment; a
named resource (`db:orders`) by case-insensitive identity; an absolute or repository-escaping
target disqualifies its phase.

**Unproven.** Symlink targets are not resolved. The decision runs against the plan, not a
checkout, and the repository the phases will write may not exist on the deciding machine. A
symlink that makes two normalised paths one is not detected. The documentation says a worktree
does not prove independence; this is one of the reasons.

---

## Threat: a session-stop hook writes a false task outcome

**Probed.** `scripts/test-knowledge.sh` — after a normal `complete` closeout, `finish-task
--if-open` prints "already closed out", writes no second bullet, and emits no `stopped` event;
with a task that was never finished it records `needs-context` and preserves scratch, attributed
`closeout=fallback`; with no task identity it records nothing.

Every hook template called `finish-task --status needs-context` unconditionally on `Stop`, which
fires at the end of every turn. A normal session therefore ended with two closeouts — the real one
and a false "unfinished" — in project memory and in the `stopped` counter the release review
reads.

**Control.** `finish-task` appends `closed=<key>` to `.last-task-context` after a successful
closeout; `--if-open` compares it to the recorded task and is a no-op on a match, on no task, or
on an ambiguous set of in-flight tasks. `start-task` overwrites the file, so a new task clears the
marker.

---

## Threat: a typed number promotes a pattern to every project

**Probed.** `scripts/test-knowledge.sh` — `--confirmed-in 2` is refused; a project with no memory
on disk is refused; two projects with memories promote with both named.

**Control.** `--confirmed-in` names projects; each must have `_projects/<slug>/memory.md` under
the cache root; the org bullet carries all of them as provenance. Human review of org memory is
unchanged.

---

## Threat: the dispatcher's context carries the specialist's instructions

**Reasoned about.** Wamala's step 4 told it to read the owner's `SKILL.md` to check the `name:`
field, which loaded a thousand-line specialist into the dispatcher's context and then again into
the fresh agent's. The instruction now reads the frontmatter only. This is a prompt-level change;
nothing in the runtime enforces how much of a file a host's read tool returns, so it is an
obligation, not a guarantee.

---

## Findings raised during this review

1. **The secret-boundary probe I first wrote could not fail.** It removed the write boundary and
   expected the evidence field to leak, but the input cleaning still redacted it. A probe that
   passes against the property it means to test proves nothing — the exact trap the v0.37.0
   review recorded. Rewritten to remove the redactor from the module entirely.
2. **A 400-character budget still rendered 483.** The header, the trust line, and one notice do
   not fit in 400. Rendering the frame over a budget it cannot meet is the overrun the fix exists
   to prevent, so a budget below the frame's minimum now renders one line saying so.
3. **The first mutation probes in the new suite used an invalid lesson id** (`p`, shorter than the
   three characters the id rule requires), so `lesson add` failed, the file never existed, and one
   probe read the absent file as "the guard held". Fixed to a valid id; both probes now exercise
   the weakened build.
4. **`finish-task`'s new telemetry fields were asserted with the wrong JSON spacing.** The
   telemetry writer emits `"key":"value"` without a space; the first assertions grepped for
   `"key": "value"` and could never match. Corrected.

## Residual risks

| Risk | Control offered | Why not the default |
| --- | --- | --- |
| A verified definition of done was written by the agent it verifies. | `dod-check` refuses passes without records or on the wrong revision; `code-reviewer` re-runs it; CI is the stronger boundary. | The project runs on many hosts without CI; a local checkable claim beats no claim. |
| Two distinct task keys for one observation count as two. | Pull-request review of the lesson; `doctor` reports counts. | The runtime cannot know two locators are one run. |
| A symlink makes two normalised targets one. | Sequential execution when independence is uncertain; the plan template asks for resources, not only paths. | The decision has no checkout to resolve against. |
| The stop-hook fallback cannot choose between two in-flight tasks. | It records nothing rather than guessing; the agent's own `finish-task` is unaffected. | Guessing wrote memory under the wrong key before `1.0.0-rc.4`. |
| Instruction-level rules (RED with the test present, frontmatter-only dispatch) depend on the model. | The definition of done records what was run; `dod-check` refuses RED without its assertion. | No runtime hook can observe what a host's read tool returned. |

## Related

- [eval-runs/v1.0.0/summary.md](../eval-runs/v1.0.0/summary.md) — the run record.
- [Evidence discipline](evidence-discipline.md) — the rules this release enforces where it can.
- [Known limitations](known-limitations.md#memory-and-evidence) — what it does not claim.
