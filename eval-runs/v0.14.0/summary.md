# v0.14.0 Eval Runs - Summary

This is the maintainer eval-run review for release `v0.14.0`. It scores the
SKILL content sharpening that ships in this release: making project /
per-module documentation discovery a hard, sequenced step in the four
affected skills (`software-engineer`, `issue-investigator`, `manual-tester`,
`test-automation-engineer`), and adding a diagnose-before-blame rule for
failing tests on a clean tree.

Category: maintainer-authored (illustrative).

## Scope of this release

- Promoted README + `CONTRIBUTING.md` discovery from a single buried
  narrative line in `software-engineer` Phase "Context discovery" to a
  hard checklist item in Phase 1.2 ("Identify the project").
- Added an explicit per-module README requirement for multi-module /
  nested-submodule repositories, where module-level test setup is
  frequently the only place where Testcontainers, fixture generators,
  required env vars, profile flags, and Make targets are documented.
- Added a Phase 3.3 pre-flight that requires README-documented test setup
  to be in place before invoking the build command.
- Added a Phase 3.3 diagnose-before-blame rule: if tests fail on a clean
  tree, walk the documentation ladder (README → `CONTRIBUTING.md` →
  `.github/workflows/` → output signals) before reporting "tests are
  broken".
- Mirrored the documentation-first discipline into `issue-investigator`
  Step 4, `manual-tester` Step 1, and `test-automation-engineer` Step 3
  with the same rationale (classify documented prerequisites as setup
  gaps, not defects / blockers / brittle automation).
- Updated `software-engineer/references/architecture-patterns.md` so the
  "Discovering project-specific conventions" reference matches the new
  workflow checklist.
- No new skills, no new env vars, no `setup.init` change, no `.env.example`
  change, no CI change.

## Scoring summary

Each item below scores the user-visible improvement on the 5-point scale used
by previous eval runs (1=poor, 5=excellent).

- Root-cause fix for "agent reports failing tests on a clean tree without
  reading per-module README": 5/5. The instruction is now a hard checklist
  item in two distinct phases (project identification AND immediately
  before the build command), and the diagnose-before-blame rule names the
  exact failure mode out loud.
- Coverage across collaborating skills: 5/5. The four skills that touch
  test/build setup (`software-engineer`, `issue-investigator`,
  `manual-tester`, `test-automation-engineer`) all received the same
  discipline. `code-reviewer` was deliberately left alone because it
  inherits the discovery via the evidence-pack hard handoff.
- Surgical-edit discipline: 5/5. No skill renames, no contract changes,
  no new environment variables or setup flags. Pure content sharpening.
- Documentation alignment: 5/5. CHANGELOG explains the *why* (real
  failure mode), README status line and all six `SKILL.md`
  `metadata.version` fields bumped, `architecture-patterns.md` reference
  updated to match the workflow checklist.
- Reviewer self-rebuttal: 4/5. The single credible scenario in which this
  change is wrong is a project that has no README at all (or an empty
  one). The new instructions still degrade gracefully there: the build
  manifest fallback and CI-workflow inspection both remain explicit, and
  "ask the user when context is insufficient" is unchanged. Lost half a
  point because the failure mode for "README exists but is wrong / stale"
  is still resolved by the same fallback ladder rather than called out
  separately.

## Follow-ups recorded for future releases

- Consider an opt-in cache of "discovered project-doc summaries" so the
  README pass does not need to be re-read on every invocation in the same
  session. Out of scope for v0.14.0.
- Consider whether `code-reviewer` should explicitly check that the
  engineer's evidence pack references the per-module README pass for
  multi-module changes. Hold until evidence shows the inherited discipline
  is insufficient.
- Consider extending the diagnose-before-blame ladder to "build fails on
  a clean tree" in addition to "tests fail on a clean tree". v0.14.0
  scopes the rule to tests because that is what the reported failure mode
  was; the ladder applies equally to builds and can be added later
  without breaking changes.
