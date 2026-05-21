# Telemetry

Telemetry is the count layer of the [Company Brain](company-brain.md). It
exists so that "the skills are improving" stops being a feeling and becomes a
number. The implementation is in
[`scripts/telemetry.py`](../scripts/telemetry.py).

## Storage

```
${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills}/
  _projects/<project-slug>/telemetry.ndjson
```

One event per line, append-only, JSON. No free-form messages, no PII, no
secrets. The file lives under `_projects/` so it survives per-task cleanup
along with the rest of project memory.

## Event shape

```json
{"at": "2026-05-22T09:14:01Z", "project": "acme-checkout",
 "event": "invoked", "skill": "software-engineer", "issue": "ABC-123"}
```

Required keys: `at`, `project`, `event`. All other keys are passed through as
the `--field K=V` pairs supplied by the caller.

## Recognised events

| Event | Meaning | Typical fields |
| --- | --- | --- |
| `invoked` | A skill started a run. | `skill`, `issue` |
| `loop_round` | A producer-reviewer round started/finished. | `skill`, `reviewer`, `round` |
| `handoff` | One skill handed off to another. | `from`, `to`, `reason` |
| `finding` | A reviewer / investigator emitted a finding. | `skill`, `severity` |
| `stopped` | A skill stopped on missing context. | `skill`, `reason` |
| `completed` | A skill finished its contract for this task. | `skill`, `issue` |
| `artifact` | A durable artifact was produced. | `skill`, `kind`, `path` |
| `outcome` | An outcome was recorded for the task. | `outcome`, `issue` |

Custom event names are accepted; `report` lists unknown ones separately so
they can be folded back into this table.

## CLI

```bash
python3 scripts/telemetry.py emit acme-checkout invoked \
  --field skill=software-engineer --field issue=ABC-123

python3 scripts/telemetry.py report acme-checkout --since 2026-05-01T00:00:00Z

python3 scripts/telemetry.py report --all
```

`report` aggregates counts per skill and per event name. Combine with the
[`Outcomes`](company-brain.md#outcome-feedback) section of project memory and
the per-release `eval-runs/<version>/summary.md` for the full picture going
into the next
[skill performance review](skill-performance-review.md).

## What does not belong

- Free-form messages, log lines, or stack traces.
- Per-user identifiers, customer IDs, ticket bodies, or any field that could
  contain PII.
- Secrets — same rule as project memory.

## Cross-references

- [Company Brain](company-brain.md)
- [Project memory](project-memory.md)
- [Outcome recorder](../scripts/outcome-recorder.py)
- [Skill performance review](skill-performance-review.md)
