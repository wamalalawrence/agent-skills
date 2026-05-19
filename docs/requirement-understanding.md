# Requirement Understanding

Most failed engineering work fails before any code is written. The agent (or person) misreads the
task, treats the first plausible interpretation as confirmed, hides assumptions inside an
implementation, or starts coding while the requirement is still ambiguous. This document defines a
shared, lightweight workflow every relevant skill in this repository runs **before** implementation,
review, manual testing, or automation.

The goal is not ceremony. The goal is to keep the agent from confidently moving in the wrong
direction.

## Scope

This workflow is consumed by:

- [`software-engineer`](../skills/software-engineer/SKILL.md) before any code change.
- [`issue-investigator`](../skills/software-engineer/skills/issue-investigator/SKILL.md) at the
  start of every investigation.
- [`code-reviewer`](../skills/software-engineer/skills/code-reviewer/SKILL.md) before issue-aware
  review.
- [`product-owner`](../skills/product-owner/SKILL.md) before producing tracker-ready output.
- [`manual-tester`](../skills/manual-tester/SKILL.md) before writing test scenarios.
- [`test-automation-engineer`](../skills/test-automation-engineer/SKILL.md) before automating any
  behavior.

Each skill's `Requirement Understanding Gate` section binds this shared workflow to the skill's
specific stopping conditions and output contract.

## When To Run It

- The skill has just been invoked and the user task is in hand.
- The skill is about to leave its preparation phase and start a phase that changes files, produces
  tracker-ready output, writes a test, or hands off to another skill.
- Any time the requirement materially changes mid-task (stakeholder added a constraint, evidence
  contradicts the original brief, scope expands).

If a skill is asked to *only* perform a narrow read-only step the user has already scoped (for
example "summarize this file"), the gate is still required but most of its output reduces to "no
expected behavior to derive — the task is purely descriptive". The agent must still record that
decision rather than skipping the step silently.

## The Twelve-Step Workflow

Run these in order. Skipping a step is allowed only if the agent explicitly states why it does not
apply (e.g., "step 5 is not applicable — this is a greenfield feature with no current behavior").

### 1. Interpret the task

- Restate the task in one or two plain-language sentences.
- Strip metaphors, vendor names, and fashion words. Keep the actual change being requested.
- If the task statement contains two or more interpretations, list them separately and mark them as
  candidate interpretations until one is confirmed.

### 2. Classify the requirement type

Pick the smallest set of types that fit. A single task can be more than one.

- `bug` — observed behavior contradicts intended behavior.
- `regression` — behavior previously worked and now does not.
- `incident` — production impact, time pressure, evidence is shallow.
- `feature` — new capability, no current behavior to compare against.
- `enhancement` — change to existing capability with a current behavior baseline.
- `refactor` — internal change with no intended behavior change.
- `configuration` — runtime / environment / flag change, no code change.
- `data correction` — fix data state, not code.
- `documentation` — text-only change.
- `spike / discovery` — answer a question, not yet ready to implement.
- `unclear` — the type cannot be determined from the available context.

### 3. Identify the user/business goal

- Who benefits and how.
- What outcome the user, operator, or stakeholder is trying to reach.
- What measurable or observable signal would mean the goal is met (a metric, a workflow that
  finishes, an error that no longer happens).
- If the goal is not stated and cannot be inferred from issue evidence, mark it as an open question.

### 4. Identify expected behavior

- The behavior the system is supposed to exhibit after the change.
- Phrase it in observable terms. Avoid "works correctly" / "is user-friendly".
- Include happy paths, important edge cases, and at least one negative criterion ("the system MUST
  NOT do X") when the requirement type is anything other than pure refactor / docs.
- Source it from the ticket, acceptance criteria, product docs, related tickets, code comments,
  tests, or product-owner output. If invented, mark explicitly as an assumption.

### 5. Identify actual / current behavior (when applicable)

- Skip for greenfield features and pure new capabilities.
- For bugs, regressions, incidents, enhancements, or any change that modifies existing behavior:
  describe what the system does today and how that was observed (logs, screenshots, reproduction,
  code path, test output, user report).
- Distinguish "reported actual behavior" (what the user said) from "observed actual behavior" (what
  the agent verified). Both are useful; conflating them is dangerous.

### 6. Identify scope and out-of-scope

- What this task should change.
- What this task should not change, even if it looks adjacent or tempting.
- What the agent should hand off rather than absorb (e.g., a related defect surfaced during
  investigation belongs in its own ticket, not this one).

### 7. Review available evidence

- Issue / ticket / brief, comments, linked docs, screenshots.
- Code paths, tests, configuration, CI results, recent commits in the affected area.
- Logs, traces, metrics, monitoring evidence; environment evidence when accessible read-only.
- Existing manual or automated test coverage for the area.
- Any prior investigation result, evidence pack, or reproduction recipe in the cache.

For each evidence item, capture: source, what it shows, and how it connects to expected vs actual
behavior. Do not list evidence the agent has not actually seen.

### 8. Separate facts from assumptions

Maintain three explicit lists.

- **Facts** — directly observable in the evidence reviewed in step 7. Quote or cite.
- **Assumptions** — claims the agent is making to bridge gaps in evidence. Each assumption is one
  line, in plain language. Mark each as `safe` (low risk if wrong) or `load-bearing` (the
  recommendation breaks if it is wrong).
- **Decisions taken from the user** — explicit answers the user gave during the conversation,
  recorded verbatim or close to it.

### 9. Identify unknowns and contradictions

- Unknowns: questions the evidence cannot answer yet but that affect the recommendation.
- Contradictions: places where two pieces of evidence (or two stakeholders, or two acceptance
  criteria) point in different directions.
- A load-bearing unknown or unresolved contradiction blocks `READY_FOR_IMPLEMENTATION`. The agent
  must either close the gap (more evidence) or surface it (clarification).

### 10. Define disconfirming checks

For each load-bearing assumption and each candidate interpretation in step 1:

- Write one short, falsifiable check: "what observation would prove this wrong?"
- Prefer checks that are read-only, bounded, and cheap (a query with a `LIMIT`, a single test run,
  a code grep, a one-line log filter, a question to the user).
- This is the artifact that distinguishes understanding from guessing. If no disconfirming check
  exists, the assumption stays at confidence `low` regardless of how plausible it sounds.

### 11. Assign understanding confidence

Pick exactly one level. The level is about *understanding the requirement*, not about
implementation difficulty.

- `unknown` — the agent cannot describe expected behavior, the task is missing inputs, or the
  candidate interpretations cannot be discriminated. Examples: bug report with no environment, no
  reproduction, no expected behavior.
- `low` — expected behavior is partially known, but at least one load-bearing assumption is
  unverified, or there is an unresolved contradiction. Implementation would gamble on the right
  interpretation.
- `medium` — expected behavior is known well enough to plan and to surface specific risks, but the
  agent still has assumptions that should be visible in the plan and verified during validation.
- `high` — expected behavior is observable and testable, evidence is sufficient, no load-bearing
  unknown remains, and the candidate interpretation is the only one consistent with the evidence.

### 12. Decide readiness to proceed

The readiness decision is the final output of the gate. It tells the calling skill whether to move
forward, and what kind of next action is appropriate.

- `READY_FOR_IMPLEMENTATION` — confidence is `high`, scope is bounded, expected/actual behavior is
  defined, validation route is known. Engineering can implement.
- `READY_FOR_INVESTIGATION` — confidence is `low` or `medium` because actual behavior or root
  cause is unclear. `issue-investigator` should run before any fix work.
- `READY_FOR_REVIEW` — confidence is `high` enough to review a diff against expected behavior,
  acceptance criteria are accessible, and the diff scope is known.
- `READY_FOR_TEST_DESIGN` — expected behavior is stable enough to plan manual scenarios or
  regression automation, and the testing skill has the inputs it needs.
- `NEEDS_CLARIFICATION` — the user, product owner, or stakeholder must answer a specific question
  before the work can move forward. The agent stops and asks.
- `NEEDS_EVIDENCE` — the agent could move forward if it had a specific piece of evidence (a log
  excerpt, a code path, an environment check, a reproduction). The agent stops and asks for it, or
  proposes a safe read-only check the user can run.
- `BLOCKED` — the work cannot proceed without a decision outside the agent's reach (legal, product,
  destructive-action approval, missing access, irreconcilable contradiction).

## Confidence-To-Action Rules

These three rules are binding. Skill `Guardrails` sections cite them directly.

- If understanding confidence is **`unknown` or `low`**, the agent **must not implement** the
  requirement, must not produce tracker-ready output as if intent were settled, must not write
  automated regression coverage, and must not give a bare `PASS` review verdict. The correct
  decision is `NEEDS_CLARIFICATION`, `NEEDS_EVIDENCE`, or `BLOCKED`.
- If understanding confidence is **`medium`**, the agent may investigate, plan, draft, or run
  read-only checks, but every load-bearing assumption must be visible in the output. Implementation
  is allowed only when the medium-confidence assumptions are explicitly accepted by the user or
  validated during the work.
- If understanding confidence is **`high`**, the agent may proceed within the understood scope.
  Adjacent problems discovered along the way are recorded as follow-ups, not silently absorbed.

The first plausible interpretation is not "high confidence". High confidence requires that
disconfirming checks have been considered and either run or judged unnecessary because evidence
already excludes the alternatives.

## Required Output Block

Every skill that runs this gate emits a `Requirement Understanding` block in its output. The block
fits in roughly 15–25 lines for a typical task. Empty fields use `not applicable` (with a one-line
reason) rather than being deleted.

```markdown
## Requirement Understanding

- Interpreted task:
- Requirement type:
- User/business goal:
- Expected behavior:
- Actual / current behavior:
- In scope:
- Out of scope:
- Evidence reviewed:
- Facts:
- Assumptions (mark each safe | load-bearing):
- Unknowns:
- Contradictions:
- Disconfirming checks:
- Understanding confidence: unknown | low | medium | high
- Readiness decision: READY_FOR_IMPLEMENTATION | READY_FOR_INVESTIGATION | READY_FOR_REVIEW |
  READY_FOR_TEST_DESIGN | NEEDS_CLARIFICATION | NEEDS_EVIDENCE | BLOCKED
- Next action:
```

When the skill already maintains an [evidence pack](../skills/software-engineer/references/evidence-pack.md),
the same fields can be persisted there under an `understanding:` block so subsequent skills do not
re-derive them. The textual block in the user-facing output is still required because the user
needs to see the reasoning before the agent acts on it.

## What This Gate Does Not Do

- It does not replace investigation, product refinement, or code review. It is a precondition for
  them, not a substitute.
- It does not require the agent to produce a long ceremony for trivial tasks. A typo fix runs the
  gate in three lines: interpreted task, expected behavior, readiness `READY_FOR_IMPLEMENTATION`,
  every other field marked `not applicable`.
- It does not block simple read-only questions. If the user asked for a description, the gate
  records "no behavior change requested — descriptive task" and proceeds.
- It does not give the agent permission to invent product intent. When evidence is missing, the
  correct readiness is `NEEDS_CLARIFICATION` or `NEEDS_EVIDENCE`, never `READY_FOR_IMPLEMENTATION`
  with a confident-sounding guess.

## How To Apply It Without Drowning Simple Tasks

- Run all twelve steps in your head; write down only the ones that have non-trivial content.
- Mark inapplicable steps `not applicable` with one short reason. The discipline is in *naming*
  what does not apply, not in inventing content.
- Reuse content. If `issue-investigator` already wrote expected vs actual behavior into the
  evidence pack, `software-engineer` reads it and references it instead of restating it.
- Prefer one-liners. The gate is supposed to fit on a screen.

The reader of the output should be able to tell, from the block alone, whether the agent
understood the task, what it is unsure about, and whether the next step it is about to take is
justified.
