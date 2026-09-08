# Eval Run Summary — v0.40.0

Release-scoped verification for the developer-testing change: a new `software-engineer` policy
reference, six test-design decisions in the implementation phase, a restructured `test-quality`
review profile in `code-reviewer`, an explicit ownership line against `test-automation-engineer`,
and ten new eval scenarios.

Run type: automated and structural. **No model was invoked** — the harness still has no agent
runner behind `--invoke` — so nothing here says whether an agent given a mock-heavy test actually
rewrites it. What it does say is that the contracts are present and consistent, that the routing
row this release adds is pinned by an assertion that was shown failing three ways, and that no
installer, resolver, or credential path moved. Read
[what this run does not prove](#what-this-run-does-not-prove) before reading any of it as evidence
that tests get better.

Reproduce the mechanical half with one command:

```bash
bash scripts/test-release-readiness.sh
```

## Structural verification

| Check | Command | Result |
| --- | --- | --- |
| Repository validation | `python3 scripts/validate-repo.py` | pass, 71 warnings |
| Compatibility shim | `python3 scripts/validate_skills.py` | pass, 71 warnings |
| Eval corpus | `python3 scripts/run-evals.py` | 44 files, 10 skills, 0 failures, 0 warnings |
| Eval corpus, strict | `python3 scripts/run-evals.py --strict-sections` | 44 files, 0 failures, 0 warnings |
| Version consistency | `VERSION` vs every `metadata.version` | all ten at `0.40.0` |
| Release readiness | `bash scripts/test-release-readiness.sh` | 76 checks, 0 failures |

The warning count is **unchanged at 71**, and the set is identical to v0.39.0's — the two lists were
diffed, not the totals. No new warning was introduced and none was suppressed.

## Automated suites

| Suite | Assertions | Result |
| --- | --- | --- |
| `scripts/test-global-install.sh` | 119 | pass |
| `scripts/test-access-resolution.sh` | 100 | pass |
| `scripts/test-front-door-skill.sh` | 63 (from 62) | pass |
| `scripts/test-setup-update-preserves-credentials.sh` | 10 exact `.env` lines | pass |
| `scripts/test-release-readiness.sh` | 76 | pass |

Only the front-door suite changed count, and only because this release adds a routing row.

## The routing row is pinned, and the assertion was shown failing

Wamala gains one row: tests for a code change this session is making or just made go to
`software-engineer`, above the `automation` catch-all. First-match-wins is the whole mechanism —
without the ordering, "write unit tests for the pricing rules I just changed" reaches
`test-automation-engineer` because it contains the word "tests", and an engineer needs a second
specialist to test their own code.

The five existing `assert_class_owners` sequences **cannot see this row.** They match rows
containing a class token in backticks (`` `automation` ``, `` `review` ``, and so on); the new row
contains none, so it is invisible to every one of them, including their shadowing protection. A row
added under that blind spot with no check of its own is a contract nobody is holding.

One assertion now holds it: the row must exist, must be owned by `software-engineer`, and must
appear above the automation catch-all. Three mutations, each applied, run, and reverted with
`git checkout --`:

| Mutation | Result |
| --- | --- |
| Delete the developer-test row | `FAIL a routing row owns the developer tests that ship with a change` |
| Move it below the automation catch-all | `FAIL the developer-test row precedes the automation catch-all` (row 16 vs catch-all 15) |
| Change its owner to `test-automation-engineer` | `FAIL developer tests route to software-engineer` |

Restoring the file returns the suite to 63 passing assertions. The ordered-subsequence check against
both baselines passes unchanged: rows may be added, and none was removed, reordered, or reassigned.

## The rule this release replaces

One line in the code-review checklist:

```text
External dependencies mocked, not called for real, in unit tests
```

Read literally — and an agent reads literally — "dependency" covers anything injected into a
constructor. The safe reading was to mock every collaborator and verify every call, which produces
tests that pass while the behaviour is broken (the stubs supply the answers the assertions then
check) and that fail when a refactor moves a call without changing anything observable.

The replacement distinguishes an external **process** boundary — network, third-party APIs,
email/SMS, brokers, filesystem, clock, randomness — from an ordinary in-process collaborator that is
deterministic, cheap, and owned. The first is substituted. The second is used for real unless there
is a stated reason, and being a constructor dependency is explicitly not one.

Two things were deliberately **not** written into this release, and the final diff was swept for
both: no "never mock" and no "always mock external dependencies"; no Detroit or London allegiance,
no universal test-first mandate, no mock-count threshold, and no claim that coverage measures
quality. The grep over the staged diff returns only the sentences that forbid those things.

## New eval scenarios

Three eval files, ten scenarios, plus one added to the routing eval. All written against decisions,
not vocabulary — an answer that reaches the right decision in different words passes, and one that
recites the terminology while still doubling everything fails.

**[Unit boundary and double
selection.](../../evals/developer-testing-unit-boundary-and-doubles.md)** An over-mocked service
whose four collaborators are pure and owned; a refund flow where suppressing the second provider
call is the behaviour; a settlement test buried in a fifteen-object fixture graph; a shipping quote
computed by four cheap classes that should form one unit.

**[Third-party boundaries and test
levels.](../../evals/developer-testing-boundaries-and-test-levels.md)** Business logic tested
through three levels of a stubbed cloud SDK builder chain; a serialization regression that every
passing unit test missed while it was live.

**[Test verification quality.](../../evals/code-reviewer-test-verification-quality.md)** Four review
scenarios, and the discrimination is the point: a refactor-fragile test and a set of coverage-driven
tests contain real defects, while an audit publisher and an onboarding orchestrator are mock-heavy
and correct. A reviewer that finds problems in all four fails as surely as one that finds problems
in none.

[`evals/wamala-routing.md`](../../evals/wamala-routing.md) gains scenario G, whose plausible wrong
destination is `test-automation-engineer`.

The scenario worth naming is the coverage-driven one. `assertThat(result).isNotNull()` across every
public method moves a gate from 62% to 84% and protects nothing, and the correct review response is
neither to approve it because the number rose nor to demand the tests be deleted when the gate is
mandatory — it is to ask for assertions on the report's actual rules.

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

Two events on this machine, both `completed`, unchanged from v0.39.0 — the same two events, not two
new ones. No `stopped` events and no unknown events. That is too little to compare per-skill
completion rates, and it is reported as the raw counter rather than dressed as a trend.

**This release was not driven by a telemetry finding.** It came from reading what the skills told an
agent to do about mocking, and finding one line that told it to mock everything. Saying so is the
point of the step: a counter credited with a decision it did not make is worse than no counter.

`agent-skills knowledge doctor` passes on a fresh base, as in previous releases; this repository
has never committed a knowledge base.

## Public-safety and security review

- Release-readiness section 8 passes: no private absolute path, no secret-shaped string, and no
  private or generated config file in tracked files.
- An independent grep over every new and modified file for credential patterns, private keys, and
  absolute home paths returned nothing. The worked example and the eval scenarios use invented
  services, generic amounts, and no real hostnames.
- **No security-review document is required for this release.** The checklist requires one when a
  release changes authentication, credential storage, global filesystem state, or the trust boundary
  around repository-supplied content. This release changes none of them. No installer, resolver, or
  credential code path is touched; `test-access-resolution.sh` and
  `test-setup-update-preserves-credentials.sh` are unchanged and passing. The only executable change
  is one added assertion in `scripts/test-front-door-skill.sh` and two list entries in
  `scripts/validate-repo.py`.

## Skill size

| File | Lines |
| --- | --- |
| `skills/software-engineer/SKILL.md` | 1265 (from 1189) |
| `skills/software-engineer/skills/code-reviewer/SKILL.md` | 873 (from 769) |
| `skills/software-engineer/references/developer-testing.md` | 370 (new) |
| `skills/software-engineer/references/code-review-checklist.md` | 130 (from 112) |

The 370-line policy went into a reference read on demand rather than into `SKILL.md`, per
[token efficiency](../../docs/token-efficiency.md). What sits in `SKILL.md` is the six-decision
list and the pointer — a decision an agent makes mid-implementation, not an essay it loads on every
invocation.

## What this run does not prove

- **No model was invoked.** Nothing here shows that an agent given the over-mocked `PricingService`
  restores the real collaborators, or that a reviewer leaves the audit publisher alone. The evals
  describe what would count as passing; they were not executed against a model.
- **No test suite in any language was run.** No JUnit, pytest, Vitest, Mockito, or Testcontainers
  code was executed. The Java in the reference and the evals is illustrative and was never compiled.
- **The diff review was not independent.** The release checklist asks for a reviewer with no stake
  in the change being correct. This diff was reviewed by the context that wrote it, which is weaker,
  and it is recorded here rather than glossed. The mutation testing is the part of the review that
  does not depend on the reviewer's judgement.
- **Routing quality is unmeasured.** The new assertion proves the row exists, keeps its owner, and
  sits above the catch-all. It says nothing about whether a model classifies "write unit tests for
  what I just changed" as `change` rather than `automation`.
- **The judgement this release asks for is not mechanically checkable.** "Prefer the real
  collaborator unless there is a reason" has no validator. The evals are the only instrument, and
  they are prose until a runner exists.
- **Telemetry is too sparse to compare.** Two events is not a trend, and it is not treated as one.
