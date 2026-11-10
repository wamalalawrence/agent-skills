# Definition of Done

A machine-readable record `software-engineer` produces at the end of Phase 5 (Commit & PR) and
that `code-reviewer` must verify before declaring `PASS` on the outer-loop or PR review.

It exists to prevent silent shortcuts (`--no-verify`, skipped tests, a missing regression test
for a bug fix) from reaching a PR, and — since `1.0.0` — to make "done" a checkable statement
rather than a claim. The rules behind it are in
[evidence discipline](../../../docs/evidence-discipline.md); this page is the artifact.

```
${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills}/<issue-key>/definition-of-done.json
```

Validate it with:

```bash
agent-skills dod-check <path>/definition-of-done.json     # or: python3 scripts/dod-check.py
```

Exit `0` is verified; `1` prints one reason per line; `2` means the file is missing or not this
schema. `finish-task` runs the same check when the file is present and records the result in
telemetry as `verified_delivery`.

## Three kinds of field

The schema separates questions that used to share one shape:

| Kind | Examples | Values | Waivable |
| --- | --- | --- | --- |
| **Check** | `build`, `tests`, `regression_red` | `pass` · `fail` · `not_run` · `not_applicable` | `fail` / `not_run` only, by a named authority |
| **Classification** | `is_bug_fix`, `shared_library_changed` | `true` / `false` | never — it is a fact, not an obligation |
| **Safety acknowledgement** | `applies`, `execution_path` | per the policy | per the [destructive-action policy](../../../docs/destructive-action-safety.md) |

A check that `pass`es carries the execution record that produced it. Without the record it is
a claim, and `dod-check` refuses it.

## Schema

```jsonc
{
  "schema": "agent-skills.definition-of-done/v2",
  "issue_key": "PROJ-1234",
  "primary_jira_key": "PROJ-1234",
  "related_jira_keys": [],
  "produced_by": "software-engineer",
  "produced_at": "2026-09-11T15:30:00Z",
  "branch": "bugfix/PROJ-1234-saml-expiry-redirect",
  "head_sha": "deadbee1234",          // every check's revision must match this
  "base_branch": "main",
  "pr_url": "https://github.com/example-org/example-api/pull/987",

  // Checks. Each is pass | fail | not_run | not_applicable. A pass records how
  // it was observed; a not_applicable records why; a fail or not_run needs a
  // waiver below or it blocks verified delivery.
  "checks": {
    "build": {
      "result": "pass",
      "command": "mvn clean verify",
      "cwd": "services/example-api",
      "revision": "deadbee1234",
      "exit_code": 0,
      "evidence": ".cache/agent-skills/PROJ-1234/logs/build.log",
      "reused": false                  // true when an unchanged-revision result was reused
    },
    "tests": {
      "result": "pass",
      "command": "mvn test -Pintegration",
      "cwd": "services/example-api",
      "revision": "deadbee1234",
      "exit_code": 0,
      "evidence": ".cache/agent-skills/PROJ-1234/logs/tests.log",
      "coverage_on_changed_lines_pct": 92,
      "coverage_target_pct": 80
    },
    "format": {
      "result": "pass",
      "command": "mvn fmt:check",
      "cwd": "services/example-api",
      "revision": "deadbee1234",
      "exit_code": 0
    },
    "lint_or_static_analysis": {
      "result": "pass",
      "command": "mvn spotbugs:check sonarlint:check",
      "cwd": "services/example-api",
      "revision": "deadbee1234",
      "exit_code": 0,
      "new_findings": 0
    },
    "security_scan": {
      "result": "not_applicable",
      "reason": "no dependency or configuration change in this diff"
    },

    // Bug fixes only (classification.is_bug_fix = true). RED is the regression
    // test run against the unfixed implementation WITH the test present, and
    // the assertion is the behavioural one that failed — a missing test, zero
    // collected tests, or a setup error is not RED. The command asserts the
    // failure (exit 0 = failed as expected) from head_sha; the baseline and the
    // test's own exit code sit beside it.
    "regression_red": {
      "result": "pass",
      "command": "git worktree add ../red fa11ed00 && cd ../red && ! mvn test -Dtest=SamlExpiryRedirectTest",
      "cwd": "services/example-api",
      "revision": "deadbee1234",
      "exit_code": 0,
      "baseline_revision": "fa11ed00",  // the test-only commit, or the isolated baseline
      "test_exit_code": 1,
      "assertion": "expected 302 to /login, got 200",
      "evidence": ".cache/agent-skills/PROJ-1234/logs/red.log"
    },
    "regression_green": {
      "result": "pass",
      "command": "mvn test -Dtest=SamlExpiryRedirectTest",
      "cwd": "services/example-api",
      "revision": "deadbee1234",
      "exit_code": 0,
      "evidence": ".cache/agent-skills/PROJ-1234/logs/green.log"
    },

    // Conditional contracts (evidence-discipline.md). Record not_applicable
    // with a reason when the change does not touch the surface.
    "docs_contract": {
      "result": "pass",
      "command": "npm run openapi:check",
      "cwd": "services/example-api",
      "revision": "deadbee1234",
      "exit_code": 0,
      "owning_document": "docs/api/openapi.yaml"
    },
    "ui_visual": {
      "result": "not_applicable",
      "reason": "backend-only change"
    }
  },

  // Classifications. Facts about the change. Never pass/fail, never waived.
  "classification": {
    "is_bug_fix": true,
    "repro_recipe_path": ".cache/agent-skills/PROJ-1234/repro-recipe.yml",
    "observability_added": true,
    "observability_notes": "Added correlation_id to AuthFilter error path.",
    "shared_library_changed": false,
    "shared_library_consumers_listed": [],
    "no_unrelated_files": true,
    "no_ide_configs_committed": true
  },

  // Operational hygiene. These are checks in boolean clothing and are read
  // as checks: a `false` here is a `fail` and needs a waiver.
  "git": {
    "no_force_push": true,
    "no_no_verify": true,
    "branch_starts_with_ticket_key": true,
    "commit_message_starts_with_ticket_key": true,
    "single_jira_issue_scope": true,
    "open_pr_checked_for_existing_work": true,
    "pushed_to_remote": true
  },

  // Safety acknowledgement. Required whenever the change introduces or
  // performs ANY mutating action against a deployed environment, or touches
  // credentials / IAM / secrets / backups / monitoring / network policy.
  // Otherwise `applies: false` with a one-line reason and nothing else.
  "safety_acknowledgement": {
    "applies": false,
    "reason": "local-only code change; no deployed-environment mutation"
  },

  // Waivers. One per failed or unrun check. The authority is who approved it,
  // and it is never the agent that wrote this file.
  "waivers": [
    // {
    //   "check": "tests",
    //   "reason": "generated mapper code; covered by upstream contract test",
    //   "authority": "user",          // user | reviewer | project-policy | ticket
    //   "scope": "PROJ-1234 only",
    //   "recorded_at": "2026-09-11T15:20:00Z"
    // }
  ]
}
```

The `safety_acknowledgement` block, when `applies: true`, carries the fields the
[destructive-action policy](../../../docs/destructive-action-safety.md) requires:
`policy_version`, `environment`, `environment_confirmed_via`, `blast_radius`, `credential_used`,
`credential_source`, `no_discovered_credentials_invoked`, `no_in_repo_tokens_invoked`,
`destructive_command_used`, `destructive_command_authorization`, `backups_isolated`,
`backup_restore_tested`, `execution_path`, `human_approver`, `monitoring_unchanged`,
`iam_unchanged`, `network_policy_unchanged`. Unchanged from before `1.0.0`.

## Rules

- **Verified delivery requires every required check to be `pass` on `head_sha`, or
  `not_applicable` with a reason, or waived by a named authority.** Required always:
  `build`, `tests`, `format`, `lint_or_static_analysis`, `security_scan`. Required when
  `classification.is_bug_fix` is `true`: `regression_red`, `regression_green`.
- **A pass without an execution record is not a pass.** `command`, `cwd`, `revision`, and
  `exit_code` are mandatory on a pass; `regression_red` also needs `assertion`. A recorded
  `revision` that is not `head_sha` is stale evidence; for `regression_red` the test-only
  baseline goes in `baseline_revision`.
- **`regression_red` proves the defect, not the absence of a test.** The reviewer verifies it in
  `--repro-verify` mode by running the named test on a baseline that **contains the test and not
  the fix** — the test-only commit, or an isolated checkout with the test transplanted — and
  confirming the behavioural assertion failed. Then the same test on `head_sha` must pass. A
  parent commit without the test is not a valid baseline.
- **Classifications are never waived.** `shared_library_changed: false` is a fact. A waiver
  naming a classification is itself a finding. `shared_library_changed: true` requires a
  non-empty `shared_library_consumers_listed`.
- **`git.*` booleans are checks.** `no_no_verify: false` is a `blocker` unless waived with
  explicit user approval recorded in `waivers[]`. `single_jira_issue_scope: false` is a
  `blocker` for ticket-driven work. `open_pr_checked_for_existing_work: false` is a `major`
  when Jira is in scope. `pushed_to_remote: false` or a missing `pr_url` means the change is not
  PR-ready.
- **A waiver names its authority.** `agent` is not one. An agent may *propose* a waiver in its
  output and record it only after the user, the reviewer, a project policy, or a ticket has
  approved it.
- **Exhausting the review budget does not convert a failed check into a follow-up.** The file
  keeps the `fail`; the verdict stays `REQUEST_CHANGES`.
- **`safety_acknowledgement` is required whenever the change introduces or performs any
  mutating action against a deployed environment, or touches credentials / IAM / secrets /
  backups / monitoring / network policy.** When `applies: true`, the reviewer raises a `blocker`
  for any of: `no_discovered_credentials_invoked: false`, `no_in_repo_tokens_invoked: false`,
  `destructive_command_used: true` without a populated `destructive_command_authorization`
  block (approver + ticket + runbook_path), `execution_path: agent` for a
  destructive/IAM/secret/backup change, or `monitoring_unchanged: false` /
  `iam_unchanged: false` / `network_policy_unchanged: false` without a waiver. A missing block on
  a change that obviously should have one (IaC, CI deployment, IAM, secret stores, migrations,
  any cloud-provider command) is itself a `blocker`.
- The file is regenerated on every Phase 5 run; it is a gate signal between engineer and
  reviewer, not a long-lived artifact.

## Optional fields

`dod-check` does not require these in `1.6.0`; a file without them verifies as before. Waivers
cover required checks only: an optional check that is `not_run` with a `reason` needs none.

- **`checks.mutation`** — at execution profile `RIGOROUS` (`software-engineer` 3.2). Fields:
  `result`, `command`, `revision`, `exit_code`, `killed`, `total`, `survived_on_changed_lines`
  (each with its added assertion or a reason), and `reason` when the result is `not_run`. The
  reviewer, not `dod-check`, treats an absent or reasonless record as `major`.
- **`checks.regression_red.predicted`** — the failure expected before the RED run
  (`software-engineer` 1.5). `dod-check` still requires only `assertion`. When they differ, the
  evidence says why before the fix.

## Producing it

`software-engineer` writes this file as the last step of Phase 5.1 (Commit) and updates it again
before opening the PR. Then it runs `dod-check` on its own artifact and puts the one-line result in
the lifecycle receipt. The reviewer reads the file as part of the outer-loop hard handoff (see
`code-reviewer` Step 1) and runs `dod-check` itself; it does not trust the engineer's line.

If the project has its own definition of done, prefer it; this schema is a portable fallback.
Either way, the artifact must exist and verify before the reviewer can declare `PASS`.

## Migrating from the pre-1.0 shape

The old file carried booleans (`build.passed`, `tests.unit_passed`, `bug_fix.fails_on_parent`) and
the rule "every `false` needs a waiver". `dod-check` reports that shape as unverifiable rather than
verified. Regenerate the file: each boolean becomes a check with a result and an execution record,
`bug_fix.*` becomes `classification.is_bug_fix` plus `regression_red` / `regression_green`, and
`scope.*` becomes `classification.*`.
