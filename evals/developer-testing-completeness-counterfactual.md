# Developer Testing Eval: Completeness Over A Catalogue Specification

A specification shaped like a table. The failure this eval punishes is a suite that is green while
one cell of the table is wrong — and, on the other side, a suite that enumerates every combination
and still misses the one cell with its own rule.

## Skill Under Test

`software-engineer`

## Input Context

Implement storage pricing. Four tiers — `free`, `basic`, `pro`, `enterprise` — and three
operations — `upload`, `download`, `delete`. The specification:

| Tier | upload, per GB | download, per GB | delete |
| --- | ---: | ---: | --- |
| free | 0.00 | 0.00 | free |
| basic | 0.02 | 0.01 | free |
| pro | 0.02 | 0.01 | free |
| enterprise | 0.015 | 0.01 | free |

Every price is rounded half-up to the cent per request. The request: implement the pricing
function with tests. No mutation-testing tool is configured; the profile is `STANDARD`.

## Expected Behavior

- Names the dimensions the entries can vary along independently — here tier, operation, and the
  rounding rule — before writing tests.
- Applies the completeness counterfactual: for each stated entry, would any test fail if that
  entry alone were wrong? Notices that `basic` and `pro` share every price, so a test on one says
  nothing about the other, and that `enterprise` upload is the only cell with its own rate.
- Adds a discriminating test for each cell that can drift on its own: the `enterprise` upload
  rate, the `free` tier's zero prices, a `basic` and a `pro` case that would fail if either
  tier's row were changed, the uniform download rate, `delete` being free, and a rounding case
  whose expected value differs between half-up and the alternatives.
- Uses one representative test where a single uniform rule governs several values (`delete` is
  free for every tier) rather than one test per tier.
- Keeps the test count proportional: roughly one test per independently drifting cell, not twelve
  price tests plus twelve rounding tests.

## Must Not Do

- Must not generate the full tier-by-operation cross product as its completeness argument.
- Must not test only one of `basic` or `pro` and treat the other as covered.
- Must not leave the `enterprise` upload rate covered only by a test that would pass at 0.02.
- Must not enter a test-driven mode or produce a test-list ceremony; nobody asked for one.

## Pass/Fail Checklist

- [ ] The independent dimensions are named.
- [ ] The `enterprise` upload rate has its own discriminating test.
- [ ] `basic` and `pro` each have a test that fails if that tier's row changes.
- [ ] The rounding rule has a case that distinguishes half-up from other rounding.
- [ ] No mechanical cross product; representative tests where one rule is uniform.
