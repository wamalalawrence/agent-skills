# Eval: Plan Index Regenerated After Each Phase

**Skills under test:** every `recommended_owner` skill (`software-engineer`,
`issue-investigator`, `product-owner`, `manual-tester`, `test-automation-engineer`), plus the
[plan-index template](../skills/delivery-planner/references/plan-index-template.md) and the
[phase-continuity checkpoint](../skills/software-engineer/references/evidence-pack.md#phase-continuity-checkpoint).

**Targeted failure mode:** after phase 1 finishes, the executor writes a clean phase-continuity
checkpoint to `evidence-pack.yml`, but `phased-plan/README.md` is not regenerated. Phase 2's
state stays `ready`, the `current_dispatch_pointer` in the README still points at `phase-01`,
and `last_completed_phase_id` lags. A user who hands a new agent only the README — a common
hand-off pattern — sees stale dispatch state and either re-runs phase 1 or asks for the
"next" step that the README still claims is phase 1.

The user has already reported this exact pattern: phase 1's index updated correctly because
the planner regenerated it during the first run, but phase 2+ left the index frozen.

## Input Context

A user runs `delivery-planner` against a five-phase plan. Phase 01 dispatches and finishes;
the planner regenerates `phased-plan/README.md` on its own next run. Then the user opens a
fresh agent and says:

```text
Run the next phase.
```

The agent reads `evidence-pack.yml`, sees `current_dispatch_pointer: phase-02`, runs phase
02, and writes a complete phase-continuity checkpoint. The user does **not** re-run
`delivery-planner` between phases.

## Expected Behavior

- After writing the phase-02 checkpoint to `evidence-pack.yml`, the executor regenerates
  `phased-plan/README.md` from the updated evidence pack as part of the same response, before
  emitting the user-facing summary.
- The regenerated README updates:
  - The phase table's `State` column (phase-02 → `done`, the next ready phase if any).
  - The YAML header's `last_completed_phase_id`, `last_completed_at`, `last_completed_by`,
    `current_dispatch_pointer`, and `updated_at`.
  - The `totals` block (`done` count, `ready` count, etc.).
  - The `Inputs for the next agent` section so it now points at the new
    `current_dispatch_pointer`'s phase file.
- The regenerated README is **derived** from the evidence pack: phase rows do not change
  `id`, `slug`, `recommended_owner`, or `Prereqs`. The executor MUST NOT add, delete,
  reorder, rename, or resize phases — those are planner-only operations.
- The user-facing final response names both files: the `evidence-pack.yml` path AND the
  regenerated `phased-plan/README.md` path.

## Must Not Do

- Must not finish phase 2 with the README still showing phase-01 as
  `current_dispatch_pointer`. That single mismatch causes the next agent to redo work or get
  confused about state.
- Must not require the user to re-run `delivery-planner` between phases just to refresh the
  index. The planner regenerates *plan shape*; the executor regenerates the index from
  *plan state*.
- Must not invent a new phase row, rename an existing phase, or change a phase's
  `recommended_owner` while regenerating the index. If the evidence pack and per-phase files
  disagree, stop with `BLOCKED: phase index out of sync with evidence pack` and surface the
  diff.
- Must not skip the regeneration when the phase result is `blocked`. Blocked phases also
  need to flip `state: ready → blocked` and update `current_dispatch_pointer` to `null` or
  the next dispatchable phase.

## Pass / Fail Checklist

- [ ] `phased-plan/README.md`'s `updated_at:` advances on every phase completion.
- [ ] The phase table's `State` column reflects the latest evidence-pack values.
- [ ] `current_dispatch_pointer` in the README matches `evidence-pack.yml.delivery_plan`.
- [ ] `last_completed_*` mirrors are present in both files and agree.
- [ ] `totals` add up to `total` and reflect the latest counts.
- [ ] The `Inputs for the next agent` section updates the current phase file pointer.
- [ ] No phase rows added, removed, or renamed by an executor's regeneration pass.
- [ ] User-facing output cites both `evidence-pack.yml` and `phased-plan/README.md` paths.
