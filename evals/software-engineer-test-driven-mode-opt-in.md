# Software Engineer Eval: Test-Driven Mode Is Opt-In

Test-driven mode buys stronger tests at several times the tokens of the default path, so it runs
only when someone asks for it. This eval checks both halves: asked, the loop is real; not asked —
including at `RIGOROUS` — nothing of it appears.

## Skill Under Test

`software-engineer`

## Input Context

The task in every scenario: implement `bowlingScore(rolls)` for ten-pin bowling in a TypeScript
repository whose test runner supports `it.todo`. The acceptance criteria carry literal examples:
twenty gutter balls score 0; twenty rolls of 1 score 20; a spare followed by a 3 scores 16 over
those three rolls; a strike followed by 3 and 4 scores 24 over those three rolls; a perfect game
scores 300. Requirement-understanding confidence is `high`.

### (a) Asked

The user writes: "Use TDD for this."

### (b) Not asked

The user writes: "Implement the bowling score function with tests." Execution profile `STANDARD`.

### (c) RIGOROUS, not asked

The same request as (b), but the brief says execution profile `RIGOROUS`. Nobody mentions TDD or
test-first.

## Hidden Acceptance Checks

Run by the evaluator against the delivered code; not shown to the agent.

- A game of all spares with a final bonus roll of 5 (21 rolls of 5) scores 150.
- Nine strikes followed by a final frame of 9 and a miss scores 267.
- A strike in the tenth frame followed by two bonus strikes, after nine open frames of 0, scores 30.
- Ten open frames of 9 and a miss each (twenty rolls alternating 9 and 0) score 90.

## Expected Behavior

**(a)** Before any production code, shows a test list derived from the examples, each added
inactive with `it.todo`, ordered simplest first (gutter game before spare, spare before strike,
perfect game last). Because confidence is `high`, it carries on without waiting for approval.
Each cycle activates one test and writes a one-line prediction before running it. If a test
passes on activation — the perfect game may, once strike handling is complete — records it as
`already-passing` and changes nothing to make it fail. Refactors only while green.
Logs one line per cycle to the evidence pack's `tdd` block rather than narrating cycles in chat.
The delivered function passes the hidden acceptance checks.

**(b)** Follows the default Phase 2: test design, implementation, tests. No test list shown, no
per-run predictions, no `tdd` block, no cycle log.

**(c)** Same as (b). The `RIGOROUS` profile raises review and evidence depth, and mutation testing
where a tool exists, but does not enter test-driven mode.

## Must Not Do

- Must not enter test-driven mode in (b) or (c), or describe the default work as TDD.
- Must not, in (a), stop for approval of the test list at `high` confidence.
- Must not, in (a), edit a test or the code to force a failure for a test that already passes.
- Must not, in (a), run the code-reviewer loop once per cycle.
- Must not hand refactoring to a separate agent in (a).

## Pass/Fail Checklist

- [ ] (a): the test list comes first, inactive, simplest first.
- [ ] (a): one prediction per test run; one behaviour per cycle.
- [ ] (a): if a test passes on activation, it is recorded as `already-passing`, not forced red.
- [ ] (a): the hidden acceptance checks pass.
- [ ] (b): no test-list ceremony and no `tdd` block.
- [ ] (c): `RIGOROUS` alone does not enter the mode.
