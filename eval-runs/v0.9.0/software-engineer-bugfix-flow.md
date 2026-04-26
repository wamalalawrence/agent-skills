# Eval Run: `software-engineer` - Bugfix Flow

- Scenario: [`evals/software-engineer-bugfix-flow.md`](../../evals/software-engineer-bugfix-flow.md)
- Skill under test: `software-engineer`
- Release: `v0.9.0`

> **Illustrative run.** Maintainer-authored example output, not a verbatim
> capture from a single specific model.

## Run Setup

- Host: generic chat-style assistant with file read and shell access.
- Mode: `in-repo`.
- Tools available: file read, `git diff`, test runner.
- Inputs withheld: production logs, real Jira ticket.

## Inputs Provided

- Investigation handoff from `issue-investigator` with status `suspected
  cause: stale overdue-list cache after payment events`.
- Repository checkout with the relevant service and tests.
- Acceptance criterion: paid invoices do not appear in the overdue list
  within 30 seconds of payment confirmation.

## Skill Output (Illustrative)

```text
Phase 1 - Context discovery
- Read service/payments.py and shared/cache.py.
- Read tests/test_payments.py.
- Confirmed cache write happens in a different module than the listing read.

Phase 2 - Implementation
- Added cache eviction on payment-recorded event.
- Updated cache key shape to (user_id, region) to match listing side.
- Added unit test for eviction; added integration test exercising the
  listing endpoint after a recorded payment.
- Inner-loop code-reviewer hook: invoked on staged diff. Findings: minor
  helper-None case; no blockers.

Phase 3 - QA
- Ran unit tests locally: pass.
- Ran integration test locally: pass.
- Ran lint: pass.
- Outer-loop code-reviewer hook: invoked on branch diff. Findings: no
  blockers; one suggestion to record what was unavailable.

PR preparation
- Title prefixed with placeholder ticket key per repo convention.
- PR body includes: summary, evidence pack reference, test results, risks,
  rollback note (revert single commit), and explicit handoff to
  `manual-tester` and `test-automation-engineer`.

Risks
- Cache key shape change is backward compatible for existing entries
  because old keys naturally expire; documented in PR body.

Stopping point
- Awaiting manual retest from `manual-tester` and regression decision from
  `test-automation-engineer` before merge.
```

## Scoring

| Criterion | Score | Note |
| --- | --- | --- |
| Context awareness | 3 | Reads relevant modules before changing code. |
| Evidence discipline | 3 | Cites read files and test results. |
| Correct handoff | 3 | Inner/outer review hooks; downstream handoffs. |
| Output contract completeness | 3 | All phases visible. |
| Specificity / actionability | 3 | Concrete files, tests, and PR fields. |
| Hallucination avoidance | 2 | Claims local test pass without log excerpt. |
| Test / validation realism | 3 | Adds a test at the right level. |
| Risk awareness | 2 | Brief rollback; no feature-flag or canary. |
| Correct stopping behavior | 3 | Stops before merge, awaits handoffs. |
| Portability / public-safety | 1 | Implies a real ticket key convention. |

**Total: `26/30`.**

## Strengths

- Phases are clearly separated with explicit code-reviewer hooks.
- Adds the right test level (integration) instead of only unit tests.
- Stops before merge and waits for downstream skills.

## Failure Modes / Gaps Found

- Asserts local tests passed without showing a representative excerpt.
- Risk plan is shallow: no mention of feature flag, canary, or how to
  detect the symptom in production after deploy.
- Phrasing implies a fixed company ticketing convention; should be more
  portable.

## Follow-up Actions

- No skill rewrite for v0.9.0.
- Future candidate: extend the QA/PR-preparation contract to include a
  "post-deploy detection" or "rollback signal" line where applicable.
