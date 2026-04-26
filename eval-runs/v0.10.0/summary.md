# v0.10.0 Eval Runs - Summary

This is the maintainer eval-run review for release `v0.10.0`. It scores the
two new deeper scenarios introduced this release against the
[skill quality scorecard](../../docs/skill-quality-scorecard.md), records
what improved relative to `v0.9.0`, and lists the changes (and deliberate
non-changes) made to the skills.

> The transcripts in each per-skill file are **illustrative**
> (maintainer-authored). They show the kind of output a competent assistant
> should produce with the listed inputs. They are not raw outputs of any
> single specific model. See [`../README.md`](../README.md) for the three
> eval-run categories (illustrative, real model transcript, future automated).

## Scope

This release does not re-run every `v0.9.0` scenario. It adds two **deeper
scenarios** with realistic incomplete context that probe the gaps surfaced in
`v0.9.0`:

- `issue-investigator` with read-only access only (no write access, no Jira).
- `code-reviewer` with significant unavailable context (no issue access, no
  CI artifacts, no architecture guideline).

The previous scenarios in [`../v0.9.0/`](../v0.9.0/summary.md) remain valid
as the baseline for those scorecards.

## Per-Scenario Results

Scores are `0`-`3` per criterion across the ten scorecard criteria, totalling
out of `30`. See each file for the full per-criterion breakdown.

- [`issue-investigator-read-only-investigation.md`](issue-investigator-read-only-investigation.md):
  total `28/30`. The new "Safe checks the user can run" output section is
  populated with bounded, hypothesis-tied read-only checks. Up from `26/30`
  on the analogous v0.9.0 scenario.
- [`code-reviewer-unavailable-context.md`](code-reviewer-unavailable-context.md):
  total `27/30`. The new "Review Limitations / Unavailable Context" section
  is filled out and the verdict refuses a bare `PASS` while context is
  missing. Up from `25/30` on the analogous v0.9.0 scenario.

## What Improved

- `issue-investigator` no longer stops at "missing evidence". It proposes
  bounded read-only checks that are tied to specific hypotheses and labelled
  with the safe environment they belong in.
- `code-reviewer` records what it could not see in a dedicated output section
  and uses that section to calibrate the final verdict. A bare `PASS` while
  significant context is missing is now disallowed by the workflow and the
  behavior checklist.
- Eval-run files now declare a category (illustrative, real model transcript,
  or future automated). This makes it easier for a reader to tell what kind
  of evidence each file represents.

## Changes Made For v0.10.0

- `skills/software-engineer/skills/code-reviewer/SKILL.md`: added workflow
  step 9 "Record review limitations explicitly" and an output-contract
  section "Review Limitations / Unavailable Context". Behavior checklist
  updated to require the section to be filled.
- `skills/software-engineer/skills/issue-investigator/SKILL.md`: added
  "Safe read-only checks the user can run" subsection in the workflow and
  a matching "Safe Checks The User Can Run" block in the output contract.
  Behavior checklist updated. Guardrails updated to forbid mutating or
  unbounded checks being labelled "safe".
- `eval-runs/README.md`: rewrote "How These Were Produced" into three
  explicit categories (illustrative, real model transcript, future
  automated) with required labels.
- Added two new eval scenarios under [`evals/`](../../evals/) and the
  matching v0.10.0 run files under this directory.
- Bumped `VERSION`, README status, all six skill metadata, and the
  changelog to `0.10.0`.

## Changes Deliberately Not Made

- No new skills.
- No nested skill promoted to top level.
- Skill philosophy was not rewritten. The two changes above are wording-level
  additions that the v0.9.0 eval runs explicitly recommended as future work.
- No real model transcripts were captured in this release. The category
  exists; producing one is a future-release task.
- Eval runs still do not gate CI.

## Suggested Future Eval Runs

- A real-model-transcript run (category 2) of the read-only investigation
  scenario, captured verbatim from a single assistant on a single date.
- A `software-engineer` deeper scenario covering an in-repo greenfield
  change with partial product-owner context.
- A `code-reviewer` run on a long-lived branch with mixed feature and
  refactor commits, to see how severity filters and the new
  "Review Limitations" section behave at scale.
