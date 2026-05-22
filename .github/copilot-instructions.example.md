# agent-skills — Copilot Instructions

Copy this file to `.github/copilot-instructions.md` in YOUR project repository.
GitHub Copilot in VS Code auto-loads it into every chat session. It encodes the
non-negotiable Company Brain memory contract so every Copilot session respects
the read-on-start / write-on-finish lifecycle without needing to find it buried
in a 400+ line SKILL.md.

## MANDATORY: Before ANY code change, investigation, review, or testing

Run this ONE command first — it loads project memory, org memory, and initialises
the per-task blackboard:

```bash
bash agent-skills/scripts/start-task.sh <project> <issue-key>
```

If you don't know the project name, resolve it from `.agent-skills.yml` first.
If you don't have an issue key, derive one from the branch name, tracker ticket,
or user's task description.

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

The Company Brain is the self-improving loop that makes agent-skills compound
value across sessions. Every task that skips the read-on-start / write-on-finish
contract is a task whose discoveries are lost and whose successor pays the same
discovery cost again.

Skipping these steps is the #1 failure mode observed in real usage. The skill
files are correct — this file closes the enforcement gap.
