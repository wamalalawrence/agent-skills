# Verification Bars

What "done" looks like, per class, when Wamala verifies a step from its artifacts.

Engineering already had a high bar: a `definition-of-done.json` that `agent-skills dod-check`
accepts, plus a PR URL. Everything else was judged by "the artifact exists, is populated, and its
status says so". For prose that is a low bar. A refinement with an empty acceptance-criteria
section and `READY` at the top passes it, and so does an audit whose findings cite nothing.

Each bar below is checkable by **reading** the artifact. Nothing on this page asks Wamala to judge
whether the work is good, which belongs to the owner and to any reviewer. What Wamala checks is
whether the work is **complete in the shape its owner promised**. Every bar also includes the
common floor.

## Common floor (every class)

- The artifact is at the path the brief named, or at the path the step's final message named.
- It carries an outcome of `done`, `blocked`, or `needs-context`. For a phase, the checkpoint
  state and the index row agree.
- A `blocked` outcome names the missing thing and who supplies it.
- No credential-shaped value appears in it. Run it through `agent-skills redact --check` when
  unsure.

## Per class

### `defect`, investigation

**Done:** Root-cause status (`confirmed`, `suspected`, `unknown`, or `disproved`), expected versus
actual with sources, and a reproduction recipe or the reason there is none.

**Not done:** The cause is asserted with no cited evidence, or the status is missing.

### `defect` or `change`, implementation

**Done:** A `definition-of-done.json` that `dod-check` verifies, a commit or PR, and
`review.independence` recorded.

**Not done:** `dod-check` fails, the closeout reads `NOT verified`, or the review is
`same-context` with no sibling review scheduled.

### `intent-unclear`, refinement

**Done:** Acceptance criteria that are each testable, scope and out-of-scope, and a readiness
decision whose reason names what closed the gap.

**Not done:** Criteria that restate the request, or `READY` with open questions still listed.

### `question`

**Done:** The answer in the shape the output contract asked for, each claim traceable to a source
at a named path.

**Not done:** An evidence trail instead of an answer, or an answer with no source.

### `design-review`

**Done:** The standard it was measured against, or an explicit "no stated standard". Each finding
says where it was observed (page, viewport, state) and carries evidence (a screenshot path or a
measured value). Defects are kept apart from usability observations.

**Not done:** Findings with no location or evidence, a verdict with no standard, or any edit to
the thing reviewed.

### `review` of a diff

**Done:** A verdict, findings with severity and file and line, and the diff range reviewed.

**Not done:** A verdict with no range, or findings with no location.

### `validation`, manual

**Done:** Scenarios executed with results, the environment and build, and defects filed with
expected versus actual.

**Not done:** Scenarios planned but not run, reported as done.

### `automation`

**Done:** The suite command run and its result, the level chosen per behaviour, and every failure
classified.

**Not done:** Tests written but never run, or a failure left unclassified.

### `oversized`, planning

**Done:** `destination.md`, an index at `READY_FOR_DISPATCH` or a readiness that names what is
missing, and one owner per phase.

**Not done:** Phases with no exit criterion, or two owners on one phase.

### `plan-amendment`

**Done:** The index `updated_at` moved; each changed phase says what changed and why; superseded
phases are `skipped` with a reason, not deleted; the pointer is recomputed.

**Not done:** The answers live only in chat, or a phase was edited with no trace of what it said
before.

### `terminology`

**Done:** The glossary entry or ADR at its path, with the decision, the alternatives, and the
reason.

**Not done:** An ADR with no rejected alternative.

### `oversized-input`

**Done:** A pack id whose omissions report is present and whose budget was honoured.

**Not done:** A summary with no provenance.

## Delete-shaped steps

On top of their class bar: the `agent-skills reversibility` report for every target, and either
the targets archived at the stated path or the user's explicit go-ahead to delete, quoted from
this conversation. A delete that was not recoverable, and was carried out anyway, is a failed
step whatever else it achieved.

## When the bar is not met

Handle it the same as a missing artifact. Retry **once**, and tell the step exactly which part of
the bar is unmet. If the second attempt still misses it, stop with
`BLOCKED: step did not meet the <class> verification bar` and name the part. Do not lower the bar
to fit what came back.
