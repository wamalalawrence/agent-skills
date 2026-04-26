# Eval Run: Multi-Skill Bug-To-Regression Flow

- Scenario: [`evals/multi-skill-bug-to-regression-flow.md`](../../evals/multi-skill-bug-to-regression-flow.md)
- Skills under test: `issue-investigator`, `software-engineer`,
  `code-reviewer`, `manual-tester`, `test-automation-engineer`.
- Release: `v0.9.0`

> **Illustrative run.** Maintainer-authored example output across the
> chained skills, not a verbatim capture from a single specific model.

## Run Setup

- Host: generic chat-style assistant capable of loading multiple skills in
  sequence.
- Mode: `in-repo`.
- Tools available: file read, `git diff`, test runner.
- Inputs withheld: production logs, real ticket text, real CI history.

## Inputs Provided

- The same overdue-invoice symptom used by the per-skill runs.
- A request: "Take this from bug report to merged regression coverage,
  using the right skills in order."

## Chained Output (Illustrative, Condensed)

```text
1. issue-investigator
   - Status: under investigation; root cause suspected (stale cache).
   - Evidence gate set; handoff to software-engineer only after the gate.

2. product-owner (advisory step)
   - Confirms acceptance criterion: paid invoices removed from overdue
     list within 30 seconds of payment confirmation.

3. software-engineer
   - Phase 1: read relevant modules.
   - Phase 2: implement cache eviction; add unit + integration tests.
   - Inner-loop code-reviewer: minor findings only.
   - Phase 3: outer-loop code-reviewer: no blockers.
   - PR prepared; stop and await downstream skills.

4. manual-tester
   - Defect report attached for traceability.
   - Retest plan executed against staging build with placeholder data.
   - Result: pass for the affected state; pass for one alternate state;
     pass for one negative state.

5. test-automation-engineer
   - Decides regression test belongs at integration level (already added
     in step 3); adds one additional contract test for the cache key
     shape; flake budget recorded.

6. Final audit (the gap)
   - No single end-of-chain summary that lists every skill that
     contributed, what evidence each produced, and what was deferred.
```

## Scoring

| Criterion | Score | Note |
| --- | --- | --- |
| Context awareness | 3 | Each step uses the prior step's evidence. |
| Evidence discipline | 3 | Evidence gate is honored. |
| Correct handoff | 3 | Skills invoked in the right order. |
| Output contract completeness | 3 | Each skill produces its contract. |
| Specificity / actionability | 3 | Concrete code, tests, and retest. |
| Hallucination avoidance | 2 | Asserts staging pass without log excerpt. |
| Test / validation realism | 3 | Tests added at the right level. |
| Risk awareness | 2 | No combined risk register at the end. |
| Correct stopping behavior | 3 | Each skill stops at its boundary. |
| Portability / public-safety | 0 | Uses generic placeholders throughout. |

**Total: `25/30`.**

## Strengths

- Handoffs between skills are clean and ordered.
- Each skill stops at its own boundary; no skill claims downstream work.
- Output contracts are honored throughout the chain.

## Failure Modes / Gaps Found

- No end-of-chain audit summary that lists what each skill contributed,
  what evidence was produced, and what was deferred. A reviewer has to
  reconstruct it from the per-skill outputs.
- Risk awareness is per-skill only; there is no combined risk register at
  merge time.

## Follow-up Actions

- No skill rewrite for v0.9.0.
- Future candidate: define an optional "chain audit" output that the last
  skill in a multi-skill flow can emit, summarizing contributions, gaps,
  and the merge decision.
