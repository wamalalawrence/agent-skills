# Security review — v1.0.0-rc.2 (release-candidate certification)

Follows [the v0.37.0 review](security-review-v0.37.0.md) as the shape. Each threat is labelled
**probed** (a test exercises it), **reasoned about** (argued from the design), or **unproven**.

This candidate does two things a security review has to look at hard. It closes a real
credential-disclosure path, and it introduces a mechanism that *reduces* workflow depth — which
is a security-relevant change even though nothing about it is a security feature. A system that
decides how careful to be is a system that can decide wrongly, quietly.

## Scope of this review

`v1.0.0-rc.2` changes: `scripts/project-memory.py` (`cleanup_task` rewritten);
`scripts/guard_audit.py` (six added redaction patterns); new `scripts/redact.py`,
`scripts/execution-profile.py`, `scripts/execution-watchdog.py`; redaction applied on the write
paths of `scripts/blackboard.py`, `scripts/knowledge.py`, `scripts/project-memory.py`, and
`scripts/telemetry.py`; a `progress` subcommand on the blackboard; profile, effort, and
concurrency fields in `scripts/delivery-run-next.py`; three new CLI verbs in `bin/agent-skills`;
and the corresponding skill and documentation changes.

No change to the release provider, the archive-safety or integrity checks, the Access Resolver,
the Execution Guard decision engine, the credential model, or the installation layout. The threat
model is the union of the prior reviews plus the two new surfaces below.

## Threat: a credential reaches model context, a transcript, or a committed file

**Probed.** `scripts/test-secret-boundary.sh` — 33 assertions, 4 mutation probes.

This is the threat that motivated the release. It was not hypothetical: a script printed two
database passwords into a chat during read-only work.

The boundary is stated in [docs/secret-boundary.md](secret-boundary.md), and the primary control
is unchanged and is **not** redaction — it is that service access resolves through the Access
Resolver and a credential never goes on a command line. Redaction is defence in depth for when
that discipline fails, which it did.

Probing the existing `redact()` against the shapes a database workflow actually emits found six
holes, all of which leaked before this release:

```text
mysql -u root -p<value>      attached short flag
{"password": "<value>"}      quoted JSON value
{"db_password":"<value>"}    prefixed JSON key name
password: <value>            colon spelling; only `=` was covered
MYSQL_PWD=<value>            abbreviated variable name
DB_PASS=<value>              abbreviated variable name
```

All six now redact, and the four mutation probes confirm each pattern is load-bearing by deleting
it and watching the matching case leak.

Four durable write paths redact on write rather than trusting the caller — the blackboard,
project memory, telemetry, and the committed repo knowledge base. The last is the worst case and
the reason this is not left to discipline: it lands in a repository, survives a fresh clone, and
is pushed. A credential written there is a credential published.

**Two properties are asserted together**, because either alone is useless: the value is gone, and
enough shape survives that the failure is still debuggable. `PGPASSWORD=[redacted] psql -h
db.internal -U svc` still names the variable, host, and user. An over-eager scrubber that emits
an opaque hash gets bypassed by the next person under time pressure, and then there is no control
at all.

**No false-positive regression.** The patterns are shared with the Execution Guard's decision
log, so widening them risks the guard's usability, and an unusable guard gets switched off.
`test-guard.sh` holds at 108 passed with its false-positive corpus unchanged, and p95 decision
cost is unchanged at 0.268 ms.

## Threat: adaptive execution silently reduces rigour on work that needed it

**Probed.** `scripts/test-adaptive-execution.sh` — 68 assertions, 3 mutation probes.

The new surface, and the one with a genuinely silent failure mode. Nothing looks wrong when a
security fix runs at the depth meant for a documentation change: the output is confident,
correctly formatted, and less true.

Three structural defences:

1. **Escalation is unconditional and evaluated first.** Nine domains (`security`, `crypto`,
   `auth`, `migration`, `infrastructure`, `payments`, `credentials`, `data-loss`,
   `cross-system`), irreversibility, and a production or cross-system blast radius each force
   `RIGOROUS`. Asserted for every domain individually, each given the full set of
   LIGHT-qualifying signals alongside — so no escalation can be argued down by surrounding
   context.
2. **A request cannot lower a floor.** `--require LIGHT` on a migration is refused, and the
   refusal is *stated in the output*. Silent refusal would be its own defect: a user who asked
   for something and was not told they did not get it will assume they did.
3. **Unstated is risky, not safe.** A bare invocation returns `STANDARD`. `LIGHT` requires seven
   conditions to hold explicitly, and an unrecognised profile in a plan index falls back to
   `STANDARD` rather than to `LIGHT` — a garbled column must never buy a discount.

**The safety invariants do not vary.** `credential-safety`, `authorization-checks`,
`bounded-reads`, `explicit-verification`, `evidence-retained`, and `safety-floor` are one list,
and the suite asserts it is byte-identical at all three profiles. This is the assertion that
decides whether the whole feature was worth building: `LIGHT` buys less ceremony, not less
safety, and a per-profile safety list is exactly what would rot.

Mutation probe 1 empties the escalation table and confirms a migration then drops to `LIGHT`,
proving the floor tests are not passing vacuously.

**Determinism** is a security property here, not a nicety. The same signals always produce the
same profile and the same reasons, in any argument order — so a profile can be reproduced from a
plan file, tested, and disputed. A model deciding "this feels small" could not be any of those.

**Reasoned about, not probed:** whether an agent supplies *honest* signals. A caller that
declares a migration as `--reads-only --size S` gets `LIGHT`, because the classifier believes its
inputs. The mitigations are that the domain flag is the escalating signal rather than the size
flags, that the phase file rather than the summary index is authoritative, and that the runner
cannot downgrade what the plan declared. A deliberately mis-declared phase is not defended
against and is not claimed to be.

## Threat: recursive cleanup destroys data it was not aimed at

**Probed.** `scripts/test-lifecycle-fs.sh` — 28 assertions, 2 mutation probes.

Recursive deletion driven by a user-supplied string is the most dangerous thing this project
does, and it went wrong: a lowercase issue key deleted the uppercase key's directory, because
`Path.exists()` matches case-insensitively on macOS and the code deleted whatever that resolved
to. The log then named a path that had never existed, so the incident was unreconstructable from
its own record.

The fix resolves the key against real directory entries by exact name, and refuses anything
ambiguous while naming the directory it declined to touch. Fail-closed throughout: a refused
cleanup removes nothing and reports nothing removed.

Writing the regression suite found two further live holes, both worse than the reported one:

- `cleanup-task .` and `cleanup-task ""` deleted the **entire cache root** — every task's
  scratch in one call.
- A directory containing a git repository was deleted recursively, so a misconfigured cache root
  took the user's work with it.

Both now refuse. So does a symlinked task directory; `shutil.rmtree` already declined that one,
but with an unhandled `OSError` rather than a message naming the path, and the explicit guard
carries no mutation probe precisely because removing it does not change what survives. Saying so
is the point — a probe that passes against a weakened build proves nothing, and claiming one here
would be the same error in reverse.

Reserved names (`_projects`, `_org`) were already protected by the leading-underscore check and
still are, now with an explicit named check as well.

## Threat: concurrency corrupts shared state

**Probed.** `scripts/test-adaptive-execution.sh` §concurrency.

Parallel dispatch is new and is the classic source of unattributable corruption. A group forms
only when **all** hold: no dependency edge in either direction, both phases `parallel_safe`,
mutual `parallel_with`, and disjoint declared `mutation_targets`.

Each condition has a test that fails without it, because each one alone admits a plausible-looking
unsafe group: checking only `parallel_safe` groups two writers to the same file; checking only
`parallel_with` groups a schema change with its consumer; treating a missing `mutation_targets`
as empty groups a phase that never said what it writes. Mutation probe 2 removes the overlap
check and confirms two writers to one file are then grouped.

**A phase that does not declare `mutation_targets` is treated as writing everything.** Silence is
not a safety claim.

Bounded at 3. `AGENT_SKILLS_MAX_PARALLEL` is clamped rather than trusted — a caller exporting 400
gets 3, so an environment variable cannot turn a plan into a fork bomb against the user's own
test runner. Concurrency is never a correctness requirement; the sequential path remains the
fallback everywhere and losing concurrency costs time only.

## Threat: the watchdog becomes a denial of service against its own work

**Probed.** `scripts/test-adaptive-execution.sh` §stagnation.

A supervisor that kills work is a way to lose work. Three properties keep it from being one:

- **It measures stagnation, not elapsed time.** Work still writing milestones at eight times its
  budget reaches `split`, never `stop` — asserted directly. A hard timeout would have destroyed
  exactly the careful work the rigour exists to protect. Mutation probe 3 forces every run to
  read as stalled and confirms still-producing work is then killed.
- **It kills nothing.** It is a read-only pure function returning a verdict; the caller decides.
  There is no daemon, no polling, no child process, and so no orphan, stale lock, or signal
  handling introduced into a release whose purpose is stability.
- **The first milestone gets a longer window** than a mid-run gap, so it does not interrupt an
  agent that is still orienting. A watchdog that interrupts working agents is disabled within a
  week, and a disabled watchdog catches nothing.

## Threat: a new CLI verb widens the attack surface

**Reasoned about.** Three verbs were added: `redact`, `execution-profile`, `watchdog`.

All three are read-only with respect to the machine. `redact` reads stdin or named files and
writes to stdout. `execution-profile` reads only its own arguments and touches no filesystem.
`watchdog` reads one blackboard JSON file and writes nothing. None takes a credential, none
performs network I/O, none executes anything, and none writes outside what it was already given.

`redact --check` deliberately reports line *numbers* and never the line, because the line is what
holds the secret — a checker that prints its findings has moved the leak rather than found it.

## Residual risks

- **Redaction cannot cover prose.** "The password is the project name" is not redactable without
  redacting English. Only `password <value>` where the value is at least eight characters and
  contains a digit is caught. Documented in
  [secret-boundary.md](secret-boundary.md#what-is-not-covered) rather than implied away.
- **Short or encoded secrets** with no surrounding key name are not distinguishable from ordinary
  text.
- **Anything the agent read before a redaction point** cannot be retracted by anything
  downstream. This is why the primary control is not holding the value at all, and why redaction
  is described as defence in depth everywhere it appears.
- **Signal honesty is not enforced.** A phase that mis-declares its domain or its
  `mutation_targets` gets the profile and the concurrency eligibility it declared. The controls
  are structural (the phase file is authoritative, the runner cannot downgrade, escalation is
  driven by the domain rather than the size) and not adversarial.
- **Images are not scanned.** A credential in a screenshot is not text and is not caught.

## What this review does not establish

- That real agents follow the profile the classifier returns. The classifier is deterministic and
  tested; the skills' *adherence* to it is prose instruction, pinned by evals rather than by a
  runtime gate. Seven evals cover it, but no eval was executed against a live model in this
  release — the same limitation the standing evals carry, recorded again here rather than
  quietly.
- That the six added redaction patterns are exhaustive. They cover every shape found by probing
  the tools in use plus the reported incident. The next unfamiliar client will emit a seventh
  shape, and the intended response is a new case in the suite with a mutation probe, not a
  broader pattern.
- That concurrency is safe under a hostile plan. It is safe under an honest one, bounded under
  any one, and refuses under an ambiguous one.
