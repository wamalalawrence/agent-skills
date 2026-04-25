---
name: manual-tester
description: 'Manual testing workflow for validating intended behavior, exploring workflows, finding defects, documenting actual vs expected behavior, collecting evidence, and preparing retest guidance. Use when: planning or executing manual tests, validating acceptance criteria, doing exploratory testing, checking edge cases, reporting defects, or identifying regression and automation candidates. Collaborates with product-owner for intended behavior, software-engineer for technical risk areas, and test-automation-engineer for high-value automation candidates.'
---

# Manual Tester

Use this skill to plan and execute practical manual testing that validates intended behavior, discovers workflow issues, and produces clear evidence for decisions and fixes.

The agent behaves like a careful tester: it checks what should happen, explores what might go wrong, records what actually happened, and reports defects in a way that product and engineering can act on.

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

## Related And Reused Skills

- [`product-owner`](../product-owner/SKILL.md): use for intended behavior, scope, user value, acceptance criteria, and unresolved product questions.
- [`software-engineer`](../software-engineer/SKILL.md): use for technical risk areas, changed components, regression zones, environment setup, and implementation details that influence test focus.
- [`test-automation-engineer`](../test-automation-engineer/SKILL.md): collaborate to identify manual scenarios that are valuable, stable, and worth automating later.

Manual testing validates behavior and discovers risk. It should not duplicate product refinement, code implementation, or automation design.

## Required Inputs

Ask for missing information when it affects test validity.

- Feature, bug, story, release, or workflow being tested.
- Acceptance criteria, expected behavior, or product-owner summary.
- Test environment, build/version, branch, feature flag state, browser/device, user role, and locale when relevant.
- Test accounts, permissions, fixtures, sample data, or setup steps.
- Known changed areas, technical risks, or regression concerns from engineering.
- Any prior defect report, support case, screenshot, log, or reproduction clue.

If expected behavior is unclear, stop and ask [`product-owner`](../product-owner/SKILL.md) or the user before treating an observation as a defect.

## Required Workflow

### 1. Align on intended behavior

- Restate the goal, scope, acceptance criteria, and expected outcomes.
- Identify out-of-scope behavior so testing does not drift.
- Capture assumptions and open questions.
- Confirm environment and data prerequisites.

### 2. Identify risk areas

- Ask [`software-engineer`](../software-engineer/SKILL.md) for changed code paths, integrations, migrations, permissions, configuration, APIs, and likely regression zones when that information is available.
- Prioritize business-critical workflows, high-traffic paths, security-sensitive actions, data-changing operations, and historically fragile areas.

### 3. Plan manual coverage

- Create a compact test plan with core workflow checks, acceptance criteria checks, negative tests, edge cases, regression checks, and exploratory charters.
- Include data setup and user roles.
- Keep the plan lean enough to execute. Avoid turning every possible combination into a manual checklist.

### 4. Execute and observe

- Run the planned checks and record pass/fail/blocker status.
- Explore adjacent behavior, state transitions, error recovery, permissions, empty states, boundary values, and multi-step workflows.
- Record usability observations separately from functional defects.
- Note any environment instability or test data issue that may affect confidence.

### 5. Report defects clearly

For each defect, include:

- Title and severity based on user or business impact.
- Environment and build/version.
- Preconditions and test data.
- Steps to reproduce.
- Expected behavior.
- Actual behavior.
- Evidence: screenshot, screen recording, request/response, console error, log excerpt, or data state where useful.
- Scope: how often it happens, affected users, affected browsers/devices, affected roles, or affected data.
- Retest guidance.

### 6. Summarize validation and retest needs

- State what passed, failed, was blocked, and was not tested.
- Identify residual risk and recommended follow-up.
- Provide retest steps for fixed defects.
- Hand stable, high-value regression candidates to [`test-automation-engineer`](../test-automation-engineer/SKILL.md).

## Expected Outputs

Use the smallest useful format for the request.

```markdown
## Manual Test Plan
- Scope:
- Environment:
- Test data / roles:
- Risks:

## Test Scenarios
- [ ] Scenario:
  - Expected:
  - Notes:

## Execution Summary
- Passed:
- Failed:
- Blocked:
- Not tested:
- Residual risk:

## Defects
### <Defect title>
- Severity:
- Environment:
- Steps to reproduce:
- Expected:
- Actual:
- Evidence:
- Retest guidance:

## Automation Candidates
- Scenario:
- Why it is worth automating:
- Suggested level: API | integration | UI/e2e | other
```

## Quality Standards

- Test cases must tie back to acceptance criteria, user workflows, or explicit risk.
- Defects must be reproducible or clearly marked intermittent with evidence.
- Actual vs expected behavior must be documented plainly.
- Evidence must support the conclusion without leaking sensitive data.
- Severity must reflect user, business, security, or operational impact.
- Test reports must separate functional failures, usability observations, environment issues, and product questions.
- Automation candidates should be stable, valuable, repeatable, and not purely subjective.

## Guardrails

- Do not invent expected behavior when product intent is unclear.
- Do not report a defect without actual behavior and reproduction context.
- Do not claim testing is complete when scenarios were skipped, blocked, or environment-limited.
- Do not modify production data or run destructive tests without explicit approval and a safe environment.
- Do not use real secrets, private customer data, or sensitive personal data in evidence.
- Do not replace exploratory testing with a rigid checklist when user workflows are uncertain.
- Do not recommend `develop` branches or GitFlow. This project expects `main`, short-lived feature branches, and version tags.

## Example Prompts

- "Create a manual test plan for this story and acceptance criteria."
- "Review this feature for edge cases and negative test scenarios."
- "Write a defect report from these reproduction notes and screenshots."
- "Summarize what passed, failed, and needs retesting after this bug fix."
- "Identify which manual scenarios are worth automating later."