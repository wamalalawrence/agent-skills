# Configuration

```text
.env in the workspace root
   |
   |-- loaded into the shell or agent environment
   |
   `-- referenced inside SKILL.md as ${VAR_NAME}
     skills never contain literal hostnames, tokens, repo names, or org names
```

The setup command and copied template are intentionally safe: they can describe the current workspace as a single local project, leave external systems blank, and avoid fake credentials. That is enough for generic planning or a first local dry run, but not enough for issue-aware or repository-changing work unless the generated values match the real workspace.

When loading `.env` manually in a shell, export the values so child commands can see them:

```bash
set -a
source .env
set +a
```

If `.env` is missing, a required value is blank, a copied bootstrap value would make the project identity ambiguous, or a Jira ticket cannot be read, the skill warns and stops before doing accuracy-sensitive work. Silent fallbacks are treated as a bug because they produce wrong work.

`.jira-config.yml` is optional. Jira-driven work can use the environment variables in `.env` directly, but if neither Jira credentials nor a user-supplied ticket summary are available, the issue-aware skills stop and ask for context.

## Required variables

See [`.env.example`](../.env.example) for the full annotated list. The minimum useful setup is:

| Variable | Why |
|---|---|
| `ORG_NAME` | Used in summaries and stakeholder-ready output |
| `WORKSPACE_ROOT` | Anchor for resolving repos, cache, and configs |
| `GITHUB_ORG` | Required only for GitHub repository discovery, clone, push, or PR work |
| `GITHUB_DEFAULT_BRANCH` | Default base branch when a project has no override |
| `PROJECTS_JSON` | Multi-project map with stack and command metadata |
| `CODE_REVIEWER_MODEL` | Optional model-routing hint for the nested `code-reviewer` skill |
| `JIRA_HOST` and `JIRA_API_TOKEN` | Required only for Jira-driven or story-aware modes |

## Multi-project workspaces

Declare repositories once via `PROJECTS_JSON` in `.env`. Skills use this to identify the current project, stack, runtime, base branch, build command, and formatting command.

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
