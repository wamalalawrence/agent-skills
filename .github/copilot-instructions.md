# agent-skills — Copilot Instructions

These instructions are auto-loaded by GitHub Copilot in VS Code. They encode the
non-negotiable Company Brain contract from `agent-skills` so every Copilot session
on this workspace respects the memory lifecycle without needing to read 400+ line
SKILL.md files to find it.

## MANDATORY: Before ANY code change, investigation, review, or testing

Run this ONE command first — it detects the project/task id, loads project
memory, loads org memory, records the skill version, and initialises the
per-task blackboard:

```bash
bash agent-skills/scripts/start-task.sh --skill <skill-name>=<skill-version>
```

If the detected project or task id is wrong, rerun with explicit values:

```bash
bash agent-skills/scripts/start-task.sh <project> <issue-key> --skill <skill-name>=<skill-version>
```

**The output of this command IS your starting context.** Do not re-discover facts
already recorded in project memory. Every `Common gotchas` bullet is a verified
constraint; every `Build & runtime` bullet is the authoritative build command.

## MANDATORY: After ANY task that touches code, investigation, review, or testing

1. **Run the finish wrapper FIRST so durable memory is written before cleanup:**
   ```bash
   bash agent-skills/scripts/finish-task.sh <project> <issue-key> \
     --skill <skill-name> --summary "<one sentence outcome>"
   ```
   Add `--status blocked` or `--status needs-context` when the task cannot
   complete; those states preserve per-task scratch for the next agent.

2. **Append extra durable facts when the task discovered them:**
   ```bash
   bash agent-skills/scripts/finish-task.sh <project> <issue-key> \
     --skill <skill-name> --summary "<one sentence outcome>" \
     --build-runtime "<verified build/runtime fact>" \
     --gotcha "<gotcha that surprised you>"
   ```

3. **Never** run cleanup before appending memory. The order is: write memory
   first, then cleanup. `cleanup-task` refuses to touch `_projects/` or `_org/`
   so durable knowledge survives every cleanup pass.

## Why this matters

The Company Brain (`docs/company-brain.md`) is the self-improving loop that
makes agent-skills compound value across sessions. Every task that skips the
read-on-start / write-on-finish contract is a task whose discoveries are lost
and whose successor pays the same discovery cost again.

Skipping these steps is the #1 failure mode observed in real usage. The skill
files are correct — the gap is enforcement. These instructions close that gap
for Copilot sessions.
