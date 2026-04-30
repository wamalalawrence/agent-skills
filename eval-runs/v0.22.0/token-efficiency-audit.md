# Token-efficiency audit (v0.22.0)

## Goal

Audit every artifact the agent loads at runtime — `skills/**/SKILL.md`, `docs/*.md`,
`docs/examples/*`, `evals/*`, `eval-runs/*`, `setup.init`, `.env.example`, and
cross-skill references — and confirm the repo is **cheap** to load into context for
real agent invocations. Concretely: no duplicated paragraphs across skills, no
overgrown SKILL.md files that blow the prompt, no dead pointers that send the agent
to fetch a file it does not need, no env vars that look load-bearing but are dead.

## Method

For each scope, count lines, look for repeated paragraphs, verify links resolve, and
check whether the agent actually consumes what is written.

| Scope                                       | Method                                                          |
| ------------------------------------------- | --------------------------------------------------------------- |
| `skills/**/SKILL.md`                        | `wc -l`, repeated-paragraph grep, manual review.                |
| `skills/**/references/*.md`                 | Confirm they are read on demand, not at every invocation.       |
| `docs/*.md`                                 | `wc -l`, cross-link audit via `python3 scripts/validate-repo.py`. |
| `docs/examples/*`                           | One good-shape example per skill, not a contrastive library.    |
| `evals/*`                                   | Scenarios; verbose worked outputs live in `eval-runs/` only.    |
| `eval-runs/v*/`                             | Pinned to release; not loaded on routine invocations.           |
| `setup.init`, `.env.example`                | Audit for dead env vars and env vars the agent cannot read.     |
| Cross-skill references                      | Each skill links shared docs instead of copying their text.     |

## Findings

### Skills (line counts)

```
934 skills/software-engineer/SKILL.md
679 skills/software-engineer/skills/issue-investigator/SKILL.md
635 skills/software-engineer/skills/code-reviewer/SKILL.md
353 skills/product-owner/SKILL.md
338 skills/test-automation-engineer/SKILL.md
333 skills/manual-tester/SKILL.md
```

The three big skills (software-engineer, issue-investigator, code-reviewer) carry the
heaviest workflow weight in the repo and earn their length. The three smaller skills
(product-owner, manual-tester, test-automation-engineer) are already tight; the
v0.22.0 review-loop additions add ~12 lines each, which is a deliberate trade for
correctness that the user explicitly requested.

**Action:** no full rewrite. Repeated environment-mode preamble (~10 lines per skill)
was kept because removing it broke isolated reading of a single SKILL.md outside the
workspace. The canonical full treatment lives in
[`docs/execution-modes.md`](../../docs/execution-modes.md); SKILL.md retains a one-line
summary plus link.

### Cross-skill references

Audit confirmed every markdown link in `SKILL.md` files resolves. The new
[`docs/review-loops.md`](../../docs/review-loops.md) centralises loop-bound rules so
each producer skill can link instead of restating them — net savings will accrue at the
next round of skill edits.

### `COVERAGE_TARGET_PERCENT`

Audit question from the user: *"is the env var COVERAGE_TARGET_PERCENT actually
considered or used?"*

**Answer:** referenced in three places (`software-engineer/SKILL.md`,
`software-engineer/references/sonarqube-checklist.md`,
`software-engineer/references/code-review-checklist.md`) as the literal placeholder
`${COVERAGE_TARGET_PERCENT:-80}`. **No script in this repo substitutes it.** The
agent runtime is expected to have the value in its process environment (most local
agents do, when launched from a workspace where `setup.init` wrote `.env`). When the
agent does not load `.env`, the `:-80` default applies — so the placeholder is never
a hard error, but overriding it only helps when the agent will actually see it.

**Action:** clarified in `.env.example` and in the software-engineer test-coverage
checklist that `COVERAGE_TARGET_PERCENT` is *agent-resolved*, not script-substituted.
This avoids users wasting tokens (and `.env` lines) overriding a value the agent
never reads.

### Docs

```
38  docs/README.md
6   docs/prompts.md          (compatibility redirect)
22  docs/versioning.md
29  docs/known-limitations.md
43  docs/severity-and-confidence.md
44  docs/skill-quality-scorecard.md
46  docs/release-checklist.md
61  docs/requirement-understanding-scorecard.md
82  docs/assistants.md
88  docs/skill-boundaries.md
92  docs/validation.md
106 docs/execution-modes.md
107 docs/output-discipline.md
135 docs/starter-prompts.md
143 docs/quickstart.md
143 docs/skill-source-resolution.md
164 docs/configuration.md
171 docs/skill-performance-review.md
176 docs/installation.md
191 docs/updates.md
204 docs/auth-discovery.md
256 docs/requirement-understanding.md
305 docs/destructive-action-safety.md
```

All under 305 lines. The two largest (`requirement-understanding`,
`destructive-action-safety`) are loaded on cross-reference, not on every invocation,
and earn their size.

**Action:** keep `docs/prompts.md` (one-screen redirect to `starter-prompts.md`) —
removing it would break inbound links from older copies of the README.

### Examples and evals

Each `docs/examples/*.md` shows one good-shape input/output per skill. Verbose
contrastive worked outputs live under `eval-runs/v*/`, which is loaded only when the
user asks for a release-pinned worked example. No restructuring required.

### Anti-patterns deliberately avoided

- We did not extract a shared "preamble" doc and link it from every SKILL.md, because
  the per-skill preamble is what makes a single SKILL.md self-contained for agents
  that load only one skill at a time.
- We did not collapse the four producer-skill review-pass sections into a single doc
  with no skill-side mention, because the review pass needs to be visible in the
  workflow the agent is executing.

## Re-audit triggers

Re-run this audit when:

- A new skill is added.
- Any SKILL.md grows past ~1000 lines.
- The same paragraph appears verbatim in three or more files.
- A new shared doc is added (do skills now over-link to it?).
