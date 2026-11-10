# v1.6.0 — Phase 1 budgets and verification

Phase 1 of [the plan](../../docs/plans/2026-11-tdd-lessons-v1.6.0.md), recorded on branch
`feature/tdd-lessons-1.6.0` in a clean worktree. Python 3.9.6. Every number below came from the
command named next to it. Phase 1 implementation ended at `44cbb5f`. Updated after fix round 1
([review round 1](review-round-1.md)): all figures below are for `0d0674d`, the last commit before
this file's update, unless a row says otherwise.

## Token budgets (plan section 5.3), `wc -c`

Baseline is `origin/main` at `7692795`.

| File | Before | After | Growth | Cap | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| `skills/software-engineer/SKILL.md` | 81,672 | 83,093 | +1,421 | +1,500 | within |
| `skills/product-owner/SKILL.md` | 26,696 | 27,268 | +572 | +800 | within |
| `skills/software-engineer/skills/code-reviewer/SKILL.md` | 53,335 | 53,712 | +377 | +600 | within |
| `skills/wamala/references/handoff-prompt-template.md`, template block only | 5,946 | 6,002 | +56 | +120 | within |
| `skills/software-engineer/references/test-driven-mode.md` (new) | 0 | 5,517 | +5,517 | <= 9,000 | within |
| `skills/software-engineer/references/developer-testing.md` | 17,955 | 18,861 | +906 | +1,200 | within |
| `skills/software-engineer/references/definition-of-done.md` | 11,559 | 12,538 | +979 | +1,000 | within |
| `skills/software-engineer/references/evidence-pack.md` | 26,006 | 26,573 | +567 | +1,200 | within |
| Every skill's frontmatter `description` | — | unchanged | 0 | 0 | within |

The whole handoff template file grows from 16,038 to 16,280; the rest of that growth is the
field note in "Filling rules", outside the block every brief copies. The template block was
measured as the first fenced `text` block (lines 18-118 at the base).

Per-change growth of `software-engineer/SKILL.md` (from `git show <c>^` vs `<c>`): G −6 (two
literal escapes became the arrow character), D +484 (cap 600), E +250 (cap 350), B +195, C +448
(the Phase 2 pointer plus one Reference-files line), round 1 +50 (the pointer's trigger list and
user-request clause). The pointer paragraph is now 382 bytes (cap 400). `code-reviewer`: D +221
(cap 350), C +156 (cap 250); unchanged in round 1. `definition-of-done.md` grew 207 in round 1
(the verifying example and the waiver sentence), trimmed elsewhere in the file to stay under +1,000.

`wc -c` counts bytes, so a multi-byte character (an em dash, an arrow) counts more than once;
the figures can only overstate the character growth, never understate it.

## Validator

| Measure | Before (`7692795`) | After (`0d0674d`) |
| --- | --- | --- |
| `python3 scripts/validate-repo.py` exit | 0 | 0 |
| Warnings | 84 | 84: the same 84 (sorted `WARN` lines diffed); one moved from line 399 to 412 |
| Runtime, 3 runs (`/usr/bin/time -p`, real) | 1.03, 1.07, 0.97 s | 1.17, 1.20, 1.17 s |
| Median | 1.03 s | 1.17 s (cap 1.5 s); at `44cbb5f` it was 1.08 s |
| Fragment links checked | 308 old fence rule, 305 new | 321 (plan contents list, new cross-references) |

### F1 oracle

The new anchor check, run against an export of `7692795` (`git archive`) with only
`scripts/validate-repo.py` replaced, reports exactly the ten links in the plan's F1 table and no
other anchor error:

```text
CHANGELOG.md: broken anchor (no such heading): ROADMAP.md#before-100
CHANGELOG.md: broken anchor (no such heading): docs/installation.md#upgrading-from-v036x-workspace-installation
CHANGELOG.md: link with an empty fragment: #
docs/execution-modes.md: broken anchor (no such heading): installation.md#upgrading-from-v036x-workspace-installation
docs/quickstart.md: broken anchor (no such heading): installation.md#upgrading-from-v036x-workspace-installation
docs/release-checklist.md: broken anchor (no such heading): versioning.md#contracts-under-consideration-for-a-10-freeze
docs/security-review-v0.44.0.md: broken anchor (no such heading): versioning.md#contracts-under-consideration-for-a-10-freeze
eval-runs/v1.0.0-rc.2/summary.md: broken anchor (no such heading): ../../ROADMAP.md#before-100
eval-runs/v1.0.0-rc.3/summary.md: broken anchor (no such heading): ../../ROADMAP.md#before-100
skills/software-engineer/references/evidence-pack.md: broken anchor (no such heading): #evidence-packymldelivery_plan-ownership-rule
```

That export also printed one unrelated failure, `missing required file:
skills/software-engineer/references/test-driven-mode.md`, because the final validator registers
the reference that change C adds; it is not an anchor result. The same ten were seen first on the
branch worktree before any link was edited. On the branch the check reports zero.

Re-run after fix round 1 (slug fix for reference links and code-span link text, CommonMark fence
closing, entities, literal underscores) on a fresh `git archive origin/main`: the same ten lines
and the same one unrelated failure, nothing else.

The fragment-link count on the base dropped from 308 to 305 with the stricter fence rule, and
the cause is a pre-existing rendering defect, not a checker bug:
`skills/delivery-planner/references/phase-template.md` opens a three-backtick `markdown` fence at
line 74 and nests a fenced `yaml` block (three backticks plus `yaml`) at line 115. Under CommonMark (and on GitHub) the
inner opener does not close the outer fence, so line 123 closes it, and line 189 opens a fence that
runs to the end of the file. The three links at lines 198, 203, and 207 are therefore not
rendered as links, and the checker now agrees. The file is outside plan section 5.2; the fix (a
four-backtick outer fence) is recorded here for a later change.

## Suites

| Command | Exit | Key result |
| --- | ---: | --- |
| `python3 scripts/validate-repo.py` | 0 | 84 warnings |
| `python3 scripts/run-evals.py` | 0 | 67 files, 12 skills, 0 failures, 0 warnings |
| `python3 scripts/run-evals.py --strict-sections` | 0 | 0 failures |
| `python3 scripts/test-validate-links.py` (new) | 0 | 23 passed, 0 failed; probe ok |
| `bash scripts/test-adaptive-execution.sh` | 0 | 85 passed, 0 failed, including probe 5 |
| `python3 scripts/test-release-engine.py` | 0 | 31 passed, 0 failed |
| `bash -n scripts/test-private-source.sh` (header comment changed) | 0 | syntax only |
| `python3 scripts/dod-check.py <scratch>/definition-of-done.json` | 0 | verified, 0 problems |
| `agent-skills dod-check <scratch>/definition-of-done.json` | 0 | verified, 0 problems |

Regression tests added in round 1, each run against the pre-fix code first:

- `test-validate-links.py`: seven cases (reference link in a heading, its label not in the slug,
  code span in link text, entity, literal leading underscore, underscore emphasis, info-string line
  inside a fence). Six failed before the fix; the emphasis case already passed.
- `test-adaptive-execution.sh`: the Definition-of-Done reference's schema example is extracted and
  run through `dod-check`. It failed on the pre-fix reference ("claims pass but records exit_code
  1") and passes now.

The links probe replaces the fragment comparison with `if False:` in a sandboxed copy of the
validator; the missing-anchor case then fails, which proves the test exercises the check. Probe 5
removes every `checks.mutation` line from a sandboxed copy of `software-engineer/SKILL.md`; the
performer check then fails.

The Definition of Done (scratch, outside the repository) records `head_sha` `0d0674d`, with
`build` and `tests` as passing runs, `format` and `security_scan` as not applicable with reasons,
and `checks.mutation` as not applicable: the work is `STANDARD`, and the new checks carry their
own probes.

## Paths

`git diff --name-only origin/main...HEAD` lists only files section 6 names, `CHANGELOG.md`, new
files under `evals/` and `eval-runs/v1.6.0/`, the plan itself, and the two spots the round 1
amendment to 5.2 allows (`SECURITY.md` line 3, the header comment of `test-private-source.sh`). Nothing under `lib/`, `bin/`,
`hooks/`, or `npm/`; `scripts/install.py`, `scripts/guard*`, `scripts/execution-profile.py`, and
`scripts/dod-check.py` are untouched; no version file changed.

`eval-runs/v1.6.0/summary.md` is a short not-yet-certified stub: `scripts/run-evals.py` fails any
`eval-runs/<dir>/` without a `summary.md`, so `budgets.md` cannot ship alone.

## Not done

- No push, no draft PR: this run was told to commit locally only, which overrides the plan's
  "pushed to the feature branch; a draft PR opened".
- The five new evals pass the structural runner; none was executed against a model or scored.
- `bash scripts/test-release-readiness.sh` was not run; it is a Phase 5 gate. Only its syntax was
  checked (`bash -n`).
