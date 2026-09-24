# Discovery: company-agnostic access discovery in Wamala (1.5.0)

Development record, not shipped (the release payload is `bin lib scripts skills docs hooks`).
Line numbers refer to the `1.4.0` tree (`e2d61aa`) unless a file is new in this release.

## 0.C hypotheses

**Where Wamala's preflight lives and how it produces "MCP configured" - confirmed, reworded.**
Wamala's preflight is `agent-skills start-task` (`skills/wamala/SKILL.md:53-66`), whose step 4 runs
`doctor.sh --brief` (`scripts/start-task.sh:380`). The line is `mcp  config present: <files>` from
`probe_mcp` (`scripts/doctor.sh:221-246`): a file-exists test over eight candidate paths. The literal
text "MCP configured" exists nowhere in the tree.

**Which systems Wamala's workflows touch - confirmed.** Jira (tracker) via `auth-preflight.py`,
`access resolve`, an MCP server, or the `jira` CLI; Confluence (document store) via MCP or REST;
GitHub via `github-access.sh` (`gh auth status`, git) and `gh`; the tool registry adds CI, Sonar,
Slack and others (`lib/tools/registry.d/`). Meeting platforms go through Meeting Intelligence's own
providers.

**Organisation-specific names in the shipped payload - refuted.** A search of
`skills lib scripts bin docs hooks` for the employer's name, `~/.local/bin/<x>-mcp-*` wrappers,
internal domains, and hard-coded keychain item names found nothing. Every host in the payload is a
public vendor, `example.*`, or an invented test name.

**What `hooks/` contains - partially true.** `hooks/` holds optional lifecycle templates (Claude
Code, Kiro, generic) that call `start-task`/`finish-task`; nothing is installed. The enforcing hook is
Execution Guard's `PreToolUse`, installed by `agent-skills guard install` for Claude Code and Codex,
with matchers that already include `mcp__.*` (`scripts/guard_hosts.py:210-211`). The enforcement
point for this release is therefore the guard.

**Meeting Intelligence's provider pattern - confirmed.** `READY / NOT_CONFIGURED / BROKEN` and
`Readiness` in `scripts/meeting_capture.py:89-91,169`; `readiness()` in
`scripts/meeting_providers.py:126`. Reused as vocabulary, not as a class (D6).

**Exit codes beyond the installer's list - confirmed.** `access` uses `1` for "not resolved"; the
guard uses `10` ask and `20` deny (`scripts/guard.py:73-74`); `context check` uses `10`. `11` was
unused anywhere and is added as `capability-unavailable`.

**How the runtime stores credentials - confirmed.** `KeychainBackend` (macOS `security`),
`SecretServiceBackend` (`secret-tool`), and a `0600` `FileBackend` (`scripts/access.py:210,282,349`),
chosen by `select_backend` (`:406`). Presence checks reuse the same tools, only in their no-secret
forms.

## 1.1 Preflight signals

`probe_mcp` read only whether one of these files exists: `<repo>/.mcp.json`, `<repo>/mcp.json`,
`<repo>/.cursor/mcp.json`, `<repo>/.kiro/settings/mcp.json`, `<repo>/.vscode/mcp.json`,
`~/.kiro/settings/mcp.json`, `~/.cursor/mcp.json`, `~/.claude.json`. It never read `~/.codex/config.toml`
or Claude Desktop's config, so a Codex-only machine reported **no MCP at all**. Two more copies of the
same idea exist: `detect_mcp` in `scripts/access.py:940` (a substring search for the service name in
any config, returning `mcp` or `mcp-present`) and `_detect_mcp` in `scripts/tools.py:195`.

## 1.3 Organisation-specific strings

None found (see above). The no-coupling lint (N1 in `scripts/test-access-discovery.py`) now enforces
it. Its denylist is stored as SHA-256 digests, because `scripts/` ships and a plaintext list would
itself put the names in the payload; a plaintext list kept outside the payload can be added with
`AGENT_SKILLS_COUPLING_DENYLIST=<file>`.

## 1.4 Hosts and where they keep MCP servers

Verified against the host adapters (`lib/hosts.registry`, `scripts/guard_hosts.py`) and each host's
documentation; implemented in `scripts/access_hosts.py`.

| Host | Detected by | MCP config |
| --- | --- | --- |
| Claude Code | `~/.claude.json` or `~/.claude` | `~/.claude.json` `mcpServers` (user) and `projects[<repo>].mcpServers` (local); `<repo>/.mcp.json` (project) |
| Claude Desktop | its Application Support / `~/.config/Claude` dir | `claude_desktop_config.json` `mcpServers` |
| Codex | `~/.codex` (`CODEX_HOME`) | `config.toml` `[mcp_servers.<name>]`, also `<repo>/.codex/config.toml` |
| Cursor | `~/.cursor` | `~/.cursor/mcp.json`, `<repo>/.cursor/mcp.json` |
| VS Code / Copilot | the VS Code user dir | user `mcp.json` and `settings.json` (`mcp.servers`, JSONC), `<repo>/.vscode/mcp.json` (`servers`) |
| Kiro | `~/.kiro` (`KIRO_HOME`) | `~/.kiro/settings/mcp.json`, `<repo>/.kiro/settings/mcp.json` |

## 1.5 Knowing the current host

Reliable: `CLAUDECODE=1`, set by Claude Code, including when it runs inside the Claude desktop app
(where `CLAUDE_CODE_ENTRYPOINT=claude-desktop` and the MCP config is still `~/.claude.json`). No other
host sets a documented variable. Order used: `--host`, then `AGENT_SKILLS_HOST`, then `CLAUDECODE=1`,
otherwise every detected host is evaluated and labelled.

## 1.6 hooks/

See the table above: lifecycle templates only. Enforcement lands in Execution Guard as rule
`ACCESS_UNQUALIFIED_WRITE` (category `access`, default ASK).

## 1.7 Runtime subsystems

| Subsystem | Where | Used for |
| --- | --- | --- |
| Redaction | `scripts/guard_audit.py:41` (runtime), `lib/asrelease/providers/git.py:92` (installer) | all output of the new commands |
| Credential access | `scripts/access.py` backends; `resolve_access(values_out=...)` | `--probe` only, with a user-created identity |
| Doctor | `scripts/doctor.sh` probes and renderers | new `access` probe and Access rows |
| CLI dispatch | `bin/agent-skills` -> `scripts/access.py` argparse | new subcommands registered by `access_discovery_cli.register()` |
| Exit codes | `lib/asrelease/exits.py`, `lib/install.sh:566` | `11` added |
| Relay to the user | skills run the CLI and read its human output; `--json` is documented as safe to paste | Wamala relays `access check` verbatim |

## 1.8 The incident on 1.4.0

Fixture: Codex, server `atlassian` -> `~/.local/bin/acme-mcp-atlassian` (bash; `uvx mcp-atlassian`;
`READ_ONLY_MODE=true` unless `ACME_ATL_RW=1`; `security find-generic-password -s acme-atlassian -w`).

```text
$ agent-skills doctor --brief          (1.4.0)
    NO  mcp              no MCP configuration found (agent-skills ships none by design)

$ agent-skills access resolve --service confluence --resource https://acme.atlassian.net \
    --require host,token --secret token          (1.4.0)
status: needs-setup
missing fields:
  - token
note: host has MCP configuration; check for a confluence tool before storing a secret
[exit 1]
```

Doctor saw no MCP at all (it never reads `config.toml`); the resolver saw "MCP configuration" and
asked for a token. Neither said anything about the mode. The same fixture on 1.5.0 is test A1: blocked
at `mode`, `inferred`, citing lines 14-15, exit `11`.

## Responsibility mapping

| Responsibility | Existing owner | What this release adds |
| --- | --- | --- |
| Credential storage and resolution | Access Resolver (`scripts/access.py`) | nothing parallel: probes resolve through it in-process; config dir is its `config_dir()` |
| Redaction | `guard_audit.redact` + installer `redact` | five patterns across the two (Atlassian tokens, JSON auth header; installer: auth headers, JWT, `*_TOKEN=`) |
| Doctor | `scripts/doctor.sh` | an `access` probe and per-host, per-system rows; `mcp` row kept, now also reads Codex and Claude Desktop |
| Host detection | `lib/hosts.registry` (skills dirs), `guard_hosts.py` (hooks) | MCP config readers keyed by the same host ids (`access_hosts.py`); ownership logic untouched |
| Provider readiness | Meeting Intelligence | same `ready / not configured / broken` vocabulary in doctor |
| Capability vocabulary | Tool framework (`lib/tools/`) | a separate access registry (`lib/access/systems/`), linked by `tool_id` - see D2 |
| Enforcement | Execution Guard | rule `ACCESS_UNQUALIFIED_WRITE` and `scripts/guard_access.py` |
| Durable state | `~/.agent-skills/state`, `cache` | `state/access/audit.jsonl`, `state/access/setup-history.json`, `cache/access/grants/` |
| Dispatch contract | Wamala | step 2.9 and `references/access-resolution-dialogue.md`; a binding block in the handoff template |

## Design deviations

- **D1 - `forget` shares its name.** `access forget --profile NAME` already deleted an identity.
  `forget <system>` and `forget --all` now remove route knowledge; `--profile` keeps its exact 1.4.0
  behaviour, and combining them is a usage error so neither can be triggered by accident.
- **D2 - a separate registry.** The tool framework's definitions describe capabilities and
  transports, not MCP upstream modes, filters, write tools, or target parsers. Folding those in would
  change a schema other code validates. The access registry is its own directory, one file per
  system, with `tool_id` pointing at the tool definition.
- **D3 - exit `1` for "needs the user".** The prompt names 0/2/3/4/11. Route, launch, intent,
  unknown, and needs-confirmation outcomes use `1`, which is the Access Resolver's existing "not
  resolved" code, rather than a new number.
- **D4 - the guard asks, it does not deny.** A hard deny would lock out users working without Wamala.
  ASK puts the decision in front of the user and can be raised to deny by guard policy. Grants are
  per system, operation class and server, not per target: MCP tool arguments differ per server and
  are not a reliable place to read a page id.
- **D5 - no static-scan cache.** A scan of six hosts with launcher inspection is fast enough that a
  cache would add a staleness class (a launcher edit not noticed) for no gain. Grants are the only
  cached state.
- **D6 - Readiness reused as vocabulary, not as a class.** `meeting_capture.Readiness` is per
  capture provider; access readiness is per (host, system, route) with an evidence strength. Doctor
  rows use the same words.
- **D7 - `--probe` never uses the route's own credential,** only an identity from `access set`, and
  only when the route's site equals the site that identity names. A project-scoped route is read
  from a file a pull request can change; without the site match, `--probe` could have sent the
  user's token to a host a repository chose. The prompt did not ask for this; the security review
  of this release found it.
- **D8 - `--live` never starts a project-scoped server,** for the same reason: a repository must not
  be able to choose a command that runs.
- **D9 - the inspector reads only executable files,** so a host config cannot point it at a key file.
- **D10 - `access record`** is added (not in the prompt's CLI list) because the write audit needs a
  writer the agent can call after an MCP write.
- **D11 - `remember --yes`.** Confirmation in an agent session happens in the chat, not at a
  terminal. `--yes` records that the user said yes; without it and without a terminal, nothing is
  written. `access setup` has no such flag: host configs change only at an interactive prompt.

## Registry

| System | Upstream | Mode settings | Verified against |
| --- | --- | --- | --- |
| confluence, jira | `mcp-atlassian` (sooperset) | `READ_ONLY_MODE`, `--read-only`, `ENABLED_TOOLS`, `TOOLSETS`, space/project filters | its config, env and tools docs, 2026-09-23 |
| confluence, jira | Atlassian remote MCP | not visible locally (`unknown`) | not verified; always reported unknown |
| github | `github-mcp-server` | `GITHUB_READ_ONLY`, `--read-only`, `GITHUB_TOOLSETS`, `--toolsets` | README, 2026-09-23 |
| gitlab | `@zereight/mcp-gitlab` | `GITLAB_PERMISSION_MODE` (readonly/modify/full), `GITLAB_READ_ONLY_MODE`, `GITLAB_TOOLS`, `GITLAB_TOOLSETS` | README, 2026-09-23 |

CLI routes: `jira me`, `gh auth status` (+ `gh api repos/<o>/<r> --jq .permissions.push`),
`glab auth status`. Probes: Confluence `expand=operations`, Jira `mypermissions`.

## Other access issues found

| Issue | Status |
| --- | --- |
| Doctor's MCP probe ignored Codex `config.toml` and Claude Desktop | fixed |
| "config present" reported presence as capability | fixed: `access` rows with mode and strength |
| A wrapper named `<org>-mcp-atlassian` matched the upstream by substring in this release's first draft | fixed: exact basename match, test R1 |
| Runtime redaction missed short `ATATT` tokens and a JSON `"Authorization": "Bearer ..."` | fixed |
| Installer redaction missed auth headers, JWTs, `*_API_TOKEN=` / `*_PERSONAL_TOKEN=` | fixed |
| Host MCP configs with plaintext tokens, or group/world-readable | reported by scan and doctor |
| Host divergence (read-only in one host, read-write in another) | reported by scan and doctor |
| `detect_mcp` (access.py) and `_detect_mcp` (tools.py) substring-search configs and duplicate the path list | fixed: one detector |
| Browser fallback attempted with no session | fixed by contract: never attempted, never a write route |

## Needs a human decision

Decided by the maintainer on 2026-09-24, and implemented in this release:

- **Write profiles are limited by default** to the target's space or project (`--target`/`--scope`;
  `--all-scopes` opts out) and always to the target system's toolsets when one server serves several.
- **`ACCESS_UNQUALIFIED_WRITE` stays ASK.**
- **The two older MCP detectors are replaced** by one (`access_ladder.mcp_servers_for`, built on
  `access scan`), used by `access resolve` step 1, `tools resolve`, `tools status`, and doctor's `mcp`
  row. `access resolve` notes now name the server, host and mode, and a route for another site no
  longer resolves a request; `tools resolve` no longer counts a read-only MCP route as providing a
  WRITE capability; doctor's `mcp` row lists servers instead of config files.
