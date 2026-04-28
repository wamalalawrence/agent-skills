# v0.17.0 Eval Runs - Summary

This is the maintainer eval-run review for release `v0.17.0`. It scores
the new requirement-understanding gate that every relevant skill runs
before implementation, review, testing, or automation.

Category: maintainer-authored (illustrative).

## Scope of this release

- New shared `docs/requirement-understanding.md` workflow (twelve
  steps, three confidence-to-action rules, twelve-field output block).
- New `docs/requirement-understanding-scorecard.md` (eleven 0-3
  criteria, two release-blocking).
- New `docs/examples/requirement-understanding.md` (six worked
  examples spanning clear bug, premature implementation, ambiguous
  ticket, conflicting AC, bug vs feature, security-sensitive request).
- Five new evals under `evals/requirement-understanding-*.md`.
- New `Requirement Understanding Gate` step in the Required Workflow
  of `software-engineer`, `issue-investigator`, `code-reviewer`,
  `product-owner`, `manual-tester`, and `test-automation-engineer`,
  each with skill-tailored binding rules and a guardrail forbidding
  skipping the gate.
- `issue-investigator` now tracks dual confidence (root-cause +
  requirement-understanding); recommendations may not exceed the
  lower of the two.
- No new skills, no skill renames, no new required env vars, no
  `.env.example` change.

## Scoring summary

- Cross-skill consistency of the gate: 5/5. The same twelve-field
  block, the same `unknown` / `low` / `medium` / `high` rules, and
  the same readiness vocabulary are reused by every relevant skill,
  with skill-specific guardrails layered on top rather than replacing
  the shared rules.
- Resistance to premature implementation: 5/5. The binding rules are
  written so the agent must refuse to implement, refuse to produce
  Jira-ready output, refuse to assert pass/fail on tests, refuse a
  bare `PASS` review, and refuse to automate when understanding
  confidence is `unknown` or `low`. The starter prompts explicitly
  warn that "just do it" framing does not waive the gate.
- Disconfirming-checks discipline: 4/5. Step 10 of the workflow forces
  the agent to look for evidence that contradicts its initial
  interpretation. The scorecard separately rewards this. The risk
  remaining is that the agent treats disconfirmation as a checkbox
  rather than a search; reviewer judgement still matters.
- Honest about gate limits: 5/5. The workflow states that the gate
  cannot waive itself by user prompt, that the first plausible
  interpretation is not high confidence, and that the gate is not a
  substitute for the rest of each skill's workflow.
- Surgical-edit discipline: 4/5. No new skills, no renames, no new
  env vars. The validator's `REQUIRED_FILES` list grew by ten
  entries; `CHANGELOG` and `README` were touched. The cost is
  proportional to the cross-skill scope of the change.
- Public-good portability: 5/5. The workflow is vocabulary-only; no
  vendor products, no private rules, no internal jargon.

## Reviewer self-rebuttal

- **A gate that ends in `medium` is the most dangerous state.** True.
  `medium` allows the agent to plan, draft, and run read-only
  checks, but every load-bearing assumption must stay visible in
  the output and the readiness decision must reflect the assumption.
  The scorecard penalises hidden assumptions explicitly. The risk
  is mitigated, not eliminated.
- **The agent can score itself `high` to avoid clarification work.**
  True. The workflow states that "the first plausible interpretation
  is not high confidence" and that high requires the
  candidate-interpretation list to have been resolved to one. The
  evals (`ambiguous-ticket`, `conflicting-criteria`,
  `bug-vs-feature`, `wrong-root-cause-trap`,
  `security-sensitive-request`) exist to catch this regression in
  manual review.
- **Dual confidence in `issue-investigator` is over-engineering.**
  Considered and rejected. The `wrong-root-cause-trap` eval shows
  the failure mode where the agent is highly confident in the wrong
  cause because it never considered the possibility that the
  reported symptom and the requirement disagree. Tracking the two
  axes independently and capping the recommendation at the lower of
  the two is the smallest available correction.

## Follow-ups recorded for future releases

- Add a sixth eval covering the case where the requirement is clear
  but the existing system disagrees with it (legacy expected
  behavior vs newly stated AC).
- Consider promoting `Resistance to premature implementation` and
  `Readiness decision correctness` from release-blocking-on-zero-or-one
  to release-blocking-on-zero-only once a few releases of data exist.
- Investigate emitting the `Requirement Understanding` block in
  machine-readable form (YAML) so downstream skills can verify the
  upstream gate without re-deriving it.
