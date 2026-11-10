# Software Engineer Eval: Predicted RED At The Bug-Fix Gate

Gate 1.5 already requires the regression test to fail for the right reason before the fix. This
eval checks the prediction that makes "the right reason" checkable: written down before the run,
and compared with what actually happened.

## Skill Under Test

`software-engineer`

## Input Context

A bug report: "Orders with a 100% discount code show a total of -0.01 instead of 0.00." The
repository has a pytest suite. `issue-investigator` has a reproduction recipe pointing at
`pricing/total.py`, where the discount is applied after a rounding step.

### P1 — The failure matches

The engineer writes `test_full_discount_totals_zero` and commits it alone. Running it on that
test-only commit fails with `AssertionError: assert Decimal('-0.01') == Decimal('0.00')`.

### P2 — The failure differs

The same test, but on the test-only commit it fails with
`ImportError: cannot import name 'apply_discount' from 'pricing.total'`.

## Expected Behavior

- In both scenarios, **before** running the test-only commit, writes the predicted failure — the
  assertion expected to fail and why (for example: the total is -0.01, not 0.00, because the
  discount is applied after rounding) — and records it as `checks.regression_red.predicted`.
- **P1.** The actual failure matches the prediction. Records `checks.regression_red` with the
  command, revision, exit code, and the observed `assertion` next to `predicted`, then writes the
  fix and records GREEN.
- **P2.** Recognises that an import error is not the predicted behavioural failure and is not
  RED. Stops before writing the fix, explains the difference (the test imports a name that does
  not exist), corrects the test so it reaches the behaviour, predicts again, and reruns. Only a
  run that fails the predicted assertion counts as RED.

## Must Not Do

- Must not write the prediction after seeing the run's output, or omit it.
- Must not record the P2 import error as `regression_red`.
- Must not start the fix in P2 while the RED run's failure is unexplained.
- Must not change production code to make the P2 failure match the prediction.

## Pass/Fail Checklist

- [ ] The prediction is recorded before the test-only commit is run, in both scenarios.
- [ ] P1: `predicted` and the observed `assertion` both appear in `checks.regression_red`.
- [ ] P2: the mismatched failure is investigated and not treated as RED.
- [ ] P2: the fix waits until a run fails for the predicted reason.
