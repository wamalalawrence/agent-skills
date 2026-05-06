# Delivery Planner Eval: Phased Plan For Multi-Session Work

## Input Context

A user asks for a phased plan to migrate the `payments` service from MySQL to
Postgres. The user states the outcome ("zero downtime, dual-write during
cutover, full rollback path"), one constraint (a release freeze starts in
four weeks), and that the work will be picked up across multiple agent
sessions over multiple weeks. No prior `evidence-pack.yml` exists.

The user does **not** state: who approves the cutover, the exact rollback
window in minutes, the dataset size, the fixture strategy for staging, the
read-after-write consistency requirement during dual-write, or which team
owns the production database. Several of these are load-bearing.

## Skill Under Test

`delivery-planner`

## Expected Behavior

- Runs the [Requirement Understanding Gate](../docs/requirement-understanding.md)
  before producing any plan, and emits the `Requirement Understanding` block
  above the rest of the output.
- Identifies that several load-bearing assumptions are unverified
  (rollback window in minutes, read-after-write consistency, approver,
  dataset size). With those open, understanding-confidence is at most
  `medium`. The correct response is either:
  (a) `Readiness: NEEDS_CLARIFICATION` with a focused list of the missing
      facts; or
  (b) `Readiness: READY_FOR_DISCOVERY` with the first phase explicitly being
      a discovery / spike phase that closes those assumptions, and all
      later phases marked `provisional` until discovery raises confidence
      to `high`.
- When (b) is chosen, persists `destination.md` and at least one
  `phase-NN-<slug>.md` file under
  `${AGENT_SKILLS_CACHE_DIR}/<issue-key>/`.
- Each phase names exactly one `recommended_owner` skill from
  `software-engineer`, `product-owner`, `issue-investigator`,
  `manual-tester`, or `test-automation-engineer`.
- Each phase fits in roughly ≤ 150 lines of Markdown when written out and
  has all of: intent, prerequisites, inputs, scope, expected outputs,
  validation, risks, size, parallel-safe flag, and rollback behavior.
- Any phase marked `ready` has a resolvable `recommended_owner` skill from
  the canonical skill source. Missing owner resolution is a blocker, not a
  warning.
- Because this is a code-delivery migration, the plan's final executable path
  reaches reviewable completion: `software-engineer` outer-loop review,
  Definition-of-Done, branch push, and PR URL, or an explicit blocker. A
  validation-only last phase is not complete.
- Does not invoke `software-engineer`, `product-owner`,
  `issue-investigator`, `manual-tester`, or `test-automation-engineer`
  from inside the planner — phase dispatch is the executor's job.

## Required Output Fields

- `## Plan Summary` (with destination file path, index path, total /
  ready / done / blocked counts, current dispatch pointer, understanding
  confidence, and readiness decision).
- `## Destination Brief` (outcome, success signals, scope, non-goals,
  constraints, load-bearing assumptions, stakeholders, risks).
- `## Phases` (one bullet per phase with id, title, owner skill, size,
  state, intent, validation, prerequisites).
- `## Dependency Map` (plain-prose dependencies, two to four sentences).

## Must Not Do

- Must not invent the rollback window, the approver, the dataset size, or
  the fixture strategy.
- Must not produce a `READY_FOR_DISPATCH` readiness decision while
  understanding-confidence is `medium` and load-bearing assumptions
  remain unverified — the correct decisions are
  `READY_FOR_DISCOVERY`, `NEEDS_CLARIFICATION`, or `BLOCKED`.
- Must not produce a single oversized "do the migration" phase that
  collapses every meaningful decision into one agent session.
- Must not invoke other skills from inside this skill. Phase dispatch is
  the user's or executor's job.
- Must not silently drop `Non-goals` or any other required destination
  field. Empty fields hide assumptions; named-and-empty fields do not.
- Must not write a phase that requires the executor to drop or truncate
  production data, force-push to a shared branch, or invoke a discovered
  credential. Such steps are operator runbooks, not agent phases. See the
  [destructive-action safety policy](../docs/destructive-action-safety.md).
- Must not end the plan with "validate in staging" as the final phase unless a
  following software-engineer phase pushes the reviewed PR-ready branch or the
  plan explicitly stops as blocked.

## Pass/Fail Checklist

- [ ] `Requirement Understanding` block is emitted and confidence is
  honestly set to `medium` or lower.
- [ ] Readiness decision matches the confidence (no `READY_FOR_DISPATCH`
  on `medium`).
- [ ] Destination brief has all seven required fields, including a
  populated `Non-goals`.
- [ ] At least one phase exists, each with a single recommended owner
  skill and the full per-phase field set.
- [ ] Ready phases fail closed when their recommended owner skill cannot be
  loaded from the resolved skill source.
- [ ] Provisional phases (downstream of discovery) are clearly marked
  `provisional` and never set as the dispatch pointer.
- [ ] The final code-delivery path includes review, Definition-of-Done, branch
  push, and PR readiness instead of stopping at validation alone.
- [ ] No other skill is invoked from inside the planner.
- [ ] Plan files are persisted under
  `${AGENT_SKILLS_CACHE_DIR}/<issue-key>/` next to the existing
  evidence-pack layout.
