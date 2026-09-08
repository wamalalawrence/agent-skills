# agent-skills — Copilot Instructions

Copy this file to `.github/copilot-instructions.md` in YOUR project repository.
GitHub Copilot in VS Code auto-loads it into every chat session. It encodes the
non-negotiable Company Brain memory contract so every Copilot session respects
the read-on-start / write-on-finish lifecycle without needing to find it buried
in a 400+ line SKILL.md.

`agent-skills` is the globally installed command. Install it once per machine
(`git clone` then `./setup.init`) and it resolves from every repository, so this
file needs no path edits. If it is not on PATH, use
`"${AGENT_SKILLS_HOME:-$HOME/.agent-skills}/bin/agent-skills"`.

## MANDATORY: Before ANY code change, investigation, review, or testing

Run this ONE command first — it detects the project/task id, loads project
memory, loads org memory, records the skill version, and initialises the
per-task blackboard:

```bash
agent-skills start-task --skill <skill-name>=<skill-version>
```

If the detected project or task id is wrong, rerun with explicit values:

```bash
agent-skills start-task <project> <issue-key> --skill <skill-name>=<skill-version>
```

**The output of this command IS your starting context.** Do not re-discover facts
already recorded in project memory. Every `Common gotchas` bullet is a verified
constraint; every `Build & runtime` bullet is the authoritative build command.

## MANDATORY: After ANY task that touches code, investigation, review, or testing

1. **Run the finish wrapper FIRST so durable memory is written before cleanup:**
   ```bash
   agent-skills finish-task <project> <issue-key> \
     --skill <skill-name> --summary "<one sentence outcome>"
   ```
   Add `--status blocked` or `--status needs-context` when the task cannot
   complete; those states preserve per-task scratch for the next agent.

2. **Append extra durable facts when the task discovered them:**
   ```bash
   agent-skills finish-task <project> <issue-key> \
     --skill <skill-name> --summary "<one sentence outcome>" \
     --build-runtime "<verified build/runtime fact>" \
     --gotcha "<gotcha that surprised you>"
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
