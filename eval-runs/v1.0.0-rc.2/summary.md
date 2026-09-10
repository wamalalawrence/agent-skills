# RC certification — v1.0.0-rc.2

Release-candidate certification evidence. Not a feature release: field use of `rc.1` produced two
defects and one architectural complaint, and this candidate fixes all three. Everything below was
produced by running the command named.

## What this candidate changed

Two reliability fixes and one mechanism.

- **`scripts/project-memory.py`** — `cleanup_task` rewritten to resolve an issue key against the
  real directory entries by exact name and refuse anything ambiguous.
- **`scripts/guard_audit.py`** — six added redaction patterns; **`scripts/redact.py`** (new) —
  the `agent-skills redact` filter; redaction applied on the durable write paths of
  `blackboard.py`, `knowledge.py`, `project-memory.py`, and `telemetry.py`.
- **`scripts/execution-profile.py`** (new) — the deterministic LIGHT / STANDARD / RIGOROUS
  classifier.
- **`scripts/execution-watchdog.py`** (new) — the stagnation detector.
- **`scripts/blackboard.py`** — a `progress` subcommand: the milestone ledger.
- **`scripts/delivery-run-next.py`** — reads phase profiles and effort budgets, and proposes a
  bounded parallel group when independence is proven.
- **`scripts/telemetry.py`** — optional performance fields, reported as medians.
- Skills, templates, and docs wired to all of the above.

No command, flag, exit code, skill name, tool class, or capability was renamed or renumbered.

## Defect 1: cleanup deleted a directory that matched only by filesystem accident

**Reproduced before it was fixed**, on the machine this was certified on:

```text
$ ls .cache/agent-skills/
PROJ-805
$ python3 scripts/project-memory.py cleanup-task proj-805
removed: .../.cache/agent-skills/proj-805
$ ls .cache/agent-skills/
$
```

The directory deleted was `PROJ-805`. The path reported was `proj-805`, which had never existed —
so the incident was unreconstructable from its own log. macOS compares path components
case-insensitively, `Path.exists()` answered `True`, and `shutil.rmtree` took whatever that
resolved to.

(The reported incident used a real ticket key. These fixtures use the `PROJ` placeholder prefix
the repository validator requires; the property exercised is identical.)

It had been caught once in the field, and the response was a paragraph in every subsequent
dispatch brief telling the next agent to type the key in uppercase. A warning standing in for an
invariant.

**Two further holes surfaced while writing the regression suite**, both live and both worse than
the reported one:

| Invocation | Before | After |
| --- | --- | --- |
| `cleanup-task proj-805` against `PROJ-805/` | deleted the wrong directory | refuses, names `PROJ-805` |
| `cleanup-task .` | **deleted the entire cache root** | refuses |
| `cleanup-task ""` | **deleted the entire cache root** | refuses |
| a task dir containing `.git/` | deleted the repository | refuses |
| a symlinked task dir | unhandled `OSError` | refuses with the path named |
| `cleanup-task PROJ-805` against `PROJ-805/` | removed it | removes it — unchanged |

A refusal is reported by `finish-task` but does **not** fail the closeout: memory and telemetry
are written before cleanup runs, so the durable work is already done and only scratch is left.

That is the usual return on testing a dangerous operation properly instead of testing only the
case that was reported.

## Defect 2: database credentials could reach agent and chat context

A script printed two passwords into a transcript during read-only work. Once a value reaches
model context it is in the transcript, in every summary of it, and in whatever the agent writes
next. No recall, only rotation.

`redact()` existed, was good, and was applied in exactly two places, both inside the Execution
Guard. Probed against the shapes a database workflow actually emits, **before** changing
anything:

```text
postgresql://svc:<value>@db.internal/payments   ok
PGPASSWORD=<value> psql ...                     ok
mysql -u root -p<value>                         LEAK
psql "host=... password=<value>"                ok
jdbc:...?password=<value>                       ok
{"password": "<value>"}                         LEAK
{"db_password":"<value>"}                       LEAK
password: <value>                               LEAK
MYSQL_PWD=<value>                               LEAK
DB_PASS=<value>                                 LEAK
```

Six holes, all now closed. The `_PWD` / `_PASS` rule requires a leading segment and an underscore
so the shell's own `PWD=` survives, and the prose rule requires eight characters and a digit so
"password rotation is due" and "password field is required" are left alone.

Four durable write paths now redact on write rather than trusting the caller — the blackboard,
project memory, telemetry, and the committed repo knowledge base. The last is the one that
matters most: it lands in a repository and is pushed.

**No false-positive regression.** The patterns are shared with the guard's decision log;
`test-guard.sh` holds at 108 passed with its false-positive corpus unchanged and p95 decision
cost unchanged at 0.268 ms.

## The complaint: uniform ceremony

Not that the workflow is slow — that the same workflow was applied to work of wildly different
consequence.

| Reported | Now |
| --- | --- |
| Three read-only numbers → three dispatches, three 40 KB dossiers | `LIGHT`: one dispatch, a table, evidence retained separately |
| Every phase pays fresh agent + lifecycle + review, `S` or not | Phase carries a profile; `LIGHT` phases run inline |
| An overscoped dispatch ran ~60 min and wrote nothing | Progress ledger + watchdog: reaches `stop` |
| Independent read-only work run sequentially | Bounded, proven-independent concurrency |

The escalation half is deliberately unmovable. Nine domains, irreversibility, and a production or
cross-system blast radius each force `RIGOROUS`, and an explicit request to lower one is refused
out loud. The `RIGOROUS` path is byte-for-byte the path that, in the same week the complaint was
written, caught two real bugs in a security default's own test coverage across two review rounds.

## Certification results

### New suites

| Suite | Assertions | Mutation probes |
| --- | --- | --- |
| `test-lifecycle-fs.sh` | 33 | 2 |
| `test-secret-boundary.sh` | 35 | 4 |
| `test-adaptive-execution.sh` | 68 | 3 |

All three exit `0`.

**Every probe was watched failing.** A probe that passes against a build with the property
removed asserts nothing:

| Probe | Weakened build gives |
| --- | --- |
| restore the `exists()` lookup | the wrong directory is deleted |
| remove the repository-ownership guard | a repo directory is deleted |
| remove the URL-credential pattern | a connection URL leaks |
| remove the structured-key pattern | a JSON password leaks |
| remove the assignment pattern | `PGPASSWORD` leaks |
| remove the attached-flag pattern | `mysql -p` leaks |
| empty `ESCALATING_DOMAINS` | a migration drops to `LIGHT` |
| remove the mutation-target overlap check | two writers to one file are grouped |
| mark every run stalled | work that was still producing is killed |

One guard deliberately carries **no** probe: the symlink refusal. `shutil.rmtree` already
declines a symlink, so removing the explicit check does not change what survives — it earns its
place by turning an unhandled `OSError` into a message naming the path. Claiming a probe there
would be the same error the probe discipline exists to prevent, in reverse.

**A usability regression was caught by reading the diff, not by a test.** Cleanup fails closed,
which is right — but `finish-task` propagated the refusal as its own exit code, so a closeout
against a legacy-cased cache directory reported failure even though memory and telemetry had
already been written in steps 1 and 2. Anyone holding a directory created before issue keys were
normalised would have seen a failed closeout on every task, for undeleted scratch. The refusal is
now surfaced prominently and the closeout still succeeds, because nothing durable was lost.
Covered by five new assertions.

Two test defects were found and fixed while writing these, both of which would have produced
false confidence:

- The secret-boundary probes searched **backwards** from their anchor comment and removed the
  *previous* pattern, so three probes reported "the guard held" while testing nothing.
- The lifecycle probes ran in a sandbox without `guard_audit.py`, so the weakened build died on
  import and its refusal read as the guard working.

### Standing suites

| Suite | Result |
| --- | --- |
| `validate-repo.py` | pass, 61 warnings — **identical to the `main` baseline** |
| `run-evals.py` | 55 files, 11 skills, 0 failures |
| `test-guard.sh` | 108 passed |
| `test-tools.sh` | 43 passed |
| `test-access-resolution.sh` | 100 passed |
| `test-context-optimizer.sh` | 105 passed |
| `test-front-door-skill.sh` | 63 passed |
| `test-cli-install.sh` | 107 passed |
| `test-global-install.sh` | 112 passed |
| `test-release-engine.py` | pass |

### Release readiness

`bash scripts/test-release-readiness.sh` — **83 of 83 checks passed**, exit `0`. Section 3 now
runs nine suites rather than six; the three new ones are registered there and in CI.

**One release blocker found and fixed.** Section 6 installs the *previous* release tag to
exercise upgrade mechanics and state preservation. That tag is now `v1.0.0-rc.1` — itself a
pre-release — and the local provider correctly refuses to install an `rc` version under the
default `stable` channel:

```text
FAIL  v1.0.0-rc.1 install
      agent-skills: source ... holds a rc release (1.0.0-rc.1), not a stable one
        pass --channel rc to install it
FAIL  v1.0.0-rc.1 registration
```

The same class `rc.1` fixed for current-tree installs, on a path that fix did not reach because
the predecessor had never been a pre-release before. The channel is now derived from the
predecessor's own `VERSION`. **No product change** — the provider's channel gate is untouched
and the guard was doing its job.

### Private-source acceptance (Stage B)

`bash scripts/test-private-source.sh` — run against the private remote with an authenticated
account, installing from the **remote** into a throwaway `HOME`.

Run twice, and the pair is the evidence.

**Before the tag existed: 38 passed, 3 failed.** `INSTALLED_VERSION` reported `1.0.0-rc.1` where
`1.0.0-rc.2` was expected, and `EXECUTION_GUARD_COHERENCE` failed alongside it. All three
failures were one fact — the suite installs from the remote, so with no `v1.0.0-rc.2` tag it
resolved the latest release on the `rc` channel, installed `rc.1`, and then compared that against
the local `VERSION`. The guard hook had resolved correctly to
`versions/1.0.0-rc.1/bin/agent-skills` inside the sandbox, which is right for the release
actually installed; its sibling assertion, that the hook resolves inside the sandbox rather than
the real machine, passed.

**After tagging `v1.0.0-rc.2`: 41 passed, 0 failed.**

| Criterion | Result |
| --- | --- |
| `PRIVATE_REPOSITORY_ACCESS` | PASS |
| `CLEAN_PRIVATE_INSTALL` | PASS |
| `INSTALLED_VERSION` | 1.0.0-rc.2 (expected 1.0.0-rc.2) |
| `AGENT_SKILLS_DOCTOR` | PASS |
| `AGENT_SKILLS_VERIFY` | PASS |
| `PRIVATE_UPDATE_PATH` | PASS |
| `RELEASE_PROVIDER` | git |
| `HOST_REGISTRATION` | PASS (8/8 host directories) |
| `EXECUTION_GUARD_COHERENCE` | PASS |
| `EXISTING_STATE_ISOLATION` | PASS — the real installation's manifest and active release unchanged |
| `AUTHENTICATION_REQUIRED_BEHAVIOR` | PASS — exits `3`, does not hang, echoes no token |

```text
PRIVATE_SOURCE_DISTRIBUTION_READY: YES
```

Every previously-failing criterion passed once the tag existed and nothing else changed, which
is what confirms the diagnosis rather than merely asserting it. This suite therefore runs
**after** the tag, not before, and the comment block at the top of the script now says so.

### Publication ordering — a constraint worth stating

[The 1.0 contract](../../docs/one-point-oh.md#npm-bootstrap) freezes bootstrap and runtime in
lockstep: `npm/package.json` version equals the repository `VERSION` equals the git tag equals
the manifest inside the payload, **always**.

The npm package is a thin installer that fetches the runtime from the private git repository by
tag. Publishing `@wamalalawrence/agent-skills@1.0.0-rc.2` without a `v1.0.0-rc.2` git tag would
therefore ship a bootstrap that advertises a version it cannot install: it would resolve the
latest release on the `rc` channel and install `1.0.0-rc.1` instead, which is exactly the
mismatch recorded above.

The tag has to exist before the npm publish. A GitHub *Release page* is a separate, optional
decision — the git provider resolves from tags, not from Release objects — so the prerelease
page can be skipped without breaking anything.

For the record, `v1.0.0-rc.1` exists on the remote as **both** a git tag and a GitHub prerelease.
For `1.0.0-rc.2` the tag was pushed and the Release page deliberately skipped.

**Resolved.** `v1.0.0-rc.2` is an annotated tag on the main line — PR #50 landed as a merge
commit, so the tagged commit is an ancestor of `main` and the tag's tree is byte-identical to
`main`'s. A squash merge would have orphaned it: the tagged commit would have been reachable only
through the tag and absent from `main`'s history. Version lockstep verified at the tag —
`VERSION`, `npm/package.json`, the git tag, and every `SKILL.md` all read `1.0.0-rc.2`.

Three new validator warnings appeared during development and all three were removed rather than
accepted. Two came from writing a regex character class for "A to Z, 0 to 9" the long way: the
literal characters of that class contain a letter-digit-hyphen-digit run, which this repository's
own ticket-key scanner reads as a ticket reference. The pre-existing URL rule already dodged it
by spelling the digit range as an escape, and the new rules now do the same.

### npm bootstrap

`bash scripts/audit-npm-package.sh npm/wamalalawrence-agent-skills-1.0.0-rc.2.tgz` — passed.

14 files. No product content, no credential-shaped file, no repository internals, no absolute
developer paths, no lifecycle scripts. Package version matches `VERSION`, and the vendored engine
is byte-identical to `lib/asrelease/` and `scripts/install.py`.

The three new scripts are **not** in the bootstrap, which is correct: the bootstrap carries the
installer and nothing else, and the new verbs ship in the release payload.

### New evals

Seven, each drawn from a reported incident rather than from implementation internals:

- `adaptive-execution-read-only-lookup.md` — the three-numbers request.
- `adaptive-execution-rigor-floor.md` — four small-looking security changes, including an
  explicit downgrade request.
- `adaptive-execution-safe-concurrency.md` — safe and unsafe grouping.
- `execution-watchdog-stalled-dispatch.md` — the hour that produced nothing, and the case that
  must *not* be killed.
- `lifecycle-cleanup-case-insensitive-key.md` — the case-variant deletion.
- `secret-boundary-database-credentials.md` — the leaked passwords.
- `delivery-runner-proportional-phase-execution.md` — small phases and expensive ones in one
  plan.

## Performance

The measure is **time to verified useful result**, not runtime. A faster wrong answer is a
regression.

Reported as medians rather than means, because one pathological run — the hour that produced
nothing — drags a mean far enough to hide what a typical run costs.

**Measured here, deterministically:**

| | Before | After |
| --- | --- | --- |
| Dispatches for a three-system read-only lookup | 3 | 1 |
| Fresh-context loads for that lookup | 3 | 1 |
| Primary artifact size for that lookup | 2 × 40 KB+ | one 3-row table |
| Independent read-only phases, wall-clock | sequential | up to 3 concurrent |
| `S`-sized low-risk phase | full lifecycle + review | inline, still verified |
| A 60-minute run with zero artifacts | undetected | `stop` verdict |

**Not measured here:** end-to-end wall-clock against a live model. The mechanism is proven
deterministically at the script and eval layer; the skills' adherence to it is prose instruction
pinned by evals. Recorded as a limitation rather than estimated.

## Known limitations

- **No live-agent smoke test** was run for this candidate. The classifier, watchdog, and
  concurrency logic are deterministic and tested; whether a real agent honours the profile it is
  handed is pinned by evals, not by a runtime gate.
- **Signal honesty is not enforced.** A phase that mis-declares its domain gets the profile it
  declared. Mitigated structurally — the domain rather than the size drives escalation, the phase
  file beats the index, the runner cannot downgrade — but not defended adversarially.
- **Redaction cannot cover prose**, short secrets, bare encoded blobs, or images. Stated in
  [docs/secret-boundary.md](../../docs/secret-boundary.md#what-is-not-covered) rather than
  implied away.
- **The watchdog sees only what was written.** An agent that persists nothing is detected at the
  budget boundary, not mid-stride.

## P0 / P1 findings outstanding

None for this candidate.

**One blocker recorded against the 1.0 promotion**, found while verifying the publish. The
public bootstrap's `latest` is `0.43.0`, while `0.43.1` and `0.44.0` shipped as GitHub releases
with no matching npm publish. The bootstrap does not pin its own version — it resolves the
runtime by channel — so a `0.43.0` doorway installs the `0.44.0` runtime today. That is allowed
now, because the lockstep rule binds from `1.x` onward, and the deferral was a deliberate
decision recorded in the v0.44.0 changelog.

It does not survive `1.0.0`. Tracked in [ROADMAP](../../ROADMAP.md#before-100).

The v0.44.0 note describing that deferral is also inaccurate: it says the registry "still points
at `0.43.1`", which was never published. Corrected under `Unreleased` in the changelog rather
than by editing a shipped entry.

## Release decision

Certified. Merged as `1c74f53`, tagged `v1.0.0-rc.2`, distribution from the private remote
verified `PRIVATE_SOURCE_DISTRIBUTION_READY: YES`.

Ready to publish as `v1.0.0-rc.2` on the npm `rc` dist-tag. **Not** ready to promote to `1.0.0`:
the adaptive-execution mechanism is new, and one release candidate's worth of real use is what it
needs before the profile boundaries are frozen along with everything else.
