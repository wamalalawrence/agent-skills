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
BPF-805
$ python3 scripts/project-memory.py cleanup-task bpf-805
removed: .../.cache/agent-skills/bpf-805
$ ls .cache/agent-skills/
$
```

The directory deleted was `BPF-805`. The path reported was `bpf-805`, which had never existed —
so the incident was unreconstructable from its own log. macOS compares path components
case-insensitively, `Path.exists()` answered `True`, and `shutil.rmtree` took whatever that
resolved to.

It had been caught once in the field, and the response was a paragraph in every subsequent
dispatch brief telling the next agent to type the key in uppercase. A warning standing in for an
invariant.

**Two further holes surfaced while writing the regression suite**, both live and both worse than
the reported one:

| Invocation | Before | After |
| --- | --- | --- |
| `cleanup-task bpf-805` against `BPF-805/` | deleted the wrong directory | refuses, names `BPF-805` |
| `cleanup-task .` | **deleted the entire cache root** | refuses |
| `cleanup-task ""` | **deleted the entire cache root** | refuses |
| a task dir containing `.git/` | deleted the repository | refuses |
| a symlinked task dir | unhandled `OSError` | refuses with the path named |
| `cleanup-task PROJ-805` against `PROJ-805/` | removed it | removes it — unchanged |

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
| `test-lifecycle-fs.sh` | 28 | 2 |
| `test-secret-boundary.sh` | 33 | 4 |
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
| `test-release-engine.py` | pass |

Three new validator warnings appeared during development and all three were removed rather than
accepted. Two were the character class `A-Z0-9` containing the substring `Z0-9`, which this
repository's own ticket-key scanner reads as a ticket reference — the pre-existing URL rule
already dodged that with `\d`, and the new rules now do too.

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

None.

## Release decision

Ready to publish as `v1.0.0-rc.2` on the npm `rc` dist-tag. **Not** ready to promote to `1.0.0`:
the adaptive-execution mechanism is new, and one release candidate's worth of real use is what it
needs before the profile boundaries are frozen along with everything else.
