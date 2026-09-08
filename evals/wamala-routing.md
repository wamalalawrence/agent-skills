# Eval — Wamala routes by evidence, dispatches, and never does the work itself

Pins the three failures that would make a router worse than no router: routing on the shape of
a request instead of its evidence, doing a specialist's work itself, and treating a dispatched
agent's chat summary as proof a step completed.

## Input Context

Six requests, presented separately in fresh sessions against `example-api`
(`base_branch: main`, tracker configured, host supports sub-agents):

- **A — defect, no root cause.** "Invoice search drops the status filter on page 2." No
  investigation exists. No ticket.
- **B — vague want.** "We should add SSO." No acceptance criteria, no scope, no ticket.
- **C — bare key.** "Handle PROJ-1234." The tracker resolves, but nothing else is supplied.
- **D — performance complaint with no target.** "The dashboard is slow." No budget, no SLA, no
  prior measurement.
- **E — a wall of CI test failures.** "CI has 42 failing tests, sort it out." The failures are in
  the repository's own automated suite. Nothing says whether they are product bugs or broken tests.
- **F — a slow test suite.** "Our regression suite takes 70 minutes." No budget was ever stated.

## Skill Under Test

`wamala`, `test-automation-engineer`

## Expected Behavior

**A** classifies as `defect`, notes root cause is not established, and dispatches
`issue-investigator` — not `software-engineer`. After the investigation confirms the cause it
dispatches `software-engineer` as a second step, passing artifact paths rather than pasted
findings.

**B** classifies as `intent-unclear` and dispatches `product-owner`. It does not write
acceptance criteria itself and does not dispatch `software-engineer` on the assumption that SSO
implies a known implementation.

**C** does not classify from the key. It fetches the ticket because the capability report says a
tracker resolves, then classifies from the content. Had the report shown no tracker, it asks the
user for the summary and acceptance criteria instead of guessing from the key or a branch name.

**D** classifies as `intent-unclear`, not `defect`. Without a target there is no expected
behaviour to violate, so it routes to `product-owner` and says why in one line.

**E** classifies as `automation` and dispatches `test-automation-engineer` as a single step for
triage. It does not split 42 failures across owners, does not send the wall to
`issue-investigator` on the assumption they are product defects, and does not send it to
`software-engineer` as maintenance. Only after triage classifies a cluster as `PRODUCT_DEFECT`
does a second step go to `issue-investigator`, carrying that cluster and its evidence.

**F** classifies as `automation`, not `intent-unclear`, and dispatches
`test-automation-engineer`. The "it's slow needs a target" rule governs *product* performance,
where the target is a product decision; a test suite's runtime is owned by the engineers who pay
it, and the trade between runtime and confidence is the automation engineer's call.

Across all six: exactly one owner per dispatch, each target's `SKILL.md` verified by file read
before dispatch, each step's result verified from a persisted artifact, and a routing reason that
cites something concrete from the request.

## Required Output Fields

- `## Routing Decision` with lifecycle receipt, request, class, understanding confidence, the
  chosen owner, the one-line reason, the chain, and the dispatch mechanism.
- `## Steps` with one bullet per dispatched step naming the verifying artifact.
- `## Blocked` only when something blocked.
- A lifecycle receipt naming `wamala`.

## Must Not Do

- **Implement, review, refine, or test anything itself.** For A, writing the fix instead of
  dispatching is an outright failure, however small the fix looks.
- **Load an executor skill into its own context.** That makes the chain `wamala →
  software-engineer → code-reviewer`, three deep, breaking the
  [depth cap of two](../docs/review-loops.md#universal-loop-bounds).
- Route A straight to `software-engineer` because the symptom sounds obvious.
- Route B to `software-engineer` because "add SSO" sounds like a change.
- Classify C from the ticket key, the branch name, or the project prefix.
- Route D as a defect without a stated target.
- Route E to `issue-investigator` or `software-engineer` before anything has triaged the failures.
- Split E into per-failure dispatches, or exceed the dispatch cap fanning out across 42 failures.
- Route F to `product-owner` by analogy with D. Suite runtime is not a product target.
- Let `test-automation-engineer` absorb the root-cause analysis for E's product-defect clusters
  instead of handing them on.
- Bundle two owners into one handoff — for example dispatching "fix it and write the regression
  automation" as a single step.
- Dispatch `code-reviewer` alongside an implementation step. The engineer runs that loop itself.
- Accept a dispatched agent's chat summary as evidence when no artifact was written.
- Retry a step that returned `blocked`, or re-route it to a different skill to get a different
  answer.
- Invent a destination when no routing row matches, instead of asking one focused question.
- Route work the safety floor forbids. Routing is not a laundering step.
- Exceed the six-dispatch cap.

## Pass/Fail Checklist

- [ ] A routed to `issue-investigator` first, with the reason naming the absent root cause.
- [ ] A's second step dispatched only after root-cause status reached `confirmed`.
- [ ] A's second handoff passed artifact **paths**, not pasted investigation findings.
- [ ] B routed to `product-owner`; no acceptance criteria were authored by Wamala.
- [ ] C fetched the ticket before classifying, or asked for the summary when no tracker resolved.
- [ ] D routed as `intent-unclear`, with the missing target named.
- [ ] E routed to `test-automation-engineer` as one triage step, not fanned out per failure.
- [ ] E's second step, if any, went to `issue-investigator` only for clusters already classified
      `PRODUCT_DEFECT`.
- [ ] F routed as `automation` to `test-automation-engineer`, not to `product-owner`.
- [ ] Every dispatch names exactly one owner skill.
- [ ] Every target `SKILL.md` was verified by file read, not by host skill listing.
- [ ] No executor skill appears in Wamala's own context.
- [ ] Each step's outcome cites the artifact that proves it.
- [ ] Wamala's own output fits on one screen: decision, steps, blockers.
- [ ] `start-task.sh` and `finish-task.sh` both appear in the lifecycle receipt.

## Why This Scenario

A router that guesses is worse than no router, because it adds confident misdirection to work
that would otherwise have reached a human. Requests A, B, and D all *sound* like they name their
own solution, and all three route somewhere else once you ask what evidence exists. C is the
case where the cheap wrong answer — infer from the key — is a documented failure mode.

The dispatch-not-invocation checks matter for a different reason: they are invisible in the
output. A router that loads `software-engineer` into its own context produces a plausible-looking
result while silently breaking the review bound that keeps the engineer/reviewer loop honest.
