# v1.6.0 independent review — round 2

Reviewer: the same fresh-context subagent as round 1, no access to implementer notes. Delta
reviewed: `6e4ffc5..dbe6125` (14 commits). The full R1-R11 checklist was then re-run on `HEAD`
(`dbe6125`) against `origin/main` (`7692795`). Every number was re-measured. Scratch directory:
`<session scratchpad>/review` (`$R` below). Python 3.9.6.

Summary: 0 blocker, 0 major, 2 minor (one introduced by a fix, one pre-existing), 2 nit. Every
round-1 finding is fixed. Model-scored evals were still not run.

## Round-1 report as committed

`git diff 6e4ffc5..HEAD -- eval-runs/v1.6.0/review-round-1.md` changes four places: the scratch
path is redacted, a path in a grep pattern is escaped, and two inline fence markers are written out
in words. No finding, severity, or verdict changed, and the loop line is still `continue`.

One correction to round 1. Its R8 nit said no nested-fence case existed in the repository. That
was wrong: see the pre-existing minor under R8 below. The grep used then looked only for
four-character openers.

## Round-1 findings: are they fixed?

- **major R8: wrong slugs for headings whose links are reference-style or have code spans in
  their text.** Fixed.
  - In a sandbox export of `HEAD`, a link to `../README.md#wamala-top-level` added to
    `docs/quickstart.md` validates, and adding `#wamalawamala-top-level` gives
    `FAIL … broken anchor`.
  - `$R/slug.py`: all 11 cases match GitHub.
- **nit R8: fence closing, `&amp;`, lone `_`.** Fixed.
  - `$R/fence.py`: an info-string line no longer closes a fence.
  - The slugs are now `tom--jerry` and `the-_private-flag`.
  - `test-validate-links.py` has seven new cases, and all 23 cases pass.
- **minor R5: "exactly two places the mode pauses".** Fixed. `test-driven-mode.md:74-78` now says
  the mode adds two pauses and removes none. It names gate 1.5, the confirmations, and the safety
  floor.
- **minor R7: `not_run` vs waiver.** Fixed. `definition-of-done.md:236-237` says "Waivers cover
  required checks only".
- **Pre-existing R7: the schema example was rejected by `dod-check`.** Fixed, but see the new minor
  under R7.
  - I extracted the example on my own, without the new suite. `dod-check` exits 0 on both the
    branch and `origin/main`.
  - The adaptive-execution suite now checks it too.
- **minor R9: `SECURITY.md` and the `test-private-source.sh` header.** Fixed.
  - `SECURITY.md:3` no longer says private.
  - In `git diff origin/main..HEAD -- scripts/test-private-source.sh`, every changed line is a `#`
    comment inside lines 1-15.
  - Plan 5.2 is amended to allow both changes.
- **nit R9: upgrade links.** Fixed. They now point at `#coming-from-the-pre-v037-workspace-layout`
  in `execution-modes.md:79`, `quickstart.md:94`, and `CHANGELOG.md`, and the validator passes.
- **minor R10: the completeness eval did not match its own instruction.** Fixed.
  - The input now states five rules instead of twelve cells, and the expectations follow from
    them: rules 1-3 get one test each, rule 4 gets two, and rule 5 gets one, so six tests.
  - Rounding case checked: 3 GB at 0.015 is 0.045, which is 0.05 half-up and 0.04 half-even or
    truncated.
- **minor R10: no eval for predicted RED.** Fixed by `evals/software-engineer-predicted-red.md`.
  P1 is a matching failure. P2 is an import error, which is not RED.
- **nit R10: conditional already-passing item; STANDARD Must-Not.** Fixed. The TDD eval's
  checklist item is now conditional, and the mutation eval adds M4, a `STANDARD` case with a tool
  configured.
- **nit R4: trigger vocabulary; the brief must trace to the user.** Fixed.
  - `SKILL.md:552-555` and `test-driven-mode.md:9-11` list the same three triggers.
  - A brief counts only when it carries the user's request.

## R1 Contract — pass

`git diff --quiet origin/main...HEAD -- VERSION npm lib bin hooks` exits 0, and `VERSION` is
`1.5.0`. `scripts/dod-check.py`, `scripts/install.py`, `scripts/guard*`, and
`scripts/execution-profile.py` are unchanged. No frontmatter description changed.
`test-release-engine.py`: 31 passed, 0 failed.

## R2 Scope — pass

The delta adds `SECURITY.md` and `scripts/test-private-source.sh`. Both are allowed by the amended
5.2, and the script change is comment-only within lines 1-15 (checked above). The new eval is
under `evals/`. All other paths were already in scope.

## R3 Budgets — pass

`wc -c` against `origin/main`:

| File | Delta | Cap |
| --- | ---: | ---: |
| `software-engineer/SKILL.md` | +1,421 | +1,500 |
| `product-owner/SKILL.md` | +572 | +800 |
| `code-reviewer/SKILL.md` | +377 | +600 |
| handoff template block | +56 | +120 |
| `test-driven-mode.md` (new) | 5,517 | <= 9,000 |
| `developer-testing.md` | +906 | +1,200 |
| `definition-of-done.md` | +979 | +1,000 (21 under, confirmed) |
| `evidence-pack.md` | +567 | +1,200 |

Sub-caps: the C.1 pointer is now 383 against 400. The D.1, E.1, C.4, and D.3 sizes are unchanged
from round 1, and all are within their caps.

## R4 Opt-in — pass

I re-read every sentence on the branch that mentions the mode. Only an explicit user request
enters it, a brief counts only when it relays that request, and the profile never does.

## R5 Consistency — pass

- `docs/evidence-discipline.md:69` is unchanged.
- The code-reviewer test-first lines are unchanged.
- `docs/review-loops.md` is unchanged.
- The new pause wording in the TDD reference agrees with 2.5 and with the safety floor.

## R6 Portability and provenance — pass

- No host, path, URL, or person in the new skill text.
- I re-ran the 6-word shingle check on the changed reference and on the new and changed evals.
  The only overlaps are the technique name and the stock phrase "when the user explicitly asks
  for TDD". In the source that phrase appears only inside YAML `description` lines, and no
  sentence is copied.

## R7 Mutation testing — pass, one minor

- The 1.5.0-shaped DoD from round 1 (`$R/dod-1.5.0.json`) and its 1.6.0 variants all exit 0 under
  the branch `dod-check.py`.
- The schema example in the doc also verifies, on both the branch and `origin/main`.
- No tool is ever installed.

- **minor (introduced by the round-1 fix)** — the new `regression_red` example and the skill
  describe different shapes, and the example command is wrong.
  - Where: `skills/software-engineer/references/definition-of-done.md:99-112` and
    `skills/software-engineer/SKILL.md:531-536`.
  - **Wrong directory.** The example command runs `git worktree add ../red fa11ed00 && cd ../red`
    from `cwd: services/example-api`. That creates the worktree inside the main working tree at
    `services/red`, where it shows as untracked, and runs `mvn test` at the baseline's root
    instead of the module.
  - **Negation hides setup failures.** The `!` turns every failure into exit 0, including the
    setup and compile failures that the rule says are not RED. Only the `assertion` field still
    separates RED from them.
  - **The skill was not updated.** Gate 1.5 still says to run the test on the test-only commit
    and "record the command, revision, exit code". An engineer who reads only the skill records
    the baseline as `revision`, and `dod-check` rejects that as stale. The skill does not mention
    the new `baseline_revision`, and `test_exit_code` is not explained in Rules.
  - **CHANGELOG.** It says the example "now verifies" but not that the way RED is recorded
    changed.
  - Reproduce: in a scratch repository with `services/example-api`, run the example command's
    first two steps from that directory. `pwd` prints `…/services/red`, and the main tree's
    status shows `?? services/red/`. The stale-revision rejection was reproduced in round 1.
  - Reproduced: yes.

## R8 Anchor checker — pass, one pre-existing minor

- **Oracle.** I exported `origin/main` fresh (`$R/oracle2`) and dropped in the branch validator.
  It reports exactly the ten F1 anchor errors and no other anchor error. The one other `FAIL` is
  the expected missing `test-driven-mode.md`.
- **Fragment links.** 305 on main and 321 on the branch.
- **Probe.** `test-validate-links.py`: 23 passed, probe ok.
- **Timing.** Median of 3 is 1.16 s (1.18, 1.16, 1.15), under the 1.5 s limit.
- **Emoji and code-span headings.** No false positives (`$R/slug.py`).

- **minor (pre-existing on `origin/main`, outside 5.2) — the nested-fence claim is confirmed.**
  - `skills/delivery-planner/references/phase-template.md` opens a `markdown` fence at line 74
    and nests a `yaml` fence at 115-123.
  - Under CommonMark the line at 115 does not close the outer fence, but the bare fence at 123
    does.
  - `gh api -X POST /markdown -f mode=gfm` on the file shows the result. "Expected outputs /
    artifacts", "Validation / exit criteria", "Risks specific to this phase", "Rollback / abort
    behavior", and "Notes for the executor" render as real headings. The fence at line 189 then
    runs to the end of the file, so "When the phase is owned by a non-implementation skill" and
    its three links render as code.
  - Those three links are the drop from 308 to 305 (`sed -n 189,400p` on the file lists them).
  - The new validator models GitHub correctly here. The template file itself is broken for
    readers and needs a separate, plan-amended fix: a four-backtick outer fence.
  - Reproduced: yes.

## R9 Docs — pass, one nit

- `validate-repo.py` exits 0 with 84 warnings.
- No changed line is over 200 characters.
- The `CHANGELOG.md` additions are under `Unreleased`.
- The visibility wording is consistent across README, CONTRIBUTING, ROADMAP, SECURITY, the
  checklist, and the script header.

- **nit** — `CHANGELOG.md` (visibility entry) says README, CONTRIBUTING, ROADMAP, and SECURITY say
  "solo-maintained, not open to outside contribution". `SECURITY.md:3` actually says "proprietary,
  solo-maintained software". Also, `test-driven-mode.md:11` is an unwrapped 118-character line,
  where the rest of the file wraps at 100. Reproduce: `sed -n 3p SECURITY.md` and
  `awk 'length>100' skills/software-engineer/references/test-driven-mode.md`. Reproduced: yes.

## R10 Evals — structural pass; model scoring not run

- `run-evals.py`: 67 files, 0 failures, 0 warnings. `--strict-sections` exits 0.
- `test-adaptive-execution.sh`: 85 passed, 0 failed. This includes the new check that the
  schema example verifies, and probe 5.
- The five new evals each now test their behaviour coherently.
- The scorecard runs (the new evals, `developer-testing-*`, and
  `code-reviewer-test-verification-quality`) were not run, because the reviewer cannot execute
  models. They remain required before Phase 5 certification.

## R11 Safety floor — pass

No change to hooks, guards, `lib/`, destructive-action documents, or redaction.

## Comparison with `budgets.md` (read last)

Its budgets, timing, the 305/321 link counts, and the suite counts agree with this re-measurement.

Loop: converged
