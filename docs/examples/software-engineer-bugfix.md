# Software Engineer Bugfix Example

## Input Prompt

```text
Use the software-engineer skill to fix a bug in this repository.

Bug: users with an expired reset-token link see a 500 error instead of a helpful expired-link page.
Issue context: the bug report includes one screenshot, expected behavior, and a staging URL.
Validation: run the existing auth tests and any focused regression test you add.
```

## Assumed Available Context

- Repository with an auth or account-recovery area.
- Bug report with expected behavior, actual behavior, affected environment, and screenshot.
- Existing tests around reset-token validation or error handling.
- Local command for focused tests, such as `npm test -- reset-token` or `pytest tests/auth`.

## Expected Skill Behavior

- Gather repository, issue, and test context before editing.
- Invoke or reuse `issue-investigator` if expected behavior, reproduction, or root cause is unclear.
- State a short implementation plan and likely affected files.
- Add or update a focused regression test before or with the fix.
- Run relevant validation and disclose anything skipped.
- Invoke or reuse `code-reviewer` at the review gate before final status.

## Sample Output Structure

```markdown
## Engineering Result

- Task summary: expired reset-token links should render an expired-link page instead of 500.
- Context reviewed: issue report, auth controller, token validator, existing reset-token tests.
- Assumptions and missing context: staging logs were not available; local reproduction used a seeded expired token.
- Implementation plan: add regression test, handle expired-token exception, preserve invalid-token behavior.
- Files/areas likely affected: auth controller, token validation service, auth tests.
- Changes made or proposed: ...
- Validation performed: ...
- Tests run: ...
- Risks and rollback notes: ...
- Code-reviewer handoff/result: ...
- Final status: complete
```

## What The Skill Should Avoid

- Guessing root cause without reproduction or code evidence.
- Claiming tests passed without running them.
- Expanding scope into unrelated account-recovery redesign.
- Treating missing product intent as an implementation detail.
