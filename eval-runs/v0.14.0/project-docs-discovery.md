# Project-Docs Discovery — v0.14.0 Eval Run

- Release: `v0.14.0`
- Category: maintainer-authored (illustrative).
- Scope: SKILL content sharpening across `software-engineer`,
  `issue-investigator`, `manual-tester`, `test-automation-engineer`, and the
  `architecture-patterns.md` reference. No `setup.init`, `.env.example`,
  `.agent-skills.example.yml`, or CI changes.

## Scenario

A user asks the agent to fix a small bug in a multi-module Java repository
that has a parent `pom.xml` and three child modules. The affected child
module has its own `README.md` that documents two extra setup steps required
to run its integration tests:

1. Start a Testcontainers helper service via `make test-deps` from the
   module directory (the parent `mvn verify` does not invoke it).
2. Export `MODULE_X_FIXTURE_DB=1` so the test profile uses the seeded
   schema instead of an empty one.

Neither requirement is mentioned in the parent `README.md` or the parent
`pom.xml`. The repository is registered correctly in `${PROJECTS_JSON}` with
`build = "mvn verify"`.

## Pre-v0.14.0 behaviour (the failure mode being fixed)

- The agent followed `software-engineer` Phase 1.2 by matching the cwd
  against `${PROJECTS_JSON}`, took `build = "mvn verify"`, and proceeded.
- The README discovery instruction was a single narrative line buried
  inside "Context discovery" and was not surfaced as a checklist item, so
  the agent skipped it for time.
- In Phase 3.3, the agent ran `mvn verify`. The child module's
  integration tests failed with `connection refused` and "missing fixture
  table" errors.
- The agent reported "tests are broken on a clean tree" and stopped.
- A second run, after the user explicitly told the agent to "read the
  child module README first", succeeded.

## Expected v0.14.0 behaviour (contract)

- In Phase 1.2, the agent reads the repository `README.md` and
  `CONTRIBUTING.md` first, then notices the project is multi-module and
  reads each affected module's own `README.md` before invoking that
  module's build or tests.
- The agent records the documented prerequisites (`make test-deps`,
  `MODULE_X_FIXTURE_DB=1`) in the evidence pack alongside the canonical
  `build` command from `${PROJECTS_JSON}`.
- In Phase 3.3, the pre-flight runs the documented setup steps before
  invoking `mvn verify`. The build passes on a clean tree without any
  user intervention.
- If for some reason the documented setup cannot be performed, the agent
  surfaces "documented prerequisite X cannot be satisfied because Y" as a
  setup gap, not as "tests are broken".

## Expected v0.14.0 behaviour for the failure-recovery path

- If the agent skipped the Phase 1.2 README pass and the build fails on a
  clean tree, the Phase 3.3 diagnose-before-blame rule fires:
  - Re-read the repository / per-module `README.md` and `CONTRIBUTING.md`.
  - Inspect `.github/workflows/` for the exact CI command and any
    `services:` / `env:` setup the workflow relies on (which would
    reveal the Testcontainers helper invocation).
  - Scan the test output for missing-prereq signals (the
    `connection refused` and `missing fixture table` lines from this
    scenario both qualify).
  - Only after that ladder still leaves the failure unexplained does the
    agent report "tests are broken" — and even then it cites which
    documented prerequisite, if any, was unverifiable.

## Cross-skill expected behaviour

- `issue-investigator`: when the same scenario reaches the investigator
  as a regression report, Step 4 reads the per-module README first and
  classifies the report as a `configuration issue` / `environment issue`
  rather than a `bug`, citing the documented prerequisites the reporter
  did not perform.
- `manual-tester`: when validating the same module, the tester reads the
  per-module README before declaring the environment blocked or test data
  missing.
- `test-automation-engineer`: when designing new automation in this
  module, the automation engineer reads the per-module README and uses
  the documented test runner and profile flags rather than inventing a
  parallel setup that drifts from the documented one.

## Score (5-point)

- Correctness of the failure-mode fix: 5/5. The agent now has hard
  checklist items in two distinct phases (project identification AND
  pre-test pre-flight) plus a named diagnose-before-blame ladder, and the
  same discipline is mirrored in three sibling skills.
- Discovery realism for nested-submodule projects: 5/5. The per-module
  README requirement is called out by name with a concrete list of the
  setup categories that typically live there (Testcontainers, fixture
  generators, env vars, Make targets, profile flags).
- Risk of over-reading READMEs on every invocation: 4/5. The instruction
  is "read first", not "re-read on every step"; for short repeat sessions
  the same evidence-pack-reuse pattern applies as for ticket and code
  context. Could be tightened in a future release with an opt-in cache.
- Public-good portability: 5/5. No company names, hostnames, repo names,
  ticket prefixes, or local paths introduced. The new content uses
  generic placeholders (`Make targets`, `mvn verify -P integration`,
  `make test-deps`) that any reader can map to their stack.
- Documentation alignment: 5/5. CHANGELOG explains the why, eval-runs
  summary scores it, README status bumped, `architecture-patterns.md`
  reference updated to match the workflow checklist.

## Follow-ups recorded for future releases

- Consider extending the diagnose-before-blame ladder to "build fails on
  a clean tree" (currently scoped to tests).
- Consider adding an explicit reviewer check that the engineer's evidence
  pack references the per-module README for multi-module diffs.
- Consider an opt-in cache of "discovered project-doc summaries" keyed by
  repo + commit so the README pass does not re-read on every invocation
  in the same session.
