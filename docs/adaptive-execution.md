# Adaptive execution

How much workflow a piece of work gets, and why that is not the same question as how fast it
finishes.

## The principle

> Apply the minimum workflow that reaches the required confidence. Raise it with complexity,
> uncertainty, risk, blast radius, and irreversibility.

Not "go faster". A faster wrong answer is a regression, and the measure this release optimises
is **time to verified useful result** — a number that gets worse, not better, when verification
is skipped.

## Why this exists

The skills applied roughly the same ceremony to everything. In practice that meant:

- A request for read-only numbers from three systems was classified correctly, routed correctly,
  and then executed as three root-cause investigations. Each produced an evidence dossier over
  40 KB. What was wanted was a table that could be read in a meeting.
- Small delivery phases paid the full cost of a fresh agent, a destination brief, an evidence
  pack, a blackboard read, a `start-task`/`finish-task` lifecycle, and a review round. A phase
  rated `S` paid it twice. A sixteen-phase plan pays it at least sixteen times by design.
- One overscoped dispatch bundled four deliverables into a single brief and ran about an hour
  before being killed, having written nothing.

None of that was the rigour being wrong. It was the rigour being aimed at nothing. The
engineer/reviewer loop that caught two real bugs in a security default's own test coverage is
the same machinery — and there it was worth every minute.

## The three profiles

| | LIGHT | STANDARD | RIGOROUS |
| --- | --- | --- | --- |
| Delivery plan | no | no | yes |
| Phase decomposition | no | no | yes |
| Fresh-context dispatch | no | yes | yes |
| Independent review agent | no | yes | yes |
| Mutation testing | no | no | yes |
| Evidence depth | retained separately | cited inline | full |
| Dispatch budget | 1 | 3 | 6 |

**LIGHT** — a bounded read-only lookup, a small factual retrieval, a trivial deterministic
transformation, a very small independently verifiable change. No meaningful architectural
uncertainty.

**STANDARD** — ordinary engineering: investigate, implement, developer-test, review. Existing
specialist ownership and engineering discipline, without decomposing small coherent work into
phases. This is what work gets when nobody classified it.

**RIGOROUS** — security controls, cryptography, authentication and authorization, schema
migrations, production infrastructure, payment correctness, credential handling, anything that
can destroy data, anything spanning systems, anything irreversible. Fresh-context isolation,
independent review, stronger evidence, mutation testing. **Unchanged from before this release.**

## What LIGHT does not give up

```text
credential-safety     authorization-checks     bounded-reads
explicit-verification evidence-retained        safety-floor
```

That list is identical at all three profiles, and a test asserts it is identical, so it cannot
quietly grow a per-profile exception later. LIGHT buys less ceremony. It does not buy less
safety, and it does not buy an unverified answer — a lookup still has to check that the number
it returns is the number that was asked for.

## Choosing a profile

```bash
agent-skills execution-profile --reads-only --size S --uncertainty low \
    --blast-radius contained --verification-cost low
```

Deterministic on purpose: the same signals always give the same profile. A model deciding "this
feels small" is not a mechanism, cannot be tested, and cannot be argued with. This can.

Signals: `--reads-only` / `--mutates`, `--size`, `--uncertainty`, `--blast-radius`,
`--verification-cost`, `--shared-state`, `--dependencies`, `--reversible`, `--domain`.

### Escalation is a floor

Any of these forces RIGOROUS and nothing lowers it:

```text
security  crypto  auth  migration  infrastructure
payments  credentials  data-loss  cross-system
```

so does `--reversible no`, and so does a `production` or `cross-system` blast radius.

`--require` can raise a profile. It cannot lower a floor. Asking for LIGHT on a migration is
refused **out loud** — the decision says the request was not applied and why — rather than
honoured, and rather than silently ignored. Nobody is ever prevented from asking for *more*
rigour.

### Unstated is risky, not safe

A bare invocation returns STANDARD. Every relaxation condition must hold explicitly for LIGHT;
one unstated signal is enough to keep STANDARD. This asymmetry is deliberate: the cost of
accidentally being too careful is some wasted minutes, and the cost of accidentally being too
casual is a production incident nobody can attribute.

## Profiles in a phased plan

`delivery-planner` records the profile per phase and `delivery-runner` acts on it:

```yaml
execution_profile: LIGHT | STANDARD | RIGOROUS
fresh_context_required: true | false
independent_review_required: true | false
expected_effort_minutes: 20
parallel_safe: true | false
parallel_with: [04, 05]
mutation_targets: [src/api/handler.ts]
```

A LIGHT phase — a documentation fix, a test-name change, a small independently checkable edit —
runs without a fresh-agent handoff. A RIGOROUS phase — the interceptor, the probe suite, the
crypto relocation, the Liquibase changesets, the DB-role SQL — keeps everything it had.

Two rules protect this from drift:

- **The phase file wins, and the stronger wins.** When the index column and the phase file
  disagree, the higher profile applies. A stale roll-up table can never downgrade a phase.
- **An unrecognised profile is STANDARD.** A garbled column does not buy a discount.

The `Profile` and `Parallel` columns are **appended** to the index table, never inserted. Cells
are read positionally, so a plan written before this release parses unchanged and defaults to
STANDARD.

## Concurrency

Independent work may run at the same time. `plan-next` proposes a `parallel_group` only when
**every** one of these holds:

- no dependency edge in either direction;
- both phases marked `parallel_safe`;
- each lists the other in `parallel_with` — a one-sided claim means one phase was written
  without the other in mind, which is exactly when they collide;
- declared `mutation_targets` are disjoint **after normalisation** — the same path spelled
  differently (`./src/api`, `src/./api`) is one path, and a parent contains its children:
  `src/api` beside `src/api/handler.ts` is the same write.

A phase that does not declare `mutation_targets` is treated as writing everything. Silence is
not a safety claim. A target that cannot be proven independent — an absolute path, a path that
escapes the repository (`../elsewhere`), an empty value — disqualifies its phase from any group
rather than being compared as text.

A target is either a repository-relative path or a named resource (`db:orders`,
`port:8080`, `cache://sessions`). Paths overlap by containment; resources overlap by identity,
case-insensitively. Declare shared generated outputs, indexes, databases, and test resources as
targets too: a worktree isolates files, not the database both phases migrate.

Safe by construction: inspect CI, inspect Sentry, read AWS logs, gather database evidence — four
readers, four separate evidence files, no shared writes.

Never: two agents editing one file, a schema change beside its consumer, several writers to one
mutable artifact or cache.

Bounded at **3** concurrent phases. `AGENT_SKILLS_MAX_PARALLEL` can lower it and is clamped, not
trusted — a caller who exports 400 gets 3. Concurrency is an optimisation and never a
correctness requirement; if independence is uncertain, the work runs sequentially and nothing is
lost but time.

## The watchdog

```bash
agent-skills watchdog PROJ-1234 --budget-minutes 20
```

Verdicts: `continue`, `narrow`, `split`, `restart`, `stop` (exit `0`, `10`, `10`, `10`, `20`).

**It measures stagnation, not elapsed time.** A hard timeout kills the careful work along with
the stuck work and teaches everyone to pad their estimates. Work still writing milestones at
three times its budget is not stuck — it is bigger than someone thought, and the useful response
is to split it, not to shoot it.

The stall window is proportional to the budget, with a floor: `max(5, budget_minutes × 0.5)`
minutes of silence counts as stuck, and the first milestone gets `max(5, budget_minutes × 0.75)`.
So a 20-minute budget tolerates 10 minutes of silence and a 5-minute budget tolerates 5. A single
fixed window would either fire on careful work inside a long budget or never fire inside a short
one.

The first milestone gets a longer window than a mid-run gap, because an agent has to read the
brief and orient before it has anything worth recording.

There is no daemon and nothing polls. A supervisor process would bring orphaned children, stale
lock files, and signal handling into a release whose purpose is stability, and it could not
observe a sub-agent it did not spawn anyway. This is a pure function of what is already on disk.

## Incremental artifacts

The watchdog can only see what was written down, and an interrupted run can only be resumed from
what it left behind. So:

```bash
agent-skills blackboard progress PROJ-1234 --by issue-investigator \
    --kind hypothesis --note "connection pool exhaustion suspected"
```

Prefer initial understanding → checkpoint → evidence → artifact update → verification → final
artifact, over one long silence ending in a single write.

Kinds: `artifact`, `hypothesis`, `query`, `test`, `file`, `evidence`, `checkpoint`.

**Milestones only.** A checkpoint every few seconds is noise that hides the stall it was meant to
reveal. Any durable write — a fact, a decision, an artifact record — already counts as motion;
the explicit ledger is for progress that would otherwise leave no trace.

## Ownership does not change

Wamala remains the front door and the ownership dispatcher. It does not implement, review,
refine, or test anything — **including under LIGHT**, where the work looks small enough to just
do. What adapts is execution depth, not who owns the step.

```text
read-only numbers          -> specialist ownership -> LIGHT
ordinary defect            -> specialist           -> STANDARD
security-sensitive prod fix-> planner / runner      -> RIGOROUS
```

## Related

- [Skill boundaries](skill-boundaries.md) — who owns what. Unchanged by this page.
- [Review loops](review-loops.md) — the depth cap of two, and the loop bounds.
- [Output discipline](output-discipline.md) — the output contract that says what the human
  actually needs back.
- [Task blackboard](task-blackboard.md) — where the progress ledger lives.
- [The 1.0 contract](one-point-oh.md) — what is frozen.
