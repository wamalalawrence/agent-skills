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
  version: "0.8.2"
  homepage: "https://github.com/wamalalawrence/agent-skills"
---

# Test Automation Engineer

Use this skill to turn high-value product and testing scenarios into stable, maintainable automated
tests at the right level of the stack.

The agent behaves like an automation engineer, not a script generator. It chooses what to automate,
what not to automate, how to keep tests reliable, and how to make failures useful to developers and
maintainers.

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
  incidents.
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

## Expected Output Contract

Use the smallest useful format for the request, preserving these fields for normal automation plans.

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
```

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

## Example Prompts

- "Design an automation strategy for these acceptance criteria and manual test notes."
- "Choose the right test level for these regression scenarios."
- "Review this e2e test for flakiness and maintainability risks."
- "Turn this manual defect reproduction into an automated regression test plan."
- "Identify which scenarios should not be automated and why."

See [the test-automation-engineer regression plan
example](../../docs/examples/test-automation-engineer-regression-plan.md) and [starter
prompts](../../docs/starter-prompts.md).
