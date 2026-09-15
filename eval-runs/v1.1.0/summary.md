# Release certification — v1.1.0

Every number below was produced by running the command named, on this checkout, before tagging.

## What this release changed

An agent used Wamala for a fourteen-phase delivery run on a host where a dispatched agent cannot
dispatch, and filed a report ordered by what each problem had cost it. Nine items. Every one was
reproduced against `1.0.0` before it was accepted, and the ones the runtime can hold are held by
code and pinned by a case that fails without the fix.

| Report item | Reproduced as | Now |
| --- | --- | --- |
| The runner cannot run where Wamala sends it | runner stopped before `phase-01`; chain table still pointed at it | `nested_dispatch` probed, `unknown` treated as unavailable, plan mode documented |
| "The plan itself is wrong" has no route | `phase-05` blocked on its own criterion; only legal moves were stop or ask | `plan-amendment` → `delivery-planner`, once per phase, from the artifact |
| Independent review structurally unachievable | every phase required it; every one reviewed itself | `review.independence` recorded; sibling `code-reviewer` dispatch restores it |
| Brief boilerplate is most of the work | ten briefs, 1,000–2,500 words, mostly repeated | one run preamble per run, referenced by every brief |
| Continuity improvised between phases | `follow_up_context` written and never read back | `plan-next` returns `prerequisite_context`; briefs paste it verbatim |
| No reversibility check for deletes | untracked documents in a directory with no `.git` | `agent-skills reversibility`; archive replaces delete |
| Classifier gaps: UX review, plan answers | landed on `product-owner` by analogy | `design-review` and `plan-amendment` rows, plus a known-gaps list |
| "Verify from artifacts" under-specified | prose artifacts judged only on existence | per-class verification bars |
| Four wrapper defects | see the changelog | all four fixed, each with a regression case |

Two further findings came out of writing the security review, and both were fixed before tagging:
a shared-directory cache anchor could redirect another user's task memory, and carried-forward
context reached briefs unlabelled.

## Verification

Every suite below was run on this checkout, after the rebase onto `main`.

| Gate | Result | 1.0.0 |
| --- | --- | --- |
| `scripts/validate-repo.py` | pass, 63 warnings | pass, 63 warnings |
| `scripts/run-evals.py` | 57 files, 0 failures, 0 warnings | 56 files, 0, 0 |
| `scripts/test-cli-install.sh` | 145 passed, 0 failed | 145 |
| `scripts/test-global-install.sh` | 112 assertions | 112 |
| `scripts/test-access-resolution.sh` | 100 assertions | 100 |
| `scripts/test-front-door-skill.sh` | 77 assertions | 63 |
| `scripts/test-context-optimizer.sh` | 107 checks | 107 |
| `scripts/test-guard.sh` | 116 passed, 0 failed | 116 |
| `scripts/test-lifecycle-fs.sh` | 62 passed, 0 failed | 33 |
| `scripts/test-secret-boundary.sh` | 46 passed, 0 failed | 46 |
| `scripts/test-adaptive-execution.sh` | 81 passed, 0 failed | 74 |
| `scripts/test-knowledge.sh` | 53 passed, 0 failed | 53 |
| `scripts/test-tools.sh` | 43 passed, 0 failed | 43 |
| `scripts/test-release-engine.py` | 31 passed, 0 failed | 31 |

The warning count is unchanged. Three suites grew: lifecycle filesystem safety by 29 (artifact and
evidence-pack preservation, the `finish-task` flags, the in-flight count, coordinated-run
deferral, one cache across both resolvers, reversibility, and an anchor owned by another account),
adaptive execution by 7 (`prerequisite_context`, including a nested mapping that must not
overwrite a phase's keys and a credential-shaped value that must not reach the decision), and the
front door by 14 (the new routing guarantees and the order of the three plan rows).

Not re-measured: the Execution Guard benchmark. `scripts/guard_parse.py` and
`scripts/guard_rules.py` are byte-identical to `1.0.0`, whose numbers (p50 0.104 ms, p95 0.298 ms,
cold call 74 ms) stand.

### Mutation probes

Four new probes, each asserting the weakened build gives the weaker answer:

| Probe | Property removed | Weakened build |
| --- | --- | --- |
| lifecycle 3 | `artifacts` in the cleanup keep list | a finished step's report is deleted |
| lifecycle 4 | the coordinated-run check in `finish-task` | a step deletes the coordinator's evidence |
| lifecycle 5 | the untracked-content check in `reversibility` | an untracked note reads as recoverable |
| adaptive 4 | redaction in `plan-next`'s evidence-pack read | a credential-shaped value reaches the brief |

The four existing probes in those suites still reproduce their defects. They first reported the
opposite, which is how the sandbox copies were found to need `cache_root.py`: without the module
beside them the weakened builds died on import, and a probe that cannot run reads as a probe that
passed.

### Release readiness

`bash scripts/test-release-readiness.sh`, upgrading from `v1.0.0`:

```text
== 1. structural validators ==        4 PASS
== 2. syntax across every shipped artifact ==   4 PASS
== 3. test suites ==                  11 PASS (ten suites + release engine)
== 4. CLI surface ==                  PASS
== 5. clean-HOME install, verify, drift, rollback, uninstall ==   PASS
== 6. upgrade from the v1.0.0 installation ==   PASS
== 6b. global-install upgrade across the rename (v0.37.0) ==   PASS
== 7. cloud / in-repo mode unaffected ==   PASS
== 8. public-safety review ==         PASS
== 9. README and documentation integrity ==   PASS
== 10. telemetry review ==            PASS
== 11. version consistency ==         PASS (VERSION 1.1.0; every SKILL.md; README; eval-runs/v1.1.0)

ok: release readiness verified (84 checks)   [1.0.0: 84]
```

### CI

GitHub Actions on [PR #60](https://github.com/wamalalawrence/agent-skills/pull/60): "Validate
skills and links" passed in 6m30s against the rebased branch.

### Telemetry

`python3 scripts/telemetry.py report --all` from the repository root:

```json
{
  "total_events": 13,
  "skills": {
    "software-engineer": { "completed": 1 },
    "code-review": { "completed": 1 },
    "code-reviewer": { "completed": 1 },
    "unknown": { "completed": 2 },
    "delivery-runner": { "stopped": 1 },
    "product-owner": { "completed": 1 },
    "wamala": { "stopped": 4 },
    "delivery-planner": { "completed": 2 }
  },
  "unknown_events": {},
  "performance": {
    "runs": 13,
    "median_minutes_to_first_artifact": null,
    "median_minutes_to_verified_result": null,
    "profiles": {},
    "dispatches": 0,
    "context_loads": 0,
    "review_rounds": 0,
    "parallel_runs": 0,
    "no_output_runs": 0,
    "dispatches_per_run": 0.0,
    "context_loads_per_run": 0.0
  }
}
```

**This report drove part of the release.** `wamala` shows four `stopped` events and no
`completed` ones; `delivery-runner` shows one `stopped`. Those five are the run the field report
describes: the runner stopping because it could not dispatch, and the dispatcher stopping at each
point where the routing table had no next move. `delivery-planner` and `product-owner` completed
in the same window, which is consistent with the parts of that run that had an owner and a route.
The counter that matters after this release is whether `wamala` starts recording `completed`
events on a host that cannot nest dispatch. If it does not, plan mode is not being reached and
the next investigation starts there.

`dispatches` is `0` across thirteen runs, which is a gap in the counter rather than in the work:
dispatch counts are recorded by the closeout flags, and a dispatcher that stops before finishing
never writes them. Nothing in this release changes that, and it is worth fixing before the
counter is used to judge plan mode.

`agent-skills knowledge doctor`: passes on a fresh base. This repository carries no committed
knowledge base of its own.

## Diff review

`git diff origin/main...HEAD` — 56 files, +2,656 / -232. Read in full before merge. It found two
wording defects in `skills/wamala/SKILL.md` (a paragraph split in two by an insertion, and a cap
described as "stricter" when it is larger), both fixed, and the two security findings recorded in
[the security review](../../docs/security-review-v1.1.0.md).

**The review was not independent.** [The release checklist](../../docs/release-checklist.md#diff-review)
asks for a reading by something that did not write the code, and this diff was read by the agent
that wrote it. That is the same gap this release fixes for dispatched steps, and it is recorded
here rather than glossed: the finding stands as "reviewed, not independently reviewed". An
independent review before merge would close it.

## Security review

[`docs/security-review-v1.1.0.md`](../../docs/security-review-v1.1.0.md). Nine threats, each
labelled probed, reasoned about, or unproven. Two findings were raised and fixed during the
review; a third — a crash on a symlink leaving the repository — was found while probing
`reversibility`. Residual risks are listed there.

## Packaging

Not run in this record. The npm bootstrap is published by the maintainer from the tagged
checkout, per [the release checklist](../../docs/release-checklist.md#release-publication):
`bash scripts/build-npm-bootstrap.sh --pack`, then `bash scripts/audit-npm-package.sh` against the
exact tarball, then `npm publish`, then an install from the registry on a machine with no source
checkout. `npm/package.json` and `VERSION` both read `1.1.0`, and the build refuses a mismatch.
