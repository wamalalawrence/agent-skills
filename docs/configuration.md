# Configuration

`agent-skills` supports two execution modes — `local-workspace` (multi-repo, with `setup.init`) and
`in-repo` (single-repo, for online/cloud agents). Read [execution-modes.md](execution-modes.md)
first to pick the one that matches where the agent runs. This page documents the configuration for
each.

## `local-workspace` mode

```text
.env in the workspace root
   |
   |-- loaded into the shell or agent environment
   |
   `-- referenced inside SKILL.md as ${VAR_NAME}
     skills never contain literal hostnames, tokens, repo names, or org names
```

The setup command and copied template are intentionally safe: they can describe the current
workspace as a single local project, leave external systems blank, and avoid fake credentials. That
is enough for generic planning or a first local dry run, but not enough for issue-aware or
repository-changing work unless the generated values match the real workspace.

When loading `.env` manually in a shell, export the values so child commands can see them:

```bash
set -a
source .env
set +a
```

If `.env` is missing, a required value is blank, a copied bootstrap value would make the project
identity ambiguous, or a Jira ticket cannot be read, the skill warns and stops before doing
accuracy-sensitive work. Silent fallbacks are treated as a bug because they produce wrong work.

`.jira-config.yml` is optional. Jira-driven work can use the environment variables in `.env`
directly, but if neither Jira credentials nor a user-supplied ticket summary are available, the
issue-aware skills stop and ask for context.

## Required variables

See [`.env.example`](../.env.example) for the full annotated list. The minimum useful setup is:

| Variable                         | Why                                                                    |
| -------------------------------- | ---------------------------------------------------------------------- |
| `ORG_NAME`                       | Used in summaries and stakeholder-ready output                         |
| `ORG_DOMAIN`                     | Identity domain for PR / release-note text (optional, defaults to `localhost`) |
| `WORKSPACE_ROOT`                 | Anchor for resolving repos, cache, and configs                         |
| `GITHUB_ORG`                     | Required only for GitHub repository discovery, clone, push, or PR work |
| `GITHUB_DEFAULT_BRANCH`          | Default base branch when a project has no override                     |
| `PROJECTS_JSON`                  | Multi-project map with stack and command metadata                      |
| `CODE_REVIEWER_MODEL`            | Optional model-routing hint for the nested `code-reviewer` skill       |
| `JIRA_HOST` and `JIRA_API_TOKEN` | Required only for Jira-driven or story-aware modes                     |
| `CONFLUENCE_HOST` and `CONFLUENCE_API_TOKEN` | Required only for Confluence-aware doc lookups             |

`setup.init` auto-populates several of these where it safely can:

- `ORG_NAME` is inferred from the Jira host (e.g. `acme.atlassian.net` -> `Acme`), then from the
  GitHub org, then from the workspace root directory name.
- `ORG_DOMAIN` is inferred from the Jira login email, the Jira host, or the GitHub org.
- `GITHUB_ORG` is inferred from sibling repo `remote.origin.url` first, then from `gh api user`.
- `JIRA_PROJECT_KEYS` accepts a pasted ticket key (`ABC-123`) or ticket URL and extracts the
  project key prefix.
- `CONFLUENCE_HOST` is inferred from the Jira host (Atlassian Cloud uses `<host>/wiki`; self-hosted
  `jira.<domain>` becomes `confluence.<domain>`).

You can always override the inferred default at the prompt.

## Setup-managed marker block

`setup.init` owns one block in `.env`, delimited by:

```text
# >>> agent-skills setup.init
... managed keys ...
# <<< agent-skills setup.init
```

All setup-managed keys (org identity, workspace, projects, Jira, Confluence) live INSIDE that
block. The block is overwritten on every rerun. Edits OUTSIDE the block (custom env vars,
code-reviewer overrides, build tooling hints) are preserved verbatim.

Never define a setup-managed key a second time outside the block. The shell loader's
"last assignment wins" rule turns duplicates into silent overrides. `setup.init --verify` and
`scripts/validate-repo.py` both fail when a managed key is defined outside the block.

If you upgrade from v0.10.0 or earlier and your `.env` carries duplicate top-level definitions of
managed keys, just rerun `./setup.init`. It strips the legacy duplicates and reports how many it
removed.

## Multi-project workspaces

Declare repositories once via `PROJECTS_JSON` in `.env`. Skills use this to identify the current
project, stack, runtime, base branch, build command, and formatting command.

```jsonc
PROJECTS_JSON='[
  {"name":"example-api",    "path":"example-api",    "stack":"java",       "base_branch":"main", "build":"mvn clean verify",   "format":"mvn fmt:format && mvn fmt:check"},
  {"name":"example-web",    "path":"example-web",    "stack":"typescript", "base_branch":"main", "build":"npm ci && npm test", "format":"npm run lint && npm run format:check"},
  {"name":"example-worker", "path":"example-worker", "stack":"python",     "base_branch":"main", "build":"pytest",             "format":"ruff check . && ruff format --check ."}
]'
```

Per-project keys:

- `name`: short identifier
- `path`: relative path under `${WORKSPACE_ROOT}`
- `stack`: `java`, `typescript`, `python`, `go`, `mixed`, or `other`
- `base_branch`: overrides `${GITHUB_DEFAULT_BRANCH}` for this project
- `build`: full build-and-test command
- `format`: formatter command to run before commit or PR
- optional: `runtime_version`, `coverage_target`, `notes`

## `in-repo` mode

When the agent runs inside a single target repository (GitHub Copilot coding agent, Cursor cloud,
Devin, Codex, Codespaces, Gitpod, Claude.ai web), there is no separate workspace root and no `.env`
file. Instead, configuration lives in a committed file at the repository root:
[`.agent-skills.yml`](../.agent-skills.example.yml). Secrets still come from environment variables
injected by the host platform — never from this file.

Top-level keys:

| Key                                     | Required                    | Notes                                                                                       |
| --------------------------------------- | --------------------------- | ------------------------------------------------------------------------------------------- |
| `mode`                                  | yes                         | Must be `in-repo`.                                                                          |
| `org_name`                              | yes                         | Display name in summaries and PRs.                                                          |
| `github_org`                            | only for clone/push/PR work | GitHub owner.                                                                               |
| `github_default_branch`                 | yes                         | Default base branch.                                                                        |
| `project`                               | yes                         | Single project block; replaces `PROJECTS_JSON`.                                             |
| `jira.host`, `jira.default_project_key` | only for Jira work          | Host metadata only; the credential `JIRA_API_TOKEN` is an env var.                          |
| `confluence.host`                       | only for Confluence work    | Host metadata only; the credential `CONFLUENCE_API_TOKEN` is an env var.                    |
| `code_reviewer_model`                   | no                          | Optional model-routing hint.                                                                |
| `cache_dir`                             | no                          | Override; default is `<repo>/.cache/agent-skills/`. Equivalent to `AGENT_SKILLS_CACHE_DIR`. |

`project` keys mirror the per-project schema above (`name`, `stack`, `base_branch`, `build`,
`format`, `runtime_version`, `coverage_target`, `notes`) but with no `path` field — the project is
the repo itself.

## Variable resolution order (both modes)

For every value the skills need, the order is:

1. Process environment variable.
2. `.agent-skills.yml` (in-repo) or `${WORKSPACE_ROOT}/.env` (local-workspace).
3. Repo-file inference — only for `stack`/`build`/`format`.
4. Stop with `Missing required setup: <NAME>` if still unresolved.

## Cache path

Skills write the evidence-pack, repro-recipe, and definition-of-done artifacts to:

```
${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills/<issue-key>/}
```

That is the workspace root in `local-workspace` mode and the repository root in `in-repo` mode. Add
`.cache/` to `.gitignore` in either case (`setup.init` does it for you in local-workspace mode).
