# Eval Run Summary — v0.39.0

Release-scoped verification for the `test-automation-engineer` expansion: nine task modes,
mandatory framework discovery, a failure taxonomy, flake diagnosis, backlog dispositions,
test-level optimisation, traceability, and an `automation` routing class in `wamala`.

Run type: automated and structural. **No model was invoked** — the harness still has no agent
runner behind `--invoke` — so nothing here says anything about how well a model follows the new
workflow. What it does say is that the contracts are present and internally consistent, that the
routing table did not lose a row while gaining four, and that the whole install and access surface
is unaffected. Read [what this run does not prove](#what-this-run-does-not-prove) before treating
any of it as evidence that automation work gets better.

Reproduce the mechanical half with one command:

```bash
bash scripts/test-release-readiness.sh
```

## Structural verification

| Check | Command | Result |
| --- | --- | --- |
| Repository validation | `python3 scripts/validate-repo.py` | pass, 71 warnings |
| Compatibility shim | `python3 scripts/validate_skills.py` | pass, 71 warnings |
| Eval corpus | `python3 scripts/run-evals.py` | 41 files, 10 skills, 0 failures, 0 warnings |
| Eval corpus, strict | `python3 scripts/run-evals.py --strict-sections` | 41 files, 0 failures, 0 warnings |
| Version consistency | `VERSION` vs every `metadata.version` | all ten at `0.39.0` |
| Shell syntax | `bash -n` on `setup.init`, `lib/*.sh`, `bin/agent-skills`, `scripts/*.sh`, `hooks/*.sh` | pass |
| Python syntax | `ast.parse` on every `scripts/*.py` | pass |
| JSON templates | `json.load` on both hook templates and the link-check config | pass |
| Workflow | `yaml.safe_load` on `.github/workflows/ci.yml` | pass |
| Release readiness | `bash scripts/test-release-readiness.sh` | 76 checks, 0 failures |

The warning count is **unchanged at 71**, and the set is identical to v0.38.0's — verified by
diffing the two warning lists rather than comparing totals. Two warnings appeared during
development, where acceptance-criterion shorthand in an example and in the evidence-pack schema
read as ticket keys to the validator. Both were removed by writing "acceptance criterion N" in
prose, rather than by widening the validator's placeholder allowlist to absorb the false positive.

## Automated suites

| Suite | Assertions | Result |
| --- | --- | --- |
| `scripts/test-global-install.sh` | 119 | pass |
| `scripts/test-access-resolution.sh` | 100 | pass |
| `scripts/test-front-door-skill.sh` | 62 | pass |
| `scripts/test-setup-update-preserves-credentials.sh` | 10 exact `.env` lines | pass |
| `scripts/test-release-readiness.sh` | 76 | pass |

`test-front-door-skill.sh` grew from 50 to 62. Nothing else changed count: this release touches no
installer, resolver, or credential code path.

## The routing contract, as an ordered subsequence

v0.38.0's front-door test asserted that every routing row was **identical** to `v0.37.0`. That was
the right test for a rename, where any routing change was a defect. It is the wrong test for a
release that adds routing on purpose, and keeping it would have frozen the table rather than
protected it.

**The first attempt at replacing it was wrong, and pre-merge review caught it.** It compared the
two row sets with `comm` on sorted input: additions allowed, deletions and owner changes caught.
But a set comparison cannot see order, and the routing table is first-match-wins — its order *is*
its semantics. Two mutations passed a full 57-assertion run: moving the automation catch-all row
above the three boundary rows, which inverts exactly the ownership those rows exist to protect;
and inserting a second `review` row owned by `software-engineer` directly above the real one,
which silently changes the owner of every review request. The old equality check would have caught
both. That is a coverage regression, not a relaxation, and it was fixed before merge.

The check now asserts an **ordered subsequence**: every routing row present at a baseline must
still be present, verbatim, and in the same relative order. Rows may be added; a row may not
disappear, lose its owner, or move. Row numbers in `references/routing-table.md` are normalised
out, because renumbering on insert is not a contract change. Two baselines are checked, not one,
so a row cannot be dropped in one release and its loss go unnoticed in the next.

| Comparison | Result |
| --- | --- |
| `SKILL.md` rows vs `v0.37.0` | all present and in order, 6 added |
| `references/routing-table.md` rows vs `v0.37.0` | all present and in order, 6 added |
| `SKILL.md` rows vs `v0.38.0` | all present and in order, 6 added |
| `references/routing-table.md` rows vs `v0.38.0` | all present and in order, 6 added |
| `SKILL.md` `##` section structure vs `v0.37.0` | identical |

Ordered subsequence still cannot see a row **inserted above** an existing one: the shadowing row
takes over under first-match-wins while every baseline row remains present and in order. Five
`assert_class_owners` checks close that gap. For `automation`, `review`, `defect`, `question`, and
`validation`, the owners of the rows mentioning that class, read in table order, must be exactly
the expected sequence. A shadowing insert changes the sequence; so does a reorder.

**Shown failing.** Five mutations, each applied, run, and reverted with `git checkout --`:

| Mutation | Caught by | Result |
| --- | --- | --- |
| Delete the `review` row | subsequence (both baselines) + class owners | 3 failures |
| Change row 16's owner to `software-engineer` | subsequence (both baselines) + class owners | 3 failures |
| Swap baseline rows 5 and 6 | subsequence (both baselines) + class owners | 3 failures |
| Move the automation catch-all above the boundary rows | class owners | 1 failure |
| Shadow-insert a `review` row owned by `software-engineer` | class owners | 1 failure |

The last two are the ones the intermediate version passed. Restoring the file returns the suite to
62 passing assertions. A check that cannot fail is not evidence, and this one was rewritten twice
this release, so it was worth proving rather than asserting.

The three boundary rows matter more than the destination row: a router that sends every red test
to the automation engineer quietly makes that skill absorb root-cause analysis and product
decisions, which is the ownership this release is careful to keep out of it.

## Pre-merge diff review

The release checklist requires the diff to be reviewed by something with no stake in the change
being correct. That review ran against the full `main...HEAD` diff and raised six findings; all
six were fixed before merge, and every claimed defect was reproduced first.

| Finding | Severity | Resolution |
| --- | --- | --- |
| The replacement routing check was order-blind, and order is the contract | material | Rewritten as an ordered subsequence plus five class-owner sequence assertions; five mutations shown failing |
| The CHANGELOG did not mention the release-readiness section 6b change | material | Added, with the reason the floating tag stopped testing the rename |
| `suite-maintenance.md` said "none is forbidden absolutely" above two rows reading "Never" | minor | Two repairs marked `never`; the SKILL.md guardrail and step 4 no longer license them |
| `framework-evolution` skipped step 9, which claims every task ends with a persisted record | minor | Mode sequence now ends at 9 |
| Step 5 dropped the reference's qualifiers on `EXPECTED_PRODUCT_CHANGE` and `TEST_DATA_FAILURE` | minor | Qualifiers carried to the point of decision, where the eval-D failure mode lives |
| A triage routing row implied this skill confirms root causes | cosmetic | Reworded to name the investigation as the source |
| Both scripts' tag environment variables were undocumented | cosmetic | Added to their usage headers |

One further issue was found and deliberately **not** fixed: the anchor
`#evidence-packymldelivery_plan-ownership-rule` at
`skills/software-engineer/references/evidence-pack.md:309` points at a bold paragraph rather than a
heading, so it has never resolved. It is pre-existing on `main` and unrelated to this change.

## Section 6b was pinned to the release it tests

Release readiness section 6b upgrades a global install across the front-door rename. It read the
previous tag from `git tag --sort=-v:refname`, which meant that the moment v0.38.0 shipped it
started looking for `skills/tech-lead` in a release that no longer had it — two failures, and a
check that had silently stopped testing the rename. It is now pinned to `v0.37.0`
(`AGENT_SKILLS_RENAME_TAG`), which is the fixed historical boundary it was written for. Section 6,
the generic previous-tag upgrade, still floats and still passes.

## New eval scenarios

Three eval files, twelve scenarios, all structural-checked by `run-evals.py` and all written
against decisions rather than wording:

**[Modes and discovery.](../../evals/test-automation-engineer-modes-and-discovery.md)** New UI
automation in an existing Playwright repo; API-level choice over UI; a 63-scenario backlog; a
70-minute e2e suite; an unknown framework.

**[Failure triage.](../../evals/test-automation-engineer-failure-triage.md)** A suite broken by a
UI refactor; a regression test failing after a backend change; fifty failures behind one
authentication fixture.

**[Flake, ambiguity, and safety.](../../evals/test-automation-engineer-flake-ambiguity-and-safety.md)**
An asynchronous flake; behaviour nobody agreed on; automation aimed at production; an
authenticated sandbox resource.

[`evals/wamala-routing.md`](../../evals/wamala-routing.md) gains a wall of CI failures and a slow
test suite, both of which have a plausible wrong destination.

The scenario worth naming is the regression test that starts failing after a backend change. The
locally rational move — update the assertion to match the new behaviour — is exactly how a
regression suite stops being one, and it is the behaviour the eval exists to catch.

## Telemetry review

```json
{
  "total_events": 2,
  "skills": {
    "software-engineer": {
      "completed": 1
    },
    "manual-tester": {
      "completed": 1
    }
  },
  "unknown_events": {}
}
```

Two events on this machine, both `completed`, no `stopped` events and no unknown events. That is
too little to compare per-skill completion rates against v0.38.0, and it is reported here as the
raw counter rather than dressed up as a trend. `test-automation-engineer` shows zero `invoked`
events, which on a maintainer machine with two recorded runs means nothing either way.

**This release was not driven by a telemetry finding.** It came from a review of what the skill
could not do, not from a counter. Saying so is the point of the step: an unread counter is worse
than no counter, and so is one credited with a decision it did not make.

`agent-skills knowledge doctor` reports no knowledge base in this repository, which is expected —
this repo has never committed one. The round-trip is covered instead by release readiness against
a fresh base, and by the CI job that initialises, writes, reads, and doctors one.

## Public-safety and security review

- The public-safety sweep in release readiness section 8 passes: no private absolute path, no
  secret-shaped string, and no private or generated config file in tracked files.
- An independent grep over every new and modified file for credential patterns, private keys, and
  absolute home paths returned nothing.
- **No security-review document is required for this release.** The checklist requires one when a
  release changes authentication, credential storage, global filesystem state, or the trust
  boundary around repository-supplied content. This release changes none of them: no installer,
  resolver, or credential code path is touched, and `test-access-resolution.sh` and
  `test-setup-update-preserves-credentials.sh` are unchanged and passing. The access-related edits
  are documentation — the skill now points at `agent-skills access resolve` instead of describing
  the pre-v0.37.0 `.env`-in-a-parent-workspace model.
- The new skill text tightens rather than loosens the credential posture: it forbids asking for a
  secret in conversation, forbids writing one into a test, fixture, log, or artifact, and repeats
  the discovered-credential protocol. One eval scenario exists to catch the opposite behaviour.

## Skill size

| File | Lines |
| --- | --- |
| `skills/test-automation-engineer/SKILL.md` | 660 (from 460) |
| `references/framework-discovery.md` | 98 |
| `references/failure-triage.md` | 140 |
| `references/suite-maintenance.md` | 105 |
| `references/automation-backlog.md` | 122 |

The skill itself grew by 200 lines while roughly tripling in scope, because the deep material —
the discovery sweep, the taxonomy tables, the repair playbook, the prioritisation factors — went
into references that are read on demand rather than loaded on every invocation, per
[token efficiency](../../docs/token-efficiency.md). It remains well under `software-engineer`
(1189) and `issue-investigator` (822).

## What this run does not prove

- **No model was invoked.** Nothing here shows that an agent given "triage these 42 failures"
  actually clusters them, or that it refuses to rewrite a failing assertion. The evals describe
  the behaviour that would count as passing; they were not executed against a model.
- **No real test framework was run.** No Playwright, Cypress, Selenium, WebdriverIO, Appium, REST
  Assured, Karate, pytest, JUnit, Pact, or Testcontainers suite was executed anywhere in this
  release. The skill's framework independence is a property of its text — it names no product as a
  requirement and routes every decision through repository discovery — not a demonstrated runtime
  compatibility with any of them.
- **No browser, device, or backend environment was available.** Claims about selector stability,
  observable waits, shard behaviour, or CI-equivalent execution are contract statements the skill
  makes, not measurements this run took.
- **The stability budget was not exercised.** No repeat-execution run happened; the 20-repeat
  default is a rule the skill states, and nothing here tested a tool's support for it.
- **Routing quality is unmeasured.** The subsequence and class-owner checks prove rows exist, keep
  their owners, and stay in order. They say nothing about whether a model classifies "CI has 42
  failures" as `automation`.
- **The routing check does not cover every shadowing insert.** The class-owner assertions pin five
  classes. A row inserted above an existing one for a class outside that set would still pass, and
  the residual gap is stated here rather than left to be discovered.
- **Telemetry is too sparse to compare.** Two events is not a trend, and it is not treated as one.
