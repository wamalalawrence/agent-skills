# software-engineer

Senior-level pair-programming workflow for production software changes. This is the flagship skill
and the base workflow that implementation, review, and issue resolution go through.

See [SKILL.md](./SKILL.md) for the full workflow. References live under
[`./references/`](./references/).

## What it does

- Phase 1 — Preparation (issue context, repo identification, branch setup, compact evidence pack,
  plan)
- Phase 2 — Implementation (clean code, security, architecture rules) -> calls `code-reviewer`
  (inner loop)
- Phase 3 — Quality assurance (tests, static analysis, format, build) -> calls `code-reviewer`
  (outer loop)
- Phase 4 — Self-review
- Phase 5 — Commit & PR

The nested `code-reviewer` and `issue-investigator` skills intentionally stay inside this role for
now. They represent closely related parts of one collaborative engineering workflow rather than
separate top-level roles.

This skill also collaborates with the other top-level delivery skills:

- [`product-owner`](../product-owner/) for unclear product intent, scope, acceptance criteria,
  stakeholder value, and UX expectations.
- [`manual-tester`](../manual-tester/) for manual validation plans, exploratory coverage, defect
  evidence, and retest guidance.
- [`test-automation-engineer`](../test-automation-engineer/) for stable regression automation,
  test-level choice, fixtures, selectors, CI reporting, and flakiness prevention.

## Required environment

Run [`../../setup.init`](../../setup.init) from the `agent-skills` folder for the simplest setup
path. See the table in [SKILL.md § Required Environment](./SKILL.md#required-environment) for
details. Minimum for local planning and repo-aware work: `WORKSPACE_ROOT`, `ORG_NAME`,
`GITHUB_DEFAULT_BRANCH`, and `PROJECTS_JSON`. `GITHUB_ORG` is only required when cloning, pushing,
opening PRs, or looking up sibling repositories on GitHub.
