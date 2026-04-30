# Eval — Insightful Simplifications Concise And Anchored

This scenario pins the
[insightful-simplifications](../docs/insightful-simplifications.md) optional
output section against the
[output-discipline](../docs/output-discipline.md) rules. It exists to prevent
the section from drifting into generic coaching, template echo, or invented
architectural claims.

## Setup

- Workspace: any non-trivial repo with one cross-layer task. Two flavors should
  be exercised:
  - **A. Cross-layer engineering task.** A bug or feature that touches at least
    two of: API contract, persistence, domain rule, UI/render, tests, ops.
  - **B. Trivial task.** A typo fix, single-line refactor, or formatting-only
    change.
- Issue context: available and reachable so the
  [requirement-understanding gate](../docs/requirement-understanding.md) can
  end at `medium` or `high` for flavor A.
- Skill: any one of the top-level skills (`software-engineer`,
  `product-owner`, `manual-tester`, `test-automation-engineer`) or the nested
  `issue-investigator` / `code-reviewer`.

## Prompt (flavor A)

```text
Use the <skill> skill on this task. Use the insightful-simplifications section
when, and only when, it adds real framing value.

Task: <cross-layer task description>
Repo / context: <links>
```

## Prompt (flavor B)

```text
Use the <skill> skill on this task.

Task: fix the typo "Recieve" -> "Receive" in <file>.
```

## Pass criteria

The agent's response **must**:

1. For flavor A, when the agent emits `## Insightful Simplification`:
   - Use the **exact** heading `## Insightful Simplification` (singular).
   - Contain **1 to 3 bullets**, each ≤ 35 words, one sentence, no sub-bullets.
   - Anchor each bullet to a concrete element actually visible in the task
     (file path, layer name, state transition, contract field, environment,
     failure mode, lifecycle stage).
   - Not duplicate a finding, the diff, the verdict, or the acceptance criteria
     already present elsewhere in the output.
2. For flavor A, when no qualifying insight exists, **omit the entire section**.
   Do not render the heading with `- none`, `- n/a`, or an empty list.
3. For flavor B (trivial task), **omit the entire section**.
4. Never invent broader architectural facts, private company standards, or
   unobserved system structure to fill the section.
5. Never use generic coaching phrasing such as `consider ...`, `you might want
   to ...`, `think about edge cases`, or `write more tests` without a specific
   anchor.
6. Not promote the section above required-even-if-empty sections — the
   `code-reviewer` `## Final Verdict` and `software-engineer` `Final status:`
   line stay at the end of the output.
7. Not echo the contents of
   [`docs/insightful-simplifications.md`](../docs/insightful-simplifications.md)
   into the response.

## Failure modes this eval catches

- **Generic-coaching failure.** Bullets like "remember to consider performance"
  or "this could affect other users" with no anchor. **Fail.**
- **Restate-finding failure.** The bullet repeats a finding already in
  `## Findings`, the verdict, or the implementation plan. **Fail.**
- **Invented-architecture failure.** The bullet asserts structure the agent
  could not have observed (e.g., "the system probably needs an event-sourced
  rewrite"). **Fail.**
- **Template-echo failure.** Section rendered for a trivial task or with
  `- none` underneath when there is nothing to say. **Fail.**
- **Heading drift.** `## Insights`, `## Tips`, `## Architectural Notes`, or
  any plural / alternate heading. **Fail.**
- **Length blowout.** A bullet that runs into a paragraph or sub-bullets.
  **Fail.**

## Why this eval exists

The optional `## Insightful Simplification` section can quietly degrade two
existing properties of the repo: output discipline (concise, anchored, omit
when empty) and token efficiency (the agent should not spend tokens on
filler). This eval is the counter-pressure that keeps the section either
genuinely useful or genuinely absent.
