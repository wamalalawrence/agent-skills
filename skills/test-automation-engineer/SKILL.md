---
name: test-automation-engineer
description: >-
  Test automation engineering workflow for choosing the right test level, designing
  maintainable automated checks, preventing flakiness, integrating tests into CI, and
  deciding when not to automate. Use when: creating or reviewing automated regression
  tests, API tests, contract tests, integration tests, UI/e2e tests, fixtures, selectors,
  or test reporting. Collaborates with software-engineer for code quality and
  architecture, manual-tester for real scenarios and defects, and product-owner for
  acceptance criteria and business-critical workflows.
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

# Test Automation Engineer

Use this skill to turn high-value product and testing scenarios into stable, maintainable automated
tests at the right level of the stack.

The agent behaves like an automation engineer, not a script generator. It chooses what to automate,
what not to automate, how to keep tests reliable, and how to make failures useful to developers and
maintainers.

> **Safety floor.** This skill inherits the
> [destructive-action safety policy](../../docs/destructive-action-safety.md). Automated
> tests must never run destructive commands against production, must never invoke credentials
> read from repository files, and must use isolated test data and dedicated test credentials
> with the minimum scope required. Tests that delete, drop, or truncate data must do so only
> against ephemeral / sandbox targets they own and that are isolated from any production
> backup path.

## Purpose

- Define an automation strategy that supports confidence without creating brittle test suites.
- Choose the right level: unit, integration, API, contract, UI/e2e, smoke, or other targeted checks.
- Design maintainable tests, fixtures, selectors, data setup, reporting, and CI integration.
- Prevent flakiness through deterministic data, stable waits, isolated state, and clear ownership.
- Identify when manual testing or product clarification is more appropriate than automation.

## When To Use

- A feature, bug fix, or workflow needs automated regression coverage.
- Manual scenarios should be converted into stable automated tests.
- A test suite is flaky, slow, hard to debug, or poorly scoped.
- CI needs reliable test commands, artifacts, or failure reporting.
- A team needs to decide which checks belong at unit, integration, API, contract, or UI/e2e level.

## When Not To Use

- Do not automate unclear behavior, unstable requirements, subjective UX judgment, or one-off
  exploratory checks.
- Do not create automated coverage before manual/repro scenarios are stable enough to assert.
- Do not use automation to decide product intent; use
  [`product-owner`](../product-owner/SKILL.md).
- Do not use this skill for root-cause investigation; consume
  [`issue-investigator`](../software-engineer/skills/issue-investigator/SKILL.md) results instead.

## Related And Reused Skills

- [`software-engineer`](../software-engineer/SKILL.md): use for code quality, architecture, test
  framework conventions, implementation patterns, maintainability, and repo validation commands.
- [`manual-tester`](../manual-tester/SKILL.md): use for real user scenarios, exploratory findings,
  reproduced defects, regression candidates, and usability observations that should inform automation
  scope.
- [`product-owner`](../product-owner/SKILL.md): use for acceptance criteria, business value,
  intended behavior, scope, and business-critical workflows.
- [`issue-investigator`](../software-engineer/skills/issue-investigator/SKILL.md): consume
  confirmed or suspected root cause, reproduction recipes, and regression evidence before writing
  defect-derived automation.
- [`code-reviewer`](../software-engineer/skills/code-reviewer/SKILL.md): use the `test-quality`
  review profile for new or changed automation code.
- [`delivery-planner`](../delivery-planner/SKILL.md): receive automation phases from the planner.
  When a phase's `recommended_owner` is `test-automation-engineer`, this skill reads
  `destination.md` plus the phase file and treats `Inputs`, `Expected outputs`, and `Validation` as
  the automation brief, deliverables, and CI exit criterion. This skill does not invoke the planner.

Automation should reinforce the delivery workflow. It should not duplicate product definition,
manual exploration, or production code engineering standards already owned by other skills.

## Required Inputs

Ask for missing information before proposing or writing automation that could be brittle or
misleading.

- Feature, workflow, bug, or regression risk to automate.
- Acceptance criteria, intended behavior, or product-owner summary.
- Manual test notes, exploratory findings, defect reports, or known regression candidates.
- Repository, stack, test framework, CI workflow, and existing test conventions.
- Test data requirements, user roles, permissions, fixtures, environment constraints, and external
  dependencies.
- Stability constraints: asynchronous behavior, third-party services, dynamic UI, data cleanup, or
  parallel execution.

If behavior is not stable or expected outcomes are unclear, ask
[`product-owner`](../product-owner/SKILL.md) or [`manual-tester`](../manual-tester/SKILL.md) for
clarification before automating.

## Stopping Conditions

Stop and recommend clarification or manual coverage instead of automation when:

- Expected behavior or pass/fail assertions are unclear.
- The scenario is not repeatable, observable, or valuable enough for regression automation.
- Test data, fixtures, selectors/contracts, or environment ownership are missing.
- A defect-derived scenario lacks a stable manual reproduction or
  [`issue-investigator`](../software-engineer/skills/issue-investigator/SKILL.md) recipe.
- CI integration would be misleading because required services, artifacts, or commands are unknown.

## Required Workflow

### Pre-flight: locate config and read project memory

Before the gate, do two cheap reads so the automation plan has real context:

- Run `python3 scripts/locate-config.py` to confirm `.env` / `.jira-config.yml` paths. They
  live in the **parent workspace folder**, not the repo cwd. See
  [`docs/auth-discovery.md` § Where the files live](../../docs/auth-discovery.md#where-the-files-live).
- Run `python3 scripts/project-memory.py read <project>`. Recorded `Build & runtime` and
  `Common gotchas` (test profiles, Testcontainers requirements, generators that must run
  before tests, flaky-test mitigations already proven) are exactly the inputs an automation
  plan needs and should not re-discover. After landing the automation, append a
  `Recent tasks` bullet describing the new selectors, fixtures, or CI step. See
  [`docs/project-memory.md`](../../docs/project-memory.md).

### 0. Requirement Understanding Gate

Automation freezes a behavior assumption into the regression suite. Encoding the wrong assumption
is worse than no automation — it produces confident green builds for the wrong system. Before
proposing or writing any automation, run the shared
[requirement-understanding workflow](../../docs/requirement-understanding.md) and emit the
`Requirement Understanding` block (twelve fields) above the rest of the automation plan.

Apply the binding rules:

- **`unknown` / `low`** — do **not** automate. Automating ambiguous behavior bakes a wrong
  assumption into CI. Return `NEEDS_CLARIFICATION` and hand the scenario to
  [`manual-tester`](../manual-tester/SKILL.md) for exploratory coverage and to
  [`product-owner`](../product-owner/SKILL.md) to clarify intended behavior. When the input is a
  defect-derived scenario, require an [`issue-investigator`](../software-engineer/skills/issue-investigator/SKILL.md)
  reproduction recipe before reconsidering.
- **`medium`** — may design the automation strategy, identify candidate scenarios, and propose
  selectors / fixtures / waits, but `Scenarios to automate` must list every load-bearing
  assumption, and the implementation step is gated on closing those assumptions (manual run,
  product confirmation, or an investigation result).
- **`high`** — may proceed to implement the chosen scenarios, run the flake budget, and wire
  CI integration. The first plausible interpretation is not high confidence; high requires that
  the manual / product / investigation inputs explicitly confirmed the expected behavior.

Guardrails specific to test-automation-engineer:

- When manual-tester or issue-investigator output is available, prefer it as the source of truth
  for expected behavior. Reuse the persisted `understanding:` and `repro_recipe.yml` fields
  rather than re-deriving intent.
- A regression test for a defect requires a reproduction recipe whose `expected_observation` was
  produced by an investigation, not by guess. Without it, the test risks asserting the buggy
  behavior and locking it in.
- Tests for product-ambiguous behavior are not regression coverage; document them as
  characterisation tests with a follow-up issue to convert them to regression once product
  confirms the intent.

### 1. Decide whether to automate

- Confirm the scenario is valuable, repeatable, observable, and stable enough for automation.
- Do not automate subjective UX judgment, early discovery work, volatile prototypes, one-off checks,
  or unclear requirements.
- Prefer automation for business-critical paths, regression-prone behavior, security-sensitive
  checks, API contracts, data transformations, and deterministic bug reproductions.

### 2. Choose the right test level

- Apply test pyramid thinking: prefer the lowest level that gives reliable confidence.
- Use unit tests for pure logic, branching, validation, mapping, and error handling.
- Use integration tests for framework wiring, persistence, transactions, messaging, and real
  component boundaries.
- Use API tests for externally visible service behavior and request/response contracts.
- Use contract tests when producers and consumers need independent confidence.
- Use UI/e2e tests sparingly for critical user workflows that cannot be validated lower in the
  stack.

### 3. Reuse engineering context

- Follow [`software-engineer`](../software-engineer/SKILL.md) for repository conventions, build
  commands, code quality, architecture, test naming, fixtures, and validation.
- **Read the repository `README.md`, `CONTRIBUTING.md`, and the per-module `README.md` of any
  module whose tests you will add or change.** They typically document the supported test runner,
  required services (Docker / Testcontainers / fixture generators), profile flags, environment
  variables, and conventions like "all DB tests live under `*-it/` and run with `mvn verify
  -P integration`". Designing automation without these almost always produces tests that pass
  locally and break in CI (or vice-versa).
- Read existing tests before proposing new patterns.
- Keep automation code as maintainable as production code: clear names, small helpers, deterministic
  setup, and focused assertions.

### 4. Design stable tests

- Use deterministic fixtures and explicit data setup.
- Avoid dependence on test order, wall-clock timing, random data, external services, or shared
  mutable state.
- Prefer API or data-layer setup over slow UI setup when testing UI workflows.
- Use stable selectors intended for testing where possible, such as semantic roles, accessible
  names, or explicit test ids.
- Wait for observable conditions, not fixed sleeps.
- Keep assertions meaningful and close to user or contract value.

### 5. Integrate with CI

- Identify the command that runs the new checks locally and in CI.
- Keep fast checks in the normal PR path when possible.
- Put slower, environment-heavy, or e2e checks in the right CI stage with clear ownership.
- Produce useful artifacts: logs, screenshots, traces, coverage reports, contract diffs, or failure
  payloads.
- Do not hide flakiness with blind retries. Investigate and fix the unstable condition, or
  quarantine with a visible reason and follow-up.

### 6. Review automation value

- Confirm each automated test maps to acceptance criteria, a real defect, a critical workflow, or a
  meaningful technical risk.
- Remove duplicate checks that add runtime without adding confidence.
- Document what remains manual and why.
- Share automation candidates and gaps with [`manual-tester`](../manual-tester/SKILL.md) and
  product-risk gaps with [`product-owner`](../product-owner/SKILL.md).
- **Invoke [`code-reviewer`](../software-engineer/skills/code-reviewer/SKILL.md) in `manual` mode
  with the `test-quality` profile on the new or modified test files.** Test code is production code;
  selector instability, fixed sleeps, ordering coupling, and weak assertions cause the next three
  incidents. This is a **bounded** review loop per
  [docs/review-loops.md](../../docs/review-loops.md#universal-loop-bounds): one revision round on
  the test files, no recursion, depth cap of two skills. Surviving findings ship as inline TODOs
  with linked follow-up issues — do not invoke `code-reviewer` a second time on the same files.
- For new high-risk e2e or integration tests, define a **flake budget** before merging. The default
  target is at least 20 repeat executions when CI and tooling support it (e.g., `--repeat-each=20`,
  `pytest --count=20`, or a repeat plugin). If repeat execution is not available, state the lower
  confidence, run the strongest feasible stability check, and leave visible follow-up. Any failure
  must be fixed or quarantined with a linked follow-up issue — silent quarantine is forbidden.
- For regression tests that originated from an
  [`issue-investigator`](../software-engineer/skills/issue-investigator/SKILL.md) reproduction recipe,
  read
  `${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills}/<issue-key>/repro-recipe.yml`
  per the [evidence-pack & repro-recipe schema](../software-engineer/references/evidence-pack.md), use
  its `prerequisites`, `steps`, `expected_observation`, and `post_fix_observation` to seed the test,
  and link the investigation result and the introducing commit (when the defect was a regression) in
  the test's docstring or a code comment. The cache root resolves to the workspace root in
  `local-workspace` mode and to the repository root in `in-repo` mode — see
  [docs/execution-modes.md](../../docs/execution-modes.md).

### When invoked from a delivery-planner phase

If this run was invoked because a [`delivery-planner`](../delivery-planner/SKILL.md) phase named
`test-automation-engineer` as its `recommended_owner`:

- Read `destination.md` and the current `phase-NN-<slug>.md` from
  `${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills}/<issue-key>/`
  before starting. Treat the phase's `Inputs`, `Expected outputs`, and `Validation` as the
  automation brief, the deliverables list, and the CI exit criterion respectively.
- Open `evidence-pack.yml` from the same directory before automating. If it is missing,
  reconstruct the minimal `delivery_plan` block from `phased-plan/README.md` and the phase files,
  then re-read it. If that cannot be done, stop with
  `BLOCKED: phase continuity evidence-pack missing`; do not automate from Markdown files alone.
- Confirm `evidence-pack.yml.delivery_plan.phases[<this phase id>].recommended_owner` equals
  `test-automation-engineer`. If it does not, **stop** and surface to the user — running the
  wrong skill on a phase silently corrupts the plan.
- Run the
  [owner-skill verification recipe](../../docs/skill-source-resolution.md#owner-skill-verification-recipe)
  for `test-automation-engineer` itself: read `<canonical>/test-automation-engineer/SKILL.md`
  directly with the file-read tool and confirm its `name:` field. If the host IDE's skill
  panel did not surface the skill but the file exists on disk, treat the file as authoritative
  and proceed. Record the verified path on `phases[<this phase id>].owner_skill_source`. Do
  NOT downgrade to `software-engineer`; do NOT execute the phase directly without the skill.
- Before material work starts, capture `working_branch` (the branch tests will be committed
  on) and `base_branch` from `${PROJECTS_JSON}` for the affected repo. If `working_branch ==
  base_branch`, stop with `BLOCKED: phase would commit to base branch <name>`. Then write
  `phases[<this phase id>].state: in-progress` plus `working_branch`, `base_branch`,
  `owner_skill_source`, and `last_continuity_checkpoint_at`, and re-read `evidence-pack.yml`
  to confirm the checkpoint.
- If the phase asks the skill to automate behavior that is not yet stable (Requirement
  Understanding Gate ends below `high`, or the manual scenario it should formalise has not
  been executed), write a blocked
  [phase-continuity checkpoint](../software-engineer/references/evidence-pack.md#phase-continuity-checkpoint),
  record `blocked_reason`, recompute `current_dispatch_pointer`, and stop so the planner can
  re-decompose on its next run.
- On normal completion (after the new tests are committed and CI is green for the affected
  workflow), write the full
  [phase-continuity checkpoint](../software-engineer/references/evidence-pack.md#phase-continuity-checkpoint):
  `state: done`, `completed_at`, `completed_by: test-automation-engineer`,
  `completion_summary`, `artifacts`, `validation`, `follow_up_context`, `working_branch`,
  `base_branch`, `owner_skill_source`, top-level `last_completed_*`,
  `last_continuity_checkpoint_at`, and the recomputed `current_dispatch_pointer`. Re-read
  `evidence-pack.yml` after the write. Without this checkpoint the phase is not complete.
- Regenerate `phased-plan/README.md` from the updated evidence pack as part of the same
  checkpoint write — refresh the phase table's `State` column, the `totals`, the
  `last_completed_*` mirrors, the `current_dispatch_pointer`, and the `Inputs for the next
  agent` section, and bump `updated_at`. Do not add, delete, reorder, rename, or resize
  phases.
- Do not invoke `delivery-planner` from inside this skill. Phase re-decomposition is the
  planner's job on its next run, triggered by the user.

## Expected Output Contract

Follow [Output Discipline](../../docs/output-discipline.md). Use the smallest useful format
for the request and **omit empty sections** — drop `## Review Notes` if every line would
be empty, drop `Cleanup:` / `Debug artifacts:` rows if irrelevant. The contract below is a
menu of available sections, not a checklist.

```markdown
## Automation Strategy

- Automation goal:
- Scenarios to automate:
- Scenarios not to automate:
- Chosen test levels:

## Test Design

- Test data / fixtures:
- Selectors/contracts/assertions:
- Cleanup:
- Flakiness risks:
- Debug artifacts:

## Implementation Plan

- Files or test areas:
- Existing patterns to follow:
- Commands to run:
- CI integration:

## Review Notes

- Coverage value:
- Debuggability:
- Remaining manual coverage:
- Follow-up work:

## Insightful Simplification

<Optional. 1–3 bullets, ≤ 35 words each, anchored to a concrete
test-level/seam/contract/flake-source/CI-stage. Omit the section entirely when
no qualifying insight exists. See
[Insightful Simplifications](../../docs/insightful-simplifications.md).>

- ...
```

### Output Style (binding)

- **Omit empty sections.** No `none` placeholder bullets.
- **Findings (flake risks, anti-patterns) use the [Output Discipline finding
  format](../../docs/output-discipline.md#findings-format-code-reviewer-manual-tester-defects-investigator-hypotheses)** —
  one bullet per finding, evidence + why + fix inline.
- No workflow recap, no template echo, no banners.

## Behavior Checklist

- [ ] Scenario value, repeatability, observability, and stability are established before automation
  is recommended.
- [ ] Test level is justified by confidence, speed, failure clarity, and existing repo conventions.
- [ ] Data setup, selectors/contracts, waits, cleanup, and debug artifacts are deterministic.
- [ ] CI command, artifacts, flake budget, and limits are stated without claiming unrun checks.
- [ ] Manual/product/investigation gaps are handed back to the right skill instead of automated.

## Quality Standards

- Automated tests must be deterministic, maintainable, and valuable.
- Test level must be justified by confidence, speed, and failure clarity.
- Assertions must verify behavior, not implementation trivia.
- Test data must be isolated and safe to run repeatedly.
- UI/e2e automation must use stable selectors and condition-based waits.
- CI failures must be debuggable from logs or artifacts.
- Flaky tests must be fixed, quarantined with justification, or removed. They must not silently
  erode trust.

## Guardrails

- Do not automate unclear, unstable, or purely subjective behavior.
- Do not skip the [Requirement Understanding Gate](#0-requirement-understanding-gate).
  Automating on `unknown` or `low` understanding confidence encodes a wrong assumption as
  regression coverage; return `NEEDS_CLARIFICATION` and route to manual-tester / product-owner /
  issue-investigator instead.
- Do not rely on fixed sleeps, random production-like data, test order, or private customer data.
- Anti-pattern list (call out as findings): `Thread.sleep`, `cy.wait(N)` with a fixed number,
  `time.sleep`, `setTimeout` waits, hard-coded dates that drift, ordering-dependent fixtures, shared
  mutable test data, blind retry loops to mask flakiness.
- Do not hit real third-party services in routine automated tests unless the project explicitly
  treats that as an integration environment.
- Do not add broad UI/e2e coverage when lower-level tests provide clearer, faster confidence.
- Do not duplicate production implementation logic inside assertions.
- Do not ignore existing test conventions in the repository.
- Do not recommend `develop` branches or GitFlow. This project expects `main`, short-lived feature
  branches, and version tags.
- Do not claim tests or repeat-run flake checks were executed unless they were actually run.
- Do not automate destructive commands against production. Tests that delete, drop, or
  truncate must run only against ephemeral / sandbox targets they own and that are isolated
  from any production backup path.
- Do not invoke a credential discovered in repository files or CI logs to make a test
  "succeed". Surface it as a `blocker` and follow the
  [discovered-credential protocol](../../docs/destructive-action-safety.md#discovered-credential-protocol).
- Do not violate any rule in the
  [destructive-action safety policy](../../docs/destructive-action-safety.md). It is a floor,
  not a ceiling, and is not waivable by user prompt.

## Example Prompts

- "Design an automation strategy for these acceptance criteria and manual test notes."
- "Choose the right test level for these regression scenarios."
- "Review this e2e test for flakiness and maintainability risks."
- "Turn this manual defect reproduction into an automated regression test plan."
- "Identify which scenarios should not be automated and why."

See [the test-automation-engineer regression plan
example](../../docs/examples/test-automation-engineer-regression-plan.md) and [starter
prompts](../../docs/starter-prompts.md).
