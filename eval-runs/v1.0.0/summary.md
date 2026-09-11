# Release certification — v1.0.0

The first stable release. This record exists so the promotion from `1.0.0-rc.4` is a checked
statement rather than a decision: every number below was produced by running the command named,
on this checkout, before tagging.

## What this release changed

A pre-1.0 architecture review — the third independent review of the candidate line — probed the
memory tiers, the lifecycle wrappers, and the dispatcher with inputs no suite had sent and graded
the boundary between an agent's claim and recorded knowledge as brittle. Sixteen findings; every
one was reproduced against `1.0.0-rc.4` before it was accepted, and the ones the runtime can hold
are held by code and pinned by a case that fails without the fix. The ones only an instruction
can hold were rewritten at every site the old wording appeared, and the shared text moved to one
reference. [CHANGELOG.md](../../CHANGELOG.md) has the full list; the short version:

| Finding | Reproduced as | Now |
| --- | --- | --- |
| Lesson evidence bypassed redaction | a token-shaped locator in a committed lesson file | one serialisation boundary; probe asserts the leak returns without it |
| Repeated submission raised confidence | five identical adds → 0.9, five confirmations, one piece of evidence | evidence is the observation identity; idempotent |
| Contradiction refreshed the lesson | `verified_at` bumped to today, still recalled | `disputed`, withheld, history kept |
| Decay stepped on every run | 0.8 → 0.7 → 0.6 on one afternoon | once per 90-day window |
| Recall preferred the oldest verification | ascending ISO date among equals | most recent first |
| Budget counted the payload only | 4,258 chars rendered for a 4,000 budget | rendered length is the budget, frame included |
| Lesson updates ran unlocked | read-modify-write outside `locked` | every mutation under the lock; deterministic lock-hold case |
| `durable.locked` proceeded after timeout; masked body errors | `RuntimeError: generator didn't stop after throw()` | `LockTimeout` before the body; body errors propagate; corrupt stores quarantined |
| Overlapping targets "provably independent" | `src/api` grouped with `src/api/handler.ts` | normalised, containment-aware, aliases and escapes refused |
| Completion was an unverified claim | `--status complete` with only a summary → `completed` | `dod-check`; `verified_delivery` in telemetry; `NOT verified` printed |
| "Every `false` needs a waiver" | classifications waived | checks vs classifications; waivers name an authority |
| RED could run where the test did not exist | "check out the parent" | test present, fix absent, behavioural assertion recorded |
| Stop hook wrote a false "unfinished" | two closeouts per normal session | `--if-open` is a no-op after a finish |
| Promotion counts were typed | `--confirmed-in 2` | project names verified on disk, all named as provenance |
| Dispatcher loaded the specialist it isolated | full owner `SKILL.md` read in Wamala step 4 | frontmatter only |
| Docs contradicted their own rules | "verified constraint" / "claim to verify"; "ships with remaining issues" / "no surviving major" | one sentence each, plus `docs/evidence-discipline.md` |

Two findings were accepted as documented limitations rather than fixed: behavioural evaluation
still validates scenarios, not a model's actions (the first `1.x` roadmap item), and symbol
spans in a context pack remain inferred from indentation (now marked as such, with decorators
included and capped fragments flagged).

## Verification

Every suite below was run on this checkout.

| Gate | Result | rc.4 |
| --- | --- | --- |
| `scripts/validate-repo.py` | pass, 63 warnings | pass, 63 warnings |
| `scripts/run-evals.py` | 56 files, 0 failures, 0 warnings | same |
| `scripts/test-guard.sh` | 116 passed, 0 failed | 116 |
| `scripts/test-release-engine.py` | 31 passed, 0 failed | 31 |
| `scripts/test-cli-install.sh` | 145 passed, 0 failed | 146 |
| `scripts/test-global-install.sh` | 112 assertions | 112 |
| `scripts/test-access-resolution.sh` | 100 assertions | 100 |
| `scripts/test-front-door-skill.sh` | 63 assertions | 63 |
| `scripts/test-context-optimizer.sh` | 107 checks | 107 |
| `scripts/test-lifecycle-fs.sh` | 33 passed, 0 failed | 33 |
| `scripts/test-secret-boundary.sh` | 46 passed, 0 failed | 43 |
| `scripts/test-adaptive-execution.sh` | 74 passed, 0 failed | 68 |
| `scripts/test-knowledge.sh` (new) | 53 passed, 0 failed | — |
| `scripts/test-tools.sh` | 43 passed, 0 failed | 43 |
| `scripts/test-release-readiness.sh` | see below | 83 checks |

The warning count is unchanged. `test-cli-install.sh` reports one case fewer: it is conditional on a
pre-release `VERSION`, which `1.0.0` no longer has. The secret-boundary suite grew by three (the evidence-field case,
the locator-survival case, and the redactor-removal probe); adaptive execution by six (parent
and child, alias, escaping, absolute, disjoint siblings, resource identity). The new suite's 53
checks are listed in its header.

Not re-measured: the Execution Guard benchmark. `scripts/guard_parse.py` and `scripts/guard_rules.py`
are byte-identical to `1.0.0-rc.4`, whose numbers (p50 0.104 ms, p95 0.298 ms, cold call 74 ms)
stand.

### Release readiness

`bash scripts/test-release-readiness.sh`, upgrading from `v1.0.0-rc.4`:

```text
== 1. structural validators ==        4 PASS
== 2. syntax across every shipped artifact ==   4 PASS
== 3. test suites ==                  11 PASS (ten suites + release engine)
== 4. CLI surface ==                  PASS
== 5. clean-HOME install, verify, drift, rollback, uninstall ==   PASS
== 6. upgrade from the v1.0.0-rc.4 installation ==   PASS
== 6b. global-install upgrade across the rename (v0.37.0) ==   PASS
== 7. cloud / in-repo mode unaffected ==   PASS
== 8. public-safety review ==         PASS
== 9. README and documentation integrity ==   PASS
== 10. telemetry review ==            PASS
== 11. version consistency ==         PASS (VERSION 1.0.0; every SKILL.md; README; eval-runs/v1.0.0)

ok: release readiness verified (84 checks)   [rc.4: 83]
```

### Packaging

`bash scripts/audit-npm-package.sh` against `npm/wamalalawrence-agent-skills-1.0.0.tgz`:

```text
14 file(s) in the package.
ok    no product content
ok    no credential-shaped file
ok    no repository internals
ok    the installation engine is present
ok    no absolute developer paths
ok    no secret-shaped strings
ok    no npm lifecycle scripts; package version matches VERSION
ok    the vendored engine is byte-identical to the repository's
Package content audit passed.
```

### Telemetry

`python3 scripts/telemetry.py report --all` from the repository root:

```json
{
  "total_events": 3,
  "skills": {
    "software-engineer": {
      "completed": 1
    },
    "code-review": {
      "completed": 1
    },
    "code-reviewer": {
      "completed": 1
    }
  },
  "unknown_events": {},
  "performance": {
    "runs": 3,
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

Three events, all `completed`, all from before this release, so none carries the new
`verified_delivery` field. The counters drove nothing here — every finding came from the external
review — and are recorded because an unread counter that looks like evidence is worse than no
counter. The field to watch from the next release on is the share of `completed` events with
`verified_delivery=no`.

## What the new coverage asserts

The point of the release is not the fixes; it is that each one now has a case that fails without
it, and where the guarantee is a negative — nothing leaked, nothing inflated, nothing overran — a
mutation probe removes the guarantee and asserts the failure reappears.

- **Memory integrity** (`test-knowledge.sh`, 53 checks). Observation identity across `add` and
  `confirm`; the conflict path; `contradict` leaving `verified_at` alone and disputing;
  reactivation on a further confirmation; `doctor` accepting the new fields; idempotent decay
  and a second window; recency ordering; rendered length at four budgets plus the withheld
  notices; `memory read` and `org-memory read` budgets; a held lock making a confirm wait and
  then land; a timed-out lock reported and nothing written; a body `OSError` reaching the
  caller; a corrupt store quarantined; nine `dod-check` cases; four `finish-task` cases for the
  evidence signal and the idempotent fallback; three promotion-provenance cases; three probes.
- **Secret boundary.** The evidence field through all three lesson operations, and a probe
  that replaces the module's redactor with the identity function.
- **Adaptive execution.** Containment, alias, escape, absolute, and the two positive cases that
  keep the rule from being a blanket refusal; the probe now removes the containment test.

## The process finding

The review found these by executing the runtime with inputs nobody had written down — the same
way the two rc.4 reviews found theirs. Every input it used is now written down. Four of the
findings raised *during this release's own review* were defects in the new tests: a probe that
could not fail, a budget floor the fix did not honour, an invalid fixture id that made a probe
read an absent file as "the guard held", and assertions grepping for JSON spacing the writer does
not emit. They are recorded in [the security review](../../docs/security-review-v1.0.0.md)
because a test that cannot fail is the failure mode this project keeps meeting.

## Recommendation

Promote to `1.0.0`: tag `v1.0.0`, publish the GitHub release, publish
`@wamalalawrence/agent-skills@1.0.0` to npm on the `latest` dist-tag, and verify an install from
the registry on a machine with no source checkout.

The bar the rc.4 record set for promotion was "another adversarial pass before freezing". This
release is that pass, and its findings were about the boundary the runtime can now hold rather
than about the frozen contracts, none of which changed.

## Security review

[docs/security-review-v1.0.0.md](../../docs/security-review-v1.0.0.md). Three of the findings sit
on a security boundary — credential retention in the committed tier, a lost-update path that also
masked the caller's own errors, and the claim-to-completion trust boundary. Each threat is
labelled probed, reasoned about, or unproven; the four findings raised during the review and the
five residual risks are recorded there.
