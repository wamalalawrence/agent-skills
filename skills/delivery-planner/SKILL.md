---
name: delivery-planner
description: >-
  Phased delivery planning workflow that turns a single large or multi-day task
  (feature, refactor, migration, multi-step investigation, multi-PR bug fix) into
  two persistent artifacts: a concise destination brief and a sequence of
  small, self-contained execution phases. Use when: a task is too large to fit
  one agent's working context, when work will span multiple sessions or multiple
  agents, or when the user wants a written plan before any implementation,
  refinement, investigation, or test design begins. Each phase is sized so a
  fresh agent loaded with the destination plus that one phase has enough — and
  only enough — context to execute it well. Hands phases off to
  software-engineer, issue-investigator, product-owner, manual-tester, or
  test-automation-engineer; never re-invokes them itself.
license: MIT
compatibility: >-
  Works with any agent that supports the Agent Skills format (Claude Code, Cursor,
  Windsurf, Continue, GitHub Copilot Chat, ChatGPT, etc.). Two execution modes —
  `local-workspace` (multi-repo, setup.init + .env) and `in-repo` (single-repo,
  .agent-skills.yml). See docs/execution-modes.md.
metadata:
  author: wamalalawrence
  version: "0.28.0"
  homepage: "https://github.com/wamalalawrence/agent-skills"
---

# Delivery Planner

Use this skill at the **start** of a piece of work that is too large for a single
agent run, or that will be picked up by more than one agent or session. It turns
the work into two artifacts that any downstream skill (or fresh agent) can load
verbatim:

- **The destination** — a one-page brief that answers *where are we trying to
  end up, and how will we know we got there*.
- **The phased plan** — a sequence of small, self-contained phases that answer
  *which order do we walk it in, and what does each step look like*.

The premise is simple: agents lose accuracy as their working context grows. A
fresh agent given **destination + one phase** has a small, focused brief and
can finish that phase well, then hand the next phase to a different (or the
same) fresh agent without dragging the previous session's context along.

> **Safety floor.** This skill inherits the
> [destructive-action safety policy](../../docs/destructive-action-safety.md). A
> phase MUST NOT instruct any executing agent to perform destructive production
> actions, invoke discovered credentials, modify backups, or paste secrets into
> chat. Phases that legitimately require destructive maintenance are written as
> operator runbooks for a human, not as agent-executable steps.

## Purpose

- Convert a large, ambiguous, or long-horizon task into a destination brief and
  a phased plan that survive across agent sessions.
- Keep each phase small enough that a fresh agent loaded with `destination.md` +
  one `phase-NN.md` has the full picture and nothing else.
- Make scope, sequencing, dependencies, parallel-safe phases, validation per
  phase, and recommended owner skill explicit so the plan dispatches itself.
- Stop before the first implementation step when the destination cannot yet be
  stated honestly — premature plans are the most expensive form of context.

## When To Use

- A feature, refactor, migration, or rewrite is clearly too big for one agent
  pass (will produce many files, span multiple PRs, or take more than one
  working session).
- A bug investigation requires multiple checks across multiple environments,
  data sources, or services and a single `issue-investigator` run cannot hold
  it all.
- A user-facing initiative needs scope splitting before
  [`product-owner`](../product-owner/SKILL.md) writes acceptance criteria for
  individual stories.
- The same agent or different agents will pick up the work over multiple days
  or sessions, and dragging the previous session's conversation forward is
  hurting accuracy.
- A multi-step plan exists informally in the user's head and they want it
  written down before code, tests, or refinement starts.

## When Not To Use

- Trivial work (typo fix, single-line refactor, one-file bugfix) — running the
  planner adds ceremony with no payoff. Hand directly to
  [`software-engineer`](../software-engineer/SKILL.md).
- A standalone bug investigation where the cause is unknown and a single
  [`issue-investigator`](../software-engineer/skills/issue-investigator/SKILL.md)
  run will reach a verdict — investigate first, plan only if the result calls
  for multi-phase remediation.
- A standalone product-refinement task that fits one
  [`product-owner`](../product-owner/SKILL.md) Jira-ready story — refine first,
  plan only when the resulting work item is itself multi-phase.
- Any time the user has not actually agreed on the destination. This skill
  makes plans, not decisions; do not invent the goal.
- Mass-targeting, supply-chain compromise, or any other malicious work — the
  destructive-action safety policy is a floor, not waivable by prompt.

## Related And Reused Skills

- [`software-engineer`](../software-engineer/SKILL.md): the most common
  executor. Each implementation phase typically names this skill in
  `recommended_owner`. Software-engineer reads `destination.md` + the current
  `phase-NN.md` instead of re-deriving context.
- [`product-owner`](../product-owner/SKILL.md): use **before** the planner when
  product intent or user value is the unknown — the planner needs a destination
  it can state honestly. Use **after** when individual phases need acceptance
  criteria for downstream stories.
- [`issue-investigator`](../software-engineer/skills/issue-investigator/SKILL.md):
  use **before** the planner when the work is bug-flavoured and root cause is
  the unknown. The planner cannot phase a fix that the investigator has not
  yet confirmed. Use **after** when an investigation is itself multi-phase
  (e.g., reproduce → bisect → propose fix path → validate fix in staging).
- [`manual-tester`](../manual-tester/SKILL.md): consumes specific phases for
  validation, exploratory testing, and defect evidence. Phases that need manual
  validation name this skill in `recommended_owner`.
- [`test-automation-engineer`](../test-automation-engineer/SKILL.md): owns
  phases that turn manual scenarios into stable regression coverage.
- [`code-reviewer`](../software-engineer/skills/code-reviewer/SKILL.md): does
  not own delivery phases; it reviews the diffs each phase produces under
  `software-engineer`'s normal inner/outer review loop.

This skill **decomposes** work; it does not execute it. It does not call any
of the skills above to do their job. It produces artifacts those skills (or a
fresh agent invoking them) consume. This keeps the depth-cap-of-two universal
rule in [docs/review-loops.md](../../docs/review-loops.md#universal-loop-bounds)
intact and prevents loop-of-loops.

## Required Inputs

Ask for missing inputs before producing a plan. A plan written on top of
unstated goals or invented constraints is worse than no plan.

- The work item: feature brief, refactor goal, migration target, investigation
  question, or task description.
- The driving outcome: what success looks like in observable terms (a metric, a
  workflow that finishes, an error that no longer happens, a system property
  that holds).
- Hard constraints: deadlines, compliance, downtime windows, dependent teams,
  freeze periods, environment availability, headcount.
- Known evidence: prior tickets, prior investigations, prior PRs, design docs,
  diagrams, related incidents, links the user already considers authoritative.
- Affected repos / services / surfaces, when known. Otherwise the planner
  notes "scope of affected surface to be discovered in phase 1".
- The user's working budget: rough time horizon ("this week", "Q3"), rough
  agent budget ("each phase should be a single session"), and whether work
  will be picked up by multiple agents or sessions.

If the input is a one-line ask ("plan the auth rewrite") with no outcome, no
constraints, and no evidence pointers, **stop and ask** for at least the
outcome and one constraint before writing anything down.

## Stopping Conditions

Stop and return `Readiness: NEEDS_CLARIFICATION` / `NEEDS_EVIDENCE` / `BLOCKED`
instead of producing the plan when:

- The destination cannot be stated as one or two observable outcomes — the
  planner does not invent goals.
- Product intent, expected behavior, or root cause is unknown and another
  skill must run first (route to
  [`product-owner`](../product-owner/SKILL.md) or
  [`issue-investigator`](../software-engineer/skills/issue-investigator/SKILL.md)).
- The shortest credible phasing already collapses into a single phase — the
  task is too small for this skill; hand directly to the executing skill.
- A load-bearing constraint (deadline, compliance, downtime window, missing
  access) cannot be confirmed and the entire plan would change depending on
  the answer.
- The plan would require an executing agent to perform a forbidden destructive
  action under the [destructive-action safety
  policy](../../docs/destructive-action-safety.md). Split such steps into
  human-operator runbooks; do not phase them as agent steps.

## Required Environment

This skill is **mostly read-only**: it reads the issue source and prior cache
artifacts and writes plan files into the cache. The
[execution-modes preflight](../../docs/execution-modes.md) still applies so
that subsequent skills can resolve project / repo / branch context from the
same configuration the planner saw:

1. If `AGENT_SKILLS_MODE` is set to `local-workspace` or `in-repo`, use it.
2. Else if `${WORKSPACE_ROOT}/.env` is present and readable → `local-workspace`.
3. Else if `.agent-skills.yml` exists at the repository root → `in-repo`.
4. Else: a plan is still possible from user-supplied context alone, but the
   output must clearly state that setup was not verified and downstream skills
   may need to re-establish context before executing the first phase.

Useful but not required:

- `WORKSPACE_ROOT` / repository root — needed to write the plan into the
  shared `.cache/agent-skills/<issue-key>/` directory next to the existing
  evidence-pack and definition-of-done artifacts.
- `AGENT_SKILLS_CACHE_DIR` — overrides the cache root.
- Jira / Confluence / GitHub access — only when the input is a ticket and the
  planner needs to fetch the brief itself. If the user pastes the brief,
  these are not required.

If a Jira ticket key is supplied but Jira access is unavailable, follow the
[auth discovery walk](../../docs/auth-discovery.md) before declaring it
inaccessible. Treat unresolved `${VAR}` placeholders in `.jira-config.yml` as
incomplete configuration, not missing credentials.

## Required Workflow

### 0. Requirement Understanding Gate

Run the shared
[requirement-understanding workflow](../../docs/requirement-understanding.md)
before any decomposition and emit the `Requirement Understanding` block above
the rest of the planner output. The planner is unusually load-bearing here —
phases written on top of an `unknown` understanding multiply the original
mistake.

Apply the binding rules:

- **`unknown` / `low`** — do **not** produce a phased plan. Return
  `NEEDS_CLARIFICATION`, `NEEDS_EVIDENCE`, or `BLOCKED`. If product intent is
  the unknown, hand off to [`product-owner`](../product-owner/SKILL.md). If
  expected behavior or root cause is the unknown, hand off to
  [`issue-investigator`](../software-engineer/skills/issue-investigator/SKILL.md).
  A destination brief that says "we will figure out what we want as we go" is
  not a destination.
- **`medium`** — may write a `Discovery` first phase whose explicit purpose is
  to close the load-bearing assumptions, with the rest of the plan marked as
  *provisional*. The discovery phase's exit criterion is that
  understanding-confidence becomes `high`. Until then, downstream phases stay
  in `provisional` state.
- **`high`** — may write the full destination + phased plan and dispatch
  phases to executing skills.

The first plausible interpretation is not `high`. High requires that
disconfirming checks were either run or judged unnecessary because evidence
already excluded the alternatives — see step 11 of the shared workflow.

### 1. Establish the destination

Produce the **destination brief** — a single short document any executor can
load alongside one phase and have a complete picture of the goal.

The destination MUST contain:

- **Outcome statement.** One or two plain-language sentences describing the
  end state. Stripped of vendor names, fashion words, and metaphors. The first
  sentence is what changes from the user's perspective; the second (if any)
  is what changes from the system's perspective.
- **Success signals.** Two to five observable signals that mean the outcome
  was achieved: a metric, a workflow that finishes, an error that disappears,
  a property that holds. Each signal must be testable by *something* (manual
  check, automated test, log filter, dashboard widget); say which.
- **Scope.** What this delivery includes.
- **Non-goals.** What this delivery deliberately does not include, even when
  adjacent or tempting. Non-goals are the most-skipped field and the most
  expensive to omit; never leave it blank — write `none — the scope is
  bounded only by the success signals above` if it really is empty.
- **Constraints.** Hard limits: deadline, compliance, downtime windows, freeze
  periods, dependent teams, environment access, headcount.
- **Load-bearing assumptions.** Each one labelled `safe` or `load-bearing`,
  with a one-line *what would change my mind* falsifier on every load-bearing
  one.
- **Stakeholders / decision makers.** Who must agree before the plan executes,
  who must agree before scope changes, who reviews each phase.
- **Risks the plan must protect against.** Two to four named risks (data
  corruption, customer-visible regression, rollout cost, compliance breach,
  cross-team coupling) so phases can be scheduled to retire the highest-risk
  ones first.

Persist as
`${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills}/<issue-key>/destination.md`
following the binding [destination template](./references/destination-template.md). The file is
plain Markdown with a small YAML header (`work_key`, `state`, `created_at`, `updated_at`,
`source_refs`, `understanding_confidence`, `readiness_decision`) so a downstream agent or human
can paste it verbatim into a fresh prompt without re-derivation, and so the planner can detect
its own staleness on its next run.

If the destination has changed since the last run (outcome edited, success
signal removed, constraint added), update the file in place and bump the
`updated_at:` timestamp at the top. Do not rewrite the phased plan as a side
effect — phase rewrites happen in step 4 explicitly.

### 2. Map the work

Before naming phases, write a **work map** in the planner's working context
(does not have to ship in the final output):

- The set of changes implied by the destination, by surface (controller, model,
  schema, infra, doc, runbook, test, dashboard, release artifact, …).
- The smallest credible *vertical* slice that would already deliver some of
  the outcome — slices the user could ship and stop on if priorities shifted.
- Hard sequencing: which changes must precede which (schema before write
  path, write path before read path, read path before UI, regression test
  before fix, monitoring before rollout, etc.).
- Soft sequencing: which changes are merely cheaper-together (formatting,
  doc updates, type renames). These are candidates to bundle into a single
  phase or skip into follow-ups.
- Areas of unknown cost. Reflect these as *spike* phases with a fixed
  time-box, not as open-ended planning.

The work map is the artifact that distinguishes planning from listing. If the
phases in step 3 do not reflect the dependencies in this step, the plan is
wrong.

### 3. Decompose into phases

Produce the **phased plan** as a sequence of files
`${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills}/<issue-key>/phased-plan/phase-NN-<slug>.md`,
plus one index `phased-plan/README.md` listing them in order with their state.

Each phase is sized so that **destination.md + phase-NN.md** is a complete
brief for a fresh agent. Concretely, each phase aims for:

- A scope a single agent can finish in one focused session (typically a
  single small PR's worth of changes, or a single read-only investigation
  pass, or a single test plan).
- A combined `destination + phase` page count that fits comfortably inside
  the executing agent's context budget. As a rule of thumb keep each phase
  file ≤ ~150 lines of Markdown; if it grows past that, split.
- One owning skill. A phase that lists three skills as joint owners is
  almost always two phases.

Each `phase-NN-<slug>.md` MUST contain:

- **Phase ID and title.** `Phase 03 — failing regression test`.
- **Intent.** One sentence on what this phase exists to produce, in plain
  language. Treat as the executor's "north star" for this phase.
- **Prerequisites.** Which earlier phases must be complete (by phase ID), and
  which evidence-pack / repro-recipe / definition-of-done fields must already
  be populated. If `none`, say so.
- **Inputs.** The exact files, links, ticket excerpts, prior outputs, or
  config keys the executor reads. Prefer pointers (paths, keys, links) over
  pasted content.
- **Scope (in / out).** What this phase changes; what it deliberately does
  not, even if tempting. Mirrors the destination's non-goals at the
  phase level.
- **Recommended owner skill.** One of `software-engineer`, `product-owner`,
  `issue-investigator`, `manual-tester`, `test-automation-engineer`. The
  executor is expected to load that skill's `SKILL.md` and follow its
  workflow for this phase. The planner does not invoke skills itself. Before
  marking a phase `ready`, verify the owner skill can be resolved from the
  canonical skill source defined by
  [skill-source resolution](../../docs/skill-source-resolution.md), including
  any explicit skill path the user supplied. If it cannot be resolved, the
  phase state is `blocked`, not `ready`.
- **Expected outputs / artifacts.** What must exist when the phase is done:
  files committed, evidence-pack fields populated, tests added, a Jira-ready
  story produced, an investigation result, a passing CI run.
- **Validation / exit criteria.** The observable check that says the phase is
  finished. A test passes, a query returns the expected shape, a peer review
  signs off, an acceptance criterion is met. No `done when it feels done`.
- **Risks specific to this phase.** Anything that could surface mid-phase: a
  blocked dependency, a likely-flaky test, a destructive guardrail, a missing
  credential. Tied back to the destination's risk list when applicable.
- **Estimated size.** S / M / L. `L` is a code smell — try splitting again.
- **Parallel-safe?** `yes` / `no`. If `yes`, list which other phase IDs it
  can run alongside.
- **Rollback / abort behavior.** What happens to the system if the phase is
  half-done and abandoned. For destructive or schema-changing phases this is
  mandatory; for pure-read or pure-add phases it is `no rollback needed —
  no state mutation`.

For code-delivery plans (bug fix, feature, refactor, migration), the plan is
not complete until it reaches a reviewable delivery artifact. Each
`software-engineer` implementation phase must either finish its own
`software-engineer` Phase 5 path (committed branch, outer-loop `code-reviewer`
convergence, Definition-of-Done artifact, pushed remote branch, PR URL), or the
plan must include a later `software-engineer` closure phase that performs those
steps. A final phase that only validates behavior is not conclusive for a code
delivery; validation must feed into review and PR readiness.

The index `phased-plan/README.md` follows the binding
[plan-index template](./references/plan-index-template.md) and MUST contain:

- A YAML header with `work_key`, `destination_path`, `state`, `created_at`,
  `updated_at`, `current_dispatch_pointer`, `readiness_decision`, the
  `last_completed_*` mirrors of `evidence-pack.yml.delivery_plan`, and
  `totals`.
- An **`## Inputs for the next agent`** section that lists, with repo-relative
  paths, the destination brief, the evidence pack, the current phase file,
  and the canonical skill source path for the dispatched phase's
  `recommended_owner`. A user pasting only this README into a fresh prompt
  must be able to walk those pointers without prior conversation context.
- The list of phases in order with title, owner skill, size, state
  (`provisional` / `ready` / `in-progress` / `done` / `skipped` / `blocked`),
  and prerequisites — rendered as a Markdown table.
- The dependency graph in plain prose ("Phase 4 needs Phases 1 and 3; Phases
  2 and 3 are parallel-safe").
- The current dispatch pointer — which phase is next. Subject to the binding
  rules in the [plan-index template's "Dispatch pointer rules"
  section](./references/plan-index-template.md#body-sections):
  `READY_FOR_DISPATCH` and `READY_FOR_DISCOVERY` MUST name a phase id;
  `null` is reserved for `NEEDS_CLARIFICATION` / `NEEDS_EVIDENCE` / `BLOCKED`.

The index is **derived** from the per-phase files plus
`evidence-pack.yml.delivery_plan`: the planner regenerates it on every run
by re-reading the per-phase files and recomputing `totals`, the
`last_completed_*` mirrors, and `current_dispatch_pointer`. Where the index
and a per-phase file disagree, the per-phase file wins and the index is
regenerated.

The planner MUST also create or update
`${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills}/<issue-key>/evidence-pack.yml`
in the same run. This applies even when the user starts from a greenfield brief
and no prior evidence pack exists. The evidence pack is the durable continuity
contract for phase execution: it records the `delivery_plan` structure, the
current dispatch pointer, and the fields each executor must update when a
phase completes. A plan that writes `destination.md` and phase files without
`evidence-pack.yml` is not dispatchable.

### 4. Right-size and re-decompose

Phases that are too large hide their assumptions. Re-decompose any phase that:

- Touches more than one major surface (e.g., schema *and* controller *and* UI).
- Requires more than one owning skill to do its core work.
- Cannot state a single one-sentence intent without using the word "and".
- Cannot name an unambiguous validation step.
- Has an `L` size estimate that the user did not explicitly accept as
  unsplittable.

Re-decomposition replaces the offending phase with two or more smaller
phases, updates the index, and adjusts dependency lines. Do not silently
absorb extra work into a neighbour phase.

### 5. Sequence and dispatch

The planner picks the next phase to run and writes its phase ID into the
index's `current_dispatch_pointer`. From there, dispatch is the user's or
executor's job — the planner does not call other skills. The recommended
skill on each phase tells the executor which `SKILL.md` to load.

The dispatch pointer is a contract, not a suggestion. The executing agent must
load the `recommended_owner` skill from the resolved canonical skill source
before acting. If the skill cannot be found, if a host only checked a default
`.skills` path while the user supplied a different folder, or if the loaded
skill's `name` does not match `recommended_owner`, the phase is blocked and no
work should be performed under a substitute workflow.

The dispatch-pointer rules are **binding** and mirrored in the
[plan-index template](./references/plan-index-template.md#body-sections):

- `READY_FOR_DISPATCH` → `current_dispatch_pointer` MUST be the phase id of
  the first phase whose state is `ready` and whose prerequisites are all
  `done`. Never `null`.
- For high-confidence plans, mark phases `ready` when they are fully specified
  and only blocked by listed prerequisites; prerequisites, not `provisional`,
  gate dispatch order. Reserve `provisional` for phases that cannot be safely
  executed from the written plan because discovery or user evidence is still
  needed.
- `READY_FOR_DISCOVERY` → `current_dispatch_pointer` MUST be the phase id
  of the discovery / spike phase that closes the load-bearing assumptions
  surfaced by the medium-confidence gate. **Never `null`.** All later
  phases stay `provisional` until the discovery phase raises
  understanding-confidence to `high`. The output contract MUST NOT use
  the placeholder "none — discovery first"; it MUST name the discovery
  phase id.
- `NEEDS_CLARIFICATION` / `NEEDS_EVIDENCE` / `BLOCKED` →
  `current_dispatch_pointer` MUST be `null`. The planner has nothing to
  dispatch; the next action is on the user, not on an executor.

### 6. Self-validation pass (bounded)

Before emitting the final result, run **one** self-check against the
[plan-quality checklist](./references/plan-quality-checklist.md). Items that
fail must be fixed in this pass or moved to `Open Questions Or Provisional
Items` with a one-line gap statement. **Do not run the checklist a second
time.** This loop is bounded by the universal rules in
[docs/review-loops.md](../../docs/review-loops.md#universal-loop-bounds): one
revision round, no recursion, depth cap of two skills.

### 7. When the plan goes stale

A phased plan is a snapshot, not a contract. Re-run the planner (and update
`destination.md` + the affected phase files in place) when:

- The destination's outcome statement, success signals, or non-goals change.
- A phase is skipped, blocked, or comes back with a `not-converging` /
  `needs-user` signal from its executing skill.
- A new constraint appears (deadline, compliance, downtime window) that
  invalidates the dependency graph.
- An executor's review (typically
  [`code-reviewer`](../software-engineer/skills/code-reviewer/SKILL.md))
  surfaces a load-bearing assumption that turns out to be wrong.

Update existing files in place (do not rewrite history). Bump the
`updated_at:` timestamp on both `destination.md` and the index. Mark
superseded phases `skipped` with a one-line reason instead of deleting them
— downstream skills may still read `evidence-pack.yml` references that point
at superseded phase IDs.

## Cache layout

```text
${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills}/<issue-key>/
├── destination.md                       <- this skill writes
├── phased-plan/
│   ├── README.md                        <- phase index, dispatch pointer
│   ├── phase-01-<slug>.md               <- one file per phase
│   ├── phase-02-<slug>.md
│   └── ...
├── evidence-pack.yml                    <- this skill creates/updates; shared with other skills
├── repro-recipe.yml                     <- shared (existing, when applicable)
└── definition-of-done.json              <- shared (existing, written by software-engineer)
```

The plan files live next to the evidence pack so any downstream skill can
read both with one directory walk. The cross-skill schema for the
phase-state writes — what each executing skill appends, and what the
planner alone owns — is defined in the
[evidence-pack `delivery_plan` ownership rule](../software-engineer/references/evidence-pack.md#3-skill-responsibilities).
The short version: the planner is the sole writer of the structural fields
(`destination_path`, `index_path`, the `phases[]` list); the skill named in
a phase's `recommended_owner` is the sole writer of that phase's completion
checkpoint (`state`, `completed_at`, `completed_by`, `completion_summary`,
`artifacts`, `validation`, `follow_up_context`) and the top-level
`last_completed_*` / `last_continuity_checkpoint_at` mirrors. The executor
also recomputes `current_dispatch_pointer` to the next ready phase after its
own checkpoint. Without that checkpoint, the phase is not complete.

## Phase template

Use the [phase-template](./references/phase-template.md) when writing each
`phase-NN-<slug>.md`. The template is the binding shape; do not invent extra
fields.

## Expected Output Contract

Follow [Output Discipline](../../docs/output-discipline.md). The contract
below is a **menu** of available sections, not a checklist. **Omit empty
sections** — if there are no provisional phases, drop the
`## Provisional Phases` heading entirely instead of writing `- none`.
Required-even-if-empty: `## Plan Summary` (so dispatch state cannot be
omitted by accident).

```markdown
## Plan Summary

- Issue / work key:
- Destination file: <relative path written or updated this run>
- Phased-plan index: <relative path written or updated this run>
- Evidence pack: <relative path written or updated this run; REQUIRED for every dispatchable plan>
- Phases total / ready / done / blocked:
- Current dispatch pointer: <phase id, REQUIRED for READY_FOR_DISPATCH and
  READY_FOR_DISCOVERY (point at the discovery phase id); "none" only when
  readiness is NEEDS_CLARIFICATION / NEEDS_EVIDENCE / BLOCKED>
- Understanding confidence: unknown | low | medium | high
- Readiness decision: READY_FOR_DISPATCH | READY_FOR_DISCOVERY |
  NEEDS_CLARIFICATION | NEEDS_EVIDENCE | BLOCKED

## Destination Brief

- Outcome:
- Success signals:
- Scope:
- Non-goals:
- Constraints:
- Load-bearing assumptions:
- Stakeholders / decision makers:
- Risks the plan protects against:

## Phases

- **<id> — <title>** (owner: <skill>, size: S|M|L, state: <state>) —
  <one-sentence intent>. Validation: <one-sentence exit criterion>.
  Prerequisites: <ids or "none">.

(One bullet per phase. Skip phases that are merely placeholders.)

## Dependency Map

- <plain-prose dependency description, two to four sentences max>

## Provisional Phases

- ...

## Open Questions Or Missing Evidence

- ...

## Insightful Simplification

<Optional. 1–3 bullets, ≤ 35 words each, anchored to a concrete
boundary/state/contract/lifecycle the plan exposes. Omit the section
entirely when no qualifying insight exists. See
[Insightful Simplifications](../../docs/insightful-simplifications.md).>

- ...
```

### Output Style (binding)

- **Omit empty sections.** No `Provisional Phases:` followed by `- none`.
  Drop the heading.
- **Phases are bullets, not paragraphs.** One bullet per phase in the
  user-facing summary; the long form lives in the per-phase Markdown file.
- **No template echo, no banners.** See
  [Output Discipline](../../docs/output-discipline.md).

## Behavior Checklist

- [ ] Destination has an observable outcome, success signals tied to a way
  to test them, explicit non-goals, constraints, and load-bearing
  assumptions with falsifiers.
- [ ] Each phase fits a fresh agent's context budget and names exactly one
  recommended owner skill.
- [ ] Each `ready` phase's recommended owner skill resolves from the canonical
  skill source. Missing owner skill resolution is `blocked`, not a warning.
- [ ] `evidence-pack.yml` exists beside `destination.md` and contains the
  `delivery_plan` block for every phase. A plan with only Markdown phase files
  is not dispatchable.
- [ ] Each phase has prerequisites, inputs, scope, expected outputs,
  validation, risks, size, parallel-safety, and rollback behavior.
- [ ] Code-delivery plans end at a reviewable delivery artifact: branch pushed,
  PR URL recorded, Definition-of-Done written, and `code-reviewer` outer-loop
  convergence or explicit blocker. A validation-only final phase is incomplete.
- [ ] Dependency graph in the index matches the prerequisites listed on
  individual phase files (not silently contradicted).
- [ ] No phase requires the executor to perform a forbidden destructive
  action under the destructive-action safety policy.
- [ ] Understanding confidence and readiness decision are stated and obey
  the confidence-to-action rules.

## Quality Standards

- The destination is short enough that an executor can read it in under a
  minute and remember it for the rest of the phase.
- Each phase is self-contained: an executor with no prior conversation
  history can finish it from `destination.md + phase-NN.md` alone.
- Phases retire the highest-risk question first, not last.
- Provisional phases are clearly marked and never dispatched without an
  explicit accept-the-risk note.
- Plan artifacts live in the shared cache layout; the planner does not
  invent a new directory structure per task.
- The evidence pack is the continuity source of truth. A fresh agent must be
  able to read it and know which phase was last completed and which phase is
  next.
- Implementation plans do not hide the final engineering closure. Review,
  Definition-of-Done, push, and PR readiness are part of delivery, not optional
  afterthoughts.

## Guardrails

- Do not invent the goal, the success criteria, the constraints, or the
  stakeholders. If they are not stated and cannot be derived from real
  evidence, the readiness is `NEEDS_CLARIFICATION`.
- Do not produce a plan when the
  [Requirement Understanding Gate](#0-requirement-understanding-gate) ends at
  `unknown` or `low` confidence — that is the
  [confidence-to-action rule](../../docs/requirement-understanding.md#confidence-to-action-rules)
  and it is binding.
- Do not invoke `software-engineer`, `product-owner`,
  `issue-investigator`, `manual-tester`, `test-automation-engineer`, or
  `code-reviewer` from inside this skill. Hand the plan off; the executor
  invokes them. This preserves the
  [depth cap of two skills](../../docs/review-loops.md#universal-loop-bounds).
- Do not silently absorb new work into a neighbour phase when something
  surprises you mid-plan. Re-decompose explicitly.
- Do not write phases that depend on an executor performing destructive
  production actions, invoking discovered credentials, or pasting secrets
  into chat. Such steps are operator runbooks, not agent phases. See the
  [destructive-action safety policy](../../docs/destructive-action-safety.md).
- Do not delete superseded phase files; mark them `skipped` with a one-line
  reason. Other skills may hold references to those phase IDs.
- Do not produce a plan that contradicts itself between the index and the
  per-phase files. The index is generated from the per-phase files; if they
  disagree, the per-phase files win and the index is regenerated.
- Do not mark a phase `ready` when its `recommended_owner` skill cannot be
  resolved from the canonical skill source. Surface the missing skill as a
  blocker with the checked paths.
- Do not produce a dispatchable plan without `evidence-pack.yml`. If the cache
  write fails, readiness is `BLOCKED` even if the Markdown plan files were
  written.
- Do not end a code-changing delivery plan with validation only. The final
  executable path must either produce a pushed PR-ready branch or explicitly
  stop as blocked before claiming completion.
- Do not run the self-validation checklist more than once on the same plan.
  Surviving items move to `Open Questions Or Missing Evidence` and the
  user decides.
- Do not turn this skill into a project-management replacement. It does not
  track effort, calendar dates, headcount allocation, or vendor procurement.
  Those belong outside the agent loop.
- Do not invent the project's branching policy. Read each affected repo's
  `base_branch` from `${PROJECTS_JSON}` (with `${GITHUB_DEFAULT_BRANCH}` as
  a fallback when an entry is missing). Some teams target `develop`, some
  `main`, some a release train; the planner mirrors what the project
  declared, never overrides it. The only exception is when the user
  explicitly states a different base branch in the prompt — record the
  exception verbatim in the destination's `Constraints` section.

## Example Prompts

- "Use the delivery-planner skill to phase this auth-rewrite epic before any
  code is written. The destination is single-sign-on parity with the
  existing local-auth flow; we have eight weeks."
- "Plan a multi-phase migration of the payments service from MySQL to
  Postgres. Each phase should be small enough that I can hand it to a
  fresh agent the next morning."
- "This investigation has run long enough; turn the open hypotheses into a
  phased plan and set the first dispatch pointer to a phase whose
  recommended_owner is issue-investigator."
- "Use the delivery-planner skill to split this oversized story into smaller
  phases, each with recommended_owner: product-owner so I can dispatch them
  to product-owner one at a time for acceptance criteria."

See [the delivery-planner phased-plan example](../../docs/examples/delivery-planner-feature-decomposition.md)
and [starter prompts](../../docs/starter-prompts.md).

---

## Reference files

- [Destination template](./references/destination-template.md) — the
  binding shape of `destination.md` (header fields plus body sections).
- [Plan-index template](./references/plan-index-template.md) — the binding
  shape of `phased-plan/README.md`, including the binding dispatch-pointer
  rules.
- [Phase template](./references/phase-template.md) — the binding shape of
  each `phase-NN-<slug>.md` file.
- [Plan-quality checklist](./references/plan-quality-checklist.md) — the
  single self-validation pass step 6 runs.
- [Evidence-pack `delivery_plan` ownership rule](../software-engineer/references/evidence-pack.md#3-skill-responsibilities)
  — the cross-skill schema for phase-state writes; the contract that keeps
  the dispatch pointer fresh after real phase execution.
