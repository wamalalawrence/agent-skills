# Execution Modes

`agent-skills` supports two execution modes. The skills detect which mode they're running in during
their **Setup Preflight** phase and then resolve configuration accordingly. Pick the mode that
matches where the agent is actually running.

## Mode 1 — `local-workspace`

The original, recommended setup for engineers running an AI assistant on their own machine across
several repositories.

- When it applies: you cloned `agent-skills` next to your other repos, ran `./setup.init`, and your
  assistant runs locally with shell access.
- Workspace root: the directory that contains both `agent-skills/` and your sibling project repos.
- Config source: `${WORKSPACE_ROOT}/.env` generated or refreshed by `setup.init`, plus optional
  `${WORKSPACE_ROOT}/.jira-config.yml`.
- Project metadata: `PROJECTS_JSON` in `.env`, describing every repo's stack, build, format, and
  base branch.
- Cache path: `${WORKSPACE_ROOT}/.cache/agent-skills/<issue-key>/`, covered by the gitignore block
  `setup.init` writes.
- Typical agents: Claude Code, Cursor local, Continue, GitHub Copilot Chat in VS Code/JetBrains,
  Windsurf, or anything else that runs against your local filesystem.

See [installation.md](installation.md) and [configuration.md](configuration.md) for setup details.

## Mode 2 — `in-repo`

For users running the skills inside a **single target repository** with no separate workspace folder
— typical of online / cloud AI agents.

- When it applies: the agent is running inside one repository, with no sibling `agent-skills/`
  checkout and no `WORKSPACE_ROOT`-style multi-project layout.
- Workspace root: the repository root itself, such as `$PWD`, `$GITHUB_WORKSPACE`, or whatever the
  host platform exposes.
- Config source: [`.agent-skills.yml`](../.agent-skills.example.yml) checked into the repo, plus
  environment variables for secrets injected by the host platform.
- Project metadata: the single `project:` block inside `.agent-skills.yml`, plus repo-file inference
  from files such as `pom.xml`, `package.json`, `pyproject.toml`, or `go.mod` as a fallback.
- Cache path: `${REPO_ROOT}/.cache/agent-skills/<issue-key>/`. Add `.cache/` to the repo's
  `.gitignore`.
- Typical agents: GitHub Copilot coding agent on github.com, Cursor cloud/background agents, Devin,
  Codex, Claude on the web with the repo attached, GitHub Codespaces, and Gitpod.

The skills should never assume internet-only agents can write outside the repo, install packages, or
persist anything between turns. Anything cached must live under `${REPO_ROOT}/.cache/agent-skills/`.

## How a skill detects the mode

Every `SKILL.md`'s **Setup Preflight** runs this resolution in order:

1. **`AGENT_SKILLS_MODE` env var** — if explicitly set to `local-workspace` or `in-repo`, that wins.
  Used to override detection in CI or sandboxed evaluations.
2. **`${WORKSPACE_ROOT}/.env` exists and is readable** ⇒ `local-workspace` mode.
3. **`.agent-skills.yml` exists at the repository root** ⇒ `in-repo` mode.
4. **Neither found** ⇒ stop with the standard "Missing required setup" message, telling the user
  which file to create for whichever mode fits their environment. Do not silently guess.

## Variable resolution order (both modes)

Each value the skills need (`org_name`, `github_org`, `github_default_branch`, the project's
`stack`/`build`/`format`/`base_branch`, etc.) is resolved with this precedence:

1. Process environment variable (e.g. `GITHUB_ORG`, `JIRA_HOST`, `CONFLUENCE_HOST`).
2. `.agent-skills.yml` (in-repo mode) **or** `${WORKSPACE_ROOT}/.env` (local-workspace mode).
3. Repo-file inference — only for `stack`, `build`, `format` derived from `pom.xml` / `package.json`
  / `pyproject.toml` / `go.mod`. Never for org or credentials.
4. If still missing for the requested task, stop with `Missing required setup: <NAME>`.

Secrets (Jira tokens, Confluence tokens, GitHub tokens, API keys) **always** come from environment
variables in both modes. They are never written to `.agent-skills.yml`, which is committed to the
repository.

## Cache path resolution

Skills write their evidence-pack, repro-recipe, and definition-of-done artifacts to:

```
${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills/<issue-key>/}
```

In `local-workspace` mode this resolves to `${WORKSPACE_ROOT}/.cache/agent-skills/...`. In `in-repo`
mode it resolves to `<repo>/.cache/agent-skills/...`. `AGENT_SKILLS_CACHE_DIR` overrides both,
useful for ephemeral CI runners that want to redirect the cache to a tmpfs path.

## Quick start by environment

- Your laptop with VS Code + Copilot Chat across several repos: use `local-workspace`; run
  `git clone agent-skills && ./setup.init`.
- Your laptop with Claude Code across several repos: use `local-workspace`; run `./setup.init` and
  point the client at `<workspace>/.skills`.
- GitHub Copilot coding agent on github.com: use `in-repo`; commit `.agent-skills.yml` and the
  `skills/` folder, or a git submodule of `agent-skills`, into the target repo.
- Cursor cloud/background agent on a single repo: use `in-repo`; follow the same in-repo setup.
- GitHub Codespaces or Gitpod for one repo: use `in-repo`; make sure `.cache/` is in the repo's
  `.gitignore`.
- ChatGPT or Claude.ai web with files attached: use either mode; attach the relevant `SKILL.md` plus
  `.agent-skills.yml`, or paste `.env` values, and tell it which mode to use.
