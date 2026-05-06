# Config-File Locator Eval: `.env` Lives In The Parent Workspace Folder

## Input Context

A `setup.init`-managed workspace looks like this on disk:

```
~/work/                              # the workspace root
├── .env                             # written by setup.init
├── .env.local                       # personal overrides
├── .jira-config.yml                 # written with --with-jira
├── .skills -> ../agent-skills/skills
├── agent-skills/                    # this repo
└── example-api/                     # the repo the user is asking about
    ├── .git/
    └── src/
```

The agent's cwd is `~/work/example-api`. The user asks the agent to "fix the failing
build in the API repo", which requires Jira access (the failing build is tied to ticket
`ABC-456`).

## Skill Under Test

`software-engineer` (primary), with the same contract applying to every top-level skill
that does the new pre-flight (`delivery-planner`, `product-owner`, `manual-tester`,
`test-automation-engineer`, `issue-investigator`, `code-reviewer`).

## Why This Scenario

This is the recurring failure the v0.29.0 work targets: an agent at the repo cwd checks
`./.env`, sees nothing, and tells the user "I can't find your `.env` / `.jira-config.yml`
files — please tell me where they are". The files are one directory up, exactly where
`setup.init` put them, and the agent should never have asked.

## Expected Behavior

- The agent runs `python3 scripts/locate-config.py` (or its in-process equivalent) **before**
  declaring any config file missing.
- The locator's output names every directory it searched and reports `.env`,
  `.env.local`, and `.jira-config.yml` as **found** at `~/work/...`.
- The agent picks `~/work` as `WORKSPACE_ROOT` because that is the directory holding the
  `.skills` symlink and the resolved `.env`.
- The agent then sources `.env` and proceeds with the Jira-aware workflow.
- The agent **never** says "`.env` not found" without naming the directories it searched.
- The agent **never** asks the user to paste the path of `.env` / `.jira-config.yml` in
  chat when the locator already resolved them.

## Anti-Patterns This Eval Pins

- Checking only the cwd for `.env` and giving up.
- Asking the user "where is your `.env`?" before running the locator.
- Treating a `.git` boundary as the limit of the search; `setup.init` writes outside every
  repo's `.git` on purpose.
- Inventing a `.env` path from a guess instead of using the locator's output.
- Reporting `.jira-config.yml` as missing when only the placeholders are unresolved (that is
  an [auth-discovery](../docs/auth-discovery.md) failure, not a locator failure).

## Required Output

The skill output must include a one-line trace:

```
config locator: workspace_root=~/work; .env=~/work/.env; .jira-config.yml=~/work/.jira-config.yml
```

(or the equivalent JSON when the agent is in machine-readable mode), and the rest of the
workflow must reflect that those paths were used.
