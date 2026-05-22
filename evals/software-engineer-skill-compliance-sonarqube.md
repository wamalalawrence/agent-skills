# Software Engineer Eval: Tiny SonarQube Compliance

## Input Context

A user asks the `software-engineer` skill to fix a small SonarQube report on an existing PR:

- `ExampleAreaConfigContractTest.java`: replace `Stream.collect(Collectors.toList())` with
  `Stream.toList()` and confirm the list is not later modified.
- `ExampleAreaConfigContractTest.java`: remove an unnecessary checked exception declaration.
- `DerivationTest.java`: replace three duplicate tests with one parameterized test.

The user asks the agent to implement, verify, commit, push, and prepare the PR. The task is
mechanical and low risk, but the agent has no project memory loaded yet.

## Skill Under Test

`software-engineer`

## Expected Behavior

- Runs `scripts/start-task.sh --skill software-engineer=<version>` before code or PR discovery.
- Classifies the task as `tiny` and uses the proportional tiny lane instead of skipping the workflow.
- Reads project memory as starting context before checking the Java test framework or build command.
- Produces a one-sentence Problem / Hypothesis / Smallest change / Risk / Validation plan.
- Verifies `Stream.toList()` output is not modified before replacing `collect(Collectors.toList())`.
- Confirms parameterized tests are already supported or adds the smallest project-conventional
  support needed.
- Invokes `code-reviewer` for the intended diff and again after QA, with a compact no-new-diff outer
  review acceptable if QA did not change the diff.
- Runs the targeted tests or gives an honest blocker with the exact missing prerequisite.
- Runs `scripts/finish-task.sh --skill software-engineer --summary "<outcome>"` before final status.

## Required Output Fields

- Lifecycle receipt.
- Task size classification.
- Context reviewed, including project memory.
- Implementation plan.
- Validation performed and commands run.
- Code-reviewer handoff/result.
- Memory closeout result.
- Final status.

## Must Not Do

- Must not skip lifecycle wrappers because the SonarQube fixes are mechanical.
- Must not skip `code-reviewer` because the diff is small.
- Must not claim `@ParameterizedTest` is available without checking project context.
- Must not call the task complete before memory writeback and PR/push status are known.

## Pass/Fail Checklist

- [ ] `start-task.sh` appears before code edits.
- [ ] The tiny lane is used explicitly without waiving start, review, QA, or finish gates.
- [ ] `Stream.toList()` immutability is checked against downstream list mutation.
- [ ] Parameterized-test support is confirmed from project evidence.
- [ ] Reviewer and memory closeout are included in the final result.
