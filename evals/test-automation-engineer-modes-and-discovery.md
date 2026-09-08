# Eval — Task mode, framework discovery, and the decision not to automate

Five requests that all sound like "write some tests" and each need a different workflow. The
failure this pins is the one that makes an automation agent expensive: running the new-coverage
workflow on every request, and reaching for a familiar framework instead of the repository's.

## Input Context

Five requests, presented separately in fresh sessions.

**A — new UI automation.** `example-shop`, a TypeScript web app. `package.json` has
`@playwright/test`, page objects under `tests/e2e/pages/`, `data-testid` selectors throughout the
components, `npm run e2e` locally and a sharded variant in CI. A refined story carries four
acceptance criteria for the guest-checkout flow, confirmed by product and already manually tested.
Request: "Automate the guest checkout acceptance criteria."

**B — API automation.** `example-orders`, a Java service. It has JUnit unit tests and an existing
integration harness using Testcontainers and REST Assured under `src/it/`. There is a small
Selenium suite in a separate repository. Request: "Add regression coverage for the order-status
transitions." The transitions are fully observable through the service's HTTP API.

**G — automation backlog.** A manual regression pack of 63 scenarios, exported from a
spreadsheet. Mixed: payment paths, form validation rules, a PDF layout check, three scenarios that
duplicate each other at different levels, two for a feature removed last quarter, and four whose
expected result column reads "looks correct". Request: "Work out what we should automate."

**H — expensive suite.** `example-shop` again. The e2e suite runs 70 minutes. Inspection shows 31
of its 96 specs assert password-strength and email-format validation rules through the browser,
9 duplicate assertions already covered by unit tests, and 6 exercise cross-service checkout
against the real payment sandbox. Request: "This suite is too slow."

**K — unknown framework.** `example-telemetry`, a repository whose tests run under a framework the
agent has no prior knowledge of. Tests live in `verification/`, invoked by a documented
`make verify` target, with a fixture convention and an assertion helper visible in the existing
files. Request: "Add coverage for the new retention rule."

## Skill Under Test

`test-automation-engineer`

## Expected Behavior

**A** names the mode `new-automation`, discovers Playwright and the existing page objects and
`data-testid` convention before proposing anything, and implements inside that structure. It does
not add a second selector scheme or a parallel abstraction layer. It arranges state through the
API or a fixture rather than driving the UI through setup, waits on observable conditions, and
chooses which of the four criteria genuinely need a browser.

**B** names the mode and considers the API/integration level *before* UI. Order-status transitions
are observable over HTTP, so the coverage lands in the existing REST Assured harness rather than
in a new browser suite. If any UI coverage is proposed, it is one thin path with a stated reason.

**G** returns dispositions, not 63 tests. The duplicates are `REMOVE_DUPLICATE` or
`MOVE_TO_LOWER_LEVEL`, the removed feature's scenarios are `OBSOLETE`, the PDF layout check is
`KEEP_MANUAL`, and the four "looks correct" scenarios are `NEEDS_CLARIFICATION` routed to
`product-owner` — not automated against a guessed expectation. Each row carries a one-line reason.

**H** identifies the 31 validation specs as belonging at unit level and the 9 duplicates as
removable, keeps the cross-service checkout specs at e2e because that is where their failure mode
lives, and states what confidence is given up. It does not pursue a pyramid ratio and does not
propose deleting coverage to hit a runtime number.

**K** discovers the convention from the existing tests, the runner target, and the CI invocation,
then follows it. An unfamiliar framework is not treated as a blocker and not replaced.

Across all five: the mode is named with a one-line reason, and the mode actually changes which
steps run.

## Required Output Fields

- `## Automation Strategy` carrying the mode, the discovered stack, and the chosen levels.
- `## Automation Backlog` for G, with a disposition and a reason per scenario.
- A lifecycle receipt naming `test-automation-engineer`.

## Must Not Do

- Run the new-coverage workflow on G or H, which are decision requests, not implementation requests.
- Propose Playwright, Cypress, or any other named tool for K because it is familiar. The
  repository's stack wins unless a written tradeoff says otherwise.
- Introduce a second page-object layer, selector convention, or HTTP client alongside an existing one.
- Automate B through the UI when the behaviour is observable at the API.
- Automate G's four "looks correct" scenarios against an assumed expectation.
- Emit a numeric priority score for G when the repository has no scoring model.
- Claim a suite runtime improvement for H that was not measured.
- Propose a framework migration without the tradeoff record and a named human owner.

## Pass/Fail Checklist

- [ ] Each request names exactly one primary mode, with a reason.
- [ ] Framework discovery ran before any implementation proposal in A, B, and K.
- [ ] A reuses the existing page objects and `data-testid` convention.
- [ ] B lands at API/integration level with the reason stated.
- [ ] G returns dispositions with reasons, including at least one `NEEDS_CLARIFICATION`.
- [ ] G's ambiguous scenarios are routed to `product-owner`, not automated.
- [ ] H names what moves down, what stays at e2e, and what confidence is given up.
- [ ] K follows the repository's own framework without proposing a replacement.
- [ ] No numeric score was invented for G.
- [ ] `start-task.sh` and `finish-task.sh` both appear in the lifecycle receipt.

## Why This Scenario

The cheap failure is uniformity: treating every automation request as "write tests", which turns
a backlog question into 63 unwanted specs and a runtime problem into more coverage. The other
failure is subtler and more common in practice — an agent that knows one framework well will
introduce it beside a perfectly good one, and the cost lands on whoever maintains both.
