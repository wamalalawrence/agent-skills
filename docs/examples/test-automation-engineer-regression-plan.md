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

- Name the task mode. This one is `new-automation`; a broken suite or a wall of CI failures would
  run a different workflow.
- Discover the repository's automation stack before proposing an approach, and follow it.
- Decide whether the scenario is valuable and stable enough to automate.
- Prefer the lowest reliable test level.
- Define fixtures, selectors/contracts/assertions, CI integration, and debug artifacts.
- Identify flakiness risks and remaining manual coverage.
- Ask `code-reviewer` for test-quality review if automation code is written.
- Persist the result in the evidence pack's `automation:` block, and keep the link from the
  acceptance criterion to the automated check.

## Sample Output Structure

```markdown
## Automation Strategy

- Mode: new-automation — stable behaviour with manual evidence, no existing coverage.
- Stack discovered: pytest + requests API suite under tests/api, Playwright smoke under
  tests/smoke, `make test-api` locally and in CI, fixtures per worker.
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

## Validation Run

- Commands actually run: `make test-api -- -k saved_filters`
- Result: 6 passed
- Stability: 20 repeats, 20 passed (`pytest --count=20`)
- CI-equivalent: verified — same target, same fixtures

## Review Notes

- Traceability: acceptance criterion 2 → "saved filters are private to their owner" → the two
  API tests, tagged
  `@privacy`; recorded in the evidence pack's coverage map.
- Remaining manual coverage: visual placement and rename/delete UX.
```

## What The Skill Should Avoid

- Automating before expected behavior and reproduction are stable.
- Using real user data or shared mutable fixtures.
- Choosing UI/e2e when an API test gives clearer confidence.
- Hiding flakiness behind blind retries.
- Introducing a second framework, selector convention, or client alongside the one the repository
  already uses.
- Reporting a stability run, or a CI-equivalent run, that did not happen.
