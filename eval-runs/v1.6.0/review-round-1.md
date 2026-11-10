# v1.6.0 independent review — round 1

Reviewer: fresh-context subagent, no access to implementer notes. Branch
`feature/tdd-lessons-1.6.0` at `fe9ef7a`, diffed against `origin/main` (`7692795`). Every number
below was re-measured; `budgets.md` was read only at the end, and its numbers agree with these.
Scratch: `<session scratchpad>/review`
(`$R` below). Python 3.9.6.

Summary: 1 major, 6 minor, 4 nit, 1 pre-existing observation. Model-scored evals were not run.

## R1 Contract — pass

- `git diff --quiet origin/main...HEAD -- VERSION npm lib bin hooks` → no change. `VERSION` is `1.5.0`.
- `scripts/install.py`, `scripts/guard*`, `scripts/execution-profile.py`, `scripts/dod-check.py`: unchanged.
- No skill frontmatter `name`/`description` line in the diff; no skill directory added or removed.
- `python3 scripts/test-release-engine.py` → `31 passed, 0 failed`, exit 0.

## R2 Scope — pass

All 33 changed paths are in 5.2: files named in section 6 (including the F1 table files, `ci.yml`
and `test-release-readiness.sh` from F.4, `docs/evidence-discipline.md` from E.3,
`docs/adaptive-execution.md` from D.5), `CHANGELOG.md`, new `evals/`, `eval-runs/v1.6.0/`, the plan.

## R3 Budgets — pass

`wc -c` against `git show origin/main:<file>`:

| File | Base | Branch | Delta | Cap |
| --- | ---: | ---: | ---: | ---: |
| `software-engineer/SKILL.md` | 81,672 | 83,043 | +1,371 | +1,500 |
| `product-owner/SKILL.md` | 26,696 | 27,268 | +572 | +800 |
| `code-reviewer/SKILL.md` | 53,335 | 53,712 | +377 | +600 |
| handoff template block (lines 18-119) | 5,946 | 6,002 | +56 | +120 |
| `test-driven-mode.md` (new) | 0 | 5,219 | +5,219 | <= 9,000 |
| `developer-testing.md` | 17,955 | 18,861 | +906 | +1,200 |
| `definition-of-done.md` | 11,559 | 12,331 | +772 | +1,000 |
| `evidence-pack.md` | 26,006 | 26,573 | +567 | +1,200 |

Sub-caps (added-line bytes per hunk): C.1 pointer 333 (<= 400), D.1 checkbox 484 (<= 600),
E.1 bullet 250 (<= 350), C.4 reviewer sentence 155 (<= 250), D.3 reviewer bullet 221 (<= 350).
Descriptions: 0.

## R4 Opt-in — pass, two nits

Every branch sentence matching `test-driven|TDD|test-first|red-green` was read
(`git grep -n -i -E "test-driven|\bTDD\b|test-first|red-green|red–green"`). Entry is only on an
explicit user or brief request (`SKILL.md:552-555`, `test-driven-mode.md:9-12`); the profile,
risk, and agent judgement are named as non-triggers; nothing in Wamala, the handoff template, or
`delivery-*` inserts the mode — the template note (`handoff-prompt-template.md:129-130`) only
preserves a method the user named.

- **nit** — trigger vocabulary differs: `SKILL.md:553` says "TDD or test-first";
  `test-driven-mode.md:10` adds "red-green-refactor". Reproduce: the grep above. Reproduced: yes.
- **nit (hypothesis)** — "the dispatch brief explicitly asks" does not say the brief's request must
  trace back to the user, so a planner could in principle write "use TDD" on its own judgement. No
  producer that does so was found. Reproduce: `git grep -n -i tdd -- skills/wamala skills/delivery-*`
  (empty). Reproduced: no — hypothesis.

## R5 Consistency — pass, one minor

- `docs/evidence-discipline.md:69` still says not to demand universal RED–GREEN–REFACTOR; the new
  sentence at 54-56 is scoped to bug-fix RED. Compatible.
- code-reviewer "do not require test-first" lines (`:505-508`, `:863`) unchanged (the diff only adds).
- `docs/review-loops.md` unchanged (`git diff --quiet` → 0).
- 2.5 auto-iterate concerns review rounds; the mode's two pauses do not hand review rounds back.

- **minor** — `skills/software-engineer/references/test-driven-mode.md:73-75`: "This is one of
  exactly two places the mode pauses … Everything else proceeds without asking". That is not true
  inside the mode: gate 1.5's escalation (`SKILL.md:543`, a bug that cannot be reproduced) applies
  to list item one, and dependency and destructive-action confirmations still stop work. Line 4-5
  ("every other … gate … stays as it is") mitigates it, but an absolute "exactly two" invites an
  agent to skip a stop. Suggest "the mode adds two pauses of its own". Reproduce:
  `sed -n 73,75p skills/software-engineer/references/test-driven-mode.md; sed -n 543,544p skills/software-engineer/SKILL.md`.
  Reproduced: yes (text contradiction).

## R6 Portability and provenance — pass

- No host, path, URL, company or person name in new skill text
  (`git diff origin/main...HEAD -- skills | grep '^+' | grep -i -E "https?://|/Use[r]s/|\.com|lab|@"` → only "tokens").
- Five distinctive sentences from `test-driven-mode.md` grepped (`grep -rniF`) in
  `…/scratchpad/src/lab/site/.claude/skills`: "a third guess is where a loop starts to drift",
  "Do not hand it to a separate refactoring agent", "Predict that the suite stays green with the
  whole list inactive", "Undo a step that does not leave the intent clearer", "the trade belongs
  to the user" → 0 hits each. A 6-word shingle comparison of `test-driven-mode.md`,
  `developer-testing.md`, and `product-owner/SKILL.md` against the whole source finds one shared
  shingle, the technique name "the four rules of simple design". The 3-word phrase "smallest
  deterministic check" also occurs in the source (`predictive-tdd/SKILL.md:129`); it comes from the
  plan's own spec and is not a sentence copy.
- CHANGELOG credit names the public lab repository, as 5.5 asks.

## R7 Mutation testing — pass, one minor; one pre-existing observation

- Never installs: `SKILL.md:820` "Adding a tool is the user's dependency decision, never yours";
  `not_run` needs a reason and a PR mention; the reviewer bullet (`code-reviewer/SKILL.md:485-487`)
  makes a missing or reasonless record `major`.
- 1.5.0-shaped DoD hand-built from `origin/main`'s schema (`$R/dod-1.5.0.json`, v2 schema, bug fix,
  all required checks, no `mutation`/`predicted`): `python3 scripts/dod-check.py` → exit 0 on the
  branch, exit 0 with `origin/main`'s `dod-check.py`, and `./bin/agent-skills dod-check` → exit 0.
  Variants with `checks.mutation` `not_run`+reason and `pass`, plus `regression_red.predicted`
  (`$R/dod-1.6.0*.json`) → exit 0. `scripts/dod-check.py` unchanged.

- **minor** — `skills/software-engineer/references/definition-of-done.md:53-55` (schema comment):
  "a fail or not_run needs a waiver below or it blocks verified delivery", while the new optional
  `checks.mutation` (`:235-238`) and the reviewer rule accept `not_run` with a reason and no waiver.
  The reader cannot tell whether an unwaived mutation `not_run` blocks. Say in "Optional fields"
  that `not_run` with a reason needs no waiver. Reproduce:
  `sed -n 53,55p skills/software-engineer/references/definition-of-done.md; sed -n 235,238p …`.
  Reproduced: yes (text).
- **pre-existing, not introduced by this branch (minor)** — the schema example's
  `regression_red` (`definition-of-done.md:104-105`: `revision: fa11ed00`, `exit_code: 1`) is
  rejected by `dod-check` on both base and branch ("claims pass but records exit_code 1", then
  "stale evidence" once exit_code is 0); `dod-check` accepts `regression_red` only with
  `exit_code 0` on `head_sha`. Reproduce: build the documented example and run
  `python3 $R/base/scripts/dod-check.py <file>` → exit 1. Reproduced: yes. Outside 5.2 to fix in
  `dod-check.py`; recorded so it is not lost, since the branch documents `predicted` next to it.

## R8 Anchor checker — findings: 1 major, 1 nit

- Oracle: `git archive origin/main` into `$R/oracle`, branch `scripts/validate-repo.py` dropped
  in, run → exactly the ten F1 anchor errors and no other anchor error (the one other `FAIL` is
  the expected `missing required file: …/test-driven-mode.md`). Fragment links checked: 308 on
  base, 324 on the branch (`$R/probe.py`).
- Probe: `python3 scripts/test-validate-links.py` → `16 passed, 0 failed, probe ok`; the probe
  replaces the check line with `if False:` and the missing-anchor case fails.
- Timing, median of 3: branch 1.16 s (1.20, 1.15, 1.16); base 1.08 s. Under 1.5 s.
- Emoji headings (`🚀 Launch` → `-launch`) and plain code-span headings (`` The `--json` flag ``
  → `the---json-flag`; the 18 `` `x.*` — … `` headings in `engineering-tool-capabilities.md`) are
  slugged correctly.

- **major** — `scripts/validate-repo.py:905-918` (`heading_slug`) with `:879`
  (`INLINE_LINK_TEXT_RE`): a heading that contains a link is slugged wrongly when the link is
  reference-style (`[text][ref]`) or its text holds a code span. The code-span split runs first and
  breaks the inline-link match, and reference links are not handled at all, so the URL or ref
  label is kept in the slug. Twelve README headings have this shape (`README.md:270-392`, e.g.
  ``### [`wamala`][wamala] (top-level)``). GitHub renders that heading's text as
  "wamala (top-level)" (confirmed with `gh api -X POST /markdown -f mode=gfm`), so its anchor is
  `wamala-top-level`; the validator computes `wamalawamala-top-level`. A correct link to any README
  skill section fails CI, and the "fix" the error invites is a link that is dead on GitHub — the
  failure this change exists to prevent. Also a heading of "Read", then a link whose text is the code span `guide` and whose target is
  `g.md`, then "first" →
  `read-the-guidegmd-first` (GitHub: `read-the-guide-first`). Not caught by the oracle because no
  current link targets these headings, and not by `test-validate-links.py`, whose link-in-heading
  case has neither a code span nor a reference link. Reproduce:
  `git archive HEAD | tar -x -C $R/fpbox`; append
  `[a](../README.md#wamala-top-level) [b](../README.md#wamalawamala-top-level)` to
  `docs/quickstart.md`; `python3 scripts/validate-repo.py` → `FAIL … broken anchor … #wamala-top-level`,
  and the wrong slug passes. Also `python3 -I $R/slug.py .`. Reproduced: yes.
- **nit** — `scripts/validate-repo.py:886-902` (`without_fenced_code`): a closing fence is any line
  starting with the opening's first three characters, so a line of three backticks followed by `python` closes a three-backtick fence and a
  heading after it is counted (CommonMark: a closing fence has no info string and is at least as
  long as the opener). Slug edge cases of the same kind: `Tom &amp; Jerry` → `tom-amp-jerry`
  (GitHub `tom--jerry`); `The _private flag` → `the-private-flag` (GitHub keeps `_private`). No
  instance in the repository today (a `git grep` for four-character backtick or tilde openers is empty). Reproduce:
  `python3 -I $R/fence.py .` and `$R/slug.py`. Reproduced: yes.

## R9 Docs — pass, one minor, one nit

- `python3 scripts/validate-repo.py` → exit 0, 84 warnings (unchanged count). No changed `.md`
  line over 200 chars. `CHANGELOG.md` entry is under `## Unreleased` (line 5), above `1.5.0`.
- F1 targets checked against what each sentence means: `ROADMAP.md#previously-v100` covers the
  stable-line npm question; `versioning.md#the-10-contract` lists the capability vocabulary as a
  freeze review target; `one-point-oh.md` holds the frozen list; `#delivery-plan-ownership-rule`
  sits directly above the bold rule; the bare `#1` is now text. All correct.
- H wording: README, CONTRIBUTING, ROADMAP say "solo-maintained … not open to outside
  contribution" consistently; the checklist's Stage B is conditional on private visibility.

- **minor** — visibility wording left inconsistent outside H's file list: `SECURITY.md:3` still
  says "`agent-skills` is private, proprietary software", and `scripts/test-private-source.sh:6-7`
  still calls Stage B "a precondition for every release", contradicting the checklist's new skip
  rule. Both are outside 5.2 (the plan keeps the script as is and never names `SECURITY.md`), so
  the fix needs a plan amendment. Reproduce:
  `sed -n 3p SECURITY.md; sed -n 4-7p scripts/test-private-source.sh`. Reproduced: yes.
- **nit** — three upgrade links (`docs/execution-modes.md:79`, `docs/quickstart.md:94`,
  `CHANGELOG.md:2472`) are about `agent-skills migrate` from the workspace layout; the target section
  covers it, but its subsection `#coming-from-the-pre-v037-workspace-layout` is the exact match.
  Reproduce: `grep -n '^##' docs/installation.md`. Reproduced: yes.

## R10 Evals — structural pass; findings: 2 minor, 1 nit; model scoring not run

- `python3 scripts/run-evals.py` → 66 files, 12 skills, 0 failures, 0 warnings; `--strict-sections`
  → exit 0. `bash scripts/test-adaptive-execution.sh` → 84 passed, 0 failed, including probe 5.
- Bowling hidden checks verified by hand: 150, 267, 30, 90 are correct.
- The scorecard runs of the four new evals plus `developer-testing-*` and
  `code-reviewer-test-verification-quality` were **not run** (no model execution available to the
  reviewer). Required before convergence can be certified.

- **minor** — `evals/developer-testing-completeness-counterfactual.md:26-44`: the expected behaviour
  does not follow from the instruction it tests. `developer-testing.md` asks the counterfactual "for
  each entry the specification states explicitly"; the eval's table states all twelve cells
  explicitly, yet the eval wants one test for "the uniform download rate" and one for `delete`
  across tiers and forbids "twelve price tests". A faithful agent that tests each stated cell fails
  it, and an agent that tests one download case leaves `enterprise` download undetected — the very
  drift the eval punishes for `basic`/`pro`. State the uniform rules as rules in the input ("delete
  is free on every tier", "download is 0.01/GB on every paid tier"), or accept per-cell tests.
  Reproduce: read the eval's table against lines 33-39 and `developer-testing.md:303-305`.
  Reproduced: yes (text).
- **minor** — change E (predicted RED at gate 1.5, `SKILL.md:540-542`) has no eval; `grep -l -i
  predict evals/*.md` finds only the TDD-mode eval, which does not cover the bug-fix gate. R10 asks
  for one per new behaviour. Reproduced: yes.
- **nit** — `evals/software-engineer-test-driven-mode-opt-in.md:70`: the "already-passing test is
  recorded" item depends on the agent's implementation order actually producing one; it should
  read "if a test passes on activation, …" so a run without one is gradable. Also
  `software-engineer-rigorous-mutation-testing.md` has a Must-Not for `STANDARD`/`LIGHT` with no
  scenario that exercises it. Reproduced: yes (text).

## R11 Safety floor, secret boundary, destructive-action policy — pass

No change under `hooks/`, `lib/`, `scripts/guard*`, `docs/destructive-action-safety.md`, or the
destructive-action references; no `ALWAYS_REQUIRED` or redaction change. The only related wording
is the R5 minor above.

## Comparison with `budgets.md` (read last)

Budgets, timings (1.16 s vs its record), 308/324 fragment-link counts, the ten oracle lines, and
suite results agree with this re-measurement.

Loop: continue
