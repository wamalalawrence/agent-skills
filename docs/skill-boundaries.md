# Skill Boundaries

These skills are meant to collaborate, not compete. Each role owns a different decision surface and
must hand off when the task moves outside that surface.

## Role Ownership

### `wamala`

- Owns: classifying an incoming request, running the requirement-understanding gate, choosing
  the single skill that owns the next step, dispatching a fresh-context agent, and verifying
  each step from persisted artifacts.
- Does not own: implementation, review, refinement, investigation, testing, automation,
  decomposition, or terminology. It owns the **choice** of owner and nothing the owner does.
- Typical handoff: exactly one owner per dispatched step, taken from the rows in
  [`routing-table.md`](../skills/wamala/references/routing-table.md). Like
  `delivery-runner`, it **dispatches rather than invokes** — it never loads an executor skill
  into its own context, so the depth-cap-of-two bound applies inside each step and the lead
  never appears in that chain.
- Never mandatory. Direct invocation of any skill remains first-class and is preferable
  whenever the owner is already known.

### `delivery-planner`

- Owns: phased decomposition of large or multi-session work, the `destination.md` brief, the
  per-phase `phase-NN-<slug>.md` files, the dependency graph, and the dispatch pointer.
- Does not own: implementation, refinement, investigation, manual testing, or automation. It
  produces artifacts those skills consume.
- Typical handoff: each phase names exactly one of `software-engineer`, `product-owner`,
  `issue-investigator`, `manual-tester`, or `test-automation-engineer` in `recommended_owner`;
  the executor invokes that skill itself. The planner does **not** call other skills, preserving
  the depth-cap-of-two universal loop bound.

### `software-engineer`

- Owns: repository context, implementation plan, code changes, validation, and PR readiness.
- Does not own: product intent invention, standalone root-cause guessing, or final human release
  approval.
- Typical handoff: to `issue-investigator` for unclear bugs, to `code-reviewer` at review gates,
  and to testing skills for validation coverage.

### `issue-investigator`

- Owns: issue classification, expected vs actual behavior, evidence, reproduction, root-cause
  status, and next action.
- Does not own: implementing fixes, final PR verdicts, or invented acceptance criteria.
- Typical handoff: to `software-engineer` for fixes, to `product-owner` for unclear intended
  behavior, and to `test-automation-engineer` for stable regressions.

### `code-reviewer`

- Owns: issue-aware diff review, engineering-quality findings, severity/confidence, and final
  review verdict.
- Does not own: writing the implementation unless asked, guessing issue intent, or generic
  formatting review.
- Typical handoff: to `issue-investigator` when ticket/root-cause context is unclear and to
  `software-engineer` for fixes.

### `product-owner`

- Owns: product goal, user value, scope, acceptance criteria, UX notes, and tracker-ready handoff.
- Does not own: technical architecture, code review, test implementation, or deciding bug root
  cause.
- Typical handoff: to `issue-investigator` for bug-flavored input, to `software-engineer` for
  feasibility, and to testing skills for coverage concerns.

### `manual-tester`

- Owns: manual test scope, scenarios, execution results, defect evidence, retest guidance, and
  automation candidates.
- Does not own: root-cause analysis, product intent invention, or automation implementation.
- Typical handoff: to `issue-investigator` for reproducible defects, to `product-owner` for unclear
  expected behavior, and to `test-automation-engineer` for stable regression candidates.

### `test-automation-engineer`

- Owns: automation strategy, test level choice, fixtures, selectors/contracts, CI artifacts, and
  flakiness risk.
- Does not own: automating unclear behavior, manual exploration, product intent, or root-cause
  investigation.
- Typical handoff: to `manual-tester` for unstable/manual scenarios, to `issue-investigator` for
  repro evidence, and to `code-reviewer` for test-quality review.

### `domain-modeler`

- Owns: canonical domain glossary (`CONTEXT.md`), Architecture Decision Records (`docs/adr/`),
  terminology disambiguation, and cross-referencing stated behaviour against code.
- Does not own: product scope or user-facing language (that's `product-owner`), implementation
  or architectural authority (that's `software-engineer`), or phase-level work decomposition
  (that's `delivery-planner`).
- Typical handoff: to `product-owner` when user-facing terminology needs refinement, to
  `software-engineer` when an ADR needs feasibility validation, and to `delivery-planner` when
  a glossary change or ADR affects the phasing of a multi-phase delivery.

## Required Handoffs

- `wamala` must dispatch to exactly one owner per step and must not perform any owner's
  work itself. When a request needs several specialists it dispatches them in sequence,
  re-running the requirement-understanding gate against each completed step before dispatching
  the next. When no routing row matches it asks one focused question rather than inventing a
  destination. When a phased plan already exists it routes to `delivery-runner` and stops.
- All relevant skills must run the
  [requirement-understanding workflow](requirement-understanding.md) before implementing,
  reviewing, testing, or automating. When the gate ends at `unknown` / `low` confidence, the
  correct handoff is to `product-owner` (when product intent is unclear) or to
  `issue-investigator` (when expected vs actual behavior or root cause is unclear), not to
  `software-engineer`, `manual-tester`, or `test-automation-engineer`.
- `software-engineer` must use `issue-investigator` when expected behavior, issue context, or root
  cause is unclear.
- `software-engineer` must use `code-reviewer` after implementation and again before final PR or
  release handoff.
- `code-reviewer` must use `issue-investigator` when correctness depends on ticket understanding or
  root-cause evidence that is missing.
- `product-owner` must route support complaints, incidents, regressions, and other bug-flavored
  requirements through `issue-investigator` before writing fix acceptance criteria.
- `manual-tester` must hand reproducible defects to `issue-investigator` with environment, build
  SHA, expected vs actual behavior, steps, and evidence.
- `test-automation-engineer` must consume stable manual or reproduction scenarios and should not
  automate unclear, subjective, or unstable behavior.
- `delivery-planner` must hand off each phase to exactly one owner skill and must not invoke any
  other skill itself. Executors read `destination.md` plus the current `phase-NN-<slug>.md`
  alongside their normal context. When a phase is too large or its assumptions turn out to be
  wrong mid-execution, the executor stops and surfaces to the user; the planner re-decomposes on
  its next run rather than being called recursively.

## Nested Support Skills

`issue-investigator` and `code-reviewer` are nested under `software-engineer` for now because they
serve the engineering loop: evidence first, implementation second, review before completion. They
also share the same evidence-pack and definition-of-done artifacts with the engineering workflow.

They might become top-level skills later if real usage shows they are commonly invoked
independently, need separate installation/versioning, or support non-engineering workflows without
depending on the software-engineer evidence loop. Until then, keeping them nested makes the current
collaboration model explicit without adding top-level role sprawl.
