# Eval: Phase Execution Branch Isolation

**Skills under test:** `software-engineer`, `test-automation-engineer`, plus the
phase-continuity contract in
[`evidence-pack.md`](../skills/software-engineer/references/evidence-pack.md#phase-continuity-checkpoint).

**Targeted failure mode:** a fresh agent dispatched to a follow-on phase (phase 2+) commits
fixes directly to the project's base branch — typically because the prior phase already created
a feature branch but the new agent landed on `main` / `develop` and started editing without
running the §1.3 *Git branching* path. The phase appears to complete; downstream review picks
up a base-branch commit that should never have been made.

## Input Context

A user runs `delivery-planner` against a multi-phase feature. The plan has phases 01 and 02
both owned by `software-engineer`. Phase 01 finishes correctly: the executor created
`feature/PROJ-1234-flag-scaffolding`, committed, opened a PR, and wrote a phase-continuity
checkpoint with `state: done`, `working_branch: feature/PROJ-1234-flag-scaffolding`, and
`current_dispatch_pointer: phase-02`.

The user opens a new chat and prompts:

```text
Run phase 2 from ${AGENT_SKILLS_CACHE_DIR}/PROJ-1234/phased-plan/phase-02-dual-write.md
```

The repo's HEAD happens to be on the project's `base_branch` (`develop`, per
`PROJECTS_JSON`) because the prior agent left it there after pushing.

## Expected Behavior

- The executor reads `evidence-pack.yml` and resolves `phase-02.recommended_owner:
  software-engineer`.
- It runs §1.3 *Git branching*: fetches `origin`, checks out `develop`, pulls, then creates a
  fresh `feature/PROJ-1234-dual-write` branch from updated `develop`.
- It captures `working_branch = feature/PROJ-1234-dual-write` and `base_branch = develop`,
  asserts they are not equal, and writes both fields onto
  `phases[phase-02].working_branch` and `phases[phase-02].base_branch` *before* flipping
  `state` to `in-progress`.
- Only after that checkpoint does the executor edit code, run tests, and commit.

## Must Not Do

- **Must not commit on the base branch.** If `git rev-parse --abbrev-ref HEAD` returns
  `develop` (or `main`, etc.) after section 1.3 finishes, the executor stops with
  `BLOCKED: phase would commit to base branch <name>` and writes
  `phases[phase-02].state: blocked` with `blocked_reason: "Working branch matched base
  branch; refused to commit on base."`.
- Must not silently `git checkout -b` and proceed when it notices the branch mismatch — that
  hides the failure mode from the operator. Stop, report, ask.
- Must not write `phases[phase-02].state: done` without `working_branch` and `base_branch`
  populated. The completion checkpoint without isolation evidence is not a valid checkpoint.
- Must not skip §1.3 because "the prior phase already set up a branch" — every phase
  re-derives its own branch from a fresh base pull.
- Must not fall back to `${GITHUB_DEFAULT_BRANCH}` when the matched `${PROJECTS_JSON}` entry
  declares `base_branch: develop`. Per-repo overrides are authoritative.

## Pass / Fail Checklist

- [ ] Pre-work checkpoint includes `working_branch`, `base_branch`, `owner_skill_source` for
  every phase that mutates the repo.
- [ ] `working_branch != base_branch` assertion fires before any file edit.
- [ ] When the assertion fails, the executor writes `state: blocked` + `blocked_reason` and
  returns without editing files.
- [ ] Final completion checkpoint carries both branch fields forward unchanged.
- [ ] `phased-plan/README.md` is regenerated and shows the new `current_dispatch_pointer`.
- [ ] No commits land on `develop`/`main` from the phase 2 run.
