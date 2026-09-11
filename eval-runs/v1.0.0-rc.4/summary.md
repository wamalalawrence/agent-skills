# RC certification — v1.0.0-rc.4

Release-candidate certification evidence. This candidate exists because two independent pre-1.0
reviews ran every documented gate, saw all of them pass, and then found seven defects the gates
could not reach. Everything below was produced by running the command named.

## What this candidate changed

Seven defects, in four areas, plus the process gap that let all of them through.

- **`lib/asrelease/release.py`** — `require_version`, `is_version`, and `versions_equal`.
  `compare_versions` keeps its "unknown compares equal" behaviour and now documents why that makes
  it the wrong function for identity.
- **`lib/asrelease/layout.py`** — `safe_component`, `staging_path`, `installed_path`,
  `clear_manifest`, and `exclusive`, the per-install-root advisory lock.
- **`lib/asrelease/transaction.py`** — the entry manifest and the displaced release directory are
  transaction state; `_restore_displaced` and `_restore_manifest`; `_rollback` verifies before it
  claims; `install` and `rollback` hold the lock.
- **`lib/asrelease/providers/{git,local}.py`** — every version source validates before returning a
  `ReleaseRef`; `resolve_version` compares with `versions_equal`.
- **`lib/asrelease/archive.py`** — a payload entry that is itself a link out of the checkout is
  refused, as is a directory symlink that escapes.
- **`lib/install.sh`, `bin/agent-skills`** — `verify` re-hashes the active payload and returns `7`;
  `verify --explain-codes`.
- **`scripts/guard_parse.py`, `scripts/guard_rules.py`** — wrapper option values, argv re-quoting,
  inline shell-out extraction, the `cp`/`mv` home-path gap, and the dropped redirect target.
- **`scripts/context.py`** — the cache-reuse marker is reserved during `fill_budget`.
- **`scripts/durable.py`** (new) — atomic, lock-serialised writes; adopted by
  `project-memory.py`, `org-memory.py`, `knowledge.py`, `blackboard.py`.
- **`scripts/org-memory.py`** — redacts in `append_note`.
- **`scripts/guard_audit.py`** — quoted credential values, and the `mariadb` client family.
- **`scripts/install.py`** — an explicit `--channel` is recorded even when no release moves;
  `check-updates` refuses an uninstalled machine; the `apply:` hint is self-contained.
- **`scripts/{finish-task.sh,task-context.sh}`** — implicit task resolution refuses when more than
  one task is in flight; every structured flag is validated before anything is written.
- **`scripts/{delivery-run-next.py,promote-rules.py,tools.py,access.py}`** — an empty
  `mutation_targets` means "writes everything"; the placeholder prefix matches what the skeleton
  writes; three more bounded-read markers; `--field` no longer echoes the value.
- **`.github/workflows/ci.yml`** — `scripts/test-guard.sh` runs on every pull request.

No command, flag, exit code, skill name, tool class, or capability was renamed or renumbered.
`verify` now returns the code it always published for a case that previously returned `1`, which is
a correction toward the frozen contract rather than a change to it.

## The defects

Each one was reproduced against `1.0.0-rc.3` before being fixed, and each has a regression case
that fails without the fix.

### 1. A `VERSION` file could delete an arbitrary directory

```text
$ python3 -c "import sys; sys.path.insert(0,'lib')
> from asrelease.layout import Layout
> print(Layout(home='/tmp/as-home-probe').version_path('../../victim'))"
/tmp/victim
```

Nothing validated that a version was a version, and the value became a path in three places. The
first thing the transaction does with the staging path is `shutil.rmtree` it — before the payload
is verified — so a source whose `VERSION` read `../../victim` deleted `victim` and then reported
`staged release failed its self-test; nothing was activated`, which was no longer true.

Now refused twice over: at the boundary the string arrives from, and again by the path builder.

### 2. A malformed `--version` installed a real but different release

```text
$ resolve_version("definitely-not-a-version")
0.43.0
```

`compare_versions` reports an unparseable operand as *equal* so that a machine carrying a version
this build cannot read is treated as "nothing to do". Used as an identity test, that made every
typo match the first tag — on a fresh machine, the oldest release. `--version X` now installs X or
exits `2`.

### 3. Rollback reported success over a machine it had not restored

Two halves. After a verification failure:

```text
current  = 1.0.0
manifest = 1.1.0
```

and when the failing release carried the *same* version as the one installed:

```text
active marker = new-broken
saved marker  = old-known-good
reported      = rolled back to 1.0.0
```

An install changes four things; rollback restored two. The entry manifest and the displaced release
directory are now transaction state, and "rolled back" is printed only after the restored machine
verifies.

### 4. `verify` broke its frozen exit code and did not verify

Drift returned `1`, which [the 1.0 contract](../../docs/one-point-oh.md) says never appears; only a
missing manifest returned `7`. Separately, `verify` checked that `release.json` existed and never
re-hashed the tree, so `Installation verified.` was printed over an edited release.

### 5. The Execution Guard walked past wrapper commands

Every one of these reached `ALLOW` on `1.0.0-rc.3`, and `sudo rm -rf /` was correctly denied
throughout — the difference is entirely in the option handling:

| Command | rc.3 | rc.4 |
| --- | --- | --- |
| `sudo -u root rm -rf /` | ALLOW | DENY |
| `nice -n 10 rm -rf /` | ALLOW | DENY |
| `env -u FOO rm -rf /` | ALLOW | DENY |
| `find . -exec sh -c 'rm -rf /' \;` | ALLOW | DENY |
| `cp k ~/.ssh/authorized_keys` | ALLOW | DENY |
| `python3 -c 'import os; os.system("rm -rf /")'` | ALLOW | DENY |
| `sh < <(printf 'rm -rf /')` | ALLOW | ASK |

The benign counterparts still pass: `nice -n 19 make build`, `sudo -u postgres psql -c "select 1"`,
`find . -name '__pycache__' -exec rm -rf {} \;`, and
`python3 -c 'import subprocess; subprocess.run(["git","status"])'` are all ALLOW.

One reported case was **not** a defect. `ssh host sh -c 'rm -rf /'` is reported as ALLOW because
that is what it does: `ssh` joins its arguments with spaces and the remote shell re-parses, so the
remote command is `sh -c rm -rf /`, which runs `rm` with `-rf` as `$0`. The guard models that
correctly. `ssh host 'rm -rf /'` and `ssh host 'sh -c "rm -rf /"'` are both DENY.

### 6. A cached context pack failed permanently from its second run

```text
run 1 exit=0
run 2 exit=2  FAIL rendered pack is 2040 chars, over the 2000-char budget
run 3 exit=2  FAIL rendered pack is 2040 chars, over the 2000-char budget
```

`fill_budget` guarantees the fit; the `cache: reused` marker is appended afterwards, on a cache hit
only. Any pack within ~75 characters of its budget worked once and then failed forever — and the
documented 2,000-char floor makes that the normal case. After the fix, the same command at the same
budget: 1,919 chars fresh, 1,993 chars reused, exit `0` on every run.

### 7. Org memory kept credential values

It was the one durable tier with no redaction, and the widest-reaching: `start-task` prints it into
every later task in *every* project, and `--promote-to-org` feeds it from one project's notes. Two
redaction patterns were also weaker than the four-path table implied — a quoted value under a
credential key (`password: "…"`, the spelling every YAML file uses) and the `mariadb` name for the
`mysql` client.

## Verification

Every suite below was run on this candidate.

| Gate | Result | rc.3 |
| --- | --- | --- |
| `scripts/validate-repo.py` | pass, 63 warnings | pass, 61 warnings |
| `scripts/run-evals.py` | 56 files, 0 failures, 0 warnings | same |
| `scripts/test-guard.sh` | 116 passed, 0 failed — 266 corpus cases | 108 / 247 |
| `scripts/test-release-engine.py` | 31 passed, 0 failed | 21 |
| `scripts/test-cli-install.sh` | 146 passed, 0 failed | 135 |
| `scripts/test-global-install.sh` | 112 assertions | 112 |
| `scripts/test-access-resolution.sh` | 100 assertions | 100 |
| `scripts/test-front-door-skill.sh` | 63 assertions | 63 |
| `scripts/test-context-optimizer.sh` | 107 checks | 105 |
| `scripts/test-lifecycle-fs.sh` | 33 passed, 0 failed | 33 |
| `scripts/test-secret-boundary.sh` | 43 passed, 0 failed | 35 |
| `scripts/test-adaptive-execution.sh` | 68 passed, 0 failed | 68 |
| `scripts/test-tools.sh` | 43 passed, 0 failed | 40 |
| `scripts/test-release-readiness.sh` | see below | 83 checks |

The warning count rose by two because the new release-engine tests contain fixture hostnames
(`example.invalid`, `x-access-token`), which is what those warnings are for.

### Guard performance

Re-measured because this candidate changes `scripts/guard_parse.py`, which runs before every shell
command. `bash scripts/test-guard.sh --bench-only`:

```text
SAMPLES 1540
P50 0.104   P95 0.298   P99 0.429   MAX 0.559
COLD-CALL 74 ms (process startup included, per invocation)
```

Against rc.3: p50 `0.109`, p95 `0.330`, p99 `0.471`, max `1.954`, cold call `81` ms. The added work
— a value-flag lookup, an occasional second reading of a wrapper line, and a regex pass over inline
code bodies — is bounded and does not show above the noise. No benign case in the false-positive
corpus moved from `ALLOW` to `ASK`.

### Packaging

`bash scripts/audit-npm-package.sh` against `npm/wamalalawrence-agent-skills-1.0.0-rc.4.tgz`:

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
  "total_events": 2,
  "skills": {
    "software-engineer": { "completed": 1 },
    "code-review": { "completed": 1 }
  },
  "unknown_events": {},
  "performance": { "runs": 2, "dispatches": 0, "review_rounds": 0, "no_output_runs": 0 }
}
```

Two events, both `completed`, no `stopped` events and no `unknown_events`. The counters carry no
signal at this volume, and they drove nothing in this candidate — every defect here came from the
two external reviews, not from telemetry. Recorded because an unread counter that looks like
evidence is worse than no counter.

## What the new coverage asserts

The point of this candidate is not the seven fixes; it is that each one now has a test that fails
without it. Where a guarantee is a *negative* — nothing was deleted, no secret landed, no bypass
reached ALLOW — a mutation probe removes the guarantee and asserts the failure reappears, because a
check that never exercised the property passes whether or not the property holds.

- **Guard.** 19 new `REDTEAM` corpus cases: wrapper option values across seven wrappers, an
  unrecognised wrapper option, `find -exec` and `-execdir` running a nested shell, four inline
  shell-out spellings, three copy-over-credential-path cases, and the process-substitution input.
  Eight of them also run through the CLI, which is the path the hook uses. The benign counterparts
  are asserted alongside, so the wrapper handling cannot become a false-positive engine.
- **Release engine.** The traversal end to end — a pre-existing `victim/keepme.txt` must survive a
  failed install from a source whose `VERSION` is `../../victim`. `version_path` and `staging_path`
  refuse six shapes. Both halves of the rollback defect: the manifest is restored, and the
  known-good tree is identified by a marker file written into it rather than by its name. Lock
  contention across two `Layout` instances.
- **CLI install.** `verify` exits `7` on a tampered tree and on manifest drift, does not print
  `Installation verified`, and passes again once the tree is restored. The `apply:` hint is run
  verbatim through `eval` with nothing appended — anything the test has to add is something the
  user would have had to work out.
- **Context Optimizer.** Three consecutive runs at the 2,000-char floor, checking the exit code and
  the rendered size each time, plus a probe that removes the reservation and asserts the reused pack
  overruns.
- **Secret boundary.** Org memory across `note`, `promote`, and `--promote-to-org`; the two new
  redaction patterns; and a probe that removes org memory's `redact` call and asserts the value
  then lands on disk. The lifecycle-filesystem probes were also repaired: they sandbox a copy of
  `project-memory.py`, which now imports `durable`, and a probe whose sandbox cannot import reads as
  "the guard held" while testing nothing.

## The process finding

`scripts/test-guard.sh` was not in `ci.yml`. The suite that decides what a destructive command is
ran only from the local release-readiness script, so a change opening a bypass could be merged and
found at release time. Given that four of this candidate's fixes are in the guard, that was the one
suite most worth having on every pull request. It now runs there, early.

The broader finding is the one the reviews made by demonstration: a green suite is evidence about
its corpus, not about the code. Both reviews found real defects by executing the CLI with inputs
nobody had thought to write down. Every input they used is now written down.

## Recommendation

Publish `1.0.0-rc.4` to npm on the `rc` dist-tag. `latest` is untouched.

**The GitHub release page is deliberately deferred.** The tag `v1.0.0-rc.4` is pushed, and nothing
depends on the release page: `agent-skills` resolves releases from git tags, so a machine on the
`rc` line installs this candidate from the tag alone. npm is the only publication channel for it.
The outstanding item is the release page itself.

Not a promotion to `1.0.0`. This candidate corrects contract violations rather than adding
contracts, and all seven defects were found from outside the test suite by reviewers executing the
CLI with inputs nobody had written down. That is a reason to invite another adversarial pass before
freezing, not a reason to freeze.

## Security review

[docs/security-review-v1.0.0-rc.4.md](../../docs/security-review-v1.0.0-rc.4.md). Three of the
seven defects are security defects: a pre-verification delete primitive driven by an untrusted
version string, four Execution Guard bypasses, and credential retention in the durable tier with
the widest reach. Each threat is labelled probed, reasoned about, or unproven; the residual risks
and the five findings raised during the review are recorded there, including the one reported
bypass that turned out to be correct behaviour.
