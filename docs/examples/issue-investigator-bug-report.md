# Issue Investigator Bug Report Example

## Input Prompt

```text
Use the issue-investigator skill.

Bug report: exporting a filtered CSV sometimes includes rows outside the selected date range.
Affected area: reports page, staging build 2026.04.18.1.
Evidence: user screenshot of filters, downloaded CSV sample, and one API response snippet.
```

## Assumed Available Context

- Bug report with filter values, sample output, and affected environment.
- Access to relevant code paths, tests, or API contract.
- Optional logs or request/response data with sensitive values removed.

## Expected Skill Behavior

- Classify the issue type and distinguish expected vs actual behavior.
- Inspect the report, sample data, and relevant code/config/tests.
- Attempt safe reproduction with anonymized or local data if possible.
- Track hypotheses and mark root-cause status as `unknown`, `suspected`, `confirmed`, or
  `disproved`.
- Recommend the next action based on evidence, not intuition.

## Sample Output Structure

```markdown
## Investigation Result

- Issue summary: filtered CSV export includes out-of-range rows for some date ranges.
- Issue type classification: bug/regression candidate.
- Confidence level: medium

## Behavior

- Expected behavior: exported rows match the active date filter.
- Actual behavior: sample CSV includes rows dated before the selected start date.
- Scope / affected users: report users exporting filtered CSVs in staging.

## Evidence Reviewed

- Ticket / issue context: ...
- Logs / screenshots / traces: ...
- Code / config / data / CI / deployment evidence: ...

## Root Cause

- Root cause status: suspected
- Root cause: ...
- Supporting evidence: ...

## Recommended Next Action

- Recommendation: reproduce with controlled fixture, then hand off to software-engineer.
- Fix/clarification/test recommendations: ...
```

## What The Skill Should Avoid

- Declaring root cause `confirmed` from one sample file alone.
- Treating inaccessible logs as proof that no backend issue exists.
- Recommending a code fix when expected behavior is still unclear.
- Using real customer data in reproduction notes.
