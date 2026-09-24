# Access: Atlassian (Confluence and Jira)

Registry entries: [`confluence.json`](../../lib/access/systems/confluence.json),
[`jira.json`](../../lib/access/systems/jira.json). Checked against the upstream
[mcp-atlassian configuration](https://github.com/sooperset/mcp-atlassian/blob/main/docs/configuration.mdx),
its `.env.example`, and its tools reference on 2026-09-23.

## Routes

| Route | How it is recognised | Mode comes from |
| --- | --- | --- |
| `mcp-atlassian` (sooperset) | `uvx mcp-atlassian`, a `mcp-atlassian` binary, or the `ghcr.io/sooperset/mcp-atlassian` image | `READ_ONLY_MODE`, `--read-only`; default read-write |
| Atlassian's remote MCP server | a URL or `mcp-remote` argument on `mcp.atlassian.com` | the OAuth scopes granted at sign-in; always `unknown` locally |
| a launcher script | anything else that execs one of the above | the script's own logic, inferred by the inspector |
| `jira` CLI | on PATH | the account's permissions; no client-side mode |

A launcher named after its upstream (`<org>-mcp-atlassian`) is **not** mistaken for it: commands
match by exact name, never by substring.

## Read-only vs a write profile

`READ_ONLY_MODE=true` removes every write tool. `ENABLED_TOOLS` and `TOOLSETS` narrow further; a
tool must pass both. A check for `update` fails at `mode` when either leaves no write tool for the
system - `TOOLSETS=jira_issues` has none for Confluence.

Keep the read-only server and add a second one for writes:

```bash
agent-skills access setup confluence --write-profile --host <id> --target "<page url>"
```

It copies the existing entry, sets `READ_ONLY_MODE=false` (or the launcher's own switch), limits it
to the page's space (`CONFLUENCE_SPACES_FILTER`) and to the Confluence toolsets (`TOOLSETS`), and
shows the diff. You apply it in a terminal. `--all-scopes` drops the space limit; the Confluence-only
limit stays. The toolset names were checked against upstream's `toolsets.py` on 2026-09-24.

## Cloud vs Server / Data Center

| | Cloud | Server / Data Center |
| --- | --- | --- |
| Credential | `CONFLUENCE_USERNAME` + `CONFLUENCE_API_TOKEN` (`JIRA_*` likewise) | `CONFLUENCE_PERSONAL_TOKEN` / `JIRA_PERSONAL_TOKEN` |
| Base URL | your site under atlassian.net, with `/wiki` for Confluence | your own host |
| Token shape | starts `ATATT` (redacted everywhere) | opaque |

**Scoped API tokens.** A Cloud API token created with scopes can read and still fail every write
with 401 or 403. That is a `target` (token scope) problem, not a network fault, and
`agent-skills access classify-error --status 403` says so. The fix is a token with the write scope,
which you create yourself.

## The personal-space pitfall

`CONFLUENCE_SPACES_FILTER=DEV,OPS` limits a route to those spaces. A page in your personal space
(`~yourname`) is then not "forbidden" - it is invisible, and a lookup returns 404 as if it did not
exist. The check catches this before any work:

```text
  target   FAIL     space ~jdoe is excluded by CONFLUENCE_SPACES_FILTER=DEV,OPS - a personal space;
                    pages there look missing, not forbidden   [declared]
```

`JIRA_PROJECTS_FILTER` does the same for Jira projects. A write profile made with
`--target <page url>` gets its own filter for that page's space.

## Probes (`--probe`)

Only with an identity you created (`agent-skills access set --service confluence ...`), never with
the MCP route's own credential:

- identity: `GET <base>/rest/api/user/current` (Jira: `/rest/api/2/myself`);
- Confluence page: `GET <base>/rest/api/content/<id>?expand=operations,space,version` - `update` in
  `operations` means the identity may edit it;
- Jira issue: `GET <base>/rest/api/2/mypermissions?issueKey=<key>&permissions=EDIT_ISSUES,...`.

None of them writes.

## Write safety

- Confluence: read the current version right before writing, submit `version + 1`, keep the body
  representation, show a diff before applying, and on a version conflict (409) stop and show the
  user - `classify-error --status 409` says the same.
- Jira: validate a transition against the issue's current status and show field changes first.
  Closing and resolving transitions are treated like destructive operations: explicit confirmation
  naming the issues and the count.
