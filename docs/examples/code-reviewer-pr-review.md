# Code Reviewer PR Review Example

## Input Prompt

```text
Use the code-reviewer skill in PR mode.

Review target: pull request that changes invoice search pagination.
Issue context: story says users must keep the same filters while moving between pages.
Base branch: main.
```

## Assumed Available Context

- PR diff or local branch diff.
- Story or issue with acceptance criteria.
- Existing search/pagination tests and any new tests in the PR.
- Repository standards supplied by the repo, not private assumptions.

## Expected Skill Behavior

- Review issue/ticket alignment before general code quality.
- Reuse `issue-investigator` if the expected behavior or root cause is unclear.
- Group findings by severity with evidence and confidence.
- Separate blocking findings from advisory notes.
- Finish with one final verdict from the contract vocabulary.

## Sample Output Structure

```markdown
## Code Review - example-repo @ feature/invoice-pagination

- Review scope: PR diff against main.
- Review mode: pr
- Issue awareness: issue-aware
- Base: main
- Files reviewed: 6/6 after filtering
- Standards used: repo README and existing test patterns

## Issue/Ticket Alignment Result

- Issue summary: preserve invoice filters while paginating.
- Alignment verdict: partially aligned

## Findings Grouped By Severity

### major: Page navigation drops the status filter

- Severity: major
- Title: Page navigation drops the status filter
- Affected file/area: invoice search URL builder
- Evidence: ...
- Why it matters: users see invoices outside their selected status on page 2.
- Suggested fix: include all active filters when building next/previous URLs.
- Confidence: high
- Blocking/advisory decision: blocking

## Final Verdict

- Verdict: REQUEST_CHANGES
- Reason: core acceptance criterion is not met.
```

## What The Skill Should Avoid

- Starting with style nits before checking ticket alignment.
- Guessing acceptance criteria that were not supplied.
- Reporting formatter noise as review findings.
- Returning `PASS` when skipped files or missing issue context materially limit review confidence.
