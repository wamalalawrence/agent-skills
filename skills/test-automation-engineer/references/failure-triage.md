# Failure Triage And Flake Diagnosis

How to decide what a red test actually means, and what to do about a test that is red only
sometimes. Both start from the same refusal: **a failing test is not evidence that the test is
wrong.** It is evidence that the assertion and the system disagree, and which of the two is at
fault is the question, not the premise.

## Part 1 — Classifying failures

Every failure, or every cluster of failures, gets exactly one class. Assign it from evidence; when
the evidence does not support a class, `UNKNOWN` is the honest answer and it routes to more
investigation rather than to a code change.

| Class | Means | Owner of the fix |
| --- | --- | --- |
| `PRODUCT_DEFECT` | The product behaves differently from the agreed behaviour; the test is right | `issue-investigator`, then `software-engineer` |
| `AUTOMATION_DEFECT` | The test is wrong, brittle, or asserts something it should not | `test-automation-engineer` |
| `EXPECTED_PRODUCT_CHANGE` | Behaviour changed deliberately; the test encodes the old contract | `test-automation-engineer`, after product confirms |
| `FLAKY_TEST` | Same code, same input, non-deterministic result | `test-automation-engineer` (see Part 2) |
| `TEST_DATA_FAILURE` | Fixture, seed, or shared record is missing, stale, or mutated | `test-automation-engineer`, or the data owner |
| `ENVIRONMENT_FAILURE` | The environment under test is down, misconfigured, or contended | Environment owner; hand off with evidence |
| `DEPENDENCY_FAILURE` | An upstream service, sandbox, or third party failed | Dependency owner; hand off with evidence |
| `CONFIGURATION_FAILURE` | Runner, CI, credentials, or build configuration is wrong | Whoever owns that configuration |
| `UNKNOWN` | The evidence does not distinguish the classes above | Nobody yet — gather evidence first |

`EXPECTED_PRODUCT_CHANGE` is the one most often mislabelled as `AUTOMATION_DEFECT`. The difference
matters: one is a test to update, the other is a test that was doing its job and a decision that
needs confirming before the assertion is loosened.

## Evidence that supports a classification

Name the evidence you used. A classification without evidence is a guess with a label on it.

- The failure message and stack, read in full rather than by its first line.
- Traces, screenshots, videos, HAR files, and DOM snapshots the runner already produced.
- Application and service logs for the failing window.
- The product diff since the last green run — commits, merged PRs, config and flag changes.
- Actual API responses versus the contract the test asserts.
- Historical behaviour: when it last passed, how often it fails, on which shard or worker.
- A reproduction attempt, locally and against a CI-equivalent command.
- Environment health: service status, migrations applied, seed jobs, quota and rate limits.
- Fixture state before and after the failing test.
- Recent dependency, base-image, browser, or driver upgrades.

## Cluster before you fix

Fifty failures are rarely fifty problems. Group first, then classify the group.

```text
collect failures
      |
      v
group by shared signal ── failing fixture, shared helper, one endpoint,
      |                    one worker/shard, one page object, one deploy
      v
one class per group
      |
      v
fix the group's root cause once
```

Signals worth grouping on: identical error text, a common setup or fixture, a single endpoint or
component, one CI shard, a single deployment or migration, one browser or driver version, tests
that all authenticate the same way.

A group of fifty failures traced to one broken authentication fixture is **one** incident with one
fix. Editing fifty tests to accommodate it is not a fix; it is fifty new defects.

## Routing

Triage decides the owner. It does not license this skill to do the owner's job.

| Finding | Route to | With |
| --- | --- | --- |
| Suspected product defect | [`issue-investigator`](../../software-engineer/skills/issue-investigator/SKILL.md) | Failing test, evidence, the product diff you suspect |
| Defect whose root cause an investigation confirmed | [`software-engineer`](../../software-engineer/SKILL.md) | The investigation's result and the failing test that pins it |
| Intended behaviour unclear | [`product-owner`](../../product-owner/SKILL.md) | The assertion, the new behaviour, the question |
| Needs exploratory reproduction | [`manual-tester`](../../manual-tester/SKILL.md) | What to try, and what evidence would settle it |
| Automation defect | This skill | The repair, and what coverage must survive it |
| Infrastructure or build outside automation ownership | The owning team | Evidence, timing, and what is blocked |

## Part 2 — Flake diagnosis

A test that fails intermittently has a cause. "Flaky" is a symptom name, not a diagnosis, and
re-running until green converts a real defect into a silent one.

### Candidate causes

```text
timing            race conditions, async state not yet settled, animation and render timing,
                  eventual consistency, retries in the product masking latency
data              non-deterministic generated data, shared mutable records, leftover state
                  from a previous run, clock and timezone assumptions, unseeded randomness
isolation         test-order dependence, shared fixtures across workers, leaked sessions or
                  tokens, cleanup that failed silently, parallel execution conflicts
surface           selector instability, dynamic ids, re-rendered nodes, text that varies
                  by locale or formatting
environment       network and service instability, contended shared environments, rate limits,
                  resource exhaustion on the runner
```

### Diagnosis loop

```text
reproduce  ──>  isolate  ──>  classify cause  ──>  fix root cause  ──>  stability run  ──>  CI-equivalent run
```

- **Reproduce.** Repeat execution, the failing shard's worker count, the CI browser version, or the
  same seed. A flake that cannot be reproduced at all is `UNKNOWN`, not `FLAKY_TEST`.
- **Isolate.** Run the test alone, then in its suite, then in parallel. Where it starts failing
  names the class: alone-only is timing or data; suite-only is order or shared state; parallel-only
  is isolation.
- **Classify.** One cause from the list above, with the evidence that picked it.
- **Fix the cause.** Wait on the observable condition, seed the data, scope the fixture, isolate
  the identity, stabilise the selector. Not: raise the timeout everywhere and hope.
- **Stability run.** Repeat execution — 20 runs is the default target where tooling supports it.
  Report the actual count and the actual pass rate.
- **CI-equivalent run.** The local pass rate is not the CI pass rate. Say which one you measured.

### Retries and quarantine

Retries hide the signal that would have found the defect. A product race condition that CI retries
away is a production incident waiting for a customer to find it. Use retries only as a declared,
visible policy, never as a fix for one test.

Quarantine is temporary containment, not a resolution. Every quarantined test carries:

```yaml
quarantine:
  test: "<identifier>"
  reason: "<the diagnosis so far, not 'flaky'>"
  owner: "<a named human>"
  follow_up: "<issue link>"
  visible_in: "<where CI or the report shows it is quarantined>"
  removal_condition: "<what must be true to un-quarantine>"
  quarantined_at: "<date>"
```

A quarantine with no owner, no follow-up, or no removal condition is a deletion with extra steps.
Silent quarantine — skipping a test without any of this — is forbidden.
