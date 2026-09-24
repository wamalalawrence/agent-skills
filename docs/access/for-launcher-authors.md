# For launcher authors: letting agents know your server's mode

Many organisations ship a small launcher script for an MCP server: it fetches a token from the OS
credential store, sets a few variables, and execs the upstream server. That is a good pattern -
it keeps tokens out of host configuration files. It has one cost: nothing outside the script
knows what mode the server runs in. An agent sees "configured", tries a write, and fails late.

Agent Skills reads a launcher statically to infer its mode (it never runs an unknown script), and
it asks the user to confirm what it inferred. You can make that exact instead of inferred, at no
cost to anyone who does not use Agent Skills.

## The convention

1. **Answer one flag.** When run as `<launcher> --agent-skills-capabilities`, print one JSON object
   on stdout and exit `0` without starting the server:

   ```json
   {
     "mode": "read-only",
     "mode_source": "MYORG_ATL_RW is not 1",
     "systems": ["confluence", "jira"],
     "enabled_tools": [],
     "toolsets": ["default"],
     "scope_filters": {"CONFLUENCE_SPACES_FILTER": ["DEV", "OPS"]},
     "deployment": "cloud",
     "credential_source": "macOS Keychain item myorg-atlassian"
   }
   ```

   `mode` is `read-only`, `read-write`, or `modify` (writes but not deletes). Everything else is
   optional. Never print a token, a password, or anything derived from one.

2. **Say the mode at startup, on stderr.** One line such as `myorg-mcp-atlassian: mode=read-only
   (set MYORG_ATL_RW=1 for writes)`. Stdout is the MCP stdio channel; anything else written there
   breaks the protocol.

3. **Keep the switch in the environment.** A variable the host's MCP `env` block can set
   (`MYORG_ATL_RW=1`) lets a user add a separate write profile with
   `agent-skills access setup <system> --write-profile` and leave the read-only entry alone.

A minimal shell implementation:

```bash
if [ "${1:-}" = "--agent-skills-capabilities" ]; then
  if [ "${MYORG_ATL_RW:-0}" = "1" ]; then mode=read-write; else mode=read-only; fi
  printf '{"mode":"%s","mode_source":"MYORG_ATL_RW","systems":["confluence","jira"]}\n' "$mode"
  exit 0
fi
[ "${MYORG_ATL_RW:-0}" = "1" ] || export READ_ONLY_MODE=true
echo "myorg-mcp-atlassian: mode=$([ "${READ_ONLY_MODE:-}" = true ] && echo read-only || echo read-write)" >&2
exec uvx mcp-atlassian
```

## When Agent Skills runs the flag

Only after a user marks your launcher as trusted to self-report on their machine
(`agent-skills access remember ... --trust-self-report`). An unknown script is never executed to
find out what it is. Without that mark, the static reading still works; it is just `inferred`
rather than `declared`, and the user is asked to confirm it.

## What helps static reading

If you cannot add the flag, these make the inferred answer right:

- set the upstream's documented mode variable (`READ_ONLY_MODE`, `GITHUB_READ_ONLY`,
  `GITLAB_PERMISSION_MODE`) directly, under a plain `if` on your own switch;
- read your switch with a default (`${MYORG_ATL_RW:-0}`);
- fetch credentials with a single visible command (`security find-generic-password -s <item> -w`,
  `secret-tool lookup ...`, `pass show ...`), so the locator can be reported without the value;
- exec the upstream (`exec uvx mcp-atlassian`) rather than wrapping it in further indirection.
