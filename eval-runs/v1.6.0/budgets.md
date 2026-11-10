# v1.6.0 — Phase 1 budgets and verification

Phase 1 of [the plan](../../docs/plans/2026-11-tdd-lessons-v1.6.0.md), recorded on branch
`feature/tdd-lessons-1.6.0` in a clean worktree. Python 3.9.6. Every number below came from the
command named next to it. Implementation commits end at `44cbb5f`; this file is committed after it.

## Token budgets (plan section 5.3), `wc -c`

Baseline is `origin/main` at `7692795`.

| File | Before | After | Growth | Cap | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| `skills/software-engineer/SKILL.md` | 81,672 | 83,043 | +1,371 | +1,500 | within |
| `skills/product-owner/SKILL.md` | 26,696 | 27,268 | +572 | +800 | within |
| `skills/software-engineer/skills/code-reviewer/SKILL.md` | 53,335 | 53,712 | +377 | +600 | within |
| `skills/wamala/references/handoff-prompt-template.md`, template block only | 5,946 | 6,002 | +56 | +120 | within |
| `skills/software-engineer/references/test-driven-mode.md` (new) | 0 | 5,219 | +5,219 | <= 9,000 | within |
| `skills/software-engineer/references/developer-testing.md` | 17,955 | 18,861 | +906 | +1,200 | within |
| `skills/software-engineer/references/definition-of-done.md` | 11,559 | 12,331 | +772 | +1,000 | within |
| `skills/software-engineer/references/evidence-pack.md` | 26,006 | 26,573 | +567 | +1,200 | within |
| Every skill's frontmatter `description` | — | unchanged | 0 | 0 | within |

The whole handoff template file grows from 16,038 to 16,280; the rest of that growth is the
field note in "Filling rules", outside the block every brief copies. The template block was
measured as the first fenced `text` block (lines 18-118 at the base).

Per-change growth of `software-engineer/SKILL.md` (from `git show <c>^` vs `<c>`): G −6 (two
`→` escapes became the character), D +484 (cap 600), E +250 (cap 350), B +195, C +448
(the Phase 2 pointer plus one Reference-files line; the pointer alone is under the 400 cap).
`code-reviewer`: D +221 (cap 350), C +156 (cap 250).

`wc -c` counts bytes, so a multi-byte character (an em dash, an arrow) counts more than once;
the figures can only overstate the character growth, never understate it.

## Validator

| Measure | Before (`7692795`) | After (`44cbb5f`) |
| --- | --- | --- |
| `python3 scripts/validate-repo.py` exit | 0 | 0 |
| Warnings | 84 | 84: the same 84 (sorted `WARN` lines diffed); one moved from line 399 to 412 |
| Runtime, 3 runs (`/usr/bin/time -p`, real) | 1.03, 1.07, 0.97 s | 1.08, 1.08, 1.08 s |
| Median | 1.03 s | 1.08 s (cap 1.5 s) |
| Fragment links checked | 308 | 324 (the plan's own contents list and the new cross-references) |

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

## Suites

| Command | Exit | Key result |
| --- | ---: | --- |
| `python3 scripts/validate-repo.py` | 0 | 84 warnings |
| `python3 scripts/run-evals.py` | 0 | 66 files, 12 skills, 0 failures, 0 warnings |
| `python3 scripts/run-evals.py --strict-sections` | 0 | 0 failures |
| `python3 scripts/test-validate-links.py` (new) | 0 | 16 passed, 0 failed; probe ok |
| `bash scripts/test-adaptive-execution.sh` | 0 | 84 passed, 0 failed, including probe 5 |
| `python3 scripts/test-release-engine.py` | 0 | 31 passed, 0 failed |
| `python3 scripts/dod-check.py <scratch>/definition-of-done.json` | 0 | verified, 0 problems |
| `agent-skills dod-check <scratch>/definition-of-done.json` | 0 | verified, 0 problems |

The links probe replaces the fragment comparison with `if False:` in a sandboxed copy of the
validator; the missing-anchor case then fails, which proves the test exercises the check. Probe 5
removes every `checks.mutation` line from a sandboxed copy of `software-engineer/SKILL.md`; the
performer check then fails.

The Definition of Done (scratch, outside the repository) records `head_sha` `44cbb5f`, with
`build` and `tests` as passing runs, `format` and `security_scan` as not applicable with reasons,
and `checks.mutation` as not applicable: the work is `STANDARD`, and the new checks carry their
own probes.

## Paths

`git diff --name-only origin/main...HEAD` lists only files section 6 names, `CHANGELOG.md`, new
files under `evals/` and `eval-runs/v1.6.0/`, and the plan itself. Nothing under `lib/`, `bin/`,
`hooks/`, or `npm/`; `scripts/install.py`, `scripts/guard*`, `scripts/execution-profile.py`, and
`scripts/dod-check.py` are untouched; no version file changed.

`eval-runs/v1.6.0/summary.md` is a short not-yet-certified stub: `scripts/run-evals.py` fails any
`eval-runs/<dir>/` without a `summary.md`, so `budgets.md` cannot ship alone.

## Not done in Phase 1

- No push, no draft PR: this run was told to commit locally only, which overrides the plan's
  "pushed to the feature branch; a draft PR opened".
- No independent review yet (Phase 2), so no `review-round-*.md`.
- The four new evals were added and pass the structural runner; they were not executed against a
  model or scored. That is Phase 2's R10.
- `bash scripts/test-release-readiness.sh` was not run; it is a Phase 5 gate. Only its syntax was
  checked (`bash -n`).
