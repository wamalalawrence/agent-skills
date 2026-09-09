# Installation

Tested on macOS and Linux with `bash` 3.2+ and `zsh`. Windows users should run via WSL or Git Bash;
native PowerShell is not supported.

## Install once, per machine

```bash
git clone https://github.com/wamalalawrence/agent-skills.git
cd agent-skills
./setup.init
```

That is the entire local installation. You do not run it again per workspace, per repository, or per
project.

What it does:

- establishes one canonical installation under `AGENT_SKILLS_HOME` (default `~/.agent-skills`);
- registers the skills with every supported agent host it finds on the machine;
- links the `agent-skills` launcher into a directory on your `PATH`;
- creates the non-secret user config directory;
- writes update and version metadata, then verifies the result.

What it does **not** do, by design:

- ask which workspace or repositories you work in;
- ask for a Jira, Confluence, Sonar, GitHub, database, cloud, or API credential;
- ask for project keys, organisations, or deployment environments;
- create a workspace `.env`, `.jira-config.yml`, or `.skills` symlink;
- store a secret of any kind.

Installation, project configuration, and authentication are three separate concerns. This command
owns only the first. Access to an external service is resolved when a task needs it — see
[access-resolution.md](access-resolution.md).

## The layout it creates

```text
~/.agent-skills/            # AGENT_SKILLS_HOME — the canonical installation
├── install.json            # version, source, registered hosts, timestamps
├── VERSION
├── skills   -> <clone>/skills
├── scripts  -> <clone>/scripts
├── lib      -> <clone>/lib
├── bin      -> <clone>/bin
├── docs     -> <clone>/docs
└── hooks    -> <clone>/hooks

~/.config/agent-skills/     # non-secret user state (XDG_CONFIG_HOME aware)
├── credentials.json        # profile metadata only — never a secret value
└── bindings.json           # which identity a repository uses

~/.local/bin/agent-skills -> ~/.agent-skills/bin/agent-skills
```

Every tree is a symlink into the clone, so there is exactly **one** copy of each skill on the
machine and `git pull` in the clone updates everything at once. The clone can live anywhere; move it
and rerun `./setup.init` to re-point the install.

## Host registration

Each host gets one symlink per skill inside its own global skills directory:

```text
~/.claude/skills/wamala -> ~/.agent-skills/skills/wamala
~/.agents/skills/wamala -> ~/.agent-skills/skills/wamala
```

Per-skill links rather than a directory replacement is what makes this safe next to skills you
already installed: the installer only ever creates, inspects, or removes links whose target lives
inside `AGENT_SKILLS_HOME`. A real directory or a link pointing somewhere else is left alone and
reported.

Hosts are registered when they are detected on the machine. An absent host is skipped, not failed.
See [assistants.md](assistants.md) for the per-host table, including which directories each host
scans and what that means for duplicate listings.

```bash
agent-skills hosts          # what is supported and what is registered
agent-skills hosts --json   # the same, machine-readable
```

## Verify

```bash
agent-skills verify
```

Reports the installed version, the canonical source, every host integration and whether it resolves
to the canonical tree, runtime and lifecycle-helper availability, the credential-store backend
(without listing any secret), legacy installation remnants, version drift, and the cloud limitation.

```bash
agent-skills doctor         # what this environment can actually do
agent-skills doctor --json
```

## Flags

| Flag | Purpose |
| --- | --- |
| `--yes` | Non-interactive; accept safe defaults. |
| `--hosts a,b,c` | Register only these host ids (see `agent-skills hosts`). |
| `--all-hosts` | Register every supported host, detected or not. |
| `--no-path-link` | Do not link the launcher into a `PATH` directory. |
| `--verify` | Check the installation and report problems. Writes nothing. |
| `--check-updates` | Compare local `VERSION` against the latest release tag on `origin`. Exits `0` up-to-date, `10` update available, `2` setup error. |
| `--update` | Fetch tags, check out the latest release (or `--branch NAME`), refresh the install. Refuses on a dirty working tree. |
| `--legacy-workspace` | Use the pre-v0.37.0 workspace model instead. |
| `--workspace-root PATH` | Legacy workspace root. Implies `--legacy-workspace`. |
| `--help` | Show usage. |

The legacy Jira/Confluence/Sonar/environment flags (`--with-jira`, `--no-confluence`, …) still exist
and still select the legacy model, because that is the only model in which they mean anything.

Environment overrides, useful for testing and for unusual layouts:

| Variable | Effect |
| --- | --- |
| `AGENT_SKILLS_HOME` | Install root. Default `~/.agent-skills`. |
| `AGENT_SKILLS_CONFIG_DIR` | Non-secret user state. Default `$XDG_CONFIG_HOME/agent-skills` or `~/.config/agent-skills`. |
| `AGENT_SKILLS_SOURCE` | Use this source tree instead of the detected one. |
| `AGENT_SKILLS_CACHE_DIR` | Where per-task artifacts go. Default: `<repo>/.cache/agent-skills`. |
| `AGENT_SKILLS_MODE` | Force `global`, `in-repo`, or `local-workspace`. |
| `AGENT_SKILLS_STRICT_BINDING` | Require an explicit credential binding. See [access resolution](access-resolution.md). |

## Using it from a repository

Nothing to set up. Open the repository and invoke a skill by name; the host discovered it globally.
Skills call their own runtime through the launcher:

```bash
agent-skills start-task --skill software-engineer
agent-skills finish-task --skill software-engineer --summary "<one sentence outcome>"
```

If `agent-skills` is not on `PATH` — for example in a hook that runs with a minimal environment —
the absolute form always works:

```bash
"${AGENT_SKILLS_HOME:-$HOME/.agent-skills}/bin/agent-skills" start-task --skill software-engineer
```

Project context is inferred from the repository itself:

```bash
agent-skills project          # git root, remote, base branch, stack, build, format, CI
agent-skills project --json
```

A repository with no `agent-skills` configuration is a normal, supported case. Anything that could
not be inferred safely appears under `needs_confirmation` rather than being asserted. Committed
configuration is optional and wins where present — see [configuration.md](configuration.md).

## Execution Guard (separate, opt-in)

`agent-skills install` does **not** register [Execution Guard](execution-guard.md). It prints a
recommendation and the exact commands, and stops.

The reason is scope of consent. Registering the guard edits host configuration files the user
owns — `~/.claude/settings.json`, `~/.cursor/hooks.json`, `~/.kiro/hooks/`, `~/.codex/hooks.json`
— and those files decide what the user's agent is allowed to do. Changing them as a side effect
of "install the skills" would be a surprise in the one category where surprises are least
acceptable. Nothing about a security tool justifies installing it without being asked.

```bash
agent-skills guard install --dry-run   # print every change; write nothing
agent-skills guard install             # register the hooks
agent-skills guard verify              # confirm the registrations
agent-skills guard doctor              # per-host enforcement level
agent-skills guard uninstall           # remove only agent-skills-owned entries
```

`--hosts a,b` limits the operation to named hosts. `--all-hosts` registers every hook-capable
host including undetected ones.

What installation does to each file:

| Host | File | Change |
| --- | --- | --- |
| Claude Code | `~/.claude/settings.json` | two `hooks.PreToolUse` entries appended |
| Cursor | `~/.cursor/hooks.json` | one entry each on `beforeShellExecution` and `beforeMCPExecution`, with `failClosed` |
| Kiro | `~/.kiro/hooks/agent-skills-guard.json` | a new file it owns entirely |
| Codex | `~/.codex/hooks.json` | two `PreToolUse` entries appended |

Every one of those is a merge, never a replacement:

- Hooks you already had survive, including ones on the same event.
- The first modification leaves `<name>.agent-skills-guard.bak` beside the file.
- A file that is not valid JSON is refused rather than overwritten.
- A same-named file the installer did not write is left alone.
- Running it twice produces one registration, not two.
- `uninstall` removes only entries carrying the `guard check-tool --host` signature.

Ownership is recorded at `<config-dir>/guard/hosts.json`, alongside the local decision log. The
guard's own uninstall is separate from `agent-skills uninstall`, so removing the skills does not
silently strip a security control the user asked for — run both when that is what you want.

## Uninstall

```bash
agent-skills uninstall            # remove registrations, links, and install metadata
agent-skills uninstall --purge    # also remove credential metadata and project bindings
```

It removes only paths this project owns. Skills you installed yourself survive, the source clone is
untouched, and secrets held in an OS keychain are never removed implicitly — that needs an explicit
`agent-skills access forget --profile <name>`.

## Upgrading from v0.36.x workspace installation

Before v0.37.0, `setup.init` wrote into a parent workspace folder:

```text
~/work/
├── agent-skills/
├── repo-a/
├── repo-b/
├── .env                  <- credentials in plaintext
├── .jira-config.yml
├── .skills -> agent-skills/skills
└── .agent-skills.lock
```

That still works. Nothing about the upgrade is forced, and nothing is deleted.

### What changed

| v0.36.x | v0.37.0 |
| --- | --- |
| Setup per workspace | Install once per machine |
| `<workspace>/.skills` symlink | Host registrations into each agent's global skills dir |
| `bash agent-skills/scripts/start-task.sh` | `agent-skills start-task` |
| `PROJECTS_JSON` registered up front | Project context inferred from each repository |
| Credentials prompted at install, stored in `.env` | Resolved on demand, stored in the OS keychain |
| Credentials belonged to a workspace | Credentials belong to named identities |

### The move

```bash
cd agent-skills
git pull
./setup.init                             # installs globally; asks for nothing
agent-skills verify                      # confirm every host sees the skills
agent-skills migrate                     # what is now obsolete, and what is still read
```

`migrate` is read-only. It reports:

- `.skills` and `.agent-skills.lock` as obsolete — they carry no information the global install
  needs;
- `.env`, `.env.local`, `.jira-config.yml`, and `.agent-skills.yml` as **still discovered** by the
  access resolver, so leaving them in place costs nothing.

Optionally move legacy credentials into named identities:

```bash
agent-skills access import-legacy         # read-only report; nothing is copied
agent-skills access import-legacy --apply # opt-in
```

Import never displays a secret value and never deletes a legacy file. If a token sat in plaintext
long enough to worry you, rotate it — moving it does not un-expose it.

Then, when you are satisfied:

```bash
agent-skills migrate --remove-obsolete    # removes only .skills and .agent-skills.lock
```

`.env` is never removed automatically. It may be your only copy of a token, and the resolver still
reads it.

### Staying on the legacy model

```bash
./setup.init --legacy-workspace
./setup.init --verify --workspace-root /path/to/work
```

An inherited `WORKSPACE_ROOT` pointing at a directory with a `.env` also selects the legacy model,
so an existing shell profile or script keeps behaving as it did.

## Cloud and remote agents (`in-repo`)

A cloud agent runs on someone else's machine and cannot read your home directory, so the global
install does not reach it. Those environments use an in-repo mechanism:

1. Copy [`.agent-skills.example.yml`](../.agent-skills.example.yml) to `.agent-skills.yml` at the
   **target repository's** root and fill in the `project:` block. It contains **no secrets**.
2. Vendor the skills the agent needs into the repo — copy or `git submodule add` this repository
   under `.agent-skills/` — or reference specific `SKILL.md` files from the agent's instruction
   surface (`.github/copilot-instructions.md`, `.cursor/rules/*.mdc`, attached files).
3. Add `.cache/` to that repository's `.gitignore`.
4. Inject any required secrets through the host platform's own secret mechanism.

See [execution-modes.md](execution-modes.md) for the full comparison and
[assistants.md](assistants.md) for per-platform notes.

## Manual installation

Supported when you want full control. The install is only symlinks and a manifest:

```bash
mkdir -p ~/.agent-skills
ln -s /path/to/agent-skills/skills  ~/.agent-skills/skills
ln -s /path/to/agent-skills/scripts ~/.agent-skills/scripts
ln -s /path/to/agent-skills/lib     ~/.agent-skills/lib
ln -s /path/to/agent-skills/bin     ~/.agent-skills/bin
ln -s ~/.agent-skills/skills/software-engineer ~/.claude/skills/software-engineer
```

`agent-skills verify` will report the missing manifest; run `./setup.init` once to write it.

## Related

- [Quickstart](quickstart.md) — the shortest useful path.
- [Access resolution](access-resolution.md) — how external access is established, lazily.
- [Configuration](configuration.md) — optional committed project configuration.
- [Execution modes](execution-modes.md) — global, in-repo, and legacy workspace.
- [Assistants](assistants.md) — per-host discovery paths and verification.
- [Skill-source resolution](skill-source-resolution.md) — which directory an agent loads from.
- [Updates](updates.md) — noticing and applying a new release.
- [Known limitations](known-limitations.md) — what none of this guarantees.
