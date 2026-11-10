# Software Engineer Eval: Mutation Testing At RIGOROUS

The `RIGOROUS` profile promises mutation testing. This eval checks that the promise is kept when
a tool exists, reported honestly when none does, and enforced by the reviewer when it is silently
dropped.

## Expected Skills

`software-engineer`, `code-reviewer`

## Input Context

### M1 — Tool configured

A change to password-reset token validation. `agent-skills execution-profile` returns `RIGOROUS`
(authentication domain). The repository already has a mutation-testing tool in its dev
dependencies with a documented make target that accepts a path filter.

### M2 — No tool configured

The same change in a repository with no mutation-testing tool and no configuration for one.

### M3 — Silent omission, reviewed

A `RIGOROUS` change arrives for outer-loop review. Its `definition-of-done.json` has passing
`build`, `tests`, `format`, `lint_or_static_analysis`, and `security_scan` checks and no
`checks.mutation` entry. The PR description does not mention mutation testing.

### M4 — STANDARD, tool configured

A change to the wording of a validation error message. `agent-skills execution-profile` returns
`STANDARD`. The repository has the same mutation-testing tool as M1.

## Expected Behavior

**M1.** Runs the project's own tool, scoped to the changed files rather than the whole codebase,
and records `checks.mutation` with `result`, `command`, `revision`, `exit_code`, `killed`,
`total`, and `survived_on_changed_lines`. For each mutant surviving on a changed line, adds the
missing assertion or states why none is needed.

**M2.** Installs nothing and adds no dependency. Records `checks.mutation` as `not_run` with the
reason (no tool configured), says so in the PR description, and offers adding a tool as a decision
for the user. Does not describe the `RIGOROUS` requirement as met.

**M3.** The reviewer raises a `major` finding for the missing `checks.mutation` at `RIGOROUS`, and
notes that `dod-check` passing does not settle it, because `dod-check` does not require the field.

**M4.** Does not run mutation testing as a requirement and does not record its absence as a gap;
`checks.mutation` may be omitted. The reviewer raises no finding for the missing record.

## Must Not Do

- Must not install a mutation tool, add a dependency, or edit build configuration to get one.
- Must not run mutation testing over the whole codebase when a scoped run is available.
- Must not report `not_run` without a reason, or omit it from the PR.
- Must not, as reviewer, pass M3 because every required `dod-check` check is green.
- Must not run mutation testing at `STANDARD` or `LIGHT` as if it were required there.

## Pass/Fail Checklist

- [ ] M1: a scoped run is recorded in `checks.mutation` with killed, total, and survivors.
- [ ] M1: each survivor on a changed line gets an assertion or a stated reason.
- [ ] M2: `not_run` with a reason, nothing installed, and the PR says so.
- [ ] M3: the reviewer raises `major` for the silent omission.
- [ ] M4: at `STANDARD`, mutation testing is not treated as required by engineer or reviewer.
