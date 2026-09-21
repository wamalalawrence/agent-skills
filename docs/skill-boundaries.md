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
- When dispatched agents cannot open agents of their own, Wamala owns walking an existing plan
  one phase per dispatch (plan mode) and restoring an owed independent review with a sibling
  `code-reviewer` dispatch. Both are the same dispatch model it already uses, run from the depth
  where dispatch works. Neither makes it an executor.

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

- Owns: repository context, implementation plan, code changes, validation, PR readiness, and the
  developer tests that ship with the change — unit tests, the focused integration tests the change
  needs, and its regression tests, including the unit-boundary, test-double, and
  state-versus-interaction decisions behind them
  ([developer testing](../skills/software-engineer/references/developer-testing.md)).
- Does not own: product intent invention, standalone root-cause guessing, broader suite strategy,
  or final human release approval.
- Typical handoff: to `issue-investigator` for unclear bugs, to `code-reviewer` at review gates,
  to `manual-tester` for exploratory validation, and to `test-automation-engineer` when coverage
  belongs to the broader automated suite rather than to this change.

### `issue-investigator`

- Owns: issue classification, expected vs actual behavior, evidence, reproduction, root-cause
  status, and next action.
- Does not own: implementing fixes, final PR verdicts, or invented acceptance criteria.
- Typical handoff: to `software-engineer` for fixes, to `product-owner` for unclear intended
  behavior, and to `test-automation-engineer` for stable regressions.

### `code-reviewer`

- Owns: issue-aware diff review, engineering-quality findings, test-quality review (developer
  tests and automation alike), severity/confidence, and final review verdict.
- Does not own: writing the implementation unless asked, guessing issue intent, or generic
  formatting review.
- Typical handoff: to `issue-investigator` when ticket/root-cause context is unclear and to
  `software-engineer` for fixes.

### `product-owner`

- Owns: product goal, user value, scope, acceptance criteria, UX notes, and tracker-ready handoff.
  A `design-review` of an existing page or flow with no stated standard lands here. The output is
  UX notes and refinement input, never edits to the page.
- Does not own: technical architecture, code review, test implementation, or deciding bug root
  cause.
- Typical handoff: to `issue-investigator` for bug-flavored input, to `software-engineer` for
  feasibility, and to testing skills for coverage concerns.

### `manual-tester`

- Owns: manual test scope, scenarios, execution results, defect evidence, retest guidance, and
  automation candidates. A `design-review` measured against a stated standard (a design system,
  acceptance criteria, an accessibility level, target viewports) lands here, with usability
  observations kept apart from defects.
- Does not own: root-cause analysis, product intent invention, or automation implementation.
- Typical handoff: to `issue-investigator` for reproducible defects, to `product-owner` for unclear
  expected behavior, and to `test-automation-engineer` for stable regression candidates.

### `test-automation-engineer`

- Owns: the automated suite end to end — automation strategy, test level choice, framework and
  convention discovery, fixtures, selectors/contracts, test data and environment lifecycle, CI
  artifacts, suite maintenance after product change, failure triage, flake diagnosis, backlog
  prioritisation, suite runtime, and requirement-to-test traceability.
- Does not own: automating unclear behavior, manual exploration, product intent, root-cause
  analysis of a product defect, the developer tests that ship with a code change, or fixing the
  product. A failing test that exposes a real bug is routed, not patched.
- Typical handoff: to `issue-investigator` for a failure triaged `PRODUCT_DEFECT`, to
  `product-owner` when the behaviour a test should assert was never agreed, to `manual-tester` for
  unstable or exploratory scenarios, and to `code-reviewer` for test-quality review.

### `meeting-intelligence`

- Owns: capturing a meeting the user asked for (a visible, named assistant after a one-time
  recording notice), the meeting's lifecycle, its redacted transcript, and extracting engineering
  facts from it window by window into the repository knowledge base. See
  [Meeting Intelligence](meeting-intelligence.md).
- Does not own: acting on what a meeting decided. Refinement is `product-owner`'s, implementation
  is `software-engineer`'s. It never resolves a speaker to a real identity and never treats a
  meeting fact as more than evidence.
- Typical handoff: a meeting id and its result block; the facts themselves travel through the
  knowledge base, where the next task's preflight finds them.

### `context-optimizer`

- Owns: turning an input too large to read into a bounded, task-specific, traceable context pack.
  Cheap deterministic inspection, task-aware selection, provenance on every fragment, explicit
  omissions, and the character budget. See [Context Optimizer](context-optimizer.md).
- Does not own: any conclusion drawn from the evidence. Not root cause (`issue-investigator`), not
  a fix (`software-engineer`), not a verdict on a diff (`code-reviewer`), not triage of a failure
  wall (`test-automation-engineer`). It produces evidence and stops.
- Typical handoff: a pack id plus the brief that produced it, to whichever skill owns the
  conclusion. The pack is the handoff; a paraphrase is not, because a paraphrase has no provenance.
- **Every skill may use the runtime without dispatching this skill.** That is the point of the
  split: `agent-skills context pack` is a command, not an agent. Route to the skill only when the
  pack itself is the deliverable, or when judging what survived compression is the work. This keeps
  the [depth cap of two](review-loops.md#universal-loop-bounds) intact — a dispatch to shrink a
  file would spend a whole agent's context to save some.

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
  destination. When a phased plan already exists it routes to `delivery-runner` and stops, or runs
  plan mode when dispatch does not nest. A plan that must change — decision-gate answers, or a
  phase criterion an executor showed to be unsatisfiable — goes to `delivery-planner` as a
  `plan-amendment`, never to the user by default and never into the next brief. A request with no
  canonical owner is named as a known gap rather than routed.
- All relevant skills must run the
  [requirement-understanding workflow](requirement-understanding.md) before implementing,
  reviewing, testing, or automating. When the gate ends at `unknown` / `low` confidence, the
  correct handoff is to `product-owner` (when product intent is unclear) or to
  `issue-investigator` (when expected vs actual behavior or root cause is unclear), not to
  `software-engineer`, `manual-tester`, or `test-automation-engineer`.
- Every skill must use **Context Optimizer** before loading an input past the large-input
  threshold, per the shared rule in [Context Optimizer](context-optimizer.md). This is a runtime
  call, not a handoff: the skill runs `agent-skills context pack` itself. Reading a multi-megabyte
  log wholesale spends most of the agent's working memory before it has thought about the problem,
  and it is the one failure mode this rule exists to stop.
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
  automate unclear, subjective, or unstable behavior. It is not a prerequisite for ordinary
  developer unit testing; `software-engineer` writes the tests that ship with its own change.
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
