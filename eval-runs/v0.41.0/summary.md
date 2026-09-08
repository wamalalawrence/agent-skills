# Eval run — v0.41.0 (Context Optimizer)

Release-scoped evidence for `v0.41.0`. Everything below was produced by running the commands named,
not by assertion.

## What this release added

A reusable runtime, `agent-skills context`, that turns an input too large to read into a small,
task-specific, traceable context pack — plus the `context-optimizer` skill as its user-facing entry
point and the shared large-input rule every other skill inherits. See
[docs/context-optimizer.md](../../docs/context-optimizer.md).

## Verification

```bash
bash scripts/test-release-readiness.sh
```

| Gate | Result |
| --- | --- |
| `validate-repo.py` | pass, 71 warnings |
| `validate_skills.py` compatibility shim | pass |
| `run-evals.py` | pass — 47 files, 11 skills known, 0 failures, 0 warnings |
| `run-evals.py --strict-sections` | pass |
| `bash -n` across `setup.init`, `lib`, `bin`, `scripts`, `hooks` | pass |
| `ast.parse` across every `scripts/*.py` | pass |
| `test-global-install.sh` | pass |
| `test-access-resolution.sh` | pass |
| `test-front-door-skill.sh` | pass — 63 assertions |
| `test-context-optimizer.sh` | pass — 105 assertions |
| `test-setup-update-preserves-credentials.sh` | pass |
| Version consistency (11 `SKILL.md` vs `VERSION`) | pass — all `0.41.0` |

Warning count is unchanged from `v0.40.0`: 71 before, 71 after. Three warnings appeared during
development, all of them the validator's ticket-key regex reading a hyphenated standard name as a
tracker key. They were removed by spelling it without the hyphen, which is correct anyway — so the
warning was pointing at a real nit rather than being noise. No new warning category, and no warning
suppressed.

## Context reduction, measured

From `scripts/test-context-optimizer.sh` §14, against that suite's generated fixtures. **Characters,
not currency** — API prices change and tokenisation is provider-specific, so no cost claim is made.

| Fixture | Source chars | Selected chars | Omitted | Fragments | ms |
| --- | --- | --- | --- | --- | --- |
| `application.log` (80,632 lines) | 4,775,858 | 2,043 | 99.96% | 2 | 894 |
| `orders.json` (4,000-element array) | 484,165 | 196 | 99.96% | 2 | 92 |
| `hostile.log` | 353,204 | 1,582 | 99.55% | 3 | 66 |
| `dense.log` (100 equal matches) | 230,390 | 520 | 99.77% | 1 | 46 |
| `schema.sql` (403 tables) | 57,888 | 649 | 98.88% | 5 | 2 |
| `ci.log` (one cause, 400 effects) | 56,732 | 1,205 | 97.88% | 3 | 19 |
| `change.diff` (63 files) | 34,681 | 401 | 98.84% | 2 | 5 |

The ratios are the least interesting column. What matters is the next section.

## Correctness: did the evidence survive?

The suite asserts the four properties that make a pack worth having, per fixture. **A 99.9% reduction
that removes the root cause is a failure**, so ratio is never the criterion.

| Scenario | Required evidence | Retained? |
| --- | --- | --- |
| Giant repetitive log | `ERROR` line, exception class, all six trace frames, the `Caused by:` chain, `... 14 more` | yes |
| Giant repetitive log | 80,000 health-check lines reduced to a count | yes — fewer than 20 survive |
| Giant repetitive log | 400-line cascade summarised, not reproduced | yes — 7 survive, count stated |
| Identifier near a failure | surrounding window, preceding batch-start event | yes |
| Large SQL schema | 3 linked tables, the foreign key, the unique index, the check constraint | yes |
| Large SQL schema | 400 unrelated tables absent and counted | yes |
| Giant JSON | `$.orders[3178]`, its enclosing object, the array element count | yes |
| Huge diff | the `permitAll()` hunk among 61 generated files | yes |
| Huge diff | zero generated hunks emitted; 60 collapsed to one map row | yes |
| CI cascade | the `cannot find symbol` compile error, flagged `first-failure` | yes |
| CI cascade | 400 downstream failures not reproduced | yes — 6 survive, cascade stated |
| Prompt injection | the real failure, alongside the flagged hostile text | yes |
| Secret in log | the surrounding evidence, with the value redacted | yes |
| Budget pressure | relevant evidence at a 2,000-char budget, exclusions reported | yes |

Task-awareness was verified rather than assumed: the same 4.7 MB log packed against
*"Why did payment settlement fail for transaction 84721?"* and against *"Why is startup taking 90
seconds and which beans are slow?"* produces different pack ids, and the repeated bean-timing lines
are **collapsed as noise** for the first brief and **sampled as evidence** for the second.

Determinism was verified: two runs of the same brief produce byte-identical output once the
wall-clock `time:` line is excluded.

## Security probes

Full review: [docs/security-review-v0.41.0.md](../../docs/security-review-v0.41.0.md).

| Property | Probe | Result |
| --- | --- | --- |
| Credential value never reaches pack, render, or cache | suite §9 + §9b (77 paths) + CI | pass |
| `inspect` output redacted | suite §12 | pass |
| Instruction-shaped text flagged and preserved | suite §8 + CI | pass |
| Source text cannot change the budget | suite §8 + CI | pass |
| Rendered pack never exceeds the budget | suite §12, 49 combinations | pass |
| Changed source never served a stale pack | suite §11 | pass |
| Every fragment carries a locator and a reason | suite §12 | pass |
| Binary input refused rather than guessed at | suite §12 | pass |
| Malformed input neither crashes nor overruns | suite §9c (126 combinations) | pass |
| Cache files mode `0600` | suite §9 | pass |
| Diff packs state their own incompleteness | suite §6 | pass |
| Committed config can only adjust a clamped integer bound | manual, recorded in the review | pass |

### Mutation probes

Each probe copies the runtime into a sandbox, deletes one guarantee, and asserts the matching check
**fails**. Without this, a check would pass whether or not the property it names actually holds.

| Probe | Property removed | Expected consequence | Observed |
| --- | --- | --- | --- |
| `redaction` | `redact()` returns input unchanged | the raw token appears in the pack | as expected |
| `injection` | `looks_like_instruction()` returns `False` | the untrusted flag disappears | as expected |
| `cache-key` | source hash dropped from the pack id | two different sources collide on one id | as expected |
| `provenance` | fragment header stops printing the locator | `-- f1  lines ` disappears | as expected |
| `budget` | the render-size guarantee loop is skipped | the pack exceeds its stated budget | as expected |

The `budget` probe is pinned to a CI log at the 2,000-char floor rather than to any fixture: the
fill passes already cap content at half the budget, so the guard loop is only load-bearing where
the header and footer are large relative to the budget. Pointed at an easier fixture the probe
passed while proving nothing, which is the failure mode probes exist to prevent.

## Findings raised and resolved before release

Six defects, recorded because a release note listing only features implies the tests found nothing.

1. **A pack of pure footer.** At a tight budget on a dense input, the omission list crowded out the
   evidence it described, producing zero fragments plus a long explanation of why. The footer is now
   bounded proportionally to the budget, with an unconditional floor guaranteeing one fragment when
   candidates exist. Regression check: `TIGHT_FRAGS` in §10 reads `fragment_count` from the JSON,
   because the earlier text-search assertion passed against the omission preview.
2. **A silently lost SQL statement.** A leading `--` comment opened the statement buffer and merged
   with the first `CREATE TABLE`, which then failed to classify and vanished from **both** the object
   count and the omission count. An invisible loss is the one kind this runtime must not produce.
   Regression check: §4 asserts `table 403`.
3. **Cascade out-scoring its own cause.** Window merging added a fraction of every merged score, so
   400 cascading errors accumulated a score no root cause could beat. Merged windows now take the
   best anchor's score plus a bounded nudge, and cascade repeats are dropped rather than scored down.
4. **Confidently wrong provenance.** The JSON scanner double-counted newlines inside strings, so
   structural paths pointed at the wrong lines — worse than absent provenance, because it looks
   verifiable.
5. **A relevance flood.** Matching against the full node path made every element of a 4,000-element
   array a hit because its ancestor was called `orders`. Matching is now against the node's own key
   and value, with frequency discounting for terms that match nearly everything. The same change made
   the scanner token-driven, taking that fixture from 2,959 ms to 92 ms.
6. **`inspect` was off the redaction path.** Raised during the security review as F1 and recorded
   there in full: the structure summary quoted the most-repeated line verbatim, and `inspect` is the
   command skills are told to run *first*.

Two of those — 1 and 6 — were found by asking "which path does not go through the control?", which is
the v0.37.0 lesson applied deliberately rather than relearned.

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

`python3 scripts/telemetry.py report --all`, verbatim, run from the repository root.

Section 10 of `test-release-readiness.sh` prints `total_events: 0` for the same command. That is not
a contradiction: the counters are per-project and the cache root resolves through
`WORKSPACE_ROOT`, which that suite sets to a sandbox. The repository-root reading above is the one
that reproduces.

- Two events total, both `completed`. Zero `stopped`, so no skill shows a rising stop share.
- **No `invoked` events at all**, and nine of eleven skills show nothing. The counters are far too
  sparse to compare per-skill health against v0.40.0.
- This report drove **no** skill change this release. Said plainly, because an unread counter is
  worse than no counter: it looks like evidence.
- The missing `invoked` events are the finding worth carrying forward. Either the lifecycle wrappers
  are not emitting them, or the local cache this was read from predates that behaviour. Worth
  establishing which before the next release treats these counters as a signal.

`agent-skills knowledge doctor` on a freshly initialised base: `ok: knowledge base valid with 0
warning(s)`.

## Pre-merge diff review

Run after validation was green and before merge, per
[the release checklist](../../docs/release-checklist.md#diff-review). The suites were green
beforehand — that is the point of doing it anyway, and v0.37.0 is the precedent: it passed every gate
and a reading of its own diff found five live defects.

It found **four further defects**, all reproduced before fixing, all now pinned by a test. Three of
them are the same class — a field written *after* the budget was reconciled, which then changed the
rendered length the reconciliation had just checked.

**R1 (MAJOR) — the omission that prevents a wrong conclusion was ranked last.**
`OMISSION_PRIORITY` had no entry for `sampled-repeats`, so it fell to the default tier behind three
`collapsed-repeats` records about irrelevant health checks. That record is the one saying "the four
lines you are reading stand for forty"; a reader who does not see it can reasonably conclude there
were four. Reproduced at budgets 1,500, 3,000 **and** 6,000 — it was hidden at every realistic
budget. Fixed by giving it the same tier as `cascade`, and by re-stating the ordering principle:
tier 0 is what the reader can act on, tier 1 is what changes how the *retained* fragments must be
read, tier 2+ describes absent bulk. Pinned by three assertions in §2.

**R2 (MAJOR) — the budget was non-monotonic.** A 2,000-char budget emitted evidence where 2,500
emitted none. The trim pass sized a fragment against an *estimate* of the header and footer; the
estimate then moved as the omission record changed, and the drop loop resolved the conflict by
throwing the fragment away. Fixed by replacing the two competing mechanisms with one,
`force_fit_one`, which measures the rendered pack instead of estimating it and shrinks the best
remaining candidate until it fits. Behaviour is now monotonic from the floor upward.

**R3 (MAJOR) — the budget could be exceeded by one character.** `processing_ms` is measured after
reconciliation and appears in the metrics as `time: N ms`, so `0 ms` during reconciliation became
`46 ms` afterwards and the pack rendered 2,001 chars against a 2,000-char budget. The redaction and
instruction-shaped counts had the same shape of problem, being assigned after the fill. Fixed twice
over: the timing field is now fixed-width, and `Pack.sync_metrics()` keeps the emitted-set metrics
in step during reconciliation rather than being applied once at the end.

**R4 (MAJOR) — the documented budget floor was a false promise.** `MIN_BUDGET_CHARS` was 1,000, and
at 1,000 the header alone does not fit: the runtime failed loudly rather than lying, but it accepted
a budget it could never honour. Measured properly: below ~1,500 the header, map, and omission records
cannot coexist with a fragment at all, and below 2,000 a pack renders inside its budget but carries
no evidence. The floor is now 2,000, with the measurement recorded in
[docs/context-optimizer.md](../../docs/context-optimizer.md#deterministic-budget). The verbose
`budget` omission record also now names one excluded locator instead of three below 6,000 chars,
because at a small budget three fully-reasoned locators cost more than the evidence whose absence
they describe.

Two process findings, both outside `scripts/context.py` and both the same shape — a hardcoded count
that assumed eight top-level skills:

**R5 (MAJOR) — `scripts/test-global-install.sh` asserted `removed 8 registration(s)`.** It broke the
moment a ninth skill shipped: a test failing for a reason unrelated to what it tests, which was that
uninstall can still find its own registrations after the source tree is deleted. Now derived from the
skill count on disk rather than re-hardcoded to nine.

**R6 (MINOR) — `scripts/test-release-readiness.sh` still expected the `tech-lead` migration notice.**
The alias removal updated `test-front-door-skill.sh` and missed this second place. Inverted the same
way: the shipped CLI must now pass the retired name through unchanged.

Three verification sweeps were written during the review and folded into the suite permanently rather
than left as one-off scripts, since a one-off sweep proves a moment and a test proves a release:

- **§9b** — the redaction claim on **every** emitter for **every** strategy: 77 output paths across
  seven fixtures (`pack` in three formats, `inspect` in two, `explain` in three, `expand` two ways,
  the cache listing, and the cache files). Section 9 had checked one strategy's text output, which is
  the path a test naturally looks at and not the only path a secret can leave by.
- **§9c** — nine malformed inputs (empty, no trailing newline, blank lines only, unterminated JSON
  string, truncated JSON, unterminated SQL, hunkless diff, headerless diff, one 400 KB line) against
  all seven strategies at two budgets: 126 combinations, no crash and no overrun.
- **§2** — the sampling-record survival checks that pin R1.

The suite grew from 97 to 105 assertions as a result.

Earlier findings and their resolutions are in the
[Findings](#findings-raised-and-resolved-before-release) section above and in
[the security review](../../docs/security-review-v0.41.0.md).

## What this run does not establish

- That the streaming design holds at tens of gigabytes. The largest fixture exercised is 4.7 MB.
- That relevance heuristics find the answer in inputs unlike these fixtures.
- Any dollar figure. Reductions are in characters; no measurement here was taken against a known
  model-and-pricing configuration.
- That an agent will follow the skill's guardrails. Same limit as every instruction in this
  repository — see [known limitations](../../docs/known-limitations.md).
