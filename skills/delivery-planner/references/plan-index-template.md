# Plan Index Template

The binding shape of `phased-plan/README.md` written by `delivery-planner`
to
`${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills}/<work_key>/phased-plan/README.md`.

The index is the dispatch source: it lists every phase in order with its
state and names the **current dispatch pointer** — the phase the executor
runs next. The per-phase files are still authoritative for the contents of
each phase; the index is the lightweight roll-up the planner regenerates
from them.

The `current_dispatch_pointer` is binding on the executor. The executor must
load the pointed phase's `recommended_owner` skill from the resolved canonical
skill source before doing work. If the owner skill cannot be loaded, the phase
is blocked; the executor must not substitute a generic workflow or another
skill.

The index is not enough on its own. A sibling `../evidence-pack.yml` must
exist and contain the same phase ids under `delivery_plan.phases[]`. Executors
write their continuity checkpoint there before claiming a phase is complete.

Do not invent extra fields. If something is genuinely not applicable, write
`not applicable — <one-line reason>` instead of removing the field.

## File header

```yaml
---
work_key: AUTH-SSO-PARITY        # MUST equal destination.md's work_key
destination_path: ../destination.md
state: active | superseded       # superseded = a fresh plan replaced this one;
                                 # kept on disk so back-references still resolve
created_at: 2026-05-06
updated_at: 2026-05-06           # MUST bump on every regeneration
current_dispatch_pointer: phase-03   # phase id of the next phase to run, or
                                     # null only when readiness_decision is
                                     # NEEDS_CLARIFICATION / NEEDS_EVIDENCE / BLOCKED.
                                     # READY_FOR_DISCOVERY MUST point at the
                                     # discovery phase id, not null.
                                     # READY_FOR_DISPATCH MUST point at the
                                     # first ready phase, not null.
readiness_decision: READY_FOR_DISPATCH   # READY_FOR_DISPATCH | READY_FOR_DISCOVERY |
                                         # NEEDS_CLARIFICATION | NEEDS_EVIDENCE | BLOCKED
last_completed_phase_id: phase-02       # mirror of evidence-pack.yml.delivery_plan
last_completed_at: 2026-05-06T14:00:00Z # mirror of evidence-pack.yml.delivery_plan
last_completed_by: software-engineer    # mirror of evidence-pack.yml.delivery_plan
totals:
  total: 5
  ready: 1
  in_progress: 0
  done: 2
  blocked: 0
  skipped: 0
  provisional: 2
---
```

## Body sections

```markdown
# Phased plan — SSO parity for the example-api login flow

## Inputs for the next agent

A fresh agent given **this README plus the dispatched phase file** must have
enough context to start. Always include this block, regenerate it on every
checkpoint, and use repo-relative paths from this README's location:

- **Destination brief**: `../destination.md` — outcome, success signals,
  scope, non-goals, constraints. Read first.
- **Evidence pack**: `../evidence-pack.yml` — durable continuity record
  including `delivery_plan.phases[]` state, `current_dispatch_pointer`, and
  prior `last_completed_*` mirrors. The dispatch contract.
- **Current phase file**: `phase-<NN>-<slug>.md` (the file matching
  `current_dispatch_pointer`). Each phase file is self-contained so no other
  phase file needs to be read.
- **Recommended owner skill**: load `<skill_source>/<recommended_owner>/SKILL.md`
  from the resolved canonical skill source — see
  [skill-source-resolution.md](../../../docs/skill-source-resolution.md).
  The current owner is named in the phase row below.
- **Optional**: `../repro-recipe.yml` (when bug-flavored) and
  `../definition-of-done.json` (written by `software-engineer` once a Phase 5
  closure runs). Read only if referenced by the dispatched phase.

If any of the above is missing, follow the
[missing evidence-pack recovery rule](../../software-engineer/references/evidence-pack.md)
or stop with `BLOCKED: required input missing` — do not invent context.

## Phases

| ID         | Title                                | Owner skill              | Size | State        | Prereqs |
| ---------- | ------------------------------------ | ------------------------ | ---- | ------------ | ------- |
| phase-01   | Confirm JWT issuer metadata          | issue-investigator       | S    | done         | none    |
| phase-02   | Feature flag scaffolding             | software-engineer        | S    | done         | 01      |
| phase-03   | Dual-write path (legacy + SSO)       | software-engineer        | M    | ready        | 02      |
| phase-04   | Manual cutover validation in staging | manual-tester            | S    | provisional  | 03      |
| phase-05   | Regression test for flag-flip rollback | test-automation-engineer | S    | provisional  | 03      |

## Dependency map

Plain-prose two-to-four-sentence summary of the dependency graph. Example:

> Phase 1 must finish first; it gates phase 2's design choices. Phase 2
> must finish before phase 3. Phases 4 and 5 are parallel-safe with each
> other but both require phase 3 to finish first.

## Dispatch pointer rules (binding)

- `READY_FOR_DISPATCH` → `current_dispatch_pointer` MUST be the phase id
  of the first phase whose state is `ready` and whose prerequisites are
  all `done`. Never `null`.
- In high-confidence plans, phases that are fully specified but wait on prior
  phase completion should still be `ready`; their `prerequisites` gate dispatch.
  Use `provisional` only when the phase needs more discovery or evidence before
  a fresh executor can run it safely.
- `READY_FOR_DISCOVERY` → `current_dispatch_pointer` MUST be the phase id
  of the discovery / spike phase that closes the load-bearing assumptions.
  Never `null`. All later phases stay `provisional` until the discovery
  phase raises understanding-confidence to `high`.
- `NEEDS_CLARIFICATION` / `NEEDS_EVIDENCE` / `BLOCKED` →
  `current_dispatch_pointer` MUST be `null`. The planner has nothing to
  dispatch; the next action is on the user, not on an executor.
```

## Update discipline

- Bump `updated_at:` on every regeneration. The planner regenerates the
  index whenever it runs (re-reads the per-phase files and recomputes
  `totals`, `last_completed_*` mirrors, and `current_dispatch_pointer`).
- **Executors regenerate the index too.** Any skill that completes its
  phase-continuity checkpoint to `evidence-pack.yml` MUST also regenerate
  this README from the updated evidence pack — re-derive the phase table's
  `State` column, refresh the `totals` and `last_completed_*` mirrors,
  recompute `current_dispatch_pointer`, refresh the `Inputs for the next
  agent` section, and bump `updated_at`. Executors MUST NOT add, delete,
  reorder, rename, or resize phases — those are planner-only operations.
  See the
  [phase-continuity checkpoint](../../software-engineer/references/evidence-pack.md#phase-continuity-checkpoint).
- The index is **derived**: never edit it by hand. If the index and a
  per-phase file disagree, the per-phase file wins and the planner
  regenerates the index on its next run.
- When the planner produces a fresh plan after a destination change,
  set `state: superseded` on the old index and write the new one
  alongside the new destination.
- Mark superseded phases `skipped` with a one-line reason in the per-phase
  file rather than deleting the file — downstream skills may still hold
  references to those phase IDs through `evidence-pack.yml.delivery_plan`.
