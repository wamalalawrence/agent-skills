# Optional hook templates

These are **templates, not requirements.** Nothing in `agent-skills` needs them, and no skill
behaves differently when they are absent. Copy one if your host supports hooks and you want the
lifecycle to run deterministically instead of depending on the model following an instruction.

## The problem they solve

Every skill opens with a `PREFLIGHT` block telling the agent to run `start-task.sh` before doing
anything, and `finish-task.sh` at the end. That instruction is markdown, which means compliance
is probabilistic. A skipped `start-task.sh` means the agent re-discovers facts it already had; a
skipped `finish-task.sh` means everything the session learned is lost.

A hook fires every time, because the host runs it rather than the model choosing to.

The same finding is what pushed [ECC](https://github.com/affaan-m/everything-claude-code) to
rewrite its continuous-learning system around hooks: instruction-driven observation depends on
the model's judgement and misses cases, while hook-driven observation runs on every event.
Content rephrased for compliance with licensing restrictions.

## Why they are not installed for you

Host neutrality is one of this project's design principles. Hook formats are host-specific and
mutually incompatible: Claude Code, Kiro, Cursor, and OpenCode each have their own schema, event
names, and config location. Shipping one wired-in would quietly make this a single-host project.

So the templates live here, unwired, and you copy the one that matches your host.

## What is here

| File | Host | Installs to |
| --- | --- | --- |
| [`claude-code-settings.json`](claude-code-settings.json) | Claude Code | merge into `~/.claude/settings.json` or `.claude/settings.json` |
| [`kiro-lifecycle.json`](kiro-lifecycle.json) | Kiro | `.kiro/hooks/agent-skills-lifecycle.json` |
| [`generic-session-hooks.sh`](generic-session-hooks.sh) | any host that can run a shell command on session start and stop | call from your host's own hook mechanism |

## Before you copy one

Two things worth knowing, because both have bitten people:

- **Do not install a hook twice.** If your host already auto-loads a plugin's hooks, adding the
  same command to a settings file as well makes it fire twice. Two `start-task.sh` runs are
  harmless but noisy; two `finish-task.sh` runs write the same memory bullet twice.
- **Hooks run shell commands.** Read a template before installing it. Every command in these
  templates is read-mostly — `start-task.sh` only reads memory, `doctor.sh` only probes — but
  the general rule holds: treat hook configuration as executable code, because it is.

## What the templates do

On session start:

```bash
bash scripts/start-task.sh --skill "${AGENT_SKILLS_ACTIVE_SKILL:-unknown}"
```

Loads org memory, project memory, the repo knowledge base, and the capability report. Read-only
with respect to knowledge; it never writes a fact.

On session stop:

```bash
bash scripts/finish-task.sh --skill "${AGENT_SKILLS_ACTIVE_SKILL:-unknown}" \
  --summary "session ended" --status needs-context --no-cleanup
```

Deliberately conservative. A hook cannot know whether the work actually finished, so it records
`needs-context`, which **preserves** the per-task scratch and the working branch. The agent's own
`finish-task.sh` call, with a real summary and a real status, is still the one that matters — this
is a floor that stops a crashed or abandoned session losing everything, not a replacement.

Set `AGENT_SKILLS_ACTIVE_SKILL` in your environment if you want honest per-skill attribution in
telemetry rather than `unknown`.

## Verifying a hook actually fires

```bash
bash scripts/doctor.sh --brief          # should appear in your session-start output
python3 scripts/telemetry.py report --all
```

If the telemetry report shows no `completed` or `stopped` events after a few sessions, the hook
is not firing. Check for a duplicate registration first; that is the most common cause.

## Related

- [Lifecycle preflight](../docs/lifecycle-preflight.md) — what the two commands do in full.
- [Repo knowledge](../docs/repo-knowledge.md) — the tier a skipped `finish-task.sh` loses.
- [Telemetry](../docs/telemetry.md) — how to tell whether any of this is running.
