# Developer Testing Eval: Unit Boundary And Double Selection

Four scenarios that test whether the engineer chooses a unit boundary and a test double on
engineering grounds rather than by reflex. The grader judges the **decision and its stated reason**,
not whether particular words appear. An answer that reaches the right decision with different
vocabulary passes; an answer that recites the vocabulary and still doubles everything fails.

## Skill Under Test

`software-engineer`

## Input Context

### A — Over-mocked service

`PricingService` computes an order total. Its constructor takes four collaborators, all in this
repository, all pure and deterministic: `TaxRuleSet`, `DiscountPolicy`, `RoundingStrategy`, and
`CurrencyConverter` (which reads a rate table passed into its constructor — no network). The user
supplies a draft test and asks the engineer to finish the change:

```java
@Test
void testTotal() {
  when(taxRuleSet.rateFor(order)).thenReturn(Percent.of(21));
  when(discountPolicy.apply(any(), any())).thenReturn(EUR("80.00"));
  when(roundingStrategy.round(any())).thenReturn(EUR("96.80"));
  when(currencyConverter.toEur(any())).thenReturn(EUR("96.80"));
  assertThat(service.total(order)).isEqualTo(EUR("96.80"));
}
```

### B — Legitimate external boundary

`RefundService` issues a refund through `PaymentGateway`, an interface this repository owns; its
only implementation wraps a third-party provider's HTTP API. The behaviour to protect: a refund for
an already-refunded order must not send a second request to the provider, and the first refund must
send exactly one request carrying the original charge id.

### F — Large fixture graph

A `SettlementCalculator` test needs a `Contract` that requires a `Party`, an `Agreement`, a
`FeeSchedule`, and eleven other objects, most of them irrelevant to the rule being tested. The
existing tests build this graph by hand across roughly 60 lines of setup, duplicated in each test
class. The engineer is adding one new settlement rule.

### H — Unit is not a class

A shipping quote is produced by four small classes cooperating: `ZoneResolver`, `WeightBand`,
`SurchargeRules`, and `QuoteAssembler`. All are pure, in-process, and construct in one line each.
The behaviour to protect is a business rule: an oversize parcel to a remote zone gets the remote
surcharge and the oversize surcharge, and the two do not compound.

## Expected Behavior

**A.** Recognises that all four collaborators are deterministic, cheap, in-process, and owned, so
there is no reason to double them; being constructor dependencies is not a reason. Rebuilds the test
with the real collaborators and asserts the computed total (and at least one interesting boundary
case). Names what the draft test actually proved — that the service called four collaborators, with
the stubs supplying the arithmetic the assertion then checks, so it would pass with the tax rate
applied twice or not at all. May note that if the collaborator set makes the test unwieldy, the
boundary or the class's responsibilities are the thing to look at.

**B.** Doubles `PaymentGateway` — an external process boundary behind an owned port — and does not
call the provider. Accepts interaction verification here and says why: "no second request is sent"
has no observable output to assert, and the outbound call carrying the charge id is the contract.
Does not additionally verify unrelated internal calls. May use a hand-written recording fake instead
of a mocking framework; either is correct as long as the assertion is about the requests that left
the system.

**C (control, applies to all four).** Does not state or imply a rule that external dependencies are
always mocked, that collaborators are never mocked, that a test may contain at most N doubles, or
that the change must be written test-first.

**F.** Treats the setup pain as design feedback and considers the options rather than defaulting to
either extreme: a shared test data builder or object mother; narrowing the unit so the rule under
test does not need the whole graph; extracting the rule into something that takes only what it
needs. Does not conclude "never mock" and hand-build 60 more lines, and does not conclude "mock
everything" and assert on calls. Keeps any production refactor proportional to the task — a new
settlement rule does not license restructuring the contract model — and says so if the better fix
is out of scope.

**H.** Lets the four classes form one behavioural unit with all of them real. Writes a test named
for the rule (surcharges apply and do not compound) that asserts the resulting quote. Does not
create four class-level tests asserting delegation, and does not double `ZoneResolver` or
`WeightBand` to "isolate" `QuoteAssembler`.

## Must Not Do

- Must not double a collaborator only because it is injected.
- Must not present interaction assertions in A or H as equivalent confidence to asserting the total.
- Must not refuse interaction verification in B, where the suppressed second call is the behaviour.
- Must not introduce a mock-count threshold, a coverage claim, or a Detroit/London allegiance as the
  justification for any decision.
- Must not call the real payment provider in B, or suggest a sandbox call as the unit test.

## Pass/Fail Checklist

- [ ] A: real collaborators restored, assertion is on the computed total, and the draft test's
      weakness is named concretely.
- [ ] B: owned port doubled, provider not called, and interaction verification justified by the
      behaviour rather than by habit.
- [ ] F: test pain treated as a signal, options weighed, and the chosen fix sized to the task.
- [ ] H: the four classes are exercised together as one unit and the assertion states the business
      rule.
- [ ] No universal mocking rule, double-count threshold, school allegiance, or test-first mandate
      appears in any answer.
