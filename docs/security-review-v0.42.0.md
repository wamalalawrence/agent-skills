# Security Review — v0.42.0 (Execution Guard)

Scope: the runtime enforcement layer added in this release —
[`scripts/guard.py`](../scripts/guard.py), `guard_parse.py`, `guard_paths.py`, `guard_rules.py`,
`guard_policy.py`, `guard_audit.py`, `guard_hosts.py`, `lib/guard.registry`, and the changes to
`bin/agent-skills`, `lib/install.sh`, and `scripts/doctor.sh`.

This release changes the trust boundary around repository-supplied content and writes to global
host configuration, so a review is required by
[the release checklist](release-checklist.md#security-review).

Every claim below is labelled **probed**, **reasoned about**, or **unproven**. An unlabelled
claim reads as evidence when it is not, which is the mistake v0.37.0 made.

## What this feature is, stated precisely

A deterministic pre-execution check. Given an action the agent has already decided to take, it
answers `ALLOW`, `ASK`, or `DENY` before the host executes it, wherever the host provides an
interception point.

What it is **not**, stated equally precisely: it is not a sandbox, not an IAM control, not a
prompt-injection detector, and not a guarantee. The
[destructive-action policy](destructive-action-safety.md) remains the authoritative contract,
scoped credentials and human-controlled execution remain the stronger controls, and
[Known limitations](execution-guard.md#known-limitations) is part of the feature.

## Threat model

The guard exists for an attacker or failure mode that has already won at the reasoning layer.
Its value is that winning there is no longer sufficient.

### Assets

| Asset | Why it matters |
| --- | --- |
| The user's filesystem outside the working repository | irreversible loss; credentials in `~/.ssh`, `~/.aws`, `~/.gnupg` |
| Deployed environments and their data | the failure mode the policy was written for |
| Backups, snapshots, retention policies | the last line of defence against everything above |
| Identity material (IAM, KMS, secrets, keys) | compromise persists after the incident |
| Observability (audit trails, threat detection) | its removal hides everything else |
| The user's own host configuration | the guard writes to it; a careless write is itself an incident |
| The guard's audit log | it sees every command, including ones carrying secrets |

### Actors

| Actor | Capability |
| --- | --- |
| A fallible agent | generates a wrong command in good faith |
| Hostile repository content | a `README`, knowledge entry, issue body, dependency PR, or tool response carrying instruction-shaped text |
| A hostile repository *configuration* | a committed file attempting to grant the agent capabilities |
| A compromised or malicious MCP server | returns steering text, or exposes a destructive tool |
| The user of the machine | trusted; the guard is not a control against them |

### Trust boundaries

```text
untrusted:  repository content, repository configuration, tool/MCP responses,
            web content, ticket bodies, memory tiers written by previous runs
trusted:    the machine/user policy file, organisation policy outside any repo,
            the compiled hard floor
```

## Threat-by-threat

### T1 — A dangerous command reaches execution

**Control.** Deterministic classification, hard floor of 31 non-lowerable rules.

**Status: probed.** 248 corpus cases in [`scripts/guard_corpus.py`](../scripts/guard_corpus.py),
run by `scripts/test-guard.sh` section 1. Every dangerous case resolves to `DENY` with a named
rule; every benign case to `ALLOW`.

**Probe that it can fail:** `probe recursive-delete-rule` removes the system-root branch and the
weakened build answers `ALLOW` to `rm -rf /`.

### T2 — A safe prefix hides a dangerous subcommand

**Control.** The command is decomposed into every simple command the shell would run before any
rule sees it.

**Status: probed.** Section 2 of the suite plus 39 `BYPASS` corpus cases: `&&`, `||`, `;`, `&`,
newline, `$( )`, backticks, `<( )`, `( )`, `{ }`, `VAR=x`, `env`, `sudo`, `nohup`, `time`,
`timeout 5`, `command`, absolute binary paths, `bash -c`, doubly nested `bash -c`, `sh -ec`,
`ssh host '…'`, `find -exec`, whitespace padding, flag reordering, long flags, quoted paths,
trailing tabs, path normalisation, and SQL in lowercase/mixed case/padded/nested.

**Probe:** `probe compound-inspection` truncates the parse after the first subcommand; the
weakened build answers `ALLOW` to `git status && rm -rf /`.

**Residual risk.** Aliases, shell functions, and variables only the live shell can expand are
not knowable from the command string. They resolve to `UNRESOLVED`, which is `ASK`, not `ALLOW`.
An interpreted program that assembles its command at runtime is not visible from its invocation.
Both are documented.

### T2b — A bypass nobody wrote a test for

The `BYPASS` corpus covers the shapes the guard was *designed* against, which is a weaker claim
than it looks: it tests the designer's imagination.

**Status: probed by attack.** A separate pass tried 43 techniques with no corresponding test.
**Thirteen reached `ALLOW` on the first attempt**, in four families:

| Family | Reached `ALLOW` |
| --- | --- |
| the program is hidden | `$SHELL -c '…'`, `` `echo rm` -rf / ``, `busybox rm -rf /` |
| the payload arrives out of band | `bash <<< '…'`, `bash < script.sh`, `psql -f x.sql`, `cat drop.sql \| psql` |
| deletion by another route | `find / -delete`, `perl -e 'unlink glob "/*"'`, `__import__('shutil').rmtree('/')`, `truncate -s 0 /etc/passwd` |
| fetch and execution separated | `curl URL -o /tmp/s && sh /tmp/s` |

All thirteen are fixed. Four rules were added — `EXEC_UNRESOLVED_COMMAND`, `EXEC_OPAQUE_INPUT`,
`DB_OPAQUE_STATEMENT`, `FETCH_THEN_EXECUTE` — and the parser gained here-strings, multi-call
binaries, and detection of a command whose program name it cannot read. After the fixes, 0 of 43
reach `ALLOW`, the existing corpora are unchanged, and p95 is unmoved.

All 28 are permanent regression cases in the `REDTEAM` corpus.

**The lesson is about method, not about these thirteen.** Four green corpora and seven passing
mutation probes were not sufficient evidence that the guard could not be bypassed; attacking it
was. A guard reviewed only against the cases its author thought of is reviewed against the wrong
threat model.

### T3 — A parse failure is read as permission

**Control.** `unparsed` is a first-class field. A parse failure runs a crude signature scan that
can escalate to `DENY`, and otherwise resolves to `ASK`.

**Status: probed.** `rm -rf '/unterminated` → `DENY` (`PARSE_UNRESOLVED_HIGH_RISK`);
`npm test "unterminated` → `ASK`; `$(rm -rf /` → `DENY`; substitution nested past the depth
ceiling → not `ALLOW`.

**Probe:** `probe parse-failure-floor` empties the signature list; the weakened build downgrades
the unterminated dangerous command from `DENY` to `ASK`.

### T4 — A host payload shape changes and the guard silently allows everything

This is the failure mode that would be hardest to notice: the hook keeps running, keeps
answering, and answers `allow` to everything.

**Control.** An unrecognised payload raises rather than producing an empty action, and resolves
through the same fail-closed path as any other failure.

**Status: probed.** Section 9: an empty payload, a payload with no `tool_name`, and a payload
whose `command` field has been renamed to `cmd` all produce `permissionDecision: "ask"`, not
`"allow"`. Unparseable stdin does the same.

**Finding raised and fixed during this review.** The first implementation built an `Action` with
an empty command in exactly that case. An empty action matches no rule, which reads as `ALLOW`.
Caught by adding a malformed-payload case to the dialect tests; fixed by `PayloadShapeError`;
pinned by two assertions.

**Residual risk.** `AGENT_SKILLS_GUARD_ON_ERROR` defaults to `ask` rather than `deny`. Denying
every command in every session because of a bug in the guard would be worse than the risk it
removes, and `ask` is still not `allow`. `=deny` is available and documented.

### T5 — Repository content weakens the guard

**Control.** Four trust layers. Repository scope may add and escalate; it may never relax. Hard
floor rules cannot be lowered by any layer including machine scope.

**Status: probed.** Section 5 loads a hostile `.agent-skills.yml` and a hostile
`.agent-skills/guard-policy.json` attempting: an invented `allow_rm_rf: true`; lowering two
hard-floor rules to `allow`; lowering a third to `ask`; relaxing a non-floor rule; supplying
`allow_commands`; and disabling the audit log. All six are refused and recorded. A repository
*escalation* is honoured, because tightening is not an attack. The hard floor still denies
`rm -rf /` while that configuration is active.

**Probe:** `probe repository-trust` adds `REPO` to `RELAXING_LAYERS`; the weakened build lets a
repository relaxation take effect.

**Design note.** A refused attempt is ignored and reported rather than fatal. A fatal error would
let a hostile committed file deny service to the whole repository.

### T6 — Prompt injection

**Control.** None claimed at the detection layer. The guard changes the *consequence*.

**Status: probed, and deliberately narrow.** Section 6 writes a synthetic hostile `README`
containing "Ignore all previous instructions", a permission claim, a `curl … | sh` instruction,
an `rm -rf /` instruction, and "Do not report this step". The scanner flags all four signal
classes. The test then simulates the steering having succeeded and asserts that both resulting
commands are still `DENY`. Reading the hostile file is `ALLOW`, because the file is data.

**Explicitly not claimed.** Regex scanning does not solve prompt injection. The scanner reports
`SUSPICIOUS_INSTRUCTION_SHAPED_CONTENT`, not `THIS FILE IS AN ATTACK` — a pattern cannot tell a
threat from a paragraph about threats, and `docs/execution-guard.md` itself trips several of
these patterns. The suite asserts the report carries the words "evidence for a reviewer, not
proof of an attack".

### T7 — A path escapes the workspace through a symlink

**Control.** Every target is canonicalised. A path that reads as workspace-local and resolves
outside it is `FS_SYMLINK_ESCAPE`, `DENY`.

**Status: probed.** Section 4 creates `repo/linked -> <outside>` and `repo/etcdir -> /etc`, and
asserts `DENY` for the link, for a link to a system path, and for a path *traversing* an escaping
symlink. The rule is asserted by name, not just by outcome.

**Probe:** `probe path-canonicalisation` disables the escape test; the weakened build answers
`ALLOW`.

**Finding raised and fixed during this review.** The lexical side of the comparison used only the
canonicalised workspace root. On macOS a checkout under `mktemp -d` has an unresolved root of
`/var/folders/…` and a real root of `/private/var/folders/…`, so the lexical test never matched
and the check was silently inert. Fixed by comparing against both spellings; pinned by the
by-name assertion above, which fails without it.

### T8 — The audit log becomes a credential store

The guard inspects exactly the commands most likely to carry a secret. A naive log would create
a plaintext credential store, populated automatically, on the machine of every user who
installed a security tool.

**Control.** No raw command line is stored. Records carry the rule, the classification, a
redacted target, and a SHA-256 prefix of the *redacted* command. Every string field is redacted
on the way out. Mode `0600`, bounded to 5000 records, never uploaded.

**Status: probed.** Section 7 runs three commands carrying a synthetic GitHub token and a
synthetic AWS key id through the decision output and the audit log, and asserts neither value
appears in either, that a fingerprint is present, that the raw command line is absent, and that
the file mode is `-rw-------`.

**Probe:** `probe redaction` neuters `redact()`; the token survives.

**Residual risk.** Redaction is pattern-based. An unrecognised internal credential format can
reach the log's `target` field. The mitigation that does not depend on pattern coverage is that
the command itself is never stored — only a digest. `AGENT_SKILLS_GUARD_AUDIT=off` disables the
log entirely, and repository configuration cannot turn it off (only the user or the organisation
can), because a hostile file must not be able to blind the record.

### T9 — Installation damages the user's host configuration

The guard writes to `~/.claude/settings.json`, `~/.cursor/hooks.json`, `~/.kiro/hooks/`, and
`~/.codex/hooks.json` — files the user owns, that decide what their agent may do.

**Control.** Merge, never replace. Ownership by command signature. Backups. Idempotency. Refusal
on malformed input. Refusal to claim a same-named file we did not write.

**Status: probed.** Section 8 seeds pre-existing user hooks in Claude Code and Cursor and asserts
they survive install; that `--dry-run` writes nothing; that a backup appears; that Cursor is
registered `failClosed`; that a second install adds no second entry; that uninstall removes ours
and leaves theirs; that a foreign Kiro file is untouched; and that a non-JSON config is refused
rather than replaced.

**Probe:** `probe host-ownership` removes the signature test from `_is_ours`; the weakened build's
uninstall destroys the user's own `user-audit.sh` hook.

**Decision recorded.** `setup.init` and `agent-skills install` do **not** install the guard. They
print a recommendation and the exact commands. Silently changing security-sensitive IDE
configuration as a side effect of installing skills would be the wrong default even for a control
that improves safety, because the user's consent is scoped to what they asked for.

### T10 — The guard is so noisy it gets disabled

A disabled guardrail protects nothing, which makes usability a security property here rather than
a nicety.

**Status: probed.** 77 benign cases spanning six build ecosystems, formatters, git inspection,
reading and searching, build-output cleanup, local containers, read-only cloud and cluster
investigation, and local test databases — all `ALLOW`. Three cases whose *text* contains a
dangerous command while doing nothing dangerous (`echo`, `grep`, a commit message) are `ALLOW`,
which is what structural parsing buys.

**Calibration decisions recorded.** An ordinary MCP mutation (create an issue, post a message) is
not turned into an `ASK`; only destructive verbs, identity/secret mutations, and mutations in
hard-to-undo domains are gated. `docker compose down -v` is `ASK` rather than `DENY`, while
`docker volume rm` and `docker system prune` stay `DENY` because the existing policy names them.

### T11 — Performance makes the guard a liability

**Status: probed.** 1540 samples over the benign corpus: p50 0.09 ms, p95 0.26 ms, p99 0.39 ms,
max 0.58 ms in-process; ~68 ms per cold invocation including Python startup. The suite fails if
p95 exceeds 5 ms.

**Design note.** Two choices keep it there: no model is ever consulted, and the repository root
is found by walking up for `.git` rather than shelling out to `git rev-parse` — the subprocess
cost more than the entire rule evaluation that followed it, at roughly 15 ms against 0.1 ms.

### T12 — MCP and structured tools bypass the guard entirely

**Control.** The engine is built on an action abstraction, not a shell string. Embedded shell
strings, embedded SQL, and the tool's own verb are all inspected.

**Status: probed.** An MCP `query` carrying `DROP TABLE` is denied through both the Claude Code
and Cursor dialects; a structured `Write` to `/etc/hosts` is denied; a cluster-deletion MCP tool
is denied; a benign MCP read is allowed.

**Residual risk.** Coverage depends on the host exposing MCP interception. Cursor and Claude Code
do; a host that gates only shell leaves structured tools ungated, and `guard doctor` does not
currently distinguish shell-only from shell-plus-MCP enforcement. **Unproven** for any host not
in the four tested dialects.

### T13 — The engine's answer depends on what it was asked before

**Control.** Every per-call fact — the branch, the environment, the kube context, the configured
protected branches — travels through a `context` dictionary built per call. No module-level state
is mutated during evaluation.

**Status: probed.** Section 5b evaluates the same command in two workspaces in one process and
asserts that the configured workspace denies, the unconfigured one asks, and the compiled branch
pattern does not grow across five further calls.

**Found in diff review, after the suites were green.** The first implementation rebuilt
`PROTECTED_BRANCHES` on every call, appending the configured names each time. Measured against
the pre-fix build, the pattern grew 90 characters over five calls and the second workspace
inherited the first one's configuration. In a per-command hook the process is short-lived, so
this would rarely have been noticed in production — which is precisely why a test loop, a
wrapper-mode session, or any future long-lived caller would have been the place it eventually
mattered.

### T14 — Time-of-check / time-of-use

**Status: reasoned about, not mitigated.** The decision is made against the command as written,
immediately before execution. A target whose meaning changes in that interval — a symlink swapped
between check and run — is not covered. This is inherent to the interception point, and is
documented in both limitation sections rather than papered over.

## Findings raised during this review

| Ref | Finding | Resolution |
| --- | --- | --- |
| 1 | A malformed or renamed hook payload produced an empty action, which read as `ALLOW` | `PayloadShapeError`; fail-closed to `ASK`; two regression assertions |
| 2 | The symlink-escape lexical comparison used only the canonicalised root, silently disabling the check under a `mktemp` checkout | compare both spellings; rule asserted by name |
| 3 | A temp- or `/var`-backed workspace read as a system path, denying build-output cleanup there | workspace membership decided before the absolute-path rules |
| 4 | Home and credential directories were checked after the temp exemption, and `$HOME` was compared uncanonicalised | home checked first; `_home()` returns a real path |
| 5 | The relaxation ceiling started at each rule's default, making machine-scope policy inert | ceiling starts at the floor for floor rules and at `ALLOW` otherwise |
| 6 | A refused weakening attempt attached an `ASK` to every decision in the session | note by default; finding only when it targeted a rule the action triggered |
| 7 | The content scanner reported one signal per line, hiding the more concrete of two | all matching signals reported |
| 8 | Redaction's assignment rule matched query parameters and greedily truncated the record | anchored to start-or-whitespace |
| 9 | `timeout 5 <cmd>`, `env \| curl`, and `rm --recursive` were mis-parsed | duration skipped, wrapper stripping cannot consume the whole command, long flags recognised |
| 10 | The configured branch list was folded into a module-level regex per call, so it grew without bound and leaked between workspaces | per-call context; three regression assertions |
| 11 | Every `--` was stripped from the inspected command, not only the leading separator | leading separator only; regression assertion |

Findings 1–4 are security defects. Finding 10 is a correctness defect with a security edge: the
engine was not reentrant, so a configuration read for one repository silently applied to the
next one evaluated in the same process. The direction of that leak was stricter rather than
looser, so it was not exploitable, but an engine whose answer depends on what it was asked
previously is not one whose decisions can be reasoned about. Findings 5–9 and 11 are correctness
or usability defects; 6 has security consequences, because an unusable guard gets disabled.

Findings 10 and 11 were found by reading the diff **after** every suite was green, which is the
step the release checklist requires for exactly this reason.

Accepted rather than fixed:

- **Kiro's contract has no "ask".** `ASK` is surfaced into the agent's context rather than
  blocking. Documented in `lib/guard.registry`, in `docs/execution-guard.md`, and switchable with
  `AGENT_SKILLS_GUARD_ASK_FALLBACK=deny`. Blocking on `ASK` by default would make `git push`
  impossible in Kiro, which is not a trade the user asked for.
- **Codex's hook contract is documented as Claude-compatible but was not verified against a live
  Codex install.** The adapter is tested against the documented contract. `guard doctor` reports
  `AVAILABLE` until the hook is actually registered. **Unproven** on a live install.

## Residual risks

| Risk | Control offered | Why it is not the default |
| --- | --- | --- |
| Internal failure resolves to `ASK`, not `DENY` | `AGENT_SKILLS_GUARD_ON_ERROR=deny` | a guard bug that blocked every command would be worse than the risk removed |
| Audit log records `ASK`/`DENY` only | `AGENT_SKILLS_GUARD_AUDIT=all` | recording every `ALLOW` on every shell command is large and slow for no security gain |
| Redaction is pattern-based | the raw command is never stored, only a digest | pattern coverage cannot be complete |
| Four hosts enforce; the rest do not | `agent-skills guard run` wrapper mode | wrapper mode only covers commands routed through it |
| A local user can remove the hook | none | these are the user's own files; the guard is not a control against them |
| No sandbox, no IAM | the policy's scoped-credential and human-execution requirements | a guard cannot substitute for least privilege |

## Behaviours pinned by tests

Each of these was a deliberate decision, and each would otherwise drift away from the
documentation:

- Quoted dangerous text is `ALLOW` (`echo "rm -rf /"`).
- Build-output deletion is `ALLOW`; tracked-source deletion is `ASK`.
- Repository escalation is honoured; repository relaxation is not.
- Machine scope may relax a non-floor rule and may not relax a floor rule.
- `ALLOW` decisions are not audited by default.
- Cursor registration carries `failClosed`.
- Every rule has a safe alternative and a known category.
- p95 stays under 5 ms.

## Probe discipline

Seven mutation probes. Each copies the runtime into a sandbox, removes one guarantee, and
asserts the corresponding check then gives the weaker answer. A probe that cannot be set up —
because the pattern it removes no longer exists — fails loudly rather than passing silently.

| Probe | Removes | Weakened build answers |
| --- | --- | --- |
| `recursive-delete-rule` | the system-root branch | `ALLOW` to `rm -rf /` |
| `compound-inspection` | parsing past the first subcommand | `ALLOW` to `git status && rm -rf /` |
| `path-canonicalisation` | symlink-escape detection | `ALLOW` to a delete through an escaping symlink |
| `parse-failure-floor` | the unparseable-input signatures | `ASK` where `DENY` is required |
| `repository-trust` | the repository-cannot-relax rule | the repository relaxation takes effect |
| `redaction` | secret redaction | the token survives into the record |
| `host-ownership` | the ownership signature test | uninstall destroys the user's own hook |

## Conclusion

The release adds a real control with real limits, and both are documented in the same voice.
Fourteen of fifteen threats are probed; T14 is reasoned about and documented as unmitigated;
two items are explicitly marked unproven. Eleven defects were found — four of them security
defects, three of which would have made a control silently inert while continuing to report
success. That is the failure mode probe discipline exists to catch, and it caught them. Two more
were found by reading the diff after every suite was green, and thirteen bypasses were found by
attacking the guard after that — which is why "the tests pass" is not where this review ended.
