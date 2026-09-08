# Access Resolution

This is the single mechanism every skill uses to reach an external service. One command, any
service, resolved only when a task actually needs it.

```bash
agent-skills access resolve --service <name> [--resource <uri>] \
  --require <field,field,...> [--secret <field>]
```

Nothing about Jira, Confluence, Sonar, GitHub, a database, or an internal API is built into it.
The **caller** supplies the service name and the field names it needs, so a skill can ask for
access to a service that did not exist when `agent-skills` was installed.

Three ideas carry the whole design:

1. **Lazy.** Installation asks for nothing. Access is established the first time a task needs it.
2. **Capability-first.** An already-authenticated tool or session beats storing another secret.
3. **Credentials are identities, not projects.** A profile is an account on a service. Several
   repositories share one; one repository may use several.

## The shape of a request

The caller declares what it needs. These are examples, not a schema the resolver is limited to:

```text
service:  jira
resource: https://example.atlassian.net
required: host, login, token
secret:   token
```

```text
service:  internal-orders-api
resource: https://orders.example.com
required: base_url, client_id, client_secret
secret:   client_secret
```

```text
service:  postgres-production-readonly
required: host, port, database, username, password
secret:   password
```

As commands:

```bash
agent-skills access resolve --service jira \
  --resource https://example.atlassian.net --require host,login,token --secret token

agent-skills access resolve --service internal-orders-api \
  --require base_url,client_id,client_secret --secret client_secret

agent-skills access resolve --service postgres-production-readonly \
  --require host,port,database,username,password --secret password
```

Exit codes: `0` resolved, `1` not resolved (the report says what is missing), `2` usage error.
`--json` gives the same answer as a structured object, and is safe to include in agent context
because it never contains a secret value.

## Resolution order

Deterministic, walked once, top to bottom. The first step that satisfies every required field wins.

```text
Task needs an external resource
        |
        v
1. Is an already-authenticated tool or session available?
        |  gh, glab, aws, gcloud, az, kubectl, jira, or a host MCP server
       yes --> use it. No secret is read or stored.
        |
        no
        v
2. Explicit process environment?
        |  AGENT_SKILLS_<SERVICE>_<FIELD>, <SERVICE>_<FIELD>, or a legacy name
       yes --> use it. This always overrides stored state.
        |
        no
        v
3. Project-local credential source?
        |  untracked .agent-skills.local.yml, then legacy .env / .env.local /
        |  .jira-config.yml for backwards compatibility
       yes --> use it
        |
        no
        v
4. Does this repository bind the service to a named identity?
        |  the user-global binding registry, or the untracked local override
       yes --> resolve that identity
        |
        no
        v
5. Do compatible global identities exist?
        |
        +--> exactly one: use it (unless strict binding is on)
        +--> several: report the candidates and ask which one
        +--> none
                |
                v
6. Lazy setup: name the missing fields and how to supply them safely.
   Never ask for a secret value in the conversation.
```

Step 2 sits above every file on purpose: an operator must always be able to override stored state
for one command without editing anything.

Step 1 sits above step 2 because the cheapest credential is the one you never store. If `gh` is
logged in, the agent should use `gh`, not ask for a token that duplicates it. This is the same
[tool-preference order](mcp.md#tool-preference-order) the skills already follow.

## Identities, not projects

A profile represents an account on a service:

```text
work-jira
personal-github
twendex-github
client-acme-azure
production-readonly-db
```

Create one when a task first needs it:

```bash
agent-skills access set --profile work-jira --service jira \
  --resource https://example.atlassian.net --account person@example.com \
  --field host=https://example.atlassian.net --field login=person@example.com \
  --secret-field token
```

`--secret-field` reads the value with hidden terminal input and stores it in the OS credential
store. It never appears in your shell history, in the output, or in any file inside a repository.
Non-secret fields go to user configuration.

List what exists (values are never shown):

```bash
agent-skills access profiles
```

Bind a service to an identity for the current repository:

```bash
agent-skills access bind --service github --profile work-github
```

Bindings live in a user-global registry keyed by the repository's git remote, so they survive the
repo being moved or re-cloned, and they contain **no secrets**.

## Where things are stored

| What | Where | Contains a secret |
| --- | --- | --- |
| Secret field values | OS credential store (see below) | yes |
| Profile metadata: name, service, resource, account, field names, timestamps | `credentials.json` in the user config dir, mode `0600` | no |
| Project bindings | `bindings.json` in the user config dir, mode `0600` | no |
| Project-local overrides | untracked `.agent-skills.local.yml` in the repository | possibly |
| Committed project config | `.agent-skills.yml` in the repository | **never** |

The user config directory is `$XDG_CONFIG_HOME/agent-skills`, or `~/.config/agent-skills` when
that is unset. `AGENT_SKILLS_CONFIG_DIR` overrides it.

### Secret storage backends

Checked in order, and the choice is always reported:

| Backend | Used when | Secure |
| --- | --- | --- |
| macOS Keychain | `security` is available on macOS | yes |
| Linux Secret Service | `secret-tool` is available and a collection can be reached | yes |
| Restricted file | no OS store is available | no — filesystem permissions only |

```bash
agent-skills access backend
```

The file fallback is deliberate, not a silent default:

- it is reported every time, as a warning rather than a status line;
- the file is mode `0600` inside a `0700` directory, outside every repository;
- it is never substituted for a store that previously worked. A profile written to the Keychain
  and then read on a machine where the Keychain is unavailable is reported as unavailable, not
  quietly re-read from a weaker place;
- there is no home-grown encryption. An encrypted file next to its own key is theatre, and
  pretending otherwise would be worse than being honest about what the tier protects.

Windows is evaluated but not implemented: run under WSL or Git Bash, where the Linux or file
backend applies. See [known limitations](known-limitations.md).

## Security boundaries

These are the rules that make the model safe, and each one is covered by a test in
`scripts/test-access-resolution.sh`.

### A committed file may never select a credential profile

`.agent-skills.yml` is checked into a repository. From the resolver's point of view that makes it
attacker-controlled: anyone who can open a pull request can edit it. It may declare **what** a
service is — a name, a host — but it may not choose **which** identity to unlock.

Profile selection comes only from:

- the user-global binding registry, written by `agent-skills access bind`; or
- `.agent-skills.local.yml`, **verified untracked with git** rather than trusted because of its
  name. A tracked file with that name is ignored, with an explanation.

So a repository cannot contain "use `production-readonly-db`" and thereby reach a credential that
has nothing to do with it.

### Resolution is not authorization

Resolution answers one question: *can I authenticate?* It says nothing about *may I perform
destructive action X?* The [destructive-action safety policy](destructive-action-safety.md) is
unchanged and still governs the second question. Every resolution report restates this, because
finding a credential is exactly the moment the distinction gets blurred.

### Secrets never enter the conversation

When a secret is required, the resolver points at a safe way to supply it and stops:

- hidden terminal input via `agent-skills access set --secret-field <name>`;
- the OS credential-store flow;
- OAuth or an MCP integration, when the service offers one;
- a process environment variable for one session.

With no terminal available it refuses rather than asking an agent to relay the value. An agent must
never say "paste your production API token here".

### Names are rejected, not sanitised

Profile, service, and field names are validated against a strict pattern. A name containing a path
separator, a shell metacharacter, whitespace, or `..` is refused. Transforming a bad name into a
different valid one is how you end up writing to the wrong place.

One transformation is applied, and only one: names are **case-folded to lowercase** before
validation, so `Work-Jira` and `work-jira` are the same identity rather than two. Case-folding
cannot introduce a separator or a metacharacter, so it does not widen what the pattern allows.

### Strict binding, for machines holding several customers' credentials

Step 5 uses a lone compatible identity automatically. That is what makes "two repositories share
one work account" work without re-entering a token, and it is safe because a checked-in file cannot
create, rename, or point at an identity.

If one machine holds identities for several customers or environments, that convenience may not be
the posture you want:

```bash
export AGENT_SKILLS_STRICT_BINDING=1
```

An identity is then used only when it was bound explicitly. Everything else is unchanged.

## Backwards compatibility

Configuration written by v0.36.x and earlier still works. Step 3 discovers `.env`, `.env.local`,
and `.jira-config.yml` in the repository, its parent, and `${WORKSPACE_ROOT}` when that is set,
and maps the long-standing variable names onto fields.

An unresolved `${VAR}` placeholder in `.jira-config.yml` is treated as **incomplete
configuration**, not as a value and not as missing auth. That distinction is what stops an agent
reporting "no tracker access" when the real problem is an unloaded `.env`.

To move legacy credentials into named identities:

```bash
agent-skills access import-legacy            # read-only report, nothing is copied
agent-skills access import-legacy --apply    # opt-in
```

Import never displays a secret value, never deletes a legacy file, and never runs without
`--apply`. Your `.env` keeps working either way, so there is no forced migration. If a token sat
in plaintext long enough to worry you, rotate it — moving it does not un-expose it.

## Removing access

```bash
agent-skills access unbind --service jira        # drop this repo's binding
agent-skills access forget --profile work-jira   # delete the identity and its secrets
```

`forget` deletes the stored secret fields, removes the profile metadata, and clears any binding
that referenced it. It reports counts, never values.

## Worked examples

### An unknown future service

A skill needs an internal orders API nobody configured. No installer change, no new subsystem:

```bash
agent-skills access resolve --service internal-orders-api \
  --resource https://orders.example.com \
  --require base_url,client_id,client_secret --secret client_secret
```

Unresolved on the first run, so the report names the two missing fields and the safe way to supply
them. After one `access set`, every repository that needs that API resolves it.

### Two accounts for one service

```bash
agent-skills access set --profile personal-github --service github \
  --resource https://github.com --account personal-user --secret-field token
agent-skills access set --profile work-github --service github \
  --resource https://github.com --account work-user --secret-field token
```

With two compatible identities the resolver will not guess. It reports both and waits:

```bash
cd ~/code/work-repo && agent-skills access bind --service github --profile work-github
cd ~/code/side-project && agent-skills access bind --service github --profile personal-github
```

### Two repositories, one identity

Nothing to do. Create `work-jira` once; every repository that needs Jira resolves it through step
5, and the token is stored once.

### A project-local credential the repo already has

A repository with a gitignored `.env` carrying its own tracker token: step 3 finds it and no global
identity is created. The resolver reports which file the value came from, never the value.

## Troubleshooting

| Symptom | Real cause | Fix |
| --- | --- | --- |
| `status: needs-setup` listing every field | nothing configured for this service yet | follow the `next:` lines in the report |
| `status: needs-setup` listing candidate identities | several identities match | `agent-skills access bind --service <s> --profile <p>` |
| "tracked by git and was ignored" | `.agent-skills.local.yml` is committed | `git rm --cached` it and add it to `.gitignore` |
| "does not exist on this machine" | a binding names a deleted identity | recreate it, or `access unbind` |
| "Refusing to fall back to weaker storage" | the profile's OS store is unavailable here | unlock the keyring, or recreate the identity on this machine |
| resolved, but the service returns 401 | credentials are well-formed but rejected | the token was rotated or lacks scope. Ask the user; do not retry blindly |
| "cannot read secret without a terminal" | a secret was requested in a non-interactive context | run `access set` yourself in a terminal, or export the variable |

A resolved status means a correct request can be constructed. It does not prove the credential is
still valid on the far side.

## Related

- [Configuration](configuration.md) — project configuration, which holds no secrets.
- [Execution modes](execution-modes.md) — global, in-repo, and the legacy workspace model.
- [MCP](mcp.md) — the tool-preference order, and why OAuth beats a stored token.
- [GitHub access ladder](github-access.md) — the service-specific walk for GitHub.
- [Destructive-action safety](destructive-action-safety.md) — the authorization question this
  document deliberately does not answer.
- [Installation](installation.md) — why the installer asks for none of this.
