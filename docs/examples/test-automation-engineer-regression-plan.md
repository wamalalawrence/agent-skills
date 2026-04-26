# Test Automation Engineer Regression Plan Example

## Input Prompt

```text
Use the test-automation-engineer skill.

Scenario: saved report filters must remain private to the user who created them.
Manual evidence: manual tester reproduced cross-user visibility on staging and attached steps.
Repository context: web app with existing API tests and a small UI smoke suite.
CI context: PR checks run unit and API tests; UI smoke tests run nightly.
```

## Assumed Available Context

- Stable expected behavior and manual/repro steps.
- Existing test framework and CI commands.
- Test user or fixture strategy that avoids real customer data.
- Selectors, API contracts, or stable observable outcomes.

## Expected Skill Behavior

- Decide whether the scenario is valuable and stable enough to automate.
- Prefer the lowest reliable test level.
- Define fixtures, selectors/contracts/assertions, CI integration, and debug artifacts.
- Identify flakiness risks and remaining manual coverage.
- Ask `code-reviewer` for test-quality review if automation code is written.

## Sample Output Structure

```markdown
## Automation Strategy

- Automation goal: prevent saved filters from leaking across users.
- Scenarios to automate: API-level create/list saved filters with two users.
- Scenarios not to automate: subjective saved-filter list layout.
- Chosen test levels: API integration test in PR; UI smoke only for create/apply happy path.

## Test Design

- Test data / fixtures: two isolated users and one report fixture.
- Selectors/contracts/assertions: API list response includes only owner-created filters.
- Cleanup: delete created filters by id after test.
- Flakiness risks: shared test users and clock-based filter names.
- Debug artifacts: request/response payload on failure.

## Implementation Plan

- Files or test areas: existing saved-filter API tests.
- Existing patterns to follow: ...
- Commands to run: ...
- CI integration: include API test in PR checks.

## Review Notes

- Remaining manual coverage: visual placement and rename/delete UX.
```

## What The Skill Should Avoid

- Automating before expected behavior and reproduction are stable.
- Using real user data or shared mutable fixtures.
- Choosing UI/e2e when an API test gives clearer confidence.
- Hiding flakiness behind blind retries.
