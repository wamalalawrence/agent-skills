# Developer Testing Eval: Third-Party Boundaries And Test Levels

Two scenarios about where a test double belongs and which level a test has to sit at to catch the
defect it exists for. Both punish the cheap answer: stubbing the vendor because it is right there,
and writing a unit test because unit tests are fast.

## Skill Under Test

`software-engineer`

## Input Context

### C — Third-party SDK stubbed inside business logic

`InvoiceArchiver` decides which invoices are archivable and writes them to object storage. It takes
the cloud provider's SDK client directly and calls it through a fluent builder. The existing test
stubs three levels of that builder:

```java
when(s3Client.putObject(any(PutObjectRequest.class), any(RequestBody.class)))
    .thenReturn(PutObjectResponse.builder().eTag("etag-1").build());
when(s3Client.serviceClientConfiguration()).thenReturn(config);
when(config.region()).thenReturn(Region.EU_WEST_1);
```

The request is: add a rule that credit notes are archived under a different key prefix, with tests.

### I — Integration-level regression

A production defect: an API response omits the `cancelledAt` field for cancelled orders. The cause
is a serializer configuration — a `@JsonInclude(NON_NULL)` on the DTO combined with a mapper that
leaves the field null when the source uses a different type. The domain logic is correct; every
existing unit test on the order aggregate passes, and passed while the bug was live. The request is
to fix it with a regression test.

## Expected Behavior

**C.** Identifies the boundary problem: the business rule (which invoices are archivable, which key
prefix each gets) is entangled with a vendor client, and the stubbed builder chain asserts the shape
of someone else's API. Says plainly what that test cannot catch — the provider changing behaviour
under the stub — and what breaks it for no reason — the provider changing syntax that never
mattered. Recommends an owned port (an archive/storage interface expressed in this codebase's
terms), with the archiving rules tested against it and the adapter covered separately by an
integration or contract test against the real API, a recorded interaction, or a local substitute
such as a provider-compatible test server. Sizes the refactor honestly against the task: if
introducing the port is too large for this change, says so, puts the key-prefix rule wherever it can
actually be tested, and names the follow-up — rather than adding a fourth level of stubbing and
calling it coverage.

**I.** Does not force this into a unit test. Recognises that the defect lives in serialization and
mapping configuration, so the regression test has to serialize — a web-layer or serialization test
that asserts the JSON body for a cancelled order contains `cancelledAt` with the right value. Notes
that the passing aggregate unit tests are exactly the evidence that a lower-level test cannot detect
this. Keeps the reproduce-before-fix expectation: the regression test fails on the parent commit and
passes on the fix. May add a cheap unit test for any pure mapping logic that comes out of the fix,
but not instead of the one that reproduces the defect.

## Must Not Do

- Must not deepen the SDK stubbing in C, or describe a mocked vendor client as adapter coverage.
- Must not claim in C that mocking is wrong in general; the boundary and its ownership are the
  issue, not the presence of a double.
- Must not propose rewriting unrelated storage architecture in C when a bounded change would do.
- Must not satisfy I with a unit test on the mapper alone if that test would pass while the endpoint
  still returns the wrong body, and must not claim coverage as evidence that the defect is fixed.
- Must not skip the failing-first regression test in I.
- Must not hand ordinary developer testing in either scenario to `test-automation-engineer`.

## Pass/Fail Checklist

- [ ] C: names the owned-port/adapter split and what the current stubbing fails to protect.
- [ ] C: the recommended refactor is proportional, with an explicit fallback and follow-up if it is
      out of scope for this change.
- [ ] I: the regression test sits at the level that actually reproduces the defect and is stated to
      fail on the parent commit.
- [ ] I: explains why the existing green unit tests are not counter-evidence.
- [ ] Neither answer resolves the problem by adding stubs or by asserting a coverage percentage.
