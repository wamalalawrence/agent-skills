# Token Efficiency

`agent-skills` is loaded into agent context at runtime — every line the agent actually reads
during an invocation occupies tokens that compete with the user's prompt and the agent's
working memory. Most files in this repo are **not** auto-loaded; they are read on demand when
the workflow follows a link. This doc captures the principles, the audit methodology, and the
v0.22.0 audit findings.

> **This page is one half of the problem.** It is about the cost of the **instructions**. The
> other half is the cost of the **evidence** — a multi-million-line log, an 800-table schema
> dump, a 40,000-line diff — and that is [Context Optimizer](context-optimizer.md). Trimming a
> SKILL.md by 200 lines is worth doing; it is also worth nothing next to an agent that read a
> 4 MB log wholesale in its first tool call.

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

## v0.41.0: the evidence side

Everything above concerns files this repository controls. v0.41.0 added the capability for files it
does not: [Context Optimizer](context-optimizer.md).

The two are the same principle applied to different inputs, and the second one dominates in
practice. Measured on the release's own fixtures:

| Input | Source chars | Selected chars | Omitted |
| --- | --- | --- | --- |
| 4.7 MB application log | 4,775,858 | 2,043 | 99.96% |
| 484 KB JSON payload | 484,165 | 196 | 99.96% |
| 58 KB / 403-table schema | 57,888 | 649 | 98.88% |
| 35 KB / 63-file diff | 34,681 | 401 | 98.84% |
| 57 KB CI log | 56,732 | 1,205 | 97.88% |

Those are character counts, not cost figures. Token estimates are approximate and provider
tokenisation varies, so no dollar claim is made — see
[the metrics section](context-optimizer.md#metrics) for the defensible version of the claim.

Three principles from this page carry straight over, and one is new:

1. **Persistent artifacts over chat** becomes *pass the pack id, not the pack*. A pack is
   deterministic and cached, so a fresh agent re-reads it instead of the source; pasting it into a
   transcript spends the context it exists to save.
2. **Reference, do not copy** becomes *one shared rule*. Six consumer skills link
   [the large-input rule](context-optimizer.md#the-shared-large-input-rule) rather than restating
   it; a per-skill copy would be six places to drift.
3. **Bounded loops** becomes *bounded budgets*. `--budget-chars` bounds the whole rendered pack,
   and it is enforced rather than advised.
4. **New: correctness beats ratio.** Nothing on this page can be optimised to the point of being
   wrong — a shorter SKILL.md still says what it says. A context pack can be, and a 99.9% reduction
   that removes the root cause is a failure. That asymmetry is why the evidence side needs its own
   evals rather than an audit.

## When to revisit

Re-run this audit at every minor version bump. Specifically:

- After adding a new skill (does it duplicate a shared doc?).
- After adding a new shared doc (do skills now over-link to it?).
- When a skill grows past ~1000 lines (extract `references/`).
- When the same paragraph appears verbatim in three or more files (extract a shared doc).
