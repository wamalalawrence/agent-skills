# Phase Template

The binding shape of each `phase-NN-<slug>.md` file under
`${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills}/<issue-key>/phased-plan/`.

Do not invent extra fields. If something is genuinely not applicable, write
`not applicable — <one-line reason>` instead of removing the field. Empty
fields hide assumptions; named-and-empty fields do not.

## File header

```yaml
---
phase_id: 03
slug: failing-regression-test
title: Failing regression test for expired SAML cookie redirect
state: provisional | ready | in-progress | done | skipped | blocked
recommended_owner: software-engineer | product-owner | issue-investigator |
                   manual-tester | test-automation-engineer
size: S | M | L
execution_profile: LIGHT | STANDARD | RIGOROUS
fresh_context_required: true | false
independent_review_required: true | false
expected_effort_minutes: 20
parallel_safe: true | false
parallel_with: []        # phase ids it can run alongside, when parallel_safe
mutation_targets: []     # every path or resource this phase WRITES; an empty
                         # list means "unstated", which is read as "writes
                         # everything" and rules the phase out of any group
prerequisites: [02]      # phase ids that must be complete first
created_at: 2026-05-06
updated_at: 2026-05-06
---
```

### Execution profile

See [adaptive execution](../../../docs/adaptive-execution.md) for the full policy. Choose with
`agent-skills execution-profile` rather than by feel, and record the answer:

- **LIGHT** — a small, independently verifiable, low-risk phase: a documentation fix, a test
  rename, a bounded read-only check. Runs without a fresh-agent handoff or a review agent.
- **STANDARD** — ordinary implementation work. The default, and what an unmarked phase gets.
- **RIGOROUS** — security controls, cryptography, auth, schema migrations, production
  infrastructure, payment correctness, credential handling, anything irreversible or spanning
  systems. Nothing downgrades a phase marked RIGOROUS.

Do not mark a phase LIGHT to make a plan look cheaper. The runner reads this field to decide
whether to skip isolation and review, and the cost of being wrong is paid by whoever inherits
the change.

### `expected_effort_minutes`

What this phase should take, so `agent-skills watchdog` has something to measure against. It is
not a deadline: the watchdog looks for *stagnation*, and a phase still writing milestones past
its budget gets narrowed or split, never killed. An honest number is more useful than a padded
one.

### `mutation_targets`

Every path or resource this phase writes — source files, migrations, generated artifacts, shared
caches. Concurrency eligibility is decided by whether two phases' targets are disjoint.

A phase that omits this field is treated as writing **everything** and will never run alongside
anything. That is the safe default and it is fine to leave it that way; declare targets only
when the phase is genuinely a candidate for parallel execution.

`parallel_with` must be **mutual**. If phase 04 lists 05, phase 05 must list 04. A one-sided
claim means one of the two was written without the other in mind, which is exactly the case that
collides.

## Body sections

```markdown
# Phase 03 — Failing regression test for expired SAML cookie redirect

## Intent

One sentence. The executor's north star for this phase. No "and" without a
justified reason.

## Prerequisites

- Phase IDs that must be complete: `02`.
- Evidence-pack fields that must already be populated:
  `investigation.root_cause_status: suspected|confirmed`,
  `repro_recipe.status: reproduced`.
- External pre-conditions: e.g. "staging has the seeded expired-SAML
  fixture loaded".

If genuinely none, write `none — first phase of the plan`.

## Inputs

Pointers, not pasted content. Examples:

- `evidence-pack.yml` (specifically `acceptance_criteria`, `plan.smallest_change`).
- `repro-recipe.yml`.
- Source files: `src/auth/AuthFilter.java`, `src/auth/__tests__/AuthFilter.test.ts`.
- Ticket: `<issue-key>` and the comments since the most recent investigation.

## Scope

- **In scope.** What this phase changes.
- **Out of scope.** What this phase deliberately does not change, even when
  adjacent or tempting. Mirrors the destination's non-goals at the phase
  level.

## Output contract

What the human on the other end actually needs back, per
[output discipline](../../../docs/output-discipline.md). Distinct from the artifact list
below: the deliverable is not automatically the evidence.

```yaml
output_contract:
  audience: reviewer | engineering meeting | operator | ticket
  primary_question: <the one question this phase answers>
  deliverable: patch | table | short answer | test plan | report
  reading_time_target: under 2 minutes
  evidence_depth: cited-inline | retained-separately | none
  evidence_location: <path, when evidence is kept apart>
```

Omit for an implementation phase whose deliverable is obviously the diff. Include it whenever
the phase produces something a person reads, because that is where the mismatch happens.

## Expected outputs / artifacts

What must exist when the phase is done. Examples:

- Files committed under `<paths>` on a feature branch.
- `evidence-pack.yml.plan.smallest_change` populated.
- `evidence-pack.yml.review.round` advanced.
- `evidence-pack.yml.delivery_plan.phases[<this phase id>]` updated with
  state, completion summary, artifacts, validation, and follow-up context.
- `evidence-pack.yml.delivery_plan.current_dispatch_pointer` advanced to the
  next ready phase, or `null` with a blocker reason.
- Failing-regression-test commit referenced from `repro-recipe.yml`.
- For implementation phases: Definition-of-Done artifact written, branch
  pushed, PR URL recorded, and `code-reviewer` outer-loop convergence reached.
- A passing CI run for `<workflow-name>`.

## Validation / exit criteria

The observable check that says the phase is finished. Examples:

- "The new test fails on the parent commit and passes on the fix commit"
  (verified by `git checkout <parent>` then re-running the test).
- "`mvn -pl auth test` passes locally and in CI."
- "The third acceptance criterion is checked off in the tracker-ready story."
- "`code-reviewer` returns `Loop: converged` for the inner-loop review."
- "`evidence-pack.yml` was re-read after the phase checkpoint write and now
  names the completed phase plus the next dispatch pointer."
- "For a code-delivery phase, the remote branch is pushed and the PR URL is
  present in `definition-of-done.json` after outer-loop review convergence."

No "done when it feels done".

## Risks specific to this phase

Two to four named risks that could surface mid-phase. Examples:

- Test relies on Testcontainers; CI runner without Docker would skip silently.
- Auth filter ordering is environment-specific — test must exercise the
  same chain as production.
- Fixture relies on a clock-skew injection that already breaks on JDK 21.

Tied back to the destination's risk list when applicable.

## Rollback / abort behavior

What happens to the system if the phase is half-done and abandoned.
Examples:

- "No state mutation — phase is purely additive (new test file). Abort is
  safe; just delete the branch."
- "Schema migration is forward-only; abort requires running `02-revert.sql`
  manually. Operator runbook attached."
- "Feature flag `saml.expired-cookie-redirect` defaults to `off`; abort is
  safe by leaving the flag off."

## Notes for the executor

Optional. One short paragraph at most. Use only when the phase has a
non-obvious gotcha the executor would not otherwise see (a hidden module
README, a flake-prone area, a test selector convention specific to this
repo). Otherwise omit the section.
```

## When the phase is owned by a non-implementation skill

The same fields apply. Translate the implementation-flavoured wording to the
owner skill's vocabulary:

- `product-owner` phase: `Expected outputs` is the tracker-ready story or
  acceptance-criteria block; `Validation` is the
  [Definition of Ready](../../product-owner/SKILL.md#definition-of-ready-gate-before-handoff)
  pass.
- `issue-investigator` phase: `Expected outputs` is the investigation
  result and the populated `evidence-pack.yml.investigation` block;
  `Validation` is the
  [investigation-quality checklist](../../../docs/review-loops.md#investigation-quality-checklist)
  pass.
- `manual-tester` phase: `Expected outputs` is the test plan and any
  defect rows; `Validation` is the
  [test-plan review checklist](../../../docs/review-loops.md#test-plan-review-checklist)
  pass.
- `test-automation-engineer` phase: `Expected outputs` is the new
  regression test files and CI integration; `Validation` is the
  test-quality review and a passing CI run.
