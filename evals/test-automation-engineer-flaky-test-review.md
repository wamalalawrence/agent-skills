# Test Automation Engineer Eval: Flaky Test Review

## Input Context

A UI end-to-end test intermittently fails in CI. The test logs in, creates a report, waits five
seconds, then asserts that the report appears in a table. Failures show the report sometimes appears
after six to eight seconds. The app has an API for creating report data and the UI has accessible
table row names.

## Skill Under Test

`test-automation-engineer`

## Expected Behavior

- Identifies fixed sleeps and slow UI setup as flakiness risks.
- Recommends condition-based waits and lower-level setup through API or fixtures.
- Chooses the right test level and explains what should remain UI/e2e.
- Suggests repeat-run verification and useful CI artifacts.
- Uses `code-reviewer` test-quality review for changed automation code when implementation is in
  scope.

## Required Output Fields

- Automation strategy.
- Test design.
- Implementation plan.
- Review notes.

## Must Not Do

- Must not recommend blind retries as the main fix.
- Must not rely on real third-party services or production data.
- Must not automate unclear assertions.
- Must not claim the flake is fixed without repeat-run evidence.

## Pass/Fail Checklist

- [ ] Flakiness root contributors are identified from supplied evidence.
- [ ] Proposed waits are observable and deterministic.
- [ ] Test data setup is isolated and repeatable.
- [ ] CI/repeat-run validation is realistic.
- [ ] Remaining manual or lower-level coverage is stated.