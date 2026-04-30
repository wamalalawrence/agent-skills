# Insightful Simplifications

A small synthesis layer that any skill MAY add to its output when one short
observation would help the user better see the **shape** of the problem they are
working on. Optional. Bounded. Evidence-grounded.

This is not "tips" and it is not coaching. It is a better mental model in one
sentence — a senior-engineer framing moment that surfaces the wider context the
user might overlook (a boundary, a state machine, a contract, a lifecycle, a
coupling point, a failure mode, a blast radius).

## What It Is

A **single section** named exactly `## Insightful Simplification` (singular) with
**1–3 bullets**. Each bullet is a brief architectural / framing observation that
helps the user understand the wider context of the issue, anchored to something
the agent actually saw (a file, a layer, a state, a contract, an environment, a
known failure mode).

The section is **optional**. The default is to omit it. It is governed by the
"omit empty sections" rule from
[Output Discipline](output-discipline.md), and by the token-conscious design
principles in [Token Efficiency](token-efficiency.md).

## When To Emit It

Emit only when ALL of the following are true:

- The agent already gathered enough evidence through the normal skill workflow.
- The task spans multiple layers (product / API / persistence / UI / tests /
  operations) **OR** has a hidden simplifying frame the user is likely to
  overlook.
- The insight is grounded in evidence the agent actually saw, not invented
  context.
- One sentence is enough to make the insight useful.

When in doubt, omit.

## When NOT To Emit It

- Trivial tasks (typo fix, single-line refactor, formatting change).
- The [Requirement Understanding Gate](requirement-understanding.md) ended at
  `unknown` or `low` — there is not enough understanding to frame the wider
  context honestly.
- The agent would need to invent broader architectural facts, private company
  standards, or unobserved system structure to make the bullet sound deep.
- The "insight" would just restate a finding, the diff, the verdict, or the
  acceptance criteria.
- The bullet is generic coaching ("write tests", "consider performance",
  "think about edge cases") with no specific anchor in the work.

If none of the bullets survive these filters, drop the entire section. A skill
output without `## Insightful Simplification` is the default.

## Format (binding)

- Section heading: exactly `## Insightful Simplification`.
- Maximum **3 bullets**. Prefer 1.
- Each bullet ≤ **35 words**, one sentence, no sub-bullets, no preamble.
- Each bullet anchored to a concrete element: a file path, a layer, a state, a
  contract, a boundary, a known failure mode, a lifecycle stage.
- No metaphors, no banners, no "consider", no "you might want to".
- Omit the section entirely when no qualifying insight exists. Do not write
  `- none`.

## Examples

Good (boundary framing):

```markdown
## Insightful Simplification

- Input normalization belongs at the controller edge, invariants in `Order`,
  display in the React layer; the bug exists because validation is currently
  split across all three.
```

Good (state-machine framing):

```markdown
## Insightful Simplification

- The risky behavior is the transition `submitted -> billed`, not the `amount`
  field; the reverse path is currently silently allowed.
```

Good (contract framing):

```markdown
## Insightful Simplification

- This is contract drift: the API returns `total_cents` but the frontend
  reads `total`; the symptom is visual, the cause is the response shape, not
  the formatter.
```

Bad (generic coaching, no anchor):

```markdown
- Consider thinking about edge cases and writing more tests.
```

Bad (restates a finding already in the output):

```markdown
- The bug is in `OrderService.submit`, which is also the finding above.
```

Bad (invented architecture, no evidence):

```markdown
- The system probably needs an event-sourced rewrite.
```

## Why This Exists

The default skill output answers **what to do**. The user sometimes also
benefits from **what shape this problem actually has**. That second answer can
be much shorter than the first and still raise the user's understanding.

Kept optional and bounded, this section costs near-zero tokens when irrelevant
and yields a senior-engineer framing moment when relevant. It does not replace
the [requirement-understanding workflow](requirement-understanding.md), the
[evidence pack](../skills/software-engineer/references/evidence-pack.md), or
any existing skill output — it sits alongside them and is dropped whenever it
would be filler.

## Inheritance

Every top-level and nested skill's `Expected Output Contract` lists
`## Insightful Simplification` as an **optional** section governed by this doc
and by [Output Discipline](output-discipline.md). The same "omit empty sections"
hard rule applies — the section is dropped when no qualifying insight exists.
