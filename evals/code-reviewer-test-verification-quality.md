# Code Reviewer Eval: Test Verification Quality

Four review scenarios. Two contain real test defects, two contain tests that look mock-heavy and are
correct. The eval fails a reviewer that finds problems in all four as readily as one that finds them
in none — the point is discrimination, not suspicion of mocks.

## Skill Under Test

`code-reviewer`

## Input Context

### D — Refactor-fragile test

A PR refactors `OrderTotals` so the tax lookup moves from the service into the calculator. No
behaviour changes. The diff also updates a test that now fails:

```java
verify(taxRuleSet).rateFor(order);
verify(discountPolicy).apply(order, BASE);
verify(calculator).total(order, Percent.of(21), EUR("80.00"));
```

The class's contract is the total it returns. `total()` is asserted nowhere in the test.

### E — Interaction really is the behaviour

A PR adds `AuditPublisher`. Requirement: every permission change emits exactly one
`PermissionChanged` event to the audit topic, and a retried request must not emit a second. The test
doubles the topic client and asserts one event with the expected payload on first call, and no
further event on the retry. There is no persisted state or return value that records the emission.

### G — Coverage-driven tests

A PR raises line coverage on a `ReportBuilder` from 62% to 84%. The new tests call every public
method and assert `assertThat(result).isNotNull()`, plus two that assert
`assertThat(rows).hasSize(3)` on a fixture whose size is set in the test's own setup. The PR
description says the change was needed to pass the coverage gate.

### J — Mock-heavy orchestrator

A PR adds `OnboardingOrchestrator`, whose entire job is to coordinate four side-effecting ports in
order: provision the account, seed default settings, send the welcome email, and publish an
`AccountReady` command. Failure of any step must stop the ones after it. The test doubles all four
ports and asserts the calls, including that nothing after a failing step is invoked. It does not
verify any getters or internal helper calls.

## Expected Behavior

**D.** Raises a `major`: the test verifies implementation choreography rather than the behaviour the
class promises, and it broke under a refactor that changed nothing observable. Suggests asserting
the returned total (and the boundary cases the verifications were standing in for) rather than
patching the verifications to match the new call graph. Names the specific coupling — the test
recorded a design decision as if it were a requirement.

**E.** Raises no finding against the mocking or the interaction assertions. If the reviewer comments
at all, it is to confirm the interaction is the contract: emission has no observable state, "exactly
once" and "not twice on retry" are the requirement, and the payload assertion carries the behaviour.
A finding that the test should use real collaborators or state verification here is itself an error.

**G.** Raises a `major` (or `blocker` where the repository treats unverified behaviour as blocking):
the tests execute lines without protecting behaviour, `isNotNull` asserts almost nothing, and the
`hasSize(3)` assertions restate the test's own setup rather than a rule of the report. States that
the coverage movement is not evidence of confidence, and asks for assertions on the report's actual
rules — grouping, ordering, totals, empty and error inputs. Does not demand the tests be deleted
outright if the coverage gate is mandatory; asks for them to be made meaningful, and notes if the
gate is being met at the cost of test value.

**J.** Accepts interaction-focused testing: coordinating side-effecting ports in a defined order,
and stopping on failure, is the observable contract of an orchestrator, and each port is an external
boundary. Raises no finding merely because four doubles appear. May raise a `minor` if it finds
verification of something outside the contract, and may note that any pure decision logic inside the
orchestrator would be better tested directly — but must not require the ports be made real, and must
not treat the number of doubles as the finding.

## Required Output Fields

- Findings with severity, affected file/area, evidence, why it matters, suggested fix, confidence,
  and blocking status.
- Review limitations where context was unavailable.
- A final verdict from `PASS`, `PASS_WITH_NOTES`, `REQUEST_CHANGES`, `NEEDS_CONTEXT`,
  `NOT_REVIEWABLE`.

## Must Not Do

- Must not raise a finding against mocks, stubs, or `verify(...)` on principle in E or J.
- Must not accept D on the grounds that the verifications were updated and the suite is green.
- Must not accept G on the grounds that coverage rose or the gate now passes.
- Must not state a maximum number of test doubles, a mock-to-assertion ratio, or any numeric
  threshold as the basis of a finding.
- Must not require a testing school, or test-first authoring, as a condition of approval.
- Must not emit the same test finding across all four scenarios; the two correct tests must come
  back clean on the test-double question.

## Pass/Fail Checklist

- [ ] D and G produce evidence-backed findings that name the unprotected behaviour.
- [ ] E and J produce no finding against the use of doubles or interaction verification.
- [ ] Every test finding names a behaviour left unprotected or a coupling that breaks under a
      behaviour-preserving refactor — not the presence or count of doubles.
- [ ] G's response separates the coverage number from the confidence claim.
- [ ] The verdict for each scenario follows from its findings, and limitations are disclosed.
