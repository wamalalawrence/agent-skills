---
name: issue-investigator
description:
  "Issue investigation workflow for Jira tickets, GitHub issues, support tickets, incidents,
  regressions, feature requests, and technical tasks. Use when: understanding expected vs actual
  behavior, classifying issue type, gathering evidence, reproducing problems, analyzing root cause,
  refining tickets before implementation, or recommending the next action. Reuses software-engineer
  for technical code analysis and implementation feasibility, and supports code-reviewer by
  producing reliable issue context before review."
license: MIT
compatibility:
  Works with any agent that supports the Agent Skills format (Claude Code, Cursor, Windsurf,
  Continue, GitHub Copilot Chat, ChatGPT, etc.). Two execution modes — `local-workspace`
  (multi-repo, setup.init + .env) and `in-repo` (single-repo, .agent-skills.yml). Optional Jira CLI
  integration via `.jira-config.yml`. See docs/execution-modes.md.
metadata:
  author: wamalalawrence
  version: "0.7.0"
  homepage: "https://github.com/wamalalawrence/agent-skills"
argument-hint:
  "issue URL/key, bug report, incident, support ticket, feature request, or task description plus
  affected repo/service/environment"
user-invocable: true
disable-model-invocation: false
---

# Issue Investigator

Use this skill to understand an issue before deciding what to build, fix, configure, roll back,
test, monitor, or clarify.

This is intentionally not only a Jira bug-fix skill. It investigates many issue types and produces
an evidence-based result before recommending the next action. It must not jump directly to
implementation.

## Purpose

- Read and understand the full issue context from tickets, descriptions, comments, screenshots,
  logs, linked documents, related issues, and codebase evidence.
- Classify the issue type and distinguish expected behavior from actual behavior.
- Reproduce the issue locally or in a safe environment when useful and possible.
- Identify suspected or confirmed root cause with real evidence.
- Recommend the next action: fix, clarification, rollback, configuration change, data correction,
  test addition, monitoring improvement, product decision, or no code change.
- Produce reliable issue context for [`code-reviewer`](../code-reviewer/SKILL.md) and implementation
  planning for [`software-engineer`](../../SKILL.md).

## When To Use

- Bug investigation.
- Production incident investigation.
- Regression investigation.
- Support ticket investigation.
- New feature clarification.
- Technical task analysis.
- Jira ticket or GitHub issue refinement before implementation.
- Root-cause analysis before fixing.
- Review preparation when expected behavior or issue context is unclear.

## When Not To Use

- Do not use to implement the fix; hand confirmed or suspected fix work to
  [`software-engineer`](../../SKILL.md).
- Do not use to invent acceptance criteria for unclear product behavior; hand that to
  [`product-owner`](../../../product-owner/SKILL.md).
- Do not use for final PR approval; hand the diff to [`code-reviewer`](../code-reviewer/SKILL.md).
- Do not continue when the only available input is a vague symptom with no issue source, affected
  area, expected behavior, or reproduction clue.

## Related And Reused Skills

- [`software-engineer`](../../SKILL.md): use for technical code-path analysis, architecture
  constraints, implementation feasibility, validation commands, and production-risk judgment.
- [`code-reviewer`](../code-reviewer/SKILL.md): use after a fix or implementation exists and needs
  issue-aware review.
- [`product-owner`](../../../product-owner/SKILL.md): use when intended behavior, business value,
  scope, UX expectation, or acceptance criteria are unclear.
- [`manual-tester`](../../../manual-tester/SKILL.md): use for reproduction scenarios, exploratory
  validation, defect evidence, and retest guidance.
- [`test-automation-engineer`](../../../test-automation-engineer/SKILL.md): use when the
  investigation identifies stable regression scenarios that should be automated.

Issue investigation owns facts, evidence, classification, root cause, and next-step recommendation.
It does not own broad implementation quality; that belongs to [`software-engineer`](../../SKILL.md)
and [`code-reviewer`](../code-reviewer/SKILL.md).

## Required Inputs

Accept any of these as the starting issue source:

- Jira ticket key or URL.
- GitHub issue URL or number.
- Support ticket, production incident, regression report, bug report, feature request, task
  description, or user-provided issue brief.
- Affected repo, service, component, environment, release, branch, or version.
- Expected vs actual behavior, if known.
- Screenshots, logs, traces, request/response examples, deployment notes, CI output, monitoring
  links, or related documents.

If the issue source is missing or too vague, ask focused questions. If access to a referenced system
is unavailable, say what could not be inspected and request the smallest useful excerpt.

## Stopping Conditions

Stop and return a `root cause status` of `unknown` when:

- The issue source cannot be accessed and the user did not provide enough direct detail.
- Expected behavior cannot be established from ticket, product, docs, tests, or user context.
- Reproduction would require unsafe production mutation or sensitive data exposure.
- Evidence is too weak to support the recommended next action.
- Root-cause hypotheses are plausible but untested; mark them `suspected`, not `confirmed`.

## Required Environment

Run this setup preflight before investigating.

**Detect execution mode** ([docs/execution-modes.md](../../../../docs/execution-modes.md)): if
`${WORKSPACE_ROOT}/.env` is present → `local-workspace`; else if `.agent-skills.yml` exists at the
repo root → `in-repo`; else continue only when the user supplied the issue details directly and no
repository/Jira lookup is needed. Otherwise warn and stop because the investigation would be based
on incomplete context.

For Jira tickets, usable Jira access is required unless the user provides the ticket summary,
acceptance criteria, key comments, linked-doc excerpts, and affected environment details directly.
`.jira-config.yml` is optional when the Jira environment variables work. If a Jira key or URL is
supplied but the ticket cannot be read and no direct ticket details are provided, stop instead of
producing a low-confidence investigation.

| Variable                                        | Required                                   | Used for                                                                                                                             |
| ----------------------------------------------- | ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| `WORKSPACE_ROOT`                                | yes (local-workspace)                      | Resolving repos, cache, and local context. In `in-repo` mode the repository root is used.                                            |
| `PROJECTS_JSON`                                 | yes (local-workspace)                      | Matching affected repos/services to stack and commands. In `in-repo` mode the `project:` block in `.agent-skills.yml` replaces this. |
| `JIRA_HOST`, `JIRA_API_TOKEN`, `JIRA_AUTH_TYPE` | only for Jira tickets                      | Jira ticket lookup                                                                                                                   |
| `JIRA_LOGIN`                                    | yes for basic auth; recommended for bearer | Jira CLI identity                                                                                                                    |
| `JIRA_CONFIG_FILE`                              | no                                         | Jira CLI config path                                                                                                                 |
| `CONFLUENCE_HOST`, `CONFLUENCE_API_TOKEN`       | only when linked docs require them         | Confluence lookup                                                                                                                    |
| `ISSUE_INVESTIGATOR_CACHE_DIR`                  | no                                         | Cache for fetched ticket/doc summaries; default `${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/issue-investigator}` |
| `ISSUE_INVESTIGATOR_CACHE_TTL_HOURS`            | no                                         | Cache TTL; default `24`                                                                                                              |

For GitHub issues, prefer the authenticated `gh` CLI when available. Do not require new secrets in
this public skill unless the user's environment already uses them.

If setup is incomplete, output:

> Missing required setup: `<NAME or file>`. I will not continue with issue-aware investigation
> because the result would be based on incomplete context. Add/update `${WORKSPACE_ROOT}/.env`
> (local-workspace) or `.agent-skills.yml` at the repo root (in-repo — see
> `agent-skills/.agent-skills.example.yml`), provide the missing issue details directly, or rerun
> without the unavailable issue source.

## Required Workflow

### 1. Gather issue context

- Verify that local setup is sufficient for the requested issue source before fetching or inferring
  details.
- Read title, description, comments, attachments, screenshots, logs, acceptance criteria, linked
  issues, related incidents, linked docs, and recent updates.
- Identify affected users, roles, environments, versions, data sets, integrations, and workflows.
- Capture timestamps, deployment windows, feature flags, configuration changes, and CI/deployment
  history when relevant.
- Separate confirmed facts from assumptions and unknowns.

### 2. Classify the issue

Classify the most likely type, and explain the evidence:

- Bug.
- Regression.
- Production incident.
- Support request.
- Feature request.
- Enhancement.
- Technical task.
- Configuration issue.
- Environment issue.
- Data issue.
- Unclear requirement.
- Duplicate, already fixed, cannot reproduce, or not a product/code issue.

### 3. Define expected and actual behavior

- Determine expected behavior from acceptance criteria, product docs, existing behavior, related
  tickets, product-owner input, tests, or stakeholder comments.
- Determine actual behavior from the report, logs, screenshots, data, reproduction, monitoring, or
  code paths.
- If expected behavior is unclear, use [`product-owner`](../../../product-owner/SKILL.md) or ask the
  user before treating the issue as a bug.

### 4. Investigate evidence

- Inspect relevant code paths, configuration, data, logs, CI output, deployment history, feature
  flags, and environment-specific behavior where available.
- Prefer the actual affected environment when access and safety allow; operate read-only unless
  explicitly authorized.
- Reproduce locally or in a safe test environment when useful (see _Safe reproduction protocol_
  below).
- Use [`software-engineer`](../../SKILL.md) for deeper technical analysis, architecture impact,
  repository conventions, or implementation feasibility.
- Avoid stopping at the first plausible explanation. Use the _Three-hypothesis discipline_ below to
  fight confirmation bias.
- For regressions, run the _Regression triage_ checklist below before forming hypotheses.
- Track primary and secondary contributing factors separately.

#### Safe reproduction protocol

Never reproduce a defect against live production data or by mutating shared state. Pick the cheapest
safe environment that still reproduces the behavior:

1. Local stack (docker-compose, devcontainer, in-process test harness).
2. Ephemeral branch environment with a snapshot or seeded data set.
3. Replayed input only: HAR file, recorded log slice, captured request/response pair, or anonymized
   payload.
4. Read-only inspection of the affected environment (`SET TRANSACTION READ ONLY`, `--dry-run`,
   read-replica, snapshot DB) when no other option reproduces it.

For each reproduction attempt, record: environment chosen, exact commands and inputs, observed
output, and a deterministic recipe (env vars + commands + expected log lines) that another agent or
human can replay verbatim. Persist the recipe to
`${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills}/<issue-key>/repro-recipe.yml`
per the [evidence-pack & repro-recipe schema](../../references/evidence-pack.md). Hand that recipe
to [`software-engineer`](../../SKILL.md) and
[`test-automation-engineer`](../../../test-automation-engineer/SKILL.md) so it can become the
failing regression test before any fix is written.

#### Evidence-pack output

Persist the full investigation result to
`${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills}/<issue-key>/evidence-pack.yml`
per the [evidence-pack schema](../../references/evidence-pack.md). At minimum populate `issue_*`,
`project`, `expected_behavior`, `actual_behavior`, `investigation` (root-cause status, evidence,
hypotheses considered, confidence, what-would-change-my-mind), and `risk_areas`. Subsequent skills
append to this file rather than re-deriving the context.

#### Three-hypothesis discipline

When the root cause is not obvious from evidence already in hand:

1. List the **top three** candidate causes, ranked by prior likelihood plus evidence already seen.
2. For each hypothesis, write a one-line **"what would change my mind"** falsifier.
3. Design the **single cheapest experiment that discriminates between the top two** hypotheses (a
   query, a log filter, a one-line probe, a unit test, a config flip in a sandbox).
4. Run it. Update rankings. Eliminate or promote.
5. Repeat until one hypothesis dominates the evidence or all three are eliminated and a new set is
   needed.

Do not skip to step 5 by intuition. Recording the discriminating experiment is the artifact that
distinguishes investigation from guessing.

#### Regression triage (when the issue worked before)

For any reported regression, run these high-signal cheap moves before forming hypotheses:

- `git log -L :<symbol>:<file>` or `git log --follow -p -- <file>` on the suspect file or function.
- `git blame` the suspect line and read the introducing commit message and PR (title, description,
  review comments).
- `git bisect` between the last known-good and first known-bad commit when those are available,
  using the deterministic reproduction recipe as the bisect predicate.
- Compare CI output, deploy timestamps, and feature-flag/config changes between the good and bad
  versions.

Document the introducing commit hash and PR link in the investigation result so the fix can
reference them.

### 5. Establish root-cause status and confidence

- Mark root cause as `unknown`, `suspected`, `confirmed`, or `disproved`.
- Tie every suspected or confirmed cause to evidence.
- State what evidence would be needed to raise confidence.
- If the issue cannot be reproduced, document what was attempted and why confidence is limited.
- Use [the shared severity/confidence definitions](../../../../docs/severity-and-confidence.md) for
  `confidence level` and root-cause status semantics.

**Evidence gate for the next-action recommendation:**

| Recommended next action                                        | Minimum required root-cause status / evidence                                          |
| -------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `code fix`                                                     | `confirmed`, or `suspected` plus a reproducible recipe and a falsifiable hypothesis    |
| `rollback` / `revert`                                          | `suspected` or higher, plus a clear introducing change identified by regression triage |
| `configuration change` / `data correction`                     | `confirmed` (mutation in a real environment requires evidence, not a hunch)            |
| `monitoring or alerting improvement`                           | any status (safe to add observability when scoped correctly)                           |
| `product clarification` / `documentation` / `support response` | any status                                                                             |

If the evidence does not meet the bar for the action you want to recommend, choose a lower-impact
action (typically `monitoring` or `clarification`) and state explicitly what evidence is missing.

### 6. Recommend the next action

Choose the most appropriate next action based on evidence:

- Code fix.
- Product clarification.
- Rollback or revert.
- Configuration change.
- Data correction.
- Test addition.
- Monitoring or alerting improvement.
- Documentation or runbook update.
- Support response.
- No change, duplicate, cannot reproduce, or already fixed.

When recommending a code fix, provide implementation guidance and hand off to
[`software-engineer`](../../SKILL.md). After a fix exists, use
[`code-reviewer`](../code-reviewer/SKILL.md) to review issue alignment and engineering quality.

## Expected Output Contract

```markdown
## Investigation Result

- Issue summary:
- Issue type classification:
- Confidence level: low | medium | high

## Behavior

- Expected behavior:
- Actual behavior:
- Scope / affected users:

## Evidence Reviewed

- Ticket / issue context:
- Comments / linked docs:
- Logs / screenshots / traces:
- Code / config / data / CI / deployment evidence:

## Reproduction Status

- Status: reproduced | partially reproduced | not reproduced | not attempted | not applicable
- Environment:
- Steps attempted:
- Result:

## Root Cause

- Root cause status: unknown | suspected | confirmed | disproved
- Root cause:
- Supporting evidence:
- Assumptions:

## Affected Components And Environments

- Components:
- Environments:
- Downstream or cross-repo impact:

## Recommended Next Action

- Recommendation:
- Why:
- Fix/clarification/test recommendations:
- Monitoring / documentation / support follow-up:

## Open Questions Or Missing Evidence

- ...
```

Normal output must include every section above unless the user asked only for a narrow partial
analysis. If a section cannot be completed, write `not available` and explain what evidence is
missing.

## Quality Standards

- Investigation results must distinguish facts, assumptions, and unknowns.
- Root-cause claims must cite evidence.
- Expected behavior must come from reliable context, not invention.
- Recommendations must match the classification and evidence.
- The skill must be useful even when no code change is needed.
- Reproduction attempts, skipped evidence, access limits, and uncertainty must be disclosed.
- Root-cause status and confidence must follow the shared
  [severity/confidence definitions](../../../../docs/severity-and-confidence.md).

## Guardrails

- Do not invent issue details, logs, screenshots, code behavior, acceptance criteria, or company
  standards.
- Do not implement a fix before producing an investigation result.
- Do not mutate production data, configuration, or environments without explicit approval and a
  rollback plan.
- Do not assume every issue is a code bug.
- Do not treat missing credentials or inaccessible systems as proof of behavior.
- Do not claim reproduction was attempted, tests were run, or root cause was confirmed unless the
  evidence shows it.
- Do not hide uncertainty. Mark assumptions and missing evidence clearly.
- Do not hard-code private company practices into this public skill.

## Example Prompts

- "Investigate this Jira ticket and tell me whether it is a bug, config issue, or unclear
  requirement."
- "Analyze this production incident and recommend the next action before we fix anything."
- "Read this support ticket and identify expected vs actual behavior."
- "Investigate this regression report and find the likely root cause."
- "Refine this technical task before implementation and list missing evidence."

See [the issue-investigator bug report example](../../../../docs/examples/issue-investigator-bug-report.md)
and [starter prompts](../../../../docs/starter-prompts.md).
