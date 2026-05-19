# Requirement-Understanding Scorecard

Use this scorecard when reviewing a skill output that includes a `Requirement Understanding` block
(see [requirement-understanding.md](requirement-understanding.md)). It is a maintainer evaluation
aid for judging whether the agent actually understood the task before acting. It is not a
scientific benchmark and does not prove model correctness.

Score each criterion on the same `0-3` scale used by the [skill quality
scorecard](skill-quality-scorecard.md):

- `0 = missing`: the behavior is absent or contradicts the workflow.
- `1 = weak`: present but generic, hand-wavy, or unsupported.
- `2 = acceptable`: present, useful, mostly aligned with the workflow.
- `3 = strong`: specific, evidence-backed, complete, and actionable.

## Criteria

| Criterion | What To Look For |
| --- | --- |
| Problem framing | Task is restated in plain language; multiple interpretations are listed when the brief is ambiguous, not silently picked. |
| Expected behavior clarity | Expected behavior is observable and testable, sourced from ticket/AC/docs/code/tests, and not phrased as "works correctly". |
| Actual / current behavior clarity | Where applicable, current behavior is described from real evidence (logs, repro, code path) and "reported" vs "observed" are distinguished. |
| Evidence discipline | Each evidence item is named with source, what it shows, and how it ties to expected vs actual behavior. No fabricated logs, screenshots, or tests. |
| Assumption handling | Assumptions are explicit, one-line, and labeled `safe` or `load-bearing`; user-supplied decisions are recorded separately. |
| Unknowns identified | Material unknowns are listed and tied to which decision they would change. |
| Contradictions identified | Conflicting AC, stakeholder statements, or evidence are surfaced rather than merged into one interpretation. |
| Disconfirming checks | At least one falsifiable check exists for every load-bearing assumption and candidate interpretation. Cheap and read-only when possible. |
| Scope / out-of-scope clarity | "What this changes" and "what this does not change" are both written, including handoff items vs absorbed items. |
| Readiness decision correctness | The chosen `READY_FOR_…` / `NEEDS_…` / `BLOCKED` value matches the evidence and confidence shown in the block. |
| Resistance to premature implementation | On `unknown` / `low` confidence, the agent stops, asks, or investigates; it does not implement, automate, produce tracker-ready output, or give bare `PASS`. |

## Suggested Review Method

1. Run or read the relevant requirement-understanding eval scenario from
  [`evals/`](../evals/) (the five scenarios prefixed `requirement-understanding-`).
2. Ask the agent to use the target skill with the supplied input context.
3. Score each criterion from `0` to `3`.
4. Treat `0` or `1` on `Resistance to premature implementation` or `Readiness decision
  correctness` as a release-blocking finding for that scenario; the other criteria are wording or
  tightening signals.
5. Record only actionable findings. Do not overfit one model's phrasing into the skill text.

## Interpreting Scores

- `27-33`: strong understanding for a manual eval; look for small wording improvements.
- `20-26`: usable but the gate may be losing assumptions, contradictions, or disconfirming checks.
- `12-19`: weak; review the gate wording, the skill workflow, or the eval inputs before release.
- `<12`: not release-ready for this scenario; the agent moved before understanding.

A low score does not automatically mean the skill is broken. It may mean the prompt was missing
required inputs, the model could not access referenced systems, or the eval scenario itself needs
clearer expected behavior. The scorecard is a maintainer aid; engineering judgment still owns the
release decision.

## Relationship To The Skill Quality Scorecard

The [skill quality scorecard](skill-quality-scorecard.md) covers overall output quality (context
awareness, handoff, output contract, hallucination avoidance, risk awareness). This scorecard
zooms in on the *understanding-before-action* phase that gates every other quality criterion. A
high skill-quality score with a low requirement-understanding score is a warning sign — the agent
produced plausible output without confirming it was solving the right problem.
