# Eval: Context Optimizer keeps the evidence, drops the bulk

Four scenarios about the property that matters: the pack contains what the question needed.
Compression ratio is not the thing being judged. **A 99.9% reduction that removes the root cause is
a failure**, and two of these scenarios are designed so a ratio-maximising agent fails them.

## Skill Under Test

`context-optimizer`, with handoffs to `issue-investigator` and `software-engineer`.

## Setup

A repository with a production log at `var/log/settlement.log`: 4.7 MB, 80,632 lines. Roughly
80,000 of them are identical health-check lines. Buried in it:

- one `ERROR` naming transaction `84721`, with a merchant id and a failure reason;
- a six-frame stack trace with a `Caused by:` chain immediately after it;
- 400 identical downstream `ERROR` lines caused by that failure;
- 40 near-identical `INFO [startup] initialised bean ... in NNNNms` lines;
- one `WARN` saying startup took 88,000 ms;
- a token-shaped value on the line before the error.

## Scenario 1 — the root cause survives

The user asks: *"Why did payment settlement fail for transaction 84721?"*

### Expected agent behavior

- Runs `agent-skills context inspect` **before** packing, and reports the threshold verdict.
- Writes a brief containing `84721`. A brief of "investigate the log" is a fail: the identifier is
  the strongest selection signal available and it was sitting in the request.
- Never reads the file whole, and never falls back to reading it whole when the first pack
  disappoints.
- The pack it builds contains the `ERROR` line, the exception class, and **all six trace frames
  including the `Caused by:` chain and the `... 14 more`**. A truncated trace is a fail: it reads as
  though the frames were not there.
- Reports findings with a line range: `var/log/settlement.log:60179-60198`. A paraphrase with no
  locator is a fail — a downstream reader cannot verify one.
- Does **not** paste the pack into chat. It names the pack id and path and reports the findings.

### Fail modes this catches

- Reading the whole log "just to be sure", then reporting from memory.
- A brief built from the ticket title, ignoring the identifier the user supplied.
- Reporting the exception class without the frames, so nobody can see what called what.
- Celebrating "99.96% reduction" as the headline instead of the finding.

## Scenario 2 — the noise does not survive

Same log, same brief.

### Expected agent behavior

- The 80,000 health-check lines appear as a **count**, not as content. If the agent's output or the
  pack it quotes contains dozens of `GET /health 200 OK` lines, the compression did not happen.
- The 400 downstream errors are reported as a cascade with their count, and the agent says in its
  own words that they are one finding rather than 400 problems.
- The agent distinguishes the first failure from its consequences, and says which is which.

## Scenario 3 — a different question, a different pack

The same log, a different request: *"Why is startup taking 90 seconds and which beans are slow?"*

### Expected agent behavior

- The pack is **materially different**. The bean-timing lines are now evidence, and the settlement
  failure is at most background.
- The agent notices that 40 near-identical timing lines were sampled rather than quoted in full,
  and reads the sample count before concluding anything about how many beans are slow.
- The agent does not reuse the previous pack. A different question needs a different pack, and the
  pack id makes that visible.

### Fail modes this catches

- Reusing a pack built for another brief because "it is the same file".
- Concluding "only four beans are slow" from a four-line sample when the omission record says 40
  lines shared that shape.

## Scenario 4 — the budget kept something out

The same log, brief as scenario 1, but the agent is given a 2,000-character budget.

### Expected agent behavior

- The pack still contains the failure. Zero fragments plus a long footer explaining why is a fail.
- The agent reads the `budget:` omission record and **restates it in its own output**. Leaving it
  inside the pack invites the reader to assume completeness.
- Escalation uses the path the pack names — `--budget-chars` or `context expand` — not a wholesale
  read.
- After at most three escalation rounds the agent stops and says what it searched, rather than
  packing a fourth time.

## Pass criteria

| No. | Criterion |
| --- | --- |
| 1 | `context inspect` ran before `context pack`, and the threshold verdict is reported. |
| 2 | The brief contains the identifier from the request, or its absence is stated as a limitation. |
| 3 | The `ERROR` line, exception class, and the complete trace including `Caused by:` are present. |
| 4 | Repeated noise appears as a count; the cascade is named as one finding, not 400. |
| 5 | Every reported finding cites a line range or a structural path. |
| 6 | The pack is not pasted into chat; its id and path are named instead. |
| 7 | The startup question produces a different pack, and the sampling is read before concluding. |
| 8 | Under budget pressure the pack still holds evidence, and the exclusion is restated. |
| 9 | Escalation uses `--budget-chars` or `context expand`, never a wholesale read. |
| 10 | No dollar figure is claimed anywhere. Characters are reported. |

## Why this eval exists

The failure this guards against is not "the agent read too much". It is the opposite and worse
failure: an agent that produced a very small pack, reported confidently from it, and never noticed
that the answer was in the 99.96% it dropped. The omission records exist so that mistake is
visible; this eval checks the agent actually reads them.
