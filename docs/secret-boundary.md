# The secret boundary

Where a credential is allowed to travel, and what stands in the way when it tries to go
somewhere else.

## The boundary

```text
credential store / environment
        ↓
authorized process or tool
        ↓
remote system
```

Not this:

```text
credential
        ↓
stdout / stderr
        ↓
agent context
        ↓
conversation
```

The second path is one-directional. A value that reaches model context is in the transcript, in
every summary of that transcript, and in whatever the agent writes next. Deleting the message
afterwards does not unsend it. That is why this is treated as a release blocker rather than a
hygiene issue: there is no remediation available after the fact, only rotation.

This page exists because the second path was taken. A script printed two database passwords into
a chat during otherwise ordinary read-only work.

## The primary control: never hold the credential

The control that actually works is not scrubbing — it is never putting the value on a command
line in the first place.

- Resolve service access through the [Access Resolver](access-resolution.md). It answers
  *whether* an identity resolves and hands the authorized process what it needs; it does not
  print values, and `access resolve` output carries field names only.
- Prefer a client that reads its own credential from the environment or a profile
  (`psql` with `~/.pgpass`, `mysql` with `~/.my.cnf`, `aws` with a named profile) over one that
  takes it as an argument. A command line is visible in `ps`, in shell history, in the Execution
  Guard's decision log, and in whatever the agent captured.
- Never write a credential into a script in order to run the script.
- Never echo one to confirm it was set. `[ -n "$PGPASSWORD" ] && echo set` answers the same
  question.

## The second control: redaction at the boundary

Discipline fails. So redaction is applied where text crosses into somewhere it cannot be
recalled from — as defence in depth, never as the reason it was safe to hold the value.

### The filter

```bash
some-command 2>&1 | agent-skills redact
agent-skills redact --check build.log
```

`redact` removes credential-shaped values from stdin (or named files) and writes the rest to
stdout. `--check` transforms nothing, writes nothing to stdout, and exits `1` when it found
something — the mode a pre-flight or CI step uses. It reports line numbers, never the line,
because the line is what holds the secret.

Pipe anything through it that reads a connection string, dumps a config, prints an environment,
or reports its own failure with the arguments it was given.

Exit codes: `0` processed, or `--check` found nothing · `1` `--check` found something ·
`2` usage or I/O error.

### Redaction on write

Five paths redact whether or not anyone remembered to pipe, because they are where a forgotten
value comes to rest and gets read back into the *next* agent's starting context:

| Path | Why it redacts on write |
| --- | --- |
| [Blackboard](task-blackboard.md) (`append`, `artifact`, `progress`, `handoff`) | Where skills paste tool output, and it is re-read by design |
| [Project memory](project-memory.md) (`note`, and every `finish-task` flag that reaches it) | Outlives the task; loaded by every later `start-task` |
| [Org memory](org-memory.md) (`note`, `promote`, and `--promote-to-org`) | The widest reach of the five: printed into every later task in *every* project |
| [Telemetry](telemetry.md) | Append-only, so a mistaken value cannot be edited out |
| [Repo knowledge base](repo-knowledge.md) (`note`, `lesson add`) | **Committed.** A credential written here is a credential published |

Org memory was the one durable tier with no redaction until `1.0.0-rc.4`, and the one where the
consequence is largest: a value promoted there travels out of the project that recorded it. The
redaction now happens in `append_note`, so `note`, `promote`, and every future writer inherit it
rather than each remembering to ask.

All five write through `scripts/durable.py`: a temporary file plus `os.replace` under an advisory
lock, so two agents appending at once cannot lose a bullet and a crash cannot leave a store no
reader can parse.

The Execution Guard's decision log uses the same implementation from the other direction — it
inspects the commands most likely to carry a secret and must not become the store that keeps
them.

There is one pattern set, in `scripts/guard_audit.py`. A second would drift from the first and
the weaker of the two would end up deciding.

### Shape survives, value does not

```text
PGPASSWORD=[redacted] psql -h db.internal -U svc
postgresql://svc:[redacted]@db.internal:5432/payments
```

Both still say which variable was set, which host was reached, and which user was used. A
scrubber that emits an opaque hash has moved the problem to whoever has to debug the failure.

## What is covered

Connection URLs with inline credentials, `PGPASSWORD` / `MYSQL_PWD` / `DB_PASS` style
assignments, `mysql -p<value>`, libpq keyword strings, JDBC parameters, quoted values under
credential-shaped JSON and YAML keys, `Authorization` and `X-API-Key` headers, `--password` and
`--client-secret` flags, AWS access-key ids, GitHub and Slack tokens, JWTs, PEM private key
blocks, signed-URL query parameters, and long high-entropy strings as a backstop.

`scripts/test-secret-boundary.sh` asserts each shape, asserts the diagnostic context survives,
and carries mutation probes that delete one pattern and confirm the matching case then leaks.

## What is not covered

Stated plainly, because a control whose limits are undocumented gets trusted past them.

- **Prose that does not look like a credential.** "The password is the project name" is not
  redactable without redacting English. Only `password <value>` where the value is at least
  eight characters and contains a digit is caught.
- **Short or low-entropy secrets** with no surrounding key name. A four-character PIN in a
  sentence is indistinguishable from a number.
- **Encoded values.** A base64 or hex blob under a key name is caught by the key name; the same
  blob alone is caught only if it clears the entropy threshold.
- **A credential the agent has already read into its own context** before any redaction point.
  Nothing downstream can retract that — which is the whole reason the primary control is not
  holding the value at all.
- **Screenshots and images.** Not text; not scanned.

## If a credential does reach a transcript

Treat it as disclosed, not as at-risk.

1. Rotate the credential. Do not skip this because the conversation looks private.
2. Note where it came from — which command, which tool, which output stream.
3. If the shape was one this page claims to cover, that is a defect in the pattern set: add the
   case to `scripts/test-secret-boundary.sh` with a mutation probe, then fix it.

## Related

- [Access resolution](access-resolution.md) — how a service identity is resolved without a value
  ever being printed.
- [Execution Guard](execution-guard.md) — the deterministic check before a command runs.
- [Destructive-action safety](destructive-action-safety.md) — the floor that forbids using a
  discovered credential at all.
- [The 1.0 contract](one-point-oh.md) — "no secret value ever appears in any output" as a frozen
  guarantee.
