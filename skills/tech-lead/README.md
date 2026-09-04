# tech-lead

Single entry point for engineering work. Describe the task; this skill works out who should do
it, hands the job to a fresh agent, checks the result on disk, and either advances or stops.

- Skill definition: [`SKILL.md`](./SKILL.md)
- Routing rules: [`references/routing-table.md`](./references/routing-table.md)
- Handoff brief: [`references/handoff-prompt-template.md`](./references/handoff-prompt-template.md)

## What it is for

The other skills each own one decision surface, and picking the right one is real work. Pick
wrong and you get the expensive failures: code written against unclear intent, a fix for a root
cause nobody established, automation built on an unstable scenario.

```text
Use the tech-lead skill: invoice search drops the status filter on page 2.
```

It classifies that as a defect, runs the requirement-understanding gate, notices no root cause
exists, and dispatches `issue-investigator` — then hands the confirmed cause to
`software-engineer`.

## What it does not do

It never implements, reviews, refines, tests, or plans. Those belong to specialists, and this
skill's only job is choosing the right one and verifying the handoff landed.

It also never becomes mandatory. If you already know you want
[`software-engineer`](../software-engineer/SKILL.md), invoking it directly is faster and
better. This is an addition to the catalogue, not a front door you have to walk through.

## Dispatch, not invocation

The distinction is load-bearing. This skill opens a **fresh agent with empty context** per step
rather than loading the executor into its own context.

That keeps two properties. Each step gets a small focused context instead of inheriting
everything before it. And the dispatched agent is the root of its own call chain, so the
depth-cap-of-two review bound still holds inside the step — the chain is `executor →
code-reviewer`, and the lead never appears in it.

Loading an executor here instead would make it three deep and quietly break the bound that keeps
the engineer/reviewer loop honest.

Requires a host that can open a fresh-context agent: a sub-agent or Task tool, an external CLI
re-invocation, or a human pasting the prepared brief into a new chat.

## Where it stops

It stops rather than guessing: when no routing row matches, when a step comes back blocked, when
a target skill cannot be loaded from disk, when a step writes no artifact after one retry, and
at a hard cap of six dispatches. Full list in
[`SKILL.md`](./SKILL.md#stopping-conditions).

## Related

- [Skill boundaries](../../docs/skill-boundaries.md) — the ownership rules this skill implements.
- [Review loops](../../docs/review-loops.md) — the bounds it has to respect.
- [Requirement understanding](../../docs/requirement-understanding.md) — the gate it runs first.
- [`delivery-runner`](../delivery-runner/SKILL.md) — the specialist dispatcher for an existing
  phased plan. When one exists, use that instead.
