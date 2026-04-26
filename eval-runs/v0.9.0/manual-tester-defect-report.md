# Eval Run: `manual-tester` - Defect Report

- Scenario: [`evals/manual-tester-defect-report.md`](../../evals/manual-tester-defect-report.md)
- Skill under test: `manual-tester`
- Release: `v0.9.0`

> **Illustrative run.** Maintainer-authored example output, not a verbatim
> capture from a single specific model.

## Run Setup

- Host: generic chat-style assistant.
- Mode: `local-workspace`.
- Tools available: read-only.
- Inputs withheld: production access, real customer accounts, real
  screenshots.

## Inputs Provided

- A user report: "Refund button does nothing for some orders."
- An environment description: staging, recent build identifier, browser and
  OS placeholders.
- A request: produce a defect report and a short retest plan.

## Skill Output (Illustrative)

```text
Defect report
- Title: Refund button is non-responsive for orders in state X (suspected)
- Environment: staging build BUILD_ID; placeholder browser/OS; placeholder
  test user.
- Severity: medium (suspected; downgrade if not reproducible).
- Summary: clicking Refund on some orders produces no UI feedback and no
  network request is observed.

Reproduction
- Pre-conditions: staging account with at least one order in suspected
  state X.
- Steps:
  1. Sign in as the placeholder test user.
  2. Open order whose state is X.
  3. Click "Refund".
  4. Observe: no toast, no modal, no network request in DevTools Network.
- Expected: Refund modal opens or an error is displayed.
- Actual: nothing visible happens.

Evidence
- Console: no errors observed.
- Network: no request fired on click.
- Screenshot/video: not captured (placeholder tooling only).

Out of scope for this report
- Backend root cause (handoff to `issue-investigator`).
- Cross-browser scope beyond the listed placeholder.
- Performance, accessibility, security validation of the refund flow.

Retest plan (after fix)
- Repeat the four reproduction steps.
- Confirm Refund modal opens for state X.
- Confirm at least one alternate state (Y) still works.
- Confirm a known no-refund state (Z) shows the expected blocked message.
- Capture before/after screenshots and network traces.
```

## Scoring

| Criterion | Score | Note |
| --- | --- | --- |
| Context awareness | 3 | Uses the supplied environment placeholders. |
| Evidence discipline | 3 | Marks missing artifacts honestly. |
| Correct handoff | 3 | Routes root cause to `issue-investigator`. |
| Output contract completeness | 3 | Defect + retest plan, both complete. |
| Specificity / actionability | 3 | Numbered steps, expected vs actual. |
| Hallucination avoidance | 3 | No invented logs or screenshots. |
| Test / validation realism | 3 | Retest plan can actually be executed. |
| Risk awareness | 2 | Severity stated as suspected; minimal blast-radius. |
| Correct stopping behavior | 3 | Stops at evidence boundary. |
| Portability / public-safety | 0 | Uses placeholder tooling and accounts. |

**Total: `26/30`.**

## Strengths

- Strong reproduction structure with steps, expected, and actual.
- Honest about what evidence was not captured.
- Retest plan covers the affected state plus one alternate and one negative
  state.

## Failure Modes / Gaps Found

- Risk awareness is shallow: the report could note blast radius (which
  customers would be affected and over what window) at suspected severity.
- Does not list what it deliberately did **not** test beyond a one-line
  "out of scope" block; the contract could require a clearer "not tested
  and why" subsection.

## Follow-up Actions

- No skill rewrite for v0.9.0.
- Future candidate: extend `manual-tester` output contract with a "not
  tested and why" field distinct from "out of scope".
