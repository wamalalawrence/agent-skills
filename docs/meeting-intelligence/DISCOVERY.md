# Meeting Intelligence: discovery

This was written before any Meeting Intelligence code, against the `1.1.0` release tree (commit
`9a3ba19`). It records what exists, what the feature brief assumed, where they disagree, and the
design decisions that follow. Every later file in this feature traces back to a row here.

## 1. The named subsystems, as they actually exist

### Engineering Tool Framework — exists

- Where: `scripts/tools.py`, `lib/tools/`.
- Entry points: `agent-skills tools list/status/inspect/classify/resolve/doctor`.
- Owns: the capability vocabulary, transport resolution, and READ/WRITE/DESTRUCTIVE classification
  of actions against external tools. It never authenticates and never runs a request.

### Access Resolver — exists

- Where: `scripts/access.py`.
- Entry points: `agent-skills access resolve/profiles/set/bind/unbind/forget/backend`; in-process
  `resolve_access()`.
- Owns: credential identities (profiles), OS-native secret storage (macOS Keychain, libsecret, a
  `0600` file fallback), the precedence order, and the rule that a committed file cannot select an
  identity. It owns **authentication only**. It does **not** own scope or access decisions for
  knowledge; nothing in it knows about knowledge scope.

### Context Optimizer — exists

- Where: `scripts/context.py`, `skills/context-optimizer/`.
- Entry points: `agent-skills context inspect/check/pack/explain/expand/cache`.
- Owns: deterministic, budget-bounded **selection** from a large input, with provenance, explicit
  omissions, redaction, and instruction-shaped-content marking. It has no coverage-preserving mode:
  a pack deliberately drops what is irrelevant to a brief.

### Knowledge system — exists, three tiers

- Where: `scripts/knowledge.py` (repository tier, committed), `scripts/project-memory.py` (project
  tier, gitignored cache), `scripts/org-memory.py` (org tier, gitignored cache).
- Entry points: `agent-skills knowledge path/init/read/note/lesson/decay/doctor/promote`,
  `agent-skills memory …`, `agent-skills org-memory …`; `start-task` reads all three.
- Owns: see §3 and §4.

### Wamala — exists

- Where: `skills/wamala/`; routing table in `skills/wamala/references/routing-table.md`.
- Owns: classification and dispatch to specialist skills. It implements, reviews, and tests
  nothing itself.

### Secret protection — exists, two implementations

- Where: `scripts/guard_audit.py` `redact()` (the documented single implementation, used by
  `redact.py`, `knowledge.py`, `project-memory.py`, `org-memory.py`, and the guard log), and
  `scripts/context.py` `redact()` (a second, labelled pattern set used for packs).
- Entry point: `agent-skills redact [--check]`.
- Owns: credential-shaped values in text. Neither recognises a secret that was **spoken**: spelled
  out letter by letter, or split across two utterances.

### Prompt-injection protection — exists, pattern-based

- Where: `context.py` `INJECTION_PATTERNS` / `looks_like_instruction()`; `knowledge.py`
  `INJECTION_PATTERNS` (doctor); `guard scan-content`.
- Entry points: `agent-skills guard scan-content`, `agent-skills knowledge doctor`.
- Owns: marking instruction-shaped text as untrusted data and preserving it as evidence. There is
  no model-side sandbox: the protection is the data contract plus marking.

### CLI conventions — exist

- Where: `bin/agent-skills` (bash dispatcher), `lib/asrelease/exits.py`.
- Owns: frozen exit codes, one launcher, and helpers resolved through `current`, so a command
  always delegates to `scripts/<helper>` from the **same** release.

Nothing named in the brief is missing. Two are shaped differently than the brief assumes:

- **Access Resolver does not own scope/access decisions for knowledge.** It resolves credentials.
  Knowledge isolation today is physical: the repository tier lives inside the repository. The
  brief's suggestion to "reuse Access Resolver if that is what owns scope/access decisions" does
  not apply, because it is not what owns them. Isolation is enforced in the Knowledge read path
  instead (§7 of the brief), which is where retrieval happens.
- **Context Optimizer selects; it does not window.** Meeting extraction needs every segment read
  exactly once (plus overlap), not the fragments most relevant to a brief. See deviation D3.

## 2. Where model inference happens

**The `agent-skills` CLI never calls a model.** There is no LLM client, no model SDK, and no API
key for one anywhere under `scripts/`, `lib/`, or `bin/` (checked by grep for `anthropic`,
`openai`, and provider SDK imports). All reasoning runs in the host agent session (Claude Code,
Cursor, Codex, Copilot, …) through skills; the CLI is the deterministic backend those skills
call. `context.py` says so explicitly: "The first stage is deliberately **not** a model."

Consequence: fact extraction is a **skill-driven step**. The CLI prepares bounded, delimited
transcript windows and validates what the host returns; the host model reads a window and emits
structured JSON. No second inference path, no new API key.

## 3. How the Knowledge system represents a fact

- **Repository tier** (`knowledge.py`): `<repo>/.agent-skills/knowledge/`, **committed**, reviewed in
  pull requests. `project.md` holds free-text bullets under sections. `lessons/<id>.md` holds
  front matter `id, trigger, action, domain, confidence (0.3–0.9), evidence[], verified_at,
  confirmations, contradictions, status`. Provenance is the `evidence` list of locator strings.
  Status is `active / disputed / superseded / archived`; `superseded` is a manual, reviewed status
  with no link to the replacing lesson.
- **Project tier** (`project-memory.py`): `<cache>/_projects/<slug>/memory.md` and `.json`,
  gitignored. Bullets under sections; no provenance beyond a date prefix; no status; no
  supersession.
- **Org tier** (`org-memory.py`): `<cache>/_org/`, gitignored. Bullets; `promote --from` records the
  source project; no status; no supersession.

Of the fields Meeting Intelligence needs (`id, type, statement, status, scope, speakers, owner,
due, meeting_id, evidence[{segment, start, end}], confidence, source, supersedes, created_at,
review_state`), a lesson can hold `id`, `confidence` (but clamped to 0.3–0.9, which would inflate
low extractor confidences), a flat `evidence` string list, and a four-value status that does not
match `CONFIRMED / PROPOSED / OPEN / REJECTED / SUPERSEDED / UNCERTAIN`. A lesson is a
trigger→action rule, not a statement. `project.md` bullets hold none of the structure.

**Decision (D1): extend the repository tier, do not bypass it.** `knowledge.py` gains a
`meetings/` directory beside `lessons/`, one JSON file per meeting, written and read only through
`knowledge.py` functions, redacted at its one serialisation boundary like lessons are, covered by
`knowledge doctor`, and included in `knowledge read` (which `start-task` already calls with the
task brief). No separate meeting-memory database exists anywhere.

## 4. Scopes the Knowledge system supports

- **`repository`** — exists as the committed repository tier. **Supported**: it is the only
  durable, reviewable, per-repository store.
- **`project`** — partly: per-project cache memory, gitignored, keyed by a slug inside one
  workspace's cache. Not used: unreviewed, not shared, and its "project" is a cache slug, not a
  scope boundary anyone enforces.
- **`team`** — **does not exist**. Not supported; no team store is added.
- **`organization`** — partly: the `_org` cache tier, local to one machine's workspace, not
  central. Not supported: it is not organisation-wide storage, and the brief forbids inventing one.

`--scope` therefore accepts a repository (`repo:<path>` or a path). `team:` / `org:` / `project:`
are rejected with `usage-error` and a message naming the gap. A meeting joined outside any
repository with no `--scope` is **unscoped**: its facts stay `PENDING_REVIEW` in local meeting
state and reach the Knowledge system only through an explicit `inspect --accept --scope`.

Scope identity is the repository's normalised `origin` remote (via `access.project_identity`,
the same identity bindings use), falling back to the real path. A meeting file carries it; `read`
withholds any meeting file whose scope does not match the repository being read, so a copied or
committed-elsewhere file cannot leak across scopes.

## 5. Credentials under `~/.config/agent-skills`

`access.py` resolves `config_dir()` = `$AGENT_SKILLS_CONFIG_DIR`, else `$XDG_CONFIG_HOME/agent-skills`,
else `~/.config/agent-skills`. `credentials.json` (`0600`) holds profile metadata and non-secret
fields; secret fields go to the Keychain / libsecret, or a `0600` file under `secrets/` as the
declared fallback. Values resolve by precedence: process env (`AGENT_SKILLS_<SERVICE>_<FIELD>`,
then `<SERVICE>_<FIELD>`), untracked `.agent-skills.local.yml`, legacy config, then a bound or
sole-compatible identity. `resolve_access()` deliberately never returns values.

**Decision (D2):** Recall credentials are an ordinary access-resolver service, `recall`, with
fields `api_key` (secret), `verification_secret` (secret, listener mode only), and `region`
(non-secret). Users store them with the existing `agent-skills access set` (hidden input) or the
environment:

```bash
agent-skills access set --profile recall --service recall \
  --field region=eu-central-1 --secret-field api_key
```

 `resolve_access` gains an optional out-parameter so an
in-process caller can receive values without them crossing a process boundary. Values are sent
only as an HTTP header to the configured region host, never in argv, never to another host.

Non-secret meeting configuration (region default, bot name, chat notice, timeouts, retention,
transcription preference, listener URL, consent acknowledgement) lives in
`~/.config/agent-skills/meeting.json` beside the other non-secret config.

## 6. Durable state under `~/.agent-skills/state/`

`lib/asrelease/layout.py` defines `state/` as "survives every upgrade and rollback". Today only
`state/history.json` lives there. The install transaction repoints `current` and never writes
`state/` except history. `uninstall` keeps `state/` unless `--purge`.

**Decision:** meeting state is `state/meetings/<meeting-id>/`, schema-versioned
(`agent-skills.meeting/v1`). Releases before this one never read `state/meetings/`, so a rollback
ignores it by construction; this release refuses (without crashing) a record whose schema major
version it does not know.

## 7. Redaction and untrusted content

- `guard_audit.redact()` is the shared implementation; every durable tier calls it at its write
  boundary. `asrelease` has its own `redact()` for install output, unrelated to runtime content.
- `context.py` keeps a second pattern set for packs (not unified; out of scope here, noted).
- Untrusted content handling is: treat as data, mark instruction-shaped text, never change a
  bound or path because content says so, redact before storage.

**Decision:** transcripts pass `guard_audit.redact()` **plus** a meeting-local spoken-secret layer
(`scripts/meeting_secrets.py`) before they are written, and every fact passes both again at the
Knowledge boundary. The spoken layer is meeting-local on purpose: adding its rules to the shared
pattern set would move the Execution Guard's false-positive corpus, which the release checklist
treats as a regression. Instruction-shaped segments are marked with `context.looks_like_instruction`.

## 8. CLI dispatch, doctor/verify, exit codes

- `bin/agent-skills` maps a command to `scripts/<helper>` in the same release (`run_script`).
  A new `meeting` command is one `case` line; `self-test` lists required helpers.
- `doctor.sh` is a report, never a gate, and **never contacts the network**.
- `verify` checks installation integrity only.
- Exit codes (frozen at 1.0, `lib/asrelease/exits.py`): `0` ok, `2` usage, `3` authentication
  required, `4` network, `5` integrity, `6` installation failed, `7` verification failed / bad
  state, `10` update available.

**Mapping:** invalid URL / unknown id / bad flags / consent not given → `2`; missing or rejected
Recall key, region/key mismatch → `3`; Recall unreachable or 5xx → `4`; malformed provider payload
→ `5`; corrupt or future-schema meeting record → `7`. **No new exit codes.**

## 9. Dependency policy

The installer is stdlib-only Python ≥ 3.8, bash, and git. The runtime scripts are the same:
every `scripts/*.py` imports only the standard library and sibling scripts; `knowledge.py`
hand-rolls front matter to avoid PyYAML. Meeting Intelligence follows: `urllib.request` for HTTPS
(certificate verification left on), `hmac` + `hashlib` + `hmac.compare_digest` for webhook
signatures, `http.server` for the optional listener, `json` for everything. No new dependency.

## Responsibility mapping

| Responsibility | Existing owner | What Meeting Intelligence adds |
| --- | --- | --- |
| Credential storage and resolution | Access Resolver (`access.py`) | A `recall` service by convention; an in-process out-parameter for values |
| Non-secret config location | `~/.config/agent-skills` convention | `meeting.json` |
| Durable local state | `state/` (layout.py) | `state/meetings/`, schema-versioned |
| Atomic writes and locks | `durable.py` | Nothing; reused |
| Secret redaction | `guard_audit.redact()` | A spoken-secret layer for transcripts (`meeting_secrets.py`) |
| Instruction-shaped content | `context.looks_like_instruction()` | Reused to mark transcript segments |
| Bounding model input | Context Optimizer (`context.py`) | A coverage-preserving windowing primitive in `context.py` (`window_items`), reused by meetings |
| Durable facts, recall, doctor | Knowledge repository tier (`knowledge.py`) | `meetings/` facts with provenance, status, supersession, scope check on read |
| Scope isolation | Physical (tier lives in the repo) | Scope identity recorded per meeting file and checked on every read |
| Model reasoning | The host agent via skills | `meeting-intelligence` skill: reads windows, returns strict JSON |
| Routing natural language | Wamala | Routing row for meeting capture → `meeting-intelligence` |
| CLI surface and exit codes | `bin/agent-skills`, `exits.py` | `agent-skills meeting join/status/stop/list/inspect`, existing codes only |
| Environment report | `doctor.sh` | A meeting section (local checks; network probe only with an explicit flag) |
| Meeting capture transport | — (none) | `MeetingCaptureProvider` boundary, `RecallMeetingBotProvider` |
| Lifecycle / reconcile | — (none) | Monotonic state machine and idempotent reconciler |

## Known limitations / design deviations

- **D1 — facts live in a new `meetings/` directory of the repository knowledge tier**, not as
  lessons, because a lesson cannot represent a statement, its status set, or unclamped
  confidence. It is the same tier, the same write discipline, the same doctor, and the same read.
- **D2 — no team or organisation scope.** Only `repository` exists as a reviewable, enforced
  scope. Unscoped meetings stay local and `PENDING_REVIEW` until accepted into a repository.
- **D3 — windowing is a new Context Optimizer primitive, not a pack.** A pack drops irrelevant
  text by design, which would silently lose decisions. `context.window_items()` is budget-bounded
  with overlap and reports every window's size; meetings use it. It is covered by the meeting
  tests rather than the pack suite because it is a separate contract.
- **D4 — `doctor` does not probe Recall by default.** `doctor.sh` is documented as never
  contacting the network. Reachability and the live region/key check run with
  `doctor --probe-meeting`, and on every `meeting join`.
- **D5 — webhooks are hints, not state.** A verified webhook only schedules a reconcile of the
  correlated meeting; the reconciler polls the provider for truth. Duplicate, stale, and
  out-of-order events therefore cannot regress state by construction, in addition to the
  monotonic state machine. Listener mode is `agent-skills meeting status --listen <host:port>`,
  bound to loopback only; the user's own tunnel supplies the public URL.
- **D6 — extraction is a host step, driven through `inspect` flags** (`--next-window`,
  `--submit`, `--reprocess`, `--accept`, `--purge`), because the brief fixes the command surface
  at five commands. The CLI never sees model output it did not validate against a strict schema.
- **D7 — "provider-side transcription" is a join-time choice.** Recall configures one live
  transcript provider per bot. The preference list picks it at join (`meeting_captions` or
  `recallai_streaming`); the post-meeting fallback is Recall async transcription of the retained
  recording. Captions → provider transcription cannot both run on one bot.
- **D8 — a meeting that ends before any recording is `FAILED` with reason
  `ended_without_media`** (or `TIMED_OUT` when the provider reports no-one joined), so every
  terminal state is one of the named terminal states.
