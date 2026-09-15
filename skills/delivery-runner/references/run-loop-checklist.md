# Run-Loop Checklist

The single pre-flight plus per-iteration self-check `delivery-runner` applies.
It is bounded: the checks below run once before the loop and once per dispatched
phase. They never trigger their own review loop and never re-plan.

## Before the loop (once)

- [ ] `start-task.sh --skill delivery-runner=<version>` ran.
- [ ] The task cache dir is resolved and contains both
      `phased-plan/README.md` and `destination.md`.
- [ ] `delivery-run-next.py "<cache-dir>/<work-key>"` returns `action: dispatch`
      (not a first-decision `stop` / `error`). If it stops, report and exit —
      there is nothing to run autonomously.
- [ ] No phase is `in-progress` from another active agent/runner (concurrency
      guard). If one is, confirm with the user before resuming.
- [ ] The dispatch mechanism is known (sub-agent, CLI, or human-relayed), and it
      works from **here**: a runner that was itself dispatched confirmed it can
      open a fresh agent, or stopped with `BLOCKED: nested dispatch unavailable`.

## Per iteration (per phase)

- [ ] Re-ran `delivery-run-next.py`; acted on its `action`
      (`dispatch` / `stop` / `error`).
- [ ] For `dispatch`: the `recommended_owner` `SKILL.md` was loaded by file read
      from the canonical skill source and its `name` matches.
- [ ] The phase file was safety-screened (no forbidden destructive action, no
      discovered-credential use, not an operator runbook).
- [ ] The handoff prompt was built from the
      [handoff-prompt template](./handoff-prompt-template.md) with correct
      pointers and the single-phase constraint, and with
      `phase.prerequisite_context` pasted under **Carried forward**.
- [ ] A fresh-context agent was dispatched (the runner did not do phase work in
      its own context).
- [ ] The result was verified from the index + checkpoint, not from chat:
      - done/skipped + pointer advanced + non-empty validation → continue;
      - `blocked` → stop the loop, surface the reason, no auto-retry;
      - `blocked` because the phase's own criterion cannot hold → stop with
        `plan-defect` and the evidence, for the planner;
      - `done` with independent review required and `review.independence` not
        `fresh-context` → schedule a sibling `code-reviewer`; report it owed;
      - no checkpoint / pointer unchanged → retry this phase once, then stop;
      - index ↔ evidence-pack mismatch → stop `BLOCKED: phase index out of sync`.
- [ ] One line of progress was recorded; the runner's context stayed lean.

## Loop guards

- [ ] Iteration count is below `total_phases + retry_budget`.
- [ ] No pointer has recurred past its retry budget without a state change.
- [ ] The plan is not `superseded` (if it is, stop and route to the planner).

## After the loop (once)

- [ ] `finish-task.sh` ran once with a one-sentence summary and the correct
      `--status` (`blocked` / `needs-context` preserve scratch).
- [ ] The run report names every dispatched phase, its result, and — when
      stopped — the exact phase and reason.
