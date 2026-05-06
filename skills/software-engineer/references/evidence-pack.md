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

# Existing related work discovered before creating a competing branch/PR
related_work:
  already_addressed_status: none # none | possible | likely | confirmed
  open_prs:
    - url: "https://github.com/example-org/example-api/pull/987"
      title: "PROJ-1234 redirect expired SAML sessions"
      status: open
      overlap: "touches AuthFilter and references the same Jira key"
      decision: review_existing_pr # review_existing_pr | continue_existing_branch | create_new_branch | ask_user
  matching_branches:
    - "origin/bugfix/PROJ-1234-saml-expiry-redirect"
  checked_at: 2026-05-06T13:00:00Z

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

# Phased delivery tracking. The planner writes the plan shape. The executing
# skill writes phase-state and continuity checkpoints. See the delivery_plan
# ownership rule and phase-continuity checkpoint below.
delivery_plan:
  destination_path: ".cache/agent-skills/PROJ-1234/destination.md"
  index_path: ".cache/agent-skills/PROJ-1234/phased-plan/README.md"
  current_dispatch_pointer: phase-03 # next phase id, or null when no phase is dispatchable
  last_completed_phase_id: phase-02
  last_completed_at: 2026-05-06T14:00:00Z
  last_completed_by: software-engineer # which skill marked the most recent phase done/blocked
  last_continuity_checkpoint_at: 2026-05-06T14:02:00Z
  phases:
    - id: phase-01
      slug: confirm-jwt-issuer
      recommended_owner: issue-investigator
      state: done # provisional | ready | in-progress | done | skipped | blocked
      completed_at: 2026-05-06T10:00:00Z
      completed_by: issue-investigator
      completion_summary: "Confirmed issuer metadata source and eliminated stale config hypothesis."
      artifacts:
        - ".cache/agent-skills/PROJ-1234/repro/issuer-check.log"
      validation:
        - "Read-only issuer query matched production metadata."
      follow_up_context:
        - "Phase 02 can use issuer `https://idp.example.com/oauth2/default`."
    - id: phase-02
      slug: feature-flag-scaffolding
      recommended_owner: software-engineer
      state: done
      completed_at: 2026-05-06T14:00:00Z
      completed_by: software-engineer
      working_branch: feature/PROJ-1234-sso-feature-flag
      base_branch: develop
      owner_skill_source: ".skills/software-engineer/SKILL.md"
      completion_summary: "Added disabled-by-default SSO dual-write flag and config tests."
      artifacts:
        - "src/auth/SsoFlags.java"
        - "src/auth/SsoFlagsTest.java"
      validation:
        - "mvn -pl auth test -Dtest=SsoFlagsTest passed."
      follow_up_context:
        - "Next phase may assume `sso.dualWrite.enabled=false` is present in all profiles."
    - id: phase-03
      slug: dual-write-path
      recommended_owner: software-engineer
      state: ready
```

**Loading rule**: every skill `set -a && source ${WORKSPACE_ROOT}/.env && set +a`, then reads/writes
`${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills}/${issue_key}/evidence-pack.yml`.
Skills append to lists; they do not delete prior entries.

**Planner creation rule**: `delivery-planner` MUST create `evidence-pack.yml` when it writes
`destination.md` and `phased-plan/`, even when no prior evidence pack exists. A greenfield plan
without an evidence pack is invalid because a fresh executor has no durable state to update. The
minimal file contains `issue_key`, `issue_url` or source brief, `issue_type`, `title`, `summary`,
`project` when known, and `delivery_plan` with every phase id, slug, owner, initial state,
prerequisites, `destination_path`, `index_path`, and `current_dispatch_pointer`.

**Skill-dispatch blocker rule**: when `delivery_plan.current_dispatch_pointer` is set, the
executor must read that phase and load the `SKILL.md` for
`delivery_plan.phases[<phase id>].recommended_owner` from the canonical skill source before doing
work. Resolve the source with [`docs/skill-source-resolution.md`](../../../docs/skill-source-resolution.md),
including any explicit skill path the user supplied in the current prompt. If the owner skill cannot
be loaded, or the loaded skill's `name` does not equal `recommended_owner`, stop with
`BLOCKED: recommended owner skill unavailable` and list the paths checked. Do not substitute a
generic agent workflow, do not keep using the wrong skill, and do not mark the phase complete.

An agent output such as "I did not find `.skills/software-engineer`" is insufficient when the user
or config supplied a different skill source. Missing the recommended owner is a blocker, not a
warning.

**Missing evidence-pack recovery rule**: if an executor is invoked with `destination.md` and a
`phase-NN.md` but `evidence-pack.yml` is missing, it MUST NOT silently continue. It may reconstruct
the minimal `delivery_plan` block from `phased-plan/README.md` and the per-phase files, then continue
only after re-reading the file it wrote. If reconstruction is not possible, stop with
`BLOCKED: phase continuity evidence-pack missing` and list the expected path. Do not mark the phase
done in chat only.

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

| Skill                      | Reads                              | Writes                                                                       |
| -------------------------- | ---------------------------------- | ---------------------------------------------------------------------------- |
| `issue-investigator` †     | env, prior `evidence-pack.yml`     | `evidence-pack.yml` (investigation, risk, hypotheses, related_work, phase checkpoint); `repro-recipe.yml` |
| `software-engineer` †      | both files                         | `evidence-pack.yml.plan`, `related_work`, phase checkpoint; regression test commit referenced from recipe |
| `code-reviewer`            | both files                         | `evidence-pack.yml.review` (sole owner — see ownership rule below)           |
| `manual-tester` †          | `evidence-pack.yml`                | `repro-recipe.yml` (when manual repro produces one); defect rows; phase checkpoint |
| `test-automation-engineer` † | `repro-recipe.yml`              | regression test files; references the recipe in test docstring; phase checkpoint |
| `product-owner` †          | `evidence-pack.yml.investigation`  | `evidence-pack.yml.acceptance_criteria`; phase checkpoint                    |
| `delivery-planner`         | env, prior `delivery_plan` block   | `evidence-pack.yml` creation, `delivery_plan` structure; plan files on disk  |

† **also writes the phase-continuity checkpoint** (`phases[<id>].state`,
completion or blocked timestamp, owner, summary/reason, artifacts,
validation, follow-up context, the top-level `last_completed_*` /
`last_blocked_*` mirrors, `last_continuity_checkpoint_at`, and the derived
`current_dispatch_pointer`) into `evidence-pack.yml.delivery_plan` when
invoked from a `delivery-planner` phase, per the
[`delivery_plan` ownership rule](#evidence-packymldelivery_plan-ownership-rule)
below. `code-reviewer` does not own a phase (it is invoked by
`software-engineer` from inside a phase) and `delivery-planner` writes
the structural fields, not phase-state.

If a consumer skill cannot find the file it needs, it stops with the standard _Missing required
setup_ message instead of inferring context silently, except for the explicit missing
evidence-pack recovery rule above when planner phase files are present and can reconstruct the
minimal `delivery_plan`.

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

### Phase-continuity checkpoint

Any skill invoked from a `delivery-planner` phase must write a checkpoint before returning, then
re-read `evidence-pack.yml` and confirm the write is present. This is mandatory even when the user
only asked for "phase 1" and even when the implementation itself finished successfully. If the write
fails, the phase result is `blocked` because the next agent cannot continue safely.

#### Pre-work isolation gate (binding)

Before writing `phases[<id>].state: in-progress` and before any code edit, branch creation, commit,
push, or PR-affecting action, the executor MUST record and self-check the following on
`phases[<this phase id>]`:

1. `working_branch` ← the actual git branch the executor will commit on. Capture with
   `git -C <repo-root> rev-parse --abbrev-ref HEAD` after `1.3 Git branching` (for
   `software-engineer`) or the equivalent step in other executors.
2. `base_branch` ← the project's `base_branch` from `${PROJECTS_JSON}` (or
   `${GITHUB_DEFAULT_BRANCH}` fallback) for the repo this phase touches.
3. **Branch-isolation assertion.** For any phase that mutates the repo (commits, pushes, or opens
   a PR — i.e. `software-engineer` and any other repo-mutating owner), `working_branch` MUST NOT
   equal `base_branch`. If they are equal, the executor stops with
   `BLOCKED: phase would commit to base branch <name>` and writes `phases[<id>].state: blocked`
   with `blocked_reason: "Working branch matched base branch; refused to commit on base."` Do
   not edit files, do not stash, do not silently `git checkout -b` and proceed; ask the user to
   confirm the intended branch first. Read-only owners (`issue-investigator`,
   `manual-tester` against deployed environments, `product-owner` discovery) skip this assertion
   and instead record `working_branch: not-applicable — read-only`.
4. **Owner-skill verification.** The executor MUST verify that the resolved canonical skill
   source contains a `SKILL.md` for `phases[<id>].recommended_owner`. The verification is a file
   read, not a host listing — see
   [skill-source-resolution.md](../../../docs/skill-source-resolution.md#owner-skill-verification-recipe).
   Record the verified path on `phases[<id>].owner_skill_source`. A host listing that omits the
   skill (some IDEs only expose a curated subset) is **not** evidence the skill is missing.

These three writes happen in the same evidence-pack update that flips the phase to `in-progress`.
Without them the executor has not entered the phase.

#### Checkpoint write

The checkpoint write contains:

1. `phases[<this phase id>].state` ← `in-progress` before material work starts, then `done` or
   `blocked` before the final response.
2. `phases[<this phase id>].completed_at` or `blocked_at` ← current ISO-8601 timestamp.
3. `phases[<this phase id>].completed_by` or `blocked_by` ← this skill's own `name`.
4. `phases[<this phase id>].completion_summary` or `blocked_reason` ← one to three sentences
   written for the next fresh agent, not for chat transcript readers.
5. `phases[<this phase id>].artifacts` ← files, PRs, commits, cache files, test reports, or
   investigation outputs produced by the phase.
6. `phases[<this phase id>].validation` ← commands/checks run and their result, or explicit
   skipped/blocked reasons.
7. `phases[<this phase id>].follow_up_context` ← assumptions resolved, decisions made, and details
   the next phase may rely on.
8. `phases[<this phase id>].working_branch`, `base_branch`, and `owner_skill_source` ← carried
   forward from the pre-work isolation gate above. These fields are required on every checkpoint
   so the next agent can audit branch hygiene and skill resolution without rerunning git.
9. Top-level `last_completed_*` or `last_blocked_*` mirrors and
   `last_continuity_checkpoint_at`.
10. `current_dispatch_pointer` recomputed to the first `ready` phase whose prerequisites are now
    `done`; `null` only when no phase is dispatchable or the plan is blocked.

#### Index regeneration (binding)

After the checkpoint write to `evidence-pack.yml`, the executor MUST also regenerate
`phased-plan/README.md` from the updated evidence pack. This is mechanical, not planning: read
`delivery_plan.phases[]`, recompute `totals`, refresh the phase table's `State` column, refresh
the YAML header's `last_completed_*` mirrors and `current_dispatch_pointer`, bump the header's
`updated_at:`. Follow the binding shape in
[plan-index template](../../delivery-planner/references/plan-index-template.md). If the index
write fails, the phase result is `blocked` for the same reason as a failed evidence-pack write —
the next agent reading only the README would otherwise see a stale dispatch pointer.

The executor MUST NOT add, delete, reorder, rename, or resize phases while regenerating the
index. Those are planner-owned operations. If the index already contains a phase the evidence
pack does not, or vice versa, stop with `BLOCKED: phase index out of sync with evidence pack`
and surface the diff — do not silently reconcile.

The final user-facing response for a phase must name the evidence-pack path, the regenerated
phased-plan/README path, the phase id updated, the resulting phase state, and the new
`current_dispatch_pointer`. A transcript-only summary is not a checkpoint.

**`evidence-pack.yml.delivery_plan` ownership rule.** Two writers, with a strict split:

- `delivery-planner` is the sole writer of the **plan-shape** fields: `destination_path`,
  `index_path`, the entire `phases[]` list (each entry's `id`, `slug`, `recommended_owner`,
  prerequisites, and initial `state` of `provisional` / `ready`). It creates
  `current_dispatch_pointer` and MAY recompute it on each planner run by reading
  `phases[*].state`.
- The skill named in a phase's `recommended_owner` is the **only** writer of that phase's
  completion state. When invoked from a phase, before returning its final result, that skill
  performs the [phase-continuity checkpoint](#phase-continuity-checkpoint), which includes
  regenerating `phased-plan/README.md` from the updated evidence pack. It MAY update
  `current_dispatch_pointer` only by the deterministic rule above; it MUST NOT add, delete,
  reorder, rename, or resize phases. Index regeneration is mechanical (re-derive the table,
  totals, header mirrors, and pointer from `delivery_plan`); inserting or removing rows is a
  planner-only operation.

This split keeps continuity fresh after real phase execution: the planner owns the plan shape, the
executors own their own outcomes and the derived next pointer, and no skill writes another's fields.
A skill invoked outside any phase (i.e. the user invoked it directly without a planner
artifact) MUST NOT touch `delivery_plan` at all — the absence of the block is meaningful
context for the planner on its next run.
