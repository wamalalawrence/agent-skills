# Eval — An hour of work must not be able to produce nothing

A mechanism-selection dispatch bundled four deliverables into one brief and ran for roughly an
hour before being killed. It had written no artifact, no hypothesis, no partial answer. The retry
started from zero, so the hour bought nothing at all.

Two things failed. The brief was overscoped, which is partly a human error. But nothing forced
incremental progress and nothing was watching, so a bad brief could burn an hour silently — and
that is a defect in the defaults, not in the person who wrote the brief.

## Scenario

Four runs against `example-api`, evaluated at fixed points.

- **A — the reported case.** A brief bundling four deliverables. Expected effort 15 minutes.
  At 60 minutes elapsed the task has recorded no milestone of any kind.
- **B — early quiet.** The same 15-minute budget, 8 minutes elapsed, nothing recorded yet. The
  agent is reading the brief and orienting.
- **C — over budget, still producing.** A 5-minute budget, 40 minutes elapsed, and milestones
  recorded at 5, 12, 22, and 38 minutes. The work is bigger than someone thought.
- **D — gone quiet mid-run.** A 15-minute budget, 20 minutes elapsed, last milestone at
  12 minutes.

## Skill Under Test

`delivery-runner`, `issue-investigator`, `delivery-planner`

## Expected Behavior

**A** reaches `stop`. Sixty minutes against a fifteen-minute budget with nothing persisted is not
a task that needs more time; it is a brief that cannot produce anything. The runner stops the
loop and hands back rather than retrying.

**B** continues. The first milestone is allowed longer than a mid-run gap, because an agent has
to read the brief, orient in the repository, and form a hypothesis before it has anything worth
recording. A watchdog that fires here trains people to switch it off.

**C** reaches `split` — and specifically **not** `stop`. This is the property the whole design
turns on: work that is still writing milestones at eight times its budget is not stuck, it is
mis-sized. Killing it would destroy exactly the careful work the rigour exists to protect. The
runner stops its loop and routes back to `delivery-planner`, because re-scoping a phase is
planner work.

**D** reaches `narrow`. Progress happened and then stopped, past the stall window but inside
twice the budget. The response is to narrow to the next single checkable step.

Throughout, the executing agent writes milestones as it goes — initial understanding, then
evidence, then verification — rather than one artifact at the end. An interrupted run leaves
behind what it had already learned.

Verdicts are distinguishable by exit code: `continue` 0, the reassessment family 10, `stop` 20.

## Pass/Fail Checklist

- [ ] A stops, and the reason names both the elapsed time and the absence of any milestone.
- [ ] A is not retried with the same brief.
- [ ] B continues, and the settling window before a first milestone is explained rather than
      implied.
- [ ] C splits rather than stopping.
- [ ] C's handling routes re-scoping to `delivery-planner` instead of the runner resizing a phase.
- [ ] D narrows, naming the gap since the last milestone.
- [ ] Milestones were written during execution, not assembled at the end.
- [ ] An interrupted run leaves readable progress behind.
- [ ] Milestones are meaningful steps, not a per-action log.
- [ ] The same inputs produce the same verdict every time.

## Must Not Do

- Kill C because it is over budget. Elapsed time alone never produces a stop while milestones
  keep landing — a hard timeout kills careful work along with stuck work and teaches everyone to
  pad their estimates.
- Fire on B and interrupt an agent that is working.
- Retry A unchanged. The same brief produces the same hour.
- Let the runner re-scope, resize, split, or reorder a phase itself.
- Record a checkpoint every few seconds to look busy. Noise hides the stall it was meant to
  reveal.
- Treat the absence of an explicit progress entry as no progress when durable facts, decisions,
  or artifacts were written — those already count as motion.
- Introduce a polling supervisor process. The verdict is a pure function of what is on disk;
  a daemon would add orphaned children and stale locks to a release whose purpose is stability,
  and could not observe a sub-agent it did not spawn.

## Why This Scenario

The distinction between C and A is the entire design. Both are far past budget. One is working
and one is stuck, and only the progress ledger can tell them apart — which is why the ledger and
the watchdog had to ship together. A timeout would have handled A correctly and destroyed C,
and C is the case where the work is genuinely hard: nine mechanism candidates against
twenty-three escape probes is not overhead, it is the problem being harder than the ticket looked.

B is here because a watchdog that interrupts working agents gets disabled within a week, and a
disabled watchdog catches nothing.
