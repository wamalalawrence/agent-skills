# Access: GitLab

Registry entry: [`gitlab.json`](../../lib/access/systems/gitlab.json). Checked against the
[@zereight/mcp-gitlab README](https://github.com/zereight/gitlab-mcp/blob/main/README.md) on
2026-09-23.

## Routes

| Route | Recognised by | Mode comes from |
| --- | --- | --- |
| `@zereight/mcp-gitlab` | the npm package in the server's args, or a `mcp-gitlab` binary | `GITLAB_PERMISSION_MODE`, legacy `GITLAB_READ_ONLY_MODE` |
| `glab` CLI | on PATH | the token's scopes and your project role |

`GITLAB_PERMISSION_MODE` has three values, and the check distinguishes them:

| Value | Reads | Writes | Destructive (merge, delete, cancel, unprotect) |
| --- | --- | --- | --- |
| `readonly` | yes | no | no |
| `modify` | yes | yes | no |
| `full` | yes | yes | yes |

With neither variable set, this release reports the mode as `unknown` rather than relying on an
undocumented default, so a write asks you first. `GITLAB_TOOLS` (allow-list) and
`GITLAB_TOOLSETS` narrow further. `GITLAB_READ_ONLY_MODE=true` is deprecated upstream in favour of
`GITLAB_PERMISSION_MODE=readonly`.

A write profile for GitLab sets `GITLAB_PERMISSION_MODE=modify`, never `full`: destructive
operations stay out of reach unless you choose otherwise yourself.
