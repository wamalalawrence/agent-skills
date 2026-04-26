# Software Engineer Eval: Bugfix Flow

## Input Context

A user asks for a bug fix: a search endpoint returns archived records even when the request includes
`includeArchived=false`. The user provides expected behavior and a short reproduction, but no test
command, no framework details, and no existing code excerpts.

## Skill Under Test

`software-engineer`

## Expected Behavior

- Starts with context discovery and identifies missing repo/build/test information.
- Uses or requests `issue-investigator` evidence before treating root cause as known.
- Proposes the smallest safe plan before editing.
- Requires a failing regression test path before the fix when feasible.
- Plans validation through local repo commands and code-reviewer handoff.

## Required Output Fields

- Task summary.
- Context reviewed.
- Assumptions and missing context.
- Implementation plan.
- Files or areas likely affected.
- Changes made or proposed.
- Validation performed and tests run.
- Risks and rollback notes.
- Code-reviewer handoff/result.
- Final status.

## Must Not Do

- Must not jump straight to a speculative code patch.
- Must not claim a root cause or tests without evidence.
- Must not skip the regression-test strategy for a bug fix.
- Must not over-prescribe a framework that was not supplied.

## Pass/Fail Checklist

- [ ] Missing repository/build context is requested or clearly marked.
- [ ] Bugfix flow includes investigation and reproducible evidence.
- [ ] Plan is specific but bounded.
- [ ] Validation claims are honest.
- [ ] Code-reviewer handoff is included before final completion.
