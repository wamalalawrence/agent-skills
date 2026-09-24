# Access: GitHub

Registry entry: [`github.json`](../../lib/access/systems/github.json). Checked against the
[GitHub MCP server README](https://github.com/github/github-mcp-server/blob/main/README.md) on
2026-09-23. The service-specific walk for repository access (SSH, `gh`, credential helpers) stays
in the [GitHub access ladder](../github-access.md); this page is about which route can write.

## Routes

| Route | Recognised by | Mode comes from |
| --- | --- | --- |
| GitHub MCP server (local) | `ghcr.io/github/github-mcp-server`, or a `github-mcp-server` binary | `GITHUB_READ_ONLY`, `--read-only`; `GITHUB_TOOLSETS` / `--toolsets` |
| GitHub MCP server (remote) | a URL on `api.githubcopilot.com/mcp` | not visible locally: `unknown` |
| `gh` CLI | on PATH | the token's scopes and your repository role |

Default toolsets are `context`, `repos`, `issues`, `pull_requests`, `users`. A write check fails at
`mode` when `GITHUB_TOOLSETS` names none of `repos`, `issues`, `pull_requests` (and not `all` or
`default`).

`merge_pull_request`, `delete_file` and `delete_repository` are destructive: explicit confirmation
naming the target.

## Probes

`--probe` with the `gh` route runs `gh auth status` for `auth`, and
`gh api repos/<owner>/<repo> --jq .permissions.push` for `target`. `false` means the account cannot
push: ask a maintainer for write access. Nothing is written.

## Enterprise

`GITHUB_HOST` names a GitHub Enterprise host for the MCP server. A `gh` login for `github.com` does
not qualify a route to an Enterprise host, and the check says so rather than assuming.
