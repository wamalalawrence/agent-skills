# Eval: Delivery Planner Phase Continuity

**Skills under test:** `delivery-planner`, `software-engineer`, `issue-investigator`,
`product-owner`, `manual-tester`, `test-automation-engineer`.

**Targeted failure mode:** a planner produces useful phase files, but after a fresh agent implements
phase 1 there is no durable `evidence-pack.yml` update. The next agent has no reliable record of
what phase finished, what artifacts were produced, what validation ran, or which phase is next.

## Input Context

A user asks `delivery-planner` to split a medium feature into three phases. No prior
`evidence-pack.yml` exists. The planner writes:

```text
${AGENT_SKILLS_CACHE_DIR}/EXAMPLE-123/
├── destination.md
└── phased-plan/
    ├── README.md
    ├── phase-01-confirm-contract.md
    ├── phase-02-implement-api.md
    └── phase-03-add-regression-tests.md
```

Then the user starts a fresh agent with only:

```text
Implement phase 1 from ${AGENT_SKILLS_CACHE_DIR}/EXAMPLE-123/phased-plan/phase-01-confirm-contract.md
```

## Expected Behavior

- `delivery-planner` creates `${AGENT_SKILLS_CACHE_DIR}/EXAMPLE-123/evidence-pack.yml` in the same
  run as the Markdown plan files.
- The evidence pack includes `delivery_plan.destination_path`, `index_path`,
  `current_dispatch_pointer: phase-01`, and all three `phases[]` entries. Phase 2 is `ready` with
  `prerequisites: [phase-01]`, not `provisional`, when no discovery gate remains.
- The phase 1 executor opens `evidence-pack.yml` before work. If it is missing, it reconstructs a
  minimal `delivery_plan` from the index and phase files, or stops with
  `BLOCKED: phase continuity evidence-pack missing`.
- Before material work, the executor marks phase 1 `in-progress` and re-reads the evidence pack.
- Before final output, the executor writes a phase-continuity checkpoint:
  `state: done` or `blocked`, timestamp, owner skill, `completion_summary`, `artifacts`,
  `validation`, `follow_up_context`, top-level `last_completed_*` or `last_blocked_*`, and
  `last_continuity_checkpoint_at`.
- The executor recomputes `delivery_plan.current_dispatch_pointer` to `phase-02` when phase 1 is
  done and phase 2 prerequisites are satisfied.
- The executor's final response names the evidence-pack path, updated phase id, resulting state,
  and new dispatch pointer.

## Must Not Do

- Must not claim phase 1 is complete based only on chat transcript text.
- Must not leave `current_dispatch_pointer` pointing at phase 1 after phase 1 is done.
- Must not skip the checkpoint because the code/test work succeeded.
- Must not require the user to rerun `delivery-planner` just to learn what phase is next.
- Must not invent a new cache location or write continuity into a one-off summary file.

## Pass / Fail Checklist

- [ ] Planner-created greenfield plans include `evidence-pack.yml`.
- [ ] Executor refuses or reconstructs when the evidence pack is missing; it does not proceed
  silently.
- [ ] Phase completion writes durable summary, artifact, validation, and follow-up context.
- [ ] `last_completed_*` / `last_continuity_checkpoint_at` mirrors are updated.
- [ ] `current_dispatch_pointer` advances to the next ready phase or becomes `null` with an
  explicit blocker reason.
- [ ] A fresh agent can continue from `evidence-pack.yml` without reading the previous chat.
