# agent-skills — Copilot Instructions

These instructions are auto-loaded by GitHub Copilot in VS Code. They encode the
non-negotiable Company Brain contract from `agent-skills` so every Copilot session
on this workspace respects the memory lifecycle without needing to read 400+ line
SKILL.md files to find it.

## MANDATORY: Before ANY code change, investigation, review, or testing

Run this ONE command first — it loads project memory, org memory, and initialises
the per-task blackboard:

```bash
bash agent-skills/scripts/start-task.sh <project> <issue-key>
```

If you don't know the project name, resolve it from `${PROJECTS_JSON}` or
`.agent-skills.yml` first (match the cwd against the configured projects). If
you don't have an issue key, derive one from the branch name, tracker ticket, or
user's task description.

**The output of this command IS your starting context.** Do not re-discover facts
already recorded in project memory. Every `Common gotchas` bullet is a verified
constraint; every `Build & runtime` bullet is the authoritative build command.

## MANDATORY: After ANY task that touches code, investigation, review, or testing

1. **Append durable facts to project memory FIRST:**
   ```bash
   python3 agent-skills/scripts/project-memory.py note <project> \
     --section "Build & runtime" --text "<verified fact>"
   python3 agent-skills/scripts/project-memory.py note <project> \
     --section "Common gotchas" --text "<gotcha that surprised you>"
   python3 agent-skills/scripts/project-memory.py note <project> \
     --section "Recent tasks" --text "<issue-key>: <one-sentence outcome>"
   ```

2. **Then clean up per-task scratch:**
   ```bash
   python3 agent-skills/scripts/project-memory.py cleanup-task <issue-key>
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
