# Manual Tester Eval: Defect Report

## Input Context

A tester observes that a profile form accepts an invalid phone number and then shows a success
toast. They know the expected behavior from acceptance criteria: invalid phone numbers must block
save and show an inline validation message. The tester has a staging URL, browser/version, test
account role, and anonymized input, but no screenshots yet.

## Skill Under Test

`manual-tester`

## Expected Behavior

- Produces a clear defect report with environment, build/version or commit if available, steps,
  expected behavior, actual behavior, severity, evidence needed, and retest guidance.
- Marks missing evidence honestly and asks for or recommends screenshot/log capture.
- Hands reproducible defect evidence to `issue-investigator` for root-cause analysis.
- Identifies whether this scenario is a stable automation candidate.

## Required Output Fields

- Manual test plan or execution summary.
- Test scenarios.
- Execution result.
- Defects found.
- Automation candidates.

## Must Not Do

- Must not claim a root cause.
- Must not say testing is complete if only one scenario was observed.
- Must not omit environment, role, data, or retest guidance.
- Must not include real customer data.

## Pass/Fail Checklist

- [ ] Defect report includes expected vs actual behavior.
- [ ] Evidence gaps are visible.
- [ ] Handoff to `issue-investigator` is clear.
- [ ] Severity is tied to user/business impact.
- [ ] Automation candidate is stable and justified.
