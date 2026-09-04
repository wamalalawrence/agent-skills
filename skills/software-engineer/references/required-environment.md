# Required Environment (software-engineer)

Extracted from `SKILL.md` in v0.36.0. Every variable this skill reads, when each is
required, and the exact message to emit when one is missing.

Before working through this by hand, read the capability report that
`start-task.sh` step 4 prints — it already answers most of it. See [lifecycle
preflight](../../../docs/lifecycle-preflight.md#capability-report).

Run this setup preflight before context discovery.

**Step 1 — detect execution mode** ([docs/execution-modes.md](../../../docs/execution-modes.md)):

1. If `AGENT_SKILLS_MODE` is set to `local-workspace` or `in-repo`, use it.
2. Else if `${WORKSPACE_ROOT}/.env` exists and is readable → `local-workspace`.
3. Else if `.agent-skills.yml` exists at the repository root → `in-repo`.
4. Else: stop and tell the user to either run `./setup.init` (multi-repo local) or copy
  `.agent-skills.example.yml` to `.agent-skills.yml` at the repo root (single-repo / online agent).

**Step 2 — verify context for the requested task.** Whichever mode applies, if the resolved
configuration is missing, unreadable, or lacks enough metadata for the requested task, warn the user
and stop before issue-aware, repository-changing, branch, PR, or release work. Generic planning may
continue only if the user supplied enough context directly and the output clearly states that setup
was not verified.

Treat blank values and copied placeholders that would make the requested work inaccurate as missing
context. The bootstrap `PROJECTS_JSON` entry from `.env.example` (or an empty `project:` block in
`.agent-skills.yml`) is acceptable only for local exploratory work; for implementation, review, PR,
or release work, the project entry must identify the real repo, stack, base branch, and validation
commands or the agent must inspect the repo and ask before proceeding.

Values are resolved in this order: process environment → `.agent-skills.yml` (in-repo) or
`${WORKSPACE_ROOT}/.env` (local-workspace) → repo-file inference (only for `stack`/`build`/`format`)
→ stop with `Missing required setup: <NAME>`. Secrets always come from environment variables in both
modes.

Required setup variables:

- `WORKSPACE_ROOT`: required in `local-workspace` mode. Resolves repos, configs, and cache. In
  `in-repo` mode, the repository root is used instead.
- `ORG_NAME`: required. Used for display in summaries and PR descriptions.
- `GITHUB_ORG`: required only for GitHub clone, push, PR, or sibling-repo lookup.
- `GITHUB_DEFAULT_BRANCH`: required. Default base branch for new work.
- `PROJECTS_JSON`: required in `local-workspace` mode. Multi-project map for stack, base branch,
  build, and format commands. See [`agent-skills/.env.example`](../../../.env.example). In `in-repo`
  mode, the single `project:` block in `.agent-skills.yml` replaces this.
- `GIT_COMMIT_MSG_FORMAT`: optional. Hint string for commit message format.
- `GIT_BRANCH_NAME_FORMAT`: optional. Hint string for branch name format.
- `GIT_MERGE_STRATEGY`: optional. One of `squash`, `merge`, or `rebase`.
- `JIRA_HOST`, `JIRA_API_TOKEN`, `JIRA_AUTH_TYPE`: required only when a Jira ticket is in scope.
  Used for Jira CLI or REST access. For non-Jira trackers (GitLab, Azure DevOps, etc.),
  the equivalent tracker-specific variables apply.
- `CONFLUENCE_HOST`, `CONFLUENCE_API_TOKEN`: required only if the ticket links Confluence pages.
- `JDK_MANAGER`, `NODE_MANAGER`, `PYTHON_MANAGER`: optional hints for switching language runtime.
- `DOCKER_REQUIRED`: optional. Indicates whether Docker must be running before the build.
- `SHARED_LIBRARY_NAMES`: optional. Used for cross-project impact detection.
- `SONAR_HOST_URL`: optional. Points to SonarQube reports when CI/CD provides them.

If a variable is missing, output:

> Missing required setup: `<NAME>`. Add it to `${WORKSPACE_ROOT}/.env` (local-workspace mode — see
> [`agent-skills/.env.example`](../../../.env.example)) or to `.agent-skills.yml` at the repository
> root (in-repo mode — see
> [`agent-skills/.agent-skills.example.yml`](../../../.agent-skills.example.yml)) and re-run. I will
> not continue because the result would be based on incomplete context.

For tracker-driven work, `.jira-config.yml` (or equivalent tracker config) is optional when `JIRA_HOST`, `JIRA_AUTH_TYPE`,
`JIRA_API_TOKEN`, and any required `JIRA_LOGIN` value are present and usable. If a Jira ticket is in
scope and neither Jira access nor a user-supplied ticket summary with acceptance criteria/comments
is available, stop and ask; do not infer ticket intent from the key, branch name, or code diff
alone.

**Before Phase 1.1 declares the issue tracker inaccessible, run the auth discovery walk** documented in
[`docs/auth-discovery.md`](../../../docs/auth-discovery.md): `.agent-skills.yml` →
`.jira-config.yml` → `.env` / `.env.local` → process environment → `scripts/auth-preflight.py`.
Treat unresolved `${VAR}` placeholders in `.jira-config.yml` as **incomplete configuration**, not
as missing credentials. The Jira CLI does not expand `${VAR}` placeholders; either source `.env`
first or rely on the preflight for validation. Implementation that skips the discovery walk and
silently falls back to "no tracker access" is a workflow failure, not a setup failure.

**Locate config files before claiming any are missing.** `.env` and `.jira-config.yml` (or
equivalent tracker config) are
written by `setup.init` to the **parent workspace folder**, not the repo cwd. Run
`python3 scripts/locate-config.py` (see [`docs/auth-discovery.md` § Where the files
live](../../../docs/auth-discovery.md#where-the-files-live)). The script walks the cwd, every
parent directory, the `WORKSPACE_ROOT` env var, and the directory holding the `.skills`
symlink. "Not in cwd" is **not** the same as "not in the workspace"; reporting the former as
the latter is a workflow failure.

**Project memory: read on start, write on finish.** Before context discovery, run
`python3 scripts/project-memory.py read <project>`. If no memory exists yet, run
`python3 scripts/project-memory.py init <project> --repo <owner/repo>` to create the skeleton.
Treat the contents as starting context (build commands, runtime version, common gotchas, recent
tasks) — not as gospel; correct it when this run disproves a fact. Append durable facts as
they are verified with `python3 scripts/project-memory.py note <project> --section <S> --text
<T>`. See [`docs/project-memory.md`](../../../docs/project-memory.md) for what belongs there and
the post-completion cleanup contract that preserves project memory while removing per-task
scratch.

