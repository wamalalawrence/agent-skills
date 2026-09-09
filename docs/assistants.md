# Using With Your AI Assistant

Skills are plain Markdown with YAML frontmatter under [`../skills/`](../skills/), conforming to the
[Agent Skills specification](https://agentskills.io/specification).

On a local machine you do not point an assistant at anything. `./setup.init` registers the skills in
each host's own global skills directory, so the host discovers them the way it discovers any other
installed skill. Invoke one by name.

```bash
agent-skills hosts          # what is supported, and what is registered here
agent-skills verify         # whether each integration resolves to the canonical tree
```

## Supported hosts

Every global directory below holds **symlinks into one canonical tree**
(`${AGENT_SKILLS_HOME}/skills`), so a skill has exactly one version on the machine no matter how
many hosts list it.

| Host | Global discovery path | Registered | Reaches cloud agents |
| --- | --- | --- | --- |
| Claude Code | `~/.claude/skills/` | automatically | no |
| Agent Skills standard dir | `~/.agents/skills/` | always | no |
| Codex | `~/.codex/skills/` and `~/.agents/skills/` | automatically | no |
| Cursor | `~/.cursor/skills/` | automatically | opt-in, see below |
| GitHub Copilot (VS Code, Visual Studio, CLI) | `~/.copilot/skills/` | automatically | no |
| Kiro | `~/.kiro/skills/` | automatically | no |
| JetBrains AI Assistant | IDE settings, no filesystem convention | **one manual action** | no |
| Windsurf | `~/.windsurf/skills/` | when detected | no |
| Continue | `~/.continue/skills/` | when detected | no |

"When detected" means the installer registers a host if its config or skills directory already
exists. An absent host is skipped, not failed. `--all-hosts` registers everything.

### Symlinks, recursion, and duplicate listings

Three properties decide how well a host handles this installation, and they are worth stating
plainly rather than implying:

- **Symlinks.** Every host in the table above loads a skill directory reached through a symlink in
  practice. Kiro's documentation does not state symlink behaviour either way; it works, and
  `agent-skills verify` is how you confirm it on your machine rather than trusting this table.
- **Recursive discovery.** Cursor documents that it walks the skills root recursively. That is how
  the two nested support skills (`issue-investigator`, `code-reviewer`) are found inside
  `software-engineer/skills/`. Hosts that do not recurse still see the parent skill, which loads its
  nested references itself. Kiro's recursion depth is not documented.
- **Duplicate discovery.** Several hosts deliberately scan each other's directories. Cursor reads
  `~/.agents/skills`, `~/.cursor/skills`, `~/.claude/skills`, and `~/.codex/skills`. VS Code reads
  `~/.copilot/skills`, `~/.claude/skills`, and `~/.agents/skills`. So one host can list the same
  skill more than once, and **no** assignment of directories avoids that.

  The mitigation is not to fight it. Because every registration is a symlink to the same canonical
  tree, a duplicate listing is the same file at the same version — the invariant that actually
  matters (never merge instructions from two versions of one skill) holds by construction.
  `agent-skills verify` asserts that realpath identity instead of asserting a uniqueness the hosts
  do not offer.

### Claude Code

`~/.claude/skills/` is the personal skills directory. Installed automatically. Confirm with
`/skills` in a session, or:

```bash
agent-skills verify
```

### Cursor

`~/.cursor/skills/` is registered automatically, and Cursor also picks the skills up from
`~/.agents/skills/`. Confirm by typing `/` in chat.

Cloud Agents are the one place a local install can partially reach: enable *Settings → Agents → Sync
Skills for Cloud Agents* and Cursor syncs `~/.cursor/skills` only. `~/.agents/skills` and unsynced
skills stay local. For self-hosted workers, use project skills in the repository or bake them into
the worker image.

### VS Code and GitHub Copilot

`~/.copilot/skills/` is the personal directory; VS Code also reads `~/.claude/skills/` and
`~/.agents/skills/`. Both are registered, so Copilot finds the skills with no configuration.

Skills appear as slash commands: type `/` in chat, or run *Chat: Open Customizations* from the
command palette and open the Skills tab. Repository-scoped skills additionally live in
`.github/skills/`, which is the path to use for the Copilot **coding agent** on github.com — that
runs remotely and cannot see your machine.

This replaces the pre-v0.37.0 guidance that Copilot had no native skill discovery. It does now.

### Codex

`~/.agents/skills/` is the documented user scope, and `~/.codex/skills/` is also read by some
builds. Both are registered, because shipping only one has caused skills to go undiscovered after an
update. Invoke with `$` followed by the skill name.

### Kiro

`~/.kiro/skills/` is the global directory for the IDE and CLI, and honours `KIRO_HOME`. A workspace
skill of the same name takes precedence over a global one. Discovered skills appear in the `/`
slash-command menu, and `/config skills` lists them with their source.

### JetBrains AI Assistant

This is the one host that needs a manual action, and the installer says so rather than claiming
otherwise. Global skill directories are IDE settings state, not a filesystem convention, so nothing
outside the IDE can register one safely.

Once, per IDE:

*Settings → Tools → AI Assistant → Skills →* the **Skills Settings** button *→ Manage Skill
Directories →* add a **Global** entry pointing at:

```text
~/.agent-skills/skills
```

Global entries are available across every project. The IDE may also detect the Claude Code and Codex
directories and offer to *import* skills from them; import copies into IDE storage, which creates a
second copy that will not track updates. Prefer the directory entry above.

### Windsurf and Continue

Registered when detected. Both are less thoroughly documented than the hosts above, so treat the
table as a starting point and confirm in the host UI. Continue also accepts skills referenced from
its rules files.

### ChatGPT, Claude web, and generic chat

No filesystem access, so nothing to install. Attach or paste the relevant `SKILL.md`, plus
`.agent-skills.yml` if the repository has one, and say which mode applies.

## Pre-execution enforcement

The table above answers "where does this host discover skills". A different question is "can
this host stop a dangerous command before it runs", and the answer is not the same per host.
[Execution Guard](execution-guard.md) covers that, `lib/guard.registry` is its source of truth,
and `agent-skills guard doctor` reports the live status on your machine.

| Host | Enforcement | Mechanism |
| --- | --- | --- |
| Claude Code | `enforced` | `PreToolUse` hook, native allow/ask/deny |
| Cursor | `enforced` | `beforeShellExecution` + `beforeMCPExecution`, registered `failClosed` |
| Kiro | `enforced` | `preToolUse` hook; blocking is by non-zero exit |
| Codex | `enforced` | `PreToolUse` hook, Claude-compatible contract |
| GitHub Copilot / VS Code | `partial` | terminal auto-approval rules; cannot consult the guard |
| JetBrains AI / Junie | `advisory` | Action Allowlist; no external pre-execution callout |
| Windsurf | `advisory` | none documented |
| Continue | `advisory` | none documented |

A host that discovers skills well can still enforce nothing, and the reverse is possible too.
`enforced` is claimed only where the host documents a blocking contract **and** the hook is
actually registered on this machine; a hook-capable host that has not been set up reports
`available`. For `partial` and `advisory` hosts, `agent-skills guard run -- '<command>'` is the
wrapper fallback.

## The lifecycle commands

Every skill runs these, and they work from any repository:

```bash
agent-skills start-task --skill <skill-name>
agent-skills finish-task --skill <skill-name> --summary "<one sentence outcome>"
```

If `agent-skills` is not on `PATH` — a hook with a minimal environment, for example — the absolute
form always resolves:

```bash
"${AGENT_SKILLS_HOME:-$HOME/.agent-skills}/bin/agent-skills" start-task --skill <skill-name>
```

If an assistant cannot run shell commands at all, put these in the operator checklist and require
the assistant's final answer to include the lifecycle receipt from the skill's output contract. Full
contract: [lifecycle-preflight.md](lifecycle-preflight.md).

## Cloud and remote agents (`in-repo`)

These run on a machine you do not control and cannot reach your home directory. The pattern is the
same for all of them:

1. Commit `.agent-skills.yml` at the repository root (see
   [`.agent-skills.example.yml`](../.agent-skills.example.yml)). No secrets.
2. Vendor the skills you use into the repo — `.agent-skills/skills/` via copy or `git submodule
   add`, or `.github/skills/` for Copilot's coding agent.
3. Reference them from the platform's instruction surface.
4. Add `.cache/` to the repository's `.gitignore`.
5. Inject secrets through the platform's own secret mechanism.

### GitHub Copilot coding agent

Reference the vendored `SKILL.md` from `.github/copilot-instructions.md`, or put skills in
`.github/skills/` where the coding agent and Copilot code review both look. Repository or
organisation Actions secrets become the environment variables the skills read.

### Cursor cloud and background agents

Either vendor into the repo, or enable personal-skill sync for `~/.cursor/skills` (above). Use
Cursor's secret store for credentials.

### Devin, Codex cloud, and similar

Add the vendored `SKILL.md` to project knowledge or repo-onboarding instructions so it loads before
each session.

### Codespaces and Gitpod

The repo is the workspace. Commit `.agent-skills.yml`, treat it as `in-repo`, and use Codespaces user
or repo secrets.

### Claude web

Attach the relevant `SKILL.md` and `.agent-skills.yml` to the project so they load into every
conversation there.

## Related

- [Installation](installation.md) — what the installer writes, and the flags.
- [Execution modes](execution-modes.md) — local versus remote, in full.
- [Skill-source resolution](skill-source-resolution.md) — which directory an agent must load from.
- [Access resolution](access-resolution.md) — how a skill reaches an external service.
- [Hooks](../hooks/README.md) — optional templates that make the lifecycle deterministic.
