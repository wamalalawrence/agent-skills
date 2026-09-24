# Access Discovery

"MCP configured" used to be the whole answer to "can I update this page?". It is the wrong
answer surprisingly often: the server may be read-only, a tool filter may have removed the write
tools, a scope filter may hide the page, or the server may be a company launcher script whose mode
nobody reported. Access Discovery replaces that one bit with seven questions, asked for one
operation on one target, before any dependent work starts.

```bash
agent-skills access scan                       # what every host on this machine can reach, statically
agent-skills access check --system confluence --op update \
  --target "https://example.atlassian.net/wiki/spaces/~me/pages/123/Notes" --user-authorised --own-target
```

It knows nothing about any organisation. Public knowledge about upstream MCP servers ships in a
small registry; everything specific to your employer - a launcher's name, its mode switch, the
keychain item it reads, your site's URL - is learned on your machine and kept in your own config.

It sits beside the [Access Resolver](../access-resolution.md), which answers "can I
authenticate?". Access Discovery answers "can this host do this operation on this target, and via
what?". Neither answers "may I?" - that stays with the
[destructive-action policy](../destructive-action-safety.md).

## The ladder

Every check walks these rungs for one (system, operation, target) and stops at the first failure.

| Rung | Question |
| --- | --- |
| `route` | Is there a route for this system in the current host (MCP server, CLI)? |
| `launch` | Can it start? The command exists and is executable; `uvx`, `docker`, `npx` are present. |
| `auth` | Is a credential present for this route, and (with `--probe`) accepted? |
| `mode` | Does the route's mode allow this operation: read-only flags, tool allow-lists, toolsets? |
| `target` | Is the target inside the route's scope filters, and (with `--probe`) permitted? |
| `intent` | Did the user ask for this operation on this target in the current request? |
| `policy` | Does policy allow it via this route, and what confirmation does it need? |

Each rung reports `pass`, `fail`, `unknown` or `skipped`, the evidence, and how strong it is:

| Strength | Means |
| --- | --- |
| `verified` | a probe or live introspection answered it |
| `declared` | explicit configuration, an upstream's documented default, or a fact you confirmed |
| `inferred` | read from a launcher script or guessed from a name |

`unknown` is never shown as `pass`. A write whose `mode` or `target` rests on `inferred` evidence
comes back `needs-confirmation`: Wamala tells you what it inferred, and from which file and line,
and asks before relying on it.

## Reading a check

```text
Access check: confluence · update · page 123456789 (space ~jdoe) · host codex
  route    pass     MCP server "atlassian" -> ~/.local/bin/acme-mcp-atlassian (user-local launcher)   [declared]
  launch   pass     launcher executable; uvx available   [declared]
  auth     pass     credential present (keychain-generic acme-atlassian, referenced by the launcher)   [inferred]
  mode     FAIL     read-only: launcher ~/.local/bin/acme-mcp-atlassian: READ_ONLY_MODE is set to read-only
                    unless ACME_ATL_RW=1; host config does not set ACME_ATL_RW   [inferred]
  target   skipped
  intent   skipped
  policy   skipped
Result: BLOCKED at mode.
Credentials found (locators only; a found credential is not a route):
  keychain-generic acme-atlassian (present)
Options:
  1. Confirm what I inferred from ~/.local/bin/acme-mcp-atlassian line 14, 15
  2. Add a separate write profile for this host (the read-only entry stays as it is), using ACME_ATL_RW=1
  3. Do it once yourself: I prepare the exact change and the link, and finish the rest of the task
```

The names are invented; this is the regression fixture for the incident that motivated the
feature. `--json` gives the same answer as `agent-skills.access-check/v1`:
`system, operation, target, host, rungs[{id, status, strength, evidence, fix_options}], result,
blocked_at, routes[...], found_credentials[{source, locator, system_guess, present}]`. Locators
only, never values, and everything passes through [redaction](../secret-boundary.md). Every
`access` discovery command takes `--json`; `setup`, `remember`, `forget` and `record` return
`agent-skills.access-command/v1` (`command`, `exit_code`, `result`, `messages`, `errors`), and a
`--json` run is never interactive, so `setup --json` only proposes.

### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | available |
| `1` | needs you: confirm inferred evidence, state intent, name the host, or set up a route |
| `2` | usage error, or an access-policy file that fails closed |
| `3` | authentication required (`auth` failed) |
| `4` | network failure during a probe |
| `11` | capability unavailable: the route works, but its mode, scope, or policy excludes this operation |

`11` is new in 1.5.0 and joins the frozen contract in `lib/asrelease/exits.py`
(`agent-skills verify --explain-codes`).

## Failure classes and their fixes

| Blocked at | Typical cause | What to do |
| --- | --- | --- |
| `route` | no MCP server or CLI for the system in this host | `agent-skills access setup <system>` prints the steps; or tell Wamala which tool you use |
| `route` (unknown) | routes differ by host and the current host is unknown | say which assistant you are in, or pass `--host` |
| `route` (needs confirmation) | one route is blocked by its own setting and another could do it | choose deliberately: use the other route, add a write profile, or hand off |
| `launch` | the launcher or its runtime (`uvx`, `docker`) is missing | install it or fix the path |
| `auth` | no credential, or a launcher reads an item that does not exist | store a token yourself: `agent-skills access set ... --secret-field token` |
| `mode` | read-only flag, tool allow-list, or toolset without write tools | a write profile: `agent-skills access setup <system> --write-profile --target <t>` |
| `target` | a scope filter excludes the target ("looks missing, not forbidden") | a write profile scoped to that space or project |
| `target` | the account lacks the permission (`--probe`) | ask the space or project owner for exactly that permission |
| `intent` | the request did not ask for this operation | Wamala asks you |
| `policy` | your policy file denies it, or it needs explicit confirmation | confirm, or leave it denied |

Manual hand-off is always offered: Wamala prepares the exact content or diff and the link, you
apply it, and the rest of the task continues.

## Where routes come from

**Host configuration.** One reader per host; each returns the same normalised entry. Values are
read only for mode, filter, and base-URL keys; every other key is kept as a name. Settings passed
in the server's arguments count too: `docker run -e READ_ONLY_MODE=true ...` is as binding as an
`env` block, and a launcher started through its interpreter (`bash ~/bin/wrapper.sh`,
`python3 wrapper.py`) is inspected as the script, not as `bash`.

| Host | Files |
| --- | --- |
| Claude Code | `~/.claude.json` (user, and `projects[<repo>].mcpServers`), `<repo>/.mcp.json` |
| Claude Desktop | `claude_desktop_config.json` under Application Support (macOS) or `~/.config/Claude` (Linux) |
| Codex | `~/.codex/config.toml` (`[mcp_servers.<name>]`, `CODEX_HOME` honoured), `<repo>/.codex/config.toml` |
| Cursor | `~/.cursor/mcp.json`, `<repo>/.cursor/mcp.json` |
| VS Code / Copilot | user `mcp.json` and `settings.json` (`mcp.servers`), `<repo>/.vscode/mcp.json` (`servers`) |
| Kiro | `~/.kiro/settings/mcp.json` (`KIRO_HOME` honoured), `<repo>/.kiro/settings/mcp.json` |

Codex is TOML on a Python 3.8 baseline, so a small parser reads the subset MCP tables use;
`tomllib` is used where it exists. A file that cannot be parsed makes that host's servers
**unknown**, never absent.

**The current host.** `--host` first, then `AGENT_SKILLS_HOST`, then `CLAUDECODE=1` (set by Claude
Code, including inside the desktop app). Nothing else was found reliable, so otherwise every
detected host is evaluated and labelled, and a check whose answer differs by host asks you which
one you are in.

**The system registry** (`lib/access/systems/*.json`): public upstream knowledge per system - known
MCP packages and images, their mode and filter settings, their write tools, target URL parsers,
and non-mutating probes - each with the upstream source and date it was checked against. Adding a
system is adding a file. See [Atlassian](atlassian.md), [GitHub](github.md), [GitLab](gitlab.md).

**The launcher inspector.** When a server's command is a script rather than a known package, it is
read, never run: at most 64 KB, binaries skipped, comments stripped. It finds the upstream the
script launches, assignments to the upstream's mode keys and the condition around them (the
script's own switch and its default), credential references (keychain, secret service, `pass`,
`op`, keyring, `.netrc`, files, environment - as locators), and base URLs. Everything it concludes
is `inferred` and cites file and line. `agent-skills access inspect <command>` shows the report.
A launcher can also describe itself: [for launcher authors](for-launcher-authors.md).

**Local route knowledge** (`<config>/access/routes.json`, `0600`): what you confirmed. A launcher's
switch, the systems it serves, your site's URL, the keychain item's name. It turns `inferred` into
`declared`, is written only after you confirm (`agent-skills access remember`), holds no secrets,
matches by launcher path so a write profile that reuses the launcher inherits it, and goes
**stale** when the launcher changes. `agent-skills access forget <system>|--all` removes it;
`forget --profile NAME` still removes a credential identity, as before.

## Credentials: found is not usable

A found credential is evidence that a route *could* be set up. It is never a route. A stored token
carries its account's full permissions; a read-only MCP server is read-only because of the process
holding the token. Using the token directly would route around your own safety setting.

Presence is checked without reading a value: `security find-generic-password -s <name>` without
`-w`, a `pass` entry's file, a `.netrc` machine line, an environment variable's name. Where a tool
cannot prove presence without printing the secret (`secret-tool`, `op`, keyring), the answer is
`unknown` and you are asked. The keychain is never listed.

`--probe` answers are kept for 10 minutes (keyed by system, site, target, operation and identity
name - never a value; network failures are not kept) and say "probed N min ago"; `--fresh` asks
again. `--probe` makes non-mutating permission queries (Confluence `expand=operations`, Jira
`mypermissions`, `gh api repos/<o>/<r>` for `permissions.push`) using only an identity you created
with `agent-skills access set`. It never probes a write by attempting one, and it says which
identity it spoke for.

`--live` starts a server you have already configured, with its configured environment, does the
MCP handshake and `tools/list`, and stops it. "A write tool is present" is necessary, not
sufficient; an explicit read-only setting outranks the tool list. Doctor never uses `--live`.

## Write profiles

A read-only route stays read-only. For writes, `access setup <system> --write-profile` proposes a
second entry, `<name>-write`, reusing the same command and switching write mode by that route's own
rule: `READ_ONLY_MODE=false` for the upstream, or the launcher's variable (`ACME_ATL_RW=1` in the
example).

It is **limited by default**:

- to the target's space or project, through the route's scope filter
  (`CONFLUENCE_SPACES_FILTER`, `JIRA_PROJECTS_FILTER`). Name the target with `--target <url-or-key>`
  or the key with `--scope <key>`; without either it refuses and says so. `--all-scopes` lifts this
  limit on purpose. A route with no scope filter (GitHub, GitLab) cannot be narrowed, and the
  proposal says the profile covers everything the account can write;
- to the target system, when one server serves several: a Confluence write profile of
  `mcp-atlassian` sets `TOOLSETS` to the Confluence toolsets, so it cannot write to Jira. There is no
  opt-out for this one.

The check's own fix options already carry `--target`, so the command Wamala hands you is scoped.

- It shows the exact diff, with secret-shaped values masked.
- It writes only after you type `yes` in a terminal. Run by an agent, it prints and writes nothing.
- It backs up the host file, writes atomically, keeps the file's mode. `--undo` removes only the
  entry it added (after showing the diff and asking), so edits you made to the file since survive.
- A file with comments (VS Code JSONC) is never rewritten; you get the snippet to paste.
- It tells you how to reload the host and, for Claude Code, to keep the new server's tools off
  your permissions allow list so every write is asked.

## Policy

Built in: reads need `route`-`target`; writes need `route`-`intent`, one resolved target, and a
preview (your own target: preview then go-ahead; elsewhere: preview plus explicit confirmation);
destructive and bulk operations need explicit confirmation naming targets and count.

`<config>/access-policy.json` may tighten - `deny` and `always_confirm` lists of
`{system, operation}`, and `require_probe_for_write` - and may not loosen. A key that tries to
(`allow_found_credentials`, `skip_preview`, ...) or that is unknown makes every check fail closed
with exit `2` until the file is fixed. The floor, which nothing overrides:

- never enable write mode globally;
- never edit a host MCP configuration without you confirming the exact change;
- never use a found credential outside a configured, qualified route;
- never retry a blocked write through another route to get around a `fail` at mode, target, or policy;
- never ask you to paste a secret into the chat;
- never count a browser session as a write route for a system with an API.

After each write the agent appends one line to `<install>/state/access/audit.jsonl`
(`agent-skills access record`): time, host, system, operation, target id, route, result,
confirmation. No content, no secrets.

## Enforcement

Where [Execution Guard](../execution-guard.md) runs as a host hook (Claude Code and Codex
`PreToolUse`), rule `ACCESS_UNQUALIFIED_WRITE` asks before:

- **an MCP tool** the registry lists as a write or destructive tool, unless `access check` passed
  for that system, operation class and server within the last 30 minutes. The tool is matched to a
  system by name, narrowed by the server's name where two systems share a tool name
  (`create_branch`); a server named after a system files an unlisted mutating tool under it. The
  grant is keyed by system, operation class and server, not by target: tool arguments differ per
  server and are not a reliable place to read a page id from;
- **a raw HTTP write** - `curl`, `wget`, `http`/`xh` with a writing method or a body, aimed at a known
  system's host (a registry host hint, or a base URL you confirmed), including inside `sh -c` or
  `eval` and with scheme-less URLs - **always**. No check qualifies a raw HTTP call with a token, so
  no grant covers it; you can still approve one deliberately. A shared host is resolved by path
  (`/wiki` is Confluence, `/rest/api/3` is Jira) so the message names the right system.

It fails closed: an unreadable registry makes every mutating-looking MCP tool and every fetcher
write ask, and a shell line that cannot be tokenised but names a fetcher and a known host counts as
a write. It asks rather than denies by default so that working without Wamala is slowed, not
blocked; a guard policy can raise it to deny. A program that makes HTTP calls itself (a Python or
Node one-liner) is not parsed; the Wamala contract still forbids it.

Hosts without a pre-execution hook have no enforcement point; Wamala's
[resolution dialogue](../../skills/wamala/references/access-resolution-dialogue.md) is the gate.

## What Wamala will and will not do on its own

Will: scan, check before dependent work, relay the check verbatim, inspect a launcher you name,
offer the check's options in order, remember what you confirm, re-check after you act, and prepare
a manual hand-off.

Will not: pick an option for you, edit a host configuration, turn on write mode, use a found
credential, fall back to a browser or raw HTTP, retry a blocked write another way, or ask for a
secret in chat.

## Files

| What | Where |
| --- | --- |
| System registry (shipped) | `lib/access/systems/*.json` |
| Local route knowledge | `<config>/access/routes.json` |
| Policy overrides | `<config>/access-policy.json` |
| Write audit | `<install>/state/access/audit.jsonl` |
| Write grants (30 minutes) | `<install>/cache/access/grants/` |
| `access setup` history for `--undo` | `<install>/state/access/setup-history.json` |

`<config>` is the Access Resolver's directory (`~/.config/agent-skills`, `AGENT_SKILLS_CONFIG_DIR`);
`<install>` is `~/.agent-skills` (`AGENT_SKILLS_HOME`). Every file carries a versioned schema, and
1.4.0 ignores all of them, so rollback is safe.
