# Definition of Done

A machine-readable checklist `software-engineer` produces at the end of Phase 5 (Commit & PR) and that `code-reviewer` must verify before declaring `PASS` on the outer-loop or PR review.

The file is small and explicit. It exists to prevent silent shortcuts (`--no-verify`, skipped tests, missing regression test for a bug fix) from making it into a PR.

```
${WORKSPACE_ROOT}/.cache/agent-skills/<issue-key>/definition-of-done.json
```

## Schema

```jsonc
{
  "issue_key": "PROJ-1234",
  "produced_by": "software-engineer",
  "produced_at": "2026-04-26T15:30:00Z",
  "branch": "bugfix/PROJ-1234-saml-expiry-redirect",
  "head_sha": "deadbee1234",
  "base_branch": "main",

  // Build & test
  "build": {
    "command": "mvn clean verify",
    "passed": true,
    "skipped_steps": []                 // populated only with explicit user-approved waivers
  },
  "tests": {
    "unit_passed": true,
    "integration_passed": true,
    "coverage_on_changed_lines_pct": 92,
    "coverage_target_pct": 80
  },
  "format": {
    "command": "mvn fmt:check",
    "passed": true
  },
  "lint_or_static_analysis": {
    "ran": true,
    "tools": ["sonarlint", "spotbugs"],
    "new_findings": 0
  },
  "security_scan": {
    "ran": true,
    "tool": "owasp-dependency-check",
    "new_findings": 0
  },

  // Bug-fix specific (omit for refactor/feature/docs)
  "bug_fix": {
    "is_bug_fix": true,
    "regression_test_commit": "fa11ed00",   // Phase 1.5: failing test FIRST
    "fails_on_parent": true,                // verified by code-reviewer --repro-verify
    "passes_on_head": true,
    "repro_recipe_path": ".cache/agent-skills/PROJ-1234/repro-recipe.yml",
    "observability_added": true,            // log/metric/correlation-id added if investigation lacked evidence
    "observability_notes": "Added correlation_id to AuthFilter error path."
  },

  // Operational hygiene
  "git": {
    "no_force_push": true,
    "no_no_verify": true,                   // --no-verify was NOT used to bypass hooks
    "branch_starts_with_ticket_key": true,
    "commit_message_starts_with_ticket_key": true
  },
  "scope": {
    "no_unrelated_files": true,
    "no_ide_configs_committed": true,
    "shared_library_changed": false,
    "shared_library_consumers_listed": []
  },

  // Free-form waivers (each must have a written reason)
  "waivers": [
    // {"item": "tests.coverage_on_changed_lines_pct", "actual": 71, "reason": "generated mapper code; covered by upstream test"}
  ]
}
```

## Rules

- **Every boolean flagged `false` must appear in `waivers[]` with a reason** before the reviewer can issue `PASS`. Otherwise the reviewer raises a `blocker` finding.
- **`bug_fix.is_bug_fix: true`** requires `regression_test_commit`, `fails_on_parent: true`, and `passes_on_head: true`. The reviewer verifies this in `--repro-verify` mode (checks out the parent of `regression_test_commit`, runs the test, expects failure; runs it on HEAD, expects success).
- **`git.no_no_verify: false`** is itself a `blocker` unless waived with explicit user approval recorded in `waivers[]`.
- **`scope.shared_library_changed: true`** requires a non-empty `scope.shared_library_consumers_listed` (downstream services to flag).
- The file is regenerated on every Phase 5 run; it is not a long-lived artifact, just the gate signal between engineer and reviewer.

## Producing it

`software-engineer` writes this file as the last step of Phase 5.1 (Commit) and updates it again before opening the PR. The reviewer reads it as part of the outer-loop hard handoff (see `code-reviewer` Step 1, hard handoff contract).

If the project has its own internal definition-of-done, prefer it; this schema is a portable fallback. Either way, the artifact must exist before the reviewer can declare `PASS`.
