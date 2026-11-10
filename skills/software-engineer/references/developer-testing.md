# Developer Testing

How to decide what a test should protect, where its boundary sits, which collaborators stay real,
which become doubles, and whether to verify state or interaction. This is the reference for the
tests an engineer writes alongside the code they are changing — unit tests, focused integration
tests, regression tests. Broader suite strategy, API/UI automation, and CI suite ownership belong
to [`test-automation-engineer`](../../test-automation-engineer/SKILL.md).

The governing question is not *which class am I testing and what do I mock around it*. It is:

```text
What is the smallest meaningful behavioural unit worth protecting,
and what is the cheapest reliable test that gives useful confidence in it?
```

## The six decisions

Proportional to the change. A one-line fix answers these in a sentence; a new payment flow deserves
a paragraph. Do not write a test-plan ceremony for a typo.

1. **Behaviour to protect.** What observable thing must keep working? If you cannot name it without
   naming a method, you are describing structure, not behaviour.
2. **Test level.** The lowest level that can reliably detect the regression.
3. **Unit boundary.** Which collaborating pieces form the unit under test.
4. **Real vs doubled collaborators.** Default real; double what is awkward.
5. **Double type.** The least powerful one that does the job.
6. **Verification style.** Output/state by default; interaction when the interaction *is* the
   behaviour.

Then one more, always: **is the test hard to write because the production design is wrong?**

## Choosing the unit

A unit is a behavioural boundary, not automatically a class. `one class = one unit` is a convention
that survived because it is easy to mechanise, not because it protects behaviour well. It produces
a test per class whose only content is that the class calls its neighbours in a particular order —
which is exactly the property you want to be free to change.

A unit test may exercise any of these, and all of them are legitimate:

- one pure function;
- one class;
- several collaborating domain objects;
- a small module;
- an application service or use case plus its cheap in-process collaborators.

What makes it a *unit* test is not the count of classes inside it. It is that the test stays fast,
deterministic, focused on one behaviour, isolated from external systems, readable, and informative
when it fails. A test spanning four domain objects that runs in two milliseconds and names one
business rule is a better unit test than four class-level tests that assert delegation.

Widen the boundary when the collaborating objects only make sense together — a policy, its rules,
and the value objects it reasons about. Narrow it when the behaviour is genuinely local, when the
failure message would otherwise be ambiguous, or when the wider test needs setup nobody can read.

## Real collaborators vs test doubles

**Default to the real collaborator.** Replace it when there is a reason.

Keep it real when it is in-process, deterministic, cheap to construct, fast, owned by this
codebase, and free of problematic shared state. Validators, calculators, mappers, domain policies,
value objects, formatters, and small pure services almost always qualify. So does a lightweight
deterministic fake for a repository the codebase owns.

Introduce a double when the collaborator is one of:

- an external process, network call, or third-party API;
- slow, expensive, or rate-limited;
- non-deterministic — clock, randomness, UUID generation, ambient environment;
- stateful across tests in a way you cannot reset;
- awkward to construct honestly (a large graph with no bearing on the behaviour);
- a failure mode you cannot induce safely — timeout, partial write, provider outage, 500;
- the thing whose invocation you actually need to assert.

Isolation itself is a legitimate reason: doubling a collaborator so a failure names one component
rather than five is a real benefit, and outside-in design sometimes wants the double to exist before
the collaborator does. It is a reason to be stated, not a default to be assumed.

**Do not mechanically double every constructor dependency.** "Injected" is not the same as
"external". A test that needs ten doubles is telling you something — usually that the unit boundary
is wrong, or that the class under test is doing too much. That is a prompt to look at the design,
not a threshold that fails a review. There is no correct maximum number of doubles.

## Types of test doubles

Choose the least powerful double that answers the question. Power here means how much of the test's
meaning lives in the double's configuration rather than in the assertion.

| Double | Use it when | What it gives you |
| --- | --- | --- |
| Dummy | An argument must exist but is never used | Nothing; it fills a parameter list |
| Stub | The unit needs controlled inputs or canned responses | Fixed answers, no assertions on calls |
| Fake | A working substitute is cheaper than the real thing | Real behaviour, shortcut implementation (in-memory repository, hand-rolled clock) |
| Spy | You need the real behaviour *and* a record of calls | Behaviour plus an inspectable call log |
| Mock | The calls themselves are the contract | Pre-set expectations, verified as part of the test |

The exact vocabulary does not need to appear in the code — most libraries blur these anyway, and
the repository's existing idiom wins. What matters is the choice. Reaching for a mock with
verification when a stub and a returned-value assertion would say the same thing adds coupling for
no confidence.

A hand-written fake often beats a pile of per-test stubbing. An in-memory implementation of an owned
repository interface, written once, replaces the same five `when(...).thenReturn(...)` lines
repeated across thirty tests, and it fails loudly when the interface changes rather than silently
returning `null`.

## State and output verification vs interaction verification

Ask first: **can I verify this behaviour through observable output or state?** If yes, prefer that.

Observable means any of:

- the returned value;
- changed domain state on the object or aggregate;
- the result persisted through a fake the codebase owns;
- an emitted domain event;
- the error or result contract on the failure path.

Interaction verification — asserting that a collaborator was called, how, and how often — is right
when the interaction *is* the behaviour under test. Genuine cases include:

- the confirmation email is sent exactly once;
- no transaction is attempted when validation fails;
- the outbound payment request carries the idempotency key and the agreed protocol shape;
- a cache miss reaches the origin and a hit does not;
- the audit or security side effect is recorded;
- the command is published to the broker;
- a retried request suppresses the second external call.

In each of those the call is what the caller promised, and there is no output that proves it.
That is the test for whether interaction verification is earned: *if the call did not happen, would
anything else in the system observably differ?* If yes, assert the observable thing. If no, the
call is the observable thing.

**Mocks are not banned. `verify(...)` is not banned.** What is required is a reason, and the reason
should be legible from the test's name and assertions.

## Boundaries and owned adapters

Test doubles earn their place at boundaries: HTTP and network calls, external SaaS APIs, email and
SMS, the filesystem, the clock, randomness, message brokers, cloud SDKs, third-party clients,
expensive services, and failure conditions that cannot be induced safely.

But distinguish *our abstraction* from *a third-party library's internal API*. Prefer the shape:

```text
domain / application code
        |
        v
owned port or interface        <- developer tests double this
        |
        v
adapter                        <- integration or contract tests cover this
        |
        v
third-party SDK / external API
```

Business-logic tests double the owned port. The adapter gets its own integration or contract
coverage against the real API, a recorded interaction, or a representative substitute such as a
local mock server or provider sandbox.

The failure this prevents:

```text
Do not prove that our mock of the vendor behaves like the vendor.
Test the business logic against an owned boundary, and test the adapter separately.
```

A test that stubs three levels of an AWS, Stripe, or HTTP-client builder chain asserts the shape of
someone else's fluent API. It passes when the SDK changes semantics under it, and it breaks when the
SDK changes syntax that never mattered. Both directions are wrong. The same reasoning applies to
payment providers, queues, HTTP clients, and databases.

When no owned port exists yet, say so and size the work honestly. Introducing one is often a small
and worthwhile refactor; sometimes it is out of scope, and then the correct output is a test at the
level that can actually cover the behaviour plus a named follow-up — not a deep-stubbed unit test
presented as coverage.

## Refactoring resilience

A test should generally survive internal restructuring that preserves the behaviour it protects.
Before finishing a test, ask:

```text
Would this fail if I changed the internal collaboration structure
without changing the behaviour being protected?
```

If yes, decide whether that coupling is intentional. A test that breaks because `A` now calls `C`
directly instead of going through `B`, while the outcome is identical, is overspecified: it has
recorded a design decision as if it were a requirement. A test that breaks because the outbound
payment call stopped carrying the idempotency key is doing its job.

Unnecessary implementation coupling is a maintainability problem, not a correctness one. It shows
up later as a refactor that costs a day of test edits and teaches the team that tests are tax.

## Test smells as design feedback

If writing a focused test needs many doubles, sprawling setup, knowledge of call order, a large
fixture graph, private-method access, static or global manipulation, reflection tricks, or a full
framework bootstrap for trivial logic — do not reach first for more test machinery.

Ask what the production design is saying:

- the class has too many responsibilities;
- dependencies are hidden rather than declared;
- boundaries are in the wrong place;
- orchestration and business rules are mixed in one method;
- an abstraction is missing;
- side effects are uncontrolled;
- coupling is tight enough that nothing can be exercised alone.

Test pain is design feedback. `software-engineer` may propose a small production refactor that
improves both the design and the testability when the task justifies it — extracting a pure function
from an orchestrator, introducing the missing port, passing the clock in. State it in the plan and
keep it proportional. Do not restructure unrelated production architecture to make one test tidier,
and do not block a small fix on an architectural argument.

### Smells worth a second look

None of these is a failing condition on its own. Each is a prompt to check the reasoning:

- nearly every collaborator doubled, including the deterministic ones;
- many `verify(...)` assertions and few assertions about outcomes;
- verification of getters, setters, or internal plumbing;
- double setup longer than the behaviour being tested;
- assertions on call order where no protocol requires it;
- tests that break after a behaviour-preserving refactor;
- doubles returning doubles, or deep stubbing through a chain;
- the same fragile stubbing copied across many test classes;
- a test whose name describes a method rather than an outcome.

## Naming and assertions

A test should read as *given · when · then* without needing literal BDD syntax. The name carries the
context and the expected outcome; the body carries the scenario.

```text
rejectsExpiredPaymentMethod
returnsNoAvailableTripsWhenAllCapacityIsReserved
doesNotPublishSecondCommandForDuplicateRequest
```

rather than:

```text
testCalculate
testMethod1
shouldCallRepository
```

`shouldCallRepository` is only a good name when calling the repository is genuinely the contract —
and then the name should say why it matters, not merely that a call happens.

Assertions should express the domain rule. `assertThat(quote.total()).isEqualTo(EUR("112.50"))` says
what the business promised. `verify(calculator).add(any(), any())` says which arithmetic helper was
in fashion the week the test was written. Follow the repository's assertion library rather than
introducing a second one.

## Choosing the test level

Pick the lowest level that reliably detects the regression you care about — and no lower. Forcing a
serialization, wiring, or persistence defect into a pure unit test produces a test that passes while
the system stays broken.

| The behaviour lives in | Test at |
| --- | --- |
| Pure logic, rules, calculations, validation, state transitions | Unit |
| Several domain objects cooperating on one rule | Unit, with the objects real |
| Mapping, serialization, schema, framework wiring, DI configuration | Integration |
| Persistence, queries, transactions, migrations | Integration against a real engine or an equivalent substitute |
| Messaging, retries, idempotency across a broker | Integration |
| An agreement between a producer and a consumer | Contract |
| A defect that reached production | A regression test at whichever level above reproduces it |

For bug fixes the regression test comes first and must be shown failing against the unfixed
implementation with the test present — that expectation is unchanged, and it applies at whichever
level actually reproduces the defect. See
[evidence discipline](../../../docs/evidence-discipline.md#red-means-the-test-ran-and-failed-for-the-right-reason)
for what counts as RED.

## Coverage

Coverage is evidence about which lines ran. It is not evidence that behaviour is protected.

```text
high line coverage != high confidence
```

A test that executes a branch and asserts nothing meaningful raises the number and protects nothing.
Do not add tests to move a percentage. Prefer meaningful branches, boundary values, error paths, and
invariants over exercising lines.

Where a project sets a coverage gate, meet it honestly — that means real assertions on real
behaviour, not padding — and say so if meeting it required tests you consider low value. A gate is a
floor for negligence, not a definition of quality.

## Completeness: the counterfactual check

A specification shaped like a catalogue — a table, a mapping, rules repeated across variants and
operations — invites a suite that stays green while one entry is wrong. First name the dimensions
the entries vary along independently: operation, variant, kind of input, policy attribute,
state, observable result. Then, for each entry the specification states explicitly, ask: *would
any test go red if this entry alone were wrong and everything around it were right?*

Where the answer is no, add one discriminating test for that cell: a case whose expected value
differs from what the neighbouring rule would produce. Where a single uniform rule governs several
values, one representative test covers them; a cell that can drift on its own needs its own test.
Never generate the full cross product of the dimensions — that adds volume, not discrimination.

## On the two schools

The classical/Detroit style — real collaborators, state verification, units defined by behaviour —
and the mockist/London style — collaborators doubled, interaction verification, outside-in design —
are both coherent, and each buys something real. Classical tests survive refactoring better and
catch integration mistakes between the objects they exercise. Mockist tests localise failures
precisely, and designing against doubles pushes you to name the roles your code depends on before
they exist.

This repository does not adopt either as doctrine. The question at each test is:

```text
Which style gives reliable confidence here with the least unnecessary coupling?
```

In practice that usually means real collaborators and state assertions inside the domain, and
doubles with interaction assertions at the edges where the collaboration is the contract. Neither
answer is owed to a school.

## A worked example

A `SubscriptionRenewalService` charges a card through a payment gateway, applies a loyalty discount,
and records the renewal.

Mock-heavy version — every collaborator doubled, every call verified:

```java
@Test
void testRenew() {
  when(discountPolicy.discountFor(customer)).thenReturn(Percent.of(10));
  when(priceCalculator.apply(BASE, Percent.of(10))).thenReturn(EUR("90.00"));
  when(clock.now()).thenReturn(NOW);
  when(gateway.charge(any())).thenReturn(ChargeResult.ok("ch_1"));

  service.renew(subscription);

  verify(discountPolicy).discountFor(customer);
  verify(priceCalculator).apply(BASE, Percent.of(10));
  verify(gateway).charge(any());
  verify(repository).save(any());
}
```

It passes if the service calls four collaborators. It would also pass if the amount charged were
wrong, if the renewal date were wrong, or if the discount were applied twice: the stubs hand back
the arithmetic, the only value assertion is `any()`, and the returned result is discarded. Move the
discount lookup inside the calculator and it fails, though nothing observable changed.

Behaviour-oriented version — the deterministic domain pieces stay real, the external boundary is
doubled, and the one interaction that *is* the contract is asserted:

```java
@Test
void chargesDiscountedAmountAndRecordsRenewal() {
  var gateway = new RecordingPaymentGateway(ChargeResult.ok("ch_1"));
  var service = new SubscriptionRenewalService(
      new LoyaltyDiscountPolicy(), new PriceCalculator(),
      new InMemorySubscriptionRepository(), gateway, fixedClockAt(NOW));

  var result = service.renew(goldCustomerSubscription(BASE));

  assertThat(result.chargedAmount()).isEqualTo(EUR("90.00"));
  assertThat(result.renewedUntil()).isEqualTo(NOW.plusMonths(1));
  assertThat(gateway.charges()).singleElement()
      .returns(EUR("90.00"), Charge::amount);
}
```

`LoyaltyDiscountPolicy` and `PriceCalculator` are real, so the discount arithmetic is actually
tested rather than restated in a stub. The repository is an owned in-memory fake. The gateway — the
external boundary — is doubled, and the assertion that exactly one charge left the system for the
right amount is interaction verification that earns its place: no output proves money moved.

Restructuring how the service calls its internals does not break this test. Charging the wrong
amount, charging twice, or renewing to the wrong date does.
