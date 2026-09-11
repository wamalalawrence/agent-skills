# Installation

Tested on macOS and Linux with `bash` 3.2+ and `zsh`. Windows users should run via WSL or Git Bash;
native PowerShell is not supported.

Requires Python 3.8 or newer, `bash`, and `git`.

## Install once, per machine

```bash
npx @wamalalawrence/agent-skills install
```

That is the entire local installation. No clone, no `cd`. You do not run it again per workspace, per
repository, or per project.

The npm package is a bootstrap: it checks the machine can run the installer and hands over to it.
The product is not inside the package — it is downloaded from the release source and verified. After
installing, the durable command is `agent-skills` and npm is not needed again.

What it does:

- resolves the latest release from a [release provider](release-providers.md);
- downloads the payload, checks it against the hash the release was published with, and runs its
  runtime once in a staging directory before anything points at it;
- activates it under `AGENT_SKILLS_HOME` (default `~/.agent-skills`);
- registers the skills with every supported agent host it finds on the machine;
- links the `agent-skills` launcher into a directory on your `PATH`;
- creates the non-secret user config directory, then verifies the result.

### The installation is a transaction

```text
RESOLVE -> DOWNLOAD -> VERIFY -> STAGE -> SELF-TEST -> ACTIVATE -> HOSTS -> VERIFY
```

Everything up to and including the self-test happens off to the side. If any of it fails, the
machine has not been touched and the release you were already running is still the one you are
running. Only `ACTIVATE` changes anything, and it is a single atomic symlink swap. If activation or
host registration fails after that point, the previous release is put back.

There is no state in which some hosts are on one version and some on another, because hosts do not
point at versions — they point at `~/.agent-skills/skills`, which points at `current`.

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
├── current -> versions/0.43.0     the only pointer that decides what runs
├── versions/
│   ├── 0.42.0/                    the previous release, kept for rollback
│   └── 0.43.0/                    skills, scripts, lib, bin, docs, release.json
├── state/                         install history; survives every upgrade
├── cache/                         downloads; safe to delete
├── install.json                   version, provider, registered hosts, timestamps
├── VERSION                        the active version, as plain text
├── skills   -> current/skills
├── scripts  -> current/scripts
├── lib      -> current/lib
├── bin      -> current/bin
├── docs     -> current/docs
└── hooks    -> current/hooks

~/.config/agent-skills/     # non-secret user state (XDG_CONFIG_HOME aware)
├── credentials.json        # profile metadata only — never a secret value
└── bindings.json           # which identity a repository uses

~/.local/bin/agent-skills -> ~/.agent-skills/bin/agent-skills
```

Two properties follow from this shape, and most of the rest of the design rests on them.

**A version directory is complete.** The skills, the runtime, and the docs of one release live
together and are never mixed, because `current` can only point at one of them. A skill discovered
from any repository reaches helpers from its own release.

**Every stable path goes through `current`.** A host registration points at
`~/.agent-skills/skills/<name>`; an Execution Guard hook points at `~/.agent-skills/bin/agent-skills`.
Activating a release repoints one symlink and every host, every hook, and every skill follows in the
same instant. Nothing has to be rewritten per host.

Credentials are deliberately outside all of it, so removing an installation cannot destroy an
identity.

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

Reports the active release, whether the manifest, `current`, and the payload all agree on a version,
every host integration and whether it resolves to the canonical tree, runtime and lifecycle-helper
availability, the credential-store backend (without listing any secret), what a rollback would
return to, legacy installation remnants, and the cloud limitation. It writes nothing and prints no
secret. Exit `0` healthy, `7` when something is wrong.

```bash
agent-skills doctor         # what this environment can actually do
agent-skills doctor --json
```

## Commands and flags

```bash
agent-skills install [--version X] [--channel stable|rc] [--hosts a,b] [--all-hosts]
agent-skills update  [--version X] [--channel stable|rc] [--allow-downgrade]
agent-skills rollback [--version X]
agent-skills versions [--json] [--local]
agent-skills check-updates [--json]
agent-skills provider [--json]
agent-skills verify | doctor | hosts | uninstall
```

| Flag | Purpose |
| --- | --- |
| `--version X` | Install or update to this exact release rather than the latest. |
| `--channel stable\|rc` | Which release line to follow. Remembered, so one `--channel rc` keeps later commands on that line. Default `stable`, which never offers a pre-release. |
| `--source DIR` | Install from a local source tree instead of the remote. Selects the `local` provider. |
| `--repo URL` | Use a different git remote as the release source. |
| `--provider local\|git` | Choose the release provider explicitly. |
| `--hosts a,b,c` | Register only these host ids (see `agent-skills hosts`). |
| `--all-hosts` | Register every supported host, detected or not. |
| `--no-path-link` | Do not link the launcher into a `PATH` directory. |
| `--allow-downgrade` | Permit `update` to replace the active release with an older one. |
| `--keep N` | How many releases to retain for rollback. Default `2`. |
| `--purge` | With `uninstall`: also remove credential metadata and project bindings. |
| `--home DIR` | Install into a different root. Useful for testing a branch without touching the real install. |

Exit codes are a stable contract; see [versioning.md](versioning.md#exit-codes).

Environment overrides, useful for testing and for unusual layouts:

| Variable | Effect |
| --- | --- |
| `AGENT_SKILLS_HOME` | Install root. Default `~/.agent-skills`. |
| `AGENT_SKILLS_CONFIG_DIR` | Non-secret user state. Default `$XDG_CONFIG_HOME/agent-skills` or `~/.config/agent-skills`. |
| `AGENT_SKILLS_SOURCE` | Use this source tree instead of the detected one. |
| `AGENT_SKILLS_CACHE_DIR` | Where per-task artifacts go. Default: `<repo>/.cache/agent-skills`. |
| `AGENT_SKILLS_MODE` | Force `global` or `in-repo`. |
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

It removes only paths this project owns: the installed releases under `versions/`, the activation
pointer, the launcher link, host registrations that resolve into the install root, and Execution
Guard hook entries carrying this project's signature.

It does not remove skills you installed yourself, hooks you wrote yourself, your credential
identities, your project bindings, per-project memory, or a repository's committed knowledge base.
Secrets held in an OS keychain are never removed implicitly — that needs an explicit
`agent-skills access forget --profile <name>`. `--purge` additionally removes the credential
metadata and bindings, and is the only thing that does.

## Upgrading from an earlier release

```bash
npx @wamalalawrence/agent-skills install
```

The installer recognises an existing installation, moves it onto the versioned layout, and leaves
everything you own alone. Nothing is deleted and no secret is copied without you asking.

| Before v0.43.0 | v0.43.0 |
| --- | --- |
| Clone the repository, run `./setup.init` | `npx @wamalalawrence/agent-skills install` |
| Install trees linked into a clone you maintain | Releases copied into `~/.agent-skills/versions/` |
| `agent-skills update` was `git pull` in that clone | A staged, verified, transactional update |
| A failed update left the clone in whatever state it reached | A failed update leaves the previous release running |
| No way back from a bad release | `agent-skills rollback` |
| The clone had to keep existing | The installation is self-contained |

The old clone is no longer needed once you have installed, and can be removed.

### Coming from the pre-v0.37 workspace layout

Before v0.37.0, setup wrote into a parent workspace folder:

```text
~/work/
├── agent-skills/
├── repo-a/
├── .env                  <- credentials in plaintext
├── .jira-config.yml
├── .skills -> agent-skills/skills
└── .agent-skills.lock
```

Nothing writes that layout any more, and v0.43.0 removed the code that did. Nothing is deleted
either: the access resolver still reads an existing `.env`, `.env.local`, `.jira-config.yml`, and
`.agent-skills.yml`, so leaving them in place costs nothing.

```bash
agent-skills migrate                      # what is now obsolete, and what is still read
agent-skills migrate --remove-obsolete    # removes only .skills and .agent-skills.lock
```

`migrate` is read-only by default, and `.env` is never removed automatically — it may be your only
copy of a token.

Optionally move legacy credentials into named identities:

```bash
agent-skills access import-legacy         # read-only report; nothing is copied
agent-skills access import-legacy --apply # opt-in
```

Import never displays a secret value and never deletes a legacy file. If a token sat in plaintext
long enough to worry you, rotate it — moving it does not un-expose it.

### Flags that were removed in v0.43.0

`--legacy-workspace`, `--workspace-root`, `--with-jira`, `--no-jira`, `--with-confluence`,
`--with-sonar`, `--with-environments`, `--symlink`, and `--no-symlink` are gone, along with the code
that acted on them. They belonged to a model that wrote credentials to disk during installation.
Passing one now prints what replaced it rather than failing silently.

## Working on Agent Skills itself

`setup.init` remains as a development helper. It installs the working tree you are standing in, as a
development release, through the same installation engine:

```bash
./setup.init                          # install this checkout
./setup.init --home /tmp/as-test      # into a throwaway root, leaving your real install alone
agent-skills versions --local         # which releases are installed, and which is active
```

A development install is recorded as such in the manifest and reported by `agent-skills doctor`, so
an unreleased branch is never mistaken for a release.

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

## Installing without npm

The npm package is a convenience, not a dependency. Any release can be installed directly:

```bash
git clone https://github.com/wamalalawrence/agent-skills.git
cd agent-skills
./setup.init
```

This is the same installation engine reached a different way, and it produces the same versioned
layout. It is the supported path for contributors and for machines with no Node.js.

## Related

- [Quickstart](quickstart.md) — the shortest useful path.
- [Access resolution](access-resolution.md) — how external access is established, lazily.
- [Configuration](configuration.md) — optional committed project configuration.
- [Execution modes](execution-modes.md) — global and in-repo.
- [Release providers](release-providers.md) — where releases come from, and distribution access.
- [Assistants](assistants.md) — per-host discovery paths and verification.
- [Skill-source resolution](skill-source-resolution.md) — which directory an agent loads from.
- [Updates](updates.md) — noticing, applying, and undoing a release.
- [Known limitations](known-limitations.md) — what none of this guarantees.
