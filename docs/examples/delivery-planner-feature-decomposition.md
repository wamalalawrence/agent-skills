# Delivery Planner Feature-Decomposition Example

## Input Prompt

```text
Use the delivery-planner skill to phase this work before any code is written.

Goal: replace the legacy local-auth flow on `example-api` with single-sign-on
(SSO) parity. The new flow must accept the existing JWT issuer, must not break
the current /login route during rollout, and must be feature-flagged so we can
turn it off in production within five minutes.

Constraint: a release freeze starts in three weeks. We have one engineer and
one tester. The work will be picked up across multiple agent sessions; please
size phases so a fresh agent can finish each one in a single session.
```

## Assumed Available Context

- Repository `example-api` exists in `${PROJECTS_JSON}` with `stack:
  java-spring-boot`, `base_branch: main`, and a working CI workflow.
- The existing local-auth flow is documented in `docs/auth.md` and exercised
  by `src/test/java/com/example/auth/LocalAuthFlowIT.java`.
- The JWT issuer's metadata URL and the planned feature-flag key
  (`auth.sso.enabled`) have been agreed by the on-call team.
- No prior `evidence-pack.yml` exists for this work item; this is a green
  initiative, not a bug fix.

## Expected Skill Behavior

- Run the [Requirement Understanding Gate](../requirement-understanding.md)
  before producing the plan. With the inputs above, understanding-confidence
  should reach `medium` because the rollout-cutover sequencing is the
  load-bearing assumption — confidence becomes `high` only after the first
  phase confirms the JWT issuer's metadata.
- Produce a `destination.md` with: outcome (one or two plain-language
  sentences about the user-visible change), success signals (three to five
  observable signals — feature-flag toggles within five minutes, existing
  `/login` route untouched, CI green on both flows, etc.), explicit
  non-goals (no UI redesign, no migration off the existing JWT issuer, no
  password-policy changes), constraints (release freeze date, single
  engineer + tester), load-bearing assumptions with falsifiers, and named
  risks (lockout under flag flip, JWT clock skew, observability gap during
  cutover).
- Decompose the work into a small number of phases (typically four to six)
  each sized for one focused agent session. Each phase names exactly one
  recommended owner skill, has prerequisites, inputs, scope, expected
  outputs, validation, risks, size, parallel-safety, and rollback behavior.
- Mark the discovery phase that confirms the JWT issuer's metadata as the
  dispatch pointer. Mark all later phases `provisional` until that
  discovery raises understanding-confidence to `high`.
- Persist `destination.md` and `phased-plan/phase-NN-<slug>.md` files into
  `${AGENT_SKILLS_CACHE_DIR}/<issue-key>/`.

## Sample Output Structure

```markdown
## Plan Summary

- Issue / work key: AUTH-SSO-PARITY
- Destination file: .cache/agent-skills/AUTH-SSO-PARITY/destination.md
- Phased-plan index: .cache/agent-skills/AUTH-SSO-PARITY/phased-plan/README.md
- Phases total / ready / done / blocked: 5 / 1 / 0 / 0
- Current dispatch pointer: phase-01-confirm-jwt-issuer
- Understanding confidence: medium
- Readiness decision: READY_FOR_DISCOVERY

## Destination Brief

- Outcome: SSO replaces the local-auth flow at /login while preserving the
  existing JWT issuer. Local-auth code path remains intact behind the
  `auth.sso.enabled` flag for fast rollback.
- Success signals: ...
- Scope: ...
- Non-goals: ...
- Constraints: ...
- Load-bearing assumptions: ...
- Stakeholders / decision makers: ...
- Risks the plan protects against: ...

## Phases

- **phase-01 — confirm JWT issuer metadata** (owner: issue-investigator,
  size: S, state: ready) — verify the issuer's metadata URL, signing
  algorithm, and clock-skew tolerance match production assumptions.
  Validation: a recorded read-only fetch of the well-known endpoint with
  the expected fields. Prerequisites: none.
- **phase-02 — feature flag scaffolding** (owner: software-engineer,
  size: S, state: provisional) — add `auth.sso.enabled` flag wired to an
  empty branch. Validation: existing tests pass with flag off. Prerequisites: 01.
- ...

## Dependency Map

- Phase 1 must finish first; it gates phase 2's design choices. Phases 2
  and 3 are sequential. Phase 4 is parallel-safe with phase 5.
```

## What The Skill Should Avoid

- Inventing the rollback window, the freeze date, or the issuer URL.
- Producing a single oversized "implement SSO" phase that hides every
  meaningful decision inside one agent session.
- Writing acceptance criteria — that belongs to `product-owner` once a
  phase that names it as `recommended_owner` is dispatched.
- Calling `software-engineer` or `issue-investigator` from inside the
  planner. The plan dispatches itself; executors invoke their own skills.
- Treating the discovery phase as optional once confidence is `medium` —
  the dispatch pointer must point at discovery and downstream phases must
  stay `provisional` until confidence reaches `high`.
