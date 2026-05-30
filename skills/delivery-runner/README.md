# delivery-runner

Autonomous phase-by-phase executor for a [`delivery-planner`](../delivery-planner/)
plan. It walks the phased plan to completion without manual handoff — opening a
fresh, empty-context agent for each phase, exactly like a human re-opening a new
chat per phase.

See [SKILL.md](./SKILL.md) for the full workflow. References live under
[`./references/`](./references/).

## What it does

- Reads the plan index (`phased-plan/README.md`) and its
  `current_dispatch_pointer` to know which phase runs next.
- Dispatches that phase to a **brand-new agent with empty context** (sub-agent /
  Task tool preferred, external CLI re-invocation, or a human-relayed handoff),
  using the [handoff-prompt template](./references/handoff-prompt-template.md).
- Waits for the phase agent to finish, then **verifies the result from the
  durable plan artifacts** — the index plus the phase-continuity checkpoint —
  never from the agent's chat.
- Advances to the next phase and repeats until the plan is complete, a phase is
  blocked, or a human/planner decision is required.
- Calls the read-only [`scripts/delivery-run-next.py`](../../scripts/delivery-run-next.py)
  helper to make each dispatch decision deterministically.

## What it does not do

- Does not implement phases itself and does not load executor skills into its own
  context. Each phase runs in an independent fresh agent, so the
  [depth-cap-of-two](../../docs/review-loops.md#universal-loop-bounds) review
  bound stays intact inside every phase.
- Does not plan. It executes an existing plan; when the plan is missing, stale,
  or superseded it stops and routes back to
  [`delivery-planner`](../delivery-planner/).
- Does not edit, reorder, resize, add, or remove phases, and does not hand-edit
  the index — those are planner-owned operations.
- Does not auto-retry a genuine blocker, and never marks a phase done that the
  artifacts do not show as done.

## Quick start

```text
Use the delivery-runner skill to execute the PROJ-1234 plan end-to-end.
Dispatch each phase as a fresh sub-agent and stop if anything blocks.
```

See the [main README usage example](../../README.md#skills) and
[SKILL.md § Example Prompts](./SKILL.md#example-prompts).

## Required environment

Same [execution-modes preflight](../../docs/execution-modes.md) as the rest of
the suite, plus a host that can open a fresh-context agent per phase (sub-agent,
CLI, or human-relayed). See [SKILL.md § Required Environment](./SKILL.md#required-environment).
