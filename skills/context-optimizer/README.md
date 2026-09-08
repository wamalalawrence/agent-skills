# context-optimizer

Turns an enormous input into a small, task-specific, traceable context pack before an agent reads
it.

Use it when the **evidence** is the problem rather than the task: a multi-million-line log, an
800-table schema dump, a generated OpenAPI document, a 40,000-line diff, a CI log where one compile
error caused four hundred later failures.

```text
Use Context Optimizer to extract what matters from this production log for the
payment failure on transaction 84721.
```

## What it does

Inspection is deterministic and local first — no model sees the whole file. Then selection is driven
by the engineering question you are actually asking, so two questions about the same log produce two
different packs.

Every fragment carries provenance. Every omission is reported with the command that reverses it. The
character budget is honoured exactly.

## What it does not do

It produces evidence; it does not reach conclusions. Root cause belongs to
[`issue-investigator`](../software-engineer/skills/issue-investigator/SKILL.md), the fix to
[`software-engineer`](../software-engineer/SKILL.md), and the verdict on a diff to
[`code-reviewer`](../software-engineer/skills/code-reviewer/SKILL.md).

It is read-only against every input, and it never claims a dollar figure — it reports characters.

## The runtime is available to every skill

Other skills do not invoke this skill to shrink a file; they call the runtime directly:

```bash
agent-skills context check <path>     # exit 10 means: past the threshold
agent-skills context inspect <path>   # metadata and structure
agent-skills context pack <path> --brief "<the question>"
```

This skill exists for the cases where the judgement is the work: choosing the brief, deciding
whether the pack answered the question, and escalating when it did not.

## Read next

- [`SKILL.md`](SKILL.md) — the workflow, stopping conditions, and output contract.
- [`docs/context-optimizer.md`](../../docs/context-optimizer.md) — the capability, the shared
  large-input rule every skill inherits, the threshold and its measurement, and the safety model.
- [`references/strategies.md`](references/strategies.md) — per-input-type behaviour.
- [`references/context-pack-format.md`](references/context-pack-format.md) — the pack schema.
- [`docs/examples/context-optimizer-large-log.md`](../../docs/examples/context-optimizer-large-log.md) —
  a worked run.
