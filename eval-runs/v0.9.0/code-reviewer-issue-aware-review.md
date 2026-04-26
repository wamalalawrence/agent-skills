# Eval Run: `code-reviewer` - Issue-Aware Review

- Scenario: [`evals/code-reviewer-issue-aware-review.md`](../../evals/code-reviewer-issue-aware-review.md)
- Skill under test: `code-reviewer`
- Release: `v0.9.0`

> **Illustrative run.** Maintainer-authored example output, not a verbatim
> capture from a single specific model.

## Run Setup

- Host: generic chat-style assistant with diff access.
- Mode: `in-repo`.
- Tools available: `git diff`, file read.
- Inputs withheld: linked ticket body, CI history.
- Severity filter: `${CODE_REVIEWER_SHOW_SEVERITIES}` defaulting to
  blocker/major/minor.

## Inputs Provided

- A diff of about 180 lines touching one service module and one shared
  utility, with a small test addition.
- A linked issue saying: "Fix overdue invoice listing showing paid invoices
  for some users after release `R`."
- Acceptance criteria stating: paid invoices must not appear in the overdue
  list within 30 seconds of payment confirmation.

## Skill Output (Illustrative)

```text
Review summary
- Issue alignment: the diff plausibly addresses the symptom by invalidating
  the overdue-list cache after a payment-recorded event. Acceptance criteria
  about the 30-second window are not directly verified by the diff.
- Risk: medium. Cache invalidation is broad; the new path is exercised by
  one new unit test only.

Findings (severity, file:line, summary)
- Major  service/payments.py:142  cache invalidation key uses the user id
  only; if the overdue list is cached per (user, region) the eviction is
  incomplete.
- Major  service/payments.py:160  no test for the case where the payment
  event is delivered twice; the eviction is idempotent but the test does not
  prove it.
- Minor  shared/cache.py:48  new helper accepts None silently; consider
  raising for clearer failure during development.
- Minor  tests/test_payments.py:22  test asserts cache is empty after one
  payment, but does not assert the overdue list endpoint result.
- Info   docs/internal-runbook.md  not updated; out of scope for this PR.

Acceptance-criteria mapping
- "Paid invoices must not appear in overdue list within 30 seconds":
  partially addressed. Cache eviction is immediate, but no test exercises
  the listing endpoint after a payment.

Recommended next steps
- Add an integration-level test asserting the listing endpoint result after
  a recorded payment.
- Confirm the cache key shape matches the listing-side cache key.
- Hand off to `test-automation-engineer` if a regression test should be
  added at a different level.
```

## Scoring

| Criterion | Score | Note |
| --- | --- | --- |
| Context awareness | 3 | Uses issue, acceptance criteria, and diff. |
| Evidence discipline | 3 | Distinguishes assertion vs verified. |
| Correct handoff | 3 | Routes regression test to `test-automation-engineer`. |
| Output contract completeness | 3 | Findings, severity, mapping, next steps. |
| Specificity / actionability | 3 | File:line specific findings. |
| Hallucination avoidance | 2 | Asserts behavior of helper not in inputs. |
| Test / validation realism | 2 | Suggests integration test; no commands. |
| Risk awareness | 3 | Highlights cache key shape and double delivery. |
| Correct stopping behavior | 2 | Could note CI history was unavailable. |
| Portability / public-safety | 1 | Mentions internal runbook indirectly. |

**Total: `25/30`.**

## Strengths

- Specific findings with file:line and severity.
- Explicit acceptance-criteria mapping.
- Correct handoff suggestion to `test-automation-engineer`.

## Failure Modes / Gaps Found

- Briefly states that a helper "accepts None silently" without quoting the
  exact line; this risks looking confident on a detail not visible in the
  inputs.
- Does not record that CI history was unavailable, even though that would
  affect confidence in regression risk.
- Mentions an internal runbook in passing; should be neutralized to a
  generic phrasing.

## Follow-up Actions

- No skill rewrite for v0.9.0.
- Future candidate: `code-reviewer` output contract could require an
  explicit "what was unavailable for this review" line, similar to the
  evidence section in `issue-investigator`.
