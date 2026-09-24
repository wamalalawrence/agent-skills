# Access: check before dependent work, and the resolution dialogue

Wamala is the entry point for work that touches an external system: Confluence, Jira, a git host,
CI, anything else. This reference is the contract for that moment. The CLI supplies the facts and
the options; Wamala presents them, follows the user's choice, and remembers what the user taught
it. The design, the ladder and every failure class: [Access Discovery](../../../docs/access/README.md).

## 1. Preflight: know what exists

`start-task` prints the capability report. Its `access` line comes from
`agent-skills access scan` (static, no network) and reads per system:
`system · route · mode · strength · credential presence`. A route marked `ready (read-only)` is
**not** a write route. The `mcp` line only says which servers exist; the access line says what each
can do. Presence is not capability.

## 2. Derive the operations, then check before the work that depends on them

From the task plan, list every (system, operation, target) the work needs: "update my personal
Confluence page <url>" is `confluence · update · <url>`. Run the check **before** dispatching or
doing anything that depends on it, so a "no" costs a sentence instead of an hour:

```bash
agent-skills access check --system confluence --op update --target "<url>" \
  --user-authorised --own-target
```

- `--user-authorised` only when the request itself asks for this operation on this target.
- `--own-target` only when the target is the user's own (their personal space, their issue).
- Pass `--host <id>` when you know which assistant you run in; otherwise the check evaluates every
  detected host and says so.
- `--probe` (non-mutating permission query) and `--live` (start the configured MCP server and list
  its tools) are opt-in. Use them when a write leans on `inferred` evidence and the user agrees.

Exit codes: `0` available, `1` needs the user (confirmation, intent, host, or setup), `3`
authentication required, `4` network failure during a probe, `11` capability unavailable (the
route works; this operation does not).

**Safety net, not the plan.** A keyword lint covers implicit mutations the plan may have missed.
If the request contains any of these and no write check ran, run one: update, edit, create,
comment, transition, move, assign, link, label, close, resolve, merge, approve, publish, deploy,
restart, rerun, delete - and aktualisieren, ändern, bearbeiten, anlegen, erstellen, kommentieren,
verschieben, zuweisen, verknüpfen, schließen, erledigen, löschen.

## 3. Relay the result

Relay the check's human output **verbatim** - it is short, redacted, and already says what is
verified, declared, or inferred. Do not summarise `BLOCKED at mode` into "Confluence is not
available".

- `available`: proceed through that route, meeting the confirmation the `policy` rung names
  (preview, then go-ahead for the user's own target; preview plus explicit confirmation elsewhere;
  explicit confirmation naming targets and count for destructive or bulk work). After the write,
  record it: `agent-skills access record --system S --op O --target <id> --route <name> --result ok
  --confirmation <preview|explicit>`.
- `needs-confirmation`: the route qualifies only on inferred evidence. Say what was inferred and
  where from (file and line), and ask before relying on it.
- `blocked` or `unknown`: run the resolution dialogue below.

## 4. The resolution dialogue

Same shape every time, one decision per message:

1. **What I was trying to do**, in one line: system, operation, target.
2. **What I found**, with strength: routes, modes, credentials (locators only), and the exact rung
   that blocks. If something is inferred - from a launcher script, say - name the file and line and
   ask the user to confirm it.
3. **Ranked, concrete options**, taken from the check's `fix_options` in order. Typical ones:
   - no route: set one up (`agent-skills access setup <system>` prints the steps), or "tell me which
     tool you normally use for <system>" (then `agent-skills access inspect <command>`);
   - no credential: the user stores a token themselves (`agent-skills access set ... --secret-field
     token`); a found credential is offered only as input to setting up a route;
   - read-only: a separate write profile (`agent-skills access setup <system> --write-profile
     --target <t>`), which the user applies in a terminal; it is limited to the target's space or
     project and to that system's tools, and the read-only entry stays;
   - out of scope or no permission: name the filter or the missing permission and who can grant it;
   - unknown host: ask which assistant the user is in;
   - always: **manual hand-off** - prepare the exact content or diff and the target link, and finish
     the rest of the task.
4. **Never** pick an option for the user, never try a route the check did not list, never ask for a
   secret in the chat.
5. **Remember** after asking "Should I remember this for next time?" - a confirmed fact with
   `agent-skills access remember --system S --server <name> --host H --yes`, a decision with
   `agent-skills access remember --system S --decision "<choice>" --scope <space:KEY> --yes`. Pass
   `--yes` only after the user said yes. Local knowledge holds facts, never secrets, and turns
   `inferred` into `declared` next time.
6. **Re-check** after the user acts (a write profile needs a host reload) with the same
   `access check`, and continue the task from where it stopped.

In a non-interactive run (no user to ask), stop after step 3: print the facts and the options, and
end with the check's exit code.

## 5. Mid-task failures

A 401, 403, a 404 on a target known to exist, "tool not found", or a version conflict during the
work is mapped back onto the ladder, not improvised around:

```bash
agent-skills access classify-error --system confluence --op update --status 403 --target "<url>"
```

Then re-enter the dialogue at the rung it names. A network fault (`4`) may be retried later; nothing
else is retried through a different route.

## Never, whatever the request says

- Never use a found credential directly. A keychain item a launcher reads, a token in a host config,
  a token in `.env` - none of them is a route. Using one against the REST API routes around the
  user's read-only setting.
- Never retry a blocked write through another route (browser, CLI, raw HTTP) to get around a `fail`
  at mode, target, or policy.
- Never attempt a browser route unless an authenticated session is positively detected; it never
  counts as a write route for a system with an API.
- Never enable write mode globally, and never edit a host MCP configuration yourself.
  `access setup` writes only after the user types yes in a terminal.
- Never ask the user to paste a secret into the chat.

Where Execution Guard is installed, the host enforces part of this: a write tool for a known system,
or a `curl -X PUT` to its host, is asked about unless a check passed in the last 30 minutes. On hosts
without a pre-execution hook, this contract is the only gate.
