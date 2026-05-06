# delivery-planner

Phased delivery planning workflow for work that is too large to fit one agent
session — features, refactors, migrations, multi-step investigations, multi-PR
bug fixes.

See [SKILL.md](./SKILL.md) for the full workflow. References live under
[`./references/`](./references/).

## What it does

- Produces a one-page **destination brief** (outcome, success signals, scope,
  non-goals, constraints, load-bearing assumptions, risks).
- Decomposes the work into **phases**, each sized so a fresh agent loaded
  with `destination.md` + one `phase-NN.md` has enough — and only enough —
  context to execute it well.
- Names one recommended owner skill per phase
  ([`software-engineer`](../software-engineer/), [`product-owner`](../product-owner/),
  [`issue-investigator`](../software-engineer/skills/issue-investigator/),
  [`manual-tester`](../manual-tester/),
  [`test-automation-engineer`](../test-automation-engineer/)) so the plan
  dispatches itself instead of routing through this skill on every hop. A
  missing owner skill is a blocked phase, not an optional warning.
- Persists plan files into the shared
  `${AGENT_SKILLS_CACHE_DIR}/<issue-key>/` cache next to `evidence-pack.yml`,
  so any downstream skill or fresh agent finds them in the same place.
- Creates or updates `evidence-pack.yml` for every plan, including greenfield
  plans, so phase executors have a durable continuity checkpoint to update.
- For code-delivery work, requires the final executable path to reach PR-ready
  completion: outer-loop review, Definition-of-Done, branch push, and PR URL,
  or an explicit blocker.

## What it does not do

- Does not invoke other skills. It produces artifacts; executors invoke
  whichever skill the phase recommends. This keeps the depth-cap-of-two
  universal rule in [docs/review-loops.md](../../docs/review-loops.md#universal-loop-bounds)
  intact.
- Does not invent goals, success criteria, or constraints. When they are not
  stated and cannot be derived from real evidence, the readiness decision is
  `NEEDS_CLARIFICATION`.
- Does not replace project management. No calendar dates, headcount
  allocation, or vendor procurement. Those belong outside the agent loop.

## Required environment

This skill is mostly read-only. The
[execution-modes preflight](../../docs/execution-modes.md) still applies so
that downstream skills see the same `${WORKSPACE_ROOT}` / `.agent-skills.yml`
configuration the planner did. See
[SKILL.md § Required Environment](./SKILL.md#required-environment).
