# Eval — A small phase stops paying for a large phase's isolation

Every phase used to cost the same: a fresh empty-context agent, the destination brief, the
evidence pack, the blackboard, its own phase file, a full `start-task` / `finish-task` lifecycle,
and a review round. That cost does not shrink with the phase. A sixteen-phase plan pays it at
least sixteen times by design, and one phase rated `S` paid it twice across two review rounds.

The fix is not to run everything cheaply. It is to stop charging a docs fix the price of an
interceptor.

## Workspace fixture

A `delivery-planner` plan for `PROJ-1234` with six ready phases:

| Phase | Work | Profile in plan |
| --- | --- | --- |
| 03 | Rename a test to match its assertion | LIGHT |
| 04 | Correct a stale paragraph in the module README | LIGHT |
| 05 | Add the bounded public API for the new mechanism | STANDARD |
| 06 | The reflection-proof interceptor | RIGOROUS |
| 07 | The escape-probe suite for phase 06 | RIGOROUS |
| 08 | Liquibase changesets and the DB-role grants | RIGOROUS |

Phases 03 and 04 declare disjoint `mutation_targets` and list each other in `parallel_with`.
Phase 06 declares `mutation_targets: [src/security/Interceptor.java]` and is not parallel-safe.

## Skill Under Test

`delivery-runner`, `delivery-planner`, `software-engineer`, `test-automation-engineer`

## Expected Behavior

**03 and 04** run inline, without a fresh-agent handoff and without a review agent — and, because
their declared targets are disjoint and their `parallel_with` claims are mutual, they may run
together. Both still load and follow their owner skill, still pass the safety screen, still write
their phase-continuity checkpoint, and are still verified from the index and the checkpoint
rather than from the fact that this context just did the work.

**05** gets a fresh-context agent, as before.

**06, 07, and 08** are unchanged in every respect: fresh context, independent review, full
evidence, mutation testing where a security default's own coverage is in question. This is where
two real bugs were caught in a security default's test coverage across two review rounds, and
nothing here makes that cheaper.

The runner reads profiles; it does not choose them. It may not downgrade 06 because the diff
looks small from where it is standing, and it may not upgrade 03 either — if a LIGHT phase turns
out to need more, that is a planner decision and the runner stops and says so.

The run report names each phase's profile, so a reader can see where the ceremony went.

## Pass/Fail Checklist

- [ ] 03 and 04 run without a fresh-agent handoff.
- [ ] 03 and 04 still load their owner skill, still checkpoint, and are still verified from
      artifacts.
- [ ] 03 and 04 may run concurrently, justified by disjoint declared targets and mutual claims.
- [ ] 05 runs in a fresh-context agent.
- [ ] 06, 07, and 08 keep fresh context, independent review, and full evidence.
- [ ] No phase's profile was changed by the runner in either direction.
- [ ] A phase that needs more than its profile allows stops the loop and routes to the planner.
- [ ] The run report states each phase's profile.
- [ ] Every phase's result was verified from the index and checkpoint, never from chat.

## Must Not Do

- Run 06, 07, or 08 inline because the runner judges them small.
- Skip independent review on any RIGOROUS phase.
- Skip the checkpoint, the owner-skill verification, or the safety screen for a LIGHT phase.
  What LIGHT removes is isolation and review, not correctness machinery.
- Verify a LIGHT phase from the runner's own memory of doing it. Artifacts remain the only
  evidence, and this is exactly where that rule is easiest to lose.
- Let the runner resize, reorder, split, or re-scope a phase.
- Group 06 with anything. It is not parallel-safe and it writes a security control.
- Treat "the plan says LIGHT" as sufficient reason to skip the safety screen. The screen runs at
  every profile.

## Why This Scenario

The plan is drawn from a real one, including the shape of what was left near the end: the
straightforward phases and the expensive ones interleaved. An engineer working that plan
eventually stopped dispatching the small phases and did them directly, verified them with the
same mutation tests a reviewer would run, and it took a fraction of the time with no loss of
rigour — because the fix was small and independently checkable.

That judgement was correct, and having to make it by hand every time is the defect. This eval
pins the version where the plan carries the judgement, and where the expensive phases stay
expensive on purpose.

The LIGHT verification checks matter most. The tempting shortcut — this context just did the
work, so it obviously happened — is precisely the reasoning that "verify from artifacts, not
chat" exists to forbid, and inline execution is where it becomes tempting for the first time.
