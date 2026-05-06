# Definition of Done

A machine-readable checklist `software-engineer` produces at the end of Phase 5 (Commit & PR) and
that `code-reviewer` must verify before declaring `PASS` on the outer-loop or PR review.

The file is small and explicit. It exists to prevent silent shortcuts (`--no-verify`, skipped tests,
missing regression test for a bug fix) from making it into a PR.

```
${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills}/<issue-key>/definition-of-done.json
```

## Schema

```jsonc
{
  "issue_key": "PROJ-1234",
  "primary_jira_key": "PROJ-1234",
  "related_jira_keys": [],
  "produced_by": "software-engineer",
  "produced_at": "2026-04-26T15:30:00Z",
  "branch": "bugfix/PROJ-1234-saml-expiry-redirect",
  "head_sha": "deadbee1234",
  "base_branch": "main",
  "pr_url": "https://github.com/example-org/example-api/pull/987",

  // Build & test
  "build": {
    "command": "mvn clean verify",
    "passed": true,
    "skipped_steps": [], // populated only with explicit user-approved waivers
  },
  "tests": {
    "unit_passed": true,
    "integration_passed": true,
    "coverage_on_changed_lines_pct": 92,
    "coverage_target_pct": 80,
  },
  "format": {
    "command": "mvn fmt:check",
    "passed": true,
  },
  "lint_or_static_analysis": {
    "ran": true,
    "tools": ["sonarlint", "spotbugs"],
    "new_findings": 0,
  },
  "security_scan": {
    "ran": true,
    "tool": "owasp-dependency-check",
    "new_findings": 0,
  },

  // Bug-fix specific (omit for refactor/feature/docs)
  "bug_fix": {
    "is_bug_fix": true,
    "regression_test_commit": "fa11ed00", // Phase 1.5: failing test FIRST
    "fails_on_parent": true, // verified by code-reviewer --repro-verify
    "passes_on_head": true,
    "repro_recipe_path": ".cache/agent-skills/PROJ-1234/repro-recipe.yml",
    "observability_added": true, // log/metric/correlation-id added if investigation lacked evidence
    "observability_notes": "Added correlation_id to AuthFilter error path.",
  },

  // Operational hygiene
  "git": {
    "no_force_push": true,
    "no_no_verify": true, // --no-verify was NOT used to bypass hooks
    "branch_starts_with_ticket_key": true,
    "commit_message_starts_with_ticket_key": true,
    "single_jira_issue_scope": true,
    "primary_jira_key": "PROJ-1234",
    "related_jira_keys": [],
    "open_pr_checked_for_existing_work": true,
    "pushed_to_remote": true,
    "pr_url": "https://github.com/example-org/example-api/pull/987",
  },
  "scope": {
    "no_unrelated_files": true,
    "no_ide_configs_committed": true,
    "shared_library_changed": false,
    "shared_library_consumers_listed": [],
  },

  // Safety acknowledgement (REQUIRED whenever the change introduces or
  // performs ANY mutating action against a deployed environment, or
  // touches credentials / IAM / secrets / backups / monitoring / network
  // policy. Omit only when the entire change is local-only with NO
  // deployed-environment mutation, NO credential/IAM/secret change, NO
  // backup/monitoring/network change. When omitted, set
  // `safety_acknowledgement.applies: false` with a one-line reason.)
  "safety_acknowledgement": {
    "applies": true,
    "policy_version": "v1",
    "policy_path": "docs/destructive-action-safety.md",
    "environment": "staging", // local | dev | staging | production
    "environment_confirmed_via": "${ENVIRONMENTS_JSON}.entries[name=stg-eu]",
    "blast_radius": "single bucket in staging account; no PII; backup retention untouched",
    "credential_used": "ci-deploy-staging (least-privilege, scoped to staging bucket put/get)",
    "credential_source": "host-secret-manager", // host-secret-manager | env-var | user-session
    "no_discovered_credentials_invoked": true, // discovered creds reported, never used
    "no_in_repo_tokens_invoked": true,
    "destructive_command_used": false, // true ONLY for authorized destructive maintenance
    "destructive_command_authorization": null, // {"approver": "...", "ticket": "...", "runbook_path": "..."}
    "backups_isolated": true, // backup credential != action credential; no cascade-delete
    "backup_restore_tested": null, // ISO date | "n/a" when no destructive step relies on restore
    "execution_path": "ci-pipeline", // agent | ci-pipeline | operator-runbook | not-applicable
    "human_approver": null, // required when execution_path = operator-runbook or destructive_command_used = true
    "monitoring_unchanged": true,
    "iam_unchanged": true,
    "network_policy_unchanged": true,
  },

  // Free-form waivers (each must have a written reason)
  "waivers": [
    // {"item": "tests.coverage_on_changed_lines_pct", "actual": 71, "reason": "generated mapper code; covered by upstream test"}
  ],
}
```

## Rules

- **Every boolean flagged `false` must appear in `waivers[]` with a reason** before the reviewer can
  issue `PASS`. Otherwise the reviewer raises a `blocker` finding.
- **`bug_fix.is_bug_fix: true`** requires `regression_test_commit`, `fails_on_parent: true`, and
  `passes_on_head: true`. The reviewer verifies this in `--repro-verify` mode (checks out the parent
  of `regression_test_commit`, runs the test, expects failure; runs it on HEAD, expects success).
- **`git.no_no_verify: false`** is itself a `blocker` unless waived with explicit user approval
  recorded in `waivers[]`.
- **`git.single_jira_issue_scope: false`** is a `blocker` for ticket-driven work. One Jira task
  maps to one branch and one PR. Related keys may be listed as context, but independent tasks must
  be split before PR.
- **`git.open_pr_checked_for_existing_work: false`** is a `major` finding when Jira is in scope.
  A likely existing PR or remote branch for the same key must be surfaced before creating a
  competing branch.
- **`git.pushed_to_remote: false`** or a missing `git.pr_url` means the change is not PR-ready. The
  reviewer must not report final shipping readiness until the branch has been pushed and the PR URL
  is recorded, unless the workflow is explicitly blocked by unavailable GitHub access.
- **`scope.shared_library_changed: true`** requires a non-empty
  `scope.shared_library_consumers_listed` (downstream services to flag).
- **`safety_acknowledgement` is required whenever the change introduces or performs any
  mutating action against a deployed environment, or touches credentials / IAM / secrets /
  backups / monitoring / network policy.** When the change is local-only with no such
  surface, set `safety_acknowledgement.applies: false` with a one-line reason and the
  remaining fields may be omitted.
- When `safety_acknowledgement.applies: true`, the reviewer raises a `blocker` if any of:
  `no_discovered_credentials_invoked: false`, `no_in_repo_tokens_invoked: false`,
  `destructive_command_used: true` without a populated `destructive_command_authorization`
  block (approver + ticket + runbook_path), `execution_path: agent` for a
  destructive/IAM/secret/backup change, `monitoring_unchanged: false` /
  `iam_unchanged: false` / `network_policy_unchanged: false` without an explicit waiver
  reason in `waivers[]`. See the
  [destructive-action safety policy](../../../docs/destructive-action-safety.md).
- A missing `safety_acknowledgement` block on a change that obviously *should* have one (the
  diff touches IaC, CI deployment, IAM, secret stores, migrations, or any cloud-provider
  command) is itself a `blocker` finding. The reviewer must not declare `PASS` until the
  block is added.
- The file is regenerated on every Phase 5 run; it is not a long-lived artifact, just the gate
  signal between engineer and reviewer.

## Producing it

`software-engineer` writes this file as the last step of Phase 5.1 (Commit) and updates it again
before opening the PR. The reviewer reads it as part of the outer-loop hard handoff (see
`code-reviewer` Step 1, hard handoff contract).

If the project has its own internal definition-of-done, prefer it; this schema is a portable
fallback. Either way, the artifact must exist before the reviewer can declare `PASS`.
