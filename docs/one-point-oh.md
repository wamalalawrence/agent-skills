# The 1.0 contract

What `agent-skills` commits to keeping stable from `1.0.0` onward. Everything here is frozen at
`v1.0.0-rc.1`: within the `1.x` line, names do not change, exit codes are not renumbered,
machine-readable shapes stay compatible, and removing any of it is a breaking change that waits
for `2.0`. Adding — a new command, a new flag with a safe default, a new capability, a new
optional field — stays allowed.

[Versioning](versioning.md) has the general policy. This page is the enumerated list.

## CLI command names

The launcher is `agent-skills`, resolved through any number of symlinks to the active release.

**Release lifecycle** — these share the exit-code table below:

```text
install    update    rollback    versions    check-updates    provider
verify     uninstall    hosts     doctor     migrate     version
```

**Task lifecycle:**

```text
start-task    finish-task
```

**Capability subsystems** — each is a namespace with its own subcommands and its own small exit
contract (stated with each):

```text
access <resolve|profiles|set|bind|unbind|forget|backend|import-legacy|check-permissions>
tools  <list|status|inspect|classify|resolve|capabilities|classes|doctor>
context <inspect|check|pack|explain|expand|cache>
guard  <check-command|explain|check-tool|scan-content|rules|audit|run|install|reconcile|verify|uninstall|doctor>
```

**Context and state helpers:**

```text
project    knowledge    memory    blackboard    org-memory    telemetry
plan-next    locate-config    auth-preflight    github-access
```

`dev` and `self-test` are development/internal entry points and are **not** part of the frozen
surface; they may change.

## Exit codes

### Release-lifecycle commands

`install`, `update`, `rollback`, `versions`, `check-updates`, `provider`, `verify`. Defined in
[`lib/asrelease/exits.py`](../lib/asrelease/exits.py), asserted by `scripts/test-release-engine.py`.

| Code | Name | Meaning |
| --- | --- | --- |
| `0` | ok | Succeeded. |
| `2` | usage-error | The invocation was wrong, or the request is not possible. |
| `3` | authentication-required | The release source needs credentials this machine does not have. |
| `4` | network-failure | The release source could not be reached. |
| `5` | integrity-failure | A payload was not what it claimed to be. Do not retry blindly. |
| `6` | installation-failure | The machine could not be changed; the previous release is still active. |
| `7` | verification-failure | The installation is in a bad state. Run `doctor`. |
| `10` | update-available | Informational, from `check-updates`. Not a failure. |

### Subsystem exit contracts

Distinct on purpose, the way `guard`'s predate the table above. Code `1` means different things
in different namespaces and never appears in the release table.

| Namespace | Codes |
| --- | --- |
| `access resolve` (and management verbs) | `0` resolved / action done · `1` not resolved (report names what is missing) · `2` usage or environment error |
| `tools` | `0` ok / resolved · `1` a `resolve` could not be satisfied, or `doctor` found a problem · `2` usage / unknown tool / unknown capability / blocked action class |
| `context check` | `0` under threshold · `10` over threshold · `2` usage or setup error |
| `context pack` | `0` ok · `1` nothing selected · `2` usage or setup error |
| `guard check-command` | `0` allow · `10` ask · `20` deny · `2` usage |

## Machine-readable output

`--json` is a supported, stable shape for: `hosts`, `versions`, `check-updates`, `provider`,
`doctor`, `project`, `access resolve` / `access profiles`, `tools list` / `status` / `inspect` /
`classify` / `resolve` / `capabilities` / `classes` / `doctor`, `context inspect` / `check` /
`explain`, and `guard rules` / `check-command` / `explain`.

Rules that hold across all of them:

- **No secret value ever appears** — not in stdout, stderr, a log, `doctor`, `verify`, tool
  output, an evidence pack, telemetry, or a context pack. Only whether a secret *resolves*.
- New fields may be **added**. Existing field names and their types do not change within `1.x`.
- A `--json` invocation that fails still exits with the code from the tables above; the error
  goes to stderr.

`plan-next` also emits JSON. Its pre-RC2 fields remain compatible; adaptive
execution adds `execution_mode` (string) and `execution_contract` (object).
Omitting `--mode` is `STANDARD`. Invalid modes exit `2`; a phase above the
selected mode's size budget is a successful stop decision, not a skipped phase.

## Error semantics

- A classification leads every failure message; a raw underlying error (a `git fatal:` line, a
  provider stack) is included only after that classification, and only after redaction.
- The installer never blocks on an interactive credential prompt. With no way to answer, it
  exits `3` rather than hanging.
- A failed release operation is atomic: nothing before `ACTIVATE` touches the machine, and a
  failed activation is rolled back. There is no mixed-version end state.

## Installation layout and semantics

```text
AGENT_SKILLS_HOME            default ~/.agent-skills — the canonical installation
  current -> versions/<v>    the single pointer that decides what runs
  versions/<v>/              a complete release: skills, scripts, lib, bin, docs, release.json
  state/                     install history; survives every upgrade
  cache/                     downloads; safe to delete
  install.json               version, provider, channel, registered hosts, timestamps
  VERSION                    the active version as plain text
  skills|scripts|lib|bin|docs|hooks -> current/...

<config-dir>                 default $XDG_CONFIG_HOME/agent-skills or ~/.config/agent-skills
  credentials.json           profile metadata only — never a secret value
  bindings.json              which identity a repository uses

~/.local/bin/agent-skills -> AGENT_SKILLS_HOME/bin/agent-skills
```

Frozen:

- **`AGENT_SKILLS_HOME`** names the install root; **`AGENT_SKILLS_CONFIG_DIR`** names non-secret
  user state. Both are honoured everywhere.
- **A version directory is complete and self-consistent.** Skills, runtime, and docs of one
  release are never mixed. `verify` fails (`7`) if the manifest, `current`, and the payload's own
  `VERSION` disagree.
- **`current` is the only activation lever.** Every host registration and every Execution Guard
  hook points through it, so one atomic symlink swap moves the whole machine.
- **`update` never downgrades as a side effect.** Going back is `rollback`. `--allow-downgrade`
  is required to make `update` move backward.
- **`rollback` is an undo, not a walk into the past.** After a rollback, the rollback target is
  the release you came from; a second rollback undoes the first.
- **`uninstall` removes only what this project owns** — releases under `versions/`, the
  activation pointer, the launcher link, host registrations that resolve into the install root,
  and Guard hook entries carrying this project's signature. It never removes a skill or hook the
  user wrote, a credential identity, a project binding, per-project memory, or a repository's
  committed knowledge base. `--purge` additionally removes credential metadata and bindings, and
  is the only thing that does.
- **Credentials live outside the install root**, so removing an installation cannot destroy an
  identity.
- **Channels:** `stable` never offers a pre-release; `rc` is a superset that also offers the
  stable release superseding the last candidate. The channel is recorded in `install.json`.
- **Nothing about installation asks for a project credential, a workspace, or a project key.**

## Release-provider interface

A provider answers exactly four questions and nothing else:

```text
resolve_latest(channel)   -> which release should I install?
resolve_version(v)        -> where is this specific release?
fetch_release(ref, dir)   -> put its payload here
verify_release(staged)    -> is this the release it claims to be?
```

`git` and `local` are the providers today. Everything after `fetch_release` — staging,
self-test, activation, host reconciliation, rollback — is provider-independent and does not
change. A provider is selected by name from a fixed in-process registry; there is no environment
variable or config file that loads a provider from a path.

Every release carries `release.json` (`schema: agent-skills.release/v1`) with a
`sha256-tree/v1` payload hash covering each file's path, executable bit, and content — not its
mtime or owner. Requested version, resolved tag, payload `VERSION`, and manifest must all agree
or it is an integrity failure (`5`).

## npm bootstrap

`@wamalalawrence/agent-skills` is a **public thin bootstrap**. It contains the installation
engine and nothing else — no skills, no docs, no product payload. `scripts/audit-npm-package.sh`
gates its contents and is a release blocker.

Frozen: **the bootstrap and the runtime move in lockstep.** `npm/package.json` `version` equals
the repository `VERSION` equals the git tag equals the manifest inside the payload, always.
`1.0.0` publishes both together; a `1.x.y` runtime release publishes a matching `1.x.y`
bootstrap. The bootstrap's job is only to fetch, verify, and hand over to a version-matched
installer.

## Skills

Nine top-level, two nested. These names do not change within `1.x`:

```text
wamala                 delivery-planner       delivery-runner
software-engineer      product-owner          manual-tester
test-automation-engineer   domain-modeler     context-optimizer

software-engineer/skills/issue-investigator   (nested)
software-engineer/skills/code-reviewer        (nested)
```

Frozen behaviour:

- **Wamala routes by engineering ownership, never by tool or provider.** It dispatches a
  fresh-context agent per step and never loads an executor skill into its own context.
- **One owner per dispatched step.** The engineer↔reviewer loop runs inside the implementation
  step at depth two; Wamala never appears in that chain.
- **Verification is by persisted artifact, not chat** — the evidence pack, the refinement, the
  test plan, the PR URL.
- **The lifecycle wrappers are mandatory:** `agent-skills start-task` before work,
  `agent-skills finish-task` after, with a lifecycle receipt in the output.
- **Every skill degrades safely** to CLI, then REST, then stopping and asking — no skill
  requires MCP.
- **The [destructive-action safety policy](destructive-action-safety.md) floor is above all of
  it** and is not waivable by prompt, by routing, or by repository configuration.

## Engineering Tool Capability Framework

Frozen at the [`v0.44.0`](engineering-tools.md) contract.

- **Tool classes:** `AGENT_HOST`, `LOCAL_TOOL`, `REMOTE_SERVICE`, `RUNTIME_RESOURCE`,
  `DATA_RESOURCE`.
- **Action classes:** `READ`, `WRITE`, `ELEVATED`, `DESTRUCTIVE`, fixed per capability.
  `resolve` refuses `WRITE`/`ELEVATED` without `--allow-write` and never resolves `DESTRUCTIVE`.
- **Capability vocabulary:** the 18 family prefixes are the stable extension points —
  `scm tracker knowledge communication runtime infrastructure cloud api ci quality observability
  incident messaging database data_pipeline package design security`. Individual capability
  names and their action classes are frozen; adding a capability under an existing family is a
  compatible change. Full list: [engineering-tool-capabilities.md](engineering-tool-capabilities.md).
  `data_pipeline.*`, `design.*`, and `security.*` ship with vocabulary and design but no
  validated reference tool in `1.0`; that does not change the names.
- **Tool-definition schema:** `agent-skills.tool-definition/v1`. Adding a transport `kind` is
  additive; changing the meaning of `class`, `capabilities`, or `transports` is not.
- **Transport resolution order** is deterministic: host → MCP → authenticated CLI →
  local/native client → connection profile → API adapter → unresolved. A capability the
  environment already holds always beats a stored credential.
- **Fixtures are never supported tools.** `lib/tools/fixtures/` is opt-in behind
  `--include-fixtures`, labelled, and `reference_status: "fixture"`; the framework has no
  per-provider branching.

## Not frozen

- The set of reference tool definitions in `lib/tools/registry.d/` — providers may be added.
- `doctor` / `verify` human-readable *layout* (the `--json` shape is stable; the prose is not).
- Warning text, log wording, and the exact contents of an evidence pack.
- `dev`, `self-test`, and anything under `scripts/` invoked directly rather than through
  `agent-skills <command>`.
- Which agent hosts are in `lib/hosts.registry` — hosts move quickly and the table follows them.

## Related

- [Versioning and exit codes](versioning.md) — the policy this enumerates.
- [Installation](installation.md) · [Updates](updates.md) · [Release providers](release-providers.md).
- [Engineering Tool Capability Framework](engineering-tools.md) · [capability vocabulary](engineering-tool-capabilities.md).
- [Known limitations](known-limitations.md) — what none of this guarantees.
