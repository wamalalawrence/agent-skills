# Eval: routing a large input, and not paying for it twice

Context Optimizer is a runtime available to every skill **and** a skill of its own. Getting that
split wrong is the failure this eval catches — in both directions. Routing everything through the
skill adds a dispatch and a whole agent's context to save one command. Never routing to it means the
judgement about what survived compression never gets made.

## Skill Under Test

`wamala` routing to `context-optimizer`, plus `issue-investigator`, `code-reviewer`, and
`test-automation-engineer` using the runtime directly.

## Setup

A repository with four large artifacts on disk, all past the threshold: a 200 MB application log, a
2 GB regression-suite log, a 40,000-line diff, and an 800-table schema dump. `agent-skills` is
installed globally, so `agent-skills context ...` resolves.

## Scenario 1 — the pack is the deliverable

Request: *"Extract what matters from this 200 MB log for the payment failure on transaction 84721."*

### Expected agent behavior

- `wamala` classifies this `oversized-input` and dispatches `context-optimizer`. Reducing the
  evidence **is** the deliverable, so the skill owns it.
- One dispatch, one owner. Not a chain.
- The routing reason names something concrete from the request, not the destination's name.

## Scenario 2 — the pack is a step, not the deliverable

Request: *"Payments are failing. Here is the log."* (same 200 MB file attached)

### Expected agent behavior

- `wamala` classifies this `defect` and dispatches `issue-investigator`. The deliverable is a root
  cause; the pack is that skill's first step.
- `issue-investigator` runs `agent-skills context pack` **itself**. It does not dispatch a second
  agent to shrink the file.
- Routing to `context-optimizer` first is a fail. It adds a dispatch, a fresh agent's context, and a
  handoff, to save one command — and it deepens the chain the depth cap exists to bound.

### Fail modes this catches

- Routing every request that mentions a large file to `context-optimizer`.
- `issue-investigator` reading the 200 MB log whole because "the router did not tell me to pack it".
- A three-deep chain: `wamala` → `context-optimizer` → `issue-investigator`.

## Scenario 3 — the reviewer packs its own diff

Request: *"Review this branch. It is 40,000 lines, mostly regenerated clients."*

### Expected agent behavior

- `wamala` routes to `code-reviewer`, which owns the verdict. A pack without a verdict is half an
  answer.
- `code-reviewer` packs the diff itself, reads the changed-file map first, and reviews the
  task-relevant and security-sensitive hunks.
- Its output carries the completeness statement: the review covered N of M hunks, and the rest are
  represented only by the map. A `PASS` that implies the whole diff was read is a fail.

## Scenario 4 — a wall of CI failures

Request: *"CI has 42 failures and the suite log is 2 GB."*

### Expected agent behavior

- `wamala` routes to `test-automation-engineer` as **one** step. Triage owns this.
- That skill packs the log itself with a brief about the first failure, and its triage separates the
  root failure from the cascade rather than reporting 42 problems.
- Only clusters it classifies `PRODUCT_DEFECT` are handed on to `issue-investigator`, with the
  evidence that classified them.

## Scenario 5 — the same input across a chain

A `delivery-planner` plan whose phases 2, 3, and 5 all need evidence from the same 200 MB log, each
executed by a fresh agent.

### Expected agent behavior

- The first phase to pack the log records the **pack id and path** in the phase artifacts.
- Later phases with the same question reuse that pack rather than recompressing the file. The pack
  is deterministic, cached, and already redacted.
- A phase asking a *different* question builds a new pack, and the differing pack id makes that
  visible and correct.
- If the source changed between phases, the reuse does not happen and nothing has to notice
  manually — the pack id is derived from the source hash. An agent that hand-checks timestamps
  instead is doing work the runtime already did.
- The handoff carries the pack id, not a paraphrase of what the pack said.

### Fail modes this catches

- Three fresh agents each spending 90 seconds and a full inspection pass on the same unchanged file.
- Phase 5 reusing phase 2's pack after the log rotated, and reporting stale evidence.
- A handoff that summarises the evidence in prose, losing every line range with it.

## Pass criteria

| No. | Criterion |
| --- | --- |
| 1 | "Extract what matters from X" routes to `context-optimizer` as a single step. |
| 2 | "Payments are failing, here is the log" routes to `issue-investigator`, not to the optimizer. |
| 3 | No chain is three deep. `wamala` never loads an executor into its own context. |
| 4 | Executors call `agent-skills context pack` themselves rather than dispatching for it. |
| 5 | `code-reviewer` owns the verdict and states the review's completeness. |
| 6 | A CI failure wall is one triage step, and the cascade is identified as such. |
| 7 | A pack id is recorded in the phase artifacts, and reused across phases with the same brief. |
| 8 | A different brief produces a different pack; a changed source is never reused. |
| 9 | Handoffs carry the pack id and path, never a paraphrase without provenance. |
| 10 | Routing reasons cite something concrete from the request. |

## Why this eval exists

The architecture is two layers on purpose: a runtime every skill can call, and a skill for when the
judgement is the work. Both halves are cheap to get wrong in a way that looks reasonable — a router
that sends every big file to the optimizer looks thorough, and an investigator that reads a 200 MB
log looks diligent. This eval pins the boundary between them, and pins the reuse that makes the
capability worth having in a chain rather than only in a single session.
