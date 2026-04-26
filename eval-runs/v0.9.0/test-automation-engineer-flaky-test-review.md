# Eval Run: `test-automation-engineer` - Flaky Test Review

- Scenario: [`evals/test-automation-engineer-flaky-test-review.md`](../../evals/test-automation-engineer-flaky-test-review.md)
- Skill under test: `test-automation-engineer`
- Release: `v0.9.0`

> **Illustrative run.** Maintainer-authored example output, not a verbatim
> capture from a single specific model.

## Run Setup

- Host: generic chat-style assistant.
- Mode: `in-repo`.
- Tools available: file read, test runner, `git log`.
- Inputs withheld: real CI dashboard history, real flake counts.

## Inputs Provided

- A failing end-to-end test that touches network, time, and a third-party
  webhook.
- A claim from the user: "It fails about once every five runs in CI."
- A repository checkout including the test source.

## Skill Output (Illustrative)

```text
Flake review summary
- Confidence: medium-low. The 1-in-5 figure is anecdotal; CI history was
  not available to confirm.
- Symptom: end-to-end test asserts a webhook side-effect within a fixed
  wall-clock window.

Likely contributors (ordered by suspicion)
- Time-based assertion ("within 2 seconds") combined with shared CI
  workers.
- Real network call to a third-party sandbox without a controlled clock or
  retry boundary.
- Test depends on prior tests leaving fixture state.

Recommended actions
- Move the timing-sensitive assertion to a smaller scope (unit or
  integration with a fake clock).
- Replace the third-party call with a recorded interaction or a local
  contract double; keep one nightly end-to-end smoke test against the real
  sandbox if needed.
- Make fixture setup explicit per-test instead of relying on global state.

Flake budget
- Default target: under 1 percent over a 20-run rolling window in CI.
- If 20-run history is not available, fall back to a 10-run local
  re-execution and record results, with confidence marked as lower.

Stopping point
- Do not declare the test "fixed" without evidence from at least 10 clean
  runs after the change.

Handoffs
- If root cause looks like a real product race condition, hand off to
  `issue-investigator` and `software-engineer`.
- Coordinate with `manual-tester` if the symptom needs a manual reproduce.
```

## Scoring

| Criterion | Score | Note |
| --- | --- | --- |
| Context awareness | 3 | Uses the test description and shape. |
| Evidence discipline | 3 | Names anecdotal vs measured. |
| Correct handoff | 3 | Routes real-race cases to other skills. |
| Output contract completeness | 3 | Flake budget + fallback included. |
| Specificity / actionability | 3 | Concrete refactor directions. |
| Hallucination avoidance | 3 | Does not invent CI numbers. |
| Test / validation realism | 2 | Suggests fake clock; no library named. |
| Risk awareness | 2 | Could mention test pyramid drift cost. |
| Correct stopping behavior | 3 | Refuses to declare fixed without evidence. |
| Portability / public-safety | 0 | Uses generic "third-party sandbox". |

**Total: `25/30`.**

## Strengths

- Explicit fallback for when CI history is unavailable, instead of asking
  for a fixed 20-run history.
- Concrete refactor directions tied to test pyramid level.
- Honest stopping behavior: does not claim the test is fixed without
  re-runs.

## Failure Modes / Gaps Found

- Does not suggest concrete instrumentation hooks (for example:
  log-correlation IDs, deterministic clock injection, or recorded
  interactions). The next pass could include a short "instrumentation
  hooks" subsection.
- Risk awareness is shallow: moving from end-to-end to lower-level tests
  has its own cost; the skill could state that explicitly.

## Follow-up Actions

- No skill rewrite for v0.9.0.
- Future candidate: extend `test-automation-engineer` output contract with
  an "instrumentation hooks" field and a "trade-offs of moving down the
  pyramid" line.
