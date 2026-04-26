# Eval Run: `issue-investigator` - Bug Root Cause

- Scenario: [`evals/issue-investigator-bug-root-cause.md`](../../evals/issue-investigator-bug-root-cause.md)
- Skill under test: `issue-investigator`
- Release: `v0.9.0`

> **Illustrative run.** The transcript below shows the kind of output a
> competent assistant should produce when the skill is loaded with the inputs
> recorded here. It is not a verbatim capture from a single specific model.

## Run Setup

- Host: generic chat-style assistant with file read access to the local repo.
- Mode: `in-repo`.
- Tools available: file read, shell (read-only commands only).
- Tools deliberately withheld: Jira access, production database, log
  aggregator, deployment history.
- Why withheld: to test the evidence-gate behavior of the skill when the
  obvious sources of truth are missing.

## Inputs Provided

- User report: invoices marked as paid still appear in the overdue invoice
  list after a recent release.
- Reproduction notes: create invoice, mark paid in UI, refresh overdue list,
  invoice still visible.
- Log excerpt showing the payment event was accepted.
- No code, no DB access, no Jira ticket, no production credentials.

## Skill Output (Illustrative)

```text
Investigation result
- Status: under investigation
- Confidence: low

Behavior
- Expected: invoices marked paid should disappear from the overdue list on
  refresh.
- Actual: invoice remains visible after refresh.
- Affected scope: overdue invoice listing UI; payment recording flow appears
  to succeed.

Evidence reviewed
- User reproduction notes (manual UI steps).
- Log excerpt: payment event accepted.
- Not reviewed: code, DB schema/state, deployment history, Jira ticket.

Reproduction status
- Reproducible by user; not yet reproduced in a controlled environment.

Root cause status
- Unknown. Symptom is consistent with: (a) a stale read on the overdue list,
  (b) the paid status not propagating to the listing query, or (c) a cache
  layer between the payment event and the listing.

Recommended next action
- Hand off to `software-engineer` only after evidence gate is met.
- Before handoff, the requester should provide one of: the listing query/code
  path, recent migrations, or read access to a non-production environment.

Open questions / missing evidence
- Which release introduced the symptom?
- Is the overdue listing query reading from a cache or read-replica?
- Does the payment event update the same record the listing reads from?
```

## Scoring

| Criterion | Score | Note |
| --- | --- | --- |
| Context awareness | 3 | Uses the supplied symptom and log excerpt. |
| Evidence discipline | 3 | Separates reviewed vs not-reviewed clearly. |
| Correct handoff | 3 | Defers to `software-engineer` only past the gate. |
| Output contract completeness | 3 | All required sections present. |
| Specificity / actionability | 2 | Lists candidate causes; could name safe checks. |
| Hallucination avoidance | 3 | Does not invent code, releases, or tickets. |
| Test / validation realism | 2 | Mentions controlled repro; no concrete steps. |
| Risk awareness | 3 | Flags cache and propagation risks. |
| Correct stopping behavior | 3 | Refuses confident root cause; sets gate. |
| Portability / public-safety | 1 | Mentions "production database" generically. |

**Total: `26/30`.**

## Strengths

- Strong stopping behavior and explicit evidence gate before handoff.
- Output contract is honored end to end.
- Candidate causes are listed without being asserted as conclusions.

## Failure Modes / Gaps Found

- Does not propose specific safe, read-only commands the user could run to
  narrow the cause (for example: confirm whether the listing query reads from
  a read replica, or whether the payment write and listing read share a
  transaction boundary).
- Risk language briefly mentions "production database" generically. The skill
  could remind the user not to run mutating production checks.

## Follow-up Actions

- No skill rewrite for v0.9.0. Gap recorded here.
- Future change candidate: `issue-investigator` could include a short
  "safe checks the user can run" subsection in its output contract when the
  caller has read access but not write access.
