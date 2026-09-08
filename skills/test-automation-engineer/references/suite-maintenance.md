# Suite Maintenance And Test Environments

Most automation work is not new tests. It is keeping an existing suite honest while the product
underneath it changes. This is the reference for repairing a suite without quietly deleting the
confidence it was providing, and for the data and environments that make repair possible.

## The maintenance question

Before changing any existing test, answer it:

> What behaviour would stop being protected if this test were deleted, and does the change I am
> about to make keep protecting it?

A repair that keeps the test green but stops protecting that behaviour is worse than deleting the
test, because the suite now reports confidence it does not have.

## Repair sequence

1. **Read the failures.** All of them, grouped, per
   [failure triage](failure-triage.md). Do not start editing while the class is `UNKNOWN`.
2. **Read the change that broke them.** The product diff, the component that was refactored, the
   contract that moved. Maintenance without reading the trigger is guesswork.
3. **Establish what each affected test protects.** From its name, its assertions, its ticket
   reference, or its history. Write it down before touching it.
4. **Repair at the right layer.** A DOM restructure that broke thirty tests is usually one page
   object or one selector helper, not thirty edits.
5. **Remove obsolete assumptions.** Assertions about behaviour that was deliberately removed
   should go, with the removal stated — not be weakened until they pass.
6. **Find duplicates and dead tests.** Maintenance is the cheapest moment to notice that three
   tests assert the same thing at three levels, or that a test covers a removed feature.
7. **Preserve traceability.** If a test carried a ticket, a defect id, or a scenario reference,
   the repaired test still carries it.
8. **Run the affected suite plus a proportionate regression scope.** The tests you touched, their
   suite, and the level above where the change could reach.
9. **Verify with the CI-equivalent command** when it is feasible. State plainly when it is not.

## Repairs that are actually damage

Each of these makes a suite green while removing the reason it existed. Most have a narrow
legitimate case, and every use of one needs a stated, specific justification recorded next to it —
"the suite was red" is not one. Two have no legitimate case at all and are marked `never`.

| Repair | Why it is damage | The narrow legitimate case |
| --- | --- | --- |
| Raise every timeout | Converts a product latency regression into a slower green build | One operation whose measured p95 genuinely grew for an accepted reason |
| `force: true` on interactions | Bypasses the overlay, disabled state, or covering element the user would hit | A known third-party overlay outside the product's control, named in a comment |
| Catch and swallow failures | The test can no longer fail, so it is no longer a test | `never` in an assertion path |
| Delete or weaken assertions | Removes the coverage without removing the runtime | The assertion was verifying implementation trivia, and you say which |
| Blanket-update snapshots | Approves every unreviewed change, including regressions | A reviewed, intentional visual change, updated with the diff read |
| Add retries until green | Hides a race that will reach production | A declared suite-wide policy for a known-unstable dependency, not per test |
| `sleep(5000)` | Makes the test slower and still racy | `never` — wait on the observable condition instead |
| Mark as skipped | Silent coverage loss | Only as quarantine with the full contract in [failure triage](failure-triage.md) |

## Test data

Automation is only as deterministic as the data under it. Know which kind you are using; the
guarantees differ.

| Kind | Guarantee | Use when |
| --- | --- | --- |
| Ephemeral generated | Created and destroyed by the test itself | The default for anything the test can create |
| Fixtures | Deterministic, version-controlled, shared shape | Stable reference data the test does not mutate |
| Seeded environment | Deterministic at seed time, drifts afterwards | Data too expensive to create per test |
| Shared QA data | No isolation guarantee at all | Last resort, and only for read-only assertions |
| Sandbox external service | Provider-controlled, may reset without notice | Contract and integration checks against a real API |
| Mocks and stubs | Fully deterministic, proves nothing about the real dependency | Unit and component level, or simulating failure modes |
| Production-like isolated | Realistic and safe | Performance and data-shape sensitive checks |

Requirements that hold regardless of kind:

- **Deterministic setup.** The test creates or asserts the precondition; it never assumes it.
- **Cleanup ownership is named.** Either the test cleans up what it created, or the environment
  does on a stated schedule. "Somebody will notice" is not ownership.
- **Parallel-safe identities.** Unique users, tenants, records, and files per worker. Two workers
  sharing one account is a flake generator.
- **Idempotency where the shape allows it.** A test that only passes on a clean database will fail
  the second time someone runs it locally.
- **Minimal privileges.** A test account gets exactly the permissions the scenario needs.
- **No production access, and no production credentials.** Not read-only, not "just this once".
  See the [destructive-action safety policy](../../../docs/destructive-action-safety.md).
- **No dependence on mutable shared data** unless it is genuinely unavoidable, and then it is
  written down as a known instability with a plan to remove it.

## Environments and access

Automated tests that need an authenticated external resource resolve it through the generic
access resolver rather than assuming any particular file:

```bash
agent-skills access resolve --service <name> --resource <uri> \
  --require <field,field> --secret <field>
```

The resolver walks authenticated tooling first, then explicit process environment, then
project-local sources, then bound identities — see
[access-resolution.md](../../../docs/access-resolution.md). Three rules follow from it:

- **Never ask for a secret value in conversation**, and never paste one into a test, a fixture, a
  log, or an artifact. The resolver reports what is missing and how to supply it safely.
- **A credential found in repository files or CI logs is a `blocker`**, not a way to make a test
  pass. Follow the
  [discovered-credential protocol](../../../docs/destructive-action-safety.md#discovered-credential-protocol).
- **A test pointed at production, or at shared data whose loss would matter, stops.** Report what
  it would have done and what an isolated target would need. The safety floor is not waivable by
  the person asking.
