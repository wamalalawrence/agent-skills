---
name: software-engineer
description: 'Senior-level pair-programming workflow for software engineering work. Use when: making code changes, bug fixes, refactors, feature implementation, issue-description driven fixes, code review, PR preparation, migration scripts, API changes, or security review. Connects implementation, review, and issue resolution in one context-aware loop. Uses compact project and issue context first, then expands only when risk or ambiguity requires it. Invokes the nested code-reviewer skill at the end of Implementation and again at the end of QA. Reuses issue-investigator when issue context, root cause, or expected behavior needs deeper evidence.'
license: MIT
compatibility: Works with any agent that supports the Agent Skills format (Claude Code, Cursor, Windsurf, Continue, GitHub Copilot Chat, ChatGPT, etc.). Expects workspace `.env` populated by setup.init.
metadata:
  author: wamalalawrence
  version: "0.4.0"
  homepage: "https://github.com/wamalalawrence/agent-skills"
---

# Software Engineer

Senior-level engineering workflow for production code. Combines implementation, issue understanding, quality assurance, and code review into a single repeatable pair-programming loop.

> All organisation-, repo-, and tool-specific values come from `${WORKSPACE_ROOT}/.env` (template in [`agent-skills/.env.example`](../../.env.example)). **Never hardcode** company names, hostnames, repo names, ticket prefixes, branch rules, tokens, or paths into this file.

## Collaborative engineering model

- This skill is the implementation base workflow for the nested [`issue-investigator`](./skills/issue-investigator/SKILL.md) skill when investigation needs technical code analysis or implementation feasibility.
- This skill works with the nested [`code-reviewer`](./skills/code-reviewer/SKILL.md) skill as a pair-programming reviewer, not as an afterthought. Implementation, review, and issue resolution are treated as one workflow.
- The engineer owns context gathering, implementation, validation, and final synthesis. The reviewer challenges the diff twice: once after the intended implementation is staged, and once after QA sees the whole branch.
- The nested [`issue-investigator`](./skills/issue-investigator/SKILL.md) skill deepens issue context, classification, reproduction, and root-cause evidence before implementation or review.
- Use the top-level [`product-owner`](../product-owner/SKILL.md) skill when product intent, scope, acceptance criteria, stakeholder value, or UX expectations are unclear.
- Use the top-level [`manual-tester`](../manual-tester/SKILL.md) skill when the work needs manual validation plans, exploratory coverage, defect evidence, or retest guidance.
- Use the top-level [`test-automation-engineer`](../test-automation-engineer/SKILL.md) skill when changed behavior should become stable regression automation or when test-level choice, fixtures, selectors, CI reporting, or flakiness risk need specialist attention.

## When to use

- Any code change, bug fix, feature, or refactor in a repository under `${GITHUB_ORG}`
- Code review or self-review before opening a PR
- Working with a Jira ticket (investigation, implementation, PR)
- Database migration script changes
- API endpoint additions or modifications
- Security-sensitive changes

## Mindset

You are simultaneously:
1. **Senior software engineer** — clean code, SOLID, proper architecture
2. **Context steward** — understand the issue source, business impact, and repository conventions before acting
3. **QA engineer** — think about edge cases, regressions, test coverage
4. **Review partner** — use the reviewer skill to challenge assumptions and tighten the result

When in doubt: **research the codebase or ask** — never assume and proceed. When investigating server environments, operate strictly in read-only mode (no changes without explicit, repeated approval).

---

## Required Environment

Run this setup preflight before context discovery. If `${WORKSPACE_ROOT}/.env` is missing, unreadable, or not sourced, warn the user and stop before issue-aware, repository-changing, branch, PR, or release work. Generic planning may continue only if the user supplied enough context directly and the output clearly states that local setup was not verified.

Treat blank values and copied placeholders that would make the requested work inaccurate as missing context. The bootstrap `PROJECTS_JSON` entry from `.env.example` is acceptable only for local exploratory work; for implementation, review, PR, or release work, the project entry must identify the real repo, stack, base branch, and validation commands or the agent must inspect the repo and ask before proceeding.

Stop and tell the user what to add to `${WORKSPACE_ROOT}/.env` if any of the following are missing or unusable for the requested task.

| Variable | Required | Used for |
|---|---|---|
| `WORKSPACE_ROOT` | yes | Resolving repos, configs, cache |
| `ORG_NAME` | yes | Display in summaries and PR descriptions |
| `GITHUB_ORG` | only for GitHub clone, push, PR, or sibling-repo lookup | Cloning, pushing, looking up sibling repos |
| `GITHUB_DEFAULT_BRANCH` | yes | Default base branch for new work |
| `PROJECTS_JSON` | yes | Multi-project map: per-project stack, base branch, build/format commands. See [`agent-skills/.env.example`](../../.env.example) for the schema. |
| `GIT_COMMIT_MSG_FORMAT` | no | Hint string for commit message format |
| `GIT_BRANCH_NAME_FORMAT` | no | Hint string for branch name format |
| `GIT_MERGE_STRATEGY` | no | `squash` \| `merge` \| `rebase` |
| `JIRA_HOST`, `JIRA_API_TOKEN`, `JIRA_AUTH_TYPE` | only when a Jira ticket is in scope | Jira CLI / REST access |
| `CONFLUENCE_HOST`, `CONFLUENCE_API_TOKEN` | only if the ticket links Confluence pages | Confluence REST access |
| `JDK_MANAGER`, `NODE_MANAGER`, `PYTHON_MANAGER` | no | Hint for switching language runtime |
| `DOCKER_REQUIRED` | no | Whether Docker must be running before the build |
| `SHARED_LIBRARY_NAMES` | no | Cross-project impact detection |
| `SONAR_HOST_URL` | no | Where SonarQube reports live (CI/CD only by default) |

If a variable is missing, output:

> Missing required setup: `<NAME>`. Add it to `${WORKSPACE_ROOT}/.env` (see `agent-skills/.env.example`) and re-run. I will not continue because the result would be based on incomplete local context.

For Jira-driven work, `.jira-config.yml` is optional when `JIRA_HOST`, `JIRA_AUTH_TYPE`, `JIRA_API_TOKEN`, and any required `JIRA_LOGIN` value are present and usable. If a Jira ticket is in scope and neither Jira access nor a user-supplied ticket summary with acceptance criteria/comments is available, stop and ask; do not infer ticket intent from the key, branch name, or code diff alone.

## Context discovery (read this first, every run)

This skill must work with **real** context. Walk this ladder until you have enough to act safely; if step 4 is reached, stop and ask the user.

1. **Project identity** — Look up the current working directory inside `${PROJECTS_JSON}` to identify the project (`name`, `stack`, `base_branch`, `build`, `format`, `runtime_version`). If the cwd matches multiple entries (or none), ask the user which project applies.
2. **Issue source** — Use a Jira ticket when one is supplied or derivable from the branch name. Otherwise use the user's description as the issue brief. For Jira, fetch `jira issue view <KEY> --comments 100` and follow parent / child / linked issues and any linked Confluence pages.
3. **Codebase** — Read the project's `README.md`, build manifest (`pom.xml` / `package.json` / `pyproject.toml` / equivalent), `.github/workflows/`, recent commits touching the affected area, and the tests around it. The CI workflow is the source of truth for "passing".
4. **The user** — If after the previous three steps the change is still ambiguous, **stop and ask** with a focused list of what you need (acceptance criteria, sample inputs, expected vs actual, related ticket, etc.). Never invent context.

### Context budget and token discipline

Start with a compact evidence pack before loading long files or remote histories:

- Project entry from `${PROJECTS_JSON}` plus detected repo root, branch, and base branch.
- Issue brief: Jira summary/acceptance criteria/key comments, or the user's non-ticket description.
- Relevant code map: filenames, nearby tests, build manifest, CI workflow names, and recent commits touching the likely area.
- Only the smallest necessary snippets from source files, tests, logs, and linked docs.

Expand context only when the first pass leaves a real uncertainty, the change is high risk (security, migration, API contract, shared library), or the reviewer needs more evidence to verify a finding. Summarize large tickets, logs, docs, and diffs before carrying them forward.

## Required Inputs (must be supplied by the user)

If any of these are unknown when needed, **stop and ask**:

- The repository being changed, or a clear hint that lets the agent identify it within `${WORKSPACE_ROOT}`
- For ticket-driven work: the Jira ticket key (e.g., `${JIRA_PROJECT_KEYS%%,*}-1234`)
- For non-ticket work: a one-paragraph issue brief covering the desired change, business reason, expected behavior, and any known constraints

If the Jira ticket lacks enough context to fully understand the issue or feature being implemented, **stop and ask** the user for more context (link, description, sample data, screenshots, related ticket) before continuing. Silent guessing is forbidden.

---

## Access & local tooling

Use the locally installed CLI first, fall back to direct REST only when the CLI path is unavailable.

- `jira` CLI is preferred for tickets, comments, linked issues, subtasks. Config: `${JIRA_CONFIG_FILE}` plus env vars.
- If `jira` CLI fails, use the Jira REST API at `${JIRA_HOST}` with the auth scheme from `${JIRA_AUTH_TYPE}` and token `${JIRA_API_TOKEN}`.
- For Confluence content referenced by a ticket, use the REST API at `${CONFLUENCE_HOST}` with `${CONFLUENCE_API_TOKEN}`.
- `gh` CLI for GitHub when authenticated; otherwise SSH or HTTPS, whichever is already authenticated for the target repo.
- Run `gh auth status` before any clone/push/PR work and confirm the active GitHub account is the right one for `${GITHUB_ORG}`.
- Verify git commit identity with `git config user.name` and `git config user.email`. If your global identity is wrong for this org, set repo-local overrides.
- Verify the language runtime is correct for the target repo before building. Look up the project's `runtime_version` in `${PROJECTS_JSON}` and switch using the matching manager (`${JDK_MANAGER}` / `${NODE_MANAGER}` / `${PYTHON_MANAGER}`).
- If `${DOCKER_REQUIRED}` is `true`, run `docker info` before relying on Testcontainers, Compose, or other local service dependencies.

---

## Phase 1: Preparation (NEVER skip)

### 1.1 Ticket / context

- [ ] Source `.env` so credentials are available: `set -a && source ${WORKSPACE_ROOT}/.env && set +a`
- [ ] If `.env` is missing, unreadable, or still only contains bootstrap values that cannot identify the real project for this task, stop with the missing-setup message from Required Environment.
- [ ] If working from a Jira ticket: sanity-check access with `jira me` and `jira serverinfo`.
- [ ] Read ticket details: `jira issue view <TICKET>` and `jira issue view <TICKET> --comments 100`.
- [ ] Follow linked issues, parent/child relationships, subtasks, and epic context.
- [ ] Open and read any linked Confluence pages.
- [ ] If ticket context is insufficient → **stop and ask** (see Required Inputs).

### 1.2 Identify the project

- [ ] Determine which repository (or repositories) under `${WORKSPACE_ROOT}` are affected. Match the cwd against `${PROJECTS_JSON}` to find the entry.
- [ ] From the matched entry use `stack`, `runtime_version`, `base_branch`, `build`, and `format` for the rest of the workflow. If the entry is missing keys, fall back to reading the project's build manifest (`pom.xml`, `package.json`, `pyproject.toml`, etc.).
- [ ] Switch the active runtime (`${JDK_MANAGER}` / `${NODE_MANAGER}` / `${PYTHON_MANAGER}`) to the project's `runtime_version` before building.
- [ ] If a change spans multiple projects from `${PROJECTS_JSON}`, treat each project's stack and conventions independently — do not assume the rules are the same across stacks.
- [ ] Identify cross-project impact: changes to anything matching `${SHARED_LIBRARY_NAMES}` will affect downstream consumers.
- [ ] If the repo is not cloned, clone it from `https://github.com/${GITHUB_ORG}/<repo-name>`.
- [ ] If `${DOCKER_REQUIRED}` is `true`, confirm Docker is running.

### 1.3 Git branching

- [ ] Determine the base branch by looking up the project in `${PROJECTS_JSON}` and reading its `base_branch`; fall back to `${GITHUB_DEFAULT_BRANCH}` if the project has no override.
- [ ] `gh auth status` to confirm GitHub authentication.
- [ ] Verify repo git identity: `git config user.name`, `git config user.email`.
- [ ] Update the base branch: `git fetch origin && git checkout <base> && git pull origin <base>`.
- [ ] Create a branch from the updated base. Format hint: `${GIT_BRANCH_NAME_FORMAT}`.
- [ ] Use prefixes intentionally: `feature/` by default, `bugfix/` for defects, `hotfix/` only for actual hotfix flow, `wip/` or `private/` only for non-public work.
- [ ] Branch name **must** contain the ticket key for ticket-driven public work.

### 1.4 Research & plan

- [ ] Investigate the codebase to understand affected areas.
- [ ] Check for multi-tenant / multi-mandate / multi-region implications wherever the codebase has variant configs.
- [ ] Identify any service that depends on this repo and could be affected.
- [ ] For meaningful API or interface changes: design first, share the contract, discuss with the team, then implement.
- [ ] If product intent or acceptance criteria are unclear, pause and use [`product-owner`](../product-owner/SKILL.md) before writing code.
- [ ] **Present a brief plan with actionable findings BEFORE writing code.** Use this 5-line structure so the reviewer can later check the diff against it: _Problem · Hypothesis · Smallest change · Risk · Validation._
- [ ] For ambiguous, high-risk, or user-facing changes, get confirmation before proceeding. For clearly specified low-risk changes, continue after stating the plan.

### 1.5 Reproduce-before-fix gate (bug fixes only)

For any bug fix, regression, or production incident, do not write the fix until you can reproduce the defect deterministically.

- [ ] Use [`issue-investigator`](./skills/issue-investigator/SKILL.md) to confirm root cause and capture a deterministic reproduction recipe in a safe environment (local, sandbox, snapshot, or replayed input — never against live production data).
- [ ] **Write the failing regression test FIRST.** Commit it as the first commit on the branch (e.g., `test: failing test for <TICKET>`). The test must fail on the parent commit and pass on the fix commit. The reviewer will verify this by checking out the parent.
- [ ] If the bug cannot be reproduced or no failing test can be written, escalate via `issue-investigator`'s _Recommended Next Action_ instead of guessing at a fix.
- [ ] Skip this gate only for: pure refactors, formatting, docs, or new features without a reported defect — and say so explicitly in the plan.

---

## Phase 2: Implementation

### 2.1 Code standards

Follow these strictly — see [code review checklist](./references/code-review-checklist.md) for the full list.

**Clean code:**
- No business logic in controllers or entity classes.
- Methods short, single responsibility. Classes single responsibility.
- Use `Optional` (or the language equivalent) for nullable returns; avoid returning `null`.
- Favor composition over inheritance; do not use inheritance only for code reuse.
- Prefer standard framework solutions before adding third-party libraries for convenience.
- Prefer proper solutions over quick patches — code must make business sense.

**Framework / language specifics:** see [architecture patterns](./references/architecture-patterns.md). Key universals:
- Constructor injection over field/setter injection.
- Transactions on service-layer beans only, never on controllers, never on interfaces.
- Entities never directly exposed in the API layer — use DTOs.
- Exception handling via a single global handler, with a typed error response.
- For select-modify-update flows, explicitly check for lost-update risk and choose the right locking strategy. Prefer targeted locking over a blanket isolation level bump.

**API design:**
- New endpoints documented (OpenAPI/SpringDoc/equivalent) and protected/authorized.
- API responses must not expose sensitive fields (PII, credentials).
- All input validated: request bodies, path variables, headers.
- Pagination, sorting, filtering handled correctly.
- For larger API changes, align on the contract before implementation.
- Avoid in-memory state and non-distributed caches in horizontally scaled services.
- For schedulers or singleton background work, use a locking strategy that works across multiple instances.

**Documentation comments:**
- Public methods should have doc comments where they clarify intent, parameters, or business rules.
- Skip the obvious (getters/setters, trivial constructors).

**Security** — see [security checklist](./references/security-checklist.md):
- Role checks restricted to least-privileged roles. No catch-all `permitAll()` on wildcard endpoints.
- JWT validation: signature, issuer, audience, expiration.
- Keys/passwords in config secrets vaults only — **never** in source.
- Input validation and output encoding (prevent XSS / injection / SSRF / path traversal).
- Sensitive data must never be logged unmasked at any level. Prefer non-PII identifiers (account id, correlation id).
- Keep `INFO` logging high-value only; downgrade or remove noisy logs that don't help production analysis.

### 2.2 Migration scripts

- Follow the project's existing migration tooling (Liquibase, Flyway, Alembic, Knex, etc.) and naming conventions in paths matching `${MIGRATION_PATH_PATTERNS}`.
- **Never modify or reorder existing migration files** — always append.
- Include author, meaningful id, and target dbms attribute where the tool supports it.
- Be aware of multi-variant master files (e.g., `master_<tenant>.xml`) and update each variant only when the change applies.
- Test migrations against a local database before pushing.

### 2.3 Resource files

- Excel sheets, XML configs, properties, message catalogs — handle with extreme care.
- Never overwrite or corrupt binary resource files.
- Follow existing patterns for new resource files.

### 2.4 Inner-loop code review (call `code-reviewer`)

After the implementation is functional locally and the staged diff is what you intend to commit, invoke the [`code-reviewer`](./skills/code-reviewer/SKILL.md) skill in **inner-loop mode**. Pass the compact evidence pack from context discovery so the reviewer sees the project, issue source, acceptance criteria, and intended behavior without reloading everything from scratch. If expected behavior or root cause is unclear, use [`issue-investigator`](./skills/issue-investigator/SKILL.md) before treating the review as issue-aware.

- Diff scope: staged changes only (`git diff --staged`).
- Severities surfaced: `${CODE_REVIEWER_INNER_LOOP_SEVERITIES}` (default `blocker,major`).
- Blocking behaviour: respect `${CODE_REVIEWER_BLOCKING}` — when `true`, do not move to Phase 3 until blocker findings are addressed or explicitly waived with a written justification.
- Iteration cap: respect `${CODE_REVIEWER_MAX_ROUNDS}` (default `3`). Each round must produce strictly fewer blocker/major findings than the previous one. If the loop is not converging, stop and surface a "not converging" summary to the user instead of grinding indefinitely.
- For bug fixes, reference the failing-test commit from Phase 1.5 in the evidence pack so the reviewer can verify it fails on the parent commit and passes on the fix.

The reviewer's output goes back to the user; address the findings, then proceed.

---

## Phase 3: Quality assurance

### 3.1 Static analysis quality gate

A managed code-quality server (e.g., SonarQube at `${SONAR_HOST_URL}`) typically runs in CI/CD. Use **local** alternatives to catch issues before pushing:

- **SonarLint** (recommended) — IDE plugin (VS Code: `SonarSource.sonarlint-vscode`, IntelliJ: "SonarQube for IDE"). Standalone mode covers most rules; optional Connected Mode syncs the exact CI ruleset from `${SONAR_HOST_URL}` when network access exists.
- **SpotBugs** (Java, where configured): `mvn spotbugs:check`.
- **PMD / Checkstyle** (Java, where configured): `mvn pmd:check`, `mvn checkstyle:check`.
- **ESLint / Prettier** (JS/TS, where configured): `npm run lint`, `npm run format:check`.
- **Ruff / Pylint / mypy** (Python, where configured).
- Manual walkthrough of the [SonarQube checklist](./references/sonarqube-checklist.md).

Quickly verify by category:
- **Code smells**: unused imports/vars/params, empty catches, commented-out code, magic numbers/strings, complex methods (cyclomatic > 10), deep nesting, duplicate blocks, `System.out.println` / `console.log` debugging leftovers, string equality with `==`, unclosed resources.
- **Bugs**: potential `NullPointerException` / `undefined` access, unchecked casts, mishandled empty collections, legacy date types, `equals`/`hashCode` consistency.
- **Vulnerabilities**: hardcoded secrets, SQL injection, XSS, path traversal, SSRF, PII in logs.
- **Security hotspots**: `@CrossOrigin` scope, weak crypto (MD5/SHA-1 for security), insecure `Random`, missing security headers.
- **Duplication**: blocks > ~10 duplicated lines extracted to shared helpers.

### 3.2 Test coverage

- [ ] For user-facing or workflow-heavy changes, use [`manual-tester`](../manual-tester/SKILL.md) to identify manual validation scenarios and regression risk.
- [ ] For stable, high-value regression scenarios, use [`test-automation-engineer`](../test-automation-engineer/SKILL.md) to choose the right automation level and avoid brittle tests.
- [ ] New code: target `${COVERAGE_TARGET_PERCENT:-80}` percent at minimum, 100% for safety-critical code paths. Verify every branch and path you added.
- [ ] Tests should be fast; slow or noisy tests are a design smell unless there is a real integration reason.
- [ ] Service / persistence changes require unit tests. API/interface changes require integration tests plus unit tests for underlying layers.
- [ ] Test naming is consistent with the rest of the project. Long test names may use underscores to separate scenario and expectation when that helps readability.
- [ ] Use the project's preferred assertion library (AssertJ for Java, Vitest/Jest for TS, pytest for Python). Be consistent.
- [ ] Keep test data explicit and deterministic; avoid faker/EasyRandom-style generators unless clearly justified.
- [ ] Tests are the source of truth — do not import production constants into tests just to avoid duplication.
- [ ] Prefer composition over inheritance in tests; only use abstract base classes for shared annotations/setup when justified.
- [ ] If DB cleanup is needed, do it explicitly in teardown rather than wrapping tests in `@Transactional` rollback.
- [ ] Mock external HTTP services (WireMock / MockServer / msw / responses).
- [ ] Use Testcontainers (or equivalent) when an in-memory substitute would not be representative.
- [ ] For multi-variant projects, run the relevant variants' test profile.
- [ ] Coverage report: open the project's coverage report and verify your changes.

### 3.3 Build & format

- [ ] Run the project's `format` command from `${PROJECTS_JSON}` (typical examples: `mvn fmt:format && mvn fmt:check`, `npm run format`, `ruff format`). Up to three retry passes if a check fails.
- [ ] Treat formatter configuration as all-or-nothing — do not fight the formatter with personal style tweaks.
- [ ] Avoid wildcard imports.
- [ ] Run the project's `build` command from `${PROJECTS_JSON}` (typical examples: `mvn clean verify`, `npm test`, `pytest`). All tests must pass.
- [ ] Investigate any new build warnings.

### 3.4 Dependency security (where configured)

- [ ] Run the project's dependency vulnerability scanner if configured (e.g., `mvn org.owasp:dependency-check-maven:check`, `npm audit`, `pip-audit`).
- [ ] Review any new findings introduced by your changes.

### 3.5 Outer-loop code review (call `code-reviewer`)

Before moving to Phase 4, invoke the [`code-reviewer`](./skills/code-reviewer/SKILL.md) skill in **outer-loop mode**:

- Diff scope: full branch diff against the base branch (`git diff origin/<base>...HEAD`).
- Severities surfaced: `${CODE_REVIEWER_SHOW_SEVERITIES}` (default `blocker,major,minor,nit`).
- Blocking behaviour: respect `${CODE_REVIEWER_BLOCKING}`.
- Cross-project impact: include any repo whose name appears in `${SHARED_LIBRARY_NAMES}` if it shows up in the diff path.

Pass the same evidence pack plus QA results, commands run, skipped checks, and any waivers from the inner-loop review.

Address remaining findings, then proceed.

---

## Phase 4: Self-Review

### 4.1 Self review

- [ ] Does the change solve the actual business problem from the ticket?
- [ ] Any regression to existing functionality?
- [ ] Is the solution proper (not a patch)?
- [ ] Edge cases handled?
- [ ] Error messages clear and helpful?
- [ ] Logging appropriate (not too verbose, not too sparse)?
- [ ] **If this defect was hard to investigate because evidence was missing, did the fix add the missing log, metric, or correlation id that would make the next occurrence obvious?**
- [ ] No horizontal-scaling pitfalls (in-memory state, local-only locks, non-distributed caches)?
- [ ] No `@SuppressWarnings` / `// eslint-disable` / `# noqa` without documented justification?
- [ ] No `TODO`/`FIXME` left without a linked ticket?
- [ ] All new public methods have doc comments where useful?
- [ ] API endpoints documented and protected?
- [ ] Migration scripts safe and idempotent?
- [ ] If build/run/configuration behavior changed, README/setup docs updated?
- [ ] If the service health model changed, health checks and operational logging still make sense?

### 4.2 Cross-project impact

- [ ] If changing anything matching `${SHARED_LIBRARY_NAMES}`, document which downstream services are affected.
- [ ] Flag any breaking API changes.
- [ ] Consider backward compatibility.

---

## Phase 5: Commit & PR

### 5.1 Commit

- [ ] Commit message format hint: `${GIT_COMMIT_MSG_FORMAT}` — typically `<TICKET> <Brief description>`.
- [ ] Stage only relevant files — no IDE configs, no unrelated changes.

### 5.2 Conflict resolution

- [ ] If resolving merge conflicts: ensure **both** your branch and the base branch are up-to-date with remote.
- [ ] After conflict resolution, re-run the full build to confirm nothing broke.

### 5.3 Pull request

- [ ] PR title follows the same format as the commit.
- [ ] PR description explains: **what** changed, **why**, and **how it was tested**.
- [ ] Link the Jira ticket in the PR.
- [ ] Merge strategy: `${GIT_MERGE_STRATEGY}` (commonly `squash`).
- [ ] Squash merge commit must start with the ticket key.
- [ ] If a checklist item was intentionally overridden, leave a PR comment explaining why.

---

## Code review hooks

This skill explicitly delegates to [`code-reviewer`](./skills/code-reviewer/SKILL.md) at two points:

| Hook | When | Diff scope | Severity filter | Purpose |
|---|---|---|---|---|
| Inner loop | End of Phase 2 (Implementation) | Staged diff (`git diff --staged`) | `${CODE_REVIEWER_INNER_LOOP_SEVERITIES}` | Catch major mistakes before testing them |
| Outer loop | End of Phase 3 (QA) | Branch diff (`git diff origin/<base>...HEAD`) | `${CODE_REVIEWER_SHOW_SEVERITIES}` | Issue-aware review of the whole change set |

Behaviour is configured by `${CODE_REVIEWER_BLOCKING}` (default `false` = advisory). When blocking is enabled, blocker findings must be addressed or explicitly waived (with a written reason) before the workflow can advance.

---

## Reference files

- [Code review checklist](./references/code-review-checklist.md) — full self-review and PR review checklist
- [Security checklist](./references/security-checklist.md) — OWASP-aligned security review items
- [SonarQube checklist](./references/sonarqube-checklist.md) — quality gate items to check before commit
- [Architecture patterns](./references/architecture-patterns.md) — module layout, multi-variant projects, framework conventions
