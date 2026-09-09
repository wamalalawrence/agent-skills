# Execution Modes

Where the agent actually runs decides how it finds the skills. There are three modes, and the
distinction that matters most is **local machine versus remote machine**.

```text
LOCAL MACHINE
-------------
one global install  (~/.agent-skills, one canonical skills tree)
        |
        +--> any local repository
        +--> any local repository
        +--> any repository you clone next year

REMOTE / CLOUD
--------------
repo-vendored, platform-synced, or platform-provided skills,
because a cloud agent cannot see files on your machine
```

## Mode 1 — `global` (default for local work)

- **When it applies:** you ran `agent-skills install` on your machine and the agent runs against your local
  filesystem.
- **Skill source:** `${AGENT_SKILLS_HOME}/skills`, reached through each host's global skills
  directory. One canonical tree; see [skill-source-resolution.md](skill-source-resolution.md).
- **Runtime:** the `agent-skills` command, resolvable from any directory.
- **Project metadata:** inferred per repository by `agent-skills project`. Optional committed
  `.agent-skills.yml` wins where present.
- **Credentials:** none stored at install. Resolved on demand — see
  [access-resolution.md](access-resolution.md).
- **Cache:** `<repo>/.cache/agent-skills/<issue-key>/`, anchored at the git root. Add `.cache/` to
  the repository's `.gitignore`.
- **Typical hosts:** Claude Code, Cursor, VS Code with GitHub Copilot, Codex, Kiro, JetBrains AI
  Assistant, Windsurf, Continue, Copilot CLI.

A repository needs **no** agent-skills configuration to work in this mode.

## Mode 2 — `in-repo` (cloud and remote agents)

- **When it applies:** the agent runs inside one repository on a machine you do not control, so it
  cannot read your home directory.
- **Skill source:** vendored into the repository (`<repo>/.agent-skills/skills/`, a submodule, or
  `.github/skills/`), or referenced from the platform's instruction surface.
- **Project metadata:** the `project:` block in a committed
  [`.agent-skills.yml`](../.agent-skills.example.yml), plus repo-file inference.
- **Credentials:** injected by the host platform as environment variables — Actions secrets,
  Codespaces secrets, the platform's secret store. Never in `.agent-skills.yml`.
- **Cache:** `${REPO_ROOT}/.cache/agent-skills/<issue-key>/`.
- **Typical hosts:** GitHub Copilot coding agent on github.com, Cursor cloud and background agents,
  Devin, Codespaces, Gitpod, Claude on the web with a repo attached.

Never assume a cloud agent can write outside the repository, install packages, or persist anything
between turns.

### Why the global install does not cover this

It is a filesystem fact, not a limitation of the design: `~/.agent-skills` exists on your laptop.
A cloud runner starts from a fresh container with your repository checked out and nothing else.

One partial exception is worth knowing: **Cursor can sync personal skills** from `~/.cursor/skills`
to Cloud Agents, but only when *Settings → Agents → Sync Skills for Cloud Agents* is enabled, and
only that directory. `~/.agents/skills` and unsynced local skills stay on your machine. Everything
else in the table in [assistants.md](assistants.md) reads `no`.

## Mode 3 — `local-workspace` (legacy, pre-v0.37.0)

The original model: a parent workspace folder holding the clone, sibling repos, a `.env`, and a
`.skills` symlink. Still supported so existing installs keep working.

- **When it applies:** you installed before v0.37.0 and have not migrated, or you deliberately chose
  a pre-v0.37 `setup.init` run. Nothing creates that layout any more; it is only still recognised.
- **Skill source:** `<workspace>/.skills`.
- **Project metadata:** `PROJECTS_JSON` in `${WORKSPACE_ROOT}/.env`.
- **Credentials:** `${WORKSPACE_ROOT}/.env`, still discovered by the access resolver.
- **Cache:** `${WORKSPACE_ROOT}/.cache/agent-skills/`.

Migration is documented in
[installation.md](installation.md#upgrading-from-v036x-workspace-installation) and explained by
`agent-skills migrate`. Nothing is deleted and no secret is moved without an explicit request.

## How a skill detects the mode

```bash
agent-skills project --field mode
```

Resolution order:

1. **`AGENT_SKILLS_MODE`** set to `global`, `in-repo`, or `local-workspace` — that wins. Used to
   override detection in CI and sandboxed evaluations.
2. **Committed `.agent-skills.yml` declaring `mode: in-repo`** ⇒ `in-repo`.
3. **`${AGENT_SKILLS_HOME}/install.json` exists** ⇒ `global`.
4. **`${WORKSPACE_ROOT}/.env` exists and is readable** ⇒ `local-workspace`.
5. **`.agent-skills.yml` at the repository root** ⇒ `in-repo`.
6. **Nothing found** ⇒ `global`, using inference only.

Step 6 is the important change from v0.36.x, where this position was a hard stop. A repository with
no configuration is a supported case: generic planning, engineering, review, and testing all work on
inferred context. The agent stops only when a **specific task** needs a **specific fact** that
cannot be inferred safely, and `agent-skills project` names those under `needs_confirmation`.

## Variable resolution order (all modes)

For each value the skills need (`base_branch`, `stack`, `build`, `format`, and so on):

1. Process environment variable.
2. Committed `.agent-skills.yml`, or `${WORKSPACE_ROOT}/.env` in legacy mode.
3. Repository inference — git metadata and build manifests.
4. If still missing **and the task needs it**, ask. Otherwise proceed and mark the assumption.

Credentials do not follow this order. They have their own, in
[access-resolution.md](access-resolution.md), and they are never read from a committed file.

## Cache path resolution

```text
${AGENT_SKILLS_CACHE_DIR:-<repo-root>/.cache/agent-skills/<issue-key>/}
```

In `global` and `in-repo` mode this is the repository root, found with `git rev-parse
--show-toplevel` so a nested working directory does not create a second cache. In legacy mode it is
`${WORKSPACE_ROOT}/.cache/agent-skills/`. `AGENT_SKILLS_CACHE_DIR` overrides all of it, which is
useful on ephemeral runners that want a tmpfs path.

## Quick start by environment

| Environment | Mode | What to do |
| --- | --- | --- |
| Your laptop, any local editor, any number of repos | `global` | `npx @wamalalawrence/agent-skills install` once |
| GitHub Copilot coding agent on github.com | `in-repo` | commit `.agent-skills.yml`, vendor skills into `.github/skills/` or `.agent-skills/skills/` |
| Cursor cloud / background agents | `in-repo` | vendor into the repo, or enable Cursor's personal-skill sync for `~/.cursor/skills` |
| Codespaces / Gitpod | `in-repo` | commit `.agent-skills.yml`, add `.cache/` to `.gitignore`, use platform secrets |
| Devin and similar hosted agents | `in-repo` | add the vendored `SKILL.md` to project knowledge |
| Claude or ChatGPT web with files attached | either | attach the `SKILL.md` plus `.agent-skills.yml`, and say which mode |
| A pre-v0.37.0 install you have not migrated | `local-workspace` | keeps working; `agent-skills migrate` when ready |

## Related

- [Installation](installation.md) — the global install and the migration path.
- [Assistants](assistants.md) — per-host discovery paths, verification, and cloud reachability.
- [Skill-source resolution](skill-source-resolution.md) — which directory to load from when more
  than one exists.
- [Access resolution](access-resolution.md) — external access, per mode.
- [Updates](updates.md) — how each mode applies a new release.
