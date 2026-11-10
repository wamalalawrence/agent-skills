# Release certification — v1.6.0

Every number below was produced by running the command named, on `feature/tdd-lessons-1.6.0`
after the `release: 1.6.0` bump, in a dedicated `git worktree`, so untracked files in the
developer's checkout could not affect it. Python 3.9.6. The plan, with its decisions, is
[docs/plans/2026-11-tdd-lessons-v1.6.0.md](../../docs/plans/2026-11-tdd-lessons-v1.6.0.md).

## What this release changed

Example-guided and predictive testing lessons, kept cheap on the default path: a literal-valued
example for every data-dependent rule (`product-owner`), a completeness counterfactual for
catalogue-shaped specs, a predicted RED at the bug-fix gate, mutation testing at `RIGOROUS` (the
profile promised it; no skill performed it), and an opt-in test-driven mode in its own reference.
Tooling: `validate-repo.py` now checks `#fragment` anchors, which found ten dead links (fixed).
Documentation: visibility wording matches the public repository; four inconsistencies fixed; a
nested-fence rendering defect in the delivery-planner phase template fixed. Additive against the
1.0 contract: no CLI, exit code, install layout, provider, skill name, or `description` change, and
`dod-check.py` is unchanged.

## Verification

| Gate | Result | 1.5.0 |
| --- | --- | --- |
| `scripts/test-release-readiness.sh` | `ok: release readiness verified (94 checks)`, exit 0 | pass |
| `scripts/validate-repo.py` | pass, 84 warnings (same set as 1.5.0) | pass, 84 warnings |
| `scripts/run-evals.py` (+ `--strict-sections`) | 67 files, 0 failures | 62 files, 0 failures |
| `scripts/test-validate-links.py` (new) | 23 passed, 0 failed, probe ok | — |
| `scripts/test-adaptive-execution.sh` | 85 passed (new mutation-consumer probe, DoD example check) | pass |
| `scripts/test-cli-install.sh` | 150 passed, 0 failed | 150 |
| `scripts/test-global-install.sh` | 112 assertions | 112 |
| `scripts/test-access-resolution.sh` | 100 assertions | 100 |
| `scripts/test-front-door-skill.sh` | 78 assertions | 78 |
| `scripts/test-context-optimizer.sh` | 107 checks | 107 |
| `scripts/test-guard.sh` | 116 passed, 0 failed | 116 |
| `scripts/test-release-engine.py` | 31 passed, 0 failed | 31 |
| `scripts/test-access-discovery.py` | 29 passed, 0 failed | 29 |
| `scripts/test-shared-knowledge.py` | 36 passed | 36 |
| `scripts/audit-npm-package.sh` | passed; 14 files; vendored engine byte-identical | pass |
| `scripts/test-private-source.sh` | skipped: the repository is public on purpose | run after tag |

Validator timing, median of 3: 1.17 s against 1.03 s on 1.5.0 (cap 1.5 s). Anchor links checked:
324 on the branch. On a clean export of `7692795` the new check reported exactly the ten dead
anchors the plan listed and no other anchor error.

**Manual install exercise** (local provider, throwaway `HOME`): install `1.5.0` from an export of
`origin/main`; `update` to this tree (`364 files staged`, `current -> versions/1.6.0`); `version`
`1.6.0`, `verify` 0, `doctor` 0; `rollback` -> `1.5.0`, `verify` 0. Installing from the npm tarball
resolves the `v1.6.0` tag, so it runs after tagging (plan Phase 7). The README install transcript
said `164 files staged`; a real install stages 364, so it now says that.

## Budgets

Measured with `wc -c` against `origin/main`; detail in [budgets.md](budgets.md).

| File | Growth | Cap |
| --- | ---: | ---: |
| `skills/software-engineer/SKILL.md` | +1,497 | +1,500 |
| `skills/product-owner/SKILL.md` | +572 | +800 |
| `skills/software-engineer/skills/code-reviewer/SKILL.md` | +377 | +600 |
| handoff template block | +56 | +120 |
| `references/test-driven-mode.md` (new, opt-in only) | 5,517 | 9,000 |
| `references/developer-testing.md` | +906 | +1,200 |
| `references/definition-of-done.md` | +976 | +1,000 |
| `references/evidence-pack.md` | +567 | +1,200 |
| every skill `description` | 0 | 0 |

## Independent review

A fresh-context reviewer that did not write the change worked the plan's R1-R11 checklist and
reproduced every finding: [round 1](review-round-1.md) (1 major, 6 minor, 4 nit, 1 already on
`main`), [round 2](review-round-2.md) (converged; 1 minor introduced by a fix, 1 pre-existing),
[round 3](review-round-3.md) (converged; 2 nits). The major was the anchor checker slugging
headings that contain links differently from GitHub. Remaining nits, accepted: two long-but-legal
lines, and the `regression_red` example command is not re-runnable while its `../red` worktree
exists.

## Not run, and why

- **Model-scored evals.** The five new evals pass the structural runner; scoring them against a
  model was not run for this release. They are the first thing to score in the next eval run.
- **Guard, Tools, Meeting, Access, Shared Knowledge checklist sections:** their trigger files are
  untouched; their suites still ran inside release readiness and passed.
- **Security review:** not required; no authentication, credential, global-state, or
  trust-boundary change.
- **Private-Source Acceptance:** the repository is public on purpose (plan Decisions), so the
  stage is recorded as skipped, as the checklist now says.

## Telemetry

`python3 scripts/telemetry.py report --all` on a fresh base: `total_events: 0`, no skills, no
unknown events. No counter moved, so nothing is concluded from it.
