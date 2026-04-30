# Skill review loops (v0.22.0)

## Problem

`software-engineer` has had explicit `code-reviewer` inner-loop and outer-loop calls since
v0.7. Every other skill in this repo emits an artifact that downstream skills (or humans)
act on — but the artifact was **never reviewed by a peer skill** before being declared
done. A user-facing transcript made the failure mode concrete:

- `issue-investigator` produced a confident root cause that the next-step recommendation
  could not actually justify (recommendation was `code fix`, evidence supported only
  `monitoring or alerting improvement`).
- `product-owner` emitted a "Jira-ready story" with one acceptance criterion phrased
  "system handles the edge case gracefully" — neither testable nor observable.
- `manual-tester` filed a defect against assumed expected behavior; the "defect" was
  actually a product question.
- `test-automation-engineer` proposed a UI/e2e test with `cy.wait(2000)` to "let the page
  settle" — exactly the anti-pattern the skill's own Guardrails forbid.

In every case the producer skill had a checklist that, if applied as a self-review pass,
would have caught the issue. The checklist existed; the **pass** did not.

## Risk we deliberately did not introduce

The naive fix is "have skill A review skill B's output, then have skill B review the
revised output, then …". Without explicit bounds, two skills can ping-pong inside a
single agent invocation until the context window runs out. The user's request explicitly
flagged this — *"without the risk of introducing some kind of endless loop"*.

## Mechanism

[`docs/review-loops.md`](../../docs/review-loops.md) defines the bounds as a single
written contract:

1. One revision round per loop by default.
2. Reviewer never edits the producer's artifact; it returns findings.
3. `blocker` findings stop the loop; the producer hands off to a human after one revision.
4. No skill invokes itself recursively.
5. Loop depth cap of two skills (producer → reviewer → at most one helper).
6. Persistent artifacts (evidence pack, DoD JSON) are the handoff medium, not chat.

The `software-engineer` ↔ `code-reviewer` loops keep their existing
`${CODE_REVIEWER_MAX_ROUNDS}` cap (default `3`) with a strictly-decreasing
`blocker`+`major` count per round; that is the only documented exception to the
"one round" default.

Each producer skill was updated:

- `issue-investigator` — new step 7 "Self-validation pass (bounded)" runs the new
  [investigation-quality checklist](../../docs/review-loops.md#investigation-quality-checklist)
  once, before emitting the result.
- `product-owner` — new "Bounded review pass (one round)" between the existing DoR gate
  and step 7 (Jira-ready output). Asks `manual-tester` for a testability quick-check on
  user-facing/behavior-complex work.
- `manual-tester` — new step 7 "Self-validation pass (bounded)" runs the new
  [test-plan review checklist](../../docs/review-loops.md#test-plan-review-checklist) once.
  Defects that fail the `issue-investigator` handoff become `product question` instead of
  `functional defect`.
- `test-automation-engineer` — the existing `code-reviewer` (`manual` mode,
  `test-quality` profile) call in step 6 is now explicitly tagged as a one-round bounded
  loop with a pointer to the shared bounds doc.

## Verification

- `python3 scripts/validate-repo.py` exits 0 with the same warning class as v0.21.0.
- `python3 scripts/validate_skills.py` exits 0 with the same warning class as v0.21.0.
- The four new "Bounded" sections all link back to
  [`docs/review-loops.md`](../../docs/review-loops.md), so a reader of any single
  SKILL.md can find the binding rules without searching the repo.
- The depth cap is enforced by writing, not by code: a skill that already reaches the
  cap (e.g. `code-reviewer` invoking `issue-investigator`) is documented as a "helper"
  call, not a new review loop.

## What this does NOT do

- It does not replace the human in the loop. Each terminating exit (`Open Questions`,
  `Follow-ups`, `Spike` / `Discovery`, `product question`) explicitly hands surviving
  ambiguity back to the user, not to another agent round.
- It does not enforce loop bounds at runtime. The repo cannot run other people's agents;
  the bounds are written as binding contract in SKILL.md and the shared doc, the same
  mechanism by which the rest of the skill workflow is enforced.
