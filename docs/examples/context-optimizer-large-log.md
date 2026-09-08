# Example: Context Optimizer on a large production log

One good-shape run. Not exhaustive — see [the eval](../../evals/context-optimizer-large-log-evidence.md)
for the contrastive cases.

## Input

```text
Use Context Optimizer on var/log/settlement.log — why did payment settlement fail
for transaction 84721?
```

`var/log/settlement.log` is 4.7 MB across 80,632 lines. About 80,000 of those are identical
health-check lines.

## What the agent runs

```bash
agent-skills start-task --skill context-optimizer

agent-skills context inspect var/log/settlement.log
```

```text
== context inspect: settlement.log ==
  path:            var/log/settlement.log
  strategy:        log
  size:            4,775,858 chars / 80,632 lines / 4.6 MiB
  encoding:        utf-8
  sha256:          0fabddc64fec3a76...
  over threshold:  YES (threshold 65,536 chars / 2,000 lines)
  structure:
    severities:     ERROR 401, WARN 1, INFO 80,162, DEBUG 61
    timestamps:     iso-8601 (99% of lines)
    stack traces:   1
    error classes:  SettlementTimeoutException 1, SocketTimeoutException 1
    repeated lines: 4 group(s), 80,181 line(s); top 80,000x

-- past the threshold: build a pack rather than reading this whole file.
```

The inspection cost under a second and no model saw the file. Two things are already decided: this
needs a pack, and there is exactly **one** stack trace in 80,632 lines, which is almost certainly
the answer.

```bash
agent-skills context pack var/log/settlement.log \
  --brief "Why did payment settlement fail for transaction 84721?" \
  --budget-chars 6000
```

```text
== context pack: settlement.log ==
  pack:        2c487a4f7afbce73 (strategy log, runtime 0.41.0)
  budget:      6,000 chars

## Fragments

-- f1  lines 60179-60198  (score 55)  brief term match, ERROR, first failure in the
   input, stack trace  [first-failure, credential-redacted]
2026-09-08T16:40:01.000Z INFO  [settle] starting settlement batch b-9910
2026-09-08T16:40:02.000Z INFO  [settle] acquired provider session
  token=[REDACTED:github-token] for batch b-9910
2026-09-08T16:40:03.000Z ERROR [settle] settlement failed for transaction 84721
  merchant=m-4410 amount=120.55 reason=provider-timeout
com.example.settle.SettlementTimeoutException: provider did not respond in 30000ms
    at com.example.settle.ProviderClient.await(ProviderClient.java:212)
    at com.example.settle.SettlementService.settle(SettlementService.java:88)
    at com.example.settle.BatchRunner.run(BatchRunner.java:41)
Caused by: java.net.SocketTimeoutException: Read timed out
    ... 14 more

## Omissions

- cascade: 400 occurrences of '... downstream ledger write aborted ...' after the first
    -> the first occurrence is retained; the repeats are the same finding
- collapsed-repeats: 80,000x 'GET /health 200 OK' (lines 1-80591)

## Metrics

  selected:    2,043 chars in 2 fragment(s)
  source:      4,775,858 chars
  omitted:     99.96% of the source
  redactions:  1 (github-token) — values removed, evidence kept
```

## Good-shape output

```markdown
## Pack

- Lifecycle: start-task=ran; finish-task=ran; memory=updated; skill=context-optimizer@0.41.0
- Source: var/log/settlement.log — 4,775,858 chars / 80,632 lines
- Brief: Why did payment settlement fail for transaction 84721?
- Strategy: log
- Pack: 2c487a4f7afbce73 — 2,043 chars in 2 fragments, 99.96% omitted
- Budget: 6,000 chars

## What The Evidence Shows

- **Transaction 84721 failed on a provider read timeout, not on validation.**
  settlement.log:60181 — `reason=provider-timeout`, and the trace at :60183-60189 shows
  `ProviderClient.await` waiting 30,000 ms before `SocketTimeoutException`.
- **The 400 subsequent errors are one consequence, not 400 problems.**
  settlement.log:60192-60591 — every one reads `batch b-9910 already marked failed`, so
  they are the batch refusing to re-enter a failed state.
- **A credential-shaped value is being written to this log.** settlement.log:60180 —
  redacted in the pack, but it is in the file. Worth raising regardless of this ticket.

## What Was Omitted

- 80,000 health-check lines, collapsed to a count.
- 399 of the 400 downstream errors, reported as a cascade. The first is included.
- Nothing relevant was excluded by the budget: 2,043 of 6,000 characters were used.

## Limitations

This pack establishes what the log says, not why the provider timed out — that is on the
provider side and this file has no visibility into it. Root cause belongs to
issue-investigator; hand over pack 2c487a4f7afbce73 rather than this summary, because it
carries the line ranges and this text does not.
```

## What makes it good shape

- **Inspection came first**, and it decided the strategy and the budget rather than guessing them.
- **The brief carried the identifier** the user supplied. `84721` is the reason `f1` scored 55
  instead of 29.
- **The trace is whole.** Six frames, the `Caused by:` chain, and the `... 14 more`. A trace cut in
  the middle reads as though those frames did not exist.
- **Every claim has a line number.** The next agent can verify each one; a paraphrase cannot be
  verified.
- **The cascade is named as one finding.** "400 errors" and "one error with 400 consequences" lead
  to completely different work.
- **The pack is not pasted into chat.** Its id and path are named. Re-rendering it in the transcript
  would spend the context the pack exists to save.
- **The omissions are restated** in the agent's own words, including the fact that the budget
  excluded nothing.
- **The credential is reported as a finding** without reproducing the value.
- **No dollar figure.** 99.96% fewer characters is measured; a cost saving is not.

## What would make it bad shape

- Reading the log whole "to be safe", then reporting from memory.
- A brief of "investigate settlement failures", ignoring the id in the request.
- Leading with "99.96% context reduction". The ratio is a measurement, not the finding.
- Reporting 401 errors, because the cascade was counted as distinct problems.
- Pasting the pack into chat under a `## Context Pack` heading.
- Concluding the provider is misconfigured. This file does not say that, and the output would be
  presenting an inference as evidence.
