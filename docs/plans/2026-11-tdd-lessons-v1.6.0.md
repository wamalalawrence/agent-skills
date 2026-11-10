# Plan: v1.6.0 — example-guided and predictive TDD lessons, plus verified flow fixes

Status: **ready for Phase 0** (two decisions for the maintainer, then execution).
Target release: `1.6.0` (minor, additive). Base: `main` at `7692795` (`v1.5.0`).
Written 2026-11-10. Every claim about this repository below was checked against the files at that
commit; the command or file that proves it is cited next to it.

This plan is self-contained. A fresh agent needs this file, the repository, and nothing else.

## Decisions

Recorded 2026-11-10 from the maintainer (Phase 0):

- **F3:** "i temporarily left it as public on purpose, so leave it that way". Apply change H's
  **Public is intended** branch. Do not change repository visibility.
- **O1:** "for npm, when you get to it, you could give me the CLI commands i would login and
  execute". The agent prepares the exact commands; the maintainer runs `npm login`, `npm publish`,
  and any `npm dist-tag` change. Whether `rc` moves is decided by the maintainer at step 6.6.

## Contents

1. [Outcome in one screen](#1-outcome-in-one-screen)
2. [Sources and what they actually say](#2-sources-and-what-they-actually-say)
3. [The gate: each lesson against what agent-skills already does](#3-the-gate-each-lesson-against-what-agent-skills-already-does)
4. [Verified defects in the current flows](#4-verified-defects-in-the-current-flows)
5. [Constraints, budgets, and the frozen contract](#5-constraints-budgets-and-the-frozen-contract)
6. [Change specification](#6-change-specification)
7. [Phases](#7-phases)
8. [Abort and rollback points](#8-abort-and-rollback-points)
9. [Briefs for the dispatched agents](#9-briefs-for-the-dispatched-agents)
10. [Residual risks](#10-residual-risks)

## 1. Outcome in one screen

What ships in `1.6.0`:

| ID | Change | Loaded on the default path? |
| --- | --- | --- |
| A | `product-owner`: every data-dependent rule gets at least one concrete, literal-valued example | yes, about 800 chars |
| B | `software-engineer` 2.4: a completeness counterfactual for catalogue-shaped specs | yes, about 450 chars |
| C | `software-engineer`: an **opt-in** test-driven mode, in a new reference file | pointer only, about 400 chars |
| D | RIGOROUS mutation testing: the profile already promises it, no skill performs it — make one | yes, about 900 chars total |
| E | Bug-fix RED: record the predicted failure before running the test-only commit | yes, about 350 chars |
| F | `validate-repo.py` checks `#fragment` anchors; fix the 10 broken anchors it would find | no (tooling) |
| G | Documentation hygiene: four verified inconsistencies | no |
| H | Repository-visibility wording — **only after the maintainer decides** (Phase 0) | no |

What is deliberately **not** shipped, with the reason, is in [section 3](#3-the-gate-each-lesson-against-what-agent-skills-already-does).
The most important exclusion: the full predictive-TDD loop never becomes the default. The source
lab's own measurement on the same model family this repository targets puts it at roughly 17x the
tokens of plain inline TDD (section 2.3).

Always-loaded growth across the three affected entry points is capped at 2,900 characters
(about 725 tokens, 1.8% of their combined 161,703 characters). No skill `description` changes,
so the per-session skill listing every host loads does not grow at all.

## 2. Sources and what they actually say

### 2.1 The video

`a6HYpocKwXU` on YouTube — an interview (Modern Software Engineering channel) with the two authors
of the "EXACT Coding" workflow. Transcript retrieved 2026-11-10 with `youtube-transcript-api`
(auto-generated English captions, 448 segments, about 16.5 minutes). Concrete techniques stated:

1. **Example-guided development.** TDD reframed as working from concrete examples; agents do better
   with examples than with prose descriptions (00:00-00:48).
2. **Example Mapping first** (rules, concrete examples, questions, out-of-scope stories) as a human
   collaboration step, then the LLM turns it into a **test list** and checks it for missing
   permutations (03:48-05:13). Reported: example mapping raised correctness "60, 70, 80%" over a
   prose description (06:13-06:45).
3. **Shift the thinking left** instead of producing waves of planning markdown, which leads to the
   same "looks good to me" problem as a very large pull request (07:53-08:34).
4. **Test list -> one item at a time through red, green, refactor** (Canon TDD) (04:08-04:30).
5. **Plain "do TDD" is much cheaper in tokens**; the structured workflow wins on longest function,
   cognitive complexity, and mutation score (09:10-10:00).
6. **A separate refactoring sub-agent** helped a lot on older models; on current models the extra
   value is small (11:24-12:14).
7. **Predictive TDD:** before each step, predict the result — will it be red, why, which message —
   to keep the agent aligned with reality. Their explanation of why it works is a hypothesis
   ("we think"), not a measurement (12:14-13:26).
8. **Selectable autonomy level** — stop after every phase, only after refactor, every N tests, or
   fully autonomous; more human attention gave better results for the presenter (13:26-14:44).

### 2.2 The `agentic_coding_lab` skill set — where it was found

Not on this machine: searches of `~` (name and content), Spotlight, and the claude.ai skill list
returned nothing except this session's own transcript. It is the public GitHub repository
`marcoemrich/agentic_coding_lab` (MIT licence), read at commit `ef07f30` (2026-11-01), cloned
read-only into a scratch directory. It contains two kinds of skill:

- **Lab-operation skills** in `.claude/skills/` (`run-rq`, `reanalyze`, `build-overview`,
  `publish-site`, `exact-coding-baseline-export`) — specific to running that lab. Not relevant.
- **The consumable workflow** in `site/.claude/skills/` (skill set version `2026-09-21`):
  `exact-coding`, `exact-coding-isolated-refactor`, `predictive-tdd`, `test-list`,
  `example-mapping`, `red`, `green`, `refactor`, `end-refactor`, the shared
  `exact-coding-shared/human-in-the-loop.md`, and the `agents/refactor.md` sub-agent. This is what
  the video describes, and what this plan draws on.

Techniques in that skill set beyond the video: every example becomes an *inactive* test before any
code; an **independent-dimensions cross-check** with a falsifying counterfactual ("if one listed
entry were removed while its neighbours stayed correct, would a test catch it?"); a valid Red fails
for the predicted *behavioural* reason, not a compile or setup error; a test that already passes on
activation is recorded, never forced to fail; refactoring under the **Four Rules of Simple Design**
with a domain-responsibility review; on a prediction mismatch, stop feature work and explain with
the smallest deterministic check; per-language "stack profiles".

### 2.3 The lab's own data — the numbers this plan's decisions rest on

All from `research/**/findings.md` at the commit above. n = 5 to 15 runs per cell.

| Finding | Source | Result |
| --- | --- | --- |
| Example mapping vs prose | `questions-claude/1.1-prompt-style-correctness` | +48 to +76 pp external correctness on capable models; no effect on a weak model |
| Full PTDD vs minimal inline TDD, Opus 5.5 | `questions-claude/2.4-opus55-current-workflow` | mutation score 0.76 -> 0.94, `cognitive_max` 7.6 -> 2.4, **tokens 1.4 M -> 24.4 M** |
| Isolated refactor sub-agent, Opus 5 | `workflow-dev/1.25-ptdd-refactor-subagent-cross-model` | tokens 21.8 M -> 68.4 M, duration about 4x, mutation 0.94 -> 0.88, 3 of 12 runs hit the time ceiling |
| Seven TDD workflows, Opus 5.5, example-mapped spec | `questions-claude/4.13-tdd-workflow-comparison-opus55` | all reach correctness 0.96-1.00; tokens range 5.3 M to 55.3 M |
| Dimensions cross-check | `questions-claude/4.10-test-list-dimensions-opus-native` | minimum correctness 0.733 -> 0.933; "costs no efficiency" (F-4.10.2) |
| Predictions in isolation | all 73 RQ `question:` lines searched | **no RQ isolates the effect of predictions**; F-1.26.6 says the prediction pair is not measurable on the Claude Code arm |

Two conclusions follow, and the plan is built on them. First, the cheap, high-yield lever is the
*input*: concrete examples and a completeness check. Second, the full loop buys real test-suite
quality at an order-of-magnitude token cost, so in a token-conscious repository it can only be
something the user asks for.

## 3. The gate: each lesson against what agent-skills already does

Decision key: **KEEP** (ships, scoped as stated), **NARROW** (ships in a reduced form), **DROP**.

Each entry: **lesson — decision.** *Covered by:* what already exists. *Gap and value:* why it
ships or not.

**Kept or narrowed (ships)**

- **L1 Concrete, literal-valued examples per rule — KEEP, change A.** *Covered by:*
  `skills/product-owner/SKILL.md:243-255` (observable ACs, optional Given/When/Then, one negative
  criterion) and `docs/requirement-understanding.md:78-86`. *Gap:* nothing asks for literal
  input -> output values, which is the lever measured at +48 to +76 pp. Costs a few hundred chars.
- **L2a Completeness counterfactual over independent dimensions — KEEP, change B.** *Covered by:*
  nothing equivalent. *Gap:* measured as cheap and tail-reducing (F-4.10.2).
- **L8 Mutation score as a test-quality signal — KEEP, change D.** *Covered by:*
  `scripts/execution-profile.py:110` sets `mutation_testing: True` for RIGOROUS and
  `docs/adaptive-execution.md:40,55` documents it. *Gap:* no skill performs or reads it (defect F2).
- **L2 Complete test list before code, simple to complex — NARROW, inside change C only.**
  *Covered by:* `skills/software-engineer/SKILL.md:617-651` (six test-design decisions),
  `skills/test-automation-engineer/SKILL.md:407-418` (coverage map, traceability). *Gap:* the
  inactive-test list only pays off inside a TDD loop.
- **L3 Predict before every deterministic check — NARROW, change E plus change C.** *Covered by:*
  `docs/evidence-discipline.md:49-66` (RED must fail for the right reason, bug fixes) and
  `docs/requirement-understanding.md:133-141` (disconfirming checks). *Gap:* no isolated evidence,
  and a prediction per check is output on every check. So: one prediction at the existing RED gate
  for everyone; per-check predictions only inside the opt-in mode.
- **L4 One behaviour per Red-Green-Refactor cycle, Four Rules refactor — NARROW, opt-in change C.**
  *Covered by:* `skills/software-engineer/SKILL.md:549-571` (SRP, short methods). Two existing rules
  deliberately say the opposite for the default path and stay: `docs/evidence-discipline.md:62-66`
  ("do not demand universal RED-GREEN-REFACTOR") and `code-reviewer/SKILL.md:502-505,857` (do not
  require test-first). *Gap:* real test-quality gain at about 17x tokens.
- **L7 Never manufacture a failure for an already-passing test — NARROW, change C.** *Covered by:*
  the bug-fix gate handles the inverse case (`skills/software-engineer/SKILL.md:540-541`: cannot
  reproduce -> escalate). *Gap:* matters only inside a TDD loop.
- **L9 Novel tasks with hidden acceptance tests — NARROW, eval E2.** *Covered by:* `evals/`,
  `eval-runs/`, `docs/skill-quality-scorecard.md`. *Gap:* building a lab is out of scope; one eval
  with hidden checks for change C is in scope.
- **L13 Domain-responsibility review — NARROW, one line in change C.** *Covered by:*
  `skills/domain-modeler/`, `skills/software-engineer/SKILL.md:553-554`. *Gap:* useful only in a
  refactor step.

**Dropped**

- **L1a Facilitate, do not invent rules or examples.** Covered: `product-owner/SKILL.md:143` stops
  when ACs would need invented facts; `:175-185` gates output on confidence.
- **L1b Red cards (questions) and new-story slicing.** Covered: product-owner scope, out-of-scope,
  open questions, and the Definition of Ready.
- **L5 Isolated refactor sub-agent.** Covered in spirit by the fresh-context reviewer
  (`skills/software-engineer/SKILL.md:663-666`). The lab's own data argues against it: about 3x
  tokens, about 4x duration, lower mutation score, runs hitting the time ceiling.
- **L6 Selectable autonomy levels with per-phase stops.** Covered by the execution profiles
  (`docs/adaptive-execution.md:25-56`), confidence-to-action rules
  (`docs/requirement-understanding.md:180-198`), and the auto-iterate rule
  (`skills/software-engineer/SKILL.md:680-718`), which per-phase stops would contradict. Change C
  keeps exactly two stops: the test list when confidence is below `high`, and an unexplained
  prediction mismatch.
- **L10 Avoid planning-markdown bloat.** Covered: `docs/token-efficiency.md:19-40`,
  `docs/output-discipline.md`.
- **L11 Thinking mode hurts example mapping on some models.** Model- and host-specific; not portable.
- **L12 Per-language stack profiles.** `test-automation-engineer` discovers the stack and
  `software-engineer` follows repository conventions; per-language files would cost maintenance and
  tokens for no portable gain.

## 4. Verified defects in the current flows

Each was reproduced on a clean worktree of `7692795`. "Fix" names the change in section 6.

### F1 — Broken heading anchors, and no check that can see them (fix: change F)

`scripts/validate-repo.py:843-848` strips the `#fragment` before checking a link, so a link to a
real file with a dead anchor passes. The release-readiness link check does the same
(`scripts/test-release-readiness.sh`, the block ending at line 671), and the CI link-check action
passed on `main` with all ten present (`gh run list`: `success`, 2026-09-24). 308 anchor links exist
in tracked Markdown; these 10 are dead:

| File:line | Dead target | Correct target |
| --- | --- | --- |
| `CHANGELOG.md:962` | `ROADMAP.md#before-100` | `ROADMAP.md#previously-v100` |
| `CHANGELOG.md:2413` | `docs/installation.md#upgrading-from-v036x-workspace-installation` | `docs/installation.md#upgrading-from-an-earlier-release` |
| `CHANGELOG.md:2784` | link text `#1` whose target is a bare `#` (empty fragment) | plain text `#1`, no link |
| `docs/execution-modes.md:79` | `installation.md#upgrading-from-v036x-workspace-installation` | `installation.md#upgrading-from-an-earlier-release` |
| `docs/quickstart.md:94` | same | same |
| `docs/release-checklist.md:125` | `versioning.md#contracts-under-consideration-for-a-10-freeze` | `one-point-oh.md` |
| `docs/security-review-v0.44.0.md:169` | same | `versioning.md#the-10-contract` |
| `eval-runs/v1.0.0-rc.2/summary.md:352` | `../../ROADMAP.md#before-100` | `../../ROADMAP.md#previously-v100` |
| `eval-runs/v1.0.0-rc.3/summary.md:185` | same | same |
| `skills/software-engineer/references/evidence-pack.md:311` | `#evidence-packymldelivery_plan-ownership-rule` (a bold paragraph at line 437) | see note below |

The last one was found in `v0.39.0` and deliberately deferred (`eval-runs/v0.39.0/summary.md:124-127`).
Note for the last row: add `<a id="delivery-plan-ownership-rule"></a>` on its own line above line 437
and point the link at `#delivery-plan-ownership-rule`. `docs/quickstart.md:94` is on the first-run path for anyone upgrading. Before editing each row,
the implementer confirms the replacement heading still covers what the sentence refers to.

### F2 — RIGOROUS promises mutation testing that no skill performs (fix: change D)

`scripts/execution-profile.py:92,101,110` and `docs/adaptive-execution.md:40,55` state that
RIGOROUS work gets mutation testing. `grep -rni "mutation[_ ]test\|mutant\|RIGOROUS"` over
`skills/software-engineer`, `skills/software-engineer/skills/code-reviewer`, and
`skills/test-automation-engineer` finds no instruction to run it, record it, or review it. The
executor's brief says only "At RIGOROUS: full evidence and review discipline, unchanged"
(`skills/wamala/references/handoff-prompt-template.md`, "Match the workflow depth" bullet). A
security or migration change therefore ships believed to have had a check it never got.

### F3 — The repository is public; its documents say it is private (fix: change H, after Phase 0)

`gh repo view wamalalawrence/agent-skills --json visibility` returns `PUBLIC`. These say private:
`README.md:7` ("stable, private"), `CONTRIBUTING.md:3`, `ROADMAP.md:3`, `CHANGELOG.md:1196,1272`,
`docs/release-providers.md:198-211`, and `docs/release-checklist.md` "Private-Source Acceptance".
`scripts/test-private-source.sh:205-212` exits `2` on a public repository, so that checklist stage
cannot run, and `scripts/test-private-source.sh:6` calls it a precondition for every release. The
commercial plan with pricing (`docs/commercial-roadmap.md`) is readable by anyone.

What is not known: whether the change was intended. No `PublicEvent` appears in the repository's
event history (the API keeps about 90 days). `ROADMAP.md:18-20` promises 1.x "its current
credential-free install path", which a public repository provides and a private one does not, so a
deliberate change is plausible. That is why this is a decision, not a fix.

### F4 — README skill count contradicts itself

`README.md:45` says "the eleven skills"; the table at `README.md:251-262` lists twelve, and
`README.md:414` says "the twelve specialist skills". Fix: "the twelve skills" (change G).

### F5 — Literal escape sequences instead of characters

`skills/software-engineer/SKILL.md:764` contains the six characters `→` twice instead of an
arrow; it renders as text on every load of the skill. `CHANGELOG.md:3637-3638` has `—`. Fix:
the real characters; both files already use non-ASCII (change G).

### F6 — Stale status text

`docs/versioning.md:95-96` still says "Until `v1.0.0`, pin the repository version". `ROADMAP.md:22`
is headed "Now: v1.1.0" while `VERSION` is `1.5.0`. Fix in change G.

### O1 — Observation, consequence not verified

`npm view @wamalalawrence/agent-skills dist-tags` returns `{ rc: '1.0.0-rc.4', latest: '1.5.0' }`.
`CHANGELOG.md:1185` once documented `npx @wamalalawrence/agent-skills@rc install --channel rc`.
Current docs do not, and what the `rc.4` bootstrap does today was not run, so this is recorded,
not claimed as a defect. Phase 6 decides it (step 6.6).

### Operational note, not a defect

`python3 scripts/validate-repo.py` scans the working tree, so untracked files fail it: on this
checkout it exits `1` because of four untracked `*-prompt.md` files at the root that belong to the
maintainer. In a clean worktree it exits `0` with 84 warnings, matching
`eval-runs/v1.5.0/summary.md`. Every gate in this plan runs in a clean worktree, as 1.5.0's did.
Those four files are never staged, moved, or deleted.

## 5. Constraints, budgets, and the frozen contract

### 5.1 The 1.x contract — must be byte-for-byte unaffected

From `docs/one-point-oh.md` and `docs/versioning.md`. The reviewer checks each line.

- CLI command and subcommand names, flags, and `--json` shapes: no change. No new command.
- Exit codes (`lib/asrelease/exits.py`, the subsystem table, `dod-check` 0/1/2): no change.
- Install layout and semantics (`AGENT_SKILLS_HOME`, `current`, `versions/`, `install.json`): no change.
- Release-provider interface (`lib/asrelease/providers/`): untouched.
- Skill names: the same twelve; no skill directory added, renamed, or removed.
- Engineering Tool Capability Framework (`lib/tools/`, `scripts/tools.py`): untouched.
- npm lockstep: `npm/package.json` version == `VERSION` == tag == payload manifest.
- `dod-check`: a `definition-of-done.json` that verifies under 1.5.0 verifies under 1.6.0. New DoD
  fields are optional; `scripts/dod-check.py` is not changed (it already ignores unknown fields,
  `scripts/dod-check.py:106-165`).
- Safety floor, `ALWAYS_REQUIRED` invariants, escalation table, redaction: untouched.

Versioning: everything above is additive -> **minor**, `1.5.0 -> 1.6.0`. `validate-repo.py`
becoming stricter is not a contract change: `scripts/` invoked directly is "Not frozen"
(`docs/one-point-oh.md`, section "Not frozen").

### 5.2 Paths

Allowed to change: the files named in section 6, `CHANGELOG.md`, new files under `evals/` and
`eval-runs/v1.6.0/`, this plan, and — in Phase 4 only — the version files.
Amended after review round 1 (change H completeness): `SECURITY.md` line 3, and the header comment
only (lines 1-15, no logic) of `scripts/test-private-source.sh`. After round 2: the outer fence
(lines 74 and 189) of `skills/delivery-planner/references/phase-template.md`. Must not change:
`lib/`, `bin/`, `hooks/`, `npm/` (until Phase 4), `scripts/install.py`, `scripts/guard*`,
`scripts/execution-profile.py`, `scripts/dod-check.py`, any skill's frontmatter `description`. A
diff outside the allowed set is a review blocker unless this plan is amended first.

### 5.3 Token budgets (measured with `wc -c`, never estimated)

| File | Baseline chars | Max growth | Loaded |
| --- | ---: | ---: | --- |
| `skills/software-engineer/SKILL.md` | 81,672 | +1,500 | every software-engineer run |
| `skills/product-owner/SKILL.md` | 26,696 | +800 | every product-owner run |
| `skills/software-engineer/skills/code-reviewer/SKILL.md` | 53,335 | +600 | every review |
| `skills/wamala/references/handoff-prompt-template.md` (template block only) | — | +120 | every brief |
| `skills/software-engineer/references/test-driven-mode.md` (new) | 0 | <= 9,000 | only on opt-in |
| `skills/software-engineer/references/developer-testing.md` | 17,955 | +1,200 | on demand |
| `skills/software-engineer/references/definition-of-done.md` | 11,559 | +1,000 | on demand |
| `skills/software-engineer/references/evidence-pack.md` | 26,006 | +1,200 | on demand |
| Every skill's frontmatter `description` | — | **0** | every host session |

Why the cap matters: `ROADMAP.md` ("Entry-point size") already names `software-engineer` at 1,300
lines as a cost. New detail goes into references; `SKILL.md` gets pointers and one-line rules.

### 5.4 Performance

`python3 scripts/validate-repo.py` takes 0.97-1.03 s (3 runs, Python 3.9.6, clean worktree). With
the anchor check it must stay under 1.5 s, median of 3. Slugs are computed once per target file
and cached. No other runtime code changes, so no other timing budget applies.

### 5.5 Portability and provenance

No company names, hostnames, tokens, repository names, or local paths in any `SKILL.md` or
reference file (`README.md`, "Design Principles"). Techniques are named by technique — Example
Mapping, test list, Four Rules of Simple Design — not by the people or employer behind the source.
**No sentence is copied from the MIT-licensed source**; all wording is new. Credit goes in the
`CHANGELOG.md` entry, as one line naming the public lab repository. Copying any text would require
carrying the MIT notice, which is why the rule is "write it fresh".

## 6. Change specification

Line numbers are at `7692795`. Wording in quotes is the intended meaning; the implementer may
tighten it but must not widen it.

### A. Concrete examples per rule — `product-owner`

1. `skills/product-owner/SKILL.md`, step 5 (lines 243-255), add after the negative-criterion
   bullet: "For every rule whose outcome depends on data — a calculation, threshold, mapping,
   eligibility, or state transition — give at least one concrete example with literal values
   (`given <input>, <action> -> <exact outcome>`), plus one at each boundary the rule names. Put
   examples as sub-bullets under the criterion they illustrate. If the values are not known, the
   rule is an open question: ask, do not invent. These examples become the engineer's test cases."
2. Definition of Ready (around line 446): one checkbox — "Every data-dependent rule has at least one
   literal-valued example, or is listed as an open question."
3. No template or output-section change: examples nest under ACs, so empty sections never appear.

### B. Completeness counterfactual — `software-engineer` 2.4

1. `skills/software-engineer/SKILL.md`, after the six decisions in 2.4 (line 637 area), one
   sentence: "When the specification carries a catalogue, table, mapping, or rules that repeat
   across variants and operations, apply the completeness counterfactual in
   developer testing" — linked as `./references/developer-testing.md`.
2. `skills/software-engineer/references/developer-testing.md`: new section "Completeness: the
   counterfactual check" (<= 1,200 chars): name the independent dimensions (operation, variant,
   input category, policy attribute, state, observable result); for each explicitly specified
   entry ask "if this one entry were removed or changed while its neighbours stayed correct, would
   a test fail?"; add a discriminating test per cell that can drift independently; a representative
   test is enough where one uniform rule governs several values; never build a mechanical
   Cartesian product.

### C. Opt-in test-driven mode — new reference, pointer in `software-engineer`

1. Pointer in `skills/software-engineer/SKILL.md` at the top of Phase 2 (<= 400 chars):
   "**Test-driven mode is opt-in.** Enter it only when the user or the dispatch brief explicitly
   asks for TDD or test-first work; then run Phase 2 per `references/test-driven-mode.md`.
   It costs several times the tokens of the default path. Never enter it on your own judgement or
   because of the execution profile."
2. New `skills/software-engineer/references/test-driven-mode.md` (<= 9,000 chars), sections:
   - **When it applies and what it costs.** Explicit request only. Says plainly that published
     measurements put a full predictive loop at roughly an order of magnitude more tokens than
     unstructured TDD, for markedly stronger tests (no source names, no hostnames).
   - **Test list.** From the acceptance criteria and their examples (change A): one inactive test
     per example using the project's own skip or todo mechanism; ordered simplest first, then
     single rules, modifiers, combinations, multi-step scenarios; apply the completeness
     counterfactual (change B); predict and confirm the suite stays green with the list inactive.
     Show the list and wait **only** when requirement-understanding confidence is below `high`.
   - **One cycle per behaviour.** Activate one test. One-line prediction (expected outcome, failure
     category, message or value). Run the narrowest test. Red counts only if it fails for the
     predicted behavioural reason; a load or compile failure gets the minimum scaffold and a new
     prediction. Already passing: record it, change nothing, never force a failure. Green: the
     smallest change; predict and run the focused test. Refactor while green under the Four Rules
     in order (passes tests, reveals intention, no duplicated knowledge, fewest elements), naming
     from the domain glossary when one exists; one refactoring at a time, each followed by the
     smallest relevant check; undo a refactoring that does not make intent clearer. No separate
     refactoring agent.
   - **Prediction mismatch.** Stop feature work, keep both outcomes, explain with the smallest
     deterministic check. Never change production behaviour to make an unexplained failure go
     away. Unexplained after two checks -> stop and surface (`needs-user`). The bound is the point.
   - **Suite cadence.** The full suite at the end of each cycle when it runs in under about a
     minute; otherwise at least every third cycle, and always before Phase 3.
   - **How it fits the rest.** A bug fix keeps 1.5 first: the regression test is list item one.
     The inner and outer `code-reviewer` loops run once after the cycles, never per cycle. The
     cycle log goes to the evidence pack, one line per cycle, not into chat.
3. `skills/software-engineer/references/evidence-pack.md`: optional `tdd` block — `test_list`
   (ordered ids and descriptions) and `cycles` (id, predicted, actual, green change or
   `already-passing`, refactor kept or undone). Absent unless the mode ran.
4. `skills/software-engineer/skills/code-reviewer/SKILL.md`, next to lines 502-505 (<= 250 chars):
   "When the evidence pack has a `tdd` block, check the test list against the acceptance examples
   for omissions. Judge the result, not the method." The existing "do not require test-first"
   rules stay word for word.
5. `skills/wamala/references/handoff-prompt-template.md`, field notes (outside the template block,
   so no brief grows): a one-line summary of the request must keep any working method the user
   named, such as test-first.

### D. RIGOROUS mutation testing — fixes F2

1. `skills/software-engineer/SKILL.md` 3.2, one checkbox (<= 600 chars): "At execution profile
   `RIGOROUS`, run the project's own mutation-testing tool scoped to the changed code. Installing
   one is a dependency decision for the user, not for you. Record it as `checks.mutation` in the
   Definition of Done. A mutant that survives on a changed line is a missing assertion: add it or
   say why not. With no tool configured, record `not_run` with that reason and say so in the PR.
   Never report the RIGOROUS requirement as met without a run."
2. `skills/software-engineer/references/definition-of-done.md`: document optional
   `checks.mutation` — `result`, `command`, `revision`, `exit_code`, `killed`, `total`,
   `survived_on_changed_lines`, `reason` — and state that `dod-check` does not require it in 1.6.0.
3. `skills/software-engineer/skills/code-reviewer/SKILL.md`, test-verification area (<= 350 chars):
   "At `RIGOROUS`, a missing `checks.mutation`, or a `not_run` without a reason, is a `major`
   finding. Survivors on changed lines need an added assertion or a stated reason."
4. Handoff template block, the "Match the workflow depth" bullet: append "including mutation
   testing (`software-engineer` 3.2)" (<= 120 chars).
5. `docs/adaptive-execution.md`, the "Mutation testing" row and the RIGOROUS paragraph: link to
   `software-engineer` 3.2 for what it means.
6. A consumer probe so this cannot drift again: a check in `scripts/test-adaptive-execution.sh`
   that `skills/software-engineer/SKILL.md` and the code-reviewer `SKILL.md` both still name
   `checks.mutation`, plus a probe proving the check fails when the line is deleted from a
   sandboxed copy. Touching that suite brings the "Adaptive Execution" section of the release
   checklist into scope.

### E. Predicted RED at the existing bug-fix gate

1. `skills/software-engineer/SKILL.md` 1.5 (line 531 bullet, <= 350 chars): before running the
   test-only commit, write the assertion expected to fail and why; record it as
   `checks.regression_red.predicted`. When the actual failure differs, investigate before writing
   the fix — a different failure is not yet RED.
2. `skills/software-engineer/references/definition-of-done.md`: document the optional `predicted`
   field. `dod-check` still requires only `assertion`.
3. `docs/evidence-discipline.md` "RED means..." section: one sentence pointing at the predicted
   field.

### F. Anchor validation — fixes F1

1. `scripts/validate-repo.py`: in `check_internal_links`, for a relative `.md` target, or a
   same-file `#fragment`, with a non-empty fragment, report an **error** when the fragment is not a
   heading slug of the target (or an explicit `<a id>` / `<a name>`). A bare `#` target is also
   an error. Slugs follow GitHub's rules: lowercase; drop inline Markdown (link text kept,
   backticks removed, contents kept); drop every character that is not a letter, digit, space,
   `-`, or `_` (Unicode-aware); spaces become `-`; repeated headings get `-1`, `-2`. Headings inside
   fenced code blocks are not headings, and a link inside an inline code span is not a link. Cache
   slugs per file.
2. Regression oracle: on a clean worktree of `7692795` the new check reports **exactly** the ten
   links in F1 and nothing else. Any other hit is a slug-rule bug (fix the rule), not a link to
   "fix". Record the count of anchor links checked (308 expected, give or take changes).
3. Fix the ten links as tabled in F1.
4. Tests: a new `scripts/test-validate-links.py`, stdlib only, offline. Cases: punctuation
   (`### 1.5 Reproduce-before-fix gate (bug fixes only)` ->
   `15-reproduce-before-fix-gate-bug-fixes-only`), duplicate headings, a code span in a heading,
   an emoji heading, a fenced-code fake heading, an explicit `<a id>`, an empty fragment, a missing
   anchor. Plus a probe: with the fragment check disabled in a sandboxed copy, the missing-anchor
   case must pass, proving the test exercises the check. Wire it into `.github/workflows/ci.yml`
   (beside "Validate repository structure and skills") and `scripts/test-release-readiness.sh`
   section 3.

### G. Documentation hygiene — fixes F4, F5, F6

- `README.md:45`: "the eleven skills" -> "the twelve skills".
- `skills/software-engineer/SKILL.md:764`: `→` -> the arrow character. `CHANGELOG.md:3637-3638`:
  `—` -> the em dash character.
- `docs/versioning.md:95-96`: replace with "Pin a release tag when you need repeatable behaviour
  across teams or automation."
- `ROADMAP.md`: the "Now" section names `v1.6.0` in three sentences; the `v1.1.0` paragraph moves
  under "Previously". Keep the commercial and 1.x sections as they are.

### H. Visibility wording — fixes F3, only per the Phase 0 answer

- **Public is intended:** `README.md:7` drops "private"; `CONTRIBUTING.md`, `ROADMAP.md:3` say
  "solo-maintained, not open to outside contribution" instead of "private"; the checklist's
  "Private-Source Acceptance" says it applies only while the repository is private and is skipped
  and recorded when it is public. `LICENSE` stays proprietary — public source is not open source.
  `scripts/test-private-source.sh` stays as it is. The commercial plan's exposure is the
  maintainer's call; this plan does not move it.
- **Private is intended:** the maintainer changes visibility (a GitHub setting, never an agent).
  `README.md` "No clone, no per-repository step, no credentials" then gains "it uses your existing
  git authentication", because a private source returns exit `3` without it. Stage B runs after
  the tag in Phase 6.
- **No answer:** change nothing in H. The `1.6.0` changelog records the mismatch as outstanding.

## 7. Phases

Every phase runs in a clean `git worktree`. The four untracked root files are never touched.

### Phase 0 — Preflight and decisions

- **Inputs:** this plan; `main` at `7692795`.
- **Actions:** (1) confirm `git fetch && git status -sb` shows `main` equal to `origin/main`;
  (2) ask the maintainer two questions: F3 — public intended, private intended, or defer; O1 —
  move npm `rc` to `1.6.0` at publish, leave it, or decide later; (3) record the answers at the
  top of this file under "Decisions".
- **Artifacts:** "Decisions" block in this file.
- **Verification:** both answers recorded verbatim (or "defer").
- **Done:** answers recorded. Nothing else waits on them except change H and step 6.6.

### Phase 1 — Implementation (dispatched implementer agent)

- **Inputs:** this plan; the Phase 0 decisions; brief 9.1.
- **Actions:** `git worktree add ../agent-skills-1.6.0 -b feature/tdd-lessons-1.6.0 origin/main`.
  Use the repository's own `software-engineer` workflow (lifecycle wrappers, 5-line plan, inner and
  outer review). Implement F first (it protects every later link), then G, D, E, A, B, C, H.
  Add the four evals in 7.1. Update `CHANGELOG.md` under `## Unreleased`. Do not bump versions.
- **Artifacts:** branch commits (one per change letter); `evals/` additions; the evidence pack and
  `definition-of-done.json` under the task cache; `eval-runs/v1.6.0/budgets.md` with before/after
  `wc -c` for every file in 5.3 and the validator timing.
- **Verification:** `python3 scripts/validate-repo.py` exit `0`, warnings <= 84 (any increase
  accounted for by category); `python3 scripts/run-evals.py` and `--strict-sections` 0 failures;
  `python3 scripts/test-validate-links.py` passes and its probe reports the weakened build failing;
  `bash scripts/test-adaptive-execution.sh` passes with the new probe; the F1 oracle (exactly ten
  hits on the base, zero on the branch); every budget in 5.3 met; validator median < 1.5 s;
  `git diff --name-only origin/main...` is inside 5.2; `agent-skills dod-check` passes on the
  task's DoD.
- **Done:** all of the above green and pushed to the feature branch; a draft PR opened; no merge.

#### 7.1 Evals to add (existing format, `scripts/run-evals.py` rules)

- `evals/product-owner-examples-per-rule.md` (`product-owner`): each data rule gets literal and
  boundary examples; an unknown value becomes an open question, never an invented number.
- `evals/software-engineer-test-driven-mode-opt-in.md` (`software-engineer`): (a) "use TDD" gives
  a test list first, one-line predictions, one behaviour per cycle, and records an already-passing
  test; (b) no TDD request keeps the default path with no test-list ceremony; (c) a RIGOROUS
  profile alone does **not** enter the mode.
- `evals/software-engineer-rigorous-mutation-testing.md` (`software-engineer`, `code-reviewer`):
  with a tool configured, a scoped run lands in `checks.mutation`; with none, `not_run` with a
  reason, nothing installed, and the PR says so; the reviewer raises `major` on a silent omission.
- `evals/developer-testing-completeness-counterfactual.md` (`software-engineer`): a catalogue spec
  (for example four tiers by three operations, one tier with its own rate) gets discriminating
  tests per independently drifting cell, not a full cross product.

Scenario (a) of the second eval includes hidden acceptance checks the agent is not shown (L9).

### Phase 2 — Independent review (a separate, fresh-context subagent)

- **Inputs:** the branch diff (`git diff origin/main...HEAD`), sections 5 and 6 of this plan,
  brief 9.2. **Not** the implementer's reasoning, chat, or self-review — independence is the point.
- **Checklist** (each item: pass, or a finding with severity per `docs/severity-and-confidence.md`):
  - R1 Contract: every 5.1 line holds; `lib/`, `bin/`, `hooks/`, `npm/`, frontmatter
    `description`s untouched; exit codes unchanged (`python3 scripts/test-release-engine.py`).
  - R2 Scope: every changed path is in 5.2.
  - R3 Budgets: re-measure 5.3 yourself with `wc -c`; do not trust `budgets.md`.
  - R4 Opt-in: no path enters test-driven mode without an explicit request — not the profile, not
    Wamala, not agent judgement. Read every sentence that mentions the mode.
  - R5 Consistency: `docs/evidence-discipline.md` still says not to demand universal
    RED-GREEN-REFACTOR; the code-reviewer "do not require test-first" lines are unchanged; review
    loop bounds in `docs/review-loops.md` unchanged; the mode's stops do not contradict 2.5's
    auto-iterate rule.
  - R6 Portability and provenance: no company, host, path, or token in skill files; pick five
    distinctive sentences from the new reference and confirm none appears in the source skill set.
  - R7 Mutation testing: never installs a tool; `not_run` is honest; a 1.5.0-shaped DoD still
    passes `agent-skills dod-check` (build one by hand, do not infer it).
  - R8 Anchor checker: on the base worktree it reports exactly the F1 ten; the probe fails when the
    check is removed; median runtime < 1.5 s; no false positive on emoji or code-span headings.
  - R9 Docs: links, 200-char line limit, `CHANGELOG.md` under `Unreleased`, README renders.
  - R10 Evals: each new behaviour has one; strict sections pass; run the four new evals and
    `developer-testing-*`, `code-reviewer-test-verification-quality` with the scorecard; a
    criterion below 2, or lower than the last recorded run, is a finding.
  - R11 Safety floor, secret boundary, destructive-action policy: untouched.
- **Artifacts:** `eval-runs/v1.6.0/review-round-<n>.md` — each finding with file:line, severity,
  a reproduction command, and whether it reproduced. A finding that does not reproduce is a
  hypothesis and is labelled so.
- **Verification:** every checklist item has a recorded result.
- **Done:** report written; the loop decision is `converged` (no `blocker`/`major`) or `continue`.

### Phase 3 — Fix loop (bounded)

- **Inputs:** the review report.
- **Actions:** the implementer reproduces each accepted finding, adds a regression test that fails
  on the pre-fix code where the finding is testable, fixes it, and re-runs the full Phase 1
  verification. The reviewer re-runs on the delta only, then confirms the whole checklist once more
  before declaring convergence.
- **Exit criteria:**
  - **Converged:** zero `blocker` and `major`; every Phase 1 check green again. `minor`/`nit` go
    into the PR description as notes.
  - **Bound:** at most 3 rounds (`CODE_REVIEWER_MAX_ROUNDS` default). From round 2 the
    blocker+major count must strictly fall, and the same finding may not recur twice.
  - **Not converging** or **max rounds** -> abort point A2.
- **Artifacts:** `review-round-<n>.md` per round; fix commits.
- **Done:** converged, recorded in `eval-runs/v1.6.0/summary.md`.

### Phase 4 — Version bump

- **Inputs:** converged branch.
- **Actions:** one commit `release: 1.6.0`, matching `346d063` (the 1.5.0 bump): `VERSION`;
  `npm/package.json` `version`; `metadata.version` in all 12 `SKILL.md` files (the validator
  requires each to equal `VERSION`); `README.md` status line and the install transcript
  (lines 7-9, 107-118); `docs/versioning.md:3`. Move `## Unreleased` to
  `## 1.6.0 - <title>` with an empty `## Unreleased` above it.
- **Verification:** `AGENT_SKILLS_EXPECTED_VERSION=1.6.0 python3 scripts/validate-repo.py` exit `0`;
  `git grep -n '1\.5\.0' -- skills npm VERSION` shows no version pin left behind.
- **Done:** bump committed; nothing else in that commit.

### Phase 5 — Release readiness and certification

- **Inputs:** bumped branch; `docs/release-checklist.md`.
- **Actions (clean worktree):** `bash scripts/test-release-readiness.sh` (exit `0`); the sections
  this release touches — Validation, Adaptive Execution (because of the new probe), Distribution
  and Packaging (lockstep: `bash scripts/audit-npm-package.sh`, read the listing, install **from
  the packed tarball** and run `doctor` and `verify`, exercise update -> break -> rollback by hand),
  Telemetry Review (`python3 scripts/telemetry.py report --all`), Documentation, Deprecations (none
  this release), Release Metadata, Public-Safety, Diff Review (Phase 2 satisfied it). Guard,
  Tools, Meeting, Access, and Shared Knowledge sections are out of scope: their trigger files are
  untouched — say so in the summary. No security review is required (no authentication, credential,
  global-state, or trust-boundary change); record that reason. Private-Source Stage B per Phase 0.
  CI green on the PR.
- **Artifacts:** `eval-runs/v1.6.0/summary.md` in the 1.5.0 shape: what changed; the verification
  table with the 1.5.0 column; warnings delta by category; budgets; validator timing; review
  rounds and findings; telemetry; what was out of scope and why.
- **Verification:** every gate green; nothing asserted without the command that produced it.
- **Done:** summary committed; PR ready for the maintainer.

### Phase 6 — Publish (each outward step needs the maintainer's explicit yes)

1. Maintainer merges the PR into `main` (protected). Re-run `python3 scripts/validate-repo.py` on
   the merge commit.
2. Tag the merge commit `v1.6.0` and push the tag.
3. `gh release create v1.6.0 --title "v1.6.0 — <title>" --notes-file <changelog section>`.
4. `bash scripts/audit-npm-package.sh` one last time against the exact tarball to publish.
5. **The maintainer runs `npm publish`** with that tarball. The registry account needs a one-time
   password (`ROADMAP.md`, "Previously: v1.0.0"); no agent handles it.
6. Per the O1 answer: `npm dist-tag add @wamalalawrence/agent-skills@1.6.0 rc` (maintainer).
7. Stage B, if the repository is private: `bash scripts/test-private-source.sh`, expecting
   `PRIVATE_SOURCE_DISTRIBUTION_READY: YES`.

### Phase 7 — Post-release verification

- In a throwaway `HOME` with no checkout: `npx @wamalalawrence/agent-skills@1.6.0 install`, then
  `agent-skills version` (`1.6.0`), `doctor`, `verify` (exit `0`), `check-updates` ("up to date").
- On a machine on `1.5.0`: `agent-skills update` -> `1.6.0`, `verify`; `agent-skills rollback` ->
  `1.5.0`, `verify`; `update` again.
- `npm view @wamalalawrence/agent-skills version dist-tags` matches the plan.
- **Done:** all green, appended to `eval-runs/v1.6.0/summary.md` in a follow-up PR.

## 8. Abort and rollback points

- **A0 — Phase 0 unanswered.** Proceed with H skipped and O1 deferred; record both in the
  changelog. Nothing is left behind.
- **A1 — a budget, a path rule, or a contract line cannot hold.** Stop and report the conflict;
  amend this plan or drop that change letter. The branch stays unmerged.
- **A2 — review not converging, or 3 rounds reached.** Stop the loop; surface the recurring
  findings and the decision needed. No bump. Branch unmerged, PR left as a draft.
- **A3 — release readiness fails.** Fix it as a Phase 3 round (it counts toward the bound), or
  abort as A2. No tag.
- **A4 — fault found after merge, before the tag.** Revert through a PR with
  `git revert -m 1 <merge-commit>`. No tag; `main` is back to 1.5.0 content.
- **A5 — fault found after the tag, before npm publish.** Do not publish npm; ship `1.6.1`.
  Machines on the `git` provider may already have updated, and `agent-skills rollback` restores
  1.5.0 on them. Deleting a pushed tag or release happens only on the maintainer's explicit yes.
- **A6 — fault found after npm publish.** npm versions are permanent. The maintainer runs
  `npm deprecate @wamalalawrence/agent-skills@1.6.0 "<reason>"` and
  `npm dist-tag add @wamalalawrence/agent-skills@1.5.0 latest`, then `1.6.1` ships. Users run
  `agent-skills rollback`.

## 9. Briefs for the dispatched agents

### 9.1 Implementer

```text
You are implementing docs/plans/2026-11-tdd-lessons-v1.6.0.md, Phase 1, in a fresh worktree on
branch feature/tdd-lessons-1.6.0 from origin/main. Read sections 4, 5, 6, and 7 (Phase 1) in full
before editing. Use the repository's software-engineer workflow, with its lifecycle wrappers.
Implement change letters in this order: F, G, D, E, A, B, C, H (H only as the plan's Decisions
block says). One commit per letter. Stay inside section 5.2's paths and section 5.3's budgets; if
either cannot hold, stop (abort point A1) and report rather than work around it. Write no sentence
copied from the source skill set. Do not bump versions, do not merge, do not tag, do not publish.
Never stage, move, or delete untracked files in the maintainer's checkout. Done means every
Phase 1 verification item is green and recorded in eval-runs/v1.6.0/budgets.md, and a draft PR
exists.
```

### 9.2 Reviewer

```text
You are the independent reviewer for branch feature/tdd-lessons-1.6.0. You did not write it and
have no stake in it being right. Read docs/plans/2026-11-tdd-lessons-v1.6.0.md sections 5 and 6,
then the diff (git diff origin/main...HEAD). Do not read the implementer's notes or chat. Work
through checklist R1-R11 in section 7 (Phase 2). Re-measure every number yourself. Reproduce every
finding before you report it, and say whether it reproduced. Write
eval-runs/v1.6.0/review-round-<n>.md with file:line, severity, and the reproduction command. End
with one line: Loop: converged | continue | not-converging | max-rounds.
```

## 10. Residual risks

- **`dod-check` does not enforce `checks.mutation`.** Requiring it would make a 1.5.0-valid DoD fail
  under 1.6.0. The reviewer enforces it at RIGOROUS instead; enforcing it in `dod-check` waits for a
  decision on whether that counts as additive.
- **Mutation tooling varies by stack.** Where none is configured the honest outcome is `not_run`, so
  RIGOROUS work in such repositories still lacks the check. That is now visible, which it was not.
- **Model-dependent evals can pass for the wrong reason.** The hidden acceptance checks in eval
  E2(a) and the scorecard comparison against the last recorded run are the mitigation, not proof.
- **Lab results are one kata family on a few models.** The plan uses them for direction and cost
  only: the default path changes are cheap; the expensive change is opt-in.
