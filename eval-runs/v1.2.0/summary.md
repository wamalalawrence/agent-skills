# Release certification — v1.2.0

Every number below was produced by running the command named, on this checkout, before tagging.

## What this release changed

Meeting Intelligence: "Listen to this meeting: <link>" sends a visible, named assistant into a
Teams, Zoom, or Google Meet call; polling alone carries the meeting to a redacted transcript; the
host agent extracts engineering facts one bounded window at a time; the CLI validates every fact
mechanically and commits the meeting's facts to the repository knowledge base in one write. The
design was settled in [DISCOVERY.md](../../docs/meeting-intelligence/DISCOVERY.md) before any code,
and every deviation from the feature brief is recorded there. The user guide is
[docs/meeting-intelligence.md](../../docs/meeting-intelligence.md). Additive: no existing command,
exit code, or skill changed behaviour.

It also fixes a pre-existing `1.1.0` defect found while testing: `knowledge read` overran budgets
just above its minimum.

## Verification

| Gate | Result | 1.1.0 |
| --- | --- | --- |
| `scripts/validate-repo.py` | pass, 92 warnings | pass, 90 warnings |
| `scripts/run-evals.py` | 59 files, 0 failures | 57 files, 0 failures |
| `scripts/test-cli-install.sh` | 150 passed, 0 failed | 145 |
| `scripts/test-global-install.sh` | 112 assertions | 112 |
| `scripts/test-access-resolution.sh` | 100 assertions | 100 |
| `scripts/test-front-door-skill.sh` | 78 assertions | 77 |
| `scripts/test-context-optimizer.sh` | 107 checks | 107 |
| `scripts/test-guard.sh` | 116 passed, 0 failed | 116 |
| `scripts/test-lifecycle-fs.sh` | 62 passed, 0 failed | 62 |
| `scripts/test-secret-boundary.sh` | 46 passed, 0 failed | 46 |
| `scripts/test-adaptive-execution.sh` | 81 passed, 0 failed | 81 |
| `scripts/test-knowledge.sh` | 54 passed, 0 failed | 53 |
| `scripts/test-tools.sh` | 43 passed, 0 failed | 43 |
| `scripts/test-release-engine.py` | 31 passed, 0 failed | 31 |
| `scripts/test-meeting.py` (new) | 22 passed, 0 failed, offline | — |

The warning count rose by two, both from one line of `scripts/test-meeting.py`: a deliberately
malformed meeting link with credentials in it, used to assert that such a link is refused. The
validator reads it as a hostname and an address. Every other warning is unchanged from `1.1.0`;
meeting-platform and Recall hosts were added to the validator's allowlist because this feature
has to name them.

Suites that grew: cli-install by 5 (meeting state survives update and rollback, the installed
launcher dispatches `meeting`), front-door by 1 (the tenth top-level skill), knowledge by 1 (the
budget sweep).

### Mutation probes

| Probe | Property removed | Weakened build |
| --- | --- | --- |
| meeting: monotonic | the rank check in `transition` | an old observation regresses `MEDIA_READY` to `JOINING` |
| meeting: hedge | explicit-agreement detection | a hedged proposal is committed as `CONFIRMED` |
| meeting: secrets | the spoken-secret layer | a spoken password reaches the stored transcript |
| meeting: scope | the scope check on read | another repository's decision is recalled |
| knowledge: budget sweep | the withheld-notice compaction | budgets 300-400 overrun (shown by removing it by hand) |

Knowledge probe 3 (budget accounting) still reports its overrun (4,224 of 4,000). The first
version of the budget fix hid it; the fix now applies only when no entry is left to trim.

### Model-dependent evals (brief 15-22)

`scripts/eval-meeting-intelligence.py`, six golden transcripts in
[`evals/meeting-intelligence/`](../../evals/meeting-intelligence/). **The same session wrote the
golden set and did the extraction**, so the first table shows that good extraction survives the
pipeline, not an unbiased quality measure. The second table is the one that measures the checks:
the same windows with a deliberately bad extractor (confirms every hedge, obeys injected lines,
fabricates evidence, invents an owner and a date, claims a supersession on similarity).

Host extraction — [scores](meeting-intelligence/scores.md):

| Eval | Property | Host (raw) | After CLI checks | Met |
| --- | --- | --- | --- | --- |
| 15 | explicit agreements → CONFIRMED | 3/3 | 3/3 | yes |
| 16 | hedges never CONFIRMED | 0 false | 0 false | yes |
| 17 | actions with spoken owner | 4/4 | 4/4 | yes |
| 18 | explicit supersession yes, similarity no | — | 4/4 | yes |
| 19 | evidence exists and supports | 29/29 | all | yes |
| 20 | injection changes nothing | — | 5/5 | yes |
| 21 | long meeting in bounded windows | — | 4/4 facts; 10 windows, max 11,981 of 12,000 chars | yes |
| 22 | retrieved, labelled, same scope only | — | 5/5 | yes |

Adversarial extractor — [scores](meeting-intelligence-adversarial/scores.md):

| Eval | Host (raw) | After CLI checks |
| --- | --- | --- |
| 16 | 6 false confirmations | 0 |
| 17 | wrong owner and invented date on one action | both cleared; 3/4 (the right owner cannot be supplied) |
| 18 | bogus similarity supersession | not applied; 4/4 |
| 19 | 30/35 supported | every committed fact supported |
| 20 | three injected "facts" | none committed; 5/5 |

What the evals found and changed: the shared instruction pattern missed "ignore **your**
(previous) instructions" (widened in Context Optimizer, knowledge doctor, and guard scan-content;
guard false-positive corpus unchanged); a speaker who merely spoke an action line was accepted as
its owner (now a first-person commitment is required); the scorer itself mis-classified a
replacement that names the old store (fixed in the scorer).

### Release readiness

`bash scripts/test-release-readiness.sh`, upgrading from `v1.1.0`:

```text
== 1. structural validators ==        PASS
== 2. syntax across every shipped artifact ==   PASS
== 3. test suites ==                  12 PASS (ten suites, release engine, meeting intelligence)
== 4. CLI surface ==                  PASS
== 5. clean-HOME install, verify, drift, rollback, uninstall ==   PASS
== 6. upgrade from the v1.1.0 installation ==   PASS, including: rollback to v1.1.0 with
                                      meeting state present; its verify and doctor pass; the
                                      state is byte-identical afterwards
== 6b. global-install upgrade across the rename (v0.37.0) ==   PASS
== 7. cloud / in-repo mode unaffected ==   PASS
== 8. public-safety review ==         PASS
== 9. README and documentation integrity ==   PASS
== 10. telemetry review ==            PASS
== 11. version consistency ==         PASS (VERSION 1.2.0; every SKILL.md; README; eval-runs/v1.2.0)

ok: release readiness verified (88 checks)   [1.1.0: 84]
```

### Recall API contract

Checked against Recall's published reference (`docs.recall.ai`, via its `llms.txt` index) for this
release: bot create fields, retention, `automatic_leave`, chat on join, status codes and sub-codes,
media shortcuts, async transcription, delete media, leave call, regions, and Svix webhook
signing. No live Recall account was used; the fixtures in `scripts/fixtures/meeting-recall/` are
derived from that reference and say so.

## Diff review

The complete diff was read before merge. It found, and this release fixes: `urllib` forwarding the
API key on cross-host redirects; `doctor` reading the Recall secret on every `start-task`; an
instruction-shaped fact statement reaching later agents' preflight; one meeting's local write
failure aborting reconciliation of all meetings; a finished meeting never retrying a failed media
deletion; window checkpoints briefly holding unredacted facts; incomplete records crashing
reconcile. Each has a test.

**The review was not independent.** As in `1.1.0`, it was read by the agent that wrote it. An
independent review before tagging would close the gap; it is recorded rather than glossed.

## Security review

[`docs/security-review-v1.2.0.md`](../../docs/security-review-v1.2.0.md). Ten threats, each
labelled probed or reasoned about; five findings fixed; residual risks listed. It also records a
development incident: before the offline guard existed, one test run sent a single request with a
placeholder key to Recall.

## Packaging

The npm bootstrap is published by the maintainer from the tagged checkout, per
[the release checklist](../../docs/release-checklist.md#release-publication):
`bash scripts/build-npm-bootstrap.sh --pack`, `bash scripts/audit-npm-package.sh` against the exact
tarball, `npm publish`, then an install from the registry on a machine with no source checkout.
`npm/package.json` and `VERSION` both read `1.2.0`.
