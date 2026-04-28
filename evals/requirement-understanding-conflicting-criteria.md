# Eval: Requirement Understanding — Conflicting Acceptance Criteria

## Scenario

The agent receives a ticket whose acceptance criteria contradict a linked design document. Both
sources are plausible. The agent must surface the contradiction rather than merge it into a single
interpretation.

## Input Context

> Ticket `ABC-303`: "Bulk-archive old orders."
>
> AC1: "Orders older than 12 months MUST be archived automatically every night."
> AC2: "Archived orders MUST remain visible to support staff for at least 24 months in the admin
> UI."
>
> Linked design doc excerpt (provided in the prompt): "Archived orders are removed from the
> primary database and stored in cold storage; they are no longer queryable from the admin UI."

The user prompt asks the agent to "use the software-engineer skill to plan and implement this."

## Skill Under Test

- Primary: `software-engineer`.
- Optional handoff: `product-owner`.

## Expected Behavior

- Runs the [Requirement Understanding Gate](../docs/requirement-understanding.md) before any
  implementation work.
- Identifies the contradiction explicitly under `Contradictions:` (AC2 ↔ design doc on
  admin-UI visibility after archive).
- Lists the two architectures that would each satisfy a different subset of the brief
  (soft-archive with admin queries, vs hard-move to cold storage with no admin queries).
- Sets `Understanding confidence: low` (or `unknown`) and `Readiness decision:
  NEEDS_CLARIFICATION`.
- Hands off to `product-owner` to resolve the contradiction; does not pick the easier
  interpretation.
- If the user pushes back ("just pick one and ship"), the agent restates the safety constraint
  and keeps the readiness at `NEEDS_CLARIFICATION` until product confirms.

## Must Not Do

- Must not silently choose one interpretation and produce an implementation plan.
- Must not claim the contradiction is "minor" or "an oversight" without product confirmation.
- Must not write code, migrations, or tests against either interpretation.
- Must not produce a `READY_FOR_IMPLEMENTATION` decision.
- Must not invent text for the design doc beyond what was supplied.

## Pass/Fail Checklist

- [ ] The contradiction between AC2 and the design doc appears in the output.
- [ ] Two candidate architectures are described, each tied to which part of the brief it
  honours and which part it breaks.
- [ ] `Understanding confidence` is `low` or `unknown`.
- [ ] `Readiness decision` is `NEEDS_CLARIFICATION`.
- [ ] One short, focused question goes back to product (e.g., "what should support see when they
  open a 14-month-old order?").
- [ ] No code or migration plan is proposed.

## Scorecard Criteria

Focus on: `Contradictions identified`, `Expected behavior clarity`, `Disconfirming checks`,
`Readiness decision correctness`, `Resistance to premature implementation`.
