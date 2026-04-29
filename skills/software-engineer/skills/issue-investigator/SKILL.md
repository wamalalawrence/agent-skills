---
name: issue-investigator
description: >-
  Issue investigation workflow for Jira tickets, GitHub issues, support tickets,
  incidents, regressions, feature requests, and technical tasks. Use when: understanding
  expected vs actual behavior, classifying issue type, gathering evidence, reproducing
  problems, analyzing root cause, refining tickets before implementation, or recommending
  the next action. Reuses software-engineer for technical code analysis and implementation
  feasibility, and supports code-reviewer by producing reliable issue context before
  review.
license: MIT
compatibility: >-
  Works with any agent that supports the Agent Skills format (Claude Code, Cursor,
  Windsurf, Continue, GitHub Copilot Chat, ChatGPT, etc.). Two execution modes —
  `local-workspace` (multi-repo, setup.init + .env) and `in-repo` (single-repo,
  .agent-skills.yml). Optional Jira CLI integration via `.jira-config.yml`. See
  docs/execution-modes.md.
metadata:
  author: wamalalawrence
  version: "0.19.0"
  homepage: "https://github.com/wamalalawrence/agent-skills"
argument-hint: >-
  issue URL/key, bug report, incident, support ticket, feature request, or task
  description plus affected repo/service/environment
user-invocable: true
disable-model-invocation: false
---

# Issue Investigator

Use this skill to understand an issue before deciding what to build, fix, configure, roll back,
test, monitor, or clarify.

This is intentionally not only a Jira bug-fix skill. It investigates many issue types and produces
an evidence-based result before recommending the next action. It must not jump directly to
implementation.

> **Safety floor.** This skill is **read-only by default** and inherits the
> [destructive-action safety policy](../../../../docs/destructive-action-safety.md). Every
> check the agent proposes to the user must be classified as `read-only` or `mutating`;
> mutating checks are not proposed by this skill at all and belong in a
> [`software-engineer`](../../SKILL.md) operator runbook. The agent must never invoke a
> credential discovered during investigation (see
> [Discovered-credential protocol](#discovered-credential-protocol)) and must never ask the
> user to paste a secret into chat.

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
`AGENT_SKILLS_MODE` is set to `local-workspace` or `in-repo`, use it; else if
`${WORKSPACE_ROOT}/.env` is present → `local-workspace`; else if `.agent-skills.yml` exists at the
repo root → `in-repo`; else continue only when the user supplied the issue details directly and no
repository/Jira lookup is needed. Otherwise warn and stop because the investigation would be based
on incomplete context.

For Jira tickets, usable Jira access is required unless the user provides the ticket summary,
acceptance criteria, key comments, linked-doc excerpts, and affected environment details directly.
`.jira-config.yml` is optional when the Jira environment variables work. If a Jira key or URL is
supplied but the ticket cannot be read and no direct ticket details are provided, stop instead of
producing a low-confidence investigation.

**Mandatory auth discovery before declaring Jira/Confluence inaccessible.** The agent must walk
the [auth discovery order](../../../../docs/auth-discovery.md#discovery-order) before reporting
that Jira or Confluence is unavailable:

1. Check `.agent-skills.yml` for `jira:` / `confluence:` host metadata.
2. Check `.jira-config.yml` for placeholder structure (`${JIRA_HOST}`, etc.).
3. Check `.env` and `.env.local` for actual values.
4. Check process environment variables.
5. Run `python3 scripts/auth-preflight.py` (or pass `--require-jira` when Jira is in scope).
   The preflight resolves placeholders, validates required fields, and exits 0/1/2 without
   printing any secret values.
6. Only after the preflight returns non-usable should the agent ask the user — and the ask must
   name the specific missing or unresolved fields (never the secret value).

Treat unresolved `${VAR}` placeholders in `.jira-config.yml` as **incomplete configuration**, not
as missing auth. The fix is to load `.env` (or set the variable in the process environment), not
to ask the user for credentials. Most Jira CLIs do not expand `${VAR}` placeholders themselves;
either source `.env` first (`set -a && source .env && set +a`) or rely on the auth preflight.

If config exists but is incomplete, the investigator must report:

- which non-secret fields are unresolved (e.g. `${JIRA_HOST}` not set in `.env`),
- which secret fields are missing (redacted, never echoed),
- the smallest fix (typically: rerun `./setup.init` or add the missing key inside the
  `# >>> agent-skills setup.init` block of `.env`),
- whether the investigation can continue from supplied issue text alone (it can, with a
  clearly-marked limitation).

Required setup variables:

- `WORKSPACE_ROOT` — required in `local-workspace` mode for resolving repos,
  cache, and local context. In `in-repo` mode the repository root is used.
- `PROJECTS_JSON` — required in `local-workspace` mode for matching affected
  repos/services to stack and commands. In `in-repo` mode the `project:` block in
  `.agent-skills.yml` replaces this.
- `JIRA_HOST`, `JIRA_API_TOKEN`, `JIRA_AUTH_TYPE` — required only for Jira
  tickets, used for Jira ticket lookup.
- `JIRA_LOGIN` — required for basic auth and recommended for bearer auth; used as
  Jira CLI identity.
- `JIRA_CONFIG_FILE` — optional Jira CLI config path.
- `CONFLUENCE_HOST`, `CONFLUENCE_API_TOKEN` — required only when linked docs
  require them, used for Confluence lookup.
- `ISSUE_INVESTIGATOR_CACHE_DIR` — optional cache dir for fetched ticket/doc
  summaries; default
  `${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/issue-investigator}`.
- `ISSUE_INVESTIGATOR_CACHE_TTL_HOURS` — optional cache TTL; default `24`.
- `ENVIRONMENTS_JSON` — optional JSON array of deployed-environment pointers
  (name, type, access, ssh_target, kubectl_context, namespace, log_paths,
  log_aggregator, notes). Stores POINTERS ONLY — never credentials. When
  present, the investigator uses these handles for the read-only environment
  evidence channel described in [Environment evidence
  access](#environment-evidence-access). When absent, the investigator falls
  back to asking the user where the affected environment lives.

For GitHub issues, prefer the authenticated `gh` CLI when available. Do not require new secrets in
this public skill unless the user's environment already uses them.

If setup is incomplete, output:

> Missing required setup: `<NAME or file>`. I will not continue with issue-aware investigation
> because the result would be based on incomplete context. Add/update `${WORKSPACE_ROOT}/.env`
> (local-workspace) or `.agent-skills.yml` at the repo root (in-repo — see
> `agent-skills/.agent-skills.example.yml`), provide the missing issue details directly, or rerun
> without the unavailable issue source.

## Required Workflow

### 0. Requirement Understanding Gate

This is the strongest place in the repository to apply the
[requirement-understanding workflow](../../../../docs/requirement-understanding.md). Investigation
is where most agents quietly assume the requirement and then justify the assumption with
evidence. Run the twelve-step gate before step 1 and emit the `Requirement Understanding` block
in the user-facing output above the rest of the investigation result.

The gate output for an investigation must include, in addition to the standard fields:

- The classified issue type from step 2 below, with confidence.
- Expected vs actual behavior, distinguishing **ticket facts**, **log/code evidence**, and
  **agent assumptions** — not merged into one paragraph.
- Both a **root-cause confidence** (how sure the agent is about the cause) and a
  **requirement-understanding confidence** (how sure the agent is about what the system *should*
  be doing). These are independent: a high-confidence root cause for the wrong requirement is
  worse than no investigation at all.
- A list of missing evidence and the cheapest read-only check that would close each gap.

Binding rules (from the workflow's confidence-to-action section):

- **`unknown`** — the agent cannot describe expected behavior, the issue source is missing
  inputs, or candidate interpretations cannot be discriminated. Readiness is
  `NEEDS_CLARIFICATION` or `NEEDS_EVIDENCE`. Do not recommend a fix, rollback, configuration
  change, or data correction. Permitted recommendations are `monitoring or alerting improvement`,
  `product clarification`, or `documentation`.
- **`low`** — expected behavior is partially known but at least one load-bearing assumption is
  unverified, or there is an unresolved contradiction. Recommendations limited to
  `clarification`, `monitoring`, `documentation`, or further `investigation`. Do not promote a
  hypothesis to `confirmed` and do not hand off a `code fix` recommendation.
- **`medium`** — may run the [three-hypothesis discipline](#three-hypothesis-discipline), the
  [regression triage](#regression-triage-when-the-issue-worked-before) ladder, and propose
  bounded read-only checks the user can run. Recommendations may include `rollback` (if a clear
  introducing commit exists) or `code fix` only when the recommendation matches the evidence
  gate in step 5. Every load-bearing assumption stays visible.
- **`high`** — may recommend a confirmed-cause action (`code fix`, `rollback`, `configuration
  change`, `data correction`) when the evidence gate in step 5 is met. The first plausible
  explanation is not `high` — it requires disconfirming checks that were run or judged
  unnecessary because evidence already excluded the alternatives.

A recommendation must never be more confident than the lower of root-cause confidence and
requirement-understanding confidence. If the agent is sure about the cause but unsure about what
the system should do, hand off to [`product-owner`](../../../product-owner/SKILL.md) before
recommending a fix.

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

- **Read project documentation before guessing.** Start with the repository `README.md`,
  `CONTRIBUTING.md`, any `docs/` index, and the **per-module `README.md`** of each module
  involved in the report. They commonly document expected setup, runtime versions, required
  services, supported configurations, and known constraints — facts that change classification
  ("env issue" vs "bug") and prevent investigations from labelling a documented-but-unmet
  prerequisite as a defect. For build/test failures specifically, read the affected module's
  README before treating the failure as the root cause.
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

#### Environment evidence access

The single most useful piece of evidence for many production and regression issues is a log line,
metric, or deployed-config value from the environment where the issue actually occurred. Local
repros are useful but they cannot prove root cause when the trigger is environment-specific (RBAC
rules, feature flags, secrets, network policy, data shape, traffic volume, deploy timing).

When `ENVIRONMENTS_JSON` is configured, treat its entries as the **first-class evidence channel**
for the affected environment. For each entry the investigator may use:

- `access: ssh` — read-only shell evidence: `tail`, `grep`, `journalctl --since`, `zgrep` over
  `log_paths`, `cat` of deployed config files, `systemctl status <unit>`, `ps`, `ss -tlnp`, `df`,
  `free`, `uptime`, `dmesg | tail`. Never `>`, `>>`, `tee`, `kill`, `systemctl restart`,
  `iptables`, `rm`, `mv`, package installs, `sudo` mutations, or anything that touches state.
- `access: kubectl` — read-only k8s evidence: `kubectl --context <kubectl_context> -n <namespace>`
  with `get`, `describe`, `logs`, `top`, `events`, `get pod -o yaml`, `get configmap -o yaml`,
  `get secret <name>` (metadata only — do not exfiltrate values). Never `apply`, `patch`,
  `delete`, `exec` into a writable shell, `port-forward` to a write endpoint, `scale`, `rollout
  restart`, or any imperative mutation.
- `access: log-aggregator` — a read-only saved search or query string against the URL in
  `log_aggregator` (Splunk, ELK/Kibana, Datadog, CloudWatch Logs Insights, Grafana Loki).
  Bound every query with a time window and a service/host filter; never propose an unbounded
  scan over a multi-day window.
- `access: cloud-console` — propose the exact navigation path ("AWS Console → CloudWatch → Log
  groups → `/aws/lambda/<function>` → last 1h") so the user can read it themselves.
- `access: none` — do not attempt access. Describe what evidence would help and what access
  would unblock it.

**Production guardrails (`type: prod`).** For any environment whose `type` is `prod`, the default
behaviour is *propose, do not run*: print the exact read-only command and ask the user to run it
and paste back the output. The agent runs the command itself only when the user has explicitly
authorized it for that investigation, the command is read-only by construction, and the entry's
`notes` do not say otherwise (e.g. `agent-must-not-run-itself`, `ticket-required-for-prod`).

**Credentials boundary.** `ENVIRONMENTS_JSON` stores pointers only. SSH keys live in `~/.ssh`,
cluster credentials in kubeconfig, log-aggregator login in the user's session. The investigator
must never propose copying private keys, tokens, or passwords into agent-skills files, prompts, or
the evidence pack. If a command would expose a secret value (e.g. `kubectl get secret <name> -o
yaml`), redact the value before persisting and prefer metadata-only inspection.

**Evidence quoting.** When evidence comes from a real environment, capture: environment name and
type, command actually run (or proposed and confirmed by the user), timestamp, the relevant log
lines or query result *verbatim and bounded*, and any redactions applied. Persist to the evidence
pack so downstream skills (software-engineer, code-reviewer, test-automation-engineer) can reuse
the same proof without re-querying production.

**When `ENVIRONMENTS_JSON` is absent.** Ask the user once which environment the issue occurred in
and whether they have read-only access (own SSH, kubectl context, log-aggregator login). Do not
invent hostnames, contexts, or log paths. If access is unavailable, fall back to [Safe read-only
checks the user can run](#safe-read-only-checks-the-user-can-run) and clearly state that
environment evidence is missing.

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

#### Safe read-only checks the user can run

When direct access to the affected environment, database, log aggregator, or ticket system is
unavailable, do not stop at "missing evidence". Propose a short list of **safe, read-only commands
or queries** the user can run themselves to narrow the cause. Each suggestion must satisfy all of
the following:

- **Classified out loud as `read-only` or `mutating`.** Every check must carry one of those
  two labels. A check whose classification cannot be determined is treated as `mutating` and
  not proposed. This skill is read-only by default; mutating checks are not proposed at all
  here — they belong in a [`software-engineer`](../../SKILL.md) operator runbook.
- Read-only by construction. No `INSERT`, `UPDATE`, `DELETE`, `DROP`, `TRUNCATE`, no flag flips, no
  config writes, no deploys, no cache busts. SQL examples must be wrapped in
  `SET TRANSACTION READ ONLY` (or a read-replica) where the engine supports it.
- Bounded blast radius. Add `LIMIT`, time windows, single-row predicates, or `--dry-run` flags.
  Never propose a full-table scan on a production-scale table without a bounding clause.
- Clearly labelled with the environment they are safe in (local, staging, read-replica, snapshot,
  ephemeral). Do not propose running a check against live production data unless the user has
  already stated that read-only production access is the only path and the query is bounded.
- Stated as portable templates with `<placeholders>`. Do not invent table names, column names,
  service names, hostnames, or ticket keys; mark them as placeholders.
- Tied to a hypothesis. Each check should discriminate between at least two of the candidate
  causes from the [three-hypothesis discipline](#three-hypothesis-discipline), or fill a specific
  evidence gap from `Open Questions Or Missing Evidence`.
- **Never require a credential the user has not already configured.** Do not ask the user to
  paste a token, password, connection string, or any secret value into chat. If a check
  requires a credential, instruct the user to put it in the configured secret-injection path
  (see [docs/configuration.md](../../../../docs/configuration.md)) with `0600` permissions
  and re-invoke. Pasting a secret into chat is forbidden by the
  [destructive-action safety policy](../../../../docs/destructive-action-safety.md#discovered-credential-protocol).

If no safe check is possible without access the user does not have, say so and list what access
(read-replica, snapshot, log slice, anonymized HAR) would unblock the investigation. Do not invent
commands that pretend to be safe when they are not.

#### Discovered-credential protocol

If the investigation surfaces a credential, token, key, password, kubeconfig, or connection
string anywhere — checked-in file, log line, command output, environment dump, screenshot,
ticket comment, or another tool's context:

- **Do not invoke it.** Do not export it, paste it into a tool, or use it to verify "if it
  works".
- **Do not echo the value.** In any output, evidence pack, summary, or PR description, quote
  at most a redacted prefix needed to identify the leak.
- **Surface it as a security finding** in this investigation's result, with severity
  `blocker` or `major` decided by blast radius, and recommend rotation through normal
  credential-rotation channels.
- **Treat the leak as evidence to report, not authorization to act.** The discovered
  credential's existence does not make it authorized to use against any environment.
- See the
  [destructive-action safety policy → discovered-credential protocol](../../../../docs/destructive-action-safety.md#discovered-credential-protocol)
  for the full procedure.

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
- Environment evidence (env name, type, access method, command run or proposed, redactions):

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

## Safe Checks The User Can Run

- Hypothesis being tested:
- Environment (local | staging | read-replica | snapshot | ephemeral | read-only production):
- Classification: read-only | mutating  (this skill proposes only `read-only`)
- Read-only command/query (with placeholders, bounded scope):
- What a positive result would mean:
- What a negative result would mean:

(Repeat one block per check. Write `none — no safe check is possible without <access type>` if no
safe check exists with the access the user currently has.)

## Open Questions Or Missing Evidence

- ...
```

Normal output must include every section above unless the user asked only for a narrow partial
analysis. If a section cannot be completed, write `not available` and explain what evidence is
missing.

## Behavior Checklist

- [ ] Issue source, affected area, expected behavior source, actual behavior evidence, and access
  limits are stated.
- [ ] Issue type classification is supported by evidence and confidence.
- [ ] Reproduction status records environment, steps attempted, observed result, and missing data.
- [ ] Root-cause status is `unknown`, `suspected`, `confirmed`, or `disproved` and never overstated.
- [ ] When direct environment access is unavailable, `Safe Checks The User Can Run` lists at least
  one bounded read-only check tied to a hypothesis, or explicitly says no safe check is possible
  with the current access.
- [ ] Recommended next action meets the evidence gate and hands implementation/review/testing to
  the right skill.

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
- Do not promote a root-cause hypothesis to `confirmed` when requirement-understanding
  confidence is `unknown` or `low`. The recommended next action must respect both confidences
  and the [Requirement Understanding Gate](#0-requirement-understanding-gate) readiness
  decision.
- Do not mutate production data, configuration, or environments without explicit approval and a
  rollback plan.
- Do not assume every issue is a code bug.
- Do not treat missing credentials or inaccessible systems as proof of behavior.
- Do not propose a "safe check" that writes, deletes, deploys, flips a flag, busts a cache, or
  scans a production-scale table without a bounding clause. Read-only by construction or do not
  propose it.
- Do not run any command against an environment whose `type` is `prod` in `ENVIRONMENTS_JSON`
  without explicit per-investigation user approval; default to *propose, do not run*. The agent
  may run commands itself only when the command is read-only by construction, the user has
  authorized this investigation, and the entry's `notes` do not forbid it.
- Do not copy SSH private keys, cluster credentials, API tokens, passwords, or any secret value
  into agent-skills files, prompts, or the evidence pack. `ENVIRONMENTS_JSON` stores pointers
  only; real credentials live in `~/.ssh`, kubeconfig, the user's log-aggregator session, etc.
- Do not invoke a credential, token, or key discovered during investigation. Surface it as a
  security finding and recommend rotation; never use it to call the affected system. See
  [Discovered-credential protocol](#discovered-credential-protocol).
- Do not ask the user to paste a secret value into chat. Direct them to the configured
  secret-injection path and re-invoke.
- Do not propose a check whose classification (`read-only` or `mutating`) cannot be
  determined. Treat indeterminate as `mutating` and decline.
- Do not violate any rule in the
  [destructive-action safety policy](../../../../docs/destructive-action-safety.md). It is a
  floor, not a ceiling, and is not waivable by user prompt.
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

See [the issue-investigator bug report
example](../../../../docs/examples/issue-investigator-bug-report.md) and [starter
prompts](../../../../docs/starter-prompts.md).
