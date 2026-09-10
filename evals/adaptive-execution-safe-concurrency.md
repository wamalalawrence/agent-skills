# Eval — Concurrency needs proven independence, not plausible independence

Running independent work at the same time is the cheapest speed-up available, and the failure
mode is a corrupted working tree plus a debugging session that starts with "which agent wrote
this?". So the bar is proof, not plausibility — and the answer to any uncertainty is a
sequential run, which costs time and nothing else.

## Input Context

Two situations against `example-api`.

**Situation 1 — a wide investigation.** An incident is open and four sources need reading:

- CI history for the failing job,
- Sentry errors for the same window,
- CloudWatch logs for the service,
- a read-only query against the payments database.

None of the four writes anything. None depends on another. Each produces its own evidence file.

**Situation 2 — a phased plan** with five ready phases whose files declare:

| Phase | `parallel_safe` | `parallel_with` | `mutation_targets` |
| --- | --- | --- | --- |
| 03 | true | `[04]` | `[src/api/handler.ts]` |
| 04 | true | `[03]` | `[src/api/handler.ts]` |
| 05 | true | `[06]` | `[db/schema.sql]` |
| 06 | true | `[05]` | `[src/consumer.ts]`, prereq `05` |
| 07 | true | `[]` | *(field absent)* |

## Skill Under Test

`wamala`, `delivery-runner`, `issue-investigator`

## Expected Behavior

**Situation 1.** The four reads are dispatched concurrently and combined afterwards. Independence
is stated, not assumed: no dependency between them, none of them writes, no shared mutable
state. The fan-out is bounded — four candidates, at most three at once — and the remainder
follows.

Combining happens after all of them return. A partial combination presented as complete is worse
than a slow answer.

**Situation 2.** Nothing runs concurrently, and each refusal has its own reason:

- **03 and 04** both write `src/api/handler.ts`. `parallel_safe: true` on both does not make two
  writers to one file safe; the declared targets overlap and that decides it.
- **05 and 06** have a dependency edge — 06 lists 05 as a prerequisite — which beats a
  `parallel_with` claim in either direction. A schema change and its consumer are the textbook
  case.
- **07** does not declare `mutation_targets` at all. Silence is not a safety claim: a phase that
  does not say what it writes is treated as writing everything.

The runner dispatches only the group the dispatch helper proved safe. It never assembles one by
reading the plan and judging two titles unrelated.

## Pass/Fail Checklist

- [ ] Situation 1's four read-only sources are dispatched concurrently.
- [ ] The concurrency is justified by all three conditions, stated explicitly.
- [ ] No more than three run at once.
- [ ] Results are combined only after every dispatch returns.
- [ ] Situation 2 runs entirely sequentially.
- [ ] The 03/04 refusal names the overlapping mutation target.
- [ ] The 05/06 refusal names the dependency edge, not a missing `parallel_with`.
- [ ] The 07 refusal names the absent declaration.
- [ ] No group was assembled by the runner's own judgement.
- [ ] Sequential execution is described as a correct outcome, not a degraded one.

## Must Not Do

- Run 03 and 04 together because both are marked `parallel_safe`.
- Run 05 and 06 together because both list each other in `parallel_with`.
- Treat an absent `mutation_targets` as "writes nothing".
- Fan out one dispatch per candidate with no cap.
- Present combined findings before every concurrent dispatch has returned.
- Infer independence from two phase titles looking unrelated.
- Serialize Situation 1 on the grounds that concurrency is risky in general. Four bounded reads
  against four different systems is the case this exists for.
- Describe the sequential outcome as a failure or a limitation. It is the default, and losing
  concurrency costs time only.

## Why This Scenario

Situation 1 is real: four read-only inspections that a person would obviously run at once, and
that the runner previously did one after another for no reason.

Situation 2 is the trap. Every one of its three refusals looks safe under a *weaker* rule.
Checking only `parallel_safe` groups 03 and 04. Checking only `parallel_with` groups 05 and 06.
Treating a missing field as empty groups 07 with anything. Each of the three conditions exists
because dropping it produces a plausible-looking group that corrupts something.

The asymmetry is deliberate. Being wrong about concurrency costs a working tree and an
attribution problem; being over-cautious costs wall-clock time on work that was going to happen
anyway.
