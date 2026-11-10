# Developer Testing Eval: Completeness Over A Catalogue Specification

A specification shaped like a catalogue: a few uniform rules and one exception. The failure this
eval punishes is a suite that stays green while the exception, or a rule's reach, is wrong — and,
on the other side, a suite that enumerates every tier-by-operation cell when the specification
states rules, not cells.

## Skill Under Test

`software-engineer`

## Input Context

Implement storage pricing for four tiers — `free`, `basic`, `pro`, `enterprise` — and three
operations — `upload`, `download`, `delete`. The specification states these rules, and nothing
else:

1. The `free` tier pays nothing for any operation.
2. `delete` is free on every tier.
3. `download` costs 0.01 per GB on every paid tier.
4. `upload` costs 0.02 per GB on every paid tier, except `enterprise`, which pays 0.015 per GB.
5. Every price is rounded half-up to the cent per request.

The request: implement the pricing function with tests. No mutation-testing tool is configured;
the profile is `STANDARD`.

## Expected Behavior

- Names the dimensions the rules vary along independently — tier, operation, and rounding —
  before writing tests.
- Applies the completeness counterfactual to each stated entry: would any test fail if this rule
  alone were wrong and the others right?
- Rules 1, 2, and 3 are uniform, so one representative test each is enough: a `free` operation
  costs 0, a `delete` on a paid tier costs 0, a `download` on a paid tier costs 0.01 per GB.
- Rule 4 has an exception, so the cells can drift independently: one test for `enterprise`
  upload at 0.015, and one for a non-`enterprise` paid tier at 0.02, which fails if the exception
  leaks into the general rate or the general rate replaces the exception.
- Rule 5 gets a case whose expected value differs between half-up and the alternatives (for
  example an `enterprise` upload of 1 GB, 0.015, which rounds to 0.02 half-up and to 0.01 under
  half-even or truncation).
- Ends with roughly one test per independently drifting entry: six or seven, not twelve.

## Must Not Do

- Must not generate the full tier-by-operation cross product as its completeness argument.
- Must not leave the `enterprise` upload rate covered only by a test that would also pass at 0.02.
- Must not cover rule 4 with an `enterprise` test alone, leaving the general rate untested.
- Must not enter a test-driven mode or produce a test-list ceremony; nobody asked for one.

## Pass/Fail Checklist

- [ ] The independent dimensions are named.
- [ ] One representative test for each uniform rule (1, 2, 3).
- [ ] Rule 4: a discriminating `enterprise` upload test and a general-rate upload test.
- [ ] Rule 5: a rounding case that distinguishes half-up from other rounding.
- [ ] No mechanical cross product.
