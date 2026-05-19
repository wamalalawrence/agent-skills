# Starter Prompts

Copy one prompt and replace the bracketed parts. These prompts intentionally ask the skill to stop
when required evidence is missing.

> **Understanding before action.** Every prompt below assumes the skill will run the shared
> [requirement-understanding workflow](requirement-understanding.md) and emit a
> `Requirement Understanding` block at the top of the output. If the gate ends at `unknown` /
> `low` confidence, the skill must ask for clarification or evidence — even when the prompt
> asks for an implementation, a story, a test plan, or a verdict. Do not weaken the gate by
> adding "just do it" framing.

## Single-Skill Prompts

### Implement A Feature With `software-engineer`

```text
Use the software-engineer skill for this repository.

Task: [describe the feature or change]
Context: [link or paste issue, acceptance criteria, design notes, constraints]

First gather the smallest useful context, state assumptions and missing context, then propose the
implementation plan before editing. After implementation, run the relevant validation and include
the code-reviewer handoff/result in the final output contract.
```

### Investigate A Bug With `issue-investigator`

```text
Use the issue-investigator skill.

Issue source: [tracker ticket URL (Jira/GitHub/GitLab/etc.), support report, incident note, or bug report]
Affected area: [repo/service/component/environment/version if known]
Evidence available: [logs, screenshots, traces, request/response examples, reproduction notes]

Classify the issue, separate expected from actual behavior, attempt safe reproduction if useful,
and report root-cause status as unknown, suspected, confirmed, or disproved.
```

### Review A PR With `code-reviewer`

```text
Use the code-reviewer skill in PR mode.

Review target: [PR URL or branch]
Base: [base branch]
Issue context: [ticket, issue, acceptance criteria, or task description]

Review issue alignment first, then engineering quality. Group findings by severity and finish with
one verdict: PASS, PASS_WITH_NOTES, REQUEST_CHANGES, NEEDS_CONTEXT, or NOT_REVIEWABLE.
```

### Refine A Story With `product-owner`

```text
Use the product-owner skill.

Request: [rough product idea, stakeholder request, or draft ticket]
Users/stakeholders: [who benefits or is affected]
Known context: [current behavior, desired behavior, constraints, links]

Produce a tracker-ready story or task with product goal, user value, scope, out of scope, assumptions,
acceptance criteria, edge cases, dependencies, UX notes, non-functional requirements, open
questions, and handoff notes for engineering and testing.
```

### Create A Manual Test Plan With `manual-tester`

```text
Use the manual-tester skill.

Change to validate: [story, feature, bug fix, or release candidate]
Expected behavior/acceptance criteria: [paste or link]
Environment/build/user roles/test data: [details or say unknown]

Create a focused manual test plan with scenarios, execution result fields, defect-reporting
structure, residual risk, retest guidance, and automation candidates.
```

### Create Automated Regression Coverage With `test-automation-engineer`

```text
Use the test-automation-engineer skill.

Regression risk or scenario: [workflow, bug reproduction, or acceptance criterion]
Manual/repro evidence: [manual test notes, issue-investigator recipe, logs, traces, or defect report]
Repository/test framework/CI context: [known commands and existing test areas]

Decide what to automate, what not to automate, the right test levels, fixtures, selectors/contracts,
assertions, CI integration, flakiness risks, debug artifacts, and remaining manual coverage.
```

## Multi-Skill Workflow Prompts

### Product To Delivery

```text
Use this multi-skill workflow: product-owner -> software-engineer -> manual-tester ->
test-automation-engineer.

Start from this request: [brief]
Available context: [links, criteria, designs, constraints, repo]

First refine scope and acceptance criteria. Then produce an engineering plan and implementation
handoff. Then create manual validation coverage. Finally identify stable regression automation
candidates. Stop at any step where required evidence is missing.
```

### Investigation To Fix To Review

```text
Use this multi-skill workflow: issue-investigator -> software-engineer -> code-reviewer.

Bug report: [brief or link]
Affected repo/environment/version: [details]
Evidence: [logs, screenshots, traces, reproduction notes]

Investigate expected vs actual behavior and root-cause status first. Only then plan and implement
the smallest safe fix. Finish with issue-aware code review and a final status.
```

### Manual Defect To Regression Coverage

```text
Use this multi-skill workflow: manual-tester defect -> issue-investigator ->
test-automation-engineer.

Manual finding: [defect title and notes]
Environment/build/commit: [details]
Steps/evidence: [steps, screenshots, HAR/trace/logs]

Turn the manual finding into a reproducible defect handoff, investigate root-cause status, then
design automated regression coverage only if the behavior and reproduction are stable.
```
