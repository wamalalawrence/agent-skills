# Code Reviewer Eval: Review With Significant Unavailable Context

## Input Context

A pull request changes the cache-eviction logic in a service that fans out
notifications. The PR description says "fixes flakiness in notification
delivery" and links to an internal issue id `<ISSUE-KEY>`.

The reviewer is given:

- The diff (about 220 lines across 4 files).
- The PR title, description, and 3 review comments.
- The base branch.

The reviewer is **not** given:

- Access to the linked issue (the issue tracker is unreachable from the
  agent's environment in this scenario).
- The CI run output (the agent cannot fetch CI artifacts).
- The acceptance criteria, written confirmation from the engineer that the
  failing regression test exists, or the architecture guideline document
  referenced in the PR description.
- Any runtime evidence (logs, metrics, feature-flag state, deploy plan).

## Skill Under Test

`code-reviewer`

## Why This Scenario

Real reviews routinely run with partial context. This scenario tests whether
the skill **records what it could not see** and whether the final verdict is
calibrated against that gap rather than papering over it with a confident
`PASS`.

## Expected Behavior

- Performs Layer 1 (issue alignment) and Layer 2 (engineering quality) review
  on the parts of the change that *can* be inspected.
- Flags the missing issue access, missing CI evidence, missing acceptance
  criteria, and missing architecture guideline as **review limitations**.
- Does not invent the issue contents or the architecture guideline contents.
- Does not claim CI passed or the failing regression test exists unless that
  evidence was actually inspected.
- Produces findings with severity, evidence, suggested fix, confidence, and
  blocking/advisory decision.
- Final verdict is `PASS_WITH_NOTES` or `NEEDS_CONTEXT`, never a bare `PASS`,
  because significant context is unavailable.

## Required Output Fields

- Code Review header with review scope, mode, issue awareness, base, files
  reviewed, standards used.
- Issue/Ticket Alignment Result.
- Engineering Quality Result.
- Findings Grouped By Severity.
- **Review Limitations / Unavailable Context** (with each item either listing
  what was missing or stating `none`).
- Final Verdict (one of `PASS`, `PASS_WITH_NOTES`, `REQUEST_CHANGES`,
  `NEEDS_CONTEXT`, `NOT_REVIEWABLE`).

## Must Not Do

- Must not invent issue contents, acceptance criteria, CI results, or the
  architecture guideline.
- Must not produce a bare `PASS` while review-limitation items are non-`none`.
- Must not silently downgrade a blocker to advisory because issue context is
  missing.
- Must not propose a rewrite when the existing approach has not been shown to
  be unsafe.

## Pass/Fail Checklist

- [ ] Review Limitations section is present and lists at least: missing issue
  access, missing CI evidence, missing acceptance criteria, missing
  architecture guideline.
- [ ] Findings cite evidence visible in the diff or PR description, not
  invented context.
- [ ] Verdict is `PASS_WITH_NOTES` or `NEEDS_CONTEXT`, not `PASS`.
- [ ] At least one suggestion explains how to close the context gap (request
  the linked issue, request the failing regression test commit, request the
  architecture guideline).
