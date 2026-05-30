# Eval: Single Plan Branch (Planner Creates Branch)

**Skills under test:** `delivery-planner`, `delivery-runner`, `software-engineer`, plus the
plan-branch contract in
[`evidence-pack.md`](../skills/software-engineer/references/evidence-pack.md#phase-continuity-checkpoint).

**Targeted failure mode:** a multi-phase plan produces N separate feature branches because
each phase executor (fresh agent) creates its own branch in §1.3 *Git branching*. The plan
fragments across branches; no single branch carries the complete delivery.

## Input Context

A user asks `delivery-planner` to plan a three-phase feature for `PROJ-5678`. The repo is
`example-api` with `base_branch: develop` and `${GIT_BRANCH_NAME_FORMAT}` producing
`feature/<KEY>-<slug>`. The planner:

1. Writes `destination.md`, `phased-plan/README.md`, three phase files, and
   `evidence-pack.yml`.
2. Creates `feature/PROJ-5678-auth-flow` from `develop` and pushes it.
3. Records `plan_branch: feature/PROJ-5678-auth-flow` in ALL artifacts.

The user then invokes `delivery-runner` to dispatch the three phases. Phase 01
(`software-engineer`) and phase 02 (`software-engineer`) both mutate the repo;
phase 03 (`test-automation-engineer`) adds tests.

## Expected Behavior

### Planner

- [ ] `destination.md` YAML header contains `plan_branch: feature/PROJ-5678-auth-flow`.
- [ ] `evidence-pack.yml.delivery_plan.plan_branch` equals `feature/PROJ-5678-auth-flow`.
- [ ] `phased-plan/README.md` YAML header contains `plan_branch` and the "Inputs for the next
  agent" section lists it with checkout instructions.
- [ ] When git access is unavailable, `plan_branch` is still set to the derived name and the
  plan output notes that the first executor must create it.

### Phase 01 (first repo-mutating phase)

- [ ] Reads `delivery_plan.plan_branch`. Fetches remote, finds the branch (planner pushed it),
  checks it out, pulls.
- [ ] Does NOT run `git checkout -b` or create any new branch.
- [ ] Records `working_branch: feature/PROJ-5678-auth-flow` in the pre-work isolation gate.
- [ ] Commits, pushes to the same plan branch.
- [ ] Phase-continuity checkpoint carries `working_branch` forward.

### Phase 02 (follow-on repo-mutating phase)

- [ ] Reads `delivery_plan.plan_branch`. Fetches remote, finds the branch (phase 01 pushed
  to it), checks it out, pulls.
- [ ] Does NOT run `git checkout -b` or create any new branch.
- [ ] `working_branch` equals the same `plan_branch`, NOT a different branch name.
- [ ] `working_branch` in phase 02's checkpoint matches phase 01's `working_branch`.
- [ ] Commits add to the same branch history; no parallel unrelated branches exist.

### Phase 03 (non-mutating or read-only phase)

- [ ] `test-automation-engineer` checks out the plan branch, runs tests, validates.
- [ ] `working_branch` still equals `plan_branch`.

### Runner

- [ ] `delivery-run-next.py` output includes `plan_branch` in every dispatch decision.
- [ ] Each handoff prompt includes the plan branch and explicit checkout instructions.
- [ ] The runner never tells an executor to create a new branch.

## Must Not Do

- **Must not create N branches for N phases.** One plan = one branch, regardless of phase
  count.
- **Must not have phase 02 create `feature/PROJ-5678-auth-flow-phase2`** or any other
  variant. The plan branch name is fixed by the planner.
- Must not skip the plan-branch gate when `plan_branch` is set. "I'm already on a feature
  branch" is not a valid reason to skip fetching and checking out the canonical plan branch.
- Must not push a phase's work to a different branch than `plan_branch`.

## Pass / Fail Checklist

- [ ] Planner creates exactly one branch and records it in all three artifacts.
- [ ] All repo-mutating phases check out (not create) the plan branch.
- [ ] All phases' `working_branch` values are identical (equal to `plan_branch`).
- [ ] No phase's `working_branch` is a branch name not equal to `plan_branch`.
- [ ] `delivery-run-next.py` JSON output includes non-null `plan_branch`.
- [ ] Handoff prompt template includes the `Plan branch (BINDING)` section.
- [ ] Evidence-pack schema includes `delivery_plan.plan_branch`.
- [ ] When planner cannot create the branch (no git access), `plan_branch` is still recorded
  and the first executor's handoff instructs it to create and push.
