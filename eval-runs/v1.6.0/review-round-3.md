# v1.6.0 independent review — round 3 (delta)

Reviewer: the same fresh-context subagent as rounds 1 and 2. Delta: `0f6ac09` (7 files). The suites
and budgets were then re-run on `HEAD`. Scratch directory: `<session scratchpad>/review/r3` (`$R`).

Summary: 0 blocker, 0 major, 0 minor, 2 nit. The round-2 minor is fixed, and so is the pre-existing
phase-template fence.

## Round-2 minor: the `regression_red` example and gate 1.5 — fixed

- **The command now works as described.** I ran it in a scratch repository with `cwd: "."` (the
  root) and a stub `mvn` on the path:
  - `git worktree add ../red` creates a sibling of the repository, not a directory inside it.
  - `cd ../red/services/example-api` lands in the module. The stub printed its own working
    directory as `…/red/services/example-api`.
  - When the stub prints the expected assertion and exits 1, the pipeline exits 0 (via
    `grep -q`).
  - When the stub prints a compilation error and exits 1, the pipeline exits 1. A setup or
    compile failure therefore no longer counts as RED.
  - Reproduced: yes.
- **The example still verifies.** The schema example extracted from
  `skills/software-engineer/references/definition-of-done.md` passes `python3
  scripts/dod-check.py` (exit 0). The 1.5.0-shaped DoD built by hand in round 1 also still exits 0.
- **Gate 1.5 now matches the reference.** `skills/software-engineer/SKILL.md:535-536` names the
  head-run command, which exits 0 only on the expected assertion, together with
  `baseline_revision`.
- **The CHANGELOG** now records the change in how RED is recorded.

## Round-2 pre-existing minor: the phase-template fence — fixed

- `skills/delivery-planner/references/phase-template.md` now opens and closes the outer fence with
  four backticks, at lines 74 and 189. The plan's 5.2 is amended for exactly those lines.
- `gh api -X POST /markdown -f mode=gfm` on the file:
  - Inside the template only `Phase Template`, `File header`, `Execution profile`, and
    `Body sections` are headings now. The template's own sections render as code.
  - `When the phase is owned by a non-implementation skill` is a real heading again.
  - Its three links render as links: `definition-of-ready-gate-before-handoff`,
    `investigation-quality-checklist`, and `test-plan-review-checklist`.
- All three anchors exist in their targets, checked with the validator's `heading_anchors`.
- The branch now has 324 fragment links (321 + 3).

## Round-2 nits

- **SECURITY quote in the CHANGELOG** — fixed. The entry now quotes "proprietary,
  solo-maintained".
- **nit (not fixed, moved)** — the unwrapped line in `test-driven-mode.md` is still 118 characters,
  now at line 12. The rewrap moved the long tail down a line instead of breaking it. The edited
  CHANGELOG visibility line (`CHANGELOG.md:56`) is 141 characters. Both are under the 200-character
  limit, so this is style only. Reproduce:
  `awk 'length>100{print FILENAME":"FNR": "length}' skills/software-engineer/references/test-driven-mode.md CHANGELOG.md`.
  Reproduced: yes.

## New in this delta

- **nit** — the recorded RED command cannot be re-run as written. `git worktree add ../red` fails
  with `fatal: '../red' already exists` on a second run, so a reviewer repeating the command in
  `--repro-verify` has to remove the worktree first. A `git worktree remove` step at the end, or a
  unique path, would make it repeatable. Reproduce: run the pipeline twice in the scratch
  repository; the second run exits 128. Reproduced: yes.

## Checks re-run on `HEAD`

| Check | Result |
| --- | --- |
| `software-engineer/SKILL.md` budget | +1,497 of +1,500 (3 under) |
| `definition-of-done.md` budget | +976 of +1,000 |
| `test-driven-mode.md` | 5,517 of 9,000 |
| `python3 scripts/validate-repo.py` | exit 0, 84 warnings; median 1.17 s (1.20, 1.14, 1.17) |
| `python3 scripts/test-validate-links.py` | 23 passed, probe ok |
| `bash scripts/test-adaptive-execution.sh` | 85 passed, 0 failed, schema-example check ok |
| `python3 scripts/run-evals.py` and `--strict-sections` | 67 files, 0 failures; exit 0 |
| Scope | the delta touches only paths allowed by 5.2 as amended |

Model-scored eval runs are still not run. They remain required before Phase 5 certification.

Loop: converged
