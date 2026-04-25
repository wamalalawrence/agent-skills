---
name: code-reviewer
description: 'Issue-aware code review workflow for working diffs, commits, branches, and pull requests. Use when: reviewing implementation against a Jira ticket, GitHub issue, bug report, feature request, task description, acceptance criteria, or general engineering quality bar. Applies two layers: issue/ticket alignment first, then general engineering quality. Reuses issue-investigator when expected behavior, root cause, or issue context is unclear, and reuses software-engineer for architecture, implementation quality, testability, and production-risk judgment.'
license: MIT
compatibility: Works with any agent that supports the Agent Skills format (Claude Code, Cursor, Windsurf, Continue, GitHub Copilot Chat, ChatGPT, etc.). Expects workspace `.env` populated by setup.init.
metadata:
  author: wamalalawrence
  version: "0.5.0"
  homepage: "https://github.com/wamalalawrence/agent-skills"
argument-hint: 'optional: mode inner|outer, base branch, issue key/URL, PR URL, or task description'
user-invocable: true
disable-model-invocation: false
---

# Code Reviewer

Use this skill to review code changes with both issue awareness and general engineering judgment.

The reviewer must not behave like a generic lint bot. If issue context exists, review the change against the real requested behavior first, then review the engineering quality of the implementation.

## Purpose

- Verify that a code change solves the actual issue, ticket, bug report, feature request, or task description.
- Check implementation quality, maintainability, correctness, security, performance, observability, test coverage, compatibility, and regression risk.
- Produce evidence-based findings with severity, confidence, blocking/advisory status, and concrete suggested fixes.
- Avoid low-value style comments that formatters, linters, or static analysis tools should handle.

## When To Use

- Before opening or updating a pull request.
- During the [`software-engineer`](../../SKILL.md) inner-loop review after implementation is staged.
- During the [`software-engineer`](../../SKILL.md) outer-loop review after QA has run.
- When reviewing a PR, branch, commit range, staged diff, or uncommitted working diff.
- When a change needs issue-aware review against Jira, GitHub Issues, a support ticket, incident, feature request, task description, acceptance criteria, or linked documents.

## Related And Reused Skills

- [`issue-investigator`](../issue-investigator/SKILL.md): use when ticket context, expected behavior, issue type, root cause, reproduction status, or acceptance criteria are unclear. Do not guess issue intent during review.
- [`software-engineer`](../../SKILL.md): use for implementation quality, architecture, testability, build validation, maintainability, security, and production-risk judgment.
- [`product-owner`](../../../product-owner/SKILL.md): use when product value, scope, acceptance criteria, or UX expectations are unclear.
- [`manual-tester`](../../../manual-tester/SKILL.md): use when review needs manual validation scenarios, exploratory findings, or defect evidence.
- [`test-automation-engineer`](../../../test-automation-engineer/SKILL.md): use when review needs automation-level judgment, flaky test analysis, or regression test design.

Code review does not rewrite code directly unless the user explicitly asks for implementation changes. It identifies risks and recommends fixes.

## Required Inputs

Accept any of these review targets:

- Staged diff, working diff, branch diff, commit range, or pull request URL.
- Base branch or comparison target. If absent, derive it from `${PROJECTS_JSON}` or `${GITHUB_DEFAULT_BRANCH}`.
- Issue context: Jira ticket, GitHub issue, bug report, feature request, task description, acceptance criteria, or linked documents.
- Repository path or enough context to identify the project in `${PROJECTS_JSON}`.
- Optional standards: engineering handbook, architecture notes, coding standards, API guidelines, security rules, or URLs provided by the user.

If a review target is missing, stop and ask. If issue context is available but inaccessible or ambiguous, use [`issue-investigator`](../issue-investigator/SKILL.md) or ask the user before producing a final verdict.

## Required Environment

Run this setup preflight before reviewing. If `${WORKSPACE_ROOT}/.env` is missing, unreadable, or lacks enough project metadata to identify the review target, warn and stop for local branch/PR review. Manual review of a user-supplied diff may continue only when the output clearly states that repository setup, build commands, and issue-system access were not verified.

If issue-aware review is requested or an issue key/URL is present, usable issue context is required. Jira access can come from `.env` variables directly; `.jira-config.yml` is optional. If the issue cannot be read and the user did not provide the ticket summary, acceptance criteria, and key comments directly, stop or ask for that context before producing a verdict.

| Variable | Required | Default | Used for |
|---|---|---|---|
| `WORKSPACE_ROOT` | yes | - | Resolving repos and cache paths |
| `PROJECTS_JSON` | yes | - | Project identity, stack, base branch, build and format commands |
| `GITHUB_DEFAULT_BRANCH` | yes | `main` | Base branch fallback |
| `CODE_REVIEWER_MODEL` | no | `default` | Model id used for review, when the host supports model routing |
| `CODE_REVIEWER_BLOCKING` | no | `false` | When `true`, blocker findings stop the calling workflow |
| `CODE_REVIEWER_MAX_FILES` | no | `80` | Warn when non-trivial changed files exceed this |
| `CODE_REVIEWER_MAX_DIFF_CHARS` | no | `60000` | Diff character budget per review pass |
| `CODE_REVIEWER_SHOW_SEVERITIES` | no | `blocker,major,minor,nit` | Severities surfaced in outer-loop mode |
| `CODE_REVIEWER_INNER_LOOP_SEVERITIES` | no | `blocker,major` | Severities surfaced in inner-loop mode |
| `CODE_REVIEWER_MAX_ROUNDS` | no | `3` | Maximum engineer↔reviewer iteration rounds before escalation |
| `CODE_REVIEWER_CACHE_DIR` | no | `${WORKSPACE_ROOT}/.cache/code-reviewer` | Cache for fetched issue context summaries |
| `CODE_REVIEWER_CACHE_TTL_HOURS` | no | `24` | Cache TTL |
| `JIRA_HOST`, `JIRA_API_TOKEN`, `JIRA_AUTH_TYPE` | only for Jira issue-aware review | - | Jira ticket lookup |
| `CONFLUENCE_HOST`, `CONFLUENCE_API_TOKEN` | only when linked docs require them | - | Linked document lookup |
| `SHARED_LIBRARY_NAMES` | no | - | Cross-project impact detection |
| `API_MODULE_PATTERNS` | no | - | API and contract risk detection |
| `SECURITY_CONFIG_PATTERNS` | no | - | Security-sensitive file detection |
| `MIGRATION_PATH_PATTERNS` | no | - | Migration risk detection |

If required setup is missing, output:

> Missing required setup: `<NAME or file>`. I will not continue with issue-aware or repository-aware review because the result would be based on incomplete local context. Add/update `${WORKSPACE_ROOT}/.env`, provide the missing issue/project details directly, or explicitly ask for a non-issue-aware manual review.

## Required Workflow

### 1. Resolve review target

- Verify local setup is sufficient for the requested review mode before deriving base branch, project identity, or issue context.
- Confirm the current directory is inside a git working tree when reviewing local changes.
- Identify repo, branch, base branch, changed files, and review mode.
- Supported modes:
  - `inner`: staged diff, intended for implementation checkpoint review.
  - `outer`: branch diff against base, intended for pre-PR or final review.
  - `pr`: pull request diff and metadata.
  - `manual`: user-supplied diff or code excerpt. Use the `test-quality` profile when the diff is test code (e.g., `test-automation-engineer` or `manual-tester` outputs) and focus findings on selector stability, deterministic data, condition-based waits (no fixed sleeps), assertion meaningfulness, and isolation.

#### Hard handoff contract from the engineer

When invoked from [`software-engineer`](../../SKILL.md) (inner or outer loop), read `${WORKSPACE_ROOT}/.cache/agent-skills/<issue-key>/evidence-pack.yml` per the [evidence-pack schema](../../references/evidence-pack.md) and expect every required field. Surface a `major` finding when any of the following is missing or empty:

- `project` block (name, stack, base_branch, build_command).
- `issue_url`, `summary`, `expected_behavior`, `acceptance_criteria`.
- `investigation.root_cause_status` and `investigation.confidence`, when the change is a bug fix or regression. Stop and invoke [`issue-investigator`](../issue-investigator/SKILL.md) when these are absent.
- `plan` (the engineer's 5-line plan: problem · hypothesis · smallest change · risk · validation).
- `risk_areas`.
- For bug fixes: a referenced **failing-regression-test commit** that fails on the commit's parent and passes on HEAD (`--repro-verify` mode). Cross-check with `repro-recipe.yml` if present.
- For outer-loop or PR review: `${WORKSPACE_ROOT}/.cache/agent-skills/<issue-key>/definition-of-done.json` per the [Definition of Done schema](../../references/definition-of-done.md). Any `false` flag without a written waiver is itself a `blocker`.
- Inner-loop only: `--since-last-review` delta so the reviewer focuses on changes since the previous round, not the whole staged diff again.

If the evidence pack is missing entirely, the reviewer must not re-derive context silently — it surfaces the missing handoff as a `major` finding and asks the engineer to produce it before the loop continues.

### 2. Build issue-aware context first

- Look for issue keys or URLs from user input, branch name, PR title/body, commit messages, and diff text.
- Fetch or summarize Jira tickets, GitHub issues, task descriptions, support tickets, incidents, feature requests, comments, acceptance criteria, linked docs, screenshots, logs, and related tickets where available.
- If expected behavior, root cause, issue type, or acceptance criteria remain unclear, invoke [`issue-investigator`](../issue-investigator/SKILL.md) before final review. If issue access is unavailable and the user has not supplied enough issue details directly, stop instead of downgrading silently to non-issue-aware review.
- Record whether the review is issue-aware, partially issue-aware, or non-issue-aware.

Layer 1 review questions:

- Does the change solve the real requested problem?
- Does it match expected behavior, acceptance criteria, business rules, comments, linked docs, and related tickets?
- Does it miss edge cases, users, roles, environments, data states, or workflows described by the issue?
- Does the implementation address the confirmed root cause, or only a symptom?
- Does it introduce scope creep beyond the ticket?

### 3. Review general engineering quality

Apply [`software-engineer`](../../SKILL.md) and its reference checklists for engineering quality. Focus on findings that materially affect correctness or maintainability.

Layer 2 review areas:

- Correctness and edge cases.
- Maintainability, readability, and complexity.
- Error handling and recovery.
- Test coverage and meaningful assertions.
- Security and privacy.
- Performance and resource usage.
- Observability: useful logs, metrics, traces, and correlation ids.
- Backwards compatibility, API contract risk, migration risk, and rollout safety.
- Regression risk in affected or downstream components.

Use provided company-specific standards, architecture guidance, or engineering URLs as additional context when the user provides them. Do not hard-code private standards into this public skill.

### 4. Filter noise and prioritize evidence

- Ignore formatter-only style preferences, unless they hide a real bug or readability risk.
- Do not report issues already handled by normal lint, format, or static-analysis tools unless the finding has product or production impact.
- Prioritize production code, APIs/contracts, migrations, security config, tests, and release/configuration files before docs-only changes.
- For large diffs, review a high-signal slice first and clearly report what was not reviewed.

### 5. Produce findings

Each finding must include:

- Severity: `blocker`, `major`, `minor`, or `nit`.
- Finding title.
- Affected file or area.
- Evidence from code, issue context, tests, logs, or linked docs.
- Why it matters.
- Suggested fix.
- Confidence: `high`, `medium`, or `low`.
- Blocking status: `blocking` or `advisory`.

Severity guidance:

- `blocker`: likely wrong behavior, data loss, security risk, broken build, missing core acceptance criteria, unsafe migration, or production incident risk.
- `major`: meaningful correctness, maintainability, test, compatibility, or operational risk that should be addressed before merge.
- `minor`: real improvement with limited risk or localized impact.
- `nit`: small clarity issue worth mentioning only when it is not formatter/linter noise.

### 6. Enforce blocking behavior

- If `${CODE_REVIEWER_BLOCKING}` is `true` and any blocker finding exists, the calling workflow must stop until the finding is fixed or explicitly waived with a written reason.
- If blocking is disabled, still label blockers clearly and explain the risk.

### 7. Enforce iteration convergence

When this skill is invoked iteratively in the engineer↔reviewer pair-programming loop:

- Track the round number in the evidence pack (`round: 1`, `round: 2`, ...).
- The number of `blocker` + `major` findings **must strictly decrease** between rounds. If round N has the same or more blocker/major findings than round N-1, stop and surface a "not converging" summary to the user with the recurring findings highlighted.
- After `${CODE_REVIEWER_MAX_ROUNDS}` (default `3`) rounds, escalate regardless of finding counts: report the unresolved blockers, the engineer's responses, and ask the user how to proceed. Do not loop indefinitely or silently downgrade blockers to advisory.

### 8. Devil's-advocate self-rebuttal (before final verdict)

Before producing a `PASS` verdict, write one paragraph attacking your own conclusion: _"Here is the most credible scenario in which I am wrong about this diff being safe."_ Cover at least one of: silent data loss, lost-update / race condition, auth bypass or missing authorization check, secret or PII leakage, broken or non-reversible migration, breaking API contract change, regression in a previously-fixed defect. If the rebuttal surfaces a credible risk, downgrade the verdict to `WARN` or add a `blocker`/`major` finding accordingly.

## Expected Output

```markdown
## Code Review - <repo> @ <branch>

Review mode: inner | outer | pr | manual
Issue awareness: issue-aware | partially issue-aware | non-issue-aware
Base: <base branch or comparison target>
Files reviewed: <kept>/<total> after filtering
Standards used: <repo docs / supplied URLs / none>

## Issue Alignment
- Issue summary:
- Expected behavior:
- Acceptance criteria mapping:
- Alignment verdict: aligned | partially aligned | not aligned | unclear

## Findings
### <severity>: <finding title>
- Affected file/area:
- Evidence:
- Why it matters:
- Suggested fix:
- Confidence: high | medium | low
- Blocking: blocking | advisory

## Engineering Quality Summary
- Correctness:
- Tests:
- Security:
- Performance:
- Observability:
- Compatibility / regression risk:

## Verdict
- BLOCK | WARN | PASS
- Reason:
- Follow-up needed:
```

If no findings are found, say so explicitly and list any review limits, skipped files, missing issue context, or tests not verified.

## Quality Bar

- Findings must be actionable and evidence-based.
- Review must use issue context when available.
- Review must call out uncertainty instead of inventing missing facts.
- Review must distinguish blocking risks from advisory improvements.
- Review must avoid style-only noise that belongs to automated tools.
- Suggested fixes must be concrete and minimal.
- Large-diff truncation or skipped files must be disclosed.

## Guardrails

- Do not invent issue details, logs, code behavior, acceptance criteria, or company standards.
- Do not produce issue-aware verdicts when the issue context could not be read or supplied.
- Do not recommend broad rewrites unless the evidence shows the current approach is materially unsafe or unmaintainable.
- Do not rewrite the diff during review unless the user explicitly asks for implementation help.
- Do not store secrets or private customer data in cache or output.
- Do not treat formatter, linter, or static-analysis preferences as meaningful review findings unless they affect behavior or maintainability.

## Example Prompts

- "Review my staged diff against this Jira ticket."
- "Review this PR for issue alignment and engineering risk."
- "Run an outer-loop review before I open a PR."
- "Review this bug fix and tell me if it actually addresses the root cause."
- "Review this change using the linked architecture guidelines as extra standards."