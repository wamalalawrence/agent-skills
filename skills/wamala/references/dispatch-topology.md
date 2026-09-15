# Dispatch Topology

Wamala can open a fresh-context agent. Whether **that** agent can open one is a separate fact,
and two parts of the design quietly depend on it:

- [`delivery-runner`](../../delivery-runner/SKILL.md) is nothing but nested dispatch. Dispatched
  as a step, it has to open one fresh agent per phase from inside its own.
- An executor's **independent** review. `software-engineer` calls `code-reviewer` at the end of
  its step. That review is independent only when it runs in a context that did not write the
  change, which means the executor has to open one.

On many hosts neither is possible. A sub-agent tool is often registered only at the top level
of a session. An external agent CLI can be missing, unauthenticated, or blocked by the sandbox.
In one real run the runner stopped before `phase-01`, correctly, because it could not open
anything. Meanwhile every phase set `independent_review_required: true`, and every one came back
with its review run inline. Five commits landed with no independent review, and nothing noticed.

This file is the fix: decide dispatch depth up front, and when nesting is unavailable, run the
same dispatch model from the one depth where dispatch works.

## The probe

Decide once per run, before routing anything that depends on it, and record the answer on the
blackboard and in the run preamble:

```text
nested_dispatch: available | unavailable | unknown
```

**`available` needs evidence.** Any one of:

- A dispatched agent in this run reported a sub-agent or task tool in its own tool list, by
  name, and said it could call it.
- A dispatched agent ran an agent CLI non-interactively from inside its own context, and the
  CLI returned. The capability report showing the CLI installed is not enough, because
  installed is not signed in.
- The user said so in this conversation, for this host.

**`unavailable`** when a probe said so, or a dispatched step came back reporting that it could
not dispatch.

**`unknown` is treated as `unavailable`.** The costs are lopsided. Assume nesting wrongly and
the run stops before its first phase, after a dispatch has already been spent. Assume no nesting
wrongly and Wamala dispatches phases itself, which is the same work done from one level up.

Do not spend a dispatch on the probe. Put it in the first step Wamala was going to dispatch
anyway:

```text
Before starting, report in one line whether you could open a fresh-context agent
from where you are — name the tool or the CLI — WITHOUT opening one. Then do the step.
```

Record the answer from that step's final message. It is the one fact Wamala takes from chat
rather than from an artifact, because it describes the host rather than the work.

## What the answer changes

| `nested_dispatch` | A phased plan is ready | Review of an implementation step |
| --- | --- | --- |
| `available` | dispatch `delivery-runner` and stop | inside the executor's step, as designed |
| `unavailable` | **plan mode**: Wamala dispatches each phase | **sibling review**: Wamala dispatches `code-reviewer` after the step |

Nothing else changes: not the owners, the safety floor, the verification rules, or the depth cap.

## Plan mode

When a plan is ready and nesting is unavailable, Wamala runs the delivery-runner loop at its own
depth. It is the same dispatch model the runner uses, run from the only place it works, so the
runner's contract governs it. It is not a looser copy.

Wamala reads two runner reference files. Neither is an executor skill, so reading them adds no
review layer and leaves the depth cap alone:

- [`run-loop-checklist.md`](../../delivery-runner/references/run-loop-checklist.md) — the
  per-iteration self-check, followed as written. Its lifecycle item is Wamala's own
  `start-task`, and its dispatch-mechanism item is already answered by the probe.
- [`handoff-prompt-template.md`](../../delivery-runner/references/handoff-prompt-template.md) —
  the phase brief, extended with the [run preamble](./run-preamble-template.md) pointer and the
  carried-forward block.

Per phase:

1. `agent-skills plan-next <cache-dir>/<work-key>`. Act on `action`, exactly as the runner does.
2. Verify the phase owner's `SKILL.md` frontmatter, then safety-screen the phase file.
3. Build the brief from the runner's template. Reference the preamble, and paste
   `phase.prerequisite_context` into it under **Carried forward** (see below).
4. Dispatch one fresh agent. Concurrency comes only from `plan-next`'s `parallel_group`.
5. Verify from the index and the checkpoint, never from the chat, using the runner's rules.
6. Apply the [blocked-step split](#blocked-by-the-plan-or-by-the-world). If the phase's review
   ran in the writer's context, schedule a [sibling review](#independent-review).
7. Record one line and loop.

**Confirm before the first dispatch.** A plan-mode run opens many agents. The user agrees to a
multi-phase run once, up front, and Wamala says how many phases that is.

**The cap.** The six-dispatch cap exists for ad-hoc chains. In plan mode the runner's cap
applies instead: `total_phases + retry_budget`, plus one dispatch per review checkpoint and one
per plan amendment. The no-progress guard is unchanged. If a pointer recurs past its retry budget
with no state change, stop.

**Context.** Wamala's own context holds the pointer, the preamble path, and one line per phase.
If it is carrying a phase's findings forward in its own head, it is doing what the evidence pack
exists to do. Read the pack instead.

## Carried forward

Each executor writes `follow_up_context` for the phases after it. That is half a contract, and
the other half is reading it. `plan-next` now returns what every prerequisite recorded, redacted:

```json
"prerequisite_context": {
  "evidence_pack": ".cache/agent-skills/PROJ-1234/evidence-pack.yml",
  "phases": [
    {"id": "phase-02", "state": "done", "completion_summary": "...",
     "follow_up_context": ["The Tailwind scanner reads comments; never write a class name in one"],
     "artifacts": ["..."]}
  ],
  "missing": ["phase-01"]
}
```

Put every `follow_up_context` line in the brief, verbatim, under a heading naming the phase that
wrote it. Nothing gets summarised. Every prerequisite listed in `missing` recorded nothing to carry
forward, so tell the phase to read that prerequisite's artifacts rather than assume it had nothing
to say. Outside a plan, do the same by hand from the previous step's evidence pack. The runner
does the same when it dispatches.

A line that binds **every** later step, such as a measurement recipe or a trap in the repository,
belongs in the run preamble. Wamala moves it there once, so it stops being repeated per brief.

## Blocked by the plan, or by the world

A step that comes back `blocked` stops the chain. That rule stands, with one owner-correct
exception:

| The artifact shows | Route |
| --- | --- |
| A missing dependency, access, evidence, or a failing check | Stop. Surface it. No retry. |
| The step's own criterion cannot hold: the artifact names it, the contradicting evidence, and why | `plan-amendment` → `delivery-planner`; resume from the amended pointer |
| The same criterion, amended, contradicted again | Stop. Two wrong plans in a row is a question for the user. |

Contradictions are read from the artifact, never inferred from a phase that was merely hard.

## Independent review

A review is independent when the context that judges a change is not the one that wrote it.
When an executor cannot open a fresh context, its review runs inline. Record that honestly, and
let Wamala restore independence one level up.

**What the step records.** `code-reviewer` writes `review.independence` in the evidence pack:
`fresh-context` when it ran in an agent that did not write the diff, and `same-context` when it
did not. An absent field on an evidence pack written before `1.1.0` reads as `same-context`.
Unproven independence is not independence.

**When Wamala dispatches a sibling review.** All of these hold:

- The step implemented something, and its work was committed.
- Review was required: the phase says `independent_review_required: true`, or the step ran at
  `STANDARD` or `RIGOROUS`.
- `review.independence` is not `fresh-context`.

**Cadence.** After every such step at `RIGOROUS`. At `STANDARD`, batch it: once every three
steps, and always before anything is pushed or a PR is opened, whichever comes first. The
review covers the committed range since the last independent review. Record that range as
`<base-sha>..<head-sha>` in the brief and the run report.

**Shape.** One `code-reviewer` dispatch, owner verified, with the diff range, the phases it
covers, their acceptance criteria as pointers, and the evidence pack paths. The reviewer is the
root of its own chain, so `code-reviewer` → `issue-investigator` is depth two. The sibling review
never overlaps the executor's own loop, because it runs after the step has returned.

**Findings.** They go to the evidence pack's `review` block with `independence: fresh-context`.
A `blocker` stops the run. Wamala dispatches `software-engineer` once, with the findings as
input, then re-dispatches `code-reviewer` once to check only those blockers. That is the
[universal one-revision bound](../../../docs/review-loops.md#universal-loop-bounds). Anything
still open goes to the user.

**What Wamala never does** is mark the review satisfied because the step said it reviewed its
own work. The run report says, per step, which review satisfied the requirement, or that it is
still owed and why.
