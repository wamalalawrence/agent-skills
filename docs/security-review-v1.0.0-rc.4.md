# Security review — v1.0.0-rc.4 (release-candidate certification)

Follows [the v0.37.0 review](security-review-v0.37.0.md) as the shape. Each threat is labelled
**probed** (a test exercises it), **reasoned about** (argued from the design), or **unproven**.

This candidate is unusual: it exists because two independent reviews found seven defects *behind*
a fully green gate set, and three of the seven are security defects rather than correctness ones.
One was a destructive-write primitive in the installer. Four were bypasses of the Execution Guard,
which is the control the whole product's safety posture rests on. One was a credential-retention
hole in the memory tier with the widest reach. So the review below is mostly about controls that
were believed to hold and did not, and about why the tests that were supposed to prove them
proved something narrower.

## Scope of this review

`v1.0.0-rc.4` changes:

- **Release engine.** `lib/asrelease/release.py` (`require_version`, `is_version`,
  `versions_equal`), `lib/asrelease/layout.py` (`safe_component`, `staging_path`,
  `installed_path`, `clear_manifest`, `exclusive`), `lib/asrelease/transaction.py` (undo state
  and the lock), `lib/asrelease/archive.py` (top-level entry link check),
  `lib/asrelease/providers/{git,local}.py` (validation at every version source).
- **Verification.** `lib/install.sh` (`as_verify_payload_integrity`, the `7` return,
  `as_explain_exit_codes`), `bin/agent-skills` (`verify --explain-codes`).
- **Execution Guard.** `scripts/guard_parse.py` (wrapper option values, argv re-quoting, inline
  shell-out extraction, redirect-target capture), `scripts/guard_rules.py` (the `cp`/`mv`
  home-path gap), `scripts/guard_corpus.py` (19 new cases).
- **Secret boundary.** `scripts/guard_audit.py` (two patterns), `scripts/org-memory.py`
  (redaction), `scripts/durable.py` (new), and the three other durable tiers adopting it.
- **CLI and workflow.** `scripts/install.py`, `scripts/access.py`, `scripts/finish-task.sh`,
  `scripts/task-context.sh`, `scripts/delivery-run-next.py`, `scripts/promote-rules.py`,
  `scripts/tools.py`, `lib/tools/`.
- **CI.** `test-guard.sh` added to `.github/workflows/ci.yml`.

No change to the release provider's authentication strategies, tag resolution, archive extraction,
the payload self-test, the activation sequence itself, the downgrade guard, the Access Resolver,
the credential model, the installation layout, or the host-ownership predicates. The threat model
is the union of the prior reviews plus the surface below.

---

## Threat: a version string is used as a filesystem path and deletes something

**Probed.** `scripts/test-release-engine.py` — four tests, one of them end to end with a victim
directory on disk.

This one was live. Nothing between "read a `VERSION` file" and "pass a path to `shutil.rmtree`"
asked whether the version was a version:

```text
Layout(home='/tmp/as-home-probe').version_path('../../victim')  ->  /tmp/victim
```

`InstallTransaction.run` computes `cache/staging/<version>` and immediately
`shutil.rmtree`s it, *before* the payload is downloaded, verified, or self-tested. A source
directory whose `VERSION` file read `../../victim` therefore deleted `victim` and then reported
`staged release failed its self-test; nothing was activated` — a message that was false by the
time it was printed.

**Reachability.** The value comes from a directory the user pointed `--source` at, or from a
`VERSION` file inside a payload. Both are attacker-influenced in the realistic cases: a
`--source` tree fetched from anywhere, a payload from a compromised or substituted release. It is
a pre-authentication, pre-verification write primitive with a path chosen by the input, which is
the worst shape a filesystem bug can have.

**Control, and why there are two.** The fix is deliberately duplicated:

- `release.require_version` refuses non-semver at every boundary a version arrives from — the
  `--version` argument, a resolved git tag, a `VERSION` file — before the value is used for
  anything at all. `ReleaseRef.__init__` validates as a backstop, so a provider added later
  inherits the check rather than having to remember it.
- `Layout.safe_component` independently refuses anything that is not exactly one safe path
  component — no separator, no leading dot, no traversal — on the grounds that every path this
  class builds is eventually passed to `rmtree`, `rename`, or `symlink`, and that is not a
  guarantee worth delegating to a caller.

Two checks because the consequence of the first being bypassed is unrecoverable. The path-shape
check is deliberately wider than semver: a release directory that predates the check, or a
fixture name a test chose, still has to be addressable.

**Asserted.** A pre-existing `victim/keepme.txt` must survive a failed install from a source whose
`VERSION` is `../../victim`; `version_path` and `staging_path` each refuse six shapes;
`require_version` refuses seven.

---

## Threat: the installer selects a release the operator did not name

**Probed.** `scripts/test-release-engine.py` — "an invalid `--version` is a usage error, not the
nearest release".

`providers/git.py:resolve_version` matched tags with `compare_versions(found, wanted) == 0`.
`compare_versions` reports an unparseable operand as **equal**, by design, so that a machine
carrying a version this build cannot read is treated as "nothing to do" rather than as an upgrade
or a downgrade it cannot reason about. Used as an identity test, that inverted into: every
malformed `--version` matched the first tag examined.

```text
resolve_version("definitely-not-a-version")  ->  0.43.0
```

Tags are sorted ascending, so on a fresh machine the answer was the **oldest** available release —
the release with the most published vulnerabilities. That is the payload a downgrade attack wants
delivered, reachable through a typo and without touching the remote.

**Control.** `resolve_version` validates `wanted` first and then compares with `versions_equal`,
which never treats unknown as a match. `compare_versions` keeps its behaviour, and its docstring
now names the trap and points at the right function, because the fallback is correct for the
question it was written for.

**Note on the downgrade guard.** `_guard_downgrade` was not the control that failed here and is
unchanged. It compares the resolved version against the active one, so it would have caught this
on a machine that already had a newer release installed. On a fresh machine there is nothing to
compare against, which is exactly the case that was exploitable.

---

## Threat: a failed install leaves the machine in a state its own output denies

**Probed.** `scripts/test-release-engine.py` — three tests; `scripts/test-cli-install.sh` — the
`verify` cases.

An install changes four things. Rollback restored two.

```text
after a failed verification:     current = 1.0.0   install.json = 1.1.0
after a failed same-version repair:  active tree = the new broken one
                                     reported    = "rolled back to 1.0.0"
```

The second is the more serious. Re-installing the active version moves the running tree to
`versions/<v>.replaced` and puts the new one in its place. Re-activating `<v>` then re-activates
the **new, failing** tree under a name the operator trusts, and says it rolled back. An operator
who reads that stops investigating.

**Control.** The entry manifest and the displaced release directory are now transaction state,
recorded the moment they change and restored on every post-staging failure. The failed tree is
kept as `<v>.failed` rather than deleted, so the failure stays diagnosable. And "rolled back" is
printed only after `_verify_machine` passes on the restored machine; when it does not, the message
says the machine is mixed and names `doctor`. A rollback that cannot be verified is not reported
as a rollback.

**Asserted.** The known-good tree is identified in the test by a marker file written *into* it,
not by its directory name — the two are the same name, which is the whole point of the defect.

---

## Threat: `verify` reports a tampered installation as healthy

**Probed.** `scripts/test-cli-install.sh` — tamper, drift, and restore.

`verify` checked that `release.json` **existed**. The payload hash was recomputed at stage and at
rollback, never here. So editing any file in the active release and running `verify` printed
`Installation verified.`

This matters more than it looks. `verify` is the check the install transaction itself runs after
activation, the check `doctor` defers to, and the check a human runs when they suspect something.
Something that always says yes is worse than nothing, because it is treated as evidence.

**Control.** `as_verify_payload_integrity` re-hashes the active tree through the same
`release.verify_payload` the installer uses — one implementation, not a second that could drift —
and a mismatch is a FAIL. A missing `python3` or an unreachable engine returns a distinct code and
is reported as "could not re-check", never as tampering: a missing tool is not evidence of an
attack, and conflating the two teaches operators to ignore the loud case.

**Exit code.** Drift returned `1`, the shell's default, while
[the 1.0 contract](one-point-oh.md) freezes verification failure as `7` and states that `1` never
appears. A caller branching on `7` to run `doctor` silently did nothing. Now `7`, from a named
constant so the shell half cannot drift from `lib/asrelease/exits.py` again.

---

## Threat: the Execution Guard can be walked past

**Probed.** `scripts/guard_corpus.py` — 19 new `REDTEAM` cases; `scripts/test-guard.sh` — 8 of
them re-run through the CLI, the path the hook actually uses.

Four independent bypasses, all reaching `ALLOW` on `1.0.0-rc.3`. `sudo rm -rf /` was correctly
denied throughout, which is why none of this was visible.

| Command | rc.3 | rc.4 | Root cause |
| --- | --- | --- | --- |
| `sudo -u root rm -rf /` | ALLOW | DENY | the option loop skipped `-u` but not its value, so `root` became the inspected command |
| `nice -n 10 rm -rf /` | ALLOW | DENY | same |
| `env -u FOO rm -rf /` | ALLOW | DENY | same |
| `find . -exec sh -c 'rm -rf /' \;` | ALLOW | DENY | the `-exec` body was re-joined with spaces, losing quoting |
| `cp k ~/.ssh/authorized_keys` | ALLOW | DENY | the copy rule checked `SYSTEM_ROOT` only, not `HOME_ROOT` |
| `python3 -c 'import os; os.system("rm -rf /")'` | ALLOW | DENY | the destructive-pattern list named library calls, not shell-outs |
| `sh < <(printf 'rm -rf /')` | ALLOW | ASK | a pending redirect was dropped when its target was a substitution |

**Why the failure mode is the same in all four.** Each one turns a dangerous command into
something the rules have never heard of, and an unrecognised command matches no rule, and no
finding resolves to `ALLOW`. The guard has a parse-failure floor for input it *knows* it could not
read; it had no floor for input it read incorrectly and confidently.

**Controls.**

- **Wrapper option values.** Every passthrough wrapper now declares its value-taking flags. More
  importantly, an option table can never be complete, so an *unrecognised* option followed by a
  bare word is now read both ways and both readings are inspected. An unknown wrapper flag costs a
  redundant check instead of a bypass. `sudo --frobnicate zzz rm -rf /` is DENY.
- **Argv boundaries.** `find -exec` runs an argv with no shell, so its words are re-quoted before
  re-parsing. The `{}` stand-in expands to separate words so the path classifier still judges each
  target individually.
- **Inline shell-outs.** The command string is extracted from the call — including the
  `subprocess.run(["rm","-rf","/"])` list form — and handed back to the ordinary shell rules, so
  the verdict comes from the rule that knows what `rm -rf /` is, with the right path
  classification and the right message. Only literals in the call's own argument list are taken,
  bounded at eight per body; a constructed string is not recovered and remains an unresolved
  element.
- **Credential paths.** `HOME_ROOT` added to the copy branch. A credential path does not become
  safe because the bytes arrived by `cp` rather than by `>`.

**False positives.** The counter-corpus is asserted alongside, because an unusable guard gets
switched off: `nice -n 19 make build`, `sudo -u postgres psql -c "select 1"`,
`find . -name '__pycache__' -exec rm -rf {} \;`, `timeout 5 echo hi`, and
`python3 -c 'import subprocess; subprocess.run(["git","status"])'` are all still `ALLOW`. No
benign case moved from `ALLOW` to `ASK`.

**Performance.** `test-guard.sh --bench-only`: p50 `0.104` ms, p95 `0.298` ms, p99 `0.429` ms,
max `0.559` ms, cold call `74` ms. Unchanged against rc.3 (p50 `0.109`, p95 `0.330`). This hook
runs before every shell command, so a regression here would be a correctness problem; the extra
work is bounded and does not show.

**One reported case was not a defect.** `ssh host sh -c 'rm -rf /'` is `ALLOW`, correctly. `ssh`
concatenates its arguments with spaces and the remote shell re-parses, so the remote command is
literally `sh -c rm -rf /`, which runs `rm` with `-rf` as `$0` and deletes nothing. The parser
models `ssh` exactly this way. `ssh host 'rm -rf /'` and `ssh host 'sh -c "rm -rf /"'` are both
`DENY`. Changing the `ssh` join to preserve local quoting would have made the guard model a shell
that does not exist and would have regressed the case that works.

---

## Threat: a credential value comes to rest where it is read back forever

**Probed.** `scripts/test-secret-boundary.sh` — org memory across `note`, `promote`, and
`--promote-to-org`, plus a mutation probe that removes the `redact` call.

Org memory did not redact. Of the five durable tiers it is the one where that matters most:
`start-task` prints org memory into the starting context of **every later task in every project**,
and `outcome-recorder --promote-to-org` is a designed route for a value to travel out of the one
project that recorded it. This contradicted `docs/one-point-oh.md` ("No secret value ever
appears") and the four-path table in `docs/secret-boundary.md`, and it is the same failure class
the rc.2 changelog had already treated as a release blocker for the other four tiers.

**Control.** Redaction happens in `append_note`, the one choke point, so `note`, `promote`, and
every future writer inherit it rather than each remembering to ask — the same shape the other four
tiers use. Provenance strings are redacted too.

**Two pattern gaps closed.** A quoted value under a credential-shaped key
(`password: "…"`, `db_password = '…'`) survived, because the unquoted rule's character class
excluded the quote and so stopped at it — and that is the spelling every YAML file, `.env`, and
config dump uses. `mariadb -p…` survived because the attached-flag rule named only the `mysql`
spellings of what is the same client under a different name. Both now have probes.

**Probe discipline.** The org-memory probe removes the `redact` call rather than a pattern,
because "the code does not call the filter" is a different failure from "the filter has no pattern
for this", and it was the one that shipped. The pattern probes could not have caught it.

---

## Threat: two agents corrupt shared state

**Probed** for the installer (`test-release-engine.py`, lock contention) and for the memory tiers
(12 concurrent appends, all retained). **Reasoned about** for the crash window.

Two classes, same root: read-modify-write with no lock and no atomic replace.

- **Installer.** Two concurrent updates shared `cache/staging/<v>` and `versions/<v>.incoming`,
  and the moment one moved the running release aside was a moment the other could activate into
  the gap where `current` pointed at nothing. The "atomic, no mixed state" claim held for one
  process. `install`, `update`, and `rollback` now hold one advisory lock per install root. It is
  advisory deliberately: the kernel releases it when the descriptor closes, so a killed installer
  leaves no lock file to clear by hand and no state in which the installer is permanently wedged.
  A caller that cannot acquire it within the timeout is told nothing was changed.
- **Memory tiers.** `Path.write_text` truncates and then writes. Two agents appending a bullet
  each kept one; a crash mid-write left JSON no reader could parse, which reads as an
  uninitialised tier. All five paths now go through `scripts/durable.py`: temporary file plus
  `os.replace`, under an advisory lock covering the whole read-modify-write. The lock there is
  best-effort by design — a notebook that refuses to record a fact because another agent is
  recording one is worse than an occasional lost bullet, and the atomic write still guarantees the
  file is never torn.

**Residual.** The installer lock does not cover `uninstall`, which is shell. A concurrent
`uninstall` and `update` remains possible and is not defended. Recorded rather than claimed.

---

## Threat: a source tree reaches outside itself during packaging

**Probed.** `scripts/test-release-engine.py` — "a local source entry that links outside the
checkout is refused".

`copy_payload` checked for escaping symlinks on files it walked past, but resolved each top-level
payload entry with `os.path.isdir` first. A checkout containing `skills -> ~/.ssh` therefore had
those files walked and copied into the installed release, from where the payload hash would
happily certify them as part of the product. Reachable through `--provider local`, which is the
dev-install path and the path `setup.init` delegates to.

**Control.** Every payload entry is resolved and checked before it is read. A directory symlink
inside the tree that escapes the checkout is now an error rather than being silently dropped from
the payload — silence there meant either a release missing content it expected, or a checkout
reaching outside itself, and neither should be quiet.

---

## Threat: a value is echoed by the error that rejects it

**Reasoned about**, with the change confined to a message.

`access.py` answered a malformed `--field my-key=<secret>` by printing the whole `name=value`
pair. That puts the value in the terminal, in the scrollback, and in anything capturing the
session — the exact exposure `--secret-field` exists to prevent. And the likeliest reason the name
is malformed is that somebody is passing a credential through the wrong flag, so the error path
was disproportionately likely to be carrying one. Only the name is shown now, truncated.

---

## Threat: a phase runs beside another that writes the same files

**Probed.** `scripts/test-adaptive-execution.sh` (68 checks, unchanged count, existing probes).

The parallel-dispatch gate tested `"mutation_targets" not in head` and then took
`head.get("mutation_targets") or []`. The phase template ships `mutation_targets: []`, so the
default state of every phase was "declares an empty write set" — read as "writes nothing", and
therefore "safe beside anything". The documented rule, in three places including this project's
own rc.2 security review, is the opposite: a phase that does not say what it writes is treated as
writing everything.

**Control.** An empty list is now the absence of a claim, not a claim of emptiness. The template
comment says so.

---

## Threat: the safety-critical suite is not run

**Fixed as process.** `scripts/test-guard.sh` was not in `.github/workflows/ci.yml`. The suite
that decides what a destructive command is ran only from `test-release-readiness.sh`, which is
local and deliberately not in CI because it performs full installs. So a change opening a guard
bypass could be merged and found at release time, or not at all.

Given that four of this candidate's fixes are in the guard, this was the single most valuable
suite to have on every pull request. It now runs there, and early in the job, because a guard
regression should stop everything after it.

---

## Findings raised during this review

1. **The reported `ssh host sh -c '…'` bypass is not one.** Resolution: behaviour is correct;
   documented in the changelog and in the eval-run summary with the reasoning, and pinned by the
   two `ssh` cases that *are* denied. No code change.
2. **`compare_versions` returning `0` for unknown is correct and was being misused.** Resolution:
   the function keeps its behaviour, its docstring names the trap, and a separate
   `versions_equal` exists for identity. Changing `compare_versions` itself would have broken the
   downgrade guard and `check-updates` on a machine whose version this build cannot read.
3. **`check-updates` on an uninstalled machine reported `up-to-date` and exited `0`**, because
   `"unknown"` compares equal to everything. A fleet monitor built on that reports bare machines
   as healthy. Resolution: `not-installed`, exit `2`.
4. **The lifecycle-filesystem mutation probes were passing vacuously** after this change. They
   sandbox a copy of `project-memory.py`, which now imports `durable`; without it the weakened
   build died on import, refused everything, and the probe read as "the guard held" while testing
   nothing. The suite's own comment warns about exactly this. Resolution: the sandbox copies
   `durable.py`; both probes verified failing-when-weakened again.
5. **The `apply:` hint could describe a command it did not run.** It dropped `--repo`, `--source`,
   and `--provider`, so a check against a private mirror printed a command that would update from
   the public default. Resolution: every flag that changed which release was examined travels with
   the hint, shell-quoted; the test now runs the hint verbatim through `eval` with nothing
   appended.

## Residual risks

- **`uninstall` is outside the installer lock.** Concurrent `uninstall` and `update` is
  undefended. The blast radius is one machine's install root, and both operations are re-runnable.
- **A constructed shell string inside inline code is not recovered.** `os.system(cmd)` where `cmd`
  is built at runtime remains an unresolved element rather than a decided one. The guard reports
  it as unresolved; it does not evaluate the program. Deliberate — interpreting arbitrary code is
  not a job a pre-execution hook can do safely or in 0.3 ms.
- **The wrapper option tables are still enumerations.** The both-readings fallback means an
  unknown flag is not a bypass, but a wrapper whose *entire* calling convention is unlike the
  ones here could still be modelled wrongly. New wrappers should arrive with corpus cases.
- **Signal honesty is still not enforced**, unchanged from rc.2: a phase that mis-declares its
  `mutation_targets` gets the concurrency eligibility it declared. The controls are structural,
  not adversarial.
- **Advisory locks are advisory.** A process that ignores them is not stopped. The atomic replace
  underneath means the worst case is a lost update, not a corrupt file.

## Behaviours pinned by tests so they cannot drift from this document

- A traversing version cannot delete anything (`test-release-engine.py`, with a victim directory).
- `--version X` installs X or exits `2`, never a neighbour.
- A post-staging failure restores `current`, `install.json`, host registrations, and the displaced
  release directory, and does not claim a rollback it has not verified.
- `verify` exits `7` on drift and on tampering, and does not print `Installation verified` over
  either.
- All 19 guard bypasses stay denied, and 8 benign counterparts stay allowed.
- Org memory retains no credential value through any of its three write routes, and the guarantee
  fails when the `redact` call is removed.
- A cached context pack stays inside its budget on every run, and overruns when the reservation is
  removed.
- Two concurrent installer operations cannot interleave.

## Verdict

The three security defects in this candidate — the delete primitive, the guard bypasses, and the
unredacted org memory — were all reachable on `1.0.0-rc.3` and are all closed, each with a test
that fails without the fix. The controls that failed did so in the same way: they were asserted
against corpora that did not contain the shape that breaks them. That is a statement about the
evidence, not about the design, and it is the reason this candidate does not recommend promotion
to `1.0.0` on its own authority. The right next step is another adversarial pass by something that
did not write this code.
