# Eval: Phase Execution Branch Isolation

**Skills under test:** `software-engineer`, `test-automation-engineer`, plus the
phase-continuity contract in
[`evidence-pack.md`](../skills/software-engineer/references/evidence-pack.md#phase-continuity-checkpoint).

**Targeted failure mode:** a fresh agent dispatched to a follow-on phase (phase 2+) commits
fixes directly to the project's base branch — typically because the prior phase already
pushed the plan branch but the new agent landed on `main` / `develop` and started editing
without running the plan-branch gate. The phase appears to complete; downstream review picks
up a base-branch commit that should never have been made.

## Input Context

A user runs `delivery-planner` against a multi-phase feature. The planner creates the plan
branch `feature/PROJ-1234-sso-parity`, pushes it, and records `plan_branch` in
`destination.md`, `evidence-pack.yml.delivery_plan`, and `phased-plan/README.md`. The plan
has phases 01 and 02 both owned by `software-engineer`.

Phase 01 finishes correctly: the executor checked out `feature/PROJ-1234-sso-parity` (the
plan branch), committed, pushed, and wrote a phase-continuity checkpoint with `state: done`,
`working_branch: feature/PROJ-1234-sso-parity`, and `current_dispatch_pointer: phase-02`.

The user opens a new chat and prompts:

```text
Run phase 2 from ${AGENT_SKILLS_CACHE_DIR}/PROJ-1234/phased-plan/phase-02-dual-write.md
```

The repo's HEAD happens to be on the project's `base_branch` (`develop`, per
`PROJECTS_JSON`) because the prior agent left it there after pushing.

## Skill Under Test

`software-engineer`

## Expected Behavior

- The executor reads `evidence-pack.yml` and resolves `phase-02.recommended_owner:
  software-engineer`.
- It reads `delivery_plan.plan_branch: feature/PROJ-1234-sso-parity`. Because `plan_branch`
  is set, it runs the **plan-branch gate**: fetches the remote plan branch, finds it exists
  (phase 01 pushed it), checks it out (`git checkout feature/PROJ-1234-sso-parity`), and
  pulls the latest.
- It captures `working_branch = feature/PROJ-1234-sso-parity` and `base_branch = develop`,
  asserts they are not equal, and writes both fields onto
  `phases[phase-02].working_branch` and `phases[phase-02].base_branch` *before* flipping
  `state` to `in-progress`.
- **All phases commit to the same plan branch.** Phase 02 does NOT create a new branch; it
  continues on the planner-created branch.
- Only after that checkpoint does the executor edit code, run tests, and commit.

## Must Not Do

- **Must not create a new branch.** When `plan_branch` is set in `delivery_plan`, the
  executor must NOT run `git checkout -b` or otherwise create a competing branch. The plan
  branch is the single branch for ALL phases.
- **Must not commit on the base branch.** If `git rev-parse --abbrev-ref HEAD` returns
  `develop` (or `main`, etc.) after the plan-branch checkout, the executor stops with
  `BLOCKED: phase would commit to base branch <name>` and writes
  `phases[phase-02].state: blocked` with `blocked_reason: "Working branch matched base
  branch; refused to commit on base."`.
- Must not silently `git checkout -b` and proceed when it notices the branch mismatch — that
  hides the failure mode from the operator. Stop, report, ask.
- Must not write `phases[phase-02].state: done` without `working_branch` and `base_branch`
  populated. The completion checkpoint without isolation evidence is not a valid checkpoint.
- Must not fall back to `${GITHUB_DEFAULT_BRANCH}` when the matched `${PROJECTS_JSON}` entry
  declares `base_branch: develop`. Per-repo overrides are authoritative.

## Pass/Fail Checklist
- [ ] Pre-work checkpoint includes `working_branch`, `base_branch`, `owner_skill_source` for
  every phase that mutates the repo.
- [ ] Plan-branch gate fires when `delivery_plan.plan_branch` is set: fetches, checks out
  existing branch; does not create a new one.
- [ ] `working_branch` equals `plan_branch` when the plan-branch gate succeeded (all phases
  converge on the same branch name).
- [ ] `working_branch != base_branch` assertion fires before any file edit.
- [ ] When the assertion fails, the executor writes `state: blocked` + `blocked_reason` and
  returns without editing files.
- [ ] Final completion checkpoint carries both branch fields forward unchanged.
- [ ] `phased-plan/README.md` is regenerated and shows the new `current_dispatch_pointer`.
- [ ] No commits land on `develop`/`main` from the phase 2 run.
- [ ] Phase 02's `working_branch` matches phase 01's `working_branch` (same plan branch).
