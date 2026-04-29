---
name: code-reviewer
description: >-
  Issue-aware code review workflow for working diffs, commits, branches, and pull
  requests. Use when: reviewing implementation against a Jira ticket, GitHub issue, bug
  report, feature request, task description, acceptance criteria, or general engineering
  quality bar. Applies two layers: issue/ticket alignment first, then general engineering
  quality. Reuses issue-investigator when expected behavior, root cause, or issue context
  is unclear, and reuses software-engineer for architecture, implementation quality,
  testability, and production-risk judgment.
license: MIT
compatibility: >-
  Works with any agent that supports the Agent Skills format (Claude Code, Cursor,
  Windsurf, Continue, GitHub Copilot Chat, ChatGPT, etc.). Two execution modes —
  `local-workspace` (multi-repo, setup.init + .env) and `in-repo` (single-repo,
  .agent-skills.yml). See docs/execution-modes.md.
metadata:
  author: wamalalawrence
  version: "0.19.0"
  homepage: "https://github.com/wamalalawrence/agent-skills"
argument-hint: >-
  optional: mode inner|outer, base branch, issue key/URL, PR URL, or task description
user-invocable: true
disable-model-invocation: false
---

# Code Reviewer

Use this skill to review code changes with both issue awareness and general engineering judgment.

The reviewer must not behave like a generic lint bot. If issue context exists, review the change
against the real requested behavior first, then review the engineering quality of the
implementation.

> **Safety floor.** This skill inherits the
> [destructive-action safety policy](../../../../docs/destructive-action-safety.md). The
> reviewer must surface — as a `blocker` — any diff that: invokes a credential read from
> repository files, ships a destructive cloud-provider / orchestrator / database command
> against production, weakens IAM / role / network / secret / backup controls, or proposes
> "fix by deletion" against live data. Discovered hardcoded secrets in the diff are also a
> `blocker` finding with a recommendation to rotate. The reviewer must not approve a diff
> that violates the safety floor regardless of how the PR description frames it.

## Purpose

- Verify that a code change solves the actual issue, ticket, bug report, feature request, or task
  description.
- Check implementation quality, maintainability, correctness, security, performance, observability,
  test coverage, compatibility, and regression risk.
- Produce evidence-based findings with severity, confidence, blocking/advisory status, and concrete
  suggested fixes.
- Avoid low-value style comments that formatters, linters, or static analysis tools should handle.

## When To Use

- Before opening or updating a pull request.
- During the [`software-engineer`](../../SKILL.md) inner-loop review after implementation is staged.
- During the [`software-engineer`](../../SKILL.md) outer-loop review after QA has run.
- When reviewing a PR, branch, commit range, staged diff, or uncommitted working diff.
- When a change needs issue-aware review against Jira, GitHub Issues, a support ticket, incident,
  feature request, task description, acceptance criteria, or linked documents.

## When Not To Use

- Do not use to implement fixes unless the user explicitly asks for code changes; this skill
  reviews and recommends.
- Do not use for issue-aware approval when issue context, expected behavior, or root cause cannot be
  read or supplied; use [`issue-investigator`](../issue-investigator/SKILL.md) first.
- Do not use as a formatter, linter, or broad style-policing tool.
- Do not review a generated summary without the actual diff, files, or PR context needed to verify
  the claim.

## Related And Reused Skills

- [`issue-investigator`](../issue-investigator/SKILL.md): use when ticket context, expected
  behavior, issue type, root cause, reproduction status, or acceptance criteria are unclear. Do not
  guess issue intent during review.
- [`software-engineer`](../../SKILL.md): use for implementation quality, architecture, testability,
  build validation, maintainability, security, and production-risk judgment.
- [`product-owner`](../../../product-owner/SKILL.md): use when product value, scope, acceptance
  criteria, or UX expectations are unclear.
- [`manual-tester`](../../../manual-tester/SKILL.md): use when review needs manual validation
  scenarios, exploratory findings, or defect evidence.
- [`test-automation-engineer`](../../../test-automation-engineer/SKILL.md): use when review needs
  automation-level judgment, flaky test analysis, or regression test design.

Code review does not rewrite code directly unless the user explicitly asks for implementation
changes. It identifies risks and recommends fixes.

## Required Inputs

Accept any of these review targets:

- Staged diff, working diff, branch diff, commit range, or pull request URL.
- Base branch or comparison target. If absent, derive it from `${PROJECTS_JSON}` or
  `${GITHUB_DEFAULT_BRANCH}`.
- Issue context: Jira ticket, GitHub issue, bug report, feature request, task description,
  acceptance criteria, or linked documents.
- Repository path or enough context to identify the project in `${PROJECTS_JSON}`.
- Optional standards: engineering handbook, architecture notes, coding standards, API guidelines,
  security rules, or URLs provided by the user.

If a review target is missing, stop and ask. If issue context is available but inaccessible or
ambiguous, use [`issue-investigator`](../issue-investigator/SKILL.md) or ask the user before
producing a final verdict.

## Stopping Conditions

Stop and return `final verdict: NEEDS_CONTEXT` or `NOT_REVIEWABLE` when:

- The review target, base branch, or changed files cannot be determined.
- Issue-aware review is requested but expected behavior, acceptance criteria, or root-cause evidence
  is missing.
- The diff is too large or truncated enough that high-confidence findings would be misleading.
- Required repository setup, build metadata, or supplied standards are inaccessible and the user did
  not request a manual partial review.
- A finding depends on private/company standards that were not provided.

## Required Environment

Run this setup preflight before reviewing.

**Detect execution mode** ([docs/execution-modes.md](../../../../docs/execution-modes.md)): if
`AGENT_SKILLS_MODE` is set to `local-workspace` or `in-repo`, use it; else if
`${WORKSPACE_ROOT}/.env` is present → `local-workspace`; else if `.agent-skills.yml` exists at the
repo root → `in-repo`; else stop.

If the resolved configuration is missing, unreadable, or lacks enough project metadata to identify
the review target, warn and stop for local branch/PR review. Manual review of a user-supplied diff
may continue only when the output clearly states that repository setup, build commands, and
issue-system access were not verified.

If issue-aware review is requested or an issue key/URL is present, usable issue context is required.
Jira host metadata can come from `.env` or `.agent-skills.yml`; the credential (`JIRA_API_TOKEN`)
always comes from environment variables. `.jira-config.yml` is optional. If the issue cannot be read
and the user did not provide the ticket summary, acceptance criteria, and key comments directly,
stop or ask for that context before producing a verdict.

**Auth discovery before recording Jira/Confluence as unavailable.** Before listing Jira or
Confluence under `Review Limitations / Unavailable Context`, walk the documented
[discovery order](../../../../docs/auth-discovery.md#discovery-order): `.agent-skills.yml` →
`.jira-config.yml` → `.env` / `.env.local` → process env → `scripts/auth-preflight.py`. If config
exists but `${VAR}` placeholders are unresolved, record the limitation as **"Jira config
incomplete — unresolved placeholder X"**, not "no Jira access". The reviewer must not give a
bare `PASS` when issue alignment could not be checked because of an avoidable auth-discovery
miss; if the preflight has not been run and Jira is in scope, the correct verdict is
`NEEDS_CONTEXT`.

Review setup variables:

- `WORKSPACE_ROOT`: required in `local-workspace` mode. Resolves repos and cache paths. In
  `in-repo` mode, the repository root is used.
- `PROJECTS_JSON`: required in `local-workspace` mode. Provides project identity, stack, base
  branch, build, and format commands. In `in-repo` mode, the single `project:` block in
  `.agent-skills.yml` replaces this.
- `GITHUB_DEFAULT_BRANCH`: required. Defaults to `main`; used as the base branch fallback.
- `CODE_REVIEWER_MODEL`: optional. Defaults to `default`; used when the host supports model
  routing.
- `CODE_REVIEWER_BLOCKING`: optional. Defaults to `false`; when `true`, blocker findings stop the
  calling workflow.
- `CODE_REVIEWER_MAX_FILES`: optional. Defaults to `80`; warns when non-trivial changed files
  exceed this.
- `CODE_REVIEWER_MAX_DIFF_CHARS`: optional. Defaults to `60000`; sets the diff character budget per
  review pass.
- `CODE_REVIEWER_SHOW_SEVERITIES`: optional. Defaults to `blocker,major,minor,nit`; controls
  severities surfaced in outer-loop mode.
- `CODE_REVIEWER_INNER_LOOP_SEVERITIES`: optional. Defaults to `blocker,major`; controls severities
  surfaced in inner-loop mode.
- `CODE_REVIEWER_MAX_ROUNDS`: optional. Defaults to `3`; maximum engineer-reviewer iteration rounds
  before escalation.
- `CODE_REVIEWER_CACHE_DIR`: optional. Defaults to
  `${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/code-reviewer}`; caches fetched
  issue-context summaries.
- `CODE_REVIEWER_CACHE_TTL_HOURS`: optional. Defaults to `24`; cache TTL.
- `JIRA_HOST`, `JIRA_API_TOKEN`, `JIRA_AUTH_TYPE`: required only for Jira issue-aware review.
- `CONFLUENCE_HOST`, `CONFLUENCE_API_TOKEN`: required only when linked docs require them.
- `SHARED_LIBRARY_NAMES`: optional. Used for cross-project impact detection.
- `API_MODULE_PATTERNS`: optional. Used for API and contract risk detection.
- `SECURITY_CONFIG_PATTERNS`: optional. Used for security-sensitive file detection.
- `MIGRATION_PATH_PATTERNS`: optional. Used for migration risk detection.

If required setup is missing, output:

> Missing required setup: `<NAME or file>`. I will not continue with issue-aware or repository-aware
> review because the result would be based on incomplete context. Add/update
> `${WORKSPACE_ROOT}/.env` (local-workspace) or `.agent-skills.yml` at the repo root (in-repo — see
> `agent-skills/.agent-skills.example.yml`), provide the missing issue/project details directly, or
> explicitly ask for a non-issue-aware manual review.

## Required Workflow

### 0. Requirement Understanding Gate

Before reviewing the diff, run the shared
[requirement-understanding workflow](../../../../docs/requirement-understanding.md) against the
**review target**, not the diff. The reviewer's job is to verify that the change solves the right
problem; that requires the reviewer to know what the right problem is. Emit the
`Requirement Understanding` block (twelve fields) above the rest of the review output and use it
to answer five review-specific questions:

- Does the diff solve the actual requirement, or a different one?
- Was the requirement clear enough to review against, or did the engineer have to invent intent?
- Does the diff solve only part of the issue and silently leave the rest open?
- Does the diff introduce behavior beyond what the requirement asked for, without justification?
- Are the acceptance criteria observable in the diff (tests, error messages, log lines, API
  contract) or only asserted in the PR description?

When the engineer's evidence pack already contains the gate output (written by
[`software-engineer`](../../SKILL.md) or
[`issue-investigator`](../issue-investigator/SKILL.md)), reuse it and verify it against the diff
rather than re-deriving from scratch. The reviewer must not weaken a gate decision the engineer
correctly made; if the engineer left it `low` and shipped anyway, that is itself a `blocker`
finding.

Binding rules:

- **`unknown` / `low`** understanding of the requirement — do **not** issue a bare `PASS`. Use
  `NEEDS_CONTEXT` when issue context is missing, or `PASS_WITH_NOTES` /
  `REQUEST_CHANGES` depending on the diff risk. Hand off to
  [`issue-investigator`](../issue-investigator/SKILL.md) when expected behavior, root cause, or
  reproduction status are missing.
- **`medium`** — may complete the review with the gate's load-bearing assumptions visible in the
  `Review Limitations / Unavailable Context` section. A bare `PASS` requires every gate item to
  be `none` or explicitly waived by the user.
- **`high`** — may produce any verdict, including `PASS`, when the diff matches the understood
  requirement and no other limitations remain.

This gate is the precondition for the layered review in steps 2-3 below; it is not a substitute
for them.

### 1. Resolve review target

- Verify local setup is sufficient for the requested review mode before deriving base branch,
  project identity, or issue context.
- Confirm the current directory is inside a git working tree when reviewing local changes.
- Identify repo, branch, base branch, changed files, and review mode.
- Supported modes:
  - `inner`: staged diff, intended for implementation checkpoint review.
  - `outer`: branch diff against base, intended for pre-PR or final review.
  - `pr`: pull request diff and metadata.
  - `manual`: user-supplied diff or code excerpt. Use the `test-quality` profile when the diff is
    test code (e.g., `test-automation-engineer` or `manual-tester` outputs) and focus findings on
    selector stability, deterministic data, condition-based waits (no fixed sleeps), assertion
    meaningfulness, and isolation.

#### Hard handoff contract from the engineer

When invoked from [`software-engineer`](../../SKILL.md) (inner or outer loop), read
`${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills}/<issue-key>/evidence-pack.yml`
per the [evidence-pack schema](../../references/evidence-pack.md) and expect every required field.
Surface a `major` finding when any of the following is missing or empty:

- `project` block (name, stack, base_branch, build_command).
- `issue_url`, `summary`, `expected_behavior`, `acceptance_criteria`.
- `investigation.root_cause_status` and `investigation.confidence`, when the change is a bug fix or
  regression. Stop and invoke [`issue-investigator`](../issue-investigator/SKILL.md) when these are
  absent.
- `plan` (the engineer's 5-line plan: problem · hypothesis · smallest change · risk · validation).
- `risk_areas`.
- For bug fixes: a referenced **failing-regression-test commit** that fails on the commit's parent
  and passes on HEAD (`--repro-verify` mode). Cross-check with `repro-recipe.yml` if present.
- For outer-loop or PR review:
  `${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills}/<issue-key>/definition-of-done.json`
  per the [Definition of Done schema](../../references/definition-of-done.md). Any `false` flag
  without a written waiver is itself a `blocker`.
- **`safety_acknowledgement` block in `definition-of-done.json` whenever the diff touches a
  deployed environment, credentials, IAM, secrets, backups, monitoring, or network policy.**
  The reviewer must refuse to advance — surface a `blocker` finding — when any of:
  the block is missing on a diff that obviously requires it (changes to IaC, CI deployment,
  IAM, secret stores, migrations, or any cloud-provider command);
  `safety_acknowledgement.applies: true` but `no_discovered_credentials_invoked: false` or
  `no_in_repo_tokens_invoked: false`;
  `destructive_command_used: true` without a populated `destructive_command_authorization`
  (approver + ticket + runbook_path);
  `execution_path: agent` for a destructive / IAM / secret / backup change;
  `monitoring_unchanged: false` / `iam_unchanged: false` /
  `network_policy_unchanged: false` without an explicit waiver in `waivers[]`;
  `environment: production` with `execution_path: agent`;
  `backup_restore_tested` is `null` or older than 90 days when the runbook depends on
  restoring from backup. See the
  [destructive-action safety policy](../../../../docs/destructive-action-safety.md).
- Inner-loop only: `--since-last-review` delta so the reviewer focuses on changes since the previous
  round, not the whole staged diff again.

If the evidence pack is missing entirely, the reviewer must not re-derive context silently — it
surfaces the missing handoff as a `major` finding and asks the engineer to produce it before the
loop continues.

### 2. Build issue-aware context first

- Look for issue keys or URLs from user input, branch name, PR title/body, commit messages, and diff
  text.
- Fetch or summarize Jira tickets, GitHub issues, task descriptions, support tickets, incidents,
  feature requests, comments, acceptance criteria, linked docs, screenshots, logs, and related tickets
  where available.
- If expected behavior, root cause, issue type, or acceptance criteria remain unclear, invoke
  [`issue-investigator`](../issue-investigator/SKILL.md) before final review. If issue access is
  unavailable and the user has not supplied enough issue details directly, stop instead of downgrading
  silently to non-issue-aware review.
- Record whether the review is issue-aware, partially issue-aware, or non-issue-aware.

Layer 1 review questions:

- Does the change solve the real requested problem?
- Does it match expected behavior, acceptance criteria, business rules, comments, linked docs, and
  related tickets?
- Does it miss edge cases, users, roles, environments, data states, or workflows described by the
  issue?
- Does the implementation address the confirmed root cause, or only a symptom?
- Does it introduce scope creep beyond the ticket?

### 3. Review general engineering quality

Apply [`software-engineer`](../../SKILL.md) and its reference checklists for engineering quality.
Focus on findings that materially affect correctness or maintainability.

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

Use provided company-specific standards, architecture guidance, or engineering URLs as additional
context when the user provides them. Do not hard-code private standards into this public skill.

### 4. Filter noise and prioritize evidence

- Ignore formatter-only style preferences, unless they hide a real bug or readability risk.
- Do not report issues already handled by normal lint, format, or static-analysis tools unless the
  finding has product or production impact.
- Prioritize production code, APIs/contracts, migrations, security config, tests, and
  release/configuration files before docs-only changes.
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

Use the shared [severity and confidence definitions](../../../../docs/severity-and-confidence.md)
for severity, confidence, and blocking/advisory decisions.

### 6. Enforce blocking behavior

- If `${CODE_REVIEWER_BLOCKING}` is `true` and any blocker finding exists, the calling workflow must
  stop until the finding is fixed or explicitly waived with a written reason.
- If blocking is disabled, still label blockers clearly and explain the risk.

### 7. Enforce iteration convergence

When this skill is invoked iteratively in the engineer↔reviewer pair-programming loop:

- Track the round number in the evidence pack (`round: 1`, `round: 2`, ...).
- The number of `blocker` + `major` findings **must strictly decrease** between rounds. If round N
  has the same or more blocker/major findings than round N-1, stop and surface a "not converging"
  summary to the user with the recurring findings highlighted.
- After `${CODE_REVIEWER_MAX_ROUNDS}` (default `3`) rounds, escalate regardless of finding counts:
  report the unresolved blockers, the engineer's responses, and ask the user how to proceed. Do not
  loop indefinitely or silently downgrade blockers to advisory.

### 8. Devil's-advocate self-rebuttal (before final verdict)

Before producing a `PASS` verdict, write one paragraph attacking your own conclusion: _"Here is the
most credible scenario in which I am wrong about this diff being safe."_ Cover at least one of:
silent data loss, lost-update / race condition, auth bypass or missing authorization check, secret
or PII leakage, broken or non-reversible migration, breaking API contract change, regression in a
previously-fixed defect. If the rebuttal surfaces a credible risk, downgrade the verdict to
`PASS_WITH_NOTES` or add a `blocker`/`major` finding and return `REQUEST_CHANGES`.

### 9. Record review limitations explicitly

Before producing the final verdict, list what could not be reviewed and why. The reviewer must
never produce a confident verdict without disclosing the gaps that bound that confidence. Cover at
least:

- Issue context not accessed (Jira/GitHub issue unreachable, comments/linked docs not fetched,
  acceptance criteria supplied verbally rather than from the source of truth).
- Code paths not inspected (large diff truncation, files skipped because of the configured budget,
  generated files, vendored dependencies, binary assets).
- Tests, builds, or CI runs not executed or not observed (state explicitly when results were
  reported by the engineer rather than verified directly).
- Standards or guidelines referenced but not supplied (private architecture docs, security rules,
  API guidelines, style guides). Do not invent their content.
- Runtime, deployment, observability, or data evidence that would have changed confidence (logs,
  metrics, feature-flag rollouts, migration dry-runs).

A review with significant unavailable context must use `PASS_WITH_NOTES` or `NEEDS_CONTEXT`, never
a bare `PASS`. The unavailable items appear in the `Review Limitations` section of the output
contract below.

## Expected Output Contract

```markdown
## Code Review - <repo> @ <branch>

- Review scope:
- Review mode: inner | outer | pr | manual
- Issue awareness: issue-aware | partially issue-aware | non-issue-aware
- Base: <base branch or comparison target>
- Files reviewed: <kept>/<total> after filtering
- Standards used: <repo docs / supplied URLs / none>

## Issue/Ticket Alignment Result

- Issue summary:
- Expected behavior:
- Acceptance criteria mapping:
- Alignment verdict: aligned | partially aligned | not aligned | unclear

## Engineering Quality Result

- Correctness:
- Tests:
- Security:
- Performance:
- Observability:
- Compatibility / regression risk:

## Findings Grouped By Severity

### <severity>: <finding title>

- Severity: blocker | major | minor | nit
- Title:
- Affected file/area:
- Evidence:
- Why it matters:
- Suggested fix:
- Confidence: high | medium | low
- Blocking/advisory decision: blocking | advisory

## Review Limitations / Unavailable Context

- Issue context not accessed:
- Code paths not inspected:
- Tests / builds / CI not executed or not observed:
- Standards / guidelines referenced but not supplied:
- Runtime / deployment / observability evidence not available:
- Effect on confidence:

## Final Verdict

- Verdict: PASS | PASS_WITH_NOTES | REQUEST_CHANGES | NEEDS_CONTEXT | NOT_REVIEWABLE
- Reason:
- Follow-up needed:
```

The `Review Limitations / Unavailable Context` section is required even when the review found no
findings. If everything was available, write `none` under each item rather than removing the
section. A bare `PASS` verdict requires every limitation item to be `none` or explicitly waived by
the user; otherwise use `PASS_WITH_NOTES` or `NEEDS_CONTEXT`.

## Behavior Checklist

- [ ] Review target, base, changed files, review mode, and issue-awareness level are resolved or the
  verdict is `NEEDS_CONTEXT` / `NOT_REVIEWABLE`.
- [ ] Issue/ticket alignment is checked before generic engineering quality when context exists.
- [ ] Findings include severity, evidence, impact, suggested fix, confidence, and blocking/advisory
  decision.
- [ ] `Review Limitations / Unavailable Context` section is filled in (each item either lists what
  was missing or says `none`); a bare `PASS` is not used while items are non-`none`.
- [ ] Missing evidence, skipped files, unverified tests, and review limits are disclosed.
- [ ] Final verdict uses only `PASS`, `PASS_WITH_NOTES`, `REQUEST_CHANGES`, `NEEDS_CONTEXT`, or
  `NOT_REVIEWABLE`.

## Quality Standards

- Findings must be actionable and evidence-based.
- Review must use issue context when available.
- Review must call out uncertainty instead of inventing missing facts.
- Review must distinguish blocking risks from advisory improvements.
- Review must avoid style-only noise that belongs to automated tools.
- Suggested fixes must be concrete and minimal.
- Large-diff truncation or skipped files must be disclosed.
- Final verdict must use only `PASS`, `PASS_WITH_NOTES`, `REQUEST_CHANGES`, `NEEDS_CONTEXT`, or
  `NOT_REVIEWABLE`.

## Guardrails

- Do not invent issue details, logs, code behavior, acceptance criteria, or company standards.
- Do not produce issue-aware verdicts when the issue context could not be read or supplied.
- Do not recommend broad rewrites unless the evidence shows the current approach is materially
  unsafe or unmaintainable.
- Do not rewrite the diff during review unless the user explicitly asks for implementation help.
- Do not store secrets or private customer data in cache or output.
- Do not claim tests, builds, or issue-system checks were verified unless they were actually run or
  inspected.
- Do not treat formatter, linter, or static-analysis preferences as meaningful review findings
  unless they affect behavior or maintainability.
- Do not approve a diff that violates the
  [destructive-action safety policy](../../../../docs/destructive-action-safety.md). Surface
  any of the following as `blocker` findings: discovered hardcoded credentials,
  invocations of credentials read from repository files, destructive cloud / orchestrator /
  database commands targeting production, IAM / role / network / secret / backup-control
  weakening, "fix by deletion" of live resources, removal of audit logging or monitoring.
- Do not produce a bare `PASS` verdict when the
  [Requirement Understanding Gate](#0-requirement-understanding-gate) ended at `unknown` /
  `low`, when issue context is missing, or when any item in `Review Limitations / Unavailable
  Context` is non-`none` and unwaived. The correct verdict is `NEEDS_CONTEXT` or
  `PASS_WITH_NOTES`.

## Example Prompts

- "Review my staged diff against this Jira ticket."
- "Review this PR for issue alignment and engineering risk."
- "Run an outer-loop review before I open a PR."
- "Review this bug fix and tell me if it actually addresses the root cause."
- "Review this change using the linked architecture guidelines as extra standards."

See [the code-reviewer PR review example](../../../../docs/examples/code-reviewer-pr-review.md) and
[starter prompts](../../../../docs/starter-prompts.md).
