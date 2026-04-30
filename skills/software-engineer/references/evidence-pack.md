# Evidence Pack & Repro Recipe

Shared cross-skill artifacts that let `issue-investigator`, `software-engineer`, `code-reviewer`,
`manual-tester`, and `test-automation-engineer` hand off context without re-deriving it on every
hop.

Both files are **YAML, human-editable, and small** (target < 100 lines). Cache them at:

```
${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills}/<issue-key>/
├── evidence-pack.yml
├── repro-recipe.yml
└── definition-of-done.json
```

`<issue-key>` is the Jira key, GitHub issue number, or a short slug derived from the user's brief
when no ticket exists (e.g., `local-2026-04-flaky-login`). The `.cache/` directory is already
covered by the workspace `.gitignore` block managed by `setup.init`, so nothing here ever leaks to a
repo.

Every skill that consumes one of these files MUST validate its presence and surface a finding when
it is missing or stale (older than the issue's last update).

---

## 1. `evidence-pack.yml`

Created by `issue-investigator` (or by `software-engineer` for non-ticket work). Updated in place by
every skill that touches the issue. Fields:

```yaml
# Required
issue_key: PROJ-1234 # ticket key, GitHub issue, or local slug
issue_url: https://... # canonical link, or the user's brief verbatim
issue_type: bug | regression | incident | feature | refactor | spike | task
title: "Login fails when SAML cookie expires mid-session"
summary: "One-paragraph plain-language restatement of the problem."

# Project context
project:
  name: example-api # matches a PROJECTS_JSON entry
  repo: https://github.com/<org>/<repo>
  base_branch: main
  stack: java-spring-boot
  build_command: "mvn clean verify"

# What 'done' looks like
expected_behavior: |
  Multi-line description of the behavior the system MUST exhibit.
actual_behavior: |
  Multi-line description of what is happening today (omit for greenfield work).
acceptance_criteria:
  - "Given an expired SAML cookie, when the user clicks any nav item, then they are redirected to
    /login with a one-time toast."
  - "MUST NOT silently 500."

# Investigation
investigation:
  root_cause_status: unknown | suspected | confirmed | disproved
  root_cause: "Filter chain swallows the AuthenticationException and returns 500."
  supporting_evidence:
    - "stacktrace at <log link or excerpt>"
    - "introducing commit abc1234 (PR #987)"
  hypotheses_considered:
    - "Filter order regression (eliminated by bisect)"
    - "Token clock skew (eliminated by clock-sync check)"
    - "Filter swallows exception (current best fit)"
  confidence: high | medium | low
  what_would_change_my_mind: "Reproduction with a fresh SAML cookie still 500s."

# Risk areas the engineer wants extra reviewer attention on
risk_areas:
  - "AuthenticationFilter ordering"
  - "Existing /login redirect tests"

# Engineer's 5-line plan (filled in by software-engineer in Phase 1.4)
plan:
  problem: "Expired SAML cookie causes 500 instead of redirect."
  hypothesis: "Filter chain swallows AuthenticationException."
  smallest_change: "Re-throw in AuthFilter; add redirect handler."
  risk: "Could cascade to other auth flows; covered by existing redirect tests."
  validation: "Failing test from repro-recipe + full mvn verify."

# Reviewer iteration tracking (managed by code-reviewer)
review:
  round: 0 # increments each invocation
  open_blocker_count: 0
  open_major_count: 0
  verdict: null # current round's verdict: PASS | PASS_WITH_NOTES | REQUEST_CHANGES | NEEDS_CONTEXT | NOT_REVIEWABLE
  history:
    - round: 1
      blocker_count: 2
      major_count: 4
      verdict: REQUEST_CHANGES
```

**Loading rule**: every skill `set -a && source ${WORKSPACE_ROOT}/.env && set +a`, then reads/writes
`${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills}/${issue_key}/evidence-pack.yml`.
Skills append to lists; they do not delete prior entries.

---

## 2. `repro-recipe.yml`

Produced by `issue-investigator` (and mirrored by `manual-tester`) whenever a bug or regression is
reproduced. Consumed by `software-engineer` to write the failing regression test (Phase 1.5) and by
`test-automation-engineer` to seed permanent regression coverage.

```yaml
# Required
issue_key: PROJ-1234
status: reproduced | partially_reproduced | not_reproduced | not_attempted | not_applicable
environment: local | ephemeral_branch | replayed_input | read_only_inspection
build_sha: abc1234def # exact commit the recipe was captured against
captured_at: 2026-04-26T14:03:00Z

# Setup the next agent or human needs to replay the issue
prerequisites:
  - "docker compose up -d postgres"
  - "export FEATURE_FLAG_SAML=true"
  - "seed: scripts/seed-expired-saml.sh"

# The exact deterministic recipe
steps:
  - "curl -s -b 'SAML=expired-fixture' http://localhost:8080/api/me -o /tmp/out -w '%{http_code}'"

# What success of the repro looks like (i.e., the bug is visible)
expected_observation:
  http_status: 500
  log_marker: "AuthenticationException swallowed in AuthFilter"
  artifact_path: ".cache/agent-skills/PROJ-1234/repro/run-001.log"

# Anti-checks: what MUST NOT happen if the fix works
post_fix_observation:
  http_status: 302
  redirect_location_starts_with: /login
  log_marker: "AuthFilter redirected to /login"
```

**Safety rule**: `environment: replayed_input` and `read_only_inspection` are the defaults when a
defect originates in production. Mutating production data, configuration, or environments to
reproduce is forbidden without explicit user approval and a written rollback plan inside the recipe.

---

## 3. Skill responsibilities

| Skill                      | Reads                             | Writes                                                                              |
| -------------------------- | --------------------------------- | ----------------------------------------------------------------------------------- |
| `issue-investigator`       | env, prior `evidence-pack.yml`    | `evidence-pack.yml` (investigation, risk, hypotheses), `repro-recipe.yml`           |
| `software-engineer`        | both files                        | `evidence-pack.yml.plan`, regression test commit referenced from `repro-recipe.yml` |
| `code-reviewer`            | both files                        | `evidence-pack.yml.review` (sole owner — see ownership rule below)                  |
| `manual-tester`            | `evidence-pack.yml`               | `repro-recipe.yml` (when manual repro produces one), defect rows                    |
| `test-automation-engineer` | `repro-recipe.yml`                | regression test files; references the recipe in test docstring                      |
| `product-owner`            | `evidence-pack.yml.investigation` | `evidence-pack.yml.acceptance_criteria`                                             |

If a consumer skill cannot find the file it needs, it stops with the standard _Missing required
setup_ message instead of inferring context silently.

**`evidence-pack.yml.review` ownership rule.** `code-reviewer` is the sole writer of the `review`
block. `software-engineer` does not mutate it — it only re-stages the fix and re-invokes the
reviewer. On each invocation, before emitting the verdict, the reviewer:

1. Snapshots the previous round into `review.history` as `{round, blocker_count, major_count,
   verdict}`, mapping the top-level `open_blocker_count` → `blocker_count` and
   `open_major_count` → `major_count`.
2. Increments `review.round` by 1 (or initialises it to `1` if absent).
3. Writes the new `open_blocker_count`, `open_major_count`, and `verdict` for this round.

This single-owner rule prevents double-increments, stale counts, and wrong `max-rounds` / round-1
decisions.
