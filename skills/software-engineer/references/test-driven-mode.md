# Test-Driven Mode

An opt-in way to run `software-engineer` Phase 2: one behaviour at a time, with a written prediction
before every test run. It changes how Phase 2 produces code and tests. Every other phase, gate, and
review in [`SKILL.md`](../SKILL.md) stays as it is.

## When it applies and what it costs

Enter this mode only when the user, or the brief that dispatched you, explicitly asks for TDD,
test-first, or red-green-refactor work. Nothing else enters it: not the execution profile
(`RIGOROUS` included), not the size or risk of the change, not your own view that it would help.
Without that request, Phase 2 runs as `SKILL.md` describes it.

The reason is cost. Published measurements of a full predictive loop like this one put it at
roughly ten times the tokens of plain, unstructured test-first work. What that buys is real —
noticeably stronger tests and smaller, simpler functions — but the trade belongs to the user.

## 1. Test list

Build the whole list before writing any production code.

- Derive it from the acceptance criteria and their literal examples (`product-owner` step 5):
  one example, one test. A value nobody supplied is an open question, not something to assume.
- Add every test to the suite **inactive**, using the project's own skip, pending, or todo
  mechanism. Do not invent one.
- Order the list from simple to complex: the degenerate case, then each single rule, then
  modifiers, then combinations, then multi-step scenarios.
- Run the [completeness counterfactual](./developer-testing.md#completeness-the-counterfactual-check)
  over the list and add the discriminating cases it turns up.
- Predict that the suite stays green with the whole list inactive, run it, and confirm.

Show the list and wait for the user **only** when requirement-understanding confidence is below
`high`. At `high`, carry on; the list is in the evidence pack for anyone who wants to read it.

## 2. One cycle per behaviour

Each cycle takes the next inactive test from the list to green, then tidies up.

**Red.**

1. Activate exactly one test.
2. Write a one-line prediction: the outcome, the failure category (assertion, missing symbol,
   exception), and the message or value you expect to see.
3. Run the narrowest command that executes that test.
4. It is red only when it fails for the predicted behavioural reason. A failure to load or compile
   is not red: add the minimum scaffold that lets the test run, predict again, and rerun.
5. If it passes on activation, record `already-passing` and move on. Do not touch the test or the
   code to make it fail first.

**Green.** Change production code as little as you can while still turning this one test green.
Predict the result, run the focused test, and confirm.

**Refactor.** With everything green, improve the code under the Four Rules of Simple Design,
highest priority first: the tests pass; the code states its intent; each piece of knowledge lives
in one place; nothing remains that the first three do not need. Take names from the project's
domain glossary when there is one. Refactor in single steps, running the smallest check that
covers each step before the next. Undo a step that does not leave the intent clearer than before.

The refactor step is yours. Do not hand it to a separate refactoring agent.

## 3. When a prediction is wrong

A mismatch between prediction and outcome means your model of the code is wrong somewhere. Stop
adding behaviour until it is explained.

- Keep both the prediction and the actual output, verbatim.
- Explain the gap with the smallest deterministic check available: one assertion, one printed
  value, one focused test.
- Never change production behaviour to make a failure you do not understand disappear.
- If two such checks leave it unexplained, stop and report `needs-user` with both outcomes and what
  the checks showed. The limit is deliberate: a third guess is where a loop starts to drift.

This is one of exactly two places the mode pauses; the other is the test list below `high`
confidence. Everything else proceeds without asking, as the auto-iterate rule in
[2.5](../SKILL.md#25-inner-loop-code-review-call-code-reviewer) expects.

## 4. Suite cadence

Run the full suite at the end of every cycle when it finishes in under about a minute. When it is
slower, run it at least every third cycle. Always run it before Phase 3.

## 5. How it fits the rest of the workflow

- **Bug fixes.** [Gate 1.5](../SKILL.md#15-reproduce-before-fix-gate-bug-fixes-only) still comes
  first. Its regression test is item one on the list, and its RED — with the prediction — is
  recorded as `checks.regression_red` exactly as 1.5 requires.
- **Reviews.** The inner-loop review (2.5) and the outer-loop review (3.5) each run once, after
  the last cycle, never per cycle.
- **Evidence.** The list and one line per cycle go to the optional `tdd` block of the
  [evidence pack](./evidence-pack.md), not into chat. The reviewer checks the list against the
  acceptance examples for omissions and judges the resulting tests and design, not the order of
  work.
- **Everything else** — Phase 3 gates, the Definition of Done, mutation testing at `RIGOROUS` —
  applies unchanged.
