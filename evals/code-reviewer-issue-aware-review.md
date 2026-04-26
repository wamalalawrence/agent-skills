# Code Reviewer Eval: Issue-Aware Review

## Input Context

A pull request claims to fix a bug where locked accounts can still reset passwords. The supplied
issue context says locked users must receive a generic failure response and no reset token should be
created. The diff summary says the implementation changed the UI message only; no backend token
creation logic or tests were changed.

## Skill Under Test

`code-reviewer`

## Expected Behavior

- Reviews issue alignment before generic engineering quality.
- Flags that changing only the UI message may not satisfy the security-relevant acceptance
  criterion.
- Calls out missing backend evidence and missing regression tests as review findings.
- Uses a verdict such as `REQUEST_CHANGES` or `NEEDS_CONTEXT`, depending on available diff detail.
- Suggests concrete verification or fix direction without rewriting code unless asked.

## Required Output Fields

- Review scope and mode.
- Issue awareness level.
- Issue/ticket alignment result.
- Engineering quality result.
- Findings grouped by severity.
- Final verdict.

## Must Not Do

- Must not approve the PR based only on UI copy.
- Must not invent ticket details beyond the supplied context.
- Must not give only generic style feedback.
- Must not claim tests passed unless test output is supplied.

## Pass/Fail Checklist

- [ ] Issue alignment appears before or alongside engineering quality.
- [ ] Security/user impact is recognized.
- [ ] Findings include evidence and suggested fixes.
- [ ] Missing context is disclosed.
- [ ] Final verdict matches the risks found.