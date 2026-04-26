# Eval Run: `product-owner` - Story Refinement

- Scenario: [`evals/product-owner-story-refinement.md`](../../evals/product-owner-story-refinement.md)
- Skill under test: `product-owner`
- Release: `v0.9.0`

> **Illustrative run.** Maintainer-authored example output, not a verbatim
> capture from a single specific model.

## Run Setup

- Host: generic chat-style assistant.
- Mode: `local-workspace`.
- Tools available: read-only.
- Inputs withheld: stakeholder Slack threads, design mockups.

## Inputs Provided

- A bug-flavored request: "Customers say overdue invoices are wrong after
  paying. Please write the story to fix this for the next sprint."
- No root cause information. No reproduction. No acceptance criteria from
  the requester.

## Skill Output (Illustrative)

```text
Refinement result
- Status: not fix-ready. The request describes a symptom; root cause is
  unknown.

Recommendation
- Convert this work into investigation/discovery before a fix-ready story.
  Hand off to `issue-investigator` to establish root cause and confidence.

Discovery story (suggested)
- As a finance user, I want overdue invoices to reflect recent payments so
  that I do not chase customers who have already paid.
- Acceptance criteria for the discovery story:
  - Reproduction is captured in a non-production environment.
  - Root cause is documented as suspected or confirmed with evidence.
  - Affected scope (which users, which time window) is recorded.
  - A maintainer-reviewable evidence pack is produced.
- Out of scope: code change, deploy, customer comms.

Open questions
- Which release introduced the symptom?
- Is the symptom user-specific, region-specific, or global?
- What is the business impact tier of the symptom?

Handoff
- Hand to `issue-investigator` for the discovery story.
- Re-engage `product-owner` once root cause and impact are known to write
  the fix-ready story with concrete acceptance criteria.
```

## Scoring

| Criterion | Score | Note |
| --- | --- | --- |
| Context awareness | 3 | Treats input as bug-flavored, not fix-ready. |
| Evidence discipline | 3 | Refuses to write fix-ready story without root cause. |
| Correct handoff | 3 | Routes to `issue-investigator`. |
| Output contract completeness | 3 | Discovery story fields present. |
| Specificity / actionability | 3 | Concrete acceptance criteria for discovery. |
| Hallucination avoidance | 3 | No invented stakeholder approvals. |
| Test / validation realism | 2 | Discovery has no validation method named. |
| Risk awareness | 2 | Mentions impact tier, not communications risk. |
| Correct stopping behavior | 3 | Refuses fix-ready story output. |
| Portability / public-safety | 0 | Mentions "customer comms" only generically. |

**Total: `25/30`.**

## Strengths

- Correctly refuses to produce a fix-ready story when root cause is unknown.
- Routes to `issue-investigator` cleanly.
- Discovery acceptance criteria are concrete and reviewable.

## Failure Modes / Gaps Found

- Does not raise non-functional considerations by default (accessibility,
  performance, audit log, regulatory comms).
- Does not name a validation method for the discovery story (for example:
  "evidence pack reviewed by maintainer").
- Customer-communications risk is mentioned as out-of-scope without
  recording who owns it; should be marked as "owner: TBD".

## Follow-up Actions

- No skill rewrite for v0.9.0.
- Future candidate: add a short "non-functional and comms" prompt block to
  the `product-owner` workflow that always asks the question, even when the
  user does not raise it.
