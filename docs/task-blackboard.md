# Task blackboard

The task blackboard is the **single canonical** working-memory file for one
agent task. It is the shared whiteboard every skill writes to and reads from
while the task is in flight, so handoffs between skills do not silently lose
context or force the next skill to re-derive what the previous one already
knew.

It is per-task scratch. It lives under the per-task evidence-pack directory
and is cleaned up alongside that directory when the task completes.

## Layout

```
${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills}/
  <issue-key>/
    blackboard.json     # the shared working memory for this task
    ...                 # other per-task evidence files
```

## Schema

```json
{
  "issue_key": "ABC-123",
  "project":   "acme-checkout",
  "created_at": "2026-05-22T09:14:01Z",
  "updated_at": "2026-05-22T09:31:18Z",
  "skill_versions": {
    "software-engineer": "0.33.0",
    "code-reviewer":     "0.33.0"
  },
  "facts":       [{"at": "...", "by": "software-engineer", "text": "..."}],
  "assumptions": [{"at": "...", "by": "issue-investigator", "text": "..."}],
  "unknowns":    [{"at": "...", "by": "code-reviewer", "text": "..."}],
  "decisions":   [{"at": "...", "by": "software-engineer", "text": "..."}],
  "artifacts":   [{"at": "...", "by": "software-engineer",
                   "path": ".../PR.md", "kind": "pr-body", "note": ""}],
  "handoffs":    [{"at": "...", "from": "software-engineer",
                   "to": "code-reviewer", "reason": "inner-loop review"}]
}
```

## Contract

Every skill that participates in a task MUST:

1. **Initialise or read** the blackboard on entry. The first skill in a task
   creates it with
   `python3 scripts/blackboard.py init <issue-key> --project <project> --skill <name>=<version>`;
   later skills call `read` and `record-skill`.
2. **Append** new facts, assumptions, unknowns, and decisions as they are
   produced — not only at the end. Use `blackboard.py append --section ...`.
3. **Record artifacts** (PR body, evidence pack, plan files, ADRs) with
   `blackboard.py artifact ...` so downstream skills can find them without
   re-grepping the cache.
4. **Record handoffs** with `blackboard.py handoff --from X --to Y --reason ...`
   so a reader can reconstruct who did what.

The blackboard does not replace per-skill output contracts. The skill still
emits its own structured output. The blackboard is the **inter-skill** state
the output is built from.

## What does not belong

- Secrets, tokens, PII — same rules as project memory.
- Multi-task knowledge that should outlive cleanup — that belongs in project
  or org memory.
- Free-form prose journals — keep entries short and structured.

## Cleanup

The blackboard lives under `<issue-key>/`. It is deleted by
`scripts/project-memory.py cleanup-task <issue-key>` together with the rest of
the per-task evidence pack. Anything that should survive must be lifted into
project memory **before** cleanup, per the
[Company Brain write order](company-brain.md#write-order-at-the-end-of-every-task).

## Cross-references

- [Company Brain](company-brain.md) — the loop the blackboard plugs into.
- [Project memory](project-memory.md) — durable per-project store.
- [`scripts/blackboard.py`](../scripts/blackboard.py) — the implementation.
