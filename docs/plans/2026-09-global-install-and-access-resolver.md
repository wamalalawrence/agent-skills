# Plan — Global Install And Generic Access Resolution

Status: **implemented in `v0.37.0`.** Written 2026-09-08 against `v0.36.0`.

This document is the design record for the largest structural change since the skills
themselves: `agent-skills` stops being a thing you configure *around each workspace* and
becomes a thing you install *once on a machine*. It also closes the three items
[the v0.36.0 plan](2026-09-learning-voice-and-router.md) deferred pending a decision — keychain
credentials (S2), the duplicated config surface (S5), and splitting `setup.init` (S6).

## The problem

`v0.36.0` had one installation story for local work, and it assumed a shape:

```text
~/work/
├── agent-skills/        <- the clone
├── repo-a/
├── repo-b/
├── .env                 <- credentials, in plaintext
├── .jira-config.yml
├── .skills -> agent-skills/skills
└── .agent-skills.lock
```

Four things follow from that shape, and all four are costs:

1. **Setup is per-workspace.** A repo cloned somewhere else does not get the skills. The
   answer was "move your repo" or "run setup again", which is not an answer.
2. **Setup asks for credentials it cannot use yet.** First run prompted for Jira, Confluence,
   Sonar, and deployed-environment pointers before the user had a single task. Most of those
   values were still blank a month later, and the ones that were filled in sat in plaintext.
3. **Lifecycle helpers were addressed relatively.** `bash agent-skills/scripts/start-task.sh`
   only resolves when `agent-skills` happens to be a sibling of the current directory. Three
   competing prefixes were documented, and skills were told to try all three.
4. **Project registration was filesystem archaeology.** `PROJECTS_JSON` was derived by
   globbing siblings of the clone, so the set of known projects was a side effect of directory
   layout.

## The change in one picture

```text
LOCAL MACHINE
-------------
one global install  (~/.agent-skills, one canonical skills tree)
        |
        +--> host adapters (per-skill symlinks into each agent's global skills dir)
        |
        +--> any local repository, at any path, now or in future
                 |
                 +--> project context inferred from the repo itself
                 +--> external access resolved lazily, only when a task needs it

REMOTE / CLOUD
--------------
repo-vendored or platform-synced skills, because a cloud agent cannot see your home directory
```

## Architecture

Five components, each independently testable. The old design had one 2,230-line shell script.

### 1. Runtime locator and CLI — `bin/agent-skills`, `lib/runtime.sh`

One stable entry point, resolvable from any directory:

```bash
agent-skills start-task --skill software-engineer
agent-skills access resolve --service jira --resource https://example.atlassian.net
agent-skills doctor
agent-skills verify
agent-skills update
```

`AGENT_SKILLS_HOME` (default `~/.agent-skills`) is the install root. It holds a manifest and
symlinks into exactly one source tree, so `skills/`, `scripts/`, `lib/`, and `bin/` all have a
single realpath on the machine. That is the invariant everything else rests on: a skill
discovered from any repository resolves to the same version of the same files.

Why symlinks into the clone rather than a copied snapshot: `--update` is a `git checkout` in
the clone, and a copy would need re-syncing after every one. One source of truth, updated in
one place. The cost is that deleting the clone breaks the install; `doctor` detects exactly
that and says so.

### 2. Host adapter registry — `lib/hosts.registry`

A data file, not branching logic. Each row is a host, its global skills directory, and notes
about how that host behaves. Adding a host is one line, which matters because the Agent Skills
ecosystem is still moving.

Registration is a **per-skill symlink** into the host directory, never a directory replacement.
That is what makes the installer safe next to skills the user already has: it only ever creates,
inspects, or removes links whose target is inside `AGENT_SKILLS_HOME`.

The important discovery from reading current host documentation is that hosts deliberately scan
each other's directories. Cursor reads `~/.agents/skills`, `~/.cursor/skills`, `~/.claude/skills`
and `~/.codex/skills`. VS Code reads `~/.copilot/skills`, `~/.claude/skills` and
`~/.agents/skills`. So *no* assignment of directories avoids a host seeing the same skill name
twice. The mitigation is not to fight it but to make it harmless: every registration is a
symlink to the one canonical tree, so a duplicate listing is the same file at the same version.
The invariant that actually matters — never merge instructions from two different versions of
one skill — holds by construction. `verify` asserts realpath identity rather than asserting
uniqueness it cannot deliver.

### 3. Generic access resolver — `scripts/access.py`

Not a Jira credential manager. One operation, arbitrary services, arbitrary fields:

```bash
agent-skills access resolve --service <name> --resource <uri> \
  --require host,login,token --secret token
```

The caller supplies the requirements. Nothing about Jira, Confluence, Sonar, GitHub, a database,
or an unnamed internal API is compiled into the resolver, so a skill can ask for access to a
service that did not exist when the installer ran.

Credentials are **identities, not projects**: `work-jira`, `personal-github`,
`production-readonly-db`. Several repositories share one identity; one repository may use several.

Precedence is fixed and documented in [access-resolution.md](../access-resolution.md). The head
of the order is the part that matters most: *an already-authenticated tool or session beats
storing another secret*. If `gh` is logged in, or the host has an MCP server for the service,
the resolver says so and no secret is requested or stored.

### 4. Secure storage

Secrets go to the OS store when one exists — macOS Keychain via `security`, Linux Secret Service
via `secret-tool`. The file fallback is explicit, `0600`, outside every repository, reported to
the user, and never silently substituted for a store that was working before. Metadata (profile
name, service, resource, account, field names, timestamps) lives in user config; values never do.

No home-grown encryption. An encrypted file next to its own key is theatre.

### 5. Progressive project context — `scripts/project-context.py`

The installer cannot know which repositories the user will open, so it does not ask. When an
agent enters a repository, context is derived from the repository: git root, remote, name,
default branch, build system, package manager, commands, a committed `.agent-skills.yml` if one
exists, and a repo-resident knowledge base if one exists.

A repository with no `agent-skills` configuration at all is a supported, normal case. It gets
planning, engineering, review, and testing on inferred context. Configuration is requested only
when a specific task needs a specific fact that cannot be inferred safely.

## Security decisions worth stating

- **A committed file may not name a credential profile.** `.agent-skills.yml` is checked into a
  repository, so anything in it is attacker-controlled from the resolver's point of view. It may
  declare *what* a service is (name, host); it may not select *which identity* to unlock. Profile
  selection comes from the user-global binding registry or from an untracked
  `.agent-skills.local.yml`, and the resolver verifies untrackedness rather than trusting the
  filename.
- **Resolution is not authorization.** Answering "can I authenticate?" says nothing about
  "may I perform destructive action X?". The
  [destructive-action safety policy](../destructive-action-safety.md) is unchanged and still
  governs the second question.
- **Never ask for a secret in chat.** Hidden terminal input, the OS store flow, or documented
  out-of-band configuration. If the host cannot obtain a secret securely, the resolver explains
  where to put it and asks to be re-run.

## What was rejected

- **Copying skills into every host directory.** Fast to write, guarantees version skew. The
  duplicate-discovery problem is real; duplicated *content* is what makes it dangerous.
- **A package manager (npm / Homebrew) as the install path.** It would add a dependency and a
  release surface for a project whose entire payload is Markdown plus standard-library scripts.
  `git clone` stays the install, `npx skills add` stays the alternative.
- **Encrypting the fallback file.** See above.
- **Dropping legacy workspace support.** Existing users have working `.env` files. The resolver
  still reads them; `setup.init --legacy-workspace` still writes them; `migrate` explains the
  move without copying secrets anywhere the user did not ask for.

## Deferred

- **Native Windows.** WSL and Git Bash remain the supported route. Windows Credential Manager is
  evaluated in the docs but not implemented, because nothing else in the repository is
  PowerShell-native and a half-supported platform is worse than a documented boundary.
- **Automatic JetBrains registration.** The global skill directory is IDE settings state, not a
  filesystem convention, so it takes one action in Settings. That is documented as one action
  rather than claimed as zero.
- **An agent runner behind `run-evals.py --invoke`.** Still the highest-value open item, still
  not this release.
