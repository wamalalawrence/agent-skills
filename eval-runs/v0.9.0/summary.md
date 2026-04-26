# v0.9.0 Eval Runs - Summary

This is the maintainer eval-run review for release `v0.9.0`. It scores each
skill against the [skill quality scorecard](../../docs/skill-quality-scorecard.md)
on the corresponding scenario in [`evals/`](../../evals/), records strengths
and gaps, and lists the follow-up changes (or deliberate non-changes).

> The transcripts in each per-skill file are **illustrative**, authored by the
> maintainer to show the kind of output a competent assistant should produce
> with the listed inputs. They are not raw outputs of any single specific
> model. See [`../README.md`](../README.md).

## Scope

- All four top-level skills: `software-engineer`, `product-owner`,
  `manual-tester`, `test-automation-engineer`.
- Both nested support skills: `issue-investigator`, `code-reviewer`.
- One multi-skill chained flow: bug report -> investigation -> fix -> manual
  retest -> regression automation.

## Per-Skill Results

Scores are `0`-`3` per criterion across the ten scorecard criteria, totalling
out of `30`. See each file for the full per-criterion breakdown.

- [`issue-investigator-bug-root-cause.md`](issue-investigator-bug-root-cause.md):
  total `26/30`. Strong evidence discipline and stopping behavior. Weak on
  proactively listing safe local commands the user could run.
- [`code-reviewer-issue-aware-review.md`](code-reviewer-issue-aware-review.md):
  total `25/30`. Strong issue-aware findings and severity calibration. Weak on
  recording what was unavailable for the review.
- [`software-engineer-bugfix-flow.md`](software-engineer-bugfix-flow.md):
  total `26/30`. Strong context discovery and inner/outer review hooks. Weak
  on rollback / feature-flag risk planning when the change is small.
- [`product-owner-story-refinement.md`](product-owner-story-refinement.md):
  total `25/30`. Strong handoff to `issue-investigator` when root cause is
  unknown. Weak on calling out non-functional and accessibility considerations
  by default.
- [`manual-tester-defect-report.md`](manual-tester-defect-report.md):
  total `26/30`. Strong evidence and environment capture. Weak on stating what
  it did *not* test and why, beyond the explicit scope.
- [`test-automation-engineer-flaky-test-review.md`](test-automation-engineer-flaky-test-review.md):
  total `25/30`. Strong test-pyramid reasoning and explicit fallback when CI
  history is unavailable. Weak on suggesting concrete instrumentation hooks.
- [`multi-skill-bug-to-regression-flow.md`](multi-skill-bug-to-regression-flow.md):
  total `25/30`. Handoffs between skills are clean; the chain stops cleanly
  when evidence is missing. Weak on summarizing the cross-skill audit trail at
  the end.

## Common Strengths

- All skills stop or downgrade confidence when required inputs are missing,
  rather than producing confident but unsupported output.
- Output contracts are honored consistently. Required sections appear, and
  unavailable items are marked rather than skipped silently.
- Handoffs between skills are explicit. `product-owner` correctly routes
  unknown-root-cause work to `issue-investigator`. `software-engineer`
  correctly invokes `code-reviewer` at inner and outer loop hooks.

## Common Gaps

- Skills could be more proactive about naming the **safe** commands or
  read-only checks the user could run to fill missing evidence, instead of
  only listing what is missing.
- Cross-cutting concerns (accessibility, performance, security review,
  rollback plan) are sometimes only mentioned when the input explicitly hints
  at them.
- Multi-skill flows benefit from a single end-of-chain audit summary so the
  caller can see what each skill contributed.

## Changes Made For v0.9.0

The eval runs surfaced wording-level rather than structural problems. For this
release the skill files were not rewritten; instead the gaps are recorded here
and in each per-skill file so they can be addressed in a later release without
losing the audit trail.

The repository did receive these supporting changes:

- Added the [`eval-runs/`](../) directory and this scoring framework.
- Linked eval runs from the docs index, validation guide, release checklist,
  and skill performance review.
- Updated `VERSION`, README status, all skill metadata, and the changelog to
  `0.9.0`.

## Changes Deliberately Not Made

- No new skills were added.
- No nested skill was promoted to the top level.
- Eval runs do not gate CI. They are a maintainer review aid, not a benchmark.
- Skill wording was not rewritten purely to chase higher scores. Findings here
  describe real gaps to consider in future releases.

## Suggested Future Eval Runs

- A second pass on `software-engineer` covering an in-repo greenfield change
  rather than a bugfix.
- A `code-reviewer` run on a long-lived branch with mixed feature and refactor
  commits, to see how severity filters behave at scale.
- A `test-automation-engineer` run that has access to real (anonymized) CI
  history rather than just illustrative numbers.
