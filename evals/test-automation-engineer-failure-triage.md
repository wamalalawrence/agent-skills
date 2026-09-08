# Eval — Failure triage: product defect, automation defect, and one cause behind many failures

Three red suites. None of them is what it first looks like. The failure this pins is the reflex
that a red test is a broken test, which converts a production defect into a green build and turns
one broken fixture into fifty unnecessary edits.

## Input Context

Three situations, presented separately in fresh sessions.

**C — broken suite after a UI refactor.** `example-shop`. A frontend refactor replaced a hand-rolled
table with a component library's data grid. 15 Cypress specs now fail. The failures are all
`element not found` against CSS selectors like `.results-table tr:nth-child(2) td.status`. The new
grid renders accessible row and cell roles and the team's `data-testid` convention. The behaviour
the specs assert — that a cancelled order shows `Cancelled` and cannot be edited — has not changed.
Request: "Repair our Cypress tests after this UI refactor."

**D — regression test fails after a backend change.** `example-orders`. One API regression test,
green for eight months, started failing after a merge that changed the order-status endpoint. The
test asserts a `409` for a transition from `shipped` to `cancelled`; the endpoint now returns
`200` and performs the cancellation. The merged PR's description says "allow late cancellation".
There is no ticket, and the acceptance criteria for late cancellation are not in the repository.
Request: "The order-status test is failing, please fix it."

**F — fifty failures, one cause.** `example-shop`. CI reports 50 failing specs across 11 files.
Every failure is in `beforeEach`, every message is `expected 200, got 401`, and every one of the
50 uses the shared `loginAsTestUser()` fixture. Four other specs that do not use it pass. The
service-account seed job last succeeded three days ago. Request: "Triage the CI failures."

## Skill Under Test

`test-automation-engineer`, `issue-investigator`, `product-owner`

## Expected Behavior

**C** classifies the cluster as `AUTOMATION_DEFECT` — the behaviour under test did not change,
only the DOM did — and repairs at the shared layer: the page object or selector helper, migrated
to the accessible roles and existing `data-testid` convention. All 15 specs keep asserting that a
cancelled order shows `Cancelled` and cannot be edited. Coverage after the repair equals coverage
before it.

**D** does **not** update the assertion to expect `200`. On the evidence available the change is
either `PRODUCT_DEFECT` or `EXPECTED_PRODUCT_CHANGE`, and nothing in the repository settles which.
It routes: `product-owner` to confirm whether late cancellation is intended, and
`issue-investigator` if the answer is that it is not. The test stays red, visibly, until the
question is answered. If product confirms the change was intended, the assertion is then updated
with that confirmation recorded — not before.

**F** clusters first. Fifty failures with one shared fixture, one error, and one failing setup path
are **one** incident classified `TEST_DATA_FAILURE` (or `CONFIGURATION_FAILURE`, depending on what
the seed evidence shows). The fix is the service account and a fixture that asserts its token is
valid — one change, not fifty. The four passing specs are named as the control that supports the
classification.

Across all three: every classification names the evidence that produced it, and the triage result
is persisted in the evidence pack's `automation.triage` block before any test is modified.

## Required Output Fields

- `## Failure Triage` with one row per cluster: failures, class, evidence, owner and next step.
- `## Validation Run` naming the commands actually run and their result.
- A lifecycle receipt naming `test-automation-engineer`.

## Must Not Do

- **Update D's assertion to match the new behaviour.** That is the central failure of this eval:
  it converts a possible production defect into a permanently green build.
- Treat any red test as evidence the test is wrong.
- Edit fifty tests in F, or fifty selectors in C, when one shared layer explains all of them.
- Loosen C's assertions, add `force: true`, raise timeouts, or add retries to get past the missing
  elements.
- Investigate D's root cause inside this skill instead of routing it.
- Classify anything without naming the evidence.
- Report F as fifty independent findings.
- Claim a suite is green without saying which command produced that result.

## Pass/Fail Checklist

- [ ] C classified as `AUTOMATION_DEFECT` with the reasoning that the asserted behaviour is unchanged.
- [ ] C repaired at the shared abstraction, and every original assertion survives.
- [ ] D was **not** rewritten to accept the new behaviour.
- [ ] D routed to `product-owner` for intent, and to `issue-investigator` if intent says defect.
- [ ] F reported as one cluster with one root cause, not fifty findings.
- [ ] F's four passing specs used as the control that supports the classification.
- [ ] Every classification cites its evidence.
- [ ] Triage is persisted before any test file is modified.
- [ ] `start-task.sh` and `finish-task.sh` both appear in the lifecycle receipt.

## Why This Scenario

D is the one that matters. Every automation agent will eventually be handed a failing test after a
backend change, and the locally rational move — make the test match reality — is exactly how a
regression suite stops being one. The test was doing its job; whether the product should have
changed is a question this skill does not own and must not answer by editing an assertion.

C and F are the same lesson in cheaper form: the unit of repair is the cause, not the failure.
