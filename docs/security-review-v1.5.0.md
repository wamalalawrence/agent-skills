# Security review — v1.5.0

Follows [the v0.37.0 review](security-review-v0.37.0.md) as the shape. Each threat is labelled
**probed** (a test exercises it), **reasoned about** (argued from the design), or **unproven**.
Test ids refer to `scripts/test-access-discovery.py`.

`1.5.0` adds Access Discovery. It is the first release that reads every agent host's MCP
configuration, reads launcher scripts someone else wrote, checks the OS credential store for items
it did not create, can edit a host configuration (after an interactive yes), and can start an MCP
server the user configured (`--live`). Each of those is a way to leak a secret or to run something
a repository chose, so most of this review is about trust boundaries.

## Scope of this review

- **New:** `scripts/access_discovery_cli.py`, `access_ladder.py`, `access_hosts.py`,
  `access_toml.py`, `access_registry.py`, `access_inspect.py`, `access_creds.py`, `access_state.py`,
  `access_setup.py`, `access_live.py`, `access_probe.py`, `guard_access.py`; `lib/access/systems/`;
  fixtures under `scripts/fixtures/access/` (test only).
- **Changed:** `scripts/access.py` (subcommands registered; `forget` accepts a system or `--all`),
  `guard.py` and `guard_rules.py` (rule `ACCESS_UNQUALIFIED_WRITE`), `guard_audit.py` and
  `lib/asrelease/providers/git.py` (redaction), `lib/asrelease/exits.py` (code `11`), `doctor.sh`,
  `bin/agent-skills`, the Wamala skill and its handoff template.
- No change to the release engine's transaction, the knowledge stores, or Meeting Intelligence.

---

## Threat: a secret value reaches output, state, or local knowledge

**Probed.** The fake `security` prints a canary only when called with `-w` or `-g`; the fake
`secret-tool` always prints one. A1, A2, C1 and C2 run `scan`, `check`, `explain`, `inspect` in text
and JSON and assert no canary in any output or in any file under the config and install
directories, and that `security` was never called with `-w`/`-g` and `secret-tool` never at all.
H1 asserts host readers never return the value of a secret-shaped key. A plaintext token placed in
a host env block and in `~/.netrc` never appears (C1, C2, S1).

Values are read only for keys a registry entry or local knowledge names as mode, filter or base-URL
keys, or whose names look like a mode switch and not like a secret. A secret-shaped key's value is
examined only to tell a literal from a `${...}` reference, for the plaintext warning, and is not
kept. Every command's output passes through the shared redaction; the five new patterns are probed
in X1.

## Threat: a found credential is used as a route

**Probed and reasoned about.** Credential presence is reported as locators in
`found_credentials`, and the only fix option that mentions one leads to `access setup` (A1, R6).
Nothing in the new code sends a found credential anywhere. The one network path, `--probe`, takes
its credential only from an identity the user created with `access set` (resolved in-process by
`resolve_access(values_out=...)`), never from a keychain item a launcher reads or a host env block.

## Threat: `--probe` sends the user's credential to a site a repository chose

**Probed (P2).** Found during this review. A route's base URL comes from host configuration, and a
project-scoped route (`.mcp.json`, `.cursor/mcp.json`, ...) is read from a file any contributor can
change. The first draft probed whatever base URL the route named, with any identity the resolver
returned, and an identity from the environment or one recorded without a site matches every host.
The probe now sends a credential only when the route's host equals the host the identity itself
names; otherwise it reports "not probing" and sends nothing. P2 points a project `.mcp.json` at a
local server and asserts it receives no `Authorization` header.

## Threat: `--live` runs a command a repository chose

**Probed (L1).** Found during this review. `--live` starts the configured server to list its tools.
A project-scoped server's command comes from the repository, so starting it would execute
repository-chosen code the user never approved in this context. `--live` now refuses project-scoped
servers and says why; it starts only user- and local-scope servers the user configured themselves.

## Threat: the launcher inspector executes, or leaks, a file

**Probed (W1, A1-A3).** The inspector reads bytes; it never executes, sources, or passes a script to
a shell. Every fixture touches a marker file when run, and every test asserts the marker is absent.
Reads are bounded to 64 KB (content past the bound is not inspected, W1), binaries are reported
opaque, and only executable regular files are read at all, so a host config cannot point the
inspector at a key or credentials file (W1). Comments are stripped before matching, so a commented
decoy (`# security find-generic-password -s decoy-item -w`) is not reported (W1).

The one exception is the self-report flag (`--agent-skills-capabilities`), run only for a launcher
the user marked `trusted_self_report` in their own local knowledge (K2), with stdin closed, a 5 s
timeout, and at most 64 KB of stdout read.

## Threat: a host configuration is changed without the user's consent

**Probed (A2, S1).** `--undo` removes only the entry `setup` added and shows the diff first, so
later edits survive (the first draft restored the whole backup). `access setup --write-profile` writes only after an interactive `yes` at a
terminal (stdin and stdout both TTYs). There is no flag or variable that skips it; an agent's
non-interactive run prints the change and writes nothing (A2 asserts the file is byte-identical).
Writes back up the file, go through a temporary file and `os.replace`, and keep the mode (S1).
`--undo` restores the backup after its own confirmation (A2). A JSONC file is never rewritten (S1).
The diff is masked: secret-shaped values appear as a placeholder or `[redacted]` (S1). A write profile
is limited by default to the target's space or project and to the target system's toolsets, so a
profile made for one page's space cannot write elsewhere, and a Confluence profile cannot write to
Jira (A2, S1).

## Threat: a write routes around a read-only setting

**Probed (G1, R8) where a hook exists; reasoned about elsewhere.** Execution Guard's new rule asks
before an MCP write tool for a known system unless `access check` passed for that system,
operation class and server in the last 30 minutes, and **always** before a raw HTTP write to a known
system's host. The independent review found five ways past the first draft, all reproduced and
fixed: attached curl options (`-d'..'`), `wget --method=`, fetchers inside `sh -c`/`eval`,
scheme-less URLs, and - most serious - any passing check allowing a raw `curl -X PUT` carrying a
found token. It also found that a Confluence grant covered Jira's REST paths on the same host, that
tool names shared by GitHub and GitLab mapped to the wrong system, and that an unreadable registry
switched the gate off. G1 now runs every one of those commands. In the check itself, a write that
one route's setting blocks no longer moves silently to another route; it needs the user's choice
(R8). Hosts without a pre-execution hook depend on Wamala's contract. The grant is not bound to a
target; see residual risks.

## Threat: local state tampering loosens policy

**Probed (P1).** `access-policy.json` may only add to `deny` and `always_confirm` (and require
probes). Loosening keys and unknown keys make every check fail closed with exit `2`. Local route
knowledge can make a route look writable (it is the user's own statement), but it never overrides
an explicit read-only setting the route itself declares, and it goes stale when the launcher's
content changes (K1). An explicit read-only setting in the host config outranks local knowledge
and self-reports (K1). Route knowledge, audit, grant and setup-history files are written `0600`; the
config directory is `0700`.

## Threat: a malicious host config or TOML crashes discovery into a false pass

**Probed (H1, H2).** Unparseable files make that host's servers **unknown**, reported as a warning,
never absent. The TOML parser rejects everything outside its subset instead of guessing, and agrees
with `tomllib` where both run (H2).

## Residual risks

- **Grants are per system, operation class and server, not per target.** A passing check for one
  page allows other writes through the same server for 30 minutes. Binding to a target needs the
  target id from tool arguments, which differ per server.
- **Local knowledge is trusted.** A process that can write `~/.config/agent-skills` can mark a route
  writable or a launcher trusted to self-report. That process can already edit the host configs.
- **Heuristic inspection can be wrong.** It is always labelled `inferred`, and a write that depends
  on it needs the user's confirmation.
- **The guard asks by default** (the maintainer's decision). A user who approves every prompt gets no
  protection from the rule; it can be raised to deny in guard policy.
- **HTTP from inside a program** (`python -c 'requests.put(...)'`) is not parsed by the guard.
- **`remember --yes` is the agent's word** that the user agreed in the chat. It can raise inferred
  facts to declared; it cannot override an explicit read-only setting, and it changes no host config.
