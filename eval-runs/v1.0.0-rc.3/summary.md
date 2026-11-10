# RC certification — v1.0.0-rc.3

Release-candidate certification evidence. One defect, in two parts, both in how the installer
decides which release to install. Everything below was produced by running the command named.

## What this candidate changed

- **`scripts/install.py`** — `resolve_channel` consults the install manifest when no `--channel`
  is given; new `recorded_channel` helper; `check-updates` resolves the same way and its `apply:`
  hint carries the flag when the check overrode the machine's line; `requested_channel` added to
  `check-updates --json`; `provider` reports the followed line.
- **`lib/asrelease/transaction.py`** — writes `follow_channel`, the release line the machine
  follows, separately from `channel`, the channel the installed version belongs to. Rollback
  carries it forward rather than choosing one.
- **`lib/asrelease/release.py`** — `FOLLOWABLE_CHANNELS`, the closed set resolution accepts.
- **`scripts/doctor.sh`** — reports the followed line when it differs from the installed
  version's channel; `follow_channel` in `doctor --json`.
- Docs, changelog, and the security review.

No command, flag, exit code, skill name, tool class, or capability was renamed or renumbered.
Three optional fields were added. Nothing was removed.

## The defect

Reported by the maintainer after publishing `1.0.0-rc.2` and being unable to stay on it.

The first half of the report was not a defect. `agent-skills update` returned `0.44.0` on a
machine whose `install.json` recorded `channel: stable`, and the frozen contract says `stable`
never offers a pre-release. That was the guard working.

The defect was everything after. With `channel: rc` recorded, on the machine this was certified
on:

```text
$ agent-skills check-updates
agent-skills update check
  installed: 1.0.0-rc.2
  latest   : 0.44.0  (stable channel, via git)
  status   : ahead
```

An rc machine, told it was ahead of its own line. `resolve_channel` returned `stable` whenever
`--channel` was absent and contained no reference to the manifest; the recorded channel was read
only for display, at `scripts/install.py:246` and `:259`.

Three consequences, all shipped in `0.44.0` and `1.0.0-rc.2`:

1. `check-updates --channel rc` printed `apply: agent-skills update` — a command that provably
   would not perform the update it had just described, because the hint dropped the flag.
2. An rc machine was never told a newer candidate existed. `ahead`, indefinitely.
3. A bare `update` resolved `0.44.0`, an older release. The downgrade guard at
   `lib/asrelease/transaction.py:266` refused it and suggested `--allow-downgrade`. Nothing
   broke, but taking that advice would have moved an RC tester backwards off the line they were
   testing. (Reasoned from the code, not probed on the reporter's machine — running it there
   would have downgraded them if the guard had not held.)

## The second half, found while writing the regression test

The manifest's `channel` field records `channel_of(version)` — the channel the installed
*version* belongs to, not the line the machine follows. Those diverge exactly where the superset
rule applies: a machine following `rc` that takes the stable release superseding its candidate
installs a `stable` version, records `stable`, and is never offered a candidate again.

So the obvious fix — read `channel` from the manifest — would have reintroduced the same class of
bug one release later, and silently. `follow_channel` is a separate field for a separate
question.

This is the case the channel design exists to support, stated in
[docs/versioning.md](../../docs/versioning.md#release-channels): *"a machine tracking release
candidates must still be offered the stable release that supersedes the last candidate, or it
would be pinned to pre-releases forever."* The mechanism meant to prevent being pinned to
pre-releases was ejecting people from the line instead.

## Validation

`scripts/test-cli-install.sh` section 15 — 28 assertions over a real git remote publishing
`2.0.0-rc.1`, `2.0.0-rc.2`, `2.0.0`, `2.0.1-rc.1` in sequence.

Against the code as shipped in `rc.2`, before any fix:

```text
15. The release line a machine follows survives its next update
  ok    installing with --channel rc succeeds
  ok    the candidate is active
  FAIL  the manifest records the release line the machine follows   [expected 'rc', got '']
  FAIL  a bare check-updates offers the next candidate to an rc machine   [expected '10', got '4']
  FAIL  it names the candidate
  FAIL  the apply hint is the command that will do it   [expected 'agent-skills update', got '']
  FAIL  a bare update on an rc machine succeeds   [expected '0', got '4']
  FAIL  a bare update moves an rc machine along its own line   [expected '2.0.0-rc.2', got '2.0.0-rc.1']
  FAIL  taking a stable release does not move the machine off the rc line   [expected 'rc', got '']
  FAIL  the next candidate after a stable release is still offered   [expected '10', got '0']
  FAIL  rollback leaves the followed line alone   [expected 'rc', got '']
  ...
16 passed, 10 failed
```

After:

```text
28 passed, 0 failed
```

**Mutation probe.** A copy of the engine with the manifest lookup removed from `resolve_channel`
is built inside the suite and run against the same manifest. It must fail to offer the candidate,
and the engine under test must offer it — both asserted, in that order, so a probe that proves
nothing cannot pass quietly.

**The hint is executed.** The `apply:` line printed by `check-updates` is captured from stdout,
run verbatim, and the resulting version asserted. The class of "the tool suggests a command that
does something else" is closed for this path by execution rather than by inspection.

**Fail-closed, asserted in both directions.** A manifest holding a value that is not a channel
resolves to `stable` and cannot name a candidate. A stable machine is offered none and has none
named in its output. An install written before `follow_channel` existed still resolves `rc`.

## Certification results

| Suite | Result |
| --- | --- |
| `python3 scripts/validate-repo.py` | exit 0, 61 warnings — the `main` baseline, unchanged |
| `bash scripts/test-release-readiness.sh` | 83/83, exit 0 |
| `bash scripts/test-cli-install.sh` | 135 passed, 0 failed |
| `bash scripts/test-guard.sh` | 108 passed, 0 failed |
| `bash scripts/test-tools.sh` | 43 passed, 0 failed |
| `bash scripts/test-access-resolution.sh` | 100 assertions, pass |
| `bash scripts/test-context-optimizer.sh` | 105 checks, pass |
| `bash scripts/test-global-install.sh` | 112 assertions, pass |
| `bash scripts/test-front-door-skill.sh` | 63 assertions, pass |
| `python3 scripts/test-release-engine.py` | 21 passed, 0 failed |
| `bash scripts/test-lifecycle-fs.sh` | `LIFECYCLE_FS: PASS` |
| `bash scripts/test-secret-boundary.sh` | `SECRET_BOUNDARY: PASS` |
| `bash scripts/test-adaptive-execution.sh` | `ADAPTIVE_EXECUTION: PASS` |
| `python3 scripts/run-evals.py` | 56 files, 11 skills known, 0 failures, 0 warnings |
| `bash scripts/audit-npm-package.sh` | pass, 14 files |
| `bash scripts/test-private-source.sh` | `PRIVATE_SOURCE_DISTRIBUTION_READY: YES`, 41/0 (post-tag) |

`test-private-source.sh` is the one suite that cannot pass before the tag exists: it installs
from the real remote, so until `v1.0.0-rc.3` is pushed it resolves `v1.0.0-rc.2` and reports the
same three version-mismatch failures `rc.2` recorded at the same point. Run post-tag it is 41/0.

Telemetry report, verbatim, from a base with no recorded events:

```json
{
  "total_events": 0,
  "skills": {},
  "unknown_events": {},
  "performance": {
    "runs": 0,
    "median_minutes_to_first_artifact": null,
    "median_minutes_to_verified_result": null,
    "profiles": {},
    "dispatches": 0,
    "context_loads": 0,
    "review_rounds": 0,
    "parallel_runs": 0,
    "no_output_runs": 0,
    "dispatches_per_run": null,
    "context_loads_per_run": null
  }
}
```

## Security review

[docs/security-review-v1.0.0-rc.3.md](../../docs/security-review-v1.0.0-rc.3.md). The change adds
a decision input to the installer sourced from a file on disk, which is a supply-chain surface
and is reviewed as one. Summary: the accepted set is closed to three literal values, resolution
fails closed to the narrowest, the widening it can perform is only to a line the machine itself
opted into, the provider's channel gate is untouched, and the downgrade guard is unchanged — with
one path removed on which correct-looking tooling advised a downgrade.

## Known limitations

- Section 15 uses a local git fixture. Behaviour against the real private release source under an
  authenticated fetch is covered by `test-private-source.sh`, not by this section.
- A user who hand-edits `install.json` opts themselves into candidates without a flag. This is
  equivalent to a command they can already run, and requires write access to their own install
  root.

## Disposition

Publish `1.0.0-rc.3` to npm on the `rc` dist-tag. `latest` is untouched. Not a promotion to
`1.0.0`; the stable-line npm blocker in [ROADMAP](../../ROADMAP.md#previously-v100) is unchanged by
this candidate.
