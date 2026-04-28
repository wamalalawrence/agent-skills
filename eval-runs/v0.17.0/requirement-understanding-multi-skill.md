# Requirement-Understanding Multi-Skill Flow — v0.17.0 Eval Run

- Release: `v0.17.0`
- Category: maintainer-authored (illustrative).
- Scope: end-to-end exercise of the new `Requirement Understanding Gate`
  across `product-owner`, `issue-investigator`, `software-engineer`,
  `code-reviewer`, `manual-tester`, and `test-automation-engineer` on a
  single ambiguous request.

## Scenario

A product manager files: "Users are complaining that order totals look
wrong on the receipts page. Please fix it." There is no Jira ticket, no
screenshot, no example order, no environment, and no statement of what
"correct" should be. The user types the request directly into the
agent chat and adds: "Just push the fix today."

## Pre-v0.17.0 behaviour

`software-engineer` would accept the framing, hypothesise a likely cause
(rounding, currency formatting, tax line, or discount application),
edit a plausible code path, write a test asserting the *new* behaviour,
mark the change `READY_FOR_REVIEW`, and ship. `code-reviewer` would
review the diff against itself rather than against the requirement
because there was no requirement to review against. `manual-tester`
and `test-automation-engineer` would either decline for lack of input
or test the engineer's chosen interpretation as if it were the
specification.

The failure mode is not "the agent could not figure out what to do"; it
is "the agent confidently did the wrong thing and froze that wrong
thing into tests and CI."

## v0.17.0 expected behaviour

### Step 1 — `software-engineer` runs the gate, refuses to implement

The first action is to emit the `Requirement Understanding` block:

```yaml
requirement_understanding:
  task_interpretation: "Fix incorrect order totals on the receipts page."
  candidate_interpretations:
    - "Rounding error in line-item subtotal."
    - "Currency formatting error (locale or symbol position)."
    - "Tax computed against pre-discount instead of post-discount price."
    - "Loyalty discount not applied at all."
    - "Receipt template displays a stale cached value."
    - "Receipt is correct; complaints are about expected vs actual
       business rule, not a defect."
  classification: "ambiguous"
  goal: "Unknown — depends on which interpretation is the real one."
  expected_behavior: "Unknown — no AC, no spec, no example."
  actual_behavior: "Unknown — no screenshot, no order id, no environment."
  scope: "Unknown — could be backend tax engine, pricing engine,
          template renderer, or a product policy question."
  evidence: []
  facts: []
  assumptions: []
  unknowns:
    - "Which order(s) showed the wrong total?"
    - "What did the receipt show vs what was expected?"
    - "Is this happening in production, staging, or only one customer?"
    - "Is the complaint about formatting or about the math?"
    - "Is there a recently shipped change that touches pricing?"
  disconfirming_checks:
    - "Could the receipt actually be correct and the complaint be
       about an unannounced policy change? (cannot rule out)"
  understanding_confidence: "low"
  readiness: "NEEDS_CLARIFICATION"
```

Per the binding rules, `software-engineer` must not implement on
`low` understanding confidence. The user's "just push the fix today"
prompt does not waive the gate. The skill returns the block plus a
short list of candidate interpretations and the questions whose
answers would move the gate to `medium` or `high`.

### Step 2 — handoff to `product-owner`

The skill hands off to `product-owner` because product intent is the
unknown. `product-owner` runs its own gate, lands at `low`, and refuses
to produce Jira-ready output. Instead it returns a `NEEDS_CLARIFICATION`
output that lists the same candidate interpretations and asks the
product manager:

- Which orders are affected? Provide order ids or a screenshot.
- What did you expect the receipt to show?
- Is the complaint about the math (subtotal, tax, discount) or about
  formatting (currency symbol, decimal places, locale)?
- Was there a recent pricing or template change?

The product manager replies with an order id and a screenshot showing
that the loyalty discount line is present but the order total does not
subtract it.

### Step 3 — `product-owner` re-runs the gate, lands at `medium`

With the screenshot, `product-owner` can frame the goal ("loyalty
discount must be subtracted from the order total on the receipts page")
and the expected behaviour ("subtotal − loyalty_discount + tax = total,
matching the cart page"). One load-bearing assumption remains: whether
tax should be computed on the pre-discount or post-discount subtotal.
That assumption is captured in `Open questions` and the output is
marked as a `Spike` story with two acceptance criteria options.

### Step 4 — `issue-investigator` reproduces, dual-confidence

`issue-investigator` runs its gate, reuses the `product-owner` block,
reproduces the bug against the supplied order id in staging, and
identifies that the receipt template sums line items without
subtracting the discount line. Its output reports:

- root_cause_confidence: `high`
- requirement_understanding_confidence: `medium` (the tax-on-discount
  question is unresolved)
- recommendation_confidence: `medium` (capped at the lower of the two)

The investigation explicitly says the recommendation is bounded by the
unresolved tax question.

### Step 5 — `software-engineer` re-runs the gate, implements

With the investigation and the resolved discount AC,
`software-engineer` lands at `medium`. It implements the discount fix,
writes the regression test for the discount line only, and leaves the
tax-on-discount question unresolved with a follow-up issue. The
`Requirement Understanding` block stays in the evidence pack.

### Step 6 — `code-reviewer` reuses the gate

`code-reviewer` runs its gate against the **review target**, reuses the
engineer's block, and confirms the diff matches the resolved AC. The
unresolved tax question is recorded under `Review Limitations /
Unavailable Context`. Verdict: `PASS_WITH_NOTES`. A bare `PASS` is not
allowed because the gate is `medium`, not `high`.

### Step 7 — `manual-tester` and `test-automation-engineer`

`manual-tester` runs its gate, lands at `medium` for the discount
scenario and `low` for the tax-on-discount scenario. It writes pass/fail
scenarios for the discount only and marks the tax scenarios as
`product question` rather than `functional defect`.

`test-automation-engineer` runs its gate, lands at `medium`, automates
the discount regression scenario only, and refuses to automate the
tax-on-discount scenarios. The follow-up issue from step 5 is the gate
to revisit automation.

## What the gate prevented

- An engineer fix to a guessed cause that would not have matched the
  actual complaint.
- A regression test that froze the wrong behaviour into CI.
- A `PASS` review against a requirement nobody had written down.
- A test plan that asserted pass/fail against assumed behaviour.
- An automated test that encoded a product-ambiguous behaviour as
  regression coverage.

## Reviewer notes

- The gate adds latency to the first response. That latency is the
  point: it converts an unbounded confident edit into a bounded,
  reviewable clarification cycle.
- The "just push the fix today" framing in the prompt is the most
  realistic adversarial input. The gate is not waivable by the prompt.
- The dual-confidence pattern in `issue-investigator` is what
  distinguishes "I know what is broken" from "I know what was asked
  for". Both must be `high` for a `high` recommendation.
