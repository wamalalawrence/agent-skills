# Token Efficiency

`agent-skills` is loaded into agent context at runtime — every line the agent actually reads
during an invocation occupies tokens that compete with the user's prompt and the agent's
working memory. Most files in this repo are **not** auto-loaded; they are read on demand when
the workflow follows a link. This doc captures the principles, the audit methodology, and the
v0.22.0 audit findings.

> Note: how much is auto-loaded vs lazy-fetched depends on the host (Claude Code, Cursor,
> Copilot, etc.). The table below describes the **intended** load model the skills are
> written against, not a guarantee about any specific runtime.

## Principles (binding)

These rules apply to all SKILL.md, references, docs, examples, and evals in this repo:

1. **Menu, not checklist.** The Expected Output Contract is a **menu** of available
   sections. Empty sections are dropped, not filled with `none` placeholders. This is
   enforced by [Output Discipline](output-discipline.md).
2. **Persistent artifacts over chat.** Cross-skill handoffs use the
   [evidence-pack](../skills/software-engineer/references/evidence-pack.md) and
   `definition-of-done.json` files, not re-derivation in chat. Re-reading a YAML file is
   ~10× cheaper than reasoning the same context twice.
3. **Reference, do not copy.** Skills reference shared docs
   (`requirement-understanding.md`, `destructive-action-safety.md`,
   `severity-and-confidence.md`, `review-loops.md`) by link rather than copying their text
   into every SKILL.md.
4. **Bounded loops.** Cross-skill review loops are bounded per
   [docs/review-loops.md](review-loops.md). Endless ping-pong burns tokens for no gain.
5. **One-shot examples.** `docs/examples/*` show **one** good-shape input/output per skill.
   They are not exhaustive. Long contrastive "good vs bad" pairs belong in `eval-runs/`,
   not in skills the agent loads on every invocation.
6. **No banner-style headers in skill output.** Skills must not emit "I am now executing
   the X workflow" preamble; that is template echo and is forbidden by Output Discipline.

## What gets loaded vs what gets read on demand

| Loaded when the skill is invoked       | Read on cross-reference                                 | Read only when explicitly needed           |
| -------------------------------------- | ------------------------------------------------------- | ------------------------------------------ |
| The single SKILL.md the agent invoked. | `requirement-understanding.md` (gate runs every time).  | `references/*.md` (checklists, schemas).   |
|                                        | Linked `docs/*.md` cited in the workflow.               | Evidence-pack and DoD JSON during handoff. |
|                                        | `review-loops.md` when a review pass triggers.          | `eval-runs/*` when the user asks for one.  |
|                                        | `destructive-action-safety.md` for any mutating action. |                                            |

Implication: keep **SKILL.md compact and link out**, keep **references/** dense and
schema-shaped, and keep **eval-runs/** verbose and pinned to a release.

## Audit methodology

For each SKILL.md and shared doc:

1. Count repeated paragraphs across files. If the same idea is restated in three skills,
   extract it to a shared doc and link.
2. Strip "and remember to …" recap paragraphs that restate guardrails already in the
   Guardrails section.
3. Replace bullet checklists that exceed ~10 items with a link to a `references/*.md`
   checklist.
4. Verify cross-skill links resolve (use `python3 scripts/validate-repo.py`).
5. Spot-check the per-skill word count against its competitive responsibility — a
   400-line manual-tester skill carrying as much weight as a 900-line software-engineer
   skill is a smell.

## v0.22.0 audit findings

Tracked in [`eval-runs/v0.22.0/token-efficiency-audit.md`](../eval-runs/v0.22.0/token-efficiency-audit.md).
Headlines:

- **Skills (no full rewrite).** Repeated environment-mode preamble (~10 lines per
  skill) was kept because removing it broke isolated reading of a single SKILL.md outside
  the workspace. Pointer to `docs/execution-modes.md` is now the canonical full
  treatment; SKILL.md keeps a one-line summary plus link.
- **Cross-skill review loops.** Centralised in [docs/review-loops.md](review-loops.md);
  every producer skill links instead of duplicating the loop bounds.
- **`COVERAGE_TARGET_PERCENT`.** Clarified in `.env.example` and the software-engineer
  test-coverage checklist that the placeholder is *agent-resolved*, not script-substituted,
  so users do not waste tokens overriding a value the agent never reads.
- **`docs/prompts.md`.** Kept as a one-screen redirect to `starter-prompts.md` — removing
  it would break inbound links from older copies of the README.
- **Examples.** No reduction. Each `docs/examples/*` shows one good-shape output per skill
  and is already lean.
- **Evals.** The `evals/` directory describes scenarios; verbose worked outputs live in
  `eval-runs/`. No structural change required.

## When to revisit

Re-run this audit at every minor version bump. Specifically:

- After adding a new skill (does it duplicate a shared doc?).
- After adding a new shared doc (do skills now over-link to it?).
- When a skill grows past ~1000 lines (extract `references/`).
- When the same paragraph appears verbatim in three or more files (extract a shared doc).
