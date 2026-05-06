# Jira / Confluence Auth Discovery

This page is the canonical reference an agent should follow when it needs Jira or Confluence
access. The goal is simple: an agent should not say "I can't access Jira/Confluence" until it has
walked the documented discovery order, attempted placeholder resolution, and run the auth
preflight. Failing earlier produces avoidable dead ends; the same workspace usually has the
information available, just not in the place the agent looked first.

It pairs with the broader [configuration reference](configuration.md) and the
[execution modes](execution-modes.md) page.

## TL;DR for agents

1. **Locate the files first.** Run `python3 scripts/locate-config.py` (or read the [Where the
  files live](#where-the-files-live) section). Do not say "`.env` not found" until the locator
  has reported every directory it searched. The most common false dead-end is a `.env` that
  lives one directory **above** the cwd because `setup.init` writes it to the parent workspace
  folder, not to the repo root.
2. Walk the discovery order below in order. Do not skip steps.
3. Treat unresolved `${VAR}` placeholders in `.jira-config.yml` as **incomplete configuration**,
  not as missing auth. Resolve them from `.env` or process environment first.
4. Run `python3 scripts/auth-preflight.py` (or the documented equivalent) before declaring auth
  unusable. The preflight reports which fields are missing, which placeholders are unresolved,
  and whether the configuration is usable — without printing secrets.
5. Only after the preflight returns a non-usable result should the agent ask the user, and the
  ask must name the specific missing fields **and** every directory the locator searched.

## Where the files live

`setup.init` does **not** put `.env` and `.jira-config.yml` inside any specific repository. It
puts them in the **parent workspace folder** that holds the sibling repos and the `.skills`
symlink. An agent whose cwd is `<workspace>/<repo>` and which only checks the cwd will
incorrectly report the files as missing.

Authoritative locations, in resolution order:

1. The directory passed via `--workspace-root` to any agent-skills script, or the
  `WORKSPACE_ROOT` environment variable.
2. The cwd, then every parent directory up to the filesystem root. Do **not** stop at the first
  `.git` boundary — the workspace folder usually sits *outside* every repo's `.git`.
3. The directory containing the `.skills` symlink. Whichever directory holds `.skills` is, by
  setup.init's contract, the workspace root and therefore the home of `.env` /
  `.jira-config.yml` / `.env.local`.
4. In `in-repo` mode, the repository root itself, where `.agent-skills.yml` replaces `.env` /
  `.jira-config.yml`. Secrets in this mode come from the host platform's environment-variable
  injection, not from a file.

The locator script implements exactly this order:

```bash
python3 scripts/locate-config.py                   # everything it can find
python3 scripts/locate-config.py --require .env    # exit 1 if .env still missing
python3 scripts/locate-config.py --json            # for tools / agents
```

The script never reads file contents — it only reports paths, the searched-directory list, and
whether each requested file exists. That is enough for an agent to decide whether to source
`.env`, switch to in-repo mode, or surface a precise "missing in these N places" message.

## Discovery order

Apply this order whenever any skill needs Jira or Confluence access. Stop at the first step that
yields a usable configuration; otherwise continue.

1. **`.agent-skills.yml`** at the repository root (in-repo / cloud-agent mode). Provides
  `mode`, `jira.host`, `jira.default_project_key`, `jira.project_keys`, `jira.login`,
  `jira.auth_type`, and `confluence.host` / `confluence.login`. Secrets are **never** stored
  here — they come from environment variables injected by the host platform.
2. **`.jira-config.yml`** in the workspace root. Optional. May contain `${VAR}` placeholders
  resolved from `.env` and the process environment. See [Placeholder resolution](#placeholder-resolution).
3. **`.env`** in the workspace root (local-workspace mode). Authoritative for secrets and
  most non-secret values: `JIRA_HOST`, `JIRA_LOGIN`, `JIRA_AUTH_TYPE`, `JIRA_API_TOKEN`,
  `JIRA_PROJECT_KEYS`, `CONFLUENCE_HOST`, `CONFLUENCE_LOGIN`, `CONFLUENCE_API_TOKEN`,
  `CONFLUENCE_SPACE_KEYS`. Skills must `set -a && source .env && set +a` (or equivalent) so
  child processes inherit the values.
4. **`.env.local`** in the workspace root, when present, layered on top of `.env`. The same
  loader rules apply. `setup.init` does not write to this file; users add it for personal
  overrides (alternate hosts, sandbox tokens, scratch project keys).
5. **Process environment variables** already injected by the host (CI secrets, Codespaces
  secrets, the user's shell). These win over file values when conflicts exist.
6. **Ask the user** for the specific missing non-secret field, or explain exactly which secret
  is missing. Never request the secret value itself in chat — direct the user to put it in the
  configured secret-injection path with `0600` permissions and re-invoke.

The order is **deliberately** the reverse of the variable-resolution precedence used elsewhere
(process env wins). Discovery walks from "where the configuration was probably written" to
"where the loaded value will actually come from at runtime", so unresolved placeholders surface
as a configuration gap, not an auth failure.

## Placeholder resolution

`.jira-config.yml` is the configuration file the `jira` CLI reads. Most CLIs **do not** expand
`${VAR}` placeholders themselves — they read the literal string. Skills must resolve placeholders
before invoking the CLI, or rely on the CLI's own environment-variable support.

The annotated example shipped in this repo uses the `jira` CLI's schema:

```yaml
# .jira-config.yml
installation: cloud
server: ${JIRA_HOST}
login: ${JIRA_LOGIN}
auth_type: ${JIRA_AUTH_TYPE}
project:
  key: ABC
  type: software
```

The matching `.env` provides the actual values (kept here as illustrative placeholders, not real
secrets):

```env
JIRA_HOST=https://example.atlassian.net
JIRA_LOGIN=user@example.com
JIRA_AUTH_TYPE=bearer
JIRA_API_TOKEN=********              # never commit a real token
JIRA_PROJECT_KEYS=ABC,PROJ
```

After resolution, `${JIRA_HOST}` becomes `https://example.atlassian.net`, `${JIRA_LOGIN}` becomes
`user@example.com`, and `${JIRA_AUTH_TYPE}` becomes `bearer`. `JIRA_API_TOKEN` is read by the CLI
directly from the process environment; it is never written into `.jira-config.yml`.

### Rules

- A placeholder string left unresolved in `.jira-config.yml` (e.g. literal `${JIRA_HOST}` reaching
  the CLI) means **incomplete configuration**, not "no Jira access". The fix is to load `.env`,
  not to ask the user for credentials.
- An agent must not assume a CLI expands `${VAR}` automatically. If unsure, run the
  [auth preflight](#auth-preflight) — it reports whether each placeholder resolved.
- Placeholder syntax in this repo is the POSIX-shell form `${NAME}`. `$NAME` (no braces) and
  more elaborate `${NAME:-default}` syntaxes are not interpreted by the preflight or the
  example template; restrict yourself to `${NAME}`.
- Resolved values are not written back to disk. Resolution happens in-memory at preflight time
  and again when the consuming process loads `.env`.

## Auth preflight

`scripts/auth-preflight.py` is the single command an agent should run before deciding Jira or
Confluence is inaccessible. It:

- Loads `.env` (and `.env.local`, when present) with safe parsing — no shell interpolation,
  no command substitution.
- Loads `.jira-config.yml` when present and resolves `${VAR}` placeholders against `.env` and
  the process environment.
- Validates required Jira fields (`JIRA_HOST`, `JIRA_LOGIN` when basic auth, `JIRA_API_TOKEN`).
- Validates optional Confluence fields when `CONFLUENCE_HOST` is set.
- Reports unresolved placeholders, missing fields, and "looks like a token" mistakes
  (e.g. an API token pasted into `JIRA_PROJECT_KEYS`).
- **Redacts every secret value.** Tokens print as `set (hidden)`; values longer than 4
  characters print as `<first-2>***<last-2>` only when the user passes `--show-prefix`.
- Exits with `0` for usable, `1` for incomplete, `2` for setup error (file unreadable, YAML
  malformed). Skills can branch on the exit code without parsing the human-readable output.

Typical invocation:

```bash
python3 scripts/auth-preflight.py
```

Useful flags:

| Flag                | Effect                                                                      |
| ------------------- | --------------------------------------------------------------------------- |
| `--workspace-root`  | Override the directory that holds `.env` / `.jira-config.yml`.              |
| `--require-jira`    | Treat missing/incomplete Jira config as a failure (default: warn).          |
| `--require-confluence` | Treat missing/incomplete Confluence config as a failure (default: skip). |
| `--json`            | Emit a structured JSON report instead of human-readable text.               |
| `--show-prefix`     | Show 2-char prefix/suffix for non-secret values (never for tokens).         |

The preflight does **not** make a network call. It validates that the agent can construct a
correct request; it does not prove the credentials still work on the Jira side. A successful
preflight followed by an HTTP 401 from Jira means the token was rotated, not that discovery
failed.

## Jira / Confluence access troubleshooting

The most common failures, with the diagnosis the agent should reach. Each entry is **symptom →
real cause → fix**.

- **Jira CLI fails with `unknown host: ${JIRA_HOST}`.** The CLI does not expand the placeholder.
  Run `set -a && source .env && set +a`, then re-run; or run the auth preflight first.
- **`.env` exists but values look blank to the agent.** `.env` was never loaded into the process
  environment. Source it (above) or use the auth preflight's loader.
- **`JIRA_PROJECT_KEYS` looks like a long random string.** API token pasted into the project-keys
  field. Replace with `ABC,PROJ` style uppercase prefixes; rotate the leaked token through
  normal channels.
- **Jira project keys missing.** `JIRA_PROJECT_KEYS` is blank in `.env`. Add the comma-separated
  short codes; the preflight validates the shape.
- **Confluence "not configured" warning.** `CONFLUENCE_HOST` is blank — Confluence is genuinely
  unused. Skip Confluence; the skill must not stop on this.
- **Cloud agent reports `.env` not found.** The cloud agent has no shell / no workspace root.
  Use in-repo mode (`.agent-skills.yml`) and inject secrets via the host platform's secret
  mechanism.
- **`.jira-config.yml` exists but `${JIRA_HOST}` reaches the CLI literally.** The CLI does not
  expand placeholders. Resolve placeholders first (preflight, or sourcing `.env`), then
  re-invoke.
- **Auth preflight passes but Jira returns HTTP 401.** Credentials are well-formed but rejected
  by the server. Token rotated, login mismatch, or scope insufficient — ask the user; do not
  retry blindly.

## What an agent should report

When auth is usable: nothing — proceed.

When auth is **incomplete** (the preflight returned `1`): list the specific missing or
unresolved fields, never the secret values, and propose the smallest fix:

> Jira config: incomplete. Unresolved placeholder `${JIRA_HOST}` (no value in `.env`,
> `.env.local`, or process environment). `JIRA_API_TOKEN`: missing (hidden field).
> Add both to `${WORKSPACE_ROOT}/.env` inside the `# >>> agent-skills setup.init` block,
> or rerun `./setup.init` to regenerate. I will not continue with Jira-aware work because
> the result would be based on incomplete context.

When auth is **unusable for this task** (preflight `2`, or preflight passed but Jira rejected):
distinguish "auth not loaded" from "auth not authorized". Do not say "no Jira access" when the
real cause is one of the failures in the table above.

## CLI-independent guidance

Skills that need Jira or Confluence content must not depend on a specific CLI being present.

- **Prefer the auth preflight first.** It works without any Jira CLI installed.
- **Do not require `${JIRA_CONFIG_FILE}` to exist.** When `JIRA_HOST`, `JIRA_LOGIN`,
  `JIRA_API_TOKEN`, and `JIRA_AUTH_TYPE` are present and usable, that is enough — the file is
  a CLI convenience, not a hard requirement.
- **If using the `jira` CLI, export the environment first.** Never invoke `jira` while
  `${JIRA_HOST}` is still a literal placeholder somewhere in its config path.
- **If the CLI cannot authenticate, report the exact missing or rejected field**, not a vague
  "no auth available". If the agent has not yet run the preflight, the only correct first
  action is to run it.

## Cross-references

- [Configuration reference](configuration.md) — full `.env` / `.agent-skills.yml` schema.
- [Execution modes](execution-modes.md) — when each config source applies.
- [Quickstart](quickstart.md) — first-time setup.
- [Installation](installation.md) — `setup.init` flow.
- [Known limitations](known-limitations.md) — what auth discovery cannot guarantee.
- [Destructive-action safety policy](destructive-action-safety.md) — why discovered credentials
  must never be invoked.
