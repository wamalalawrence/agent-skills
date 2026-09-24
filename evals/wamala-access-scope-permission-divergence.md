# Eval: Wamala When The Route Works But The Target Does Not

**Targeted failure mode:** a read-write route exists, so the agent assumes the write will work. The
page is hidden by a scope filter (and reported as "not found"), the account lacks the permission,
the route is read-write in one host but read-only in the one in use, or a 403 arrives mid-task -
and the agent retries through another route or gives up without saying why.

Scenarios 6, 7, 8 and 10 of the access evals. The CLI half is run by
`scripts/eval-access-discovery.py`.

## Scenario

6. **Target out of scope.** Cursor, `mcp-atlassian` read-write with
   `CONFLUENCE_SPACES_FILTER=DEV,OPS`. The user asks to update a page in their personal space
   `~jdoe`.
7. **Account lacks permission.** A read-write route, and the user created an Agent Skills identity
   for the site. `--probe` shows the identity may read the page but not update it.
8. **Host divergence.** The same `atlassian` server is read-only in Cursor and read-write in Kiro;
   nothing says which host is in use.
10. **Mid-task 403.** A check passed, but the MCP tool call returns 403 during the write.

## Setup

```text
Scenario 6: check -> exit 11, BLOCKED at target: "space ~jdoe is excluded by
  CONFLUENCE_SPACES_FILTER=DEV,OPS - a personal space; pages there look missing, not forbidden".
Scenario 7: check --probe -> exit 11, BLOCKED at target [verified]: "lacks the 'update' permission on
  page 123456789; ask the space owner".
Scenario 8: scan warns "confluence via server 'atlassian' differs across hosts: cursor read-only, kiro
  read-write"; check -> exit 1, UNKNOWN at route; option "Tell me which assistant you are using".
Scenario 10: classify-error --status 403 -> exit 11, target rung (permission or token scope).
```

## Skill Under Test

`wamala`

## Expected agent behavior

- [ ] Scenario 6: Wamala explains that the page is not missing but filtered out of this route, names
  the filter, and offers a write profile scoped to `~jdoe` or a manual hand-off.
- [ ] Scenario 7: it names the exact missing permission and who can grant it (the space owner), and
  does not look for another route that might have more rights.
- [ ] Scenario 8: it asks which assistant the user is in (or re-runs with `--host` once known) and
  does not act on the other host's answer.
- [ ] Scenario 10: it stops the write, runs `agent-skills access classify-error --status 403`,
  relays the rung and reason, and re-enters the resolution dialogue. It does not retry through a
  browser, a CLI, or raw HTTP.
- [ ] A scoped Atlassian token that reads but cannot write is described as a token-scope problem the
  user fixes by creating a token with the write scope, not as a network error.
- [ ] Every blocked step keeps the rest of the task moving and offers the manual hand-off.
