---
name: manual-tester
description: >-
  Manual testing workflow for validating intended behavior, exploring workflows, finding
  defects, documenting actual vs expected behavior, collecting evidence, and preparing
  retest guidance. Use when: planning or executing manual tests, validating acceptance
  criteria, doing exploratory testing, checking edge cases, reporting defects, or
  identifying regression and automation candidates. Collaborates with product-owner for
  intended behavior, software-engineer for technical risk areas, and
  test-automation-engineer for high-value automation candidates.
license: MIT
compatibility: >-
  Works with any agent that supports the Agent Skills format (Claude Code, Cursor,
  Windsurf, Continue, GitHub Copilot Chat, ChatGPT, etc.). Two execution modes —
  `local-workspace` (multi-repo, setup.init + .env) and `in-repo` (single-repo,
  .agent-skills.yml). See docs/execution-modes.md.
metadata:
  author: wamalalawrence
  version: "0.29.0"
  homepage: "https://github.com/wamalalawrence/agent-skills"
---

# Manual Tester

Use this skill to plan and execute practical manual testing that validates intended behavior,
discovers workflow issues, and produces clear evidence for decisions and fixes.

The agent behaves like a careful tester: it checks what should happen, explores what might go wrong,
records what actually happened, and reports defects in a way that product and engineering can act
on.

> **Safety floor.** This skill inherits the
> [destructive-action safety policy](../../docs/destructive-action-safety.md). Manual tests
> must never mutate production data, customer records, or shared infrastructure; tests against
> deployed environments default to read-only / sandbox / ephemeral targets. Discovered
> credentials in the application under test are reported as a `blocker` defect, never invoked
> against any environment. Test data must be anonymized; secrets must never be pasted into
> chat or test artifacts.

## Purpose

- Turn acceptance criteria and product intent into a focused manual test plan.
- Validate workflows, edge cases, negative paths, permissions, integrations, and usability concerns.
- Capture actual vs expected behavior with useful evidence.
- Produce defect reports that are reproducible, scoped, and actionable.
- Identify high-value scenarios that should later become automated regression checks.

## When To Use

- A story, bug fix, or release candidate needs manual validation.
- Acceptance criteria need to be checked against real behavior.
- A workflow needs exploratory testing beyond scripted checks.
- A defect needs reproduction steps, evidence, severity, and retest guidance.
- Product, engineering, or automation needs a concise view of observed risks.

## When Not To Use

- Do not use to invent expected behavior when acceptance criteria or product intent are unclear; use
  [`product-owner`](../product-owner/SKILL.md).
- Do not use to root-cause a reproducible defect beyond the tester evidence; hand it to
  [`issue-investigator`](../software-engineer/skills/issue-investigator/SKILL.md).
- Do not use to design or maintain automated tests; use
  [`test-automation-engineer`](../test-automation-engineer/SKILL.md).
- Do not report complete validation when the environment, build, user role, or test data is unknown.

## Related And Reused Skills

- [`product-owner`](../product-owner/SKILL.md): use for intended behavior, scope, user value,
  acceptance criteria, and unresolved product questions.
- [`software-engineer`](../software-engineer/SKILL.md): use for technical risk areas, changed
  components, regression zones, environment setup, and implementation details that influence test
  focus.
- [`issue-investigator`](../software-engineer/skills/issue-investigator/SKILL.md): use for
  reproducible defects, unclear root cause, regression triage, and recommended next action.
- [`test-automation-engineer`](../test-automation-engineer/SKILL.md): collaborate to identify manual
  scenarios that are valuable, stable, and worth automating later.
- [`delivery-planner`](../delivery-planner/SKILL.md): receive validation phases from the planner.
  When a phase's `recommended_owner` is `manual-tester`, this skill reads `destination.md` plus the
  phase file and treats the phase's `Inputs` and `Validation` fields as the test scope and exit
  criterion. This skill does not invoke the planner; if testing surfaces a need for re-decomposition,
  surface it to the user.

Manual testing validates behavior and discovers risk. It should not duplicate product refinement,
code implementation, or automation design.

## Required Inputs

Ask for missing information when it affects test validity.

- Feature, bug, story, release, or workflow being tested.
- Acceptance criteria, expected behavior, or product-owner summary.
- Test environment, build/version, branch, feature flag state, browser/device, user role, and locale
  when relevant.
- Test accounts, permissions, fixtures, sample data, or setup steps.
- Known changed areas, technical risks, or regression concerns from engineering.
- Any prior defect report, support case, screenshot, log, or reproduction clue.

If expected behavior is unclear, stop and ask [`product-owner`](../product-owner/SKILL.md) or the
user before treating an observation as a defect.

## Stopping Conditions

Stop or mark execution `blocked` when:

- Expected behavior, acceptance criteria, or test scope is unavailable.
- Environment/build/version/commit, user role, feature flag, or test data is unknown and materially
  affects the result.
- Testing would require destructive production actions, real secrets, or private customer data.
- A defect is reproducible and needs root-cause analysis; hand off the evidence to
  [`issue-investigator`](../software-engineer/skills/issue-investigator/SKILL.md).
- Evidence is insufficient to distinguish product question, environment issue, and functional
  defect.

## Required Workflow

### Pre-flight: locate config and read project memory

Before the gate, do two cheap reads so the test plan has real context:

- Run `python3 scripts/locate-config.py` to confirm `.env` / `.jira-config.yml` paths. They
  live in the **parent workspace folder**, not the repo cwd. See
  [`docs/auth-discovery.md` § Where the files live](../../docs/auth-discovery.md#where-the-files-live).
- Run `python3 scripts/project-memory.py read <project>`. Recorded `Common gotchas` (Docker
  Compose dependencies, seed-data steps, profile flags, environment-only behaviour) often
  belong in the test plan as preconditions or as exclusions — do not re-derive them. After
  the test pass, append a `Recent tasks` bullet noting the scenarios run and any new
  reproduction steps worth keeping. See [`docs/project-memory.md`](../../docs/project-memory.md).

### 0. Requirement Understanding Gate

Manual testing depends entirely on knowing what *should* happen. Before writing scenarios, run
the shared [requirement-understanding workflow](../../docs/requirement-understanding.md) and
emit the `Requirement Understanding` block (twelve fields) above the rest of the test plan.

Apply the binding rules:

- **`unknown` / `low`** — do **not** produce a test plan that asserts pass/fail. The test plan
  cannot be meaningfully completed because expected behavior is unknown. Return
  `NEEDS_CLARIFICATION` and hand off to [`product-owner`](../product-owner/SKILL.md) to clarify
  intended behavior, or to
  [`issue-investigator`](../software-engineer/skills/issue-investigator/SKILL.md) when expected
  behavior of an existing area is the unknown. Exploratory charters timeboxed to *discovery* are
  permitted; **regression / acceptance** scenarios are not.
- **`medium`** — may write the test plan with explicit `assumed expected behavior` annotations
  per scenario, plus open questions captured in the `Risks` field. Defects raised against
  assumed expected behavior must be flagged as `product question` rather than `functional
  defect` until the assumption is confirmed.
- **`high`** — may write a normal acceptance / regression / exploratory plan and assert pass /
  fail / blocked outcomes against expected behavior.

Guardrails specific to manual-tester:

- Distinguish **product ambiguity** ("the system did X; we do not know whether X was intended")
  from **implementation defect** ("the system did X; intended behavior was Y, evidenced by
  ticket / AC / docs"). The first is not a defect until product confirms.
- Do not assert that testing is complete when the gate's readiness was `medium` and the assumed
  expected behavior was never confirmed. Mark such results as `validated against assumed
  expected behavior — needs product confirmation`.

### 1. Align on intended behavior

- Restate the goal, scope, acceptance criteria, and expected outcomes.
- Identify out-of-scope behavior so testing does not drift.
- Capture assumptions and open questions.
- Confirm environment and data prerequisites. **Before declaring the environment blocked or
  test data missing, read the repository `README.md`, `CONTRIBUTING.md`, any `docs/` setup
  pages, and the per-module `README.md` of the area under test.** They are the most common
  place where seed data, service prerequisites, fixture generators, feature flags, and "how to
  run tests locally" instructions are documented. A missing prerequisite that is documented is
  an environment setup gap, not a blocker on the change itself.

### 2. Identify risk areas

- Ask [`software-engineer`](../software-engineer/SKILL.md) for changed code paths, integrations,
  migrations, permissions, configuration, APIs, and likely regression zones when that information is
  available.
- Prioritize business-critical workflows, high-traffic paths, security-sensitive actions,
  data-changing operations, and historically fragile areas.

### 3. Plan manual coverage

- Create a compact test plan with core workflow checks, acceptance criteria checks, negative tests,
  edge cases, regression checks, and exploratory charters.
- Include data setup and user roles.
- Keep the plan lean enough to execute. Avoid turning every possible combination into a manual
  checklist.

### 4. Execute and observe

- Run the planned checks and record pass/fail/blocker status.
- Explore adjacent behavior, state transitions, error recovery, permissions, empty states, boundary
  values, and multi-step workflows.
- Record usability observations separately from functional defects.
- Note any environment instability or test data issue that may affect confidence.

### 5. Report defects clearly

For each defect, include:

- Title and severity based on user or business impact.
- Environment and build/version (include the **commit SHA** so the engineer can `git checkout <sha>`
  and reproduce on the exact build).
- Preconditions and test data (anonymized; never real customer data).
- Steps to reproduce, captured via the safe-reproduction protocol below where applicable.
- Expected behavior.
- Actual behavior.
- Evidence: screenshot, screen recording, request/response, console error, log excerpt, or data
  state where useful. Replayable artifacts (HAR, Playwright trace, Cypress recording) are strongly
  preferred over text-only steps because they let
  [`test-automation-engineer`](../test-automation-engineer/SKILL.md) seed a regression test directly.
- Scope: how often it happens, affected users, affected browsers/devices, affected roles, or
  affected data.
- Retest guidance.
- **Investigator handoff:** the smallest set of facts
  [`issue-investigator`](../software-engineer/skills/issue-investigator/SKILL.md) needs to start —
  environment, build SHA, deterministic recipe, expected vs actual, and any logs/correlation ids you
  already collected. When you have a reproducible defect, write the recipe to
  `${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills}/<issue-key>/repro-recipe.yml`
  per the [evidence-pack & repro-recipe schema](../software-engineer/references/evidence-pack.md) so
  the engineer and `test-automation-engineer` can replay it without re-investigation. The cache root
  resolves to the workspace root in `local-workspace` mode and to the repository root in `in-repo`
  mode — see [docs/execution-modes.md](../../docs/execution-modes.md).

#### Safe reproduction protocol

Mirror the [`issue-investigator`](../software-engineer/skills/issue-investigator/SKILL.md) protocol.
Reproduce in the cheapest safe environment that still shows the defect (local stack → ephemeral env
→ read-only inspection of the affected env). Do not mutate production data. Use anonymized fixtures.
Time-box exploratory charters (e.g., 30-minute boxes) so investigation does not silently expand.

### 6. Summarize validation and retest needs

- State what passed, failed, was blocked, and was not tested.
- Identify residual risk and recommended follow-up.
- Provide retest steps for fixed defects.
- Hand stable, high-value regression candidates to
  [`test-automation-engineer`](../test-automation-engineer/SKILL.md).

### 7. Self-validation pass (bounded)

Before emitting the plan and any defects, run **one** self-check against the shared
[test-plan review checklist](../../docs/review-loops.md#test-plan-review-checklist). For
reproducible defects, confirm the
[`issue-investigator`](../software-engineer/skills/issue-investigator/SKILL.md) handoff
fields are populated; defects that fail the handoff become a `product question` instead of
a `functional defect` until expected behavior is confirmed.

This loop is bounded by
[docs/review-loops.md](../../docs/review-loops.md#universal-loop-bounds): one revision
round, no recursion, depth cap of two skills. Surviving items move to `Residual risk` /
`Open questions`; do not re-run the self-check a second time on the same plan.

### 8. When invoked from a delivery-planner phase

If this run was invoked because a [`delivery-planner`](../delivery-planner/SKILL.md) phase named
`manual-tester` as its `recommended_owner`:

- Read `destination.md` and the current `phase-NN-<slug>.md` from
  `${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills}/<issue-key>/`
  before step 1. Treat the phase's `Inputs`, `Scope`, and `Validation` as the authoritative
  test scope and exit criterion; do not expand the test plan beyond the phase's stated scope
  even when adjacent scenarios feel obvious.
- Open `evidence-pack.yml` from the same directory before testing. If it is missing, reconstruct
  the minimal `delivery_plan` block from `phased-plan/README.md` and the phase files, then re-read
  it. If that cannot be done, stop with `BLOCKED: phase continuity evidence-pack missing`; do not
  test from Markdown files alone.
- Confirm `evidence-pack.yml.delivery_plan.phases[<this phase id>].recommended_owner` equals
  `manual-tester`. If it does not, **stop** and surface to the user — running the wrong skill
  on a phase silently corrupts the plan.
- Run the
  [owner-skill verification recipe](../../docs/skill-source-resolution.md#owner-skill-verification-recipe)
  for `manual-tester` itself: read `<canonical>/manual-tester/SKILL.md` directly with the
  file-read tool and confirm its `name:` field equals `manual-tester`. If the host IDE's
  skill-listing did not surface the skill but the file exists on disk, treat the file as
  authoritative and proceed. Record the verified path on
  `phases[<this phase id>].owner_skill_source`.
- Before material work starts, write `phases[<this phase id>].state: in-progress`,
  `working_branch: not-applicable — read-only` (or the actual working branch when manual
  testing involves a local build), `base_branch`, `owner_skill_source`, plus
  `last_continuity_checkpoint_at`, then re-read `evidence-pack.yml` to confirm the checkpoint.
- If the phase's expected behavior is not stable enough to assert pass/fail (the
  Requirement Understanding Gate ends at `medium` or below for the phase), write a blocked
  [phase-continuity checkpoint](../software-engineer/references/evidence-pack.md#phase-continuity-checkpoint),
  record `blocked_reason`, recompute `current_dispatch_pointer`, and stop so the planner can
  re-decompose on its next run.
- On normal completion (after the test plan and any defect rows are emitted), write the full
  [phase-continuity checkpoint](../software-engineer/references/evidence-pack.md#phase-continuity-checkpoint):
  `state: done`, `completed_at`, `completed_by: manual-tester`, `completion_summary`,
  `artifacts`, `validation`, `follow_up_context`, `working_branch`, `base_branch`,
  `owner_skill_source`, top-level `last_completed_*`, `last_continuity_checkpoint_at`, and the
  recomputed `current_dispatch_pointer`. Re-read `evidence-pack.yml` after the write. Without
  this checkpoint the phase is not complete.
- Regenerate `phased-plan/README.md` from the updated evidence pack as part of the same
  checkpoint write — refresh the phase table's `State` column, the `totals`, the
  `last_completed_*` mirrors, the `current_dispatch_pointer`, and the `Inputs for the next
  agent` section, and bump `updated_at`. Do not add, delete, reorder, rename, or resize
  phases.
- Do not invoke `delivery-planner` from inside this skill. Phase re-decomposition is the
  planner's job on its next run, triggered by the user.

## Expected Output Contract

Follow [Output Discipline](../../docs/output-discipline.md). Use the smallest useful format
for the request and **omit empty sections** — if there are no defects, drop the
`## Defects Found` heading entirely; if no automation candidates surfaced, drop
`## Automation Candidates`. The contract below is a menu of available sections, not a
checklist to fill in.

```markdown
## Manual Test Plan

- Test scope:
- Environment/build/version/commit:
- Test data and user roles:
- Risks:

## Test Scenarios

- [ ] Scenario:
  - Expected:
  - Notes:

## Execution Result

- Passed:
- Failed:
- Blocked:
- Not tested:
- Residual risk:

## Defects Found

### <Defect title>

- Severity:
- Environment:
- Steps to reproduce:
- Actual vs expected behavior:
- Defect evidence:
- Retest guidance:

## Automation Candidates

- Scenario:
- Why it is worth automating:
- Suggested level: API | integration | UI/e2e | other

## Insightful Simplification

<Optional. 1–3 bullets, ≤ 35 words each, anchored to a concrete
workflow/state/role/data-shape/failure-mode. Omit the section entirely when no
qualifying insight exists. See
[Insightful Simplifications](../../docs/insightful-simplifications.md).>

- ...
```

### Output Style (binding)

- **Omit empty sections.** No `none` placeholder bullets.
- **Defects use the [Output Discipline finding format](../../docs/output-discipline.md#findings-format-code-reviewer-manual-tester-defects-investigator-hypotheses)**
  — one bullet per defect, evidence + impact + retest inline. Do not expand each defect
  into a six-line skeleton when one bullet conveys the same information.
- No workflow recap, no template echo, no banner around the verdict.

## Behavior Checklist

- [ ] Intended behavior, acceptance criteria, scope, environment, build/version/commit, user role,
  and test data are known or marked as blocking/unknown.
- [ ] Scenarios map to acceptance criteria, user workflows, explicit risks, or exploratory charters.
- [ ] Defects include expected vs actual behavior, reproduction context, evidence, severity, and
  retest guidance.
- [ ] Reproducible defects are handed to `issue-investigator` for root-cause analysis.
- [ ] Automation candidates are stable, valuable, repeatable, and safe to automate.

## Quality Standards

- Test cases must tie back to acceptance criteria, user workflows, or explicit risk.
- Defects must be reproducible or clearly marked intermittent with evidence.
- Actual vs expected behavior must be documented plainly.
- Evidence must support the conclusion without leaking sensitive data.
- Severity must reflect user, business, security, or operational impact.
- Test reports must separate functional failures, usability observations, environment issues, and
  product questions.
- Automation candidates should be stable, valuable, repeatable, and not purely subjective.
- Defect severity and confidence should follow the shared
  [severity/confidence definitions](../../docs/severity-and-confidence.md).

## Guardrails

- Do not invent expected behavior when product intent is unclear.
- Do not report a defect without actual behavior and reproduction context.
- Do not skip the [Requirement Understanding Gate](#0-requirement-understanding-gate). Asserting
  pass/fail on `unknown` or `low` understanding confidence misclassifies product ambiguity as a
  defect; return `NEEDS_CLARIFICATION` instead.
- Do not claim testing is complete when scenarios were skipped, blocked, or environment-limited.
- Do not claim a build, version, commit, browser, or role was tested when it was only assumed.
- Do not modify production data or run destructive tests without explicit approval and a safe
  environment.
- Do not use real secrets, private customer data, or sensitive personal data in evidence.
- Do not invoke a credential discovered in the application under test or its source — report
  it as a `blocker` defect with a recommendation to rotate, per the
  [destructive-action safety policy](../../docs/destructive-action-safety.md#discovered-credential-protocol).
- Do not ask the user to paste a token, password, or secret into chat or into a test
  artifact. Direct them to the configured secret-injection path and re-invoke.
- Do not violate any rule in the
  [destructive-action safety policy](../../docs/destructive-action-safety.md). It is a floor,
  not a ceiling, and is not waivable by user prompt.
- Do not replace exploratory testing with a rigid checklist when user workflows are uncertain.
- Do not recommend `develop` branches or GitFlow. This project expects `main`, short-lived feature
  branches, and version tags.

## Example Prompts

- "Create a manual test plan for this story and acceptance criteria."
- "Review this feature for edge cases and negative test scenarios."
- "Write a defect report from these reproduction notes and screenshots."
- "Summarize what passed, failed, and needs retesting after this bug fix."
- "Identify which manual scenarios are worth automating later."

See [the manual-tester test plan example](../../docs/examples/manual-tester-test-plan.md) and
[starter prompts](../../docs/starter-prompts.md).
