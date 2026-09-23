# Release certification — v1.4.0

Every number below was produced by running the command named, on this branch, before tagging. The
full `scripts/test-release-readiness.sh` run was made in a clean `git worktree` of the release
commit (`1461214`), so untracked files in the developer's checkout could not affect it.

## What this release changed

Meeting Intelligence: capture is now the user's choice among three providers — `native` (the
transcript Teams, Google Meet, or Zoom already made; no bot, no extra cost, data stays in the
tenant), `recall` (the existing visible bot, now with its cost and third-party processing
disclosed), and `desktop` (a local two-channel recording transcribed with whisper.cpp, started only
by the user at a terminal after a typed consent attestation). With no provider chosen, `join`
contacts nothing and prints the options. The decisions are recorded in the
[DISCOVERY.md 1.4.0 addendum](../../docs/meeting-intelligence/DISCOVERY.md#140-addendum-capture-as-a-user-choice)
(deviations D9–D15); the user guide is [docs/meeting-intelligence/README.md](../../docs/meeting-intelligence/README.md),
the privacy page [PRIVACY.md](../../docs/meeting-intelligence/PRIVACY.md), and the security review
[security-review-v1.4.0.md](../../docs/security-review-v1.4.0.md). Additive: an installation with
Recall configured keeps working with no action, meeting state keeps schema `v1`, and no exit code
was added.

## Verification

| Gate | Result | 1.3.0 |
| --- | --- | --- |
| `scripts/validate-repo.py` | pass, 94 warnings (107 at `1461214`; see below) | pass, 94 warnings |
| `scripts/run-evals.py` (+ `--strict-sections`) | 59 files, 0 failures | 59 files, 0 failures |
| `scripts/test-cli-install.sh` | 150 passed, 0 failed | 150 |
| `scripts/test-global-install.sh` | 112 assertions | 112 |
| `scripts/test-access-resolution.sh` | 100 assertions | 100 |
| `scripts/test-front-door-skill.sh` | 78 assertions | 78 |
| `scripts/test-context-optimizer.sh` | 107 checks | 107 |
| `scripts/test-guard.sh` | 116 passed, 0 failed | 116 |
| `scripts/test-lifecycle-fs.sh` | pass | pass |
| `scripts/test-secret-boundary.sh` | 46 passed, 0 failed | 46 |
| `scripts/test-adaptive-execution.sh` | pass | pass |
| `scripts/test-knowledge.sh` | pass | pass |
| `scripts/test-release-engine.py` | 31 passed, 0 failed | 31 |
| `scripts/test-meeting.py` | **39 passed**, 0 failed, offline | 22 |
| `scripts/test-shared-knowledge.py` | 36 passed, 0 failed | 36 |
| `scripts/eval-shared-knowledge.py` | all targets met | all targets met |
| CI on PR #63 (`1461214`) | pass (7m56s) | — |

Readiness: 91 of 92 checks passed in the clean-worktree run. The one failure was
`eval-runs/v1.4.0/summary.md is missing` — this file. `run-evals.py` passed there already.

**Warnings.** The release commit had 107 warnings, 13 more than `1.3.0` (compared line by line
against a `v1.3.0` worktree). All 13 were the new provider's public endpoints read as hardcoded
hosts (`graph.microsoft.com`, `login.microsoftonline.com`, `*.googleapis.com`,
`accounts.google.com`, `huggingface.co`) plus two wording false positives (`BCP-47` read as a
ticket key, a backtick after `localhost`). As in `1.2.0`, the vendor hosts were added to the
validator's product-host allowlist and the two phrases reworded, in the commit that adds this
file; the count is back to 94. The only remaining difference is one pre-existing line of
`test-meeting.py` (a deliberately malformed link with credentials) that moved from line 312 to 324.

`test-meeting.py` grew from 22 to 39 cases (C1–C17 from the release brief) and lost none. No other
suite changed.

### Upgrade and rollback

`test-release-readiness.sh` §6 installs `v1.3.0`, upgrades to this release, and rolls back; all
pass, including "v1.3.0 verify passes with meeting state present", "v1.3.0 doctor runs with
meeting state present", and "rolling back to v1.3.0 leaves meeting state untouched". Test case C16
adds the file-level half: a 1.3.0 `meeting.json` (Recall key and region, no `default_provider`)
makes `recall` the default, the new notice is shown once without blocking, and the real `v1.3.0`
`meeting.py` (from `git archive v1.3.0`) runs `list`, `status`, and `inspect` against state that
contains native records without a traceback.

### Mutation probes

The four 1.2.0 probes (monotonic transitions, hedge detection, spoken-secret layer, scope check on
read) still run and still show the weakened build giving the weaker answer. The new cases are
direct assertions rather than probes; the properties they pin, and how each fails without the
change:

| Case | Property | Without it |
| --- | --- | --- |
| C1 | no provider → no socket, no state, preflight, exit 2 | a socket guard fails the test on any `connect` |
| C4 | a refused provider never triggers another | Recall's transport is instrumented; any call fails the test |
| C9 | PKCE verifier checked; tokens only in the `0600` store; secret-bearing `--import` refused | the fake server rejects a wrong verifier; any token in state fails |
| C11 | desktop needs a TTY and a typed attestation; raw audio deleted | the non-TTY join must exit 2 with nothing recorded |
| C12 | a device name cannot become an ffmpeg option | `-filter_complex` as a device name must be discarded |
| C13 | channel attribution never yields a guessed owner | "You" as an owner must be cleared, "Anna" kept |
| C14 | a model with the wrong checksum is refused and deleted | the mismatching download must leave no file |

### Evals 15–22 (model-dependent)

`scripts/eval-meeting-intelligence.py render|score --runs eval-runs/v1.4.0/<run>`. The stored host
extractions from `v1.2.0` were copied and re-scored against this release's code. The windows
re-rendered byte-identically (`diff -rq` against `v1.2.0` is empty), which shows the stored
extractions answer exactly the windows this release produces for a named-speaker transcript, and
both score tables are identical to `1.2.0`:

- Host extraction — [scores](meeting-intelligence/scores.md): every eval meets its target.
- Adversarial extractor — [scores](meeting-intelligence-adversarial/scores.md): every eval meets
  its target except 17 (3/4), unchanged from `1.2.0` and by design — the adversarial extractor
  names a wrong owner on one action, the CLI clears it, and cannot supply the right one.

No new model-dependent eval was run for channel attribution. Its mechanical rules (no channel
label as owner, confidence cap, the window's attribution notice) are covered by C13; how well a
model follows the window notice was not measured. The v1.2.0 caveat still applies: the golden set
and the stored extractions were written by the same session.

## Security review

[docs/security-review-v1.4.0.md](../../docs/security-review-v1.4.0.md). Five issues were found and
fixed before release, none ever published: a configured audio device name starting with `-` could
have been passed to ffmpeg as an option; Meet resource names from API responses were used as URL
paths without validation; worker and ffmpeg logs were created with default permissions; model
downloads had no size bound; and the Zoom adapter widened its allowed hosts by mutating an
attribute rather than per request. Each has an assertion or a code path the suite exercises; the
device-name one is asserted in C12.

## Diff review

The release checklist asks for review by something that did not write the code. **That did not
happen for this release.** The diff was reviewed by the same session that wrote it, after the
suites were green, which produced the security findings above. The owner should read the diff
(`git diff main...feature/meeting-capture-choice`), or have it reviewed, before merging; this
record does not claim an independent review.

## Telemetry review

`python3 scripts/telemetry.py report --all`, verbatim from the clean-worktree run. Telemetry is
local to a checkout, so a fresh worktree has none:

```text
{ "total_events": 0, "skills": {}, "unknown_events": {}, "performance": { "runs": 0, "median_minutes_to_first_artifact": null, "median_minutes_to_verified_result": null, "profiles": {}, "dispatches": 0, "context_loads": 0, "review_rounds": 0, "parallel_runs": 0, "no_output_runs": 0, "dispatches_per_run": null, "context_loads_per_run": null }}
```

No skill change this release traces to telemetry. The `meeting-intelligence` skill change (check
`status --providers` first, relay the preflight, never start a desktop recording) and Wamala's
routing row come from the brief. `knowledge doctor` passes on a fresh base.

## Not done in this certification

- **Live checks.** The native adapters (Graph, Meet REST, Zoom) were built against the vendors'
  documentation as read on 2026-09-23 and tested against sanitised fixtures; none has run against a
  live tenant. Desktop capture was tested with a fake `ffmpeg` / `whisper-cli` / `pactl`, and the
  ffmpeg filter graph against real ffmpeg 9.0.1 with synthetic inputs; no real meeting was
  recorded and no real whisper.cpp build was run. The Recall live smoke test did not run. The
  `meeting setup <provider>` self-test on a real machine is the first live check for each.
- **Zoom scope names** `user:read:user` and `meeting:read:meeting` were not confirmed in Zoom's
  docs (the recording scope was); confirm them in the Marketplace scope picker.
- **Private-source stage** (Stage B) was not run.
- **Publishing** (merge, tag, GitHub release, npm) is left to the owner, with the commands recorded
  in the hand-off.
