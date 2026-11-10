# Changelog

All notable project changes should be recorded here.

## Unreleased

Example-guided and predictive testing lessons, kept cheap on the default path, plus fixes for
flaws found while checking the current flows. Additive against the 1.0 contract: no CLI, exit
code, install layout, provider, skill name, or skill `description` changes, and `dod-check` is
unchanged, so a `1.5.0` Definition of Done still verifies. Plan:
[docs/plans/2026-11-tdd-lessons-v1.6.0.md](docs/plans/2026-11-tdd-lessons-v1.6.0.md).

### Added

- **Literal-valued examples per data rule** (`product-owner` step 5 and the Definition of Ready):
  every calculation, threshold, mapping, eligibility, or state rule gets at least one
  `given <input>, <action> → <exact outcome>` example plus one per named boundary, nested under its
  criterion. A value nobody supplied is an open question, never an invented number.
- **Completeness counterfactual** (`software-engineer` 2.4, `references/developer-testing.md`):
  for catalogue-shaped specifications, a discriminating test per cell that can drift on its own,
  never the full cross product.
- **Opt-in test-driven mode** (`references/test-driven-mode.md`): a test list first, one behaviour
  per cycle with a one-line prediction before each run, already-passing tests recorded rather than
  forced red, refactoring under the Four Rules of Simple Design, and a bounded stop on an
  unexplained mismatch. Entered only on an explicit request, never by the execution profile or the
  agent's judgement. The evidence pack gains an optional `tdd` block; the reviewer checks its test
  list against the acceptance examples.
- **Predicted RED** at the bug-fix gate (`software-engineer` 1.5): the expected failure is
  written down first as the optional `checks.regression_red.predicted`.
- **Anchor validation**: `validate-repo.py` now fails a link whose `#fragment` names no heading or
  explicit anchor in the target Markdown file, and a bare `#` link. Tested by
  `scripts/test-validate-links.py` (in CI and release readiness), including a probe that proves
  the test fails without the check.

### Fixed

- **`RIGOROUS` promised mutation testing that no skill performed.** `software-engineer` 3.2 now
  runs the project's own tool scoped to the changed code and records `checks.mutation`, or records
  `not_run` with a reason and says so in the PR; it never installs a tool. `code-reviewer` raises
  `major` on a silent omission. `dod-check` does not require the field. A probe in
  `scripts/test-adaptive-execution.sh` keeps both skills naming it.
- Ten dead heading anchors, found by the new check, including the upgrade link on the quickstart.
- The Definition-of-Done reference's worked example was rejected by `dod-check` (`regression_red`
  recorded the test's exit code 1 on the baseline). It now verifies, and
  `scripts/test-adaptive-execution.sh` runs `dod-check` on it.
- README said "the eleven skills" next to a table of twelve; literal `\u2192` / `\u2014` escapes in
  `software-engineer` and this changelog; stale "until `v1.0.0`" pinning advice; ROADMAP "Now"
  still named `v1.1.0`.

### Changed

- **Repository visibility wording.** The repository is public on purpose. README, CONTRIBUTING,
  ROADMAP, and SECURITY say "solo-maintained, not open to outside contribution" instead of
  "private"; the release checklist's Private-Source Acceptance stage runs only while the repository
  is private and is recorded as skipped when it is public, and `test-private-source.sh`'s header
  says the same. `LICENSE` stays proprietary.

### Tests and evals

- Five evals: `product-owner-examples-per-rule`, `developer-testing-completeness-counterfactual`,
  `software-engineer-rigorous-mutation-testing`, `software-engineer-predicted-red`, and
  `software-engineer-test-driven-mode-opt-in` (with hidden acceptance checks).

### Credit

- The example-mapping, test-list, completeness, and predictive-TDD ideas were studied in the public
  lab repository `marcoemrich/agentic_coding_lab` (MIT licence). No text was copied; all wording
  here is new.

## 1.5.0 - Access Discovery: can this host do *this* operation, and via what?

A user asked Wamala to update their own Confluence page. Preflight said only that an Atlassian MCP
server was configured. The server was a company launcher script that ran read-only unless a
variable of its own was set; nothing reported that. A browser fallback hit a login page, an agent
proposed using a keychain token directly against the REST API - around the user's own read-only
setting - and the user was left trying tools by hand. This release replaces "configured" with a
seven-rung check asked before any dependent work, and turns every "no" into a precise explanation
and a short list of options the user chooses from. Nothing about any organisation is built in:
company specifics are learned on the user's machine. Additive: no host configuration changes unless
the user runs `access setup` and types yes; install layout, credential locations, existing state
and existing exit codes are unchanged. Design record: `DISCOVERY-access.md`; guide:
[docs/access/README.md](docs/access/README.md); security review:
[docs/security-review-v1.5.0.md](docs/security-review-v1.5.0.md).

### Added

- **`agent-skills access check --system S --op OP [--target T]`** walks route, launch, auth, mode,
  target, intent and policy for one operation on one target. Each rung reports
  `pass | fail | unknown | skipped`, its evidence, and whether it is `verified`, `declared` or
  `inferred`; a write resting on inferred evidence needs the user's confirmation. `--json` is
  `agent-skills.access-check/v1`. `--probe` adds non-mutating permission queries (Confluence
  `expand=operations`, Jira `mypermissions`, `gh api .../permissions.push`) using only an identity
  from `access set`, sent only to the site that identity names; `--live` starts a user-configured
  MCP server and lists its tools (never a project-scoped one).
- **`access scan`** - every route in every detected host, statically: Claude Code (user, local and
  project scope), Claude Desktop, Codex (`config.toml`, via a TOML-subset parser on Python 3.8),
  Cursor, VS Code / Copilot (JSONC), Kiro. Warns about plaintext tokens in env blocks,
  group/world-readable configs, host divergence, and stale local knowledge.
- **Launcher inspection** (`access inspect <command>`): a company wrapper is read, never run -
  its upstream, its mode switch and default (file and line), its credential locators (keychain,
  secret service, `pass`, `op`, keyring, `.netrc`, files, env), its base URLs. Launchers can also
  describe themselves: [docs/access/for-launcher-authors.md](docs/access/for-launcher-authors.md).
- **System registry** `lib/access/systems/` for Confluence, Jira, GitHub and GitLab: upstream MCP
  servers, mode and filter settings, write tools, target parsers and probes, each with the source
  and date it was checked against.
- **Local route knowledge** (`access remember`, `access forget <system>|--all`) in
  `~/.config/agent-skills/access/routes.json` (`0600`): facts the user confirmed, never secrets;
  stale when the launcher changes.
- **Write profiles** (`access setup <system> --write-profile --target <t> [--undo]`): a second
  server entry with write mode switched by the route's own rule, limited by default to the target's
  space or project (`--scope KEY`; `--all-scopes` opts out) and to the target system's toolsets;
  masked diff, interactive `yes` only, backup, atomic write; `--undo` removes only the added entry.
  Every discovery command takes `--json` (`setup --json` only proposes). `access setup <system>` prints the steps for a new route.
- **No silent route switch:** a write that one route's own setting blocks does not quietly move to
  another route; the check returns `needs-confirmation` and offers it as a choice.
- **`access classify-error`** maps a mid-task 401/403/404/"tool not found"/409 back onto a rung;
  **`access explain`**, **`access systems`**, **`access record`** (write audit in
  `~/.agent-skills/state/access/audit.jsonl`, no content, no secrets).
- **Policy** `~/.config/agent-skills/access-policy.json` may tighten (`deny`, `always_confirm`,
  `require_probe_for_write`) and cannot loosen; a loosening or unknown key fails closed.
- **Execution Guard rule `ACCESS_UNQUALIFIED_WRITE`** (ASK): an MCP write tool for a known system is
  asked about unless `access check` passed for that system, operation class and server in the last
  30 minutes; a raw HTTP write (`curl`, `wget`, `http`/`xh`, also inside `sh -c`/`eval`) to a known
  system's host is always asked about, because no check qualifies it. Fails closed.
- **Wamala** checks external access before dependent work (step 2.9), relays the check verbatim,
  and runs the resolution dialogue when it does not pass: what it tried, what it found and how
  strongly, the check's options one decision at a time, remember what the user confirms, re-check
  after they act. It never picks an option, tries an unlisted route, uses a found credential, falls
  back to a browser, or asks for a secret in chat. Contract:
  [access-resolution-dialogue.md](skills/wamala/references/access-resolution-dialogue.md); the
  handoff template carries a binding "External access" block.
- **Doctor** gains `access` rows: per detected host and known system, `ready (read-only)`,
  `ready (read-write)`, `not configured`, or `broken: <reason> -> <fix>`, with evidence strength.

### Changed

- **Exit code `11 capability-unavailable`** joins the frozen contract (`verify --explain-codes`):
  the route works and is authenticated, but its mode, scope or policy excludes this operation.
  Nothing was renumbered.
- **Redaction** covers Atlassian tokens (`ATATT`/`ATCTT`) and a JSON `"Authorization"` member in the
  runtime, and `Authorization: Basic|Bearer`, JWTs, Atlassian tokens and `*_API_TOKEN=` /
  `*_PERSONAL_TOKEN=` / `*_SECRET=` assignments in the installer.
- **One MCP detector.** `access resolve` (step 1), `tools resolve`, `tools status` and doctor's `mcp`
  row used to search config files for a substring; they now read routes from Access Discovery. The
  resolver's note names the server, host and mode, and a route for another site no longer resolves
  a request; `tools resolve` no longer counts a read-only MCP route as providing a WRITE capability;
  doctor lists servers per host, including Codex and Claude Desktop (a Codex-only machine used to
  report no MCP at all). A bare `<repo>/mcp.json` (no leading dot), which no supported host reads,
  is no longer looked at.
- **`access forget`** also accepts `<system>` or `--all` for route knowledge; `--profile NAME` is
  unchanged and cannot be combined with them.

### Tests

- `scripts/test-access-discovery.py`: 29 offline checks - the incident under invented names (acme,
  then globex with a docker upstream and a `pass` credential), host readers and the TOML subset,
  registry mode rules and filters, seven launcher shapes (never executed), presence-only credential
  checks with canaries, local knowledge and staleness, live introspection against a fake MCP
  server, `classify-error`, setup under a pseudo-terminal, policy, probes against a local fake
  Confluence, the guard rule, redaction, exit codes, rollback safety, and a no-coupling lint whose
  denylist ships only as digests.
- `scripts/eval-access-discovery.py` runs the CLI side of the ten Wamala access evals
  (`evals/wamala-access-*.md`) and records the exact output Wamala would relay.

## 1.4.0 - Meeting Intelligence: you choose how meetings are captured

Field feedback on `1.3.0`: nothing told a new user that `meeting join` needed a Recall.ai account,
key, region, and secret; Recall's per-hour cost and its processing of every participant's voice
were never disclosed; and Recall was the only way to capture. Capture is now a **user choice among
three providers**, each explained before it is used, and a failing `join` is no longer reachable
without having been told exactly what to do. Additive: an installation with Recall configured
keeps working with no action. Design record:
[DISCOVERY.md, 1.4.0 addendum](docs/meeting-intelligence/DISCOVERY.md#140-addendum-capture-as-a-user-choice);
guide: [docs/meeting-intelligence/README.md](docs/meeting-intelligence/README.md).

### Added

- **`native` provider** — downloads the transcript Teams, Google Meet, or Zoom already made. No bot,
  no extra cost, data stays in the organisation's tenant. One provider with three adapters
  (Microsoft Graph, Meet REST v2, Zoom cloud recordings); an admin registers one app per platform
  and distributes a non-secret config (`meeting setup native --import <file>`, which refuses a file
  carrying a secret); each user signs in in the browser (authorization code + PKCE, loopback
  redirect; delegated, read-only scopes; no application permissions). Every platform limitation
  is a typed refusal: `external_tenant`, `no_access` (including Teams' forwarded-occurrence 403 and
  a tenant that switched Graph transcript access off), `unsupported_meeting` (a Teams meeting
  without a calendar event), `unsupported_platform`, and `not_enabled` once the fetch window
  (24 h) closes with no transcript. `meeting fetch <url>` handles a meeting that already ended.
- **`desktop` provider** — records the meeting on the user's computer with `ffmpeg` (two channels:
  microphone and system audio) and transcribes each channel locally with `whisper.cpp`. macOS
  (BlackHole loopback) and Linux (PulseAudio/PipeWire); not Windows/WSL. Started only by the user
  in an interactive terminal after typing that everyone was told and agreed (stored on the
  meeting), with a ready-to-paste chat announcement; a supervised, visibly named recorder with a
  pidfile and a maximum duration (180 min); crash-tolerant raw PCM so a crash is processed as
  `PARTIAL`; resumable chunked transcription; raw audio deleted once the transcript is stored.
  Models are downloaded on request from huggingface.co and verified against whisper.cpp's
  published checksums.
- **`agent-skills meeting setup [native|recall|desktop] [--compare]`** — guided, re-runnable setup
  per provider ending in a self-test that captures nothing real (Recall: an authenticated read
  that creates no bot; native: a sign-in and a harmless read; desktop: 5 seconds from both
  channels, transcribed). It records the default provider and a versioned acknowledgement of the
  provider's cost, data-flow, and consent notice. Secrets, sign-in, acknowledgements, and the
  self-test recording happen only at an interactive terminal; anywhere else setup prints the
  remaining steps and stops.
- **The preflight.** With no provider chosen, `join` contacts nothing, records nothing, prints the
  three options (what happens, cost, where data goes, how participants are told), and exits `2`.
  `meeting status --providers [--json]` prints the same, so the `meeting-intelligence` skill checks
  it before any `join` and relays it.
- **`join --via native|recall|desktop`** overrides the default per meeting. Never a silent
  fallback: a refused or unready provider stops with the reason and the alternatives.
- **Disclosure in every `join`:** the provider, what will happen, the cost (Recall's rate from
  `recall.cost_per_hour_usd`, default $0.65/h), where the data goes, and that fact extraction runs
  in the user's AI assistant, so transcript text reaches its model provider.
- **`doctor`** lists each provider as `ready` / `not configured` / `broken: <reason> → <fix>` and
  the default; `--probe-meeting` also records one second from the desktop system-audio input
  (never the microphone) to prove the loopback receives audio.
- **Docs:** `docs/meeting-intelligence/README.md` (comparison, data flow per provider, costs),
  `SETUP-native-teams.md`, `SETUP-native-google-meet.md`, `SETUP-native-zoom.md`,
  `SETUP-recall.md`, `SETUP-desktop.md`, and `PRIVACY.md`; an "Optional: Meeting Intelligence"
  section in the npm README.

### Changed

- `MeetingCaptureProvider` gains `readiness()`, `resolve()`, and `activity()`, and `Capabilities`
  gains live capture, post-meeting fetch, visible participant, speaker attribution, third-party
  processing, per-hour cost, and languages — all defaulted, so a provider written against 1.3.0
  still builds. Transcripts carry `speaker_attribution` (`named | channel | none`),
  `capture_provider`, and `language`.
- Extraction respects attribution: with channel or no attribution, "You" / "Remote participants"
  are never owners (an owner named in the text still is), agreement- and owner-dependent
  confidence is capped at 0.6, windows tell the extractor so, and the result says "Speakers not
  individually identified (local capture)."
- Recall setup is guided (`meeting setup recall`), suggests `eu-central-1` for EU timezones and
  locales, and `join` refuses to start a second bot for a meeting link that already has an active
  one on this machine.
- `meeting_providers.py` is the one composition root; the boundary test now asserts that
  `meeting.py`, `meeting_intel.py`, `meeting_store.py`, and `knowledge.py` import no provider.
- The HTTPS rules (certificate verification, credential-safe redirects, bounded responses) moved
  from the Recall adapter to `meeting_http.py`, shared by every provider and token endpoint.
- `access.py` exposes `store_identity()` / `fetch_identity()`, extracted from `access set`, so OAuth
  tokens and client secrets land in the same keychain / `0600` store and `access forget` removes them.

### Fixed

- `docs/known-limitations.md` still said no team or organisation knowledge store exists; that has
  been wrong since shared knowledge sources shipped in `1.3.0`.

### Migration

- An installation with Recall configured gets `recall` as its default automatically; the new cost
  and data notice is shown once on the next `join`, without blocking. In-flight meetings continue.
- Meeting state keeps schema `agent-skills.meeting/v1` and only gains fields; `meeting.json` keeps
  `provider: "recall"`. `rollback` to `1.3.0` reads the state without crashing (tested against the
  `v1.3.0` tree); 1.3.0 leaves native and desktop meetings alone. 1.3.0 drops the new config keys
  if it rewrites `meeting.json`, so re-run `meeting setup` after rolling forward again.
- No new exit code.

## 1.3.0 - Shared knowledge: one reviewed source per organisation

An organisation can now keep one shared, reviewed, provenance-carrying knowledge source, and every
installation bound to it retrieves the same facts: architecture decisions, domain facts, meeting
decisions, ownership, cross-repository dependencies, incident learnings, and standards. The v1
backend is a git repository the organisation already hosts. Repository permissions are the access
control, a pull request is the review, **a merge is the approval**, and a local clone is the
offline cache. Agents propose and never assert, and nothing is pushed without the engineer's
confirmation. Additive: with no source configured, `knowledge read` returns exactly what `1.2.0`
returned (tested byte for byte), and no existing command, exit code, or skill changed behaviour.
The design record, written before any code, is [docs/knowledge/DISCOVERY.md](docs/knowledge/DISCOVERY.md);
the user guide is [docs/shared-knowledge.md](docs/shared-knowledge.md).

### Added

- **The Knowledge Resolver** (`scripts/knowledge_resolver.py`), now the single read/write entry
  point. Meeting Intelligence, the eval harness, and `knowledge read` / `note` / `lesson` go
  through it, and a static test fails if any other module imports a store or opens a knowledge
  file. It applies the precedence rules (shared beats a local copy; superseded is history;
  local-only is labelled `local, unshared`; conflicts are shown, never resolved silently; STALE and
  low-confidence rank lower), and re-checks both isolation layers on every shared fact it returns.
- **A backend-neutral `KnowledgeStore` interface** (`get`, `query`, `propose`, `list_proposals`,
  `sync`, `capabilities`, `health`). Two implementations: `LocalKnowledgeStore` (unshared and
  pending facts, personal categories, the local status overlay, the proposal ledger, the outbox)
  and `GitKnowledgeStore`. No git concept crosses the interface, so an `HttpKnowledgeStore` can
  follow without changing skills or the Resolver.
- **The unified fact schema** (`knowledge_model.py`, `schema_version: 1`), which extends Meeting
  Intelligence's. It adds three types (`DOMAIN_FACT`, `SYSTEM_OWNERSHIP`, `ENGINEERING_STANDARD`),
  the `STALE` status, per-fact `{level, key}` scope, typed `sources[]`, `corroborated_by[]`,
  `produced_by`, `verification`, and `last_verified_at`. `approved_by` and `proposed_by` are
  derived from git history, and are rejected when they appear in content.
- **Knowledge-source bindings in the Access Resolver** (`<config_dir>/knowledge-sources.json`).
  A repository binds to at most one source by its normalised remote. Two matching sources is an
  error `doctor` reports, and the Resolver then reads neither.
- **CLI:** `agent-skills knowledge status | sources [add|remove|bind] | sync | propose | inspect |
  check | init-source`, plus `record` and `verify` (both recorded as deviations D4 and D6).
  `sources add` with no URL discovers a source from a committed pointer file
  (`.agent-skills/knowledge.json`), then from the well-known `engineering-knowledge` name.
- **The propose flow:** redaction and a content scan, then the exact files shown, then
  confirmation. The branch is `agent-skills/proposals/<installation>/<timestamp>` (never the
  default branch, never `--force`). A PR/MR opens through `gh` or `glab` when available, otherwise
  a compare URL is printed. Without write access the proposal goes to a fork PR, or to an outbox
  patch. It is never retried with another credential. Supersession edits the old and new fact in
  one commit. Near-duplicates become corroboration. `--from-source` merges a duplicate source
  with its provenance.
- **The proposal lifecycle** (`open | merged | closed_unmerged`), derived on sync. A rejected fact
  is marked `REJECTED (shared review)` and not suggested again until its content changes.
- **Sync, cache, and index.** Sync is a fast-forward to the default branch at most once per
  interval (15 minutes by default) when a read needs it, with a short timeout, falling back to
  the cache and stating its age. A derived SQLite index is rebuilt from the clone (with a scan
  fallback when `sqlite3` is missing). Sync reports facts that became SUPERSEDED or STALE. An
  upstream history rewrite purges the removed objects from the local cache.
- **Code-reference verification:** a missing path or a changed snippet hash at `HEAD` marks the fact
  STALE in the local view. `propose --mark-stale` / `--reverify` share the result, as proposals.
- **`agent-skills knowledge check [<dir>]`** for the source's CI, with no network. It checks the
  schema, secrets, transcript text, code snippets, personal data under the manifest's
  `person_names` policy, instruction-shaped text, supersession links, allowed scopes, file
  placement, duplicate ids, and near-duplicates.
- **`agent-skills knowledge init-source <dir> --org <org>`**: manifest (UUID `source_id`, org,
  status, successor, allowed scopes, policy), CODEOWNERS, README, a CI template, and the scope
  directories. It refuses when a manifest exists, or an active source for the org is
  discoverable, unless `--force --reason`.
- **First-run migration**, classifying existing local facts as `personal` or
  `shareable-candidate` without rewriting a committed file. Nothing is ever uploaded
  automatically.
- **`doctor` knowledge section**: git, bindings, cross-org sources, schema compatibility, sync age,
  index health, and setup gaps. Local by default; `--probe-knowledge` contacts each source with
  the user's own git access.
- **Docs:** [shared knowledge](docs/shared-knowledge.md), [setup and roles](docs/knowledge/SETUP.md),
  and [the history-removal runbook](docs/knowledge/HISTORY-REMOVAL.md).
- **`meeting-intelligence` skill:** it may *suggest* sharing accepted decisions, and runs
  `propose` only after the user agrees.

### Safety

- Credentials, machine bindings, private preferences, and task context can never be proposed.
  This is enforced by category in the Resolver and again in the store, whatever the flags.
- A shared fact is shown as CONFIRMED only when git shows a review: a merge commit, a host merge
  with its PR number, or a different committer. A CONFIRMED claim pushed directly is shown as
  PROPOSED.
- Pointer files are untrusted. A cross-org pointer needs the org name typed back, and a pointer
  never overrides a binding.
- Shared facts are untrusted data. Instruction-shaped text is marked, and changes no binding,
  target, or command.
- Found and fixed during the security review ([docs/security-review-v1.3.0.md](docs/security-review-v1.3.0.md)):
  a pointer file whose URL was `--upload-pack=<program>` made `sources add` execute that program
  through `git ls-remote`, before any confirmation (never published); a symlinked fact file could have been read from outside the clone; and after an
  upstream history rewrite, the clone's own local branch kept the removed objects reachable; and a
  fact recorded locally in one repository was readable from every other repository on the machine.
- Speaker names never leave the machine. Action owners are shared only under the default
  `action_owners_only` policy, and a source can set `none`.

### Changed

- `knowledge read` renders through the Resolver. Output is identical unless the repository is
  bound or has locally recorded facts.
- `meeting.py` reads committed meeting files through the Resolver (`read_meeting_file`) instead of
  opening them by path.
- `test-knowledge.sh` mutation probes now copy every runtime script into their sandbox, because
  `knowledge.py` reaches the Resolver.

### Tests and evals

- `scripts/test-shared-knowledge.py`: 36 cases, offline. Remotes are local bare repositories
  behind git's `insteadOf`, and the PR adapter is a fake `gh`
  (`scripts/fixtures/knowledge/fake-gh.sh`). It covers brief items 1-17 and 20-27, lost access,
  history removal, local isolation of recorded facts, option-shaped URLs, symlinked fact files,
  and exit codes, with five mutation
  probes: binding isolation, the personal-category rule, the unreviewed downgrade, the content
  scan, and symlink skipping.
- `scripts/eval-shared-knowledge.py` (brief evals 18-19): three installations, one source. 3/3 get
  the same CONFIRMED shared answer after approval; before approval only the proposer sees it,
  labelled `local, unshared`; a superseded decision is presented as current in 0 of 18 queries.
  These measure what each agent is *given*, not how a model phrases its answer.

### Known limitations

- Scale: thousands to low tens of thousands of facts per source. Latency: sync interval plus review
  time; not real-time.
- Deleting merged data needs a history rewrite on the source (see the runbook); git keeps what it
  merged.
- The `glab` adapter creates and reads merge requests, but cannot fork, and is exercised only by
  reasoning, not by a fake. Azure DevOps and Bitbucket get compare URLs only.
- `normalise_remote` keeps `.git` when a remote ends in `.git/`, so that rare form is a different
  repository identity. Unchanged from `1.2.0`, because credential bindings and meeting scopes
  already depend on it.

## 1.2.0 - Meeting Intelligence: "Listen to this meeting"

Tell your assistant "Listen to this meeting: <Teams, Zoom, or Google Meet link>". A visible, named
assistant joins after a one-time recording notice; polling alone carries the meeting to a
redacted, speaker-attributed transcript with no public URL; the host agent extracts engineering
facts one bounded window at a time; the CLI validates every fact against the transcript; and the
meeting's facts land in the repository knowledge base in one write, labelled as meeting evidence
for later work in the same repository. Additive: no existing command, exit code, or skill
changed behaviour. The design record, written before any code, is
[docs/meeting-intelligence/DISCOVERY.md](docs/meeting-intelligence/DISCOVERY.md); the user guide
is [docs/meeting-intelligence.md](docs/meeting-intelligence.md).

### Added

- **`agent-skills meeting join | status | stop | list | inspect`.** `join` validates the link
  locally (unknown shapes create nothing), binds a repository scope, creates the bot, and returns.
  `status`, `list`, and `inspect` reconcile idempotently: poll, advance a monotonic lifecycle,
  retrieve and redact the transcript, and prepare extraction windows. `inspect` carries the host
  steps (`--next-window`, `--submit`) and the review and retention actions (`--reprocess`,
  `--accept`, `--purge`). `status --listen` is an optional loopback webhook listener that only
  schedules reconciles.
- **A provider boundary.** `MeetingCaptureProvider` speaks Agent Skills types only;
  `RecallMeetingBotProvider` (`scripts/meeting_recall.py`) is the one module that knows Recall. It
  sets the bot's visible name, a join chat notice, `automatic_leave` timeouts, media retention
  (48 h by default — Recall's own default keeps media indefinitely), and correlation metadata on
  every bot. Region is required configuration and must match the key.
- **Transcription fallback.** Platform captions or provider transcription at join; post-meeting
  transcription of the retained recording when the live transcript is empty or clearly partial;
  the method used is recorded. All formats (and WebVTT, for future native providers) normalise
  to one segment model with deterministic ids.
- **The `meeting-intelligence` skill**, routed from Wamala as the new `meeting-capture` class
  (routing row 25). It shows the recording notice verbatim and joins only on the user's explicit
  request.
- **Meeting facts in the repository knowledge base** (`.agent-skills/knowledge/meetings/`): ten
  fact types, six statuses, evidence timestamps, supersession with explicit evidence, review
  state. `knowledge read` (and so every `start-task`) surfaces relevant facts in their own
  section, labelled as claims; `knowledge facts [--all]` lists them with history; `knowledge
  doctor` validates and scans them.
- **`window_items` in Context Optimizer**: a coverage-preserving, budget-bounded windowing
  primitive with overlap, for inputs that must be read completely but cannot be read at once.
- **`doctor` Meetings section**: credentials, region consistency, consent, listener mode, stuck
  meetings. `doctor --probe-meeting` contacts the provider once; without it doctor stays offline.
- **`resolve_access(values_out=…)`** so an in-process caller can send a credential as a header
  without it crossing a process boundary. The CLI never uses it and `Resolution` still holds no
  value.

### Safety

- Transcripts are redacted before they are stored: the shared redactor plus a spoken-secret
  layer (cue + value, spelled-out values, values announced in one utterance and said in the next,
  tokens the transcriber split). Facts are redacted again before checkpointing and at the
  knowledge write.
- Extraction output is untrusted: a closed schema (rejected, never repaired, three attempts per
  window), then mechanical checks — evidence must exist in the window and mention the statement,
  `CONFIRMED` needs explicit agreement in the evidence, owners and dates must be in the evidence,
  facts resting only on instruction-shaped speech are dropped, supersession needs an explicit
  replacement.
- Scope isolation is enforced on read: a meeting file records its repository identity and is
  withheld anywhere else. No team or organisation scope exists, and none was added.
- Webhooks are verified (Svix HMAC, constant-time) before parsing, replay-windowed, and deduped,
  and only ever schedule a reconcile.
- The Recall key goes only to the region host as a header; a cross-host redirect drops it, and an
  https→http redirect is refused.
- The instruction-shaped-text pattern shared by Context Optimizer, `knowledge doctor`, and
  `guard scan-content` now also catches "ignore **your** previous instructions" and "ignore your
  instructions". Found by the new prompt-injection eval; guard false-positive corpus unchanged.

### Fixed

- **`knowledge read` overran small budgets.** Just above the minimum (about 300-400 characters),
  once every entry had been trimmed the withheld notice alone could still exceed the budget — 307
  rendered 371 in `1.1.0`. When nothing is left to trim, the notice now shortens to one line. It
  never shortens while an entry is still shown, so the budget-accounting mutation probe still
  sees its overrun. `test-knowledge.sh` sweeps every budget from 250 to 1199, with and without
  meeting facts.

### Tests and evals

- `scripts/test-meeting.py`: 22 offline checks — polling-only lifecycle, crash recovery at every
  checkpoint, webhook signature, replay, dedupe, and ordering, fallback, the import boundary,
  failure isolation, deterministic dedupe, spoken secrets, scope isolation, retention, state
  location and unknown schemas, exit codes, Recall mapping from fixtures, bounded windows, and four
  mutation probes. In CI and in `test-release-readiness.sh`.
- `scripts/test-cli-install.sh` asserts meeting state survives `update` and `rollback`;
  `test-release-readiness.sh` rolls back to the previous tag and runs its `verify` and `doctor`
  against meeting state.
- `scripts/eval-meeting-intelligence.py` and a six-transcript golden set score brief evals 15-22,
  for the host's raw output and after the CLI's checks, plus an adversarial run. Results in
  [eval-runs/v1.2.0/summary.md](eval-runs/v1.2.0/summary.md).

### Known limitations

- The Recall adapter is built against Recall's published reference and fixtures derived from it,
  not a live account; an opt-in live smoke test exists (`AGENT_SKILLS_MEETING_LIVE_SMOKE=1`).
- Live, in-meeting streaming is out of scope; processing is post-meeting.
- Spoken-secret detection is heuristic and errs toward redaction.

## 1.1.0 - Field report: Wamala finishes the run it starts

An agent used Wamala for a long, real delivery run: fourteen phases, design-system work, on a
host where sub-agents could not open sub-agents. It filed a report listing everything that had
cost it time, ordered by cost. Every item was reproduced against `1.0.0` before it was fixed.
Where the runtime can hold a fix, a test holds it, with a mutation probe showing that test fails
when the fix is removed. Where only an instruction can hold one, the instruction now exists at
every site that needed it. Nothing in [the 1.0 contract](docs/one-point-oh.md) was renamed,
renumbered, or removed.

### Wamala: routing a run that the host cannot nest

- **Wamala routed plans to a runner that could not run.** Its chain table and its stopping
  condition both sent an existing plan to `delivery-runner`. The runner's whole mechanism is
  nested dispatch, so dispatched as a step it stopped before `phase-01`, correctly. Wamala now
  records `nested_dispatch` in a new step 2.6, from evidence, and treats `unknown` as
  unavailable. When nesting is unavailable, it walks the plan in **plan mode**: one phase per
  dispatch, following the runner's run-loop checklist and handoff template as written, under the
  runner's cap. `delivery-runner` checks at step 0 that it can dispatch, and stops with
  `BLOCKED: nested dispatch unavailable` before touching the plan.
- **"The plan itself is wrong" had no route.** A phase blocked because its own acceptance
  criterion contradicted a measurement could only stop or go to the user. When the blocked
  artifact names the criterion, the evidence, and the conflict, it now goes to
  `delivery-planner` as a `plan-amendment`, once per phase. A second contradiction goes to the
  user. `delivery-runner` stops with a new `plan-defect` reason so its caller can route it.
  `delivery-planner`'s "when the plan goes stale" now covers unsatisfiable criteria and
  decision-gate answers.
- **Independent review was unachievable, and nothing noticed.** On a host that cannot nest, an
  executor's `code-reviewer` runs in the context that wrote the change. `code-reviewer` now
  records `review.independence` (`fresh-context` or `same-context`, absent reads as
  `same-context`). When a step required independent review and did not get it, Wamala or the
  runner dispatches `code-reviewer` as a sibling step over the committed diff. That happens
  after every `RIGOROUS` step, and at `STANDARD` every three steps or before anything is pushed.
  The run report states, per step, which review satisfied the requirement.
- **Brief boilerplate was most of the work.** A new step 2.7 writes a **run preamble** once, to
  `<cache>/<work-key>/artifacts/run-preamble.md`. It holds identity, explicit lifecycle commands,
  branch and push rules, the output location, measurement recipes, known traps, and owner paths.
  Every brief points at it. Template:
  [`run-preamble-template.md`](skills/wamala/references/run-preamble-template.md).
- **Continuity between phases depended on memory.** `plan-next` now returns
  `phase.prerequisite_context`: each prerequisite's `completion_summary`, `follow_up_context`,
  and `artifacts`, read from the evidence pack and redacted. Prerequisites that recorded
  nothing are listed under `missing`. Wamala's and the runner's briefs paste it verbatim under
  **Carried forward**.
- **Delete-shaped verbs had no reversibility check.** New `agent-skills reversibility <path>...`
  is read-only. `RECOVERABLE` (exit `0`) means every file is tracked and committed.
  `NOT_RECOVERABLE` (exit `1`) covers content outside git, untracked, ignored, or uncommitted, and
  a target holding its own `.git`. That result comes with shell-quoted archive commands and the
  user's delete command. Wamala's new step 2.8 runs it for every delete-shaped request, turns
  the delete into an archive, and hands the delete to the user. The policy is in
  [destructive-action safety](docs/destructive-action-safety.md#delete-shaped-requests-check-reversibility-first).
- **Classifier gaps.** Two new classes. `design-review` covers an existing page or flow with no
  diff: it goes to `manual-tester` against a stated standard, or to `product-owner` without one,
  read-only either way. `plan-amendment` goes to `delivery-planner`. A **known gaps** list in
  the routing table records what no canonical skill owns, such as authoring a visual design, so
  the next dispatcher does not re-derive it or route to a skill that edits what it reviews.
- **"Verify from artifacts" was under-specified outside engineering.** New
  [verification bars](skills/wamala/references/verification-bars.md) give a checkable definition
  of done for each class: investigation, refinement, question, design review, diff review, manual
  validation, automation, planning, plan amendment, terminology, and context packs. A step that
  misses its bar is retried once, like a missing artifact.

### Fixes — lifecycle wrappers (`scripts/finish-task.sh`, `scripts/start-task.sh`, `scripts/project-memory.py`)

- **The ambiguity error named a flag that did not exist.** `finish-task` refused with
  "`--issue-key` is required here", and accepted the key only as a positional argument. It now
  takes `--project`, `--issue-key`, and `--task`, the same forms as `start-task`, and the error
  shows the working command.
- **A `complete` closeout deleted the step's own output.** Cleanup now always keeps `artifacts/`.
  Around a phased plan it also keeps `evidence-pack.yml`, which carries `follow_up_context`, and
  it names what it kept. Inside a coordinated run, where the blackboard records `wamala` or
  `delivery-runner`, any other skill's closeout leaves scratch for the coordinator to verify and
  clean. `--cleanup` still forces it.
- **"15 tasks are in flight."** A task counts as in flight only while its `blackboard.json`
  exists. Directories that hold only what cleanup kept on purpose no longer block an implicit
  closeout.
- **One task got several keys and two projects.** The wrappers resolved the cache at the git
  root while most Python helpers used the working directory, and outside git the wrappers used
  the working directory too. Every helper now shares one resolver (`scripts/cache_root.py`,
  mirrored in `task-context.sh`). Outside git it uses the nearest parent below `$HOME` that
  already holds `.agent-skills.yml` or a cache. `start-task` says when it generated a fresh key
  while other tasks are in flight, lists them, and says when the project name came only from a
  directory name.
- **The capability report said "NO repo knowledge" in a repository with a 650-fact knowledge
  base.** The probe only knew `.agent-skills/knowledge`. It now also reports a project's own
  knowledge base (`knowledge/`, `docs/knowledge/`, `kb/`, and similar). The text shows this as
  `?` with the path and file count, and says the knowledge base is read directly.
  `doctor --json` keeps `repo_knowledge` as `yes` or `no` and adds `repo_knowledge_other`.

### Tests

- `scripts/test-lifecycle-fs.sh` gained 28 checks: artifact and evidence-pack preservation,
  `finish-task` flags, the in-flight count, coordinated-run deferral (including a note that
  merely mentions a coordinator), one cache across the shell and Python resolvers inside and
  outside git, and reversibility. It also gained three mutation probes: remove the keep rule,
  the coordinated-run check, or the untracked-content check, and the matching test fails.
- `scripts/test-adaptive-execution.sh` gained six `prerequisite_context` checks, including a nested
  mapping that must not overwrite a phase's keys and a credential-shaped value that must not
  reach the decision. It also gained a probe that removes the redaction and watches the value leak.
- `scripts/test-front-door-skill.sh` pins the new guarantees and the order of the three plan
  rows: amendment, then plan mode, then the runner.
- Probe sandboxes in three suites now copy `cache_root.py`. Without it the weakened builds died
  on import and the probes failed. That failure is what showed the copies were needed.
- New eval: [`wamala-plan-mode-and-plan-defects.md`](evals/wamala-plan-mode-and-plan-defects.md).

### Security review

[`docs/security-review-v1.1.0.md`](docs/security-review-v1.1.0.md). Writing it surfaced two issues,
both fixed before release. First, a non-git cache anchor planted in a shared directory such as
`/tmp` could redirect another user's task memory, so anchors must now belong to the current user.
Second, carried-forward context is pasted into the next brief verbatim, so both handoff templates
now label it as recorded claims to verify, never as instructions.

### Also in this release — documentation, no behaviour change

- **Commercial subscription and distribution plan** ([`docs/commercial-roadmap.md`](docs/commercial-roadmap.md)).
  A final, decided plan for selling Agent Skills as one subscription at €11 per named developer
  per month, with individual and company seat purchasing, an account portal, and private release
  distribution that needs no customer GitHub access. Nothing in it is left open: Stripe with
  Managed Payments as merchant of record, licensing enforced at the distribution boundary only,
  a browser-approved CLI token instead of an OAuth device flow, one Cloudflare Worker over Neon
  PostgreSQL and private R2, and a fourteen-phase build order through controlled beta to launch.
  No implementation yet; the commercial line ships as `2.0` and every `1.x` contract is untouched.
  `ROADMAP.md` and `docs/README.md` point at it.

## 1.0.0 - Stable: the runtime records what it can verify, and says so when it cannot

The first stable release. Everything in [the 1.0 contract](docs/one-point-oh.md) is frozen for
the `1.x` line. Four release candidates and three independent reviews preceded it. The last of
those — a pre-1.0 architecture review that probed the memory tiers, the dispatcher, and the
lifecycle with inputs no suite had sent — is what this release answers. Its finding, in one
sentence: the weakest boundary was the transition from an agent's claim to trusted completion or
durable knowledge. Every finding below was reproduced against `1.0.0-rc.4` before it was fixed,
and every fix ships with a case that fails without it.

### Fixes — memory integrity (`scripts/knowledge.py`, `scripts/durable.py`)

- **Lesson evidence bypassed redaction.** `trigger` and `action` were redacted; `evidence` was
  merged and stored verbatim, and a token-shaped locator reached the committed lesson file.
  Every field a lesson holds — evidence, provenance, the body — now passes through one boundary
  in `Lesson.write`, and every input is cleaned before it is compared. The secret-boundary suite
  carries the evidence case through `add`, `confirm`, and `contradict`, plus a probe that
  removes the redactor and asserts the leak returns.
- **"Independent confirmation" was repeated submission.** Five `lesson add` calls citing the same
  task took a lesson from 0.5 to 0.9 with one piece of evidence; a re-add with a *different*
  action kept the old action and reinforced it anyway. Evidence is now an observation identity:
  the same locator twice is one observation and changes nothing; a re-add whose trigger or
  action differs is a conflict, writes nothing, and says so; `confirm` requires `--evidence`
  and is idempotent on a locator already recorded. `lesson add` requires `--evidence` — a lesson
  with nothing behind it was an assertion — and `doctor` now reports an active lesson with no
  evidence as an error rather than a warning, so a knowledge base carrying one fails its CI check
  until the lesson is given a locator or archived.
- **A contradiction refreshed the lesson and left it in recall.** `contradict` set `verified_at`
  to today and the lesson stayed recallable at full weight. It now records
  `last_contradicted_at`, leaves `verified_at` alone, and marks the lesson `disputed` once
  contradictions reach confirmations: kept, listed, reported by `doctor`, withheld from `read`.
  A further distinct confirmation reactivates it; `superseded` and `archived` are set by hand in
  a reviewed change. A lesson written before this release parses unchanged as `active`.
- **Decay took a step on every run.** Three `decay --apply` runs on one afternoon took a lesson
  from 0.8 to 0.5. It now records `last_decay_at` and decays once per 90-day window.
- **Recall preferred the oldest verification among equals.** The ISO date sorted ascending in a
  key whose other terms were negated. Now relevance, then confidence, then most recent first.
- **The budget counted the payload but not the frame.** A 4,000-character read rendered 4,258.
  The budget is now the length of the rendered text — header, separators, withheld notices,
  trust line — and a budget too small to hold the frame renders one line saying so rather than
  overrunning. `start-task` reads all three memory tiers within one startup budget
  (`AGENT_SKILLS_STARTUP_BUDGET_CHARS`, default 16,000); `memory read` and `org-memory read`
  gained `--budget-chars` and say what they left out and where to read it. Every skill's
  preflight now passes `--brief`, so the repo tier is ranked for the task rather than by
  confidence alone.
- **Lesson updates ran outside their lock.** Atomic replacement prevented a torn file; nothing
  prevented two confirmations reading the same count and one overwriting the other. The whole
  read-modify-write for `add`, `confirm`, `contradict`, `decay --apply`, and `note` now holds the
  file's lock. Pinned deterministically: a helper holds the lock, a confirm waits, and lands
  when it is released.
- **`durable.locked` ran the body unlocked after a timeout and masked body errors.** A lock
  that could not be taken in twenty seconds yielded `False` and the caller — none of which
  inspected it — proceeded to exactly the lost update the lock exists to prevent. And the
  `except OSError` wrapped the `yield`, so an error inside the body re-entered the generator and
  surfaced as `RuntimeError: generator didn't stop after throw()`. Contention past the timeout
  now raises `LockTimeout` before the body runs (the CLIs print "nothing was written, retry" and
  exit 1; `AGENT_SKILLS_LOCK_TIMEOUT_SECONDS` tunes it); a filesystem that cannot lock at all is
  reported once and proceeds; body errors propagate intact. `update_json` distinguishes a
  missing store from a corrupt one: the corrupt file is moved to `<name>.corrupt-<timestamp>` and
  reported, then the tier continues from the default — the evidence is kept, not overwritten.

### Fixes — completion and dispatch

- **Completion was an unverified claim.** `finish-task --status complete` with nothing but a
  summary was recorded as `completed`, indistinguishable from a change with a verified definition
  of done. A closeout still records what happened — it must stay usable for reviews, planning,
  blocked work, and recovery — but for `complete` / `pr-opened` it now reports whether a
  `definition-of-done.json` exists for the task and whether the new `agent-skills dod-check`
  accepts it, prints `NOT verified` when it does not, and carries `evidence` and
  `verified_delivery` into telemetry. Reported, not enforced there.
- **The definition of done's "every `false` needs a waiver" rule was wrong.** The schema
  intentionally contained `shared_library_changed: false` and `safety_acknowledgement.applies:
  false` — classifications and safe states — so the rule invited pointless waivers and
  normalised waiving. The artifact is now three kinds of field: **checks** (`pass` · `fail` ·
  `not_run` · `not_applicable`, a pass carrying the command, working directory, revision, exit
  code, and evidence locator that produced it), **classifications** (facts, never waived), and
  the safety acknowledgement. `dod-check` refuses a pass without an execution record, a pass
  recorded on a revision other than `head_sha`, a `fail` or `not_run` without a waiver from a
  named authority — `agent` is not one — a waiver naming a classification, and the pre-1.0
  boolean shape.
- **The prescribed RED check could run a revision where the test did not exist.** The
  engineer wrote the failing test as the first commit and the reviewer was told to check out
  that commit's *parent* and expect failure — a revision with no test, where "test not found" or
  zero collected tests read as RED. RED is now demonstrated against the unfixed implementation
  **with the test present** (the test-only commit, or an isolated baseline with the test
  transplanted), and must record the behavioural assertion that failed. Corrected at every place
  the old instruction appeared: `software-engineer` 1.5, 2.4, and 2.5; `code-reviewer`'s handoff
  contract and its failure-dismissal rule; the developer-testing reference; the definition of
  done.
- **Overlapping mutation targets were "provably independent".** `plan-next` compared targets
  by string-set intersection, so `src/api` beside `src/api/handler.ts` — and `./src/api` beside
  `src/api` — formed a parallel group. Targets are now normalised; a path overlaps by
  containment, a named resource (`db:orders`) by identity; an absolute or repository-escaping
  target disqualifies its phase rather than being compared as text. Genuinely disjoint siblings
  still group. The mutation probe now removes the containment check.
- **The stop hook recorded a false "unfinished" after every normal finish.** Every hook template
  called `finish-task --status needs-context` unconditionally on `Stop`, which fires at the end
  of every turn. `finish-task --if-open` closes out only the task the last `start-task` recorded
  and `finish-task` has not yet closed; otherwise it prints one line and writes nothing. A
  fallback that does run is attributed `closeout=fallback` in telemetry.
- **Promotion counts were typed, not derived.** `outcome record --promote-to-org --confirmed-in
  2` promoted on the number alone. `--confirmed-in` now takes project names, each of which must
  have a project memory on disk under the cache root, and the org-memory bullet names them all
  as provenance. The integer form exits `2` with a message naming the new one.
- **The dispatcher loaded the specialist it meant to isolate.** Wamala's step 4 read the whole
  owner `SKILL.md` to confirm its `name:` field, then the fresh agent read it again. The
  dispatcher now reads only the frontmatter; the owner-skill verification recipe says the same.
  Wamala's "Done" now requires the artifact's own status to say so — a readiness decision, an
  executed test plan, a `dod-check`-verified definition of done — not merely that a file exists.
- **Symbol spans in a context pack are marked as what they are.** Spans are inferred from
  indentation and capped at 400 lines; the pack now includes decorators directly above a
  declaration, flags a capped fragment `[span-capped]`, and carries a note saying spans are
  inferred and the exact target should be expanded before editing.

### Fixes — instructions that contradicted their own detailed rules

- `docs/lifecycle-preflight.md` called every gotcha "a verified constraint" and every build
  command "authoritative", then said they were claims to verify. It now says one thing:
  recorded, revision-scoped evidence, a place to start and never authority.
- `docs/review-loops.md` said the artifact "ships with any remaining issues recorded as
  follow-ups" while the engineer rules forbade shipping a surviving `major`. A bound now ends
  autonomous iteration, not the obligation to resolve a blocking finding; only explicitly
  non-blocking items ship as follow-ups, and the automation entry names its severity boundary.
- One shared reference, [`docs/evidence-discipline.md`](docs/evidence-discipline.md), now holds
  the rules each entry point used to carry in slightly different words: completion versus
  verified delivery, what RED proves, a shortcut/required-response table, recorded knowledge as
  evidence rather than authority, scope, and the conditional UI and documentation contracts. The
  `software-engineer` self-review gained two conditional checks — `docs_contract` and
  `ui_visual` — recorded in the definition of done as `pass` or `not_applicable` with a reason.

### Added

- `scripts/dod-check.py` and `agent-skills dod-check`: `0` verified, `1` not verified with one
  reason per line, `2` unreadable or not the schema.
- `scripts/test-knowledge.sh`, the tenth suite, in CI and in release readiness: 53 checks over
  observation integrity, contradiction and decay, recency, budget accounting, lock
  serialisation and timeout, `durable` error handling, `dod-check`, the closeout signal and the
  idempotent fallback, promotion provenance, and three mutation probes.
- Five new concurrency cases in `test-adaptive-execution.sh`; the evidence-field case and a
  redactor-removal probe in `test-secret-boundary.sh`.

### Not changed, and why

- **No mandatory interrogation.** The requirement gate already blocks on a load-bearing unknown
  and asks only when the answer changes behaviour, authorization, scope, or an irreversible
  decision. Adding a grilling step to every task would cost more than it catches.
- **No universal RED–GREEN–REFACTOR.** A review, a refinement, or a context pack has different
  evidence obligations. The RED rule applies to bug fixes.
- **No vector store.** Keyword and source-based recall is right for code identifiers and a small
  committed knowledge base. Budgets, evidence identity, and invalidation had to be fixed first;
  retrieval misses have not been measured.
- **No behavioural eval run.** `run-evals.py` still validates scenarios, not a model's actions,
  and [known limitations](docs/known-limitations.md#memory-and-evidence) says so. A
  release-level behavioural suite is the first `1.x` roadmap item.

Nothing in the 1.0 contract was renamed, renumbered, or retyped. Two inputs were tightened
before the freeze took effect — `lesson add` / `lesson confirm` require `--evidence`, and
`--confirmed-in` takes names — and both are recorded in [the contract](docs/one-point-oh.md).

## 1.0.0-rc.4 - Release candidate: the gates now cover the gaps two reviews found

Two independent pre-1.0 reviews ran every documented gate — all of which passed — and then found
seven defects the gates could not see. That is the finding behind this candidate: the suites were
green because their corpora did not contain the shapes that break. Every fix below ships with a
regression case, and where a guarantee had no test that fails when the guarantee is removed, a
mutation probe was added. Nothing was renamed, renumbered, or retyped.

### Fixes — release engine

- **A `VERSION` file could delete an arbitrary directory.** Nothing validated that a version was
  a version. The value from `providers/local.py` became a path in `Layout.version_path` and
  `cache/staging/<version>`, and the first thing `InstallTransaction.run` does with the staging
  path is `shutil.rmtree` it — before the release is verified. A source whose `VERSION` read
  `../../victim` deleted `victim`, then reported "staged release failed its self-test; nothing was
  activated", which was untrue by then. Fixed in two independent places, because one check being
  bypassed is unrecoverable: `release.require_version` refuses non-semver at every boundary a
  version arrives from (`--version`, a git tag, a `VERSION` file), and `Layout.safe_component`
  independently refuses anything that is not one safe path component.
- **A malformed `--version` installed a real but different release.** `providers/git.py` matched
  tags with `compare_versions(found, wanted) == 0`, and `compare_versions` deliberately reports an
  unparseable operand as *equal* so that a machine on an unreadable version reads as "nothing to
  do". Used for identity, that made every typo match the first tag: `--version
  definitely-not-a-version` resolved `0.43.0`. `resolve_version` now validates first and compares
  with the new `versions_equal`, which never treats unknown as a match. An invalid `--version` is
  exit `2`.
- **Automatic rollback reported success over a machine it had not fully restored.** An install
  changes four things — the activation pointer, host registrations, `install.json`, and, when the
  new release replaces a same-named one, the release directory itself. Rollback restored the first
  two. So a failed update left `current` at `1.0.0` and `install.json` at `1.1.0`, and a failed
  *repair* of the active version re-activated the new broken tree under the old name while
  printing "rolled back to 1.0.0". The displaced directory and the entry manifest are now
  transaction state, restored on every post-staging failure, and the restored machine is verified
  before the word "rolled back" is used. When it cannot be, the message says the machine is mixed
  and names `doctor`.
- **`verify` broke its own frozen exit code, and did not verify.** Drift between the manifest,
  `current`, and the payload's `VERSION` returned `1` — the shell's default — while
  [the 1.0 contract](docs/one-point-oh.md) freezes verification failure as `7` and says `1` never
  appears. Separately, `verify` only checked that `release.json` *existed*, so "Installation
  verified" was printed over a tree whose files had been edited; the payload hash was recomputed
  at stage and rollback only. `verify` now re-hashes the active release against its own manifest,
  and returns `7`. A missing `python3` or release engine is reported as "could not re-check",
  not as tampering.
- **No locking anywhere in the installer.** Two concurrent updates shared `cache/staging/<v>` and
  `versions/<v>.incoming`, and the moment one moved the running release aside was a moment the
  other could activate into the gap: "atomic, no mixed state" held for one process only.
  `install`, `update`, and `rollback` now hold one advisory lock per install root. It is advisory
  so a killed installer leaves nothing wedged.
- **A local source could copy files from outside itself into a release.** `copy_payload` checked
  for escaping symlinks on files it walked past, but resolved each top-level payload entry with
  `isdir` first — so a checkout containing `skills -> ~/.ssh` had those files copied into the
  installed release. Every entry is now checked before it is read, and a directory symlink
  escaping the checkout is an error rather than silently dropped from the payload.

### Fixes — Execution Guard

The guard is the product's core promise, and its suite passed because the corpus did not contain
these shapes. All of them are now permanent `REDTEAM` cases.

- **Wrapper option values hid the command.** The wrapper-stripping loop skipped option flags but
  not the values they consume, so the value became the inspected command — `sudo -u root rm -rf /`
  was read as a command called `root` — and a command no rule has heard of matches nothing and
  reads as ALLOW. Affected `sudo`, `doas`, `nice`, `ionice`, `env`, `stdbuf`, `time`, `watch`,
  `script`, and `exec`. Each now carries its value-taking flags. Because an option table can never
  be complete, an *unrecognised* option followed by a bare word is now read both ways and both
  readings are inspected: an unknown wrapper flag costs a redundant check, not a bypass.
- **`find -exec` lost its argv boundaries.** The extracted body was re-joined with plain spaces,
  so `find . -exec sh -c 'rm -rf /' \;` re-parsed as `sh -c rm` with `-rf` as `$0` and the payload
  gone. `-exec` runs an argv without a shell, so the words are now re-quoted.
- **Inline programs could shell out unseen.** The destructive-pattern list named native deletion
  calls (`rmtree`, `unlinkSync`) and could never enumerate every route to a shell, so
  `python3 -c 'import os; os.system("rm -rf /")'` was allowed. The command string is now extracted
  from the shell-out call — including the `subprocess.run(["rm","-rf","/"])` list form — and judged
  by the rules that already know what `rm -rf /` is, with the right path classification and the
  right message.
- **A credential path was protected against `>` but not against `cp`.** The redirection branch
  covered system *and* home paths; the copy branch covered only system ones. So
  `echo x > ~/.ssh/authorized_keys` was denied and `cp key ~/.ssh/authorized_keys` — the likelier
  spelling of the same write — was allowed.
- **A pending redirect was dropped when its target was a substitution**, so `sh < <(...)` looked
  like a bare `sh` that reads nothing. It is now visible as an opaque input.
- **`scripts/test-guard.sh` was not in CI.** The safety-critical suite ran only from the local
  release-readiness script, so a change opening a bypass could merge and be found at release time.
  It now runs on every pull request, early.

### Fixes — memory tiers and Context Optimizer

- **A cached pack failed permanently from its second run.** `fill_budget` guarantees the render
  fits the budget; the `cache: reused` marker is appended to the Metrics block afterwards, on a
  cache hit only. Any pack within ~75 characters of its budget therefore rendered fine once and
  then failed forever — and a tight budget, including the documented 2,000-char floor, is the
  normal case. The marker is now reserved during the fill, so the budget is true of both
  renderings.
- **Org memory was the one durable tier with no redaction**, and the widest-reaching one:
  `start-task` prints it into the starting context of every later task in *every* project, and
  `outcome-recorder --promote-to-org` feeds it from a single project's notes. It now redacts in
  `append_note`, so `note`, `promote`, and every future writer inherit the guarantee.
- **Redaction survivors.** A quoted value under a credential-shaped key
  (`password: "…"`, `db_password = '…'`) passed through, because the unquoted rule stopped at the
  first quote — the spelling every YAML file, `.env`, and config dump uses. `mariadb -p…` passed
  through because the attached-flag rule named only the `mysql` spellings of the same client.
- **Durable writes were not atomic and did not serialise.** Project memory, org memory, the
  knowledge base, and the blackboard all wrote with `Path.write_text`: two agents appending at once
  lost a bullet, and a crash mid-write left JSON no reader could parse. All now go through
  `scripts/durable.py` — temporary file plus `os.replace`, under an advisory lock covering the
  whole read-modify-write.
- **Org memory never replaced its own placeholder**, because the substitution looked for
  `- _empty` while the skeleton writes `- _No facts yet…_`. The same narrow prefix in
  `promote-rules.py` meant an untouched section looked like it held one real bullet, so an empty
  project could be promoted on the strength of its placeholder text.

### Fixes — CLI and workflow

- **`update --channel rc` was silently dropped** when the resolved version already equalled the
  active one, contradicting rc.3's own note that an explicit `--channel` wins everywhere it is
  passed. The followed line is now recorded even when no release moves.
- **`check-updates` reported an uninstalled machine as up to date and exited `0`**, because
  `"unknown"` compares equal to everything. It now reports `not-installed` and exits `2`.
- **The `apply:` hint dropped `--repo` / `--source` / `--provider`**, so it could print a command
  that would update from a different source than the one the answer above it came from. Every flag
  that changed which release was examined now travels with the hint, shell-quoted.
- **The parallel-phase gate read an empty `mutation_targets` as "writes nothing"**, when the
  documented rule — and the phase template's own default — is that silence means "writes
  everything". Two undeclared writers could be grouped.
- **A bare `finish-task` could write to the wrong project and delete another live task's
  scratch.** `start-task` rewrites one `.last-task-context` per cache root, so with two agents in
  one repository the most recent marker is not necessarily yours. Implicit resolution now refuses
  when more than one task is in flight, and lists them.
- **`finish-task` wrote the Recent-tasks bullet before validating `--fact`, `--repo-knowledge`,
  and `--lesson`**, so a typo in the third flag exited after the bullet had landed and the obvious
  retry duplicated it. All shapes are validated before anything is written.
- **`--field name=value` echoed the whole pair on a malformed name**, printing the value into the
  terminal — the exact exposure `--secret-field` exists to prevent, and a malformed name is most
  often somebody passing a credential through the wrong flag. Only the name is shown now.

### Added

- `agent-skills verify --explain-codes` prints the frozen exit-code table. `lib/asrelease/exits.py`
  had documented this flag as existing since 1.0.0-rc.1; it did not.
- `scripts/durable.py` — atomic, lock-serialised writes for every durable tier.
- `release.require_version`, `release.is_version`, `release.versions_equal`,
  `Layout.safe_component`, `Layout.staging_path`, `Layout.exclusive`, and `Layout.installed_path`.
- `BOUNDED_MARKERS` now covers `schema.read`, `artifact.read`, and `state.read` — an 800-table
  schema dump, a CI artifact, and a Terraform state are the three biggest payloads in practice and
  were the three `doctor` could not require a bound for. The reference tools that own those
  capabilities now declare them under `bounded_capabilities`.

### Documentation

- `database.explain` no longer claims to be side-effect free: `EXPLAIN ANALYZE` executes the
  statement, DML included, and needs `database.write`.
- The watchdog's stall window is documented as `max(5, budget × 0.5)` rather than a fixed twenty
  minutes, which is what the code has always computed.
- `docs/review-loops.md` no longer says a surviving `major` ships as a PR note; only
  `Loop: converged` advances, which `software-engineer` has always required.

### Publication

- **The GitHub release is deliberately deferred.** The tag `v1.0.0-rc.4` is pushed and the
  changelog and [security review](docs/security-review-v1.0.0-rc.4.md) are complete, but no GitHub
  release page is created for it. The only publication channel for this candidate is the npm
  bootstrap on the `rc` dist-tag; `latest` is untouched. What remains outstanding is the GitHub
  release page, and nothing depends on it — `agent-skills` resolves releases from git tags, not
  from GitHub releases, so a machine on the `rc` line can install this candidate from the tag
  alone.
- Guard performance re-measured because this candidate changes `guard_parse.py`: p50 `0.104` ms,
  p95 `0.298` ms, p99 `0.429` ms, max `0.559` ms, cold call `74` ms — unchanged against rc.3's
  p50 `0.109` / p95 `0.330`. No benign command moved from `ALLOW` to `ASK`.
- `scripts/audit-npm-package.sh` re-run against the exact `1.0.0-rc.4` tarball: 14 files, no
  product content, no credential-shaped file, no absolute developer paths, no lifecycle scripts,
  and the vendored engine byte-identical to `lib/asrelease/` and `scripts/install.py`.

### Test coverage added

Guard: 19 new `REDTEAM` corpus cases plus 8 CLI-path checks (266 corpus cases, 116 checks).
Release engine: 10 new tests including the traversal end to end, both halves of the rollback
defect, and lock contention (31 tests). CLI install: `verify` exit `7` on tamper and on drift,
`--explain-codes`, and self-contained apply hints (146 assertions). Context Optimizer: the
cache-reuse budget case plus a mutation probe (107 checks). Secret boundary: org memory across
`note`, `promote`, and `--promote-to-org`, the two new redaction patterns, and a probe that
removes org memory's `redact` call (43 checks).

## 1.0.0-rc.3 - Release candidate: a machine keeps the release line it chose

One defect, found by an RC tester who updated and got a stable release instead of the candidate
they had opted into. Additive against the frozen contracts; nothing renamed, renumbered, or
retyped.

### Fixes

- **`--channel` was not remembered, so an rc machine silently fell back to `stable`.**
  `resolve_channel` in `scripts/install.py` read the channel from the flags of the current
  invocation only. The recorded channel was read for display and never consulted, so on a machine
  installed with `--channel rc`:

  - a bare `agent-skills check-updates` resolved `stable` and reported `ahead` — an rc machine was
    never told a newer candidate existed;
  - a bare `agent-skills update` resolved `stable` and refused as a downgrade, suggesting
    `--allow-downgrade`, which would have moved the tester *backwards* off the line they were
    testing;
  - `check-updates --channel rc` printed `apply: agent-skills update`, a command that provably
    would not perform the update it had just described, because the hint dropped the flag.

  The effect was that every RC tester had to re-type `--channel rc` on every command, and their
  tooling actively told them they were up to date when they were not. Shipped in `0.44.0` and
  `1.0.0-rc.2`; not introduced by either.

  Channel resolution now falls back to the line recorded in `install.json` when no `--channel` is
  given, and the `apply:` hint carries the flag whenever the check asked about a line other than
  the one the machine follows. An explicit `--channel` still wins everywhere it is passed.

- **Taking a stable release dropped a machine off the `rc` line.** The manifest's `channel` field
  records `channel_of(version)` — the channel the installed *version* belongs to — so a machine
  following `rc` that took the stable release superseding its candidate recorded `stable` and was
  never offered a candidate again. This is exactly the superset case the channel design exists to
  support, and it defeated it. A second additive field, `follow_channel`, now records the line the
  machine follows, separately from the channel of what is installed. `rollback` carries it forward
  rather than choosing one.

### Added

- `follow_channel` in `install.json`, `requested_channel` in `check-updates --json`,
  `follow_channel` in `provider --json` and `doctor --json`. All optional and additive; no
  existing field changed name, type, or meaning.
- `agent-skills provider` prints the line being followed; `agent-skills doctor` prints it when it
  differs from the channel of the installed version.

### Safety

- Resolution fails closed. An `install.json` holding a value that is not a recognised channel
  resolves to `stable`, so a manifest cannot widen a machine's channel. The lookup can only ever
  resolve to a line the machine itself opted into earlier, so it cannot expose a candidate to a
  machine that never asked for one — asserted in both directions.
- Installations written before `follow_channel` existed fall back to `channel`, which for them was
  the requested channel in every case that could produce `rc`.

### Validation

`scripts/test-cli-install.sh` gains section 15 — 28 assertions over a real git remote publishing
`2.0.0-rc.1`, `2.0.0-rc.2`, `2.0.0`, and `2.0.1-rc.1` in sequence, covering both faults, the
explicit-flag override, rollback, the pre-field manifest, the malformed manifest, and a stable
machine in both directions. It includes a mutation probe: a copy of the engine with the manifest
lookup removed must fail the bare-update case, and does. The printed `apply:` hint is executed
verbatim and asserted to perform the update it described. Suite total 135, exit 0.

### Recorded

- **Correction to the v0.44.0 npm-deferral note.** That entry states the public bootstrap "still
  points at `0.43.1`". It does not, and never did: `0.43.1` was never published to the registry.
  `latest` points at `0.43.0`, so the stable-line deferral began one release earlier than the
  record says. Both `0.43.1` and `0.44.0` exist as GitHub releases with no matching npm publish.

  The v0.44.0 entry is left as written — historical changelog entries are not edited — so the
  correction lives here. The deferral itself was deliberate and remains an open owner decision;
  what was wrong was only the record of where the registry stood.

  Registry state as of `1.0.0-rc.2`: `latest` `0.43.0`, `rc` `1.0.0-rc.2`. Published versions:
  `0.43.0`, `1.0.0-rc.1`, `1.0.0-rc.2`.

- **Recorded as a 1.0 blocker:** the stable-line npm publication has to be resolved before
  `1.0.0`. See [ROADMAP](ROADMAP.md#previously-v100). Not a defect today — the lockstep rule in
  [docs/one-point-oh.md](docs/one-point-oh.md#npm-bootstrap) binds from `1.x` — but it does not
  survive the promotion unchanged.

## 1.0.0-rc.2 - Release candidate: adaptive execution and two reliability fixes

Not a feature release. Field use of `rc.1` produced two defects and one architectural
complaint; this candidate fixes all three and records the evidence. Offered only to machines on
the `rc` channel; `stable` is untouched. Every change is additive against the contracts frozen
at `rc.1` — nothing renamed, renumbered, or retyped.

### Fixes

- **Cleanup could delete a task directory that matched only by filesystem accident.**
  `finish-task` run with a lowercase issue key deleted the cache directory belonging to the
  uppercase key. macOS compares path components case-insensitively, so an existence check
  answered `True` for a directory whose real name differed only in case, and the recursive delete
  took it — then reported removing a path that had never existed on disk. It was being managed
  by pasting "always type the key in uppercase" into every subsequent dispatch brief, which is a
  warning standing in for an invariant. `cleanup_task` now resolves the key against the real
  directory entries by exact name and refuses anything ambiguous, naming the directory it
  declined to touch. Those warnings are gone from the briefs.

  Two further holes surfaced while writing the regression suite, both live: `cleanup-task .` and
  `cleanup-task ""` deleted the entire cache root, and a directory containing a git repository
  was deleted recursively. Both now refuse, as does a symlinked task directory.

- **Database credentials could reach agent and chat context.** A script printed two passwords
  into a transcript during read-only work. Once a value reaches model context it is in the
  transcript, in every summary of it, and in whatever the agent writes next — there is no recall,
  only rotation, which is why this is treated as a release blocker rather than hygiene.

  `redact()` already existed and was applied in exactly two places, both inside the Execution
  Guard. Probing it against the shapes a database workflow actually emits found six holes:
  `mysql -p<value>`, quoted JSON values, prefixed JSON key names, the `password:` colon spelling,
  `MYSQL_PWD`, and `DB_PASS`. All six now redact.

  New `agent-skills redact` filter, with a `--check` mode that exits non-zero and reports line
  numbers without printing the line. Four durable write paths — the blackboard, project memory,
  telemetry, and the committed knowledge base — now redact on write whether or not anyone
  remembered to pipe. [docs/secret-boundary.md](docs/secret-boundary.md) states the primary
  control (resolve access through the Access Resolver, never put a value on a command line) and
  states plainly what redaction does not cover.

### Adaptive execution

The complaint was not that the workflow is slow. It is that the same workflow was applied to work
of wildly different consequence: a request for three read-only numbers got three fresh-context
dispatches and three 40 KB evidence dossiers, and small delivery phases paid the full cost of a
fresh agent, a lifecycle, and a review round regardless of size.

- **Three profiles**, chosen deterministically by `agent-skills execution-profile`: `LIGHT`,
  `STANDARD`, `RIGOROUS`. The two halves are asymmetric on purpose. Relaxation needs seven
  conditions to hold at once, and any unstated signal keeps `STANDARD`. Escalation is
  unconditional — nine domains, irreversibility, and a production or cross-system blast radius
  each force `RIGOROUS`, and a request to lower one is refused out loud rather than honoured or
  silently dropped.
- **`LIGHT` buys less ceremony, never less safety.** Credential safety, authorization checks,
  bounded reads, explicit verification, evidence retention, and the destructive-action floor are
  one list, identical at all three profiles, asserted by test so it cannot grow a per-profile
  exception later.
- **Output contract.** A dispatch can now say what artifact the human needs — audience, primary
  question, deliverable, reading-time target, evidence depth and location — not only what
  question to answer. The primary deliverable is not automatically the evidence artifact;
  evidence is preserved at a named path rather than suppressed. No global character cap: a hard
  limit would truncate the one review that genuinely needed nine findings.
- **Proportional phase execution.** Phases carry `execution_profile`,
  `expected_effort_minutes`, and `mutation_targets`. `delivery-runner` runs `LIGHT` phases inline
  and keeps fresh context plus independent review for `RIGOROUS`. It reads profiles and may not
  change one in either direction — that is a planner decision. A `LIGHT` phase is still verified
  from artifacts, never from the fact that the runner's own context just did the work.
- **Safe concurrency.** `plan-next` proposes a parallel group only when there is no dependency
  edge, both phases are `parallel_safe`, each lists the other in `parallel_with`, and declared
  `mutation_targets` are disjoint. A phase that does not declare what it writes is treated as
  writing everything. Capped at 3; `AGENT_SKILLS_MAX_PARALLEL` is clamped, not trusted.
- **Watchdog.** `agent-skills watchdog` measures stagnation, not elapsed time. A hard timeout
  kills careful work along with stuck work and teaches everyone to pad estimates; work still
  writing milestones at three times its budget is bigger than someone thought, not stuck, and
  gets narrowed or split. No daemon and nothing polling — it is a pure function of what is on
  disk.
- **Incremental artifacts.** `agent-skills blackboard progress` records milestones so an
  interrupted run leaves behind what it had already learned. The reported case — an overscoped
  dispatch that ran about an hour and wrote nothing, so the retry started from zero — now reaches
  a `stop` verdict, and a brief that has produced nothing past its settling window reaches
  `restart`.
- **Wamala remains an ownership dispatcher.** It gains profile selection and one guardrail — do
  not implement under `LIGHT` either — and loses nothing. Routing, one owner per step, artifact
  verification, the dispatch cap, and the safety floor are unchanged. What adapts is execution
  depth, not ownership.

### Performance measurement

Telemetry gains optional fields for `profile`, time to first artifact, time to verified result,
dispatches, context loads, review rounds, concurrency use, and no-output runs. Reported as
medians, because one pathological run drags a mean far enough to hide what a typical run costs.
The headline measure is **time to verified useful result**; total runtime is not the target, and
a faster incorrect result is a regression. Local cache only, nothing transmitted.

### Additive against the frozen contracts

Three new CLI verbs (`redact`, `execution-profile`, `watchdog`), one new blackboard subcommand
(`progress`), optional new fields in `plan-next` output, the phase and index templates, and
telemetry. The `Profile` and `Parallel` index columns are **appended**, never inserted — cells
are read positionally, so inserting them would silently mis-read every plan already in a cache
directory. Six-column indexes parse unchanged and default to `STANDARD`, as does an unrecognised
value.

### Validation

Three new suites, 129 assertions, 9 mutation probes:
`test-lifecycle-fs.sh`, `test-secret-boundary.sh`, `test-adaptive-execution.sh`. Each probe
weakens the build and asserts the matching check then fails — emptying the escalation table drops
a migration to `LIGHT`, removing the overlap check groups two writers to one file, marking every
run stalled kills work that was still producing.

Seven new evals drawn from the reported incidents rather than implementation internals. No
regression in the standing suites: guard 108, tools 43, access-resolution 100, context-optimizer
105, front-door 63, release-engine and run-evals green, validator at its 61-warning baseline.

## 1.0.0-rc.1 - Release candidate: contract freeze and certification

Not a feature release. This candidate freezes the contracts `agent-skills` will support after
`1.0.0`, fixes the release blockers found while certifying them, and records the certification
evidence. Offered only to machines on the `rc` channel; `stable` is untouched.

### Contracts frozen

[docs/one-point-oh.md](docs/one-point-oh.md) is the enumerated list. Within the `1.x` line these
do not change and removing any of them is a breaking change held for `2.0`:

- **CLI** — the release-lifecycle command names (`install`, `update`, `rollback`, `versions`,
  `check-updates`, `provider`, `verify`, `uninstall`, `hosts`, `doctor`, `migrate`, `version`),
  the task-lifecycle commands (`start-task`, `finish-task`), and the `access` / `tools` /
  `context` / `guard` subcommand namespaces. Exit codes: the release table (`0` `2` `3` `4` `5`
  `6` `7` `10`) plus each subsystem's own small documented contract. `--json` shapes for the
  reporting commands: fields may be added, never renamed or retyped, and no secret value ever
  appears in any output.
- **Installation** — `AGENT_SKILLS_HOME` and `AGENT_SKILLS_CONFIG_DIR` semantics, the versioned
  layout, `current` as the single activation lever, the atomic transaction with rollback,
  `update` never downgrading as a side effect, `rollback` as a one-step undo, `uninstall`
  ownership rules, and the `stable` / `rc` channel behaviour.
- **Release provider** — the four-verb interface (`resolve_latest`, `resolve_version`,
  `fetch_release`, `verify_release`); everything after `fetch_release` is provider-independent;
  providers are chosen by name from a fixed in-process registry, never from a path in
  environment or config. `release.json` is `schema: agent-skills.release/v1` with a
  `sha256-tree/v1` payload hash.
- **npm bootstrap** — `@wamalalawrence/agent-skills` stays a public thin bootstrap containing the
  installer and nothing else. Bootstrap and runtime versions move in **lockstep**: one version
  number, published together.
- **Skills** — nine top-level, two nested, names fixed. Wamala routes by engineering ownership;
  one owner per dispatched step; verification by persisted artifact; lifecycle wrappers
  mandatory; the destructive-action safety floor above all of it.
- **Engineering Tool Capability Framework** — the five tool classes, the four action classes,
  the eighteen capability family prefixes and their capability names and action classes, the
  `agent-skills.tool-definition/v1` schema, the deterministic transport resolution order, and
  the rule that fixtures are never supported tools.

### Breaking changes made before the freeze

None. Nothing was renamed or renumbered. All changes below are additive or fixes.

### Fixes

- **`check-updates --vendored` assumed a public repository.** The release repo is private; an
  unauthenticated GitHub releases API call now returns not-found. The command's message and
  `docs/updates.md` (including the CI example) now state that a read token is required, and the
  error no longer implies the only cause is rate-limiting.
- **`SECURITY.md` rewritten.** The old "concerns in scope include" list read as a set of
  predetermined defects. It now describes how the project treats security — external content is
  untrusted, the Execution Guard's deterministic floor, credentials kept out of agent context —
  and what a useful report looks like.
- **`ROADMAP.md` brought current** — v0.44.0 marked shipped, the roadmap repointed at the RC and
  1.0, stale "no installer / public-benefit / nine skills" language removed.
- **`docs/versioning.md`** now leads with the RC status and points at the frozen-contract list;
  the `release.json` schema example no longer bakes in a file count.
- **`agent-skills tools resolve`** now prints the bounded-read / Context Optimizer instruction
  inline for a `bounded` capability, at the moment of resolution, rather than in the docs only —
  the minimal hardening for the v0.44.0 residual without the framework executing anything.
- **Installing a pre-release checkout: `--dev` installs no longer need `--channel`.** This is
  the project's first pre-release, and the local release provider correctly refuses to install
  an `rc` version under the default `stable` channel. That is right for `npx … install`, but it
  also broke `setup.init` and `agent-skills dev install` — a development install of your working
  tree is not a release-channel decision. `scripts/install.py` now resolves the channel: an
  explicit `--channel` always wins; `--dev` falls back to `any`; everything else falls back to
  `stable` exactly as before. A plain `install --provider local --source …` **still** refuses a
  pre-release checkout, on purpose. Covered by new `test-cli-install.sh` assertions.
- **The test harnesses and CI assumed `VERSION` was always stable.** Every path that installs
  the current tree without `--dev` (`test-cli-install.sh`, `test-global-install.sh`,
  `test-release-readiness.sh`, `.github/workflows/ci.yml`) now passes `--channel any` — the
  existing "install exactly this tree" escape hatch, a no-op for a stable version. The git
  fixture in `test-cli-install.sh` and `test-private-source.sh` derive `rc` from a pre-release
  `VERSION` so they exercise a real release-candidate publish + install.

### Certification

Full evidence: [`eval-runs/v1.0.0-rc.1/summary.md`](eval-runs/v1.0.0-rc.1/summary.md).
Security review: [`docs/security-review-v1.0.0-rc.1.md`](docs/security-review-v1.0.0-rc.1.md).

- **Clean private install** — `scripts/test-private-source.sh`: authenticated install / doctor /
  verify / update / host registration / Guard coherence all pass from the remote into a
  throwaway `HOME`; unauthenticated exits `3` with `AUTHENTICATION_REQUIRED`, no hang, no
  partial install, no credential leak, no partial host registration.
- **Upgrade / rollback** — `0.44.0 → 1.0.0-rc.1 → rollback → 0.44.0 → upgrade` with credential
  identities, bindings, legacy `.env`, and unrelated host skills preserved. Simulated failed
  download / integrity / staging / self-test / activation leave no mixed-version install.
- **Security** — 17 fresh adversarial probes (prompt injection across ticket/log/DB fixtures,
  capability escalation, secret-leak sweep) plus the standing suites: Execution Guard 108
  (BYPASS + REDTEAM corpora), release engine 21 (archive traversal, symlink escape, integrity,
  downgrade, hostile provider), access resolution 100, tool framework 43.
- **Offline** — after install, `doctor`, `verify`, Context Optimizer, Execution Guard, tool
  discovery/resolution, project context, and credential-backend reporting all work with the
  network dead. Only install / update / check-updates / external-service resolution need it.
- **Hosts** — filesystem registration verified for the eight filesystem hosts (`verify`: N/N
  skills resolve to the canonical tree each); JetBrains is manual and not filesystem-verifiable,
  documented as such, no verification manufactured.

### Publication

- Tag `v1.0.0-rc.1`; GitHub release marked **prerelease**, `latest` not moved. The
  git provider is the distribution path for this candidate.
- npm bootstrap `@wamalalawrence/agent-skills@1.0.0-rc.1` is **published** under the `rc`
  dist-tag (14 files, no product content, version matches `VERSION`, tarball byte-identical to
  `npm/`). `latest` stays on `0.43.0` — the RC is not promoted to `latest`.
  `npx @wamalalawrence/agent-skills@rc install --channel rc` into a clean `HOME` resolves
  `1.0.0-rc.1 (rc, via git)` and passes `verify` / `doctor` / `tools doctor`; run without git
  auth it exits `3` cleanly.

## 0.44.0 - Engineering Tool Capability Framework

The last substantial feature release before `1.0.0-rc.1`. Agent Skills can now use the
engineering tools a developer touches in normal delivery work — source control, a tracker, a
knowledge base, chat, a cluster, a cloud, CI, a database, a broker, a package registry — without
a bespoke adapter per vendor and without widening the Access Resolver into a product switch.

This release also removes the project's former open-source licensing. The repository is private;
see [Licensing](#licensing-changed) below.

### The framework

Infrastructure, not a skill — like the Access Resolver and Execution Guard, nothing routes work
to it. A skill names a **capability**; the resolver decides **how** it can be provided.

```text
skill -> required capability -> Engineering Tool Resolver
   host -> mcp -> authenticated CLI -> local/native client -> profile -> API -> unresolved
        (needs auth?) -> Access Resolver        (dangerous?) -> Execution Guard
```

- **Tool classes.** `AGENT_HOST`, `LOCAL_TOOL`, `REMOTE_SERVICE`, `RUNTIME_RESOURCE`,
  `DATA_RESOURCE`. VS Code / IntelliJ stay Agent Skills *hosts*, not tools the resolver reaches.
- **Capability vocabulary.** 72 provider-neutral capabilities across 18 families (`scm.*`,
  `tracker.*`, `knowledge.*`, `communication.*`, `runtime.*`, `infrastructure.*`, `cloud.*`,
  `api.*`, `ci.*`, `quality.*`, `observability.*`, `incident.*`, `messaging.*`, `database.*`,
  `data_pipeline.*`, `package.*`, `design.*`, `security.*`) in
  [`lib/tools/capabilities.json`](lib/tools/capabilities.json). A 1.0-freeze candidate — see
  [docs/engineering-tool-capabilities.md](docs/engineering-tool-capabilities.md).
- **Action classes.** Every capability is fixed as `READ`, `WRITE`, `ELEVATED`, or
  `DESTRUCTIVE`, mapped onto the existing Execution Guard rules — no second safety engine.
  `tools resolve` refuses `WRITE`/`ELEVATED` without `--allow-write` and never resolves
  `DESTRUCTIVE`. *READ cannot silently become WRITE.*
- **Tool definitions.** One small `agent-skills.tool-definition/v1` JSON file per tool in
  [`lib/tools/registry.d/`](lib/tools/registry.d). Not a DSL; `scripts/tools.py` reads it with no
  per-tool branching.
- **CLI.** `agent-skills tools list | status | inspect | classify | resolve | capabilities |
  classes | doctor`. `status` reads like the `doctor` capability report; no command configures a
  tool, and no secret value is ever printed.

### Reference tools

Validated across the engineering lifecycle: `github` (SCM + issues + PRs + Actions, reusing the
GitHub access ladder), `github-actions`, `jenkins`, `jira` (reusing tracker auth discovery),
`confluence`, `slack` (read-only), `aws`, `kubernetes`, `terraform`, `postman`, `sonarqube`,
`sentry`, `pagerduty`, `kafka`, `postgresql`, `npm`. Four definitions — `gitlab`, `gcp`, `mysql`,
`newrelic` — ship in [`lib/tools/fixtures/`](lib/tools/fixtures) as **extensibility fixtures
only**; they are not claimed as supported, and `scripts/test-tools.sh` asserts they fit with no
core change.

### Integration

- Wamala still routes by engineering **ownership**, never by which tool is involved. The
  specialist requests capabilities after routing.
- Large tool output — CI logs, CloudWatch / Kubernetes logs, Sentry events, Slack threads, Kafka
  samples, wide query results — is marked `bounded` and must be read with an explicit bound and
  passed through Context Optimizer. `tools doctor` and `validate-repo.py` enforce the marking.
- New docs: [docs/engineering-tools.md](docs/engineering-tools.md),
  [docs/engineering-tool-capabilities.md](docs/engineering-tool-capabilities.md). Cross-links
  added to `mcp.md`, `access-resolution.md`, `execution-guard.md`, `context-optimizer.md`,
  `known-limitations.md`, `versioning.md`, `release-checklist.md`.

### Tests

`scripts/test-tools.sh` — 41 assertions covering discovery, the local-tool / remote-service
split, an authenticated capability beating a stored credential, GitHub/Jira still resolving,
AWS/Kubernetes/Terraform action classification, a bounded read-only PostgreSQL path, Context
Optimizer on large tool output, untrusted external text staying inert, provider-failure
isolation, no cross-service identity bleed, READ not escalating to WRITE, a destructive operation
still denied by the Execution Guard, an unknown future tool added with only a definition file,
and the four fixtures fitting with no special core branch. `validate-repo.py` gained a
`check_engineering_tools` gate that runs `tools doctor`. New eval:
[`evals/engineering-tools-capability-resolution.md`](evals/engineering-tools-capability-resolution.md).

### JetBrains

The known limitation is documented precisely: JetBrains AI Assistant registration is a manual IDE
action and **cannot be verified from the filesystem**, so `verify` / `doctor` report it as
`manual` and a green `verify` is not evidence the IDE entry exists. No automated check is claimed
or faked. See [docs/assistants.md](docs/assistants.md#jetbrains-ai-assistant).

### Licensing changed

The repository is private. The former MIT license is removed and replaced with an all-rights-
reserved proprietary notice in [LICENSE](LICENSE) — no invented terms, just the absence of a
grant. `license:` in every `SKILL.md` is now `PROPRIETARY`; `npm/package.json` is `UNLICENSED`.
Public-project framing is gone from `README.md`, `CONTRIBUTING.md`, `SUPPORT.md`, and
`GOVERNANCE.md`. Historical CHANGELOG and eval-run entries are left as written.

- **npm publication is deferred.** The `@wamalalawrence/agent-skills` bootstrap on the public
  registry still points at `0.43.1`. Whether a private, proprietary project should keep publishing
  a public bootstrap is an owner decision recorded in
  [docs/security-review-v0.44.0.md](docs/security-review-v0.44.0.md); this release is distributed
  through the git provider (tag + GitHub release) only.

### Security review

[docs/security-review-v0.44.0.md](docs/security-review-v0.44.0.md) — threat-by-threat, covering
READ→WRITE escalation, resolution-is-not-authorization, destructive actions on the Guard floor,
bounded production reads, no-secret-in-output, provider-failure isolation, repository config not
steering machine credentials, and untrusted tool content.

### Release-harness fixes (pre-existing)

`scripts/test-release-readiness.sh` had three bugs that predate this release and reproduce on
`main`: (1) the upgrade-from-previous-tag section ran the old installer with an `install --yes`
flag no `install` subcommand has ever accepted; (2) with that fixed, the baseline install then
re-fetched the now-private repository anonymously from a throwaway `$HOME` — section 6 is about
upgrade mechanics and state preservation, not distribution access, so it now installs the
previous tag from its own on-disk tree with `--provider local`; (3) the README section required
bold skill-count prose (`**N top-level skills**`) the README had dropped in favour of "the
eleven skills". All fixed; the upgrade path is now actually exercised, and `README.md` carries
the count prose that `validate-repo.py` also verifies against the skills on disk.

## 0.43.1 - Private-Source Validation

Patch release. Confirms the v0.43.0 installation and distribution contract against the source
repository's transition from public to private, and corrects the published package identity.

### Package identity corrected

`v0.43.0` was tagged naming `@wamala/agent-skills` as the npm package. That scope was never
publishable: an authenticated publish, two-factor authentication satisfied, returned `404` on the
registry `PUT` — npm's way of reporting "you may not create a package in this scope," which reads
as a missing package rather than a permission failure. `npm view` and `npm org ls` had both
appeared to say otherwise; neither actually answers the question a publish does.

The package is `@wamalalawrence/agent-skills`, the publishing account's own scope, published
publicly and verified with `npx @wamalalawrence/agent-skills install` against the live registry —
not only the packed tarball. See
[docs/release-providers.md](docs/release-providers.md#the-package-name).

### Stage B — private-source acceptance

The repository was made private. `scripts/test-private-source.sh` was run against the real remote,
from a genuinely clean sandbox — never the source checkout, never an existing installation:

```text
PRIVATE_REPOSITORY_ACCESS       PASS      HOST_REGISTRATION               PASS
CLEAN_PRIVATE_INSTALL           PASS      EXECUTION_GUARD_COHERENCE       PASS
AGENT_SKILLS_DOCTOR             PASS      EXISTING_STATE_ISOLATION        PASS
AGENT_SKILLS_VERIFY             PASS      AUTHENTICATION_REQUIRED_BEHAVIOR PASS
PRIVATE_UPDATE_PATH             PASS      RELEASE_PROVIDER                git

PRIVATE_SOURCE_DISTRIBUTION_READY: YES
```

Authenticated install, `doctor`, `verify`, `update`, host registration into every supported host
directory, and Execution Guard resolving through the release fetched from the private source, all
pass. The unauthenticated case exits `3` with `AUTHENTICATION_REQUIRED`, leads with that
classification rather than a raw git error, never reports the repository as "not found," never
hangs, and leaks no token. The installation already on this machine was hashed before and after:
unchanged.

Full evidence: [`eval-runs/v0.43.0/summary.md`](eval-runs/v0.43.0/summary.md#stage-b--private-source-acceptance).
Both prior gaps closed: [`docs/security-review-v0.43.0.md`](docs/security-review-v0.43.0.md#what-was-not-proven-at-release-time-and-what-has-since-been-resolved).

### Two fixes, neither in product code

**The test harness's own isolation was incomplete on macOS.** `gh`'s token is commonly stored in
the login Keychain; Keychain Services resolves its default search list through
`~/Library/Preferences`, keyed to `$HOME`. A throwaway sandbox `$HOME` — needed so the acceptance
suite never registers skills into the machine's real host directories — has no matching preference
file, so `security`/`gh` silently saw no login keychain at all. Confirmed directly with `security
list-keychains` under a real vs. substituted `$HOME`. Not a product defect: a real user's shell
always matches their own Keychain. Fixed by grafting in exactly `~/Library/Preferences` and
`~/Library/Keychains` as read-only symlinks — nothing else, nothing under them ever written.

**CI's link checker started failing on the repository's own homepage link.** GitHub answers an
unauthenticated request for a private repository with `404` on every path, including the bare
homepage every `SKILL.md` and `npm/README.md` link to. One narrow ignore pattern added, matching
the style of the exemption already there for issues/pull/releases/compare/commit sub-paths.

`lib/asrelease/`, `scripts/install.py`, `bin/agent-skills`, and every host/guard registry are
unchanged in this release.

## 0.43.0 - One Command, One Installer

Minor release, and a pre-1.0 architecture change. Installing Agent Skills stops being an act of
repository maintenance.

Until now the supported install was `git clone`, `cd`, `./setup.init`. That made the distribution
channel and the product the same object: the installer was a file inside the thing being installed,
updates were `git pull`, and "which version am I on" was answered by a working tree the user was
expected to keep. It worked while the repository was public and every user was also a contributor.
It stops working the moment either of those changes — and both are about to.

The supported installation is now:

```bash
npx @wamalalawrence/agent-skills install
```

and the durable command afterwards is, as before, `agent-skills`.

### One installer, and a release provider under it

There is exactly one installation implementation. It lives in `lib/asrelease/`, and every path
reaches it: the npm bootstrap, the `agent-skills` CLI, and `setup.init`. The bootstrap package
vendors that engine rather than reimplementing it, and CI asserts the vendored copy is byte-identical
to the repository's, so the two can never drift into being two installers.

Underneath it is a release provider — the seam that decides where a payload comes from:

```text
agent-skills install
        |
        v
  Release Provider
        |
        +----------------------+----------------------+
        |                      |                      |
        v                      v                      v
GitReleaseProvider    LocalReleaseProvider    (future) PremiumRegistryProvider
```

The user-facing commands do not change across providers. `local` is how an unreleased branch is
tested and how the whole acceptance suite runs without a network; `git` is how everyone else
installs, and works identically against a public remote and an authenticated private one. A third is
proven rather than promised: the test suite registers an in-process fake registry provider — with an
entitlement check and an `AUTHENTICATION_REQUIRED` path — and runs the real install transaction
through it. If installation ever grows a hidden dependency on GitHub, that test fails.

Providers are selected by name from a fixed registry, never loaded from a path. A repository the user
has merely opened must not be able to point the global installer at code, or credentials, of its
choosing.

See [docs/release-providers.md](docs/release-providers.md).

### Installation is a transaction

```text
RESOLVE -> DOWNLOAD -> VERIFY -> STAGE -> SELF-TEST -> ACTIVATE -> HOSTS -> VERIFY
```

Everything up to and including the self-test happens in a staging directory. A download that fails, a
payload whose hash does not match the one the release was published with, or a release whose runtime
cannot answer its own self-test all leave the machine untouched and the previous release running.
Only `ACTIVATE` changes anything, and it is a single atomic symlink swap. If activation or host
reconciliation fails after that point, the previous release is put back.

```text
~/.agent-skills/
├── current -> versions/0.43.0     the only pointer that decides what runs
├── versions/
│   ├── 0.42.0/                    kept, so rollback has somewhere to go
│   └── 0.43.0/
├── state/                         install history; survives every upgrade
└── skills -> current/skills       and lib, bin, scripts, docs, hooks
```

Host registrations and Execution Guard hooks point at `~/.agent-skills/...`, which resolves through
`current`. Activating a release therefore moves every host and every hook in the same instant, and
there is no window in which two hosts disagree about which version they are on.

- `agent-skills rollback` returns to the release you were on before, re-verifying its payload first
  and reconciling hosts and hooks back to it.
- `agent-skills update` refuses to replace the active release with an older one unless asked. Going
  backwards is `rollback`; it is never a side effect of an update.
- `agent-skills versions` shows what is installed, what is active, and what a rollback would restore.
- Release channels exist: `stable` never offers a pre-release, and `--channel rc` is a superset, so
  `1.0.0-rc.1` can be installed without corrupting stable update semantics.

### Integrity, and archives treated as hostile

Every release carries a `release.json` manifest with a `tree_sha256` over every payload file's path,
executable bit, and content. Before a payload goes near activation, four things must agree: the
version requested, the tag the provider resolved, the payload's own `VERSION`, and the manifest. Any
disagreement is an integrity failure, not a warning. `signature` is reserved so signed releases add a
field rather than a schema; no custom cryptography is used or planned.

Anything unpacked from an archive is treated as an attacker-controlled write primitive. Absolute
paths, `..` components, symlinks or hardlinks escaping the extraction root, device nodes, and setuid
bits are all rejected — and rejected before a single byte is written, so a hostile archive cannot
half-extract. The adversarial cases are in `scripts/test-release-engine.py`.

### Distribution access is not project access

The git provider uses credentials the developer already has: git's own credential helpers and
ssh-agent first, then the GitHub CLI when it is installed and already logged in — through an askpass
helper, so the token never enters the installer's process, never appears in a command line visible to
`ps`, and is never written to disk or into Agent Skills configuration. There is no token prompt and
no `GH_TOKEN` requirement.

Interactive prompting is disabled outright, because an installer that blocks on an invisible
credential prompt inside an editor's integrated terminal is worse than one that fails. When access is
missing the installer exits `3` with `AUTHENTICATION_REQUIRED` — including when GitHub answers an
unauthenticated request for a private repository with a 404, which would otherwise send people
hunting for a typo that is not there. Every git message is redacted before it is printed.

The v0.37.0 rule is unchanged and now structural: installing Agent Skills does not configure project
credentials.

### The npm package is a bootstrap, not the product

It contains the Node entry point, the installation engine, and the release providers. Fourteen files,
28 KB. It contains no skills, no docs, no runtime, and no credentials, because a published npm
tarball is public permanently regardless of who can read the repository behind it. It declares no
`preinstall`, `install`, `postinstall`, or `prepare` script: nothing happens on `npm install`, only
when a human types a command.

`scripts/audit-npm-package.sh` inspects the packed tarball itself — not the `files` list, because
those two disagree the moment a glob is wrong — and fails the release on product content, anything
credential-shaped, an absolute developer path, a lifecycle script, or a vendored engine that has
drifted. It runs in CI on every change.

### `setup.init` retired, and pre-v1 debt removed

`setup.init` went from 2,465 lines to 128. It is now a development helper that installs the working
tree you are standing in, through the same engine as everything else. It is no longer the product
installer.

Removed outright, rather than carried into the 1.0 contract:

- `--legacy-workspace` and `--workspace-root`, and the workspace installation model behind them;
- the installer-written `.env` and its managed marker block, `.jira-config.yml`, the `.skills`
  symlink, and `.agent-skills.lock`;
- `PROJECTS_JSON` discovery and configuration at install time;
- the Jira, Confluence, Sonar, and environments setup prompts;
- the credential blast-radius probe, a heuristic that raised a question it could not answer;
- the legacy workspace updater and the second update path it implied.

None of this deletes anything a user has. The access resolver still reads an existing `.env`,
`.env.local`, `.jira-config.yml`, and `.agent-skills.yml`, and `agent-skills migrate` still reports
what is obsolete and what is still in use. What is gone is the code that *wrote* those files. A
removed flag prints what replaced it instead of failing silently.

### Diagnostics

`agent-skills doctor` now reports the active version, the install root, which provider and channel
the machine is on, how many skills are installed, which hosts are registered, whether the CLI is on
`PATH`, whether anything has drifted, whether any link is broken, what a rollback would return to,
and whether Context Optimizer and Execution Guard are present and version-coherent. It contacts no
network, because "am I offline" is one of the questions people run it to answer.

`agent-skills verify` is machine-oriented and asserts version coherence across the manifest,
`current`, and the payload. Exit codes are now a documented contract — `0`, `2`, `3`, `4`, `5`, `6`,
`7`, `10` — frozen at 1.0 and asserted by the test suite so a renumbering cannot pass silently. See
[docs/versioning.md](docs/versioning.md#exit-codes).

### Tests

- `scripts/test-cli-install.sh` — 104 assertions across fourteen cases, every one against a
  throwaway `HOME` with a space in its path. Written around failure rather than success: a tampered
  payload, a release that fails its self-test, an interrupted update, an unrequested downgrade, a
  source that cannot be read, migration from a pre-CLI installation, and installation from the
  packed npm artifact over a real git remote with no clone anywhere in the flow.
- `scripts/test-release-engine.py` — 21 checks covering hostile tar archives, payload integrity,
  version ordering, redaction, exit-code stability, provider independence, and the one move in the
  transaction that cannot be undone.
- `scripts/test-global-install.sh` — retargeted at the new engine and trimmed of the legacy-workspace
  cases; still 112 assertions on host adapters and ownership.
- `scripts/audit-npm-package.sh` — the package-content gate, in CI and in the release checklist.
- `scripts/test-setup-update-preserves-credentials.sh` — removed. It tested a code path that no
  longer exists.

### Upgrading

```bash
npx @wamalalawrence/agent-skills install
```

The installer recognises an existing installation, moves it onto the versioned layout, and leaves
credential identities, project bindings, unrelated skills, and unrelated hooks exactly where they
are. The old clone is no longer needed and can be removed.

## 0.42.0 - Even If The Agent Is Wrong

Minor release. Agent Skills already said what an agent must not do. The
[destructive-action safety policy](docs/destructive-action-safety.md) has been the single source
of truth for that since v0.30.0, and every `SKILL.md` inherits it.

That policy works on the agent's reasoning. It therefore holds while the agent is reasoning
correctly, and the failure modes it exists to prevent are precisely the ones where it is not:
a model that made a mistake, a hostile `README` that steered it, a tool response carrying
instruction-shaped text, a chain of individually reasonable steps that ended somewhere
unrecoverable.

This release adds the second layer:

```text
skill policy -> agent reasoning -> generated action
                                        |
                                  EXECUTION GUARD
                                        |
                             allow  /   ask   \  deny
                                        |
                                  tool / runtime
```

> **Prompt-level safety works on cooperative reasoning. Execution Guard works on actions.**

Neither layer makes the machine safe, and the documentation says so in the same voice it uses
for what the feature does.

### Added

- **[Execution Guard](docs/execution-guard.md)**, exposed as `agent-skills guard`. One canonical
  engine decides; every host adapter converts that host's request into an `Action`, calls the
  same `resolve()`, and converts the `Decision` back. No adapter contains a rule, so two hosts
  cannot drift into disagreeing about what `rm -rf /` means.
- **Deterministic classification.** No model is consulted for a blocking decision. Sending
  `rm -rf /` to a language model and asking whether it looks dangerous makes the answer
  probabilistic exactly where it must not be, and puts a network round trip in front of every
  shell command.
- **`ALLOW` / `ASK` / `DENY`**, each carrying a rule id, a risk category, a reason, the resolved
  target, and a **safe alternative**. 50 rules, 30 of them hard floor. `agent-skills guard rules`
  prints the catalogue with each rule's effective outcome under the current configuration
  (54 rules, 31 of them hard floor);
  `agent-skills guard explain` answers "why was this blocked?" for a human.
- **Structural command decomposition** rather than pattern matching. `&&`, `||`, `;`, `&`,
  newline, pipelines, `$( )`, backticks, `<( )`, subshells, brace groups, `VAR=x` prefixes,
  `sudo`/`env`/`nohup`/`timeout`/`xargs` wrappers, nested `bash -c`, `ssh host '…'`, and
  `find -exec` are all followed. `echo "rm -rf /"` is `ALLOW`, because quoting is honoured and
  the dangerous text is an argument, not a command.
- **Target awareness.** `rm -rf ./build` is `ALLOW`, `rm -rf src` is `ASK`, `rm -rf /` is `DENY`.
  Paths are canonicalised before classification, so `repo/tmp -> /important/data` is caught as
  `FS_SYMLINK_ESCAPE` rather than trusted for starting with the repository path. Globs are judged
  by the directory they would sweep; unresolvable variables become `ASK`, not `ALLOW`.
- **Configuration trust levels.** Repository configuration — committed or repo-local — may add
  restrictions and may never remove them. A `guard:` block that tries to lower a rule is ignored
  and reported; an invented knob such as `allow_rm_rf: true` is refused by name rather than
  silently dropped. Hard-floor rules cannot be lowered by any layer, including the user's own
  machine policy. This is the same rule the [access resolver](docs/access-resolution.md) already
  enforces for credentials.
- **Host integration for four hook-capable hosts**: Claude Code (`PreToolUse`), Cursor
  (`beforeShellExecution` + `beforeMCPExecution`, registered `failClosed`), Kiro (`preToolUse`),
  and Codex (`PreToolUse`). `agent-skills guard doctor` reports `ENFORCED` / `AVAILABLE` /
  `PARTIAL` / `ADVISORY` per host, and never claims enforcement a host does not offer.
- **Ownership-safe installation.** `guard install` merges rather than replaces: hooks you already
  had survive, a backup is left beside each modified file, a config that is not valid JSON is
  refused, a same-named file we did not write is left alone, running it twice produces one
  registration, and `guard uninstall` removes only entries carrying the agent-skills signature.
- **Structured-tool and MCP gating.** The engine is built around an action abstraction, not a
  shell string. An MCP `query` argument carrying `DROP TABLE` is denied, a structured `Write` to
  `/etc/hosts` is denied, and an ordinary MCP write is left alone — a guard that asks about every
  tool call is a guard that gets switched off.
- **Redacted local auditing.** Decisions are recorded at `<config-dir>/guard/decisions.ndjson`,
  `0600`, bounded, never uploaded. **No raw command line is stored**: the record carries the rule,
  the classification, a redacted target, and a SHA-256 fingerprint of the redacted command.
- **`agent-skills guard scan-content`**, which flags instruction-shaped, waiver-shaped,
  download-and-execute, credential-shaped, and destructive-command text in untrusted files. It
  reports `SUSPICIOUS_INSTRUCTION_SHAPED_CONTENT` — evidence for a reviewer — and deliberately
  does not claim to have found an attack.
- **`agent-skills guard run`**, wrapper mode for hosts with no pre-execution hook.
- **[`scripts/test-guard.sh`](scripts/test-guard.sh)**: 108 checks over a 248-case corpus, all
  four host dialects, the trust model, redaction, and seven mutation probes.
- A **red-team corpus**. After the first four corpora were green, the guard was attacked with 43
  techniques nobody had written a test for. Thirteen reached `ALLOW` on the first attempt: a
  program named by a variable or a substitution, a multi-call binary applet, a here-string, a
  script or SQL statement arriving from a file or a pipe, `find -delete`, `perl -e 'unlink'`,
  `__import__('shutil').rmtree`, `truncate` over a system file, and a download whose output file
  is executed by a later segment of the same command line. All thirteen are fixed, four rules
  were added for them, and all 28 are permanent regression cases.

### Changed

- `agent-skills doctor` reports Execution Guard status per host, in both the brief and full
  reports and in `--json`.
- `agent-skills install` prints an Execution Guard recommendation and the exact commands. It does
  **not** install it. Registering the guard edits the host configuration files that decide what a
  user's agent may do, and doing that as a side effect of installing skills would be a surprise
  in the one category where surprises are least acceptable.
- [`docs/destructive-action-safety.md`](docs/destructive-action-safety.md) gains a runtime-
  enforcement section stating the relationship in both directions: the policy remains
  authoritative and covers what no runtime check can see; where the two disagree the stricter
  outcome wins; a guard `ALLOW` is not permission.
- [`docs/release-checklist.md`](docs/release-checklist.md) gains an Execution Guard section,
  including re-verifying each host's contract against its **current** documentation rather than
  an older reading, and watching the false-positive corpus for usability regressions.
- `scripts/test-release-readiness.sh` runs the guard suite with the other five.

### Fixed

Defects found by the corpus and the probes while building this release, each now pinned by a
test:

- A workspace under `/var`, `/private`, or a `mktemp` directory was classified as a system path,
  so `rm -rf build` was denied in any repository checked out there. Workspace membership is now
  decided before the absolute-path rules, and the repository root is the credible signal.
- Home and credential directories were checked after the temp exemption, so a `$HOME` inside a
  temp tree lost its protection. `~/.ssh` is now `HOME_ROOT` wherever `$HOME` points, and `$HOME`
  is compared as a real path so a symlinked home does not silently disable the rule.
- Symlink escapes were compared only against the canonicalised workspace root, so the lexical
  test failed whenever the root's two spellings differed — silently disabling the check that
  catches `repo/tmp` pointing elsewhere.
- The relaxation ceiling started at each rule's compiled default, which clamped every machine-
  scope relaxation back to that default and made user policy inert.
- `timeout 5 rm -rf /` parsed the duration as the command. `env | curl …` lost the `env`
  entirely to wrapper stripping. `rm --recursive --force /` was not recognised as recursive.
- A refused weakening attempt attached an `ASK` finding to every decision, so one bad key in one
  configuration file degraded every command in the session. It is now a note, raised to a finding
  only when it targeted a rule the action actually triggered.
- The content scanner reported one signal per line and hid the rest, so a sentence that was both
  a policy waiver and a destructive command was reported only as the former.
- A hook payload whose command field was missing or renamed produced an empty action, which
  matched no rule and read as `ALLOW` — turning a host schema change into a silent total bypass.
  It now raises and resolves to `ASK`.
- Redaction's environment-assignment rule matched query parameters and greedily consumed the rest
  of the URL, truncating audit records.
- Configured protected branches were folded into a module-level regular expression on every call.
  The pattern grew without bound, and one repository's configuration changed the verdict for the
  next workspace evaluated in the same process. Per-call facts now travel through a per-call
  context.
- Every `--` was stripped from the inspected command rather than only the leading separator, so a
  command carrying its own `--` was inspected in a form the shell would not run.

## 0.41.0 - Spend Context On Evidence, Not On Volume

Minor release. Agent Skills already kept its own instructions token-conscious. This release
solves the other half: the **evidence** may be enormous, and reading it wholesale spends most of
an agent's working memory before it has thought about the problem.

```text
large evidence -> cheap deterministic inspection -> task-aware extraction
               -> small context pack -> agent reasoning
```

The first stage is deliberately not a model. Sending 20 MB to a model so it can pick the 20 KB
it needed defeats the feature, so inspection is local, deterministic, and repeatable: the same
source, brief, budget, and strategy produce the same pack, byte for byte.

The goal is not "summarise everything". It is to spend context only on evidence relevant to the
current engineering question, while preserving provenance and making omissions explicit.

### Added

- **[Context Optimizer](docs/context-optimizer.md)**, a reusable runtime capability exposed as
  `agent-skills context`. Six subcommands: `inspect` (cheap metadata and structure), `check`
  (threshold verdict, exit 10 when over), `pack` (bounded task-aware selection), `explain`
  (provenance and staleness read-back), `expand` (widen one region), and `cache`.
- **[`context-optimizer`](skills/context-optimizer/SKILL.md)**, the ninth top-level skill and
  the user-facing entry point. It exists for the cases where judgement is the work — choosing
  the brief, deciding whether the pack answered the question, escalating when it did not. Every
  other skill calls the runtime directly instead, because dispatching an agent to shrink a file
  would add a whole agent's context to save some and would deepen the chain the depth cap bounds.
- **Seven type-aware strategies**, auto-detected by extension then by a bounded content sniff:
  `log`, `ci`, `sql`, `structured` (JSON/YAML/XML), `source`, `diff`, and `text`. Logs stream in
  one pass that records byte offsets and per-line features but never the text, so a
  gigabyte-scale log is affordable to look at; selected windows are read back by seeking.
- **Deterministic task-aware selection.** Weighted brief terms — anything carrying a digit
  outranks a qualified identifier, which outranks a plain word — plus severity, failure
  vocabulary, first-failure priority, cascade suppression, stack-frame proximity, bounded
  foreign-key expansion, and frequency discounting for terms that match almost everything. No
  embeddings and no vector database are required, and none are used.
- **Two kinds of repetition, handled differently.** A repeated line irrelevant to the brief is
  *collapsed* to a count; a repeated line that matches the brief is *sampled* — the first few
  and the last, with the count reported. The same log therefore compresses differently for
  different questions, which is the point.
- **Mandatory provenance.** Every fragment names its source, its line range or structural path,
  and every signal that selected it. For structured inputs the path is the provenance:
  `$.orders[3178]` locates a finding more precisely than a line number, and both are recorded.
- **Explicit omissions.** Ten omission kinds, each naming its scale and the command that
  reverses it. When the budget excluded material that was relevant, that is its own record with
  the highest-scoring exclusions named. Diff packs additionally carry a completeness line: this
  is evidence for where to start reviewing, **not** a complete review.
- **A hard character budget.** `--budget-chars` bounds the whole rendered pack, provenance
  included, because that is what the agent reads. Verified across 49 fixture-and-budget
  combinations. Characters rather than tokens: provider tokenisation differs, and making one
  provider's tokeniser a hard dependency to answer "how much context is this" is a poor trade.
- **The shared large-input rule**, in one place. Six consumer skills link it rather than
  restating it — `software-engineer`, `issue-investigator`, `code-reviewer`,
  `test-automation-engineer`, `manual-tester`, `delivery-planner` — each with a single clause
  naming its own commonest large input.
- **A measured default threshold**: 65,536 characters or 2,000 lines, whichever trips first. Of
  the 27 tracked scripts in this repository exactly one is larger than 64 KiB, so ordinary
  source files are not dragged through optimisation; and past 2,000 lines a wholesale read is
  already silently truncated by several hosts, which is worse than a pack that says what it
  omitted. Both bounds, plus the budget, the relation depth, and the read cap, are configurable.
- **A deterministic pack cache** keyed on source content hash, brief, strategy, strategy
  version, budget, and window options. An edited file cannot hit a pack built from the old
  bytes, and the stored hash is verified again on read. This is what stops a 100 MB log being
  recompressed for every fresh specialist agent in a chain.
- **[`scripts/test-context-optimizer.sh`](scripts/test-context-optimizer.sh)** — 105 checks over
  ten generated fixtures plus five mutation probes. Fixtures are generated rather than
  committed: they are large by definition, and shipping a 5 MB synthetic log to test
  large-input handling would miss the point.
- **Three evals**: [evidence survival](evals/context-optimizer-large-log-evidence.md),
  [safety and omissions](evals/context-optimizer-safety-and-omissions.md), and
  [routing and reuse](evals/context-optimizer-routing-and-reuse.md). Two scenarios are built so
  a ratio-maximising agent fails them.
- **[A worked example](docs/examples/context-optimizer-large-log.md)** and
  **[a security review](docs/security-review-v0.41.0.md)** covering the new trust boundary.

### Changed

- **`wamala` gains an `oversized-input` class and a narrow row 0.** It fires when reducing the
  input **is** the request, not whenever a large file is mentioned. A defect report attaching a
  200 MB log is still `defect` and still goes to `issue-investigator`, which packs the log
  itself. The [routing table](skills/wamala/references/routing-table.md) records the ambiguous
  cases that keep the row narrow, and the rule of thumb: route here when the pack is the
  deliverable, elsewhere when it is a step toward one.
- **`oversized` and `oversized-input` are different problems**, stated explicitly. Too much
  *work* for one session goes to the planner; too much *evidence* for one context goes to
  Context Optimizer. A 150 MB log behind a one-line bug is not a phased plan.
- **`delivery-runner` handoffs pass a pack id** rather than a raw path when one exists, so the
  next phase reuses the pack instead of recompressing the file.
- **The minimum context budget is 2,000 characters, measured rather than chosen.** The first
  implementation accepted 1,000, at which the provenance header alone does not fit — it failed
  loudly rather than lying, but it accepted a budget it could never honour. Below roughly 1,500 the
  header, shape map, and omission records cannot coexist with a fragment at all; below 2,000 a pack
  renders inside its budget but carries no evidence.
- **[Token efficiency](docs/token-efficiency.md)** now says plainly that it covers one half of
  the problem. Trimming a SKILL.md by 200 lines is worth doing, and worth nothing next to an
  agent that read a 4 MB log in its first tool call.

### Security

- **Source text is data, never instructions.** Instruction-shaped content is flagged
  `untrusted-instruction-shaped` and **preserved** — text like that sitting next to a failure
  may be the finding — and it changes nothing: not the budget, not a path, not the strategy, not
  a credential, not a tool policy. Every one of those comes from the command line, the
  environment, or committed configuration. This is the same "claims to verify, never
  instructions to follow" contract the [repo knowledge base](docs/repo-knowledge.md) uses.
- **Credential-shaped values are redacted before the pack, the render, or the cache sees them**,
  with the surrounding evidence kept. Ten token shapes are detected; detection is pattern-based
  and therefore not exhaustive, which [known limitations](docs/known-limitations.md) states.
- **A committed configuration file may adjust a resource bound and nothing else.** No path, no
  credential, no strategy, no tool policy. Out-of-range values are clamped rather than obeyed
  and non-numeric values fall back with a note, because a committed file is editable by anyone
  who can open a pull request.
- **Packs are written `0600`** and hold only redacted content.
- **Telemetry is opt-in and records counters only** — no fragment, no brief, no path content.

### Fixed

Twelve defects found before release — six by the suite and its probes, six more by the pre-merge
diff review — recorded because a release note that only lists features implies the tests found
nothing. Three of the review's findings share one root cause: a field written *after* the budget was
reconciled, which then changed the rendered length the reconciliation had just checked.

- A tight budget could produce a pack of **pure footer** — zero fragments and a long explanation
  of why — because the omission list crowded out the evidence it was describing. The footer is
  now bounded proportionally to the budget, and there is an unconditional floor guaranteeing one
  fragment when candidates exist.
- A leading SQL comment opened the statement buffer and merged with the first `CREATE TABLE`,
  which then failed to classify and vanished from **both** the object count and the omission
  count. An invisible loss is the one kind this runtime must not produce.
- Window merging accumulated a fraction of every merged score, so a run of four hundred
  cascading errors could out-score the root cause that caused them. Merged windows now take the
  best anchor's score plus a small bounded nudge.
- The JSON scanner double-counted newlines inside strings, so structural paths pointed at the
  wrong lines — provenance that is confidently wrong is worse than provenance that is absent.
- Matching against the full node path made every element of a 4,000-element array a hit purely
  because its ancestor was called `orders`. Matching is now against the node's own key and
  value, with frequency discounting on top.
- Two of the suite's own assertions passed for the wrong reason, matching omission-record
  previews rather than emitted evidence. Both now target the evidence specifically.
- The omission record that says "the four lines you are reading stand for forty" had no priority
  entry, so it ranked last and was hidden at every realistic budget — behind records about
  irrelevant health checks. A reader who does not see it can reasonably conclude there were four.
- The budget was non-monotonic: a 2,000-char budget emitted evidence where 2,500 emitted none,
  because a trim pass sized a fragment against an estimate of the footer that then moved.
- The rendered pack could exceed its budget by one character, because wall-clock time is measured
  after the budget is reconciled and `0 ms` is shorter than `46 ms`.
- `scripts/test-global-install.sh` asserted `removed 8 registration(s)` and broke on the ninth
  skill — a test failing for a reason unrelated to what it tests. Now derived from the skill count.
- `scripts/test-release-readiness.sh` still expected the `tech-lead` migration notice; the alias
  removal had updated only one of the two places that asserted it.

### Deprecations

- **The `tech-lead` alias is removed**, on the schedule [docs/versioning.md](docs/versioning.md)
  recorded when it was added in `v0.38.0`: three minor releases, then gone. From `v0.41.0` the
  old name is not recognised anywhere and is passed through as an unknown skill name rather than
  silently translated. The front-door suite's alias section was inverted rather than deleted,
  because the interesting property after a scheduled removal is that the old name is genuinely
  gone and is not quietly remapped to something else.

### Telemetry Review

`telemetry.py report --all` was run and is recorded verbatim in
[`eval-runs/v0.41.0/summary.md`](eval-runs/v0.41.0/summary.md). Two events total, both `completed`,
zero `stopped`, and **no `invoked` events at all** — so the counters are far too sparse to compare
per-skill health against v0.40.0. They therefore drove **no** skill change this release, which is
said here plainly: an unread counter is worse than no counter, because it looks like evidence. The
missing `invoked` events are the finding worth carrying forward, since the lifecycle wrappers are
supposed to emit one per run.

## 0.40.0 - Tests That Survive Refactoring

Minor release. Developer testing stops being a checklist item and becomes a set of judgements.
[`software-engineer`](skills/software-engineer/SKILL.md) now decides what behaviour a test protects,
where the unit boundary sits, which collaborators stay real, which test double is the least powerful
one that answers the question, and whether the behaviour is provable through output or only through
the interaction itself. [`code-reviewer`](skills/software-engineer/skills/code-reviewer/SKILL.md)
reviews those same decisions.

The rule this replaces was one line in the code-review checklist:

```text
External dependencies mocked, not called for real, in unit tests
```

Read literally — and an agent reads literally — "dependency" means anything injected into a
constructor, so the safe reading was to mock everything and verify every call. That produces tests
that pass while the behaviour is broken, because the stubs supply the answers the assertions then
check, and that break when a refactor moves a call without changing anything observable.

Agent Skills does not adopt Detroit/classical or London/mockist TDD. Both are understood, and the
question asked at each test is which one gives reliable confidence here with the least unnecessary
coupling. No universal test-first mandate was added either — the tests and the design that resulted
are judged, not the order they were written in.

### Added

- **[Developer testing](skills/software-engineer/references/developer-testing.md)**, a new
  `software-engineer` reference and the policy the rest of this release binds to. It covers choosing
  the unit, real collaborators versus doubles, the dummy/stub/fake/spy/mock table, state and output
  verification versus interaction verification, owned ports and adapter boundaries, refactoring
  resilience, test smells as design feedback, test-level selection, naming, coverage, and a worked
  mock-heavy versus behaviour-oriented example of the same test.
- **A unit is a behavioural boundary, not a class.** One pure function, one class, several
  cooperating domain objects, a small module, or a use case plus cheap in-process collaborators are
  all valid units, provided the test stays fast, deterministic, focused, isolated from external
  systems, readable, and informative when it fails. The governing question is what the smallest
  meaningful behavioural unit worth protecting is.
- **Six test-design decisions** in `software-engineer`
  [Phase 2.4](skills/software-engineer/SKILL.md): behaviour to protect, test level, unit boundary,
  real versus doubled collaborators, double type, verification style — plus the seventh question,
  whether the test is hard to write because the production design is wrong. Proportional by design:
  a sentence each on a small change, a paragraph where the regression risk is real. It does not
  replace the reproduce-before-fix gate; the failing regression test still comes first and still
  must fail on the parent commit.
- **A restructured [`test-quality` review
  profile](skills/software-engineer/skills/code-reviewer/SKILL.md#the-test-quality-profile)** with
  one shared layer and two specific ones. Shared fundamentals — named behaviour, meaningful
  assertions, determinism, isolation, readability, failure quality — apply to every test.
  Developer-test concerns cover unit boundary, real-versus-double choice, double type, verification
  style, refactoring resilience, adapter boundaries, test level, and design feedback. Automation and
  system-test concerns keep selector stability, condition-based waits, deterministic parallel-safe
  data, level appropriateness, and the green-washing rules. Unit-mocking scrutiny does not get
  applied to a UI automation diff, and selector rules do not get applied to a unit test.
- **A binding developer-test review check** in `code-reviewer`: any diff that changes tests gets the
  profile applied, in every review mode, with nine finding shapes covering implementation
  choreography, stubbed third-party internals, regression tests that pass while the behaviour is
  broken, call-only verification, wrong test level, unnecessarily doubled deterministic
  collaborators, setup that hides the scenario, framework bootstrapping for trivial logic, and
  method-shaped test names. They are shapes, not a list to emit.
- **Three eval files, ten scenarios**, all judged on the decision rather than on vocabulary:
  [unit boundary and double selection](evals/developer-testing-unit-boundary-and-doubles.md)
  (over-mocked service, legitimate external boundary, large fixture graph, unit-is-not-a-class),
  [third-party boundaries and test levels](evals/developer-testing-boundaries-and-test-levels.md)
  (deep SDK stubbing, integration-level regression), and
  [test verification quality](evals/code-reviewer-test-verification-quality.md) (refactor-fragile
  test, interaction that really is behaviour, coverage-driven tests, mock-heavy but valid
  orchestrator). Two of the reviewer scenarios contain correct mock-heavy tests: a reviewer that
  finds problems in all four fails as surely as one that finds problems in none.

### Changed

- **[Code review checklist](skills/software-engineer/references/code-review-checklist.md)
  testing section** rewritten. The single mocking line becomes a distinction between an external
  *process* boundary — network, third-party APIs, email/SMS, brokers, filesystem, clock, randomness
  — which is substituted, and an ordinary in-process collaborator that is deterministic, cheap, and
  owned, which is not. Being a constructor dependency is explicitly not a reason to double
  something. Added items for test level, least-powerful double, owned ports versus SDK internals,
  refactoring resilience, and difficulty-as-design-feedback.
- **`software-engineer` Phase 3.2** now requires each changed behaviour to have a test at the level
  that can detect its regression, deterministic owned collaborators to be real unless there is a
  stated reason, assertions on observable output or state where that proves the behaviour, and
  business logic to be tested against an owned port rather than a stubbed vendor chain. Test names
  describe the behaviour and its outcome.
- **Coverage is evidence, not proof.** High line coverage is not high confidence. Adding
  assertion-free tests to move a number is forbidden; where a gate is mandatory it is met honestly,
  and the engineer says so if meeting it required tests of low value. Existing project coverage
  gates are untouched.
- **Ownership made explicit.** `software-engineer` owns the tests that ship with a change — unit
  tests, the focused integration tests it needs, its regression tests.
  [`test-automation-engineer`](skills/test-automation-engineer/SKILL.md) owns the suite: broader
  regression automation, API/system/UI coverage, suite strategy, framework and CI concerns. An
  engineer does not need a second specialist to test their own code. Recorded in both skills, in
  [skill boundaries](docs/skill-boundaries.md), and in the README.
- **Three things `code-reviewer` must not do**, now guardrails: no finding against a mock, a stub,
  or an interaction assertion on principle; no counting of doubles, because there is no threshold;
  no requiring a testing school or test-first authoring as a condition of approval. Coverage is not
  accepted as evidence of test quality.

## 0.39.0 - Test Automation Is A Full Engineering Workflow

Minor release. [`test-automation-engineer`](skills/test-automation-engineer/SKILL.md) stops being
a skill that writes new tests and becomes one that owns an automated suite.

It can now maintain an existing suite through product change, triage a wall of CI failures into
product defects versus automation problems, investigate flakiness to a cause, prioritise an
automation backlog, move coverage to the level where it belongs, preserve requirement-to-test
traceability, and integrate stable coverage into CI — while routing product defects, unclear
behaviour, and exploratory work to the specialists that own them.

```text
Use Wamala to triage these 37 CI test failures and separate product defects from automation problems.
Use Wamala to fix the failing Playwright suite after this UI redesign.
Use Wamala to decide what of our regression pack should be automated, kept manual, or moved lower.
```

The strengths the skill already had are unchanged: the requirement-understanding gate before any
automation, lowest-appropriate test level, the unit/integration/API/contract/UI distinction, stable
fixtures and selectors, observable waits instead of sleeps, deterministic data, CI integration and
artifacts, the bounded `code-reviewer` `test-quality` loop, flake budgets, consumption of
manual-tester / product-owner / issue-investigator evidence, and the destructive-action floor.

### Added

- **Nine explicit task modes**, named before anything else runs and each mapped to the steps it
  actually needs: `new-automation`, `suite-maintenance`, `failure-triage`, `flake-investigation`,
  `automation-strategy`, `automation-backlog`, `coverage-gap-analysis`, `ci-integration`,
  `framework-evolution`. The mode is not decoration — it decides the workflow. Running the
  new-coverage workflow on "CI has 42 failures" produces 42 edits to tests that were correct, and
  that is the failure the modes exist to prevent.
- **Mandatory framework and repository discovery** whenever automation code will be read, changed,
  or added. Eighteen dimensions — runtime, frameworks, runner, assertions, fixtures, page objects,
  API clients, data builders, mocks, container dependencies, reporting, coverage, the CI command,
  tags, retry and quarantine config, parallelism, selectors, conventions — in
  [`references/framework-discovery.md`](skills/test-automation-engineer/references/framework-discovery.md).
  The binding rule is that the repository's stack wins unless there is evidence it is inadequate;
  a new framework needs a written tradeoff record and a named human owner before any migration.
  Common ecosystems are recognised on sight, and none is hardcoded into the workflow.
- **A failure taxonomy.** Every failure — or, correctly, every failure *cluster* — is classified as
  `PRODUCT_DEFECT`, `AUTOMATION_DEFECT`, `EXPECTED_PRODUCT_CHANGE`, `FLAKY_TEST`,
  `TEST_DATA_FAILURE`, `ENVIRONMENT_FAILURE`, `DEPENDENCY_FAILURE`, `CONFIGURATION_FAILURE`, or
  `UNKNOWN`, from named evidence, with a routing table per class. A red test is not evidence the
  test is wrong. Fifty failures behind one broken authentication fixture are one incident with one
  fix, not fifty test edits.
- **Flake diagnosis before repetition** — reproduce, isolate, classify, fix the cause, stability
  run, CI-equivalent run — with a cause list covering timing, data, isolation, surface, and
  environment, and a quarantine contract requiring reason, owner, linked follow-up, visible CI
  status, and a removal condition. Silent quarantine is forbidden.
  [`references/failure-triage.md`](skills/test-automation-engineer/references/failure-triage.md).
- **Backlog dispositions** — `AUTOMATE_NOW`, `AUTOMATE_LATER`, `KEEP_MANUAL`,
  `MOVE_TO_LOWER_LEVEL`, `REFACTOR_EXISTING`, `REMOVE_DUPLICATE`, `OBSOLETE`,
  `NEEDS_CLARIFICATION` — decided on ordinal evidence rather than an invented numeric score, plus
  active test-level optimisation for suites that have grown expensive.
  [`references/automation-backlog.md`](skills/test-automation-engineer/references/automation-backlog.md).
- **A suite-maintenance playbook** with the repairs that are actually damage — blanket timeout
  increases, `force: true`, swallowed failures, deleted assertions, blanket snapshot updates,
  retries until green, `sleep(5000)`, silent skips — each needing a specific written justification
  rather than "the suite was red". Test-data kinds and their guarantees, cleanup ownership, and
  parallel-safe identities are in the same reference.
  [`references/suite-maintenance.md`](skills/test-automation-engineer/references/suite-maintenance.md).
- **Requirement → scenario → automated check → CI evidence traceability**, persisted as a coverage
  map rather than scattered through test code as ticket comments. It exists to answer one
  question: why does this test exist, and what stops being protected if it is removed?
- **An `automation:` block in the shared
  [evidence pack](skills/software-engineer/references/evidence-pack.md#the-automation-block)** —
  one block on a file every skill already reads, rather than five new artifact formats. It carries
  the mode, the discovered stack, the coverage map, the triage result, the backlog dispositions,
  the stability result, what stays manual, and the next action, so a fresh agent can resume the
  work from disk. `test-automation-engineer` is its sole writer.
- **An `automation` class in [`wamala`](skills/wamala/SKILL.md) routing**, with four ordered rows
  that keep the ownership boundaries intact: unagreed behaviour goes to `product-owner`, a failing
  test that points at a product defect goes to `issue-investigator`, a scenario too unstable to
  assert goes to `manual-tester`, and everything else about the suite goes to
  `test-automation-engineer`. Two new chains cover a wall of CI failures and a suite broken by a
  product change. The routing table gains the judgement calls: why "the regression suite takes 70
  minutes" is automation work while "the dashboard is slow" is a product target, and why a wall of
  failures is always one triage step rather than a fan-out.
- **Three behavioural evals** —
  [modes and discovery](evals/test-automation-engineer-modes-and-discovery.md),
  [failure triage](evals/test-automation-engineer-failure-triage.md), and
  [flake, ambiguity, and safety](evals/test-automation-engineer-flake-ambiguity-and-safety.md) —
  covering twelve scenarios: new UI automation, API-level choice, a suite broken by a UI refactor,
  product defect versus automation defect, an asynchronous flake, fifty failures with one cause, a
  backlog decision, an expensive e2e suite, ambiguous behaviour, an unsafe environment, an unknown
  framework, and an authenticated sandbox resource. They test decisions rather than the presence of
  wording. [`evals/wamala-routing.md`](evals/wamala-routing.md) gains two automation requests.

### Changed

- **`scripts/test-front-door-skill.sh` now checks routing rows as an ordered subsequence, not for
  equality.** The equality check was written for a rename, where any routing change was a defect.
  Kept as-is it would have frozen the table: this release adds rows deliberately. Every routing row
  from `v0.37.0` and from `v0.38.0` must still be present, verbatim, **and in the same relative
  order** — the table is first-match-wins, so its order is its semantics. Row numbers are
  normalised out, because renumbering on insert is not a contract change.

  An intermediate version of this compared the two sets with `comm` on sorted input. Pre-merge
  review caught that it allowed reordering: moving the automation catch-all row above the three
  boundary rows inverted exactly the ownership those rows exist to protect, and the suite still
  passed. Set comparison is the wrong tool for an ordered contract.

  Ordered subsequence still cannot see a row **inserted above** an existing one, which shadows it
  under first-match-wins while leaving every baseline row present and in order. Five
  `assert_class_owners` checks close that: for `automation`, `review`, `defect`, `question`, and
  `validation`, the owners of the rows mentioning that class, in table order, must be exactly the
  expected sequence. Five mutations were each shown failing and then reverted — deleting a row,
  changing an owner, reordering two baseline rows, moving the catch-all above the boundary rows,
  and shadow-inserting a `review` row owned by `software-engineer`.
- **Release-readiness section 6b is pinned to `v0.37.0`** (`AGENT_SKILLS_RENAME_TAG`), the release
  the front-door rename came from. It read the previous tag from `git tag --sort=-v:refname`, so
  the moment `v0.38.0` shipped it started looking for `skills/tech-lead` in a release that no
  longer had it — two failures, three downstream assertions made vacuous, and a check that had
  silently stopped testing the migration it was written for. Section 6, the generic previous-tag
  upgrade, still floats. Both scripts now document their tag environment variables in their usage
  headers.
- **The `test-automation-engineer` compatibility field** now describes the three current execution
  modes — `global`, `in-repo`, and the legacy `local-workspace` — and points at the generic access
  resolver. It previously advertised the pre-v0.37.0 `setup.init + .env` model as one of two modes.
  Its pre-flight no longer tells the agent to look for `.env` in a parent workspace folder; it
  resolves access on demand with `agent-skills access resolve`, and never asks for a secret in
  conversation. The same correction was applied to `wamala`, whose compatibility field carried the
  older two-mode wording.
- **The output contract is keyed by mode.** `## Automation Backlog`, `## Failure Triage`, and
  `## Validation Run` join the menu; a triage run has no `## Test Design` and a backlog run has no
  `## Implementation Plan`. `## Validation Run` distinguishes what was actually run, the observed
  stability, and whether a CI-equivalent command was verified — a run that did not happen is never
  reported as one.
- **[docs/skill-boundaries.md](docs/skill-boundaries.md)** states the widened ownership and, more
  importantly, what stays outside it: root-cause analysis, product intent, exploratory testing, and
  fixing the product. A failing test that exposes a real bug is routed, not patched.
- The README skill entry, [starter prompts](docs/starter-prompts.md), and the
  [regression-plan example](docs/examples/test-automation-engineer-regression-plan.md) now cover
  maintenance, triage, flake work, backlog decisions, and suite runtime alongside new coverage.

## 0.38.0 - Meet Wamala

Minor release. The single front door to Agent Skills has a name: **`tech-lead` is now `wamala`**.

Wamala is the interface to the specialist engineering team. Give it the work, and it determines
who should own the next step, dispatches fresh-context specialists, and keeps multi-step delivery
aligned through persisted artifacts. The specialist skills keep their role-based names and stay
directly invocable — nothing has to come through Wamala.

This is an identity change, not a redesign. The routing table, the requirement-understanding gate,
fresh-context dispatch, one-owner-per-step, artifact verification, the bounded retry, the depth cap
of two, the six-dispatch cap, and every stopping condition are unchanged, and a test now proves
that by diffing this release's routing rows against `v0.37.0`.

```text
Use Wamala to investigate why invoice search loses its filter on page 2.
Use Wamala to take this feature from requirement to delivery.
```

### Changed

- **`skills/tech-lead/` is now [`skills/wamala/`](skills/wamala/SKILL.md)**, declaring
  `name: wamala` and heading `# Wamala`. There is exactly one skill directory and one discoverable
  front door; the old directory is not kept as a copy, because two discoverable entry points drift
  apart silently and the drift is invisible until someone invokes the stale one.
- **The `wamala` description** now leads with the front-door model — arbitrary software-delivery
  request in, routing and fresh-context specialist dispatch out — rather than describing a role, so
  it is discoverable from a natural request.
- **[`evals/wamala-routing.md`](evals/wamala-routing.md)** and
  **[`docs/examples/wamala-routing.md`](docs/examples/wamala-routing.md)** renamed from their
  `tech-lead-` predecessors. The scenarios themselves are unchanged.
- **The README opens with the entry-point model.** A `## Wamala` section states what it is and
  shows the two canonical starter prompts before the catalogue.
- Active references across the README, docs index, starter prompts, quickstart, skill boundaries,
  review loops, installation, roadmap, examples, evals, CI, and the validator registry now name
  `wamala`. Historical material — release notes for `v0.36.0` and `v0.37.0`, the `v0.36.0` eval
  run, the router design plan, and the `v0.37.0` security review — still says `tech-lead`, because
  it was true when written.

### Added

- **Ownership-aware reconciliation of stale host registrations.** `agent-skills install` now
  removes registrations it owns whose skill no longer exists in the release being installed, so an
  upgrade from `v0.37.0` ends with `wamala` and no dead `tech-lead` entry in any host directory.
  The predicate is narrow by construction: an entry is pruned only when it is a symlink we wrote
  **and** its literal target's parent is the canonical skills directory. A directory the user
  created, or a link into their own tree, fails both halves and is left alone. `agent-skills
  verify` now reports such an entry as a failure with the command that fixes it. The mechanism is
  generic — nothing in it names `tech-lead` — so the next rename is covered too.
- **A bounded deprecated-name alias.** `agent-skills start-task --skill tech-lead` and
  `finish-task --skill tech-lead` resolve to `wamala` and print
  `tech-lead was renamed to wamala; using wamala` on stderr. It is a lifecycle-CLI alias only: no
  second skill directory, nothing registered under the old name, and no host discovers it. The
  table lives in [`scripts/task-context.sh`](scripts/task-context.sh) and its removal release is
  recorded in [docs/versioning.md](docs/versioning.md) — `v0.41.0`. A new **Deprecations** step in
  the [release checklist](docs/release-checklist.md) makes retiring it part of that release.
- **[`scripts/test-front-door-skill.sh`](scripts/test-front-door-skill.sh)** — 50 assertions
  covering the identity, the absence of a second front door, the specialists keeping their
  role-based names, routing-contract equivalence against the `v0.37.0` tag (skipped, not silently
  passed, when the tag is not fetched), the fourteen behavioural clauses, `start-task` and
  `finish-task` with `--skill wamala`, the deprecated alias end to end, and the rule that active
  documentation no longer advertises the old name. Wired into CI and release readiness.
- **Migration coverage in [`scripts/test-global-install.sh`](scripts/test-global-install.sh)** —
  sixteen assertions upgrading a `v0.37.0`-shaped install in place: `wamala` registered,
  agent-skills-owned `tech-lead` removed, a user's own `tech-lead` directory and a user symlink of
  that name both preserved, the prune idempotent across reruns, and `verify` reporting an
  unmigrated registration. All four of the assertions that depend on the new mechanism were shown
  failing with it disabled.
- **Section 6b in [`scripts/test-release-readiness.sh`](scripts/test-release-readiness.sh)** — the
  same upgrade against a real `v0.37.0` worktree, including the alias through the installed CLI.
- **A deprecated-skill-names section in [docs/versioning.md](docs/versioning.md)** stating the
  rename policy: one directory, one discoverable name, a CLI alias with a removal release.

### Fixed

- `agent-skills verify` previously reported nothing about a registration whose skill had been
  renamed away. It only enumerated the skills the current release ships, so a stale entry in a host
  directory was invisible to the tool whose job is to find exactly that.

## 0.37.0 - Install Once, Use Everywhere

Minor release, and the largest structural change since the skills themselves. `agent-skills` stops
being a thing you configure *around each workspace* and becomes a thing you install *once on a
machine*. It also closes the three items
[the v0.36.0 plan](docs/plans/2026-09-learning-voice-and-router.md) deferred pending a decision:
keychain credentials, the duplicated config surface, and splitting `setup.init`.

Designed in
[`docs/plans/2026-09-global-install-and-access-resolver.md`](docs/plans/2026-09-global-install-and-access-resolver.md),
including what was rejected and why.

**The user-facing model:**

```text
Install once. Use from any local project. Configure external access only when needed.
```

### Added

- **Machine-global installation.** `./setup.init` now installs to `AGENT_SKILLS_HOME`
  (default `~/.agent-skills`) and registers the skills with every supported agent host on the
  machine. Enter any repository — one you already have or one you clone next year — and the skills
  are there. No per-workspace setup, no `.skills` symlink, no sibling `agent-skills` checkout.
- **[`bin/agent-skills`](bin/agent-skills) — one stable entry point** resolvable from any directory.
  `install`, `verify`, `doctor`, `update`, `check-updates`, `uninstall`, `hosts`, `migrate`,
  `start-task`, `finish-task`, `project`, `access`, plus `memory`, `knowledge`, `blackboard`,
  `org-memory`, `telemetry`, `plan-next`, `locate-config`, `auth-preflight`, `promote-rules`,
  `outcome`, and `github-access`. Every helper is reachable through it, so no skill has to guess
  between `scripts/`, `agent-skills/scripts/`, and `.agent-skills/scripts/` — the v0.36 instruction
  was to try all three, which only worked when the clone happened to sit beside the current
  directory.
- **[`lib/hosts.registry`](lib/hosts.registry) — data-driven host adapters.** Nine hosts, each one
  row: Claude Code, the vendor-neutral `~/.agents/skills` directory, Codex, Cursor, GitHub Copilot,
  Kiro, JetBrains AI Assistant, Windsurf, Continue. Adding a host is one line, which matters
  because Agent Skills support is still moving.
- **[`scripts/access.py`](scripts/access.py) — one generic access resolver**, documented in
  [`docs/access-resolution.md`](docs/access-resolution.md). Nothing about Jira, Confluence, Sonar,
  GitHub, a database, or an internal API is compiled in: the caller supplies the service name and
  the field names it needs, so a skill can ask for a service that did not exist when the installer
  ran. Credentials are **identities, not projects** — `work-jira`, `personal-github`,
  `production-readonly-db` — so several repositories share one and one repository can use several.
- **OS-native secret storage.** macOS Keychain, Linux Secret Service, then an explicit
  permission-restricted file fallback that is always reported, never silently substituted for a
  store that previously worked, and deliberately not encrypted — an encrypted file beside its own
  key would be theatre.
- **[`scripts/project-context.py`](scripts/project-context.py) — progressive inference.** Git root,
  remote, base branch, stack, build system, package manager, commands, and CI, each reported with
  the source it came from. Anything that could not be established safely lands in
  `needs_confirmation` rather than being asserted.
- **`agent-skills migrate`** — read-only guidance off a pre-v0.37.0 workspace, plus an opt-in
  `--remove-obsolete` that removes only `.skills` and `.agent-skills.lock`.
- **`agent-skills uninstall`** — removes only paths this project owns. Skills you installed
  yourself survive, the source clone is untouched, and secrets in an OS keychain are never removed
  implicitly.
- **`AGENT_SKILLS_STRICT_BINDING`** — for a machine holding several customers' identities, requires
  an explicit binding rather than using a lone compatible one.
- **[`docs/security-review-v0.37.0.md`](docs/security-review-v0.37.0.md)** — a recorded,
  threat-by-threat review with each item labelled probed, reasoned about, or unproven.
- **Three new test suites**: [`scripts/test-global-install.sh`](scripts/test-global-install.sh)
  (78 assertions), [`scripts/test-access-resolution.sh`](scripts/test-access-resolution.sh)
  (77 assertions), and [`scripts/test-release-readiness.sh`](scripts/test-release-readiness.sh)
  (59 checks, including a real upgrade from the previous release tag).
- **Four new evals**: a zero-config repository, an unknown future service, a repository that tries
  to claim credentials it was not given, and legacy workspace migration.

### Changed

- **Setup asks for nothing.** No Jira, Confluence, Sonar, GitHub, database, cloud, or API
  credential; no project keys; no organisation; no deployment environments; no list of repositories
  you might work on. Installation, project configuration, and authentication are three separate
  concerns, and `setup.init` now owns only the first. CI asserts that a clean install mentions no
  credential and writes no credential state.
- **A repository with no configuration is a normal case.** Mode detection used to end in a hard
  stop when neither `${WORKSPACE_ROOT}/.env` nor a committed `.agent-skills.yml` existed. It now
  ends in `global` mode with inference only, so planning, engineering, review, and testing all work
  on a fresh clone. The agent stops only when a specific task needs a specific fact that cannot be
  inferred safely.
- **`setup.init` is a thin front-end** over [`lib/install.sh`](lib/install.sh) rather than growing a
  second large block of logic.
- **Skill-source resolution order is now total** — see
  [`docs/skill-source-resolution.md`](docs/skill-source-resolution.md). The old "two sources match
  and none is configured, stop and ask" rule is **removed**: every rule now has strictly higher
  precedence than the next, so there is always a first match and nothing to ask about. Keeping a
  rule that can no longer fire would teach agents to stop when they should proceed. Drift detection,
  which was always the valuable part, is kept and moved onto the install manifest.
- **All ten `SKILL.md` preflight blocks** call `agent-skills start-task` / `agent-skills finish-task`.
- **The cache root anchors at the git root** rather than `$PWD` when there is no legacy workspace, so
  running a skill from a nested directory no longer scatters `.cache` folders through the tree.
- **`doctor` reports the global install, execution mode, and credential-store backend** — and still
  prints no secret value.
- **Hook templates call the global command**, so there is no clone path to substitute.
- **`docs/auth-discovery.md` is now framed as a service-specific example** on top of the generic
  resolver rather than as the architecture. Jira and Confluence remain examples.
- **VS Code and GitHub Copilot have native skill discovery.** The prior documentation said they did
  not; that is now obsolete and corrected.
- **`.env.example` is marked as the legacy workspace template.** It still works and is still
  discovered; it is no longer the primary configuration surface.

### Security

- **A committed file can never select a credential identity, nor route one.** `.agent-skills.yml` is
  checked into a repository, so from the resolver's point of view it is attacker-controlled. It may
  declare *what* a service is; its `credentials:` block is never read. `.agent-skills.local.yml` is
  honoured only when **git confirms it is untracked**, verified rather than inferred from the
  filename, and refused outright when git cannot answer.
  Blocking *selection* turned out not to be sufficient, and a pre-merge review of this release's own
  diff proved it: because resolution fills fields independently, a repository `.env` could supply
  `host` while a machine identity supplied `token`, aiming a corporate credential at an
  attacker-chosen endpoint and reporting `resolved` — without ever naming an identity. Every
  credential source inside a repository is now tracked-checked, and a repo-supplied host that
  disagrees with the identity's recorded `resource` refuses the identity and reports a `security:`
  finding. Both holes are pinned by tests confirmed to fail against the pre-fix code.
- **Secrets leave plaintext `.env` behind.** A credential that is genuinely needed goes to the OS
  credential store. Metadata — profile name, service, resource, account, field names, timestamps —
  lives in user configuration at mode `0600`; values never do.
- **No secret in any output, in any mode.** Verified with a canary value across `profiles`,
  `profiles --json`, `backend`, `backend --json`, `check-permissions`, `resolve`, `resolve --json`,
  and the metadata file.
- **No secret is ever requested in conversation.** Hidden terminal input, the OS store flow, OAuth
  or MCP, or a session environment variable. With no terminal the resolver refuses and explains why
  rather than asking an agent to relay a value.
- **Resolution is not authorization.** Every result restates it, because finding a credential is
  exactly the moment the distinction gets lost. The
  [destructive-action safety policy](docs/destructive-action-safety.md) is unchanged.
- **The installer never touches what it does not own.** A link is ours by **location** (inside the
  install root we created) or by **literal target** (a registration pointing back into it). Anything
  satisfying neither is left pointing where it was and reported, including a *dangling* link — a
  broken link is still the user's data, and a link to an unmounted volume is not a free slot. An
  unmanaged path at a canonical location makes the install refuse rather than replace it.
- **Names are rejected, not sanitised.** Eight hostile profile and service names were probed and
  refused, with no injection artifact created. One transformation is applied and now documented
  precisely: case-folding, so `Work-Jira` and `work-jira` are one identity.
- **Three findings raised and fixed; two residual risks accepted and documented** with controls and
  measurements. One finding came from the review itself, two from a pre-merge review of the diff after
  the release was already green. The security review records all of it, including the fact that its
  own first probe of the critical criterion passed for an unrelated reason and therefore proved
  nothing.

### Fixed

- **`setup.init` discarded an inherited `WORKSPACE_ROOT`** before mode detection ran, so
  `WORKSPACE_ROOT=... ./setup.init --update` silently switched a legacy user to a global install and
  wrote into their real home directory. It also made the credential-preservation regression test
  pass vacuously, because the managed block was never regenerated.
- **Ownership of a host registration was decided by fully resolving the symlink**, so once the source
  clone was moved or deleted, `uninstall` no longer recognised its own links and orphaned them.
  Ownership now also checks the literal link target, which is what survives a broken chain.
- **A dangling symlink at a managed path could not be repaired**, because it was treated as a
  conflict. Repair is now driven by ownership: a link inside the install root, or one whose literal
  target points back into it, is replaceable even while broken. A dangling link that is neither stays
  put.

Found by a pre-merge review of the release diff, after every suite was already passing:

- **`agent-skills install --hosts` looped forever, printing nothing.** `--hosts`, `--source`, and
  `--branch` used `shift 2`, which shifts nothing when the flag is the last argument, so the parse
  loop re-read it indefinitely. The same three flags in `setup.init` exited 1 with no message. Every
  flag taking a separate value now fails with a reason.
- **A missing `lib/hosts.registry` or missing `python3` reported success.** Install registered
  nothing, wrote no manifest, printed "installed globally", and exited 0 — after which every
  manifest-dependent command reported the machine as not installed. Both are now prerequisites checked
  before anything is written, and the manifest is verified before the success banner.
- **`./setup.init` and `./setup.init --update` silently migrated a legacy workspace.** The legacy
  workspace was detected only under `--verify`, so the same machine answered "legacy" for `--verify`
  and "global" for the command v0.36 documented for updates. Legacy detection now applies to every
  command; moving to the global model is opt-in via `--global`. The global path also no longer sources
  a legacy `.env`, which could otherwise redirect `AGENT_SKILLS_HOME` or `PATH`.
- **`agent-skills verify` could never go green after a name collision.** Install deliberately preserves
  a user's own same-named skill; verify counted that as a broken registration and exited 1. Verify now
  distinguishes "ours but broken" from "yours, left alone".
- **A resolution via an authenticated tool reported no fields at all.** `status: resolved` came back
  with `fields_present` and `fields_missing` both empty, so a caller branching on the latter concluded
  it held a host and a token. The probes also matched on service name alone, so a `gh` session for
  github.com "resolved" a GitHub Enterprise host. Fields are now populated, and a probe that cannot be
  shown to serve the requested resource no longer short-circuits.
- **Task scratch dirtied every repository it ran in.** `start-task` created `.cache/` at the repo root
  with nothing ignoring it, so an agent running `git add -A` would commit ticket notes and
  investigation state. The entry now goes in `.git/info/exclude`: local to the clone, never committed,
  and no edit to a tracked `.gitignore`.
- **A profile split across two secret stores lost one of them.** `backend` was a single scalar
  overwritten by the most recent write, so an earlier secret became unreadable *and* undeletable —
  `forget` looked in the wrong store. Storage is now recorded per secret field.
- **`access import-legacy --apply` overwrote an existing identity** and read in-repo files without a
  tracked check. A clash now refuses and points at `--force`.
- **`migrate --remove-obsolete` deleted `.skills` on filename alone**, the one deletion in the release
  that did not verify the target was ours. It now checks ownership first.
- **A committed `project.build` was the one value an agent was told it need not confirm.** Committed
  build and format commands are executable and editable by anyone who can open a pull request, so they
  are now listed under `needs_confirmation`. Descriptive fields are unchanged.
- **A bare `./setup.init --yes` on an existing legacy workspace erased its own credentials.** The
  managed-block writer emits empty strings for any service whose mode resolves to "no", so "no" meant
  *erase* rather than *leave alone*, and a non-interactive rerun cleared `JIRA_HOST`, `JIRA_LOGIN`,
  and `JIRA_API_TOKEN` from inside the block. `--update` was unaffected because it already opted
  populated services back in; that logic is now shared, and honours an explicit `--no-jira` so
  removing a service still works. This predates v0.37.0, and was found because the routing fix above
  sends a bare run down the legacy path instead of quietly migrating it.

### Telemetry review

Required by the [release checklist](docs/release-checklist.md#telemetry-review). The report, verbatim:

```json
{
  "total_events": 2,
  "skills": {
    "software-engineer": { "completed": 1 },
    "manual-tester": { "completed": 1 }
  },
  "unknown_events": {}
}
```

**Two events, unchanged from the v0.36.0 baseline of two.** The counters did not move, so **no
change in this release traces to a telemetry finding.** Stated rather than glossed: an unread
counter is worse than no counter, because it looks like evidence. The baseline for the next release
remains 2 events, and the question it answers is whether the lifecycle wrappers are running at all.

### Migration

Existing installs keep working. The resolver still discovers a legacy `.env`, `.env.local`, and
`.jira-config.yml`; `./setup.init --legacy-workspace` still writes the old layout; and an inherited
`WORKSPACE_ROOT` pointing at a directory with a `.env` still selects it.

```bash
cd agent-skills && git pull && ./setup.init
agent-skills verify
agent-skills migrate
```

Nothing is deleted, and no secret moves without an explicit request.
`agent-skills access import-legacy` is read-only until `--apply`. Full path:
[installation.md](docs/installation.md#coming-from-the-pre-v037-workspace-layout).

### Cloud and remote agents

Unchanged, and the distinction is now stated plainly rather than blurred: a cloud agent runs on a
machine that cannot read your home directory, so the global install does not reach it. Those
environments continue to use the in-repo mechanism — a committed `.agent-skills.yml` plus vendored or
referenced skills. Cursor's Cloud Agents are the one partial exception, for `~/.cursor/skills` only,
with sync explicitly enabled.

## 0.36.0 - Repo-Resident Knowledge, Human Voice, And A Single Entry Point

Minor release, and the largest since the Company Brain landed. It answers four questions:
where accumulated knowledge should live, how written output should sound, how to stop having
to pick a skill by hand, and what setup should actually be doing.

Planned and reviewed in
[`docs/plans/2026-09-learning-voice-and-router.md`](docs/plans/2026-09-learning-voice-and-router.md).

### Security

- **`setup.init` did not always create the `.gitignore` it claimed to.**
  `update_workspace_gitignore` only created a missing `.gitignore` when the workspace root was
  already a git repository — and the parent workspace folder normally is not. The skip branch
  printed nothing, so the script's own security header ("generated `.env` and `.jira-config.yml`
  are added to `.gitignore`") did not hold in the default layout. Harmless while that folder
  stays unversioned; a plaintext-token exposure the moment anyone ran `git init` there. The
  ignore file is now written unconditionally.
- New `assert_env_is_ignored` verifies that claim instead of assuming it, at first run and on
  every `--verify`. A stored token in an unignored `.env` is now a hard verification failure,
  not a silent condition.
- `check_url_reachable` no longer passes `curl -k`. A probe that ignores certificate errors
  cannot distinguish a MITM proxy from the real host.
- `scripts/github-access.sh` sets `GIT_TERMINAL_PROMPT=0` and an SSH `BatchMode`, so a machine
  without a credential helper fails fast instead of blocking on an interactive prompt inside
  what the agent expects to be a non-interactive probe. It also uses `mktemp` rather than a
  guessable `/tmp/<pid>` path for captured account names.

### Added

- **Repo-resident knowledge base** — [`scripts/knowledge.py`](scripts/knowledge.py) and
  [`docs/repo-knowledge.md`](docs/repo-knowledge.md). A fourth memory tier that lives at
  `<repo>/.agent-skills/knowledge/`, is **committed**, and is reviewed in a pull request.
  Project memory lives in a gitignored cache, so what an agent learned survived sessions on one
  checkout and nothing else — a fresh clone, a CI runner, or a teammate started from zero.
  Holds curated facts in `project.md` and atomic **confidence-scored lessons** in `lessons/`
  (confidence clamped `0.3`-`0.9`, raised on independent re-confirmation, lowered on
  contradiction, decayed after 90 unconfirmed days).
- **Budgeted, ranked recall.** `knowledge.py read --brief "<task>" --budget-chars N` ranks by
  relevance to the brief first, then confidence, then recency, and **reports what it withheld**
  rather than silently truncating. The tier built to save context must not become the thing
  consuming it.
- **`knowledge.py doctor`** — validates schema, confidence range, id/filename agreement,
  duplicate ids, staleness, and scans for committed secrets **and entries shaped like
  instructions to the agent**. A committed knowledge file is a prompt-injection surface: anyone
  who can open a pull request can write text every future agent will read.
- **[`docs/writing-voice.md`](docs/writing-voice.md)** — the contract for everything a skill
  writes for a human reader: code comments, commits, PR bodies, tracker comments, document-store
  pages. Per-artifact registers, an explicit list of banned AI tells, and an **honesty boundary**
  stating that voice rules never justify hiding uncertainty. Enforced in every `SKILL.md` the
  same way output discipline is, and pinned by
  [`evals/writing-voice-human-tone.md`](evals/writing-voice-human-tone.md).
- `writing.ai_attribution` (`none` | `trailer` | `footer`) and `writing.voice_reference` in
  `.agent-skills.yml`, plus `WRITING_AI_ATTRIBUTION` / `WRITING_VOICE_REFERENCE` in `.env`.
  Default `none`. Disclosure is an operator policy decision, not a skill default.
- **New top-level skill `tech-lead`** — the single entry point. (Renamed to
  [`wamala`](skills/wamala/SKILL.md) in v0.38.0.)
  Classifies any request, runs the requirement-understanding gate, picks the one skill that owns
  the next step, and **dispatches a fresh empty-context agent**. Drives multi-specialist chains,
  verifying each step from persisted artifacts before advancing. Like `delivery-runner` it
  dispatches rather than invokes, so the depth-cap-of-two review bound holds inside each step and
  the lead never appears in that chain. Hard cap of six dispatches; nine documented stop states.
  Direct invocation of every other skill stays first-class.
- **[`scripts/doctor.sh`](scripts/doctor.sh)** — one capability report answering "what can I
  actually do here?". Aggregates the four diagnostics that already existed but never ran together
  (`--verify`, auth preflight, GitHub ladder) plus tool detection, build-tool inference from the
  repo manifest, Docker daemon reachability, and MCP availability. `start-task.sh` prints it as
  step 4, so skills plan around what exists instead of discovering it mid-task. Never prints a
  secret value, only whether one resolves.
- **[`docs/mcp.md`](docs/mcp.md)** — the MCP position. This repository ships and enables nothing;
  what it defines is the binding five-step tool-preference order, a recommended minimal server
  set, and the argument that the real case for MCP here is **authentication** (OAuth instead of
  plaintext tokens) rather than capability. Includes the Atlassian Cloud versus Data Center
  caveat that decides whether that applies.
- **[`docs/lifecycle-preflight.md`](docs/lifecycle-preflight.md)** — the full contract behind
  `start-task.sh` and `finish-task.sh`, extracted from nine near-identical copies.
- **Optional hook templates** in [`hooks/`](hooks/README.md) for Claude Code, Kiro, and any host
  that can run a shell command on session start and stop. Templates, not requirements: nothing
  needs them and no skill behaves differently without them. They exist because a markdown
  instruction is probabilistic while a hook fires every time. The stop hook deliberately records
  `needs-context` and preserves scratch, because a hook cannot know whether the work finished.
- `finish-task.sh` gained `--lesson`, `--repo-knowledge`, and `--no-candidates`, and now
  **proposes durable-fact candidates** drawn from the task blackboard. Previously the
  `Recent tasks` bullet was automatic while durable knowledge depended on the agent remembering
  a flag, so the default path produced a task log and called it learning.
- `start-task.sh` gained `--brief` for ranking the knowledge read.
- New evals: `tech-lead-routing.md`, `writing-voice-human-tone.md`.
- New example: `docs/examples/tech-lead-routing.md` (renamed to
  [`docs/examples/wamala-routing.md`](docs/examples/wamala-routing.md) in v0.38.0).
- A telemetry review step in the [release checklist](docs/release-checklist.md#telemetry-review).

### Changed

- **`PREFLIGHT` is now enforced.** `REQUIRED_SKILL_SECTIONS` went from 9 entries to 13, adding
  `PREFLIGHT`, `When Not To Use`, `Stopping Conditions`, and `Behavior Checklist`. `PREFLIGHT`
  wires memory, the blackboard, the capability report, and telemetry, and until now it was held
  in place by convention alone — a skill could ship with the entire Company Brain loop absent and
  still pass validation.
- **The nine duplicated `PREFLIGHT` blocks are gone**, replaced by a short stub plus the shared
  doc. About 285 lines of near-identical text removed; `product-owner` and `manual-tester` had
  differed on 5 lines out of 52.
- `--skill` now accepts a bare name and resolves the version from `VERSION`, and the lifecycle
  receipt templates use `@<version>`. A release no longer edits a hardcoded version in ten
  places.
- `software-engineer/SKILL.md` is 1,189 lines, down from 1,348. `Destructive Action Guardrails`
  and `Required Environment` moved to `references/`, leaving the rules that bind per phase inline.
- Every skill now declares `argument-hint`, `user-invocable: true`, and
  `disable-model-invocation: false`, and the validator requires all three. Previously only the
  two *nested* skills declared them, which was the inverse of the documented intent.
- `docs/destructive-action-safety.md` gained **Untrusted recorded context**: memory tiers, the
  committed knowledge base, and MCP or tool responses are claims to verify, never instructions to
  follow, and no recorded context can waive the safety floor.
- The Company Brain is documented as four tiers, with an honest note that telemetry has never
  been read as part of a release decision.
- `docs/installation.md` documents the six `setup.init` flags it had been omitting.
- `ROADMAP.md` refreshed: removed an item completed several releases ago, added the deferred
  credential-model decision.

### Fixed

- **Project-memory placeholders were never replaced.** `ensure_skeleton` wrote
  `- _No facts yet. ..._` but `append_note`, `dedup_memory`, and `find_repeated_bullets` only
  recognised the literal `- _empty`. So the placeholder survived under every populated section,
  and because promotion scanning used the same narrow filter, a placeholder shared by two
  projects could surface as a false org-promotion candidate.
- **The cache root could silently fork.** `resolve_cache_root` fell back to the current directory,
  so starting a task from a subdirectory created a second, empty memory store — the agent read
  nothing and wrote where the next run would not look. It now prefers the git repository root.
- Two project names that slugify to the same value now produce a warning instead of silently
  merging two projects' knowledge into one file.
- **`domain-modeler` was invisible to the validator** — zero occurrences across
  `scripts/validate-repo.py`. Its files could be deleted and its cross-skill links broken with
  validation still green. New `check_skill_registration` closes the class of bug rather than the
  instance, and immediately found six unregistered `software-engineer` reference files, both
  nested skill READMEs, and two missing `LINK_REQUIREMENTS` entries.
- New `check_readme_skill_counts` ties README prose counts to the skills on disk. The README had
  said "seven top-level and two nested" in one place and "eight specialist skills" in another.
- **Two checks in `run-evals.py` were dead and reported as passing.** `EXPECTED_SECTIONS` was an
  empty tuple, and the `Expected Skills:` check looked for an inline line while the corpus uses a
  `## Expected Skills` heading — it matched 0 of 32 files. The skill-declaration check is now
  live and hard-failing, every eval declares the skills it exercises, and heading drift
  (`Pass / Fail Checklist` versus `Pass/Fail Checklist`) is normalised so matching is exact.
- `scripts/delivery-run-next.py` is executable, like every other script in `scripts/`.
- `evals/all-skills-lifecycle-compliance.md` was missing `delivery-runner`.

### Deferred

Three items from the plan are **not** in this release because they need a decision first, and one
of them depends on an unanswered question about your Atlassian deployment:

- OS-keychain credential storage instead of plaintext `.env`.
- Collapsing the roughly 20 values duplicated across the two execution modes.
- Splitting the 2,162-line `setup.init`.

The MCP layer added here is what makes the first one decidable: on Atlassian Cloud the official
remote server removes the stored token entirely, and on Data Center it does not apply.

## 0.35.0 - Single Plan Branch (Planner Creates Branch)

Minor release. Fixes the multi-branch fragmentation problem where each
`delivery-runner` dispatched phase agent created its own feature branch, producing
N branches for N phases. Now `delivery-planner` creates one branch for the entire
plan, records `plan_branch` in all plan artifacts, and every dispatched phase
executor checks out (and continues on) that single branch.

### Added

- `plan_branch` field added to `destination.md`, `evidence-pack.yml.delivery_plan`,
  and `phased-plan/README.md` headers. The planner derives the branch name from
  `${GIT_BRANCH_NAME_FORMAT}` and the issue key, creates the branch (and pushes
  it when git access is available), then records it so every downstream phase
  executor knows which branch to use.
- `delivery-run-next.py` now extracts `plan_branch` from the index header and
  includes it in each dispatch-decision JSON so the runner can communicate it.
- Pre-work isolation gate updated: when `delivery_plan.plan_branch` is set, the
  executor checks out (not creates) that branch; branch creation is planner-only.
- New eval `evals/plan-branch-single-branch-per-plan.md` verifying that all phases
  commit to the same planner-created branch.

### Changed

- `delivery-planner` step 5 (Sequence and dispatch) now includes explicit branch
  creation and `plan_branch` recording before the final dispatch pointer is set.
- `delivery-runner` handoff prompt now communicates the plan branch and instructs
  executors to check it out rather than create a new one.
- `software-engineer` Phase 1.3 (Git branching) and the "When invoked from a
  delivery-planner phase" section now detect `plan_branch` and checkout instead
  of create.
- `phase-execution-branch-isolation` eval updated to reflect the plan-branch
  contract: phase 02 must continue on the same plan branch, not create a new one.
- All skill `metadata.version` fields bumped to `0.35.0`.

### Fixed

- Multi-branch fragmentation: N-phase plans no longer produce N separate feature
  branches. One plan = one branch, regardless of phase count.

## 0.34.0 - Delivery Runner (Autonomous Phase Handoff)

Minor release. Adds a new top-level skill, `delivery-runner`, that executes a
`delivery-planner` phased plan end-to-end with no manual handoff between phases,
and realigns every skill `metadata.version` with `VERSION` (the `0.33.2` patch
bumped `VERSION` but left the skills at `0.33.1`).

### Added

- New skill [`skills/delivery-runner`](skills/delivery-runner/SKILL.md). It reads
  a plan's `current_dispatch_pointer`, opens a **fresh, empty-context agent per
  phase** (sub-agent / Task tool, external CLI re-invocation, or a human-relayed
  handoff), waits, then verifies each phase from the persisted plan artifacts
  (the index plus the phase-continuity checkpoint) — never from chat — before
  advancing. It dispatches fresh agents rather than invoking executor skills in
  its own context, so the depth-cap-of-two review bound stays intact inside each
  phase.
- Bounded error handling in the runner: a phase that wrote `state: blocked` stops
  the run (no auto-retry); a crashed phase with no checkpoint is retried at most
  once; a hard iteration cap and a no-progress guard prevent spinning; index ↔
  evidence-pack disagreement and superseded plans stop and route back to the
  planner.
- Read-only helper [`scripts/delivery-run-next.py`](scripts/delivery-run-next.py)
  that parses `phased-plan/README.md` and prints a deterministic JSON dispatch
  decision (`dispatch` / `stop` / `error`) for each loop iteration. The index —
  which lifecycle cleanup preserves across phase boundaries — is the source of
  truth, not the per-phase `evidence-pack.yml`.
- Reference files
  [`handoff-prompt-template.md`](skills/delivery-runner/references/handoff-prompt-template.md)
  and [`run-loop-checklist.md`](skills/delivery-runner/references/run-loop-checklist.md).
- New eval
  [`evals/delivery-runner-autonomous-handoff.md`](evals/delivery-runner-autonomous-handoff.md)
  and release notes under [`eval-runs/v0.34.0/`](eval-runs/v0.34.0/summary.md).

### Changed

- Documented the runner as a dispatcher that sits **outside** the cross-skill
  review loops in [`docs/review-loops.md`](docs/review-loops.md).
- `delivery-planner` now points at `delivery-runner` for end-to-end execution in
  its `Related And Reused Skills` and dispatch sections.
- Bumped `VERSION`, README status, and every `SKILL.md` `metadata.version` to
  `0.34.0`, resolving the `0.33.1`/`0.33.2` drift.

## 0.33.2 - Preserve Plan Artifacts Across Phase Cleanup

Patch release for `0.33.1`. The `cleanup-task` subcommand of `project-memory.py`
used `shutil.rmtree` on the entire `<issue-key>/` cache directory. When an
executor agent finished a phase and the `finish-task.sh` wrapper called cleanup,
it deleted the delivery-planner's `destination.md` and `phased-plan/` artifacts.
The next executor phase then had no plan to load.

### Fixed

- `cleanup_task()` in `scripts/project-memory.py` now detects the presence of
  `phased-plan/README.md` and preserves `phased-plan/` plus `destination.md`
  while still removing other per-task scratch (blackboard, evidence pack, etc.).
  Plan artifacts survive across executor phase boundaries.
- Docstring updated to document the preservation contract.

## 0.33.1 - Lifecycle Cache-Root Patch

Patch release for `0.33.0`. Post-release closeout found that `start-task.sh`
and `finish-task.sh` could default to different cache roots when neither
`AGENT_SKILLS_CACHE_DIR` nor `WORKSPACE_ROOT` was set. That could make no-arg
finish write memory to one cache while trying to clean scratch from another.

### Changed

- `start-task.sh` now defaults to `cwd/.cache/agent-skills`, matching the
  Python memory scripts' fallback after `AGENT_SKILLS_CACHE_DIR` and
  `WORKSPACE_ROOT`.
- `finish-task.sh` passes the resolved cache root explicitly to
  `project-memory.py` and `telemetry.py`, so memory writes, telemetry, persisted
  last-context lookup, and cleanup all target the same cache.
- Added [`eval-runs/v0.33.1/summary.md`](eval-runs/v0.33.1/summary.md) with
  the patch-release smoke evidence.
- `VERSION`, README status, and all skill metadata versions moved to `0.33.1`.

## 0.33.0 - Lifecycle Wrappers Everywhere

This release addresses field feedback that agents can read a skill, decide a
task is "simple", and then skip the required workflow. The fix applies across
all skills: make the lifecycle easier to run than to skip, require a visible
receipt, and keep small tasks proportional without making gates optional.

### Added

- New [`scripts/task-context.sh`](scripts/task-context.sh) shared resolver for
  project and task ids. It detects context from `.agent-skills.yml`,
  `${PROJECTS_JSON}`, GitHub environment variables, branch names, and cwd.
- New [`scripts/finish-task.sh`](scripts/finish-task.sh) one-command closeout.
  It writes project memory first, emits telemetry, then cleans per-task scratch
  only when the terminal status is safe. `blocked` and `needs-context` preserve
  scratch by default.
- New [`evals/all-skills-lifecycle-compliance.md`](evals/all-skills-lifecycle-compliance.md)
  covering lifecycle compliance for every skill, even tiny tasks.
- New [`evals/software-engineer-skill-compliance-sonarqube.md`](evals/software-engineer-skill-compliance-sonarqube.md)
  covering the exact failure mode: a small SonarQube cleanup must still run
  memory preflight, proportional planning, reviewer handoff, QA, and closeout.
- New release evidence in [`eval-runs/v0.33.0/summary.md`](eval-runs/v0.33.0/summary.md).

### Changed

- [`scripts/start-task.sh`](scripts/start-task.sh) no longer requires
  `<project> <issue-key>`. It auto-detects both, accepts explicit overrides,
  normalizes URL-shaped task ids into safe cleanup keys, and records
  `--skill name=version` on the blackboard. It also persists the latest
  project/task pair in the cache so no-arg `finish-task.sh` closes the same
  lifecycle run.
- All eight `SKILL.md` files now use the same top-of-file lifecycle contract:
  run `start-task.sh --skill <name>=0.33.0` before context discovery and
  `finish-task.sh --skill <name> --summary ...` before final status.
- All skill output contracts now require a lifecycle receipt so skipped
  wrappers, skipped memory writes, or blocked closeout are visible in the final
  answer.
- Removed the older duplicate bottom `Company Brain integration` sections from
  every skill so agents see one current lifecycle path instead of conflicting
  start/finish examples.
- `software-engineer` adds a proportional `tiny` lane. It trims evidence volume
  for mechanical fixes but explicitly keeps lifecycle, review, QA, and memory
  gates mandatory.
- Assistant/install docs now state that cloud and IDE agents need access to
  `scripts/` as well as `skills/`.
- `VERSION`, README status, and all skill metadata versions moved to `0.33.0`.

## 0.32.0 - Memory Lifecycle Enforcement

This release closes the #1 failure mode observed in real agent-skills usage:
agents reading the SKILL.md but skipping the Company Brain memory lifecycle
(read project memory before starting, write project memory after finishing).
The fix is architectural — making the steps unavoidable rather than trusting
agent discipline.

### Added

- New [`scripts/start-task.sh`](scripts/start-task.sh) — single-command preflight
  that loads org memory, project memory, and initialises the per-task blackboard
  in one call. One tool invocation is more likely to happen than three. Prints a
  consolidated summary the agent treats as its starting context.
- New [`.github/copilot-instructions.md`](.github/copilot-instructions.md) —
  auto-loaded by GitHub Copilot in VS Code. Encodes the non-negotiable read-on-start /
  write-on-finish contract at the system-prompt level so Copilot sessions cannot skip it.
- New [`.github/copilot-instructions.example.md`](.github/copilot-instructions.example.md) —
  template for users to copy into their own project repositories.

### Changed

- **PREFLIGHT block added to all 8 SKILL.md files** — a ~20-line `## ⚠️ PREFLIGHT`
  section placed immediately after the title paragraph, before any philosophy,
  purpose, or mindset sections. Contains only the mandatory memory commands and
  the "output IS your starting context" rule. Agents see it first, not after 200
  lines of setup philosophy.
- **Skeleton output improved** in `scripts/project-memory.py` and
  `scripts/org-memory.py` — placeholders now read "_No facts yet. After your first
  task, this section will contain…_" instead of "_empty — populated as the agent
  learns._" The new text signals "this is where value accumulates" rather than
  "nothing useful here."
- **`docs/company-brain.md` read order** now names `scripts/start-task.sh` as the
  recommended single-command entry point alongside the three individual steps.
- All eight SKILL.md files bumped to `metadata.version: "0.32.0"`.
- `VERSION` and README status pin moved to `0.32.0`.

### Design rationale

The root cause diagnosed in #1 (the conversation that triggered this release)
was not that agents don't understand the memory contract — it's that the contract
was buried 130+ lines deep in a 400+ line file, behind philosophy that satisfies
curiosity but doesn't gate action. Three architectural fixes:

1. **Position**: PREFLIGHT at line ~27 (after YAML + title), not line ~130.
2. **Granularity**: One command (`start-task.sh`) instead of three separate
   invocations.
3. **Platform enforcement**: `copilot-instructions.md` for the system-prompt
   layer that agents cannot choose to skip.

The Company Brain loop (`docs/company-brain.md`) is unchanged. This release
enforces the existing contract, it doesn't change it.

This release turns the eight specialist skills into a self-improving loop:
every task writes to a per-task blackboard, every PR's fate is recorded as an
outcome, every recurring lesson can be promoted into org-tier memory, and a
telemetry layer makes "the skills are improving" a number instead of a feeling.
The loop is documented in [`docs/company-brain.md`](docs/company-brain.md).

### Added

- New [`docs/company-brain.md`](docs/company-brain.md) — the canonical map of
  the self-improving loop (three memory tiers, blackboard, outcome feedback,
  telemetry, rule promotion, cross-project index, eval harness).
- New [`docs/org-memory.md`](docs/org-memory.md) and
  [`scripts/org-memory.py`](scripts/org-memory.py) — third memory tier above
  per-project memory. Stored at
  `${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills}/_org/`.
  Subcommands: `path`, `init`, `read`, `note`, `search`, `promote`,
  `index-update`, `index-show`. `_org/` is reserved by the existing cleanup
  contract so org memory survives every per-task cleanup pass on every project.
- New [`docs/task-blackboard.md`](docs/task-blackboard.md) and
  [`scripts/blackboard.py`](scripts/blackboard.py) — the canonical per-task
  working memory shared across every skill in a task. Schema includes
  `facts`, `assumptions`, `unknowns`, `decisions`, `artifacts`, `handoffs`,
  and `skill_versions` for honest attribution after the fact.
- New [`docs/telemetry.md`](docs/telemetry.md) and
  [`scripts/telemetry.py`](scripts/telemetry.py) — append-only NDJSON event
  log per project. Subcommands: `emit`, `report`. Recognised events:
  `invoked`, `loop_round`, `handoff`, `finding`, `stopped`, `completed`,
  `artifact`, `outcome`.
- New [`scripts/outcome-recorder.py`](scripts/outcome-recorder.py) — closes
  the loop: PR fate → project memory `Outcomes`, telemetry event, automatic
  `Lesson` line in `Common gotchas` for `reverted`/`hotfixed`, and explicit
  promotion to org memory with `--promote-to-org --confirmed-in N>=2`.
- New [`scripts/promote-rules.py`](scripts/promote-rules.py) — scans every
  project's memory under a configurable section (default `Common gotchas`)
  and emits a JSON list of candidates that recur across `≥ --min-projects`
  projects. The brain proposes; humans approve.
- New [`scripts/run-evals.py`](scripts/run-evals.py) — structural eval
  harness. Checks every `evals/*.md` for a top-level heading, a context
  section, a success-criteria section, valid `Expected Skills:` references,
  and that every `eval-runs/<version>/` ships a `summary.md`. Designed so a
  future iteration can plug a real agent runner behind `--invoke`.

### Changed

- [`scripts/project-memory.py`](scripts/project-memory.py) gains `dedup`,
  `compact --keep N`, `search <query>`, and `promote-candidates --section
  --min-count` subcommands so per-project memory does not bloat unbounded
  and recurring bullets can be surfaced for org-tier promotion.
- All eight top-level SKILL.md files bumped to `metadata.version: "0.31.0"`
  and now point at the Company Brain hooks documented in
  [`docs/company-brain.md`](docs/company-brain.md).

## 0.29.0 - Config Discovery, GitHub Access Ladder, Project Memory

### Added

- New [`docs/project-memory.md`](docs/project-memory.md) and
  [`scripts/project-memory.py`](scripts/project-memory.py) — durable per-project knowledge
  store at
  `${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills}/_projects/<project-slug>/memory.md`.
  Skills read it before context discovery and append a bullet to it after every successful
  task. The `_projects/` prefix is reserved; the `cleanup-task` subcommand refuses any path
  starting with `_` so per-task cleanup never deletes accumulated project knowledge.
  Subcommands: `path`, `init`, `read`, `note`, `cleanup-task`.
- New [`docs/github-access.md`](docs/github-access.md) and
  [`scripts/github-access.sh`](scripts/github-access.sh) — the canonical ladder an agent must
  walk before declaring "no GitHub access". Steps: `gh auth status` → enumerate logged-in
  accounts on `github.com` → `gh repo view <owner>/<repo>` → `git ls-remote` over HTTPS →
  `git ls-remote` over SSH. When the active `gh` account is wrong for the target org (the
  most common false dead-end on developer laptops), the script prints a `suggest: gh auth
  switch -h github.com -u <other-login>` line for the agent to follow before giving up.
- New [`scripts/locate-config.py`](scripts/locate-config.py) — deterministic finder for
  `.env`, `.env.local`, `.jira-config.yml`, and `.agent-skills.yml`. Walks the cwd, every
  parent directory, the `WORKSPACE_ROOT` env var, and the directory holding the `.skills`
  symlink (where `setup.init` writes them). Prints the searched-directory list so an agent
  cannot honestly report "`.env` not found" without naming the directories it actually
  checked. Reads no file contents; never prints secrets.
- New [`docs/auth-discovery.md` § Where the files
  live](docs/auth-discovery.md#where-the-files-live) section pinning the location order and
  the `setup.init` contract that `.env` lives in the **parent workspace folder**, not the
  repo cwd. The TL;DR now starts with "Locate the files first" so the discovery walk cannot
  be skipped by a too-narrow cwd check.

### Changed

- **`software-engineer` Phase 1.3** — the bare `gh auth status` step now binds the agent to
  walk the [GitHub access ladder](docs/github-access.md) when the active account fails to
  reach the target repo. Surfacing "no GitHub access" without trying the ladder (and every
  printed `suggest:` line) is now an explicit workflow failure.
- **`software-engineer` Required Environment** — adds two new mandatory pre-flight reads:
  `python3 scripts/locate-config.py` (locate config files before claiming any are missing)
  and `python3 scripts/project-memory.py read <project>` (load durable project knowledge
  before context discovery). The same two reads are now required at the top of
  `delivery-planner`, `product-owner`, `manual-tester`, `test-automation-engineer`,
  `issue-investigator`, and `code-reviewer` workflows.
- **`software-engineer` new section 5.5 — Project memory and per-task cleanup.** After the PR
  is open (or the run reaches a terminal `blocked` / `abandoned` state), the agent must
  (1) append durable facts to project memory, then (2) run
  `python3 scripts/project-memory.py cleanup-task <issue-key>` to delete only
  `${cache_root}/<issue-key>/`, then (3) `git branch -d <branch>` for branches that have
  been merged and pushed. The script refuses any path starting with `_`; remote branches
  are never deleted; `blocked` runs skip cleanup so the next agent can resume.
- README documentation index now lists the new GitHub-access-ladder and project-memory
  pages alongside auth-discovery.
- `VERSION`, README status pin, and all skill metadata versions moved from `0.28.0` to `0.29.0`.

## 0.28.0 - Phase Execution Hygiene

### Added

- Added a binding **branch-isolation pre-check** to the
  [phase-continuity checkpoint](skills/software-engineer/references/evidence-pack.md#phase-continuity-checkpoint).
  Before flipping `phases[<id>].state` to `in-progress`, every executor that mutates a repo
  must capture `working_branch` (from `git rev-parse --abbrev-ref HEAD`) and the project's
  `base_branch` (from `${PROJECTS_JSON}` with `${GITHUB_DEFAULT_BRANCH}` fallback) and assert
  they are not equal. A match stops the phase with `BLOCKED: phase would commit to base
  branch <name>` and `state: blocked`. Read-only owners record `working_branch:
  not-applicable — read-only`.
- Added an **owner-skill verification recipe** to
  [`docs/skill-source-resolution.md`](docs/skill-source-resolution.md#owner-skill-verification-recipe).
  Executors must verify a phase's `recommended_owner` by reading
  `<canonical>/<recommended_owner>/SKILL.md` directly with the file-read tool — the host IDE's
  curated skill panel (Cursor, Continue, Copilot Chat) is not authoritative. An IDE listing
  that omits the skill is **not** evidence the file is missing. Verified path is recorded on
  `phases[<id>].owner_skill_source`.
- Added an **`## Inputs for the next agent`** section to the
  [plan-index template](skills/delivery-planner/references/plan-index-template.md). The
  generated `phased-plan/README.md` now lists the destination brief, evidence pack, current
  phase file, and canonical skill source path so a user pasting only the README into a fresh
  prompt has every pointer the executor needs.
- Added [`evals/phase-execution-branch-isolation.md`](evals/phase-execution-branch-isolation.md),
  [`evals/owner-skill-verification-vs-ide-listing.md`](evals/owner-skill-verification-vs-ide-listing.md),
  and [`evals/plan-index-regenerated-after-each-phase.md`](evals/plan-index-regenerated-after-each-phase.md)
  pinning the three new contracts.

### Changed

- **Executors regenerate `phased-plan/README.md`.** The phase-continuity checkpoint now
  requires the executing skill (`software-engineer`, `issue-investigator`, `product-owner`,
  `manual-tester`, `test-automation-engineer`) to regenerate the phased-plan index from the
  updated evidence pack as part of the same checkpoint write — refresh the phase table's
  `State` column, the `totals`, the `last_completed_*` mirrors, the
  `current_dispatch_pointer`, and the `Inputs for the next agent` section, and bump
  `updated_at`. Adding, deleting, reordering, renaming, or resizing phases remains
  planner-only. Without this regeneration, downstream agents reading only the README see
  stale dispatch state.
- **`setup.init --update` preserves per-repo `base_branch` overrides.** A new
  `merge_projects_json` step merges the freshly-detected `PROJECTS_JSON` with the existing
  one by `name`: every key set in the existing entry wins (`base_branch`,
  `runtime_version`, `notes`, `build`, etc.). Newly-detected repos are appended; repos
  removed from disk are dropped. Teams that target `develop` or any non-default base branch
  no longer have their overrides reset on every update. A warning surfaces when `python3` is
  unavailable for the merge.
- The `delivery-planner` guardrail "Do not recommend `develop` branches or GitFlow" was
  replaced with "Do not invent the project's branching policy. Read each affected repo's
  `base_branch` from `${PROJECTS_JSON}`." The planner now mirrors what the project declared
  rather than imposing the agent-skills repo's own preference on user repos.
- Every executor's "When invoked from a delivery-planner phase" section now points at the
  owner-skill verification recipe, the branch-isolation pre-check, and the README
  regeneration discipline. The phase-continuity checkpoint additionally requires
  `working_branch`, `base_branch`, and `owner_skill_source` on the completion write.
- `VERSION`, README status, and all skill metadata versions moved from `0.27.0` to `0.28.0`.

## 0.27.0 - Phase Continuity Checkpoints

### Added

- Added a binding
  [phase-continuity checkpoint](skills/software-engineer/references/evidence-pack.md#phase-continuity-checkpoint)
  contract to `evidence-pack.yml`. Any skill executing a `delivery-planner` phase now must record
  `in-progress`, `done`, or `blocked` state plus completion summary, artifacts, validation,
  follow-up context, `last_completed_*` / `last_blocked_*` mirrors, and the recomputed
  `current_dispatch_pointer` before claiming the phase is complete.
- Added a missing-evidence-pack recovery rule: when an executor is given `destination.md` and
  `phase-NN.md` but no `evidence-pack.yml`, it must reconstruct the minimal `delivery_plan` from
  the phase files or stop with `BLOCKED: phase continuity evidence-pack missing`.
- Added [`evals/delivery-planner-phase-continuity.md`](evals/delivery-planner-phase-continuity.md)
  to pin the greenfield planning and phase-1 execution handoff that exposed the continuity break.

### Changed

- `delivery-planner` now must create or update `evidence-pack.yml` in the same run as
  `destination.md` and `phased-plan/`, even for greenfield plans with no prior evidence pack.
  Markdown-only phase plans are no longer dispatchable.
- `software-engineer`, `issue-investigator`, `product-owner`, `manual-tester`, and
  `test-automation-engineer` phase handoff sections now require opening `evidence-pack.yml` before
  work, marking the current phase `in-progress`, writing a completion or blocked checkpoint, and
  re-reading the evidence pack after the write.
- `delivery-planner` output now includes the evidence-pack path in `Plan Summary`, and the planner
  checklist verifies that `delivery_plan` contains one phase entry per phase file.
- `VERSION`, README status, and all skill metadata versions moved from `0.26.0` to `0.27.0`.

## 0.26.0 - Dispatch And Jira Scope Hardening

### Added

- Added a prompt-supplied skill-source rule to
  [`docs/skill-source-resolution.md`](docs/skill-source-resolution.md): when a user gives an exact
  skill folder or `SKILL.md` path, agents must verify that path before falling back to host defaults
  such as `.skills`.
- Added `evidence-pack.yml.related_work` for open PRs, matching remote branches, and already
  addressed issue status so Jira-driven work can detect likely existing fixes before starting a
  competing branch.
- Added [`evals/jira-issue-scope-and-existing-pr.md`](evals/jira-issue-scope-and-existing-pr.md) to
  pin one-Jira-task-per-branch/PR behavior and existing PR detection.

### Changed

- `evidence-pack.yml.delivery_plan` now treats a missed `recommended_owner` skill as a workflow
  blocker. Executors must load the recommended owner from the resolved canonical skill source and
  stop if the skill is unavailable or mismatched.
- `software-engineer` now starts with dispatch and ticket-isolation gates: one Jira task maps to one
  branch and one PR, existing open PRs/branches are checked before branch creation, and ticket-driven
  completion requires a pushed branch plus PR URL.
- `issue-investigator` now checks for open PRs or remote branches that may already address a Jira or
  GitHub issue and records the result in `evidence-pack.yml.related_work`.
- `code-reviewer` now treats bundling independent Jira tasks into one PR as a blocker for
  issue-aware review.
- `delivery-planner` now requires code-delivery plans to reach a conclusive reviewable artifact:
  outer-loop review, Definition-of-Done, pushed branch, and PR URL, or an explicit blocker. A final
  validation-only phase is no longer sufficient for bug-fix or implementation delivery.
- `VERSION`, README status, and all skill metadata versions moved from `0.25.0` to `0.26.0`.

## 0.25.0 - Delivery Planner

### Added

- New top-level [`delivery-planner`](skills/delivery-planner/SKILL.md) skill that turns a single
  large or multi-day task (feature, refactor, migration, multi-step investigation, multi-PR bug
  fix) into two persistent artifacts: a one-page `destination.md` brief and a sequence of small
  self-contained `phased-plan/phase-NN-<slug>.md` files. Each phase is sized so a fresh agent
  loaded with `destination.md` plus one `phase-NN.md` has enough — and only enough — context to
  execute it well. Phases name exactly one recommended owner skill
  (`software-engineer`, `product-owner`, `issue-investigator`, `manual-tester`,
  `test-automation-engineer`); the planner does not invoke any of them itself, preserving the
  depth-cap-of-two universal loop bound from
  [docs/review-loops.md](docs/review-loops.md#universal-loop-bounds).
- New references for the planner: a
  [plan-quality checklist](skills/delivery-planner/references/plan-quality-checklist.md) used in
  the planner's single bounded self-validation pass, a
  [phase template](skills/delivery-planner/references/phase-template.md) defining the binding
  shape of each per-phase Markdown file, a
  [destination template](skills/delivery-planner/references/destination-template.md) defining
  the binding header + body shape of `destination.md` (with `work_key`, `state`, `created_at`,
  `updated_at`, `source_refs`, `understanding_confidence`, `readiness_decision`), and a
  [plan-index template](skills/delivery-planner/references/plan-index-template.md) defining
  the binding shape of `phased-plan/README.md` (header mirrors of
  `evidence-pack.yml.delivery_plan`, totals, the phase table, and the binding dispatch-pointer
  rules).
- New `delivery_plan` block in
  [`evidence-pack.yml`](skills/software-engineer/references/evidence-pack.md), with a strict
  two-writer ownership rule: `delivery-planner` writes the structural fields
  (`destination_path`, `index_path`, `current_dispatch_pointer`, the `phases[]` list); the
  skill named in a phase's `recommended_owner` is the sole writer of that phase's completion
  state (`state`, `completed_at`, `completed_by`) plus the top-level `last_completed_*`
  mirrors. Every receiving skill (`software-engineer`, `product-owner`, `issue-investigator`,
  `manual-tester`, `test-automation-engineer`) now has a binding `When invoked from a
  delivery-planner phase` step that performs those writes before returning, so the dispatch
  pointer stays fresh after real phase execution.
- New example
  [`docs/examples/delivery-planner-feature-decomposition.md`](docs/examples/delivery-planner-feature-decomposition.md)
  walking through an SSO-parity decomposition, including how the
  [Requirement Understanding Gate](docs/requirement-understanding.md) gates the dispatch
  pointer (discovery first when confidence is `medium`).
- New eval
  [`evals/delivery-planner-phased-plan.md`](evals/delivery-planner-phased-plan.md) pinning
  the skill against premature `READY_FOR_DISPATCH`, oversized single-phase plans, missing
  required destination fields, and silent re-invocation of other skills.

### Changed

- `delivery-planner` step 5 (Sequence and dispatch) now states the dispatch-pointer rules as
  binding: `READY_FOR_DISPATCH` and `READY_FOR_DISCOVERY` MUST name a phase id (the discovery
  phase id, when readiness is `READY_FOR_DISCOVERY`); `null` is reserved for
  `NEEDS_CLARIFICATION` / `NEEDS_EVIDENCE` / `BLOCKED`. The Expected Output Contract and the
  plan-quality checklist now mirror the same rule, and the prior contradicting "none —
  discovery first" placeholder has been removed.
- `software-engineer` Phase 1.4 now has a **size check before implementation** that hands off
  to `delivery-planner` whenever the smallest credible plan does not fit one focused agent
  session — multi-PR features, multi-step migrations, or multi-day validation routes.
- `product-owner` step 4 (Refine scope) now has an **oversized epic check** that hands off to
  `delivery-planner` before writing acceptance criteria when an epic clearly fans out into
  multiple stories spanning multiple surfaces or releases.
- `issue-investigator`, `manual-tester`, and `test-automation-engineer` `Related And Reused
  Skills` sections now describe how phases owned by them are dispatched from a planner-produced
  `destination.md` + `phase-NN.md`. None of them invoke the planner — the dispatch direction
  is one-way to keep loops bounded.
- [`docs/skill-boundaries.md`](docs/skill-boundaries.md) adds the `delivery-planner` role with
  its ownership boundary (decomposes work; does not execute it) and the binding rule that the
  planner must hand off each phase to exactly one owner skill rather than invoking any skill
  itself.
- [`docs/review-loops.md`](docs/review-loops.md) adds the planner's bounded self-validation
  loop alongside the existing producer/reviewer pairs.
- [`README.md`](README.md) now documents **five top-level skills** (was four) and lists
  `delivery-planner` first because it sits at the start of any multi-session workflow.
- [`scripts/validate-repo.py`](scripts/validate-repo.py) tracks the new SKILL, README, two
  references, the eval, and the example as required files, and adds the cross-skill link
  requirements for `delivery-planner`.
- `VERSION` bumps from `0.24.0` to `0.25.0`. All `SKILL.md` `metadata.version` fields move
  with it.

## 0.24.0 - Engineer-Owned Review Auto-Iteration

### Added

- `software-engineer` now owns the inner and outer engineer↔reviewer loops: it addresses review
  findings, re-stages changes, re-invokes `code-reviewer` with `--since-last-review`, and repeats
  until `Loop: converged` or a bounded escalation signal stops the workflow.
- `code-reviewer` now emits a binding final `Loop:` control signal when invoked from
  `software-engineer`. One-shot `pr` and `manual` reviews omit the line.
- `evidence-pack.yml.review` now records the current round `verdict`, and
  `code-reviewer` is documented as the sole writer of the review block to prevent double-increments
  and stale convergence counts.

### Changed

- `software-engineer` surfaces intermediate reviewer rounds only to its working context and
  `review.history`; the user is now the escalation path for `not-converging`, `max-rounds`,
  `needs-user`, or unresolved `needs-context`, not the driver of every round.
- README and `software-engineer` docs now describe the review loop as auto-iterating rather than a
  manual handoff between roles.

## 0.23.1 - Iteration Convergence Clarifications

### Changed

- **`code-reviewer` §7 — Round-1 baseline clarification.** Added an explicit rule that round 1 has
  no prior round and strict-decrease does not apply on round 1. A round-1 result with actionable
  findings always produces `Loop: continue` — never `Loop: not-converging`. Strict-decrease applies
  from round 2 onward (N ≥ 2 compares against N-1). Mirrored in the `software-engineer` §2.4
  inner-loop description.
- **`code-reviewer` §7 — Iteration signal taxonomy.** Introduced a formal split of the six loop
  signals into two categories: *action signals* (`Loop: continue`, `Loop: needs-context`) where the
  loop continues, and *terminal signals* (`Loop: converged`, `Loop: not-converging`,
  `Loop: max-rounds`, `Loop: needs-user`) where the loop stops. `Loop: needs-context` upgrades to
  `Loop: needs-user` only when the named follow-up skill itself returns `needs-context` or `blocked`.
- **`software-engineer` Phase 3.5 — Convergence gate.** Phase 3.5 now explicitly states that only
  `Loop: converged` advances the workflow to Phase 4. Other terminal signals (`Loop: not-converging`,
  `Loop: max-rounds`, `Loop: needs-user`) stop the workflow with unresolved findings surfaced to the
  user; a written waiver is required to override.
- **Guardrails updated.** `code-reviewer` Guardrails gains a rule forbidding `Loop: not-converging`
  on round 1. `software-engineer` Guardrails gains a rule forbidding phase advancement past the
  convergence gate on any terminal signal other than `Loop: converged`.

## 0.23.0 - Insightful Simplifications

### Added

- New [`docs/insightful-simplifications.md`](docs/insightful-simplifications.md)
  defining an **optional**, bounded `## Insightful Simplification` output section
  any skill MAY add (1–3 bullets, ≤ 35 words each, anchored to a concrete
  file/layer/state/contract) when one short architectural observation would help
  the user see the wider shape of the problem. Default behavior is to **omit**
  the section; it is governed by the existing
  [output-discipline](docs/output-discipline.md) and
  [token-efficiency](docs/token-efficiency.md) rules.
- Optional `## Insightful Simplification` block added to the Expected Output
  Contract of every top-level and nested skill
  ([`software-engineer`](skills/software-engineer/SKILL.md),
  [`product-owner`](skills/product-owner/SKILL.md),
  [`manual-tester`](skills/manual-tester/SKILL.md),
  [`test-automation-engineer`](skills/test-automation-engineer/SKILL.md),
  [`issue-investigator`](skills/software-engineer/skills/issue-investigator/SKILL.md),
  [`code-reviewer`](skills/software-engineer/skills/code-reviewer/SKILL.md)).
  Required-even-if-empty sections (`code-reviewer` `## Final Verdict`,
  `software-engineer` `## Final Status`) keep their position at the end of the
  output.
- New eval
  [`evals/insightful-simplifications-concise.md`](evals/insightful-simplifications-concise.md)
  pinning the section against generic-coaching, restate-finding,
  invented-architecture, and template-echo failure modes for both cross-layer
  and trivial tasks.

### Changed

- `software-engineer` `Expected Output Contract` promotes the trailing
  `Final status:` bullet into its own `## Final Status` section so the
  required-even-if-empty status remains the last block when the optional
  `## Insightful Simplification` is rendered above it.

## 0.22.0 - Bounded Cross-Skill Review Loops, Token-Efficiency Audit, COVERAGE_TARGET_PERCENT Clarification

### Added

- New [`docs/review-loops.md`](docs/review-loops.md) defining how producer skills hand
  off to reviewer skills with **bounded** revision rounds. Six universal bounds (one
  revision round by default, no recursion, depth cap of two skills, etc.) plus the
  documented exception for the existing `software-engineer` ↔ `code-reviewer` loop
  (which keeps `${CODE_REVIEWER_MAX_ROUNDS}`, default `3`, with strictly-decreasing
  finding counts per round). Includes the new `investigation-quality checklist` and
  `test-plan review checklist`.
- New [`docs/token-efficiency.md`](docs/token-efficiency.md) capturing the principles
  ("menu, not checklist", "persistent artifacts over chat", "reference, do not copy",
  bounded loops, one-shot examples, no banner headers), the audit methodology, and
  the v0.22.0 audit findings.
- New step **7. Self-validation pass (bounded)** in
  [`issue-investigator/SKILL.md`](skills/software-engineer/skills/issue-investigator/SKILL.md)
  that runs the new investigation-quality checklist exactly once before emitting the
  result. Surviving items move to `Open Questions Or Missing Evidence`.
- New **Bounded review pass (one round)** in
  [`product-owner/SKILL.md`](skills/product-owner/SKILL.md) between the existing DoR
  gate and the Jira-ready output. For user-facing or behavior-complex work, asks
  `manual-tester` for a testability quick-check; surviving items downgrade the work
  item to `Spike` / `Discovery`.
- New step **7. Self-validation pass (bounded)** in
  [`manual-tester/SKILL.md`](skills/manual-tester/SKILL.md) that runs the new test-plan
  review checklist exactly once. Defects that fail the `issue-investigator` handoff
  become `product question` instead of `functional defect`.
- `eval-runs/v0.22.0/` — release summary, the skill-review-loops write-up with the
  motivating failure modes and the explicit "what this does NOT do" boundary, and the
  token-efficiency audit with line counts and findings.

### Fixed

- **README "Status" badge.** The user reported v0.21.0 README still showing `0.19.0`
  status pin on GitHub. The repo HEAD on `main` already had `0.21.0`; the v0.22.0
  release moves it to `0.22.0` and bumps `VERSION` and every `SKILL.md →
  metadata.version` accordingly.
- **`COVERAGE_TARGET_PERCENT` documentation.** Clarified in `.env.example` and the
  `software-engineer` test-coverage checklist that the placeholder is
  *agent-resolved*, not script-substituted: the agent runtime must have `.env`
  loaded into its process environment for an override to take effect; otherwise the
  literal default `80` applies. Removes the silent assumption that setting a value
  in `.env` automatically reaches the agent.

### Changed

- `test-automation-engineer/SKILL.md` step 6 — the existing `code-reviewer` (`manual`
  mode, `test-quality` profile) call is now explicitly tagged as a one-round bounded
  loop with a pointer to `docs/review-loops.md`. No behavior change; the bound is
  now written.
- `docs/README.md` index gains entries for `review-loops.md` and `token-efficiency.md`.
- `VERSION` and every `SKILL.md` `metadata.version` bumped to `0.22.0`.
- `README.md` status pin moved to `0.22.0`; the `## Updating` example tag list moved
  from `v0.20.0, v0.21.0` to `v0.21.0, v0.22.0`.

### Why

The release was triggered by a user audit raising four concerns:

1. README "Status" pin lagged the actual VERSION on the published GitHub view.
2. Uncertainty whether `COVERAGE_TARGET_PERCENT` is actually consumed anywhere.
3. Whether `issue-investigator` (and `product-owner`, `manual-tester`,
   `test-automation-engineer`) outputs are reviewed/validated by a peer skill the
   way `software-engineer` is reviewed by `code-reviewer`. The repo-level
   philosophy — *skills work together via review loops to give the best possible
   output* — was implemented for one skill pair but not for the others.
4. Whether the repo as a whole is token-efficient for real AI-agent usage.

v0.22.0 wires the bounded review loops with **explicit termination rules** so the
extension carries no endless-loop risk, documents `COVERAGE_TARGET_PERCENT` as
agent-resolved, and ships the audit findings under `eval-runs/v0.22.0/`.

## 0.21.0 - Code-Reviewer Verdict Gating, Update Credential Preservation, Updating Discoverability

### Added

- New `## Updating` section in [`README.md`](README.md), placed directly
  between `## Install` and `## Skills`. Surfaces the two commands users
  actually need (`./setup.init --check-updates` and `./setup.init --update`)
  on the top-level README rather than burying them in `docs/updates.md`.
  Includes a short note on what `--update` preserves and a pointer to the
  drift-detection behavior.
- New eval [`evals/code-reviewer-verdict-gating.md`](evals/code-reviewer-verdict-gating.md)
  pinning four real-world failure modes from a v0.20.0 PR-review transcript:
  auth-discovery failure buried as a Note, date-gated rollout treated as
  single-state, fixture replacement uncritically accepted, targeted test
  failure rationalized away.
- Four new binding rules in
  [`code-reviewer/SKILL.md`](skills/software-engineer/skills/code-reviewer/SKILL.md):
  - **Auth-discovery failure during issue-aware review is not a Note** —
    the verdict must be `NEEDS_CONTEXT`, not `PASS_WITH_NOTES`, when the
    Jira/GitHub credential resolves empty, the config has unresolved
    `${VAR}` placeholders, or the fetch fails. The only exception is when
    the user supplied the ticket summary, expected behavior, and
    acceptance criteria verbatim in the prompt.
  - **Date-gated / phased-rollout check** — when the diff references a
    future cutover date, flag flip, or upstream rename, the reviewer must
    verify both pre-cutoff and post-cutoff paths. A diff that supports
    only the post-cutoff state with no gating mechanism in the change and
    no evidence the legacy state has been retired must not receive `PASS`
    or `PASS_WITH_NOTES`.
  - **Fixture-replacement / label-rename check** — when tests are updated
    by **replacing** a value rather than **adding** new tests alongside,
    surface a `major` finding because the legacy regression coverage was
    deleted. Acceptable resolutions are documented inline.
  - **Targeted test failures are blocking** — failed tests/builds/CI runs
    cannot be dismissed with hypotheses (`Spring context startup error,
    not a tariff assertion`, `flake`, `pre-existing on main`). To dismiss
    a failure the reviewer must show one of: parent-commit rerun on the
    same SHA, a linked known-flaky-test ticket, or a clean rerun on a
    clean checkout.
- New `scripts/test-setup-update-preserves-credentials.sh` end-to-end
  regression test for the `--update` credential-preservation fix. Wired
  into `.github/workflows/ci.yml` as a new CI step.
- `eval-runs/v0.21.0/` — release summary, the verdict-gating eval run with
  motivating real-world transcript and good-shape v0.21.0 output, the
  setup-update-preserves-credentials write-up with reproduction recipe,
  and the updating-discoverability rationale.

### Fixed

- **`./setup.init --update` no longer wipes Jira / Confluence / Sonar /
  Environments credentials.** In v0.20.0 and earlier, `run_self_update`
  hardcoded `JIRA_MODE=no` / `CONFLUENCE_MODE=no` / `SONAR_MODE=no` /
  `ENVIRONMENTS_MODE=no` before falling through to the rerun, which then
  wrote empty values into the marker block of `<workspace>/.env`. Every
  `--update` silently blanked the user's credentials, causing
  `code-reviewer` to report "no Jira access" against a workspace that had
  a fully-populated `.env` immediately before the update. The fix sources
  the existing `.env` first, derives `*_MODE` from whether the
  corresponding required value is non-empty, and threads the existing
  values as prompt defaults so non-interactive `prompt` /
  `prompt_secret` calls fall back to the previous value instead of
  writing an empty string. The `ENVIRONMENTS_JSON` interactive loop is
  skipped in non-interactive mode and the existing JSON is preserved
  verbatim. User-edited lines outside the marker block were already
  preserved and remain so.
- The behavior is verified by the new
  `scripts/test-setup-update-preserves-credentials.sh` regression test
  running on every CI build.

### Changed

- `code-reviewer` Behavior Checklist gains four checklist items, one per
  new binding rule, so the gate runs at three points in the spec
  (Required Workflow → Behavior Checklist → Guardrails).
- `code-reviewer` Guardrails section gains four explicit "do not …"
  entries matching the four binding rules.
- `VERSION` and every `SKILL.md` `metadata.version` bumped to `0.21.0`.
- `README.md` status pin moved to `0.21.0`.

### Why

The release was triggered by a real PR-review transcript on v0.20.0 that
showed four concrete failure modes on the same prompt:

1. The reviewer admitted in its own output that it could not read the
   ticket but emitted `PASS_WITH_NOTES` anyway, with the auth failure
   listed as a Note alongside engineering observations. The headline
   conclusion was unsupported because issue alignment was never verified.
2. The PR explicitly referenced a `01.06.2026` rollout cutover. The new
   code matched only the post-cutoff label and the diff contained no
   gating mechanism. The reviewer assumed deployment timing would handle
   it. Pre-cutoff production traffic still using the legacy label would
   silently be misclassified.
3. Tests were updated by swapping the legacy label for the new one. The
   reviewer treated the green test run as proof of correctness and did
   not notice that the regression coverage proving the legacy path used
   to work was deleted.
4. A targeted test failed during the engineer's own verification
   (`JourneyKvbIT` Spring context startup, H2 rollback). The reviewer
   dismissed it with a hypothesis ("not a tariff assertion") and let the
   verdict stand without producing parent-commit evidence, a flaky-test
   ticket, or a clean rerun.

The auth-discovery failure was itself caused by the v0.20.0 `setup.init
--update` bug fixed in this release: a previous `--update` run had
silently blanked the user's `.env` credentials, so the next agent
invocation legitimately had no way to read Jira. Each fix here addresses
one of the four failure modes; together they prevent the same prompt from
producing an unsupported `PASS_*` verdict on v0.21.0.

### Not changed

- The destructive-action safety floor.
- The requirement-understanding gate.
- The other `code-reviewer` knobs (`BLOCKING`, `MAX_FILES`,
  `MAX_DIFF_CHARS`, `*_SEVERITIES`, `MAX_ROUNDS`, `CACHE_*`).
- `docs/updates.md` itself — it remains the canonical reference; the
  README change just makes it discoverable from the front page.
- The Output Discipline format and validator gates introduced in v0.20.0.

## 0.20.0 - Output Discipline And Model-Routing Cleanup

### Added

- New [`docs/output-discipline.md`](docs/output-discipline.md) — the canonical,
  agent-facing rule set for how every skill must shape its output. Defines the
  hard rules (omit empty sections, no template echo, no workflow recap, no
  banners), the single-bullet finding format reused by `code-reviewer`,
  `manual-tester` defects, and `issue-investigator` hypotheses, and the
  one-line verdict format. Linked from the Expected Output Contract section of
  every `SKILL.md` so the rule cannot drift out of the spec.
- New [`evals/code-reviewer-concise-output.md`](evals/code-reviewer-concise-output.md)
  scenario pinning the failure modes the new spec exists to prevent
  (template-echo, seven-line per-finding skeleton, workflow recap, banner-wrapped
  verdict).
- New `## Output Style (binding)` block under the `## Expected Output Contract`
  section of every `SKILL.md` (`software-engineer`, `software-engineer/skills/code-reviewer`,
  `software-engineer/skills/issue-investigator`, `manual-tester`, `product-owner`,
  `test-automation-engineer`). Each restates the load-bearing rules inline so the
  agent reads them in the same context as the contract template.
- New `check_skill_output_discipline` validator in
  [`scripts/validate-repo.py`](scripts/validate-repo.py) — refuses any future
  `SKILL.md` whose Expected Output Contract drops the link to
  `docs/output-discipline.md` or the literal phrase `Omit empty sections`.
- New `check_no_code_reviewer_model` validator — forbids reintroduction of the
  removed `CODE_REVIEWER_MODEL` / `code_reviewer_model` knobs in tracked files
  (allow-list: `CHANGELOG.md`, the validator itself, eval-run history).
- `eval-runs/v0.20.0/` capturing the concise-output scenario, the
  model-routing-removal note, and the release summary.

### Changed

- `code-reviewer` Expected Output Contract rewritten from a long YAML-style
  skeleton into a tight "menu of available sections". The per-finding block
  collapses from eight bullet fields (`Severity:` / `Title:` / `Affected
  file/area:` / `Evidence:` / `Why it matters:` / `Suggested fix:` /
  `Confidence:` / `Blocking/advisory decision:`) to **one bullet** in the
  Output Discipline format. `Review Limitations / Unavailable Context` is now
  rendered as a single line or short paragraph instead of a six-bullet `none`
  block. The `## Final Verdict` is one line: `<VERDICT> — <reason>` with at
  most one follow-up line.
- `manual-tester`, `product-owner`, `test-automation-engineer`, `issue-investigator`,
  and `software-engineer` Expected Output Contracts updated with the same
  "menu, not checklist" framing and a binding `Output Style` subsection. Defect
  / hypothesis / finding rendering is unified on the Output Discipline format.
- The `code-reviewer` Behavior Checklist explicitly requires the Output
  Discipline format and forbids the seven-line per-finding skeleton.
- `VERSION` and every `SKILL.md` `metadata.version` bumped to `0.20.0`.
- `README.md` status pin moved to `0.20.0`.

### Removed

- `CODE_REVIEWER_MODEL` env var and its 25-line model-id comment block deleted
  from `.env.example`. The skill never invoked the value — model routing is
  always owned by the host (Copilot Chat, Claude Code, Cursor, Continue,
  Windsurf, ChatGPT). The previous `default` sentinel was confusing and the
  list of example model ids drifted out of date as new models shipped.
- `code_reviewer_model` removed from `.agent-skills.example.yml`.
- `CODE_REVIEWER_MODEL` row removed from `docs/configuration.md`'s
  `local-workspace` env table; `code_reviewer_model` row removed from the
  `in-repo` YAML key table.
- `CODE_REVIEWER_MODEL` bullet removed from
  `skills/software-engineer/skills/code-reviewer/SKILL.md` Required Environment
  list.
- The "`CODE_REVIEWER_MODEL` is optional" sentence removed from the nested
  `code-reviewer/README.md`.

Existing `.env` / `.agent-skills.yml` files that still carry the variable
continue to work because nothing reads the value; the line can be deleted at
the user's convenience. `setup.init` does not own the line and will not touch
it. See [`eval-runs/v0.20.0/model-routing-removal.md`](eval-runs/v0.20.0/model-routing-removal.md)
for the migration note.

### Why

The PR-review evaluation that motivated this release showed two concrete
problems on the same prompt against the same host:

1. **Template echo.** The v0.19.0 `code-reviewer` Expected Output Contract was
   a long skeleton listing every section the agent **may** emit. Without a
   counter-pressure rule, agents treated the skeleton as a checklist and
   rendered every heading even when empty, expanded each finding into a
   seven-line sub-list, narrated the workflow they had run, and wrapped the
   verdict in banners. Real blockers were buried under template noise.
2. **Phantom model knob.** The `CODE_REVIEWER_MODEL` variable was a
   pass-through hint to "the host" that no actual host consumed. It made
   operators think a model had to be picked, polluted `.env.example` with a
   long model-id catalog that drifted out of date, and crowded the skill's
   Required Environment list with a fake variable.

v0.20.0 fixes both at the **spec** layer (where the agent reads them) and the
**validator** layer (so they cannot silently drift back). Actual rendered
output still depends on the host model — the
[`code-reviewer-concise-output`](evals/code-reviewer-concise-output.md) eval is
the place to score real transcripts against the rule.

### Not Changed (deliberate)

- The review **logic** (severity rubric, requirement-understanding gate,
  devil's-advocate paragraph, evidence-pack handoff, iteration-convergence rule)
  is unchanged. v0.20.0 is a presentation fix.
- The destructive-action safety floor is unchanged.
- The other `CODE_REVIEWER_*` knobs (`BLOCKING`, `MAX_FILES`,
  `MAX_DIFF_CHARS`, `*_SEVERITIES`, `MAX_ROUNDS`, `CACHE_*`) are real behavior
  switches and remain.

## 0.19.0 - Skill-Source Resolution And Self-Update

### Added

- New [`docs/skill-source-resolution.md`](docs/skill-source-resolution.md) — the canonical
  agent-facing reference for which skill directory to load when more than one is present on
  disk. Defines a six-step resolution order (`.agent-skills.yml` `skills.canonical_dir` →
  repo-modification context → `.agent-skills/skills/` → `.skills/` → `agent-skills/skills/` →
  ask the user when ambiguous), the duplicate-handling rules (no merging, no "load all", warn
  on version drift), and the mode-specific defaults that match what `setup.init` ships.
- New [`docs/updates.md`](docs/updates.md) — how a user who has already cloned the repo
  notices a new release and applies it. Documents three update channels (`./setup.init
  --check-updates`, `./setup.init --update`, manual `git pull`), the in-repo / vendored update
  flow, the rollback path, and how the agent surfaces drift between the loaded skill version
  and the workspace lock file.
- New [`scripts/check-updates.py`](scripts/check-updates.py) — dependency-free Python tool
  that compares the local `VERSION` (or the highest `metadata.version` under a vendored
  `skills/` directory) against the latest release tag on `origin`. Supports `--vendored`,
  `--json`, `--use-api`, `--token` (read from `--token` or `GITHUB_TOKEN`, never echoed). Exit
  codes: `0` up-to-date / ahead, `10` update available, `2` setup error.
- New `setup.init --check-updates` subcommand — same comparison as the standalone script,
  but workspace-independent. Same exit codes.
- New `setup.init --update` subcommand — fetches tags from `origin`, refuses to act on a
  dirty working tree, checks out the latest release tag (or `--branch NAME`), then re-runs
  the setup flow non-interactively to refresh `.skills` and the new `.agent-skills.lock`
  metadata file. Never pushes, never auto-updates without the explicit flag.
- New advisory `<workspace>/.agent-skills.lock` file written by every `setup.init` run.
  JSON, gitignored, schema `agent-skills.lock/v1`. Records `version`, `git_sha`,
  `canonical_dir`, `source_repo_dir`, `installed_at`, `installed_by`. Lets agents pin to a
  known version and detect drift without inspecting the source repo.
- New `skills:` block in [`.agent-skills.example.yml`](.agent-skills.example.yml) covering
  `canonical_dir`, `duplicate_policy`, `source_repo_dir`, `allow_source_repo_fallback`, and
  `warn_on_version_drift`. All keys are optional; defaults match the resolution order.
- New [`evals/skill-source-resolution-ambiguity.md`](evals/skill-source-resolution-ambiguity.md)
  eval scenario covering the exact failure mode this release targets: a workspace with both
  `.skills/` and a vendored `.agent-skills/skills/` copy at different versions, agent must
  walk the resolution order rather than merging or arbitrarily picking.
- `eval-runs/v0.19.0/` capturing the skill-source-resolution scenario and the release summary.

### Changed

- `setup.init` now writes `.agent-skills.lock` at the end of every run, surfaces a warning
  when more than one **distinct** skill source exists in the workspace without a configured
  `skills.canonical_dir`, and reports lock-file status (matched / drifted / missing) in
  `--verify`. The ambiguity check resolves symlinks before comparing, so the expected
  `.skills -> agent-skills/skills` shape is **not** flagged.
- `setup.init --help` documents `--check-updates`, `--update`, and `--branch`.
- The setup-managed `.gitignore` block now ignores `.agent-skills.lock`.
- `scripts/validate-repo.py` `REQUIRED_FILES` extended with the new docs, eval, eval-runs,
  and `scripts/check-updates.py`. New `check_agent_skills_yaml_skills_block` validation
  ensures `.agent-skills.example.yml` keeps the documented `skills:` block keys.
- `README.md`, `docs/README.md`, `docs/quickstart.md`, `docs/installation.md`,
  `docs/configuration.md`, `docs/assistants.md`, `docs/execution-modes.md`, and
  `docs/known-limitations.md` link the two new docs.
- `VERSION` and every `SKILL.md` `metadata.version` bumped to `0.19.0`.

### Why

A user who clones `agent-skills` next to other repos and runs `./setup.init` ends up with
at least two paths that contain the same `SKILL.md` files (the source clone plus the
`.skills` symlink). In-repo / cloud-agent users frequently add a third (a vendored copy at
`.agent-skills/skills/`) that may drift from the source. Agents discovering more than one
copy could load duplicate workflows, merge contradictory instructions, or silently pick the
wrong version. This release fixes that by:

- giving the agent a written, deterministic resolution order it can follow without guessing;
- giving the operator a single config key (`skills.canonical_dir`) that pins the choice;
- giving the agent a small lock file (`.agent-skills.lock`) it can read to detect drift;
- giving the user a first-class update path (`--check-updates` / `--update`) so the
  installed runtime stays close to the source repo.

### Not Changed (deliberate)

- No new top-level or nested skills.
- No skill renames; existing collaboration handoffs unchanged.
- No new required environment variables. The lock file is gitignored and advisory.
- The `.skills` directory remains a symlink (`--no-symlink` still works). No copy mode
  was added; the supported way to vendor skills is the existing `.agent-skills/skills/`
  pattern documented in `docs/installation.md`.
- `setup.init --update` never pushes, never force-resets, and never auto-runs without the
  flag.

## 0.18.0 - Jira / Confluence Auth Discovery

### Added

- New [`docs/auth-discovery.md`](docs/auth-discovery.md) — the canonical agent-facing
  reference for Jira / Confluence configuration. Defines the explicit discovery order
  (`.agent-skills.yml` → `.jira-config.yml` → `.env` / `.env.local` → process env →
  `scripts/auth-preflight.py` → ask the user), the rules for resolving `${VAR}`
  placeholders, the troubleshooting table for the most common "I can't access Jira"
  failure modes, and the CLI-independent guidance every skill must follow before
  declaring auth unavailable.
- New [`scripts/auth-preflight.py`](scripts/auth-preflight.py) — dependency-free Python
  script that loads `.env`, `.env.local`, and `.jira-config.yml`, resolves `${VAR}`
  placeholders, validates required Jira fields and optional Confluence fields, detects
  API-token-shaped values pasted into `JIRA_PROJECT_KEYS`, and reports the result without
  ever printing a secret value. Exit codes: `0` usable, `1` incomplete, `2` setup error.
  Supports `--require-jira`, `--require-confluence`, `--json`, `--show-prefix`.
- New [`evals/auth-discovery-jira-confluence.md`](evals/auth-discovery-jira-confluence.md)
  — eval scenario for the exact failure mode this release targets: workspace has both
  `.env` and `.jira-config.yml` with placeholders, agent must walk the discovery order
  rather than reporting "no Jira access" and must never echo secret values.
- `eval-runs/v0.18.0/` capturing the auth-discovery scenario and release summary.

### Changed

- `software-engineer`, `issue-investigator`, and `code-reviewer` SKILL.md files now
  carry a mandatory auth-discovery step in their Required Environment section. The
  agent must walk the documented order and run the preflight before reporting Jira /
  Confluence as inaccessible. Unresolved `${VAR}` placeholders in `.jira-config.yml`
  are explicitly classified as **incomplete configuration**, not as missing auth.
- `.env.example` Jira / Confluence sections gained a discovery-contract preamble
  explaining where real values live, where placeholders live, and how to verify
  resolution without exposing secrets.
- `.jira-config.example.yml` placeholder block now states explicitly that `${VAR}`
  placeholders are not expanded by the Jira CLI and points at the auth preflight.
- `.agent-skills.example.yml` `jira:` block links the in-repo discovery order
  (process env → this file → ask the user; no `.env`, no `.jira-config.yml`).
- `scripts/validate-repo.py` adds `check_jira_placeholder_consistency` — fails when
  `.jira-config.example.yml` references a `${VAR}` that is not declared in
  `.env.example`, so the two files cannot drift apart silently.
- `README.md`, `docs/README.md`, `docs/quickstart.md`, `docs/installation.md`,
  `docs/configuration.md`, `docs/execution-modes.md`, and `docs/known-limitations.md`
  link the new auth-discovery doc and (where appropriate) the preflight command.

## 0.17.0 - Requirement-Understanding Phase

### Added

- New shared [`docs/requirement-understanding.md`](docs/requirement-understanding.md) workflow
  defining a twelve-step requirement-understanding gate (interpret task, classify, goal,
  expected behavior, actual behavior, scope, evidence, facts/assumptions, unknowns,
  disconfirming checks, confidence, readiness) and the binding confidence-to-action rules every
  relevant skill must apply (`unknown` / `low` blocks implementation, review verdicts, pass/fail
  testing, and automation; `medium` allows planning with visible assumptions; `high` allows
  proceeding within scope).
- New [`docs/requirement-understanding-scorecard.md`](docs/requirement-understanding-scorecard.md)
  scorecard (eleven 0-3 criteria including problem framing, expected behavior clarity, evidence
  discipline, assumption handling, disconfirming checks, readiness decision correctness, and
  resistance to premature implementation).
- New [`docs/examples/requirement-understanding.md`](docs/examples/requirement-understanding.md)
  with six worked examples (clear bug, premature implementation, ambiguous ticket, conflicting
  AC, bug vs feature, security-sensitive request).
- Five new evals targeting the gate:
  [`evals/requirement-understanding-ambiguous-ticket.md`](evals/requirement-understanding-ambiguous-ticket.md),
  [`evals/requirement-understanding-conflicting-criteria.md`](evals/requirement-understanding-conflicting-criteria.md),
  [`evals/requirement-understanding-bug-vs-feature.md`](evals/requirement-understanding-bug-vs-feature.md),
  [`evals/requirement-understanding-wrong-root-cause-trap.md`](evals/requirement-understanding-wrong-root-cause-trap.md),
  [`evals/requirement-understanding-security-sensitive-request.md`](evals/requirement-understanding-security-sensitive-request.md).
- New `Requirement Understanding Gate` step in the Required Workflow of every relevant skill:
  [`software-engineer`](skills/software-engineer/SKILL.md),
  [`issue-investigator`](skills/software-engineer/skills/issue-investigator/SKILL.md),
  [`code-reviewer`](skills/software-engineer/skills/code-reviewer/SKILL.md),
  [`product-owner`](skills/product-owner/SKILL.md),
  [`manual-tester`](skills/manual-tester/SKILL.md),
  [`test-automation-engineer`](skills/test-automation-engineer/SKILL.md). Each gate emits a
  twelve-field `Requirement Understanding` block at the top of skill output, applies the binding
  confidence-to-action rules tailored to that skill, and adds a guardrail forbidding skipping the
  gate.
- `issue-investigator` now tracks **dual confidence** — root-cause confidence and
  requirement-understanding confidence — and may not recommend at higher than the lower of the
  two.
- `eval-runs/v0.17.0/` capturing the requirement-understanding multi-skill scenario and release
  summary.

### Changed

- `README.md`, `docs/README.md`, `docs/quickstart.md`, `docs/starter-prompts.md`,
  `docs/skill-boundaries.md`, `docs/validation.md`, and `docs/examples/README.md` updated to
  reference the requirement-understanding gate and scorecard.
- `scripts/validate-repo.py` `REQUIRED_FILES` extended with the new docs, evals, and eval-runs.
- `.gitignore` now ignores `.claude/` editor state.

## 0.16.0 - Safety-Acknowledgement Artifact And Credential Blast-Radius Probe

### Added

- New `safety_acknowledgement` block in
  `references/definition-of-done.md` schema. `software-engineer` Phase 5.3
  now writes it whenever the change introduces or performs any mutating
  action against a deployed environment, or touches credentials / IAM /
  secrets / backups / monitoring / network policy. The block captures
  environment, how it was confirmed (a concrete pointer, not a guess),
  the credential used and its source (`host-secret-manager` /
  `env-var` / `user-session`), the blast radius, the execution path
  (`agent` / `ci-pipeline` / `operator-runbook` / `not-applicable`),
  explicit `no_discovered_credentials_invoked` and
  `no_in_repo_tokens_invoked` flags, backup-isolation status, and
  monitoring/IAM/network-policy unchanged flags.
- `code-reviewer` hard handoff contract requires the
  `safety_acknowledgement` block whenever the diff touches a deployed
  environment, credentials, IAM, secrets, backups, monitoring, or
  network policy. The reviewer surfaces a `blocker` finding when the
  block is missing on a diff that obviously requires it, when a
  discovered/in-repo credential was invoked, when a destructive command
  was used without a populated authorization
  (approver + ticket + runbook_path), when `execution_path: agent` for
  a destructive/IAM/secret/backup change, when monitoring/IAM/network
  policy was changed without a written waiver, when `environment:
  production` is paired with `execution_path: agent`, or when
  `backup_restore_tested` is null/older than 90 days for a runbook that
  depends on restore.
- `setup.init` gains a warn-only **credential blast-radius probe** that
  runs at the end of first setup and on `setup.init --verify`. It
  scans the configured `.env` and the current shell for
  destructive-capable cloud / orchestrator / database credentials
  (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`,
  `GOOGLE_APPLICATION_CREDENTIALS`, `GCP_SERVICE_ACCOUNT_KEY`,
  `AZURE_CLIENT_SECRET`, `DIGITALOCEAN_TOKEN`, `DO_API_TOKEN`,
  `LINODE_TOKEN`, `HCLOUD_TOKEN`, `KUBECONFIG`, `DATABASE_ADMIN_URL`,
  `POSTGRES_ADMIN_PASSWORD`, `MONGODB_ADMIN_URI`, others) and warns the
  operator to scope them to a least-privilege role with no delete-bucket
  / terminate-instance / drop-database / delete-snapshot / IAM-modify /
  backup-mutation privileges. The probe cannot inspect cloud-provider
  IAM policies — it flags the *presence* of broad credentials so the
  operator can confirm scoping in the provider console. Skip with
  `--no-credential-probe`.
- `eval-runs/v0.16.0/` directory with `summary.md` and the
  `safety-ack-and-cred-probe.md` scenario evaluating the new artifact
  and probe against the `v0.15.0` failure-mode chain.

### Changed

- `software-engineer/SKILL.md` Phase 5.3 ("Definition-of-Done artifact")
  has a new checklist item enforcing the `safety_acknowledgement`
  writeback (with the omit-when-not-applicable escape: `applies: false`
  + one-line reason for purely local changes).
- `references/definition-of-done.md` Rules section adds explicit
  reviewer-blocking conditions for the new block, including the
  "missing on a diff that obviously requires it" case (changes to IaC,
  CI deployment, IAM, secret stores, migrations, or any cloud-provider
  command).
- `docs/destructive-action-safety.md` gains an
  "Enforcement artifacts" section documenting the
  `safety_acknowledgement` block and the `setup.init` credential probe
  as the two concrete artifacts that reinforce the policy.
- `setup.init` `--help` and flag parsing add `--no-credential-probe`
  alongside the existing `--no-connectivity-check` flag.
- `VERSION`, README status line, and all six `SKILL.md`
  `metadata.version` values bumped to `0.16.0`.

### Why

`v0.15.0` introduced the destructive-action safety floor as policy +
SKILL content. The two follow-ups in this release operationalise that
policy at two new points:

- The reviewer now has a structured artifact to gate on, not just prose
  in the SKILL.md. A diff that touches a deployed environment cannot
  reach `PASS` without an explicit, machine-checkable acknowledgement
  that the engineer used scoped credentials, did not invoke discovered
  or in-repo tokens, confirmed the environment via a concrete pointer,
  isolated backups, and is not asking the agent itself to execute the
  destructive step.
- The operator now sees a warning at `setup.init` time when the shell
  or `.env` carries credentials that a future agent process would
  inherit and that, combined with the failure mode in `v0.15.0`, would
  let the agent perform destructive cloud operations. The probe is
  warn-only and heuristic; it does not promise to catch every misscope.
  It does promise to surface the most common cases (long-lived AWS
  access keys, broad kubeconfig, admin DB URIs) at a moment when the
  operator can act.

### Not Changed (deliberate)

- No new top-level or nested skills.
- No skill renames; existing collaboration handoffs unchanged.
- No new required environment variables (the probe reads the existing
  `.env` and the current shell). No `.env.example` change.
- The probe does not block setup, fail CI, or touch state. It is
  intentionally warn-only because IAM scoping cannot be inferred from
  a shell variable name alone.
- The `safety_acknowledgement` block is intentionally optional for
  purely local changes (`applies: false` with a one-line reason) so the
  artifact does not become busywork on docs/refactor/format diffs.

## 0.15.0 - Destructive-Action Safety Floor

### Added

- New top-level policy document `docs/destructive-action-safety.md`
  defining the single source of truth that every skill in this repository
  inherits. Covers: scope and precedence, definitions of "production",
  "destructive action", "discovered credential" vs "authorized credential",
  the prohibited-autonomous-actions hard floor, the read-only-by-construction
  default, the human-controlled-execution contract, the production boundary,
  backup isolation, the discovered-credential protocol, the
  "fix by deletion" anti-pattern, the operator-runbook contract, the
  authorization protocol for legitimate destructive maintenance, and a
  per-skill self-check.
- New `## Destructive Action Guardrails` section in
  `software-engineer/SKILL.md`. Operationalises the policy for engineering
  work: default mode is safe / minimal / non-destructive; never invoke
  discovered credentials; never search the repo *for* credentials in order
  to act; environment must be confirmed (`local`/`dev`/`staging`/
  `production`) before any state-mutating step; destructive commands are
  blocked unless the task is explicitly authorized destructive maintenance
  with a recorded approver, isolated backups, and a human-controlled
  execution path; bug fixing prefers root cause / config / safe migration
  over fix-by-deletion; if the fix appears to require production mutation
  the agent stops and produces a risk-assessed operator runbook instead of
  executing.
- New "Discovered-credential protocol" subsection in
  `issue-investigator/SKILL.md` Step 4: discovered credentials are evidence
  of a leak, not authorization to act; never invoke; never echo full value;
  surface as `blocker`/`major` finding; recommend rotation through the
  organisation's normal channel.
- New "Agent-execution safety (destructive-action policy)" sections in
  `references/code-review-checklist.md` and `references/security-checklist.md`
  with concrete blocker review items: hardcoded secrets, code that invokes
  discovered credentials, destructive cloud / orchestrator / database
  commands targeting production, backup mutation, monitoring-disabling, and
  unconfirmed environment classification.
- `eval-runs/v0.15.0/` directory with `summary.md` and the
  `production-volume-incident.md` scenario evaluating the new floor against
  the documented public failure mode (agent finds a token in the repo and
  uses it to delete production volume / backups).

### Changed

- All six `SKILL.md` files now carry an explicit "Safety floor" callout
  near the top that links to the policy and states the skill-specific
  operational consequences:
  - `software-engineer`: defaults to safe / minimal / non-destructive,
    must not use discovered credentials, must distinguish environments,
    production-impacting actions require human-controlled execution.
  - `issue-investigator`: read-only by default; every proposed check is
    classified `read-only` or `mutating`; mutating checks are not proposed
    by this skill (they belong in a `software-engineer` runbook); never
    asks the user to paste secrets into chat.
  - `code-reviewer`: must surface as `blocker` any diff that ships
    discovered hardcoded secrets, invokes credentials read from repo
    files, runs destructive cloud/orchestrator/db commands against
    production, weakens IAM/network/secret/backup controls, or proposes
    fix-by-deletion of live data — regardless of how the PR description
    frames it.
  - `manual-tester`: tests against deployed environments default to
    read-only / sandbox / ephemeral; discovered credentials are reported
    as `blocker` defects and never invoked; secrets are never pasted into
    chat or test artifacts.
  - `test-automation-engineer`: automated tests must not run destructive
    commands against production; tests that delete/drop/truncate run only
    against ephemeral targets the suite owns and that are isolated from
    any production backup path.
  - `product-owner`: acceptance criteria must not require an agent to run
    destructive production commands, mutate live customer data, modify
    production credentials, or delete backups; such stories must be split
    so the destructive step is an explicit operator runbook handed off
    out of the agent loop.
- `software-engineer/SKILL.md` Stopping Conditions add two new triggers:
  the proposed fix path requires destructive production action, or a
  credential was discovered that is not the agent's authorized credential.
- `issue-investigator/SKILL.md` "Safe read-only checks the user can run":
  every proposed check must now be classified `read-only` or `mutating`
  out loud (indeterminate is treated as `mutating` and not proposed).
  Output contract gains an explicit `Classification:` line.
- `README.md` and `docs/README.md` link to the new policy as a top-level
  reference.
- `scripts/validate-repo.py` REQUIRED_FILES list adds
  `docs/destructive-action-safety.md` so the policy file cannot be
  accidentally removed without breaking CI.

### Why

Production-grade response to a publicly reported failure mode in which an
AI coding agent investigated a problem, discovered a production-capable
token in a checked-in file, used it to call the cloud provider, and caused
the destruction of a production volume and its backups. The failure was
not solely a model lapse — it was the combination of excessive permissions,
in-repo secrets, destructive privileges on the same identity used to read
the codebase, no environment confirmation, no human-controlled execution
boundary, and no backup isolation. Prompt-level "be careful" instructions
are necessary but not load-bearing. After this release, every skill in this
repository inherits the same explicit floor: discovered credentials are
evidence of a leak (never authorization to act), production mutation is a
human-controlled runbook (never an agent invocation), backups are a
separate protected asset, and the floor is not waivable by user prompt.

### Not Changed (deliberate)

- No new top-level or nested skills.
- No skill renames; existing collaboration handoffs (evidence-pack and
  definition-of-done schemas) are unchanged.
- No new environment variables, no `setup.init` change, no `.env.example`
  change, no CI workflow change beyond the validator REQUIRED_FILES line.
- The four affected SKILLs from `0.14.0` (project-documentation discovery)
  are unchanged in their existing content; they only inherit the new floor.
- `VERSION`, README status line, and all six `SKILL.md` `metadata.version`
  values bumped to `0.15.0`.

## 0.14.0 - Mandatory Project-Docs Discovery (README / CONTRIBUTING / Per-Module README)

### Changed

- `software-engineer/SKILL.md` Phase 1.2 ("Identify the project") now requires
  reading the repository `README.md` and `CONTRIBUTING.md` (and any `docs/`
  setup pages they link to) **before** falling back to the build manifest.
  `${PROJECTS_JSON}` / `.agent-skills.yml` still own the canonical commands,
  but the README is now treated as the source of truth for *prerequisites*
  those commands silently assume (Docker services, fixture generators, env
  vars, profile flags, generated sources, license keys).
- `software-engineer/SKILL.md` Phase 1.2 adds an explicit checklist item for
  **multi-module / nested-submodule repositories**: the agent must read each
  affected module's own `README.md` before invoking that module's build or
  tests. Module-level setup is frequently documented only at the module
  level and is invisible from the parent README or the build manifest. This
  is the most common cause of "tests fail before any change is made"
  reports.
- `software-engineer/SKILL.md` Phase 3.3 ("Build & format") gains two new
  guardrails: a **pre-flight before invoking the test command** that
  verifies README-documented setup has been performed, and a
  **diagnose-before-blame rule** for failing tests on a clean tree (re-read
  README/CONTRIBUTING, check `.github/workflows/` for the exact CI command
  and `services:`/`env:` setup, scan output for missing-prereq signals
  before reporting the suite as broken).
- `issue-investigator/SKILL.md` Step 4 ("Investigate evidence") makes
  project documentation a first-class evidence source: read repository and
  per-module READMEs and `CONTRIBUTING.md` before guessing root cause.
  Documented-but-unmet prerequisites are reclassified from "defect" to
  "environment setup gap".
- `manual-tester/SKILL.md` Step 1 ("Align on intended behavior") requires
  reading repository / per-module READMEs before declaring the environment
  blocked or test data missing — a documented prerequisite is a setup gap,
  not a blocker on the change under test.
- `test-automation-engineer/SKILL.md` Step 3 ("Reuse engineering context")
  requires reading repository, `CONTRIBUTING.md`, and per-module READMEs of
  any module whose tests will be added or changed, so automation matches the
  documented test runner, services, profile flags, and conventions.
- `software-engineer/references/architecture-patterns.md` "Discovering
  project-specific conventions" now leads with README + CONTRIBUTING and
  promotes per-module READMEs to a top-level step, with a short note on why
  CI workflows are also required reading (`services:` / `env:` blocks that
  local docs may omit).

### Why

Production-grade response to a real failure mode: an agent ran tests in a
nested-submodule project, the tests failed because a module-specific test
infrastructure step documented in the per-module README was not performed,
and the agent reported "tests are broken" instead of completing setup. The
README discovery instruction existed only as one line of narrative inside
"Context discovery" and was not present as a hard checklist item in any
phase, nor before the build/test command, nor in the sibling skills. After
this release, the four affected skills (`software-engineer`,
`issue-investigator`, `manual-tester`, `test-automation-engineer`) all
treat repository and per-module documentation as required first-pass
context, and `software-engineer` Phase 3.3 specifically forbids reporting
test failure on a clean tree before the documentation ladder has been
walked.

### Not Changed (deliberate)

- No new top-level or nested skills.
- No skill renames or contract changes; evidence-pack and definition-of-done
  schemas are unchanged.
- `code-reviewer` is intentionally not modified — the reviewer consumes the
  engineer's evidence pack and inherits the new discovery discipline through
  the engineer↔reviewer hard handoff contract that was introduced earlier.
- No new environment variables, no `setup.init` changes, no `.env.example`
  changes, no CI changes — pure SKILL content sharpening.
- `VERSION` and all six `SKILL.md` `metadata.version` values bumped to
  `0.14.0`.

## 0.13.0 - Investigator Environment Access, Sonar In Setup, Connectivity Check, Reviewer-Model Clarity

### Added

- `setup.init` learns four new optional flags: `--with-sonar` /
  `--no-sonar` and `--with-environments` / `--no-environments`. Both flows
  also have an interactive opt-in prompt for users who run `setup.init` with
  no flags.
- `setup.init` runs an opt-in non-blocking connectivity probe (`curl --head`,
  5 s timeout) against `JIRA_HOST`, `CONFLUENCE_HOST`, and `SONAR_HOST_URL`
  when those are configured. Any HTTP response (including 401/403) counts
  as reachable; connection errors print a `WARN` and never fail setup.
  Use `--no-connectivity-check` on captive networks / VPNs.
- `SONAR_HOST_URL` and `SONAR_TOKEN` are now setup-managed keys and live
  inside the `# >>> agent-skills setup.init` marker block in `.env`. The
  prior unmanaged placeholders in `.env.example` are removed; the loader's
  "last assignment wins" rule no longer creates silent overrides.
- `ENVIRONMENTS_JSON` is a new optional setup-managed key. It is a JSON
  array of read-only POINTERS (env name, type, access method, ssh target,
  kubectl context, namespace, log paths, log-aggregator URL, notes) to the
  deployed environments where issues actually occur. Credentials are never
  stored — SSH keys stay in `~/.ssh`, cluster credentials in kubeconfig,
  log-aggregator login in the user's session.
- `issue-investigator` SKILL.md gains a new **Environment evidence access**
  subsection that treats `ENVIRONMENTS_JSON` as a first-class evidence
  channel for production and regression issues, with explicit per-access
  read-only command lists (ssh, kubectl, log-aggregator, cloud-console),
  a `propose-do-not-run` default for `type: prod`, and a strict credentials
  boundary. New guardrails forbid running commands against `prod` without
  explicit approval and forbid copying secrets into agent-skills files.
- `issue-investigator` Output Contract now includes an **Environment
  evidence** line under `Evidence Reviewed` so live-environment proof is
  recorded the same way as ticket and code evidence.
- `setup.init --verify` checks `SONAR_HOST_URL`/`SONAR_TOKEN` pairing and
  validates `ENVIRONMENTS_JSON` parses.

### Changed

- `.env.example` rewrites the `CODE_REVIEWER_MODEL` comment block. The
  literal value `"default"` is now documented as a SENTINEL meaning
  "use the host's default model routing." The misleading "uncomment the
  one you want" wording is removed; users are told to *replace the value*
  with one of the listed model ids and given an explicit override example.
- `scripts/validate-repo.py` and the CI smoke test add `SONAR_HOST_URL`,
  `SONAR_TOKEN`, and `ENVIRONMENTS_JSON` to the setup-managed-key list, so
  the marker-block discipline introduced in 0.11.0 also covers the new
  keys.
- `docs/configuration.md` documents the new keys and the `default`
  sentinel for `CODE_REVIEWER_MODEL`.
- `VERSION` and all six `SKILL.md` `metadata.version` values bumped to
  `0.13.0`.

### Not Changed (deliberate)

- No new top-level or nested skills.
- No skill renames; investigator/code-reviewer/software-engineer hand-off
  contract is unchanged.
- `ENVIRONMENTS_JSON` defaults to `[]`. Users who don't opt in see no
  behavioural change in `issue-investigator`; the existing "Safe read-only
  checks the user can run" path remains the fallback.
- No credentials are introduced into `.env`. Pointers only.

## 0.12.0 - Workspace-Root Prompt Clarity

### Changed

- `setup.init` workspace-root prompt now states explicitly that the answer
  is the **parent folder of your `agent-skills` clone and any sibling repos
  it should manage** (example: `/path/to/work` containing `agent-skills/`,
  `repo-a/`, `repo-b/`). Removes the prior wording that some users read as
  "copy `agent-skills` into a new workspace folder."
- `docs/installation.md` and `docs/quickstart.md` add a one-paragraph
  clarification to the local-workspace section restating the same
  expectation in the same words as the prompt, so prompt and docs no longer
  drift.
- `VERSION` and all `SKILL.md` `metadata.version` values bumped to `0.12.0`.

### Not Changed (deliberate)

- No `SKILL.md` content changed.
- No new top-level or nested skills.
- No changes to setup-managed keys, marker-block discipline, validators, or
  CI behaviour introduced in 0.11.0.

## 0.11.0 - Setup Flow Hardening

### Added

- `setup.init` now prompts with help text that states REQUIRED-WHEN, gives an
  EXAMPLE, and indicates whether a value is optional or whether blank is
  allowed. Secret prompts state explicitly that input is hidden and that the
  value is written only to the gitignored `.env`.
- Auto-population of setup values:
  - `ORG_NAME` is inferred from the Jira host (e.g. `acme.atlassian.net` ->
    `Acme`), then from the GitHub org, then from the workspace root.
  - `ORG_DOMAIN` is inferred from the Jira login email, the Jira host, or the
    GitHub org.
  - The Confluence host is inferred from the Jira host (Atlassian Cloud uses
    `<host>/wiki`; self-hosted `jira.<domain>` becomes `confluence.<domain>`).
  - The Jira project key is extracted from a pasted ticket key (`ABC-123`) or
    ticket URL (`/browse/ABC-123`).
- Optional Confluence configuration: `CONFLUENCE_HOST`, `CONFLUENCE_LOGIN`,
  `CONFLUENCE_API_TOKEN`, `CONFLUENCE_SPACE_KEYS`. New flags
  `--with-confluence` / `--no-confluence` and matching verify output.
- Input validators in `setup.init`: URL shape, email-or-login shape, Jira
  project-key shape, and an explicit rejection of API-token-shaped values
  when project keys are requested.
- `scripts/validate-repo.py` `check_env_example_marker_block`: fails CI if any
  setup-managed key (`ORG_NAME`, `WORKSPACE_ROOT`, `PROJECTS_JSON`, `JIRA_*`,
  `CONFLUENCE_*`) is defined outside the `# >>> agent-skills setup.init` ...
  `# <<< agent-skills setup.init` block in `.env.example`.
- `setup.init --verify` now reports "no duplicate managed keys" and "Confluence
  credentials present" when applicable.
- `eval-runs/v0.11.0/` with the release summary and the
  `setup-flow-hardening.md` scenario.

### Changed

- `.env.example` restructured so every setup-managed key lives inside the
  marker block. Non-managed keys (code-reviewer overrides, build tooling
  hints, etc.) remain outside the block and are preserved across reruns.
- `setup.init` strips legacy duplicate setup-managed keys defined outside the
  marker block during a one-time migration on rerun, reporting how many
  duplicates it removed.
- `setup.init` sets `chmod 600` on generated `.env` and `.jira-config.yml`.
- `.agent-skills.example.yml` now documents `org_domain`, the optional
  `confluence` block, and richer Jira metadata (`project_keys`, `login`,
  `auth_type`). Secrets are still injected via host environment variables.
- `docs/configuration.md`, `docs/installation.md`, `docs/quickstart.md`, and
  `docs/execution-modes.md` updated for the new managed-block discipline,
  Confluence support, and inference behaviour.
- CI workflow exercises a `--with-confluence` non-interactive flow and
  asserts no duplicate managed keys appear in `.env` after rerun.
- `VERSION` and all `SKILL.md` `metadata.version` values bumped to `0.11.0`.

### Fixed

- Root cause of duplicated `PROJECTS_JSON`, `JIRA_HOST`, `JIRA_API_TOKEN`,
  `JIRA_LOGIN`, and `JIRA_PROJECT_KEYS` keys in `.env`: the previous
  `.env.example` contained literal definitions of those keys outside the
  generated marker block, so copying the example and then writing the
  generated block produced two definitions per key. The example now keeps
  exactly one definition per key, inside the block.
- `setup.init` no longer renders an empty `JIRA_*` block when Jira is
  declined; it emits explicit empty assignments inside the marker block so
  the variables are always defined and the order is deterministic.

### Not Changed (deliberate)

- No `SKILL.md` content changed.
- No new top-level or nested skills.
- No changes to the eval scoring rubric.
- Local-workspace and in-repo modes remain the only two supported execution
  modes.

### Security

- Secrets (Jira API token, Confluence API token) are read with hidden input
  and never echoed.
- Generated files containing or potentially containing secrets are written
  with `0600` permissions.
- Workspace `.gitignore` continues to ignore `.env`, `.env.local`,
  `.env.*.local`, `.jira-config.yml`, `.skills`, and `.cache/`.
- Examples and templates use `acme.example.com` / `example.org` placeholders
  only.

## 0.10.0 - Eval-Driven Skill Improvements

### Added

- `code-reviewer` workflow step "Record review limitations explicitly" plus a
  matching `Review Limitations / Unavailable Context` section in the output
  contract. A bare `PASS` verdict is now disallowed while review-limitation
  items are non-`none`.
- `issue-investigator` workflow subsection "Safe read-only checks the user
  can run" plus a matching `Safe Checks The User Can Run` block in the output
  contract. Each suggested check must be read-only by construction, bounded,
  labelled with the safe environment, and tied to a specific hypothesis.
- Two deeper eval scenarios under `evals/` exercising realistic incomplete
  context: `issue-investigator-read-only-investigation.md` and
  `code-reviewer-unavailable-context.md`.
- `eval-runs/v0.10.0/` with the matching scored runs and a release summary.
- Three explicit eval-run categories in `eval-runs/README.md` (illustrative,
  real model transcript, future automated). Every new eval-run file must
  declare its category.

### Changed

- `code-reviewer` and `issue-investigator` behavior checklists updated to
  require the new sections to be filled.
- `issue-investigator` guardrails extended to forbid mutating or unbounded
  checks being labelled "safe".
- Updated `VERSION`, README status, and all skill metadata to `0.10.0`.
- Validator `REQUIRED_FILES` extended to require the new eval scenarios and
  the v0.10.0 eval-run files.

### Not Changed (deliberate)

- No new skills.
- No nested skill promoted to the top level.
- Skill philosophy was not rewritten. The two skill changes are wording-level
  additions that the v0.9.0 eval runs explicitly recommended as future work.
- No real model transcripts captured this release; the category exists but
  populating it is a future-release task.
- Eval runs still do not gate CI.

## 0.9.0 - Real Eval Runs and Scored Skill Outputs

### Added

- `eval-runs/` directory with a release-scoped subdirectory `eval-runs/v0.9.0/`
  containing scored sample runs for each skill plus a multi-skill chained flow.
- A summary file aggregating per-skill scores, common strengths, common gaps,
  and follow-up actions.
- An `eval-runs/README.md` that describes the practice, scoring method, and
  public-safety rules, and clearly labels the v0.9.0 transcripts as
  illustrative maintainer-authored examples.

### Changed

- `docs/validation.md`, `docs/release-checklist.md`, and
  `docs/skill-performance-review.md` now reference eval-runs as the maintainer
  evidence trail.
- `README.md` documentation index links to `eval-runs/`.
- Updated `VERSION`, README status, and all skill metadata to `0.9.0`.
- Validator `REQUIRED_FILES` extended to ensure the v0.9.0 eval-run files exist.

### Not Changed (deliberate)

- No new skills added.
- No nested skill promoted to the top level.
- Skill wording was not rewritten purely to chase higher eval scores; gaps
  surfaced during eval runs are recorded for future releases.

## 0.8.2 - Physical Source Formatting Fix

### Changed

- Replaced remaining wide Markdown tables in `README.md`,
  `docs/skill-performance-review.md`, `skills/software-engineer/SKILL.md`, and
  `skills/software-engineer/skills/issue-investigator/SKILL.md` with readable
  per-item sections so no Markdown line exceeds the new 200-character limit.
- Updated `VERSION`, README status, skill metadata, and release checklist for
  `0.8.2`.

### Fixed

- Tightened `scripts/validate-repo.py` line-length limits to 200 characters for
  Markdown and source files and lowered the source long-line warning threshold
  to 140 characters.
- Added a Markdown file-density check that fails files where the byte-per-line
  ratio shows the file is physically compressed.
- Added a YAML minification check that fails when multiple top-level keys
  collapse onto one physical line or when inline flow values look minified.
- Added a Python minification check that fails on multiple statements per line.

## 0.8.1 - Source Formatting and Release Hygiene

### Changed

- Reformatted Markdown bodies across the README, changelog, docs, evals, skill files, and support
  docs so raw GitHub view and Git diffs remain readable.
- Reformatted `SKILL.md` YAML frontmatter to use folded scalars for long descriptions and
  compatibility text.
- Replaced overwide Markdown tables in docs and skill environment sections with readable lists where
  table rows made raw source hard to review.
- Updated `VERSION`, README status, and skill metadata for `0.8.1`.

### Fixed

- Moved the v0.8.0 validation/evaluation entries out of `Unreleased` into the released v0.8.0
  changelog section.
- Strengthened `scripts/validate-repo.py` so CI fails on maintainability issues such as overlong
  Markdown lines, mid-line headings, collapsed table rows, and mid-line code fences.
- Added readability checks for YAML and Python source lines.
- Updated the release checklist with raw README, table-rendering, changelog hygiene, and validator
  line-readability checks.

## 0.8.0 - Validation, Evaluation, and Skill Performance Hardening

### Added

- **`scripts/validate-repo.py`** for repository-wide validation of required files, Markdown
  structure, balanced code fences, internal relative links, skill frontmatter, required skill
  sections, version consistency, cross-skill links, forbidden public-safety content, and tracked
  generated/cache files.
- **`docs/validation.md`** explaining what validation checks, what it does not check, how to run it,
  and how to interpret warnings vs failures.
- **`evals/`** with lightweight manual scenarios for `issue-investigator`, `code-reviewer`,
  `software-engineer`, `product-owner`, `manual-tester`, `test-automation-engineer`, and a multi-skill
  bug-to-regression workflow.
- **`docs/skill-quality-scorecard.md`** with a simple `0` to `3` maintainer scoring aid for skill
  outputs across context awareness, evidence discipline, handoffs, output completeness, hallucination
  avoidance, validation realism, risk awareness, stopping behavior, and portability.
- **`docs/skill-performance-review.md`** recording the v0.8.0 manual review findings and the
  workflow checks for bug fix, feature delivery, and PR review paths.
- **`docs/release-checklist.md`** covering validation, README rendering, skill links, changelog and
  version updates, examples/evals, secrets/private-reference review, GitHub release notes, tags, and
  funding-link rendering.

### Changed

- Updated CI to run the broader repository validator instead of only skill frontmatter checks.
- Kept `scripts/validate_skills.py` as a backward-compatible wrapper around the repository
  validator.
- Added behavior checklists to all six skills so expected behavior can be reviewed independently of
  the longer workflows.
- Bumped `VERSION`, README status, and all skill metadata versions to `0.8.0`.
- Generalized `software-engineer` issue-source wording so non-Jira issue sources and supplied task
  briefs are handled without implying a private workflow.
- Clarified `product-owner` behavior for bug-flavored input: unknown-root-cause work should become
  investigation/discovery, not a fix-ready story.
- Aligned `issue-investigator` and `code-reviewer` execution-mode detection with
  `AGENT_SKILLS_MODE`.
- Softened the `test-automation-engineer` flake-budget rule into a default target with a disclosed
  fallback when CI/tooling cannot support repeat execution.

### Guardrails

- Validation now fails on likely committed secrets, private absolute paths, missing required skill
  structure, malformed metadata, broken relative links, and version mismatches.
- Validation warns on suspicious hostnames, possible real email/customer data, hardcoded ticket
  keys, README/version drift, and local generated/cache files that lack ignore coverage.
- Documentation explicitly states that validation and scorecards do not guarantee AI model
  correctness.

## 0.7.0 - Skill Output Contracts, Examples, and Operational Behavior Hardening

### Added

- **Expected output contracts for all six skills** so agents produce predictable summaries,
  evidence, validation notes, handoffs, and final status/verdict fields.
- **`docs/examples/`** with one realistic, portable example per skill covering input prompt,
  assumed context, expected behavior, sample output structure, and what to avoid.
- **`docs/starter-prompts.md`** with copy-paste prompts for each skill plus multi-skill workflows
  (`product-owner -> software-engineer -> manual-tester -> test-automation-engineer`,
  `issue-investigator -> software-engineer -> code-reviewer`, and `manual-tester defect ->
  issue-investigator -> test-automation-engineer`).
- **`docs/skill-boundaries.md`** documenting role ownership, handoff rules, nested support-skill
  rationale, and possible future top-level criteria for `issue-investigator` and `code-reviewer`.
- **`docs/severity-and-confidence.md`** defining `blocker`, `major`, `minor`, `nit`,
  `low`/`medium`/`high` confidence, and issue-investigator root-cause statuses (`unknown`,
  `suspected`, `confirmed`, `disproved`).
- **`docs/README.md`** as a documentation index for quickstart, prompts, examples, boundaries,
  severity/confidence, limitations, and versioning.

### Changed

- Hardened all skill docs with explicit `When Not To Use` and `Stopping Conditions` sections where
  they were missing.
- Made cross-skill reuse rules explicit: engineering invokes investigation for unclear issues and
  review at gates; review invokes investigation when ticket/root-cause context is weak; manual testing
  hands reproducible defects to investigation; automation consumes stable manual/repro scenarios;
  product ownership routes bug-flavored input through investigation.
- Updated `code-reviewer` verdicts to `PASS`, `PASS_WITH_NOTES`, `REQUEST_CHANGES`,
  `NEEDS_CONTEXT`, and `NOT_REVIEWABLE`.
- Aligned public docs and skill metadata with release `0.7.0`.

### Guardrails

- Reinforced public usability disclaimers across skills: do not invent evidence, distinguish facts
  from assumptions, stop when context is insufficient, do not claim tests were run unless actually
  run, do not confirm root cause without evidence, and do not assume private company standards.

## 0.6.1 - Documentation Rendering and Public Usability Fixes

### Added

- **`docs/quickstart.md`** — short first-time user path covering what the repository is, when to use
  it, how to invoke one skill manually, both execution modes, and starter prompts for the four
  top-level skills.
- **`docs/known-limitations.md`** — public limitations for non-deterministic agent behavior,
  nested-skill support, external access, company-specific standards, human review, cache behavior, and
  no-warranty/no-SLA expectations.
- **`docs/versioning.md`** — pre-1.0 and post-1.0 versioning policy. Before `v1.0.0`, minor releases
  may change structure or output contracts; patch releases should focus on docs, formatting,
  compatibility, examples, validation fixes, and non-breaking clarifications.

### Changed

- Reformatted Markdown and YAML files so raw files and diffs are readable: headings, lists, tables,
  code fences, frontmatter, configuration templates, skill files, support docs, and reference docs.
- Replaced the broken README skills table and collaboration diagram with a GitHub-renderable table
  that clearly distinguishes the four top-level skills from the two nested support skills.
- Added README links to the quickstart, known limitations, and versioning policy.
- Polished `SUPPORT.md` and `GOVERNANCE.md` to keep solo-maintainer boundaries while using a more
  neutral public tone.
- Updated the skill validator fallback parser so CI can validate multi-line frontmatter even when
  PyYAML is unavailable.
- Bumped release-prep version references from `0.6.0` to `0.6.1`.

## 0.6.0 - In-Repo Execution Mode (Online / Cloud Agent Support)

Until now the project assumed every user runs an AI assistant locally with `agent-skills` cloned
alongside their other repos. Cloud / online agents (GitHub Copilot coding agent on github.com,
Cursor cloud, Devin, Codex, Codespaces, Gitpod, Claude.ai web with the repo attached) operate inside
a single target repository — no sibling `agent-skills` checkout, no `setup.init` shell access, no
`${WORKSPACE_ROOT}/.env`. v0.6.0 makes this a first-class second mode instead of an undocumented
edge case.

### Added

- **`docs/execution-modes.md`** — single source of truth for the two modes (`local-workspace` and
  `in-repo`), how skills detect which one applies, and the variable-resolution order each uses.
- **`.agent-skills.example.yml`** — committed-to-repo configuration template for `in-repo` mode.
  Holds the single `project:` block and the org/github/jira-host metadata previously read from `.env`.
  Contains **no secrets**; credentials still come from environment variables injected by the host
  platform.
- README install section now documents both paths explicitly: "Local workspace" (the existing
  `setup.init` flow) and "In-repo" (the new path for online agents).
- `docs/installation.md` opens with an "in-repo install" section for cloud-agent users.
- `docs/configuration.md` documents the `.agent-skills.yml` schema, the precedence order (env → file
  → repo-file inference → stop), and the cache-path resolution.
- `docs/assistants.md` adds a section covering GitHub Copilot coding agent, Cursor cloud,
  Devin/Codex, Codespaces/Gitpod, and Claude.ai web.

### Changed

- **All 6 SKILL.md preflight blocks** updated to detect mode (`AGENT_SKILLS_MODE` →
  `${WORKSPACE_ROOT}/.env` → `.agent-skills.yml` → stop), then resolve required values in
  `local-workspace` or `in-repo` mode without assuming `${WORKSPACE_ROOT}/.env` exists. The "Missing
  required setup" error message now points at whichever config file matches the detected mode.
- **All 6 SKILL.md `compatibility:` frontmatter** rewritten to declare both modes and link to
  `docs/execution-modes.md`.
- **All cache-path references** in skills and reference docs changed from the hardcoded
  `${WORKSPACE_ROOT}/.cache/agent-skills/...` to
  `${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills/...}` — works in both
  modes; can be overridden by setting `AGENT_SKILLS_CACHE_DIR`.
- README status banner bumped to `0.6.0`. All SKILL.md `metadata.version` bumped to `0.6.0`.

### Not changed

- `setup.init` behaviour and the `local-workspace` install path are unchanged. v0.5.0 setups
  continue to work as-is.

## 0.5.0 - Evidence Pack, Definition of Done, Honest Contribution Framing

The infrastructure half of the v0.4.0 plan (G1, G2, G9, G10) plus an honesty pass on the
contribution/governance/support docs.

### Added

- **`skills/software-engineer/references/evidence-pack.md`** — the schema for `evidence-pack.yml`
  and `repro-recipe.yml`. Cached at `${WORKSPACE_ROOT}/.cache/agent-skills/<issue-key>/`. Defines what
  each skill reads and writes so `issue-investigator`, `software-engineer`, `code-reviewer`,
  `manual-tester`, `test-automation-engineer`, and `product-owner` stop re-deriving context on every
  hop.
- **`skills/software-engineer/references/definition-of-done.md`** — the schema for
  `definition-of-done.json`, the Phase 5 gate artifact the reviewer must verify before declaring
  `PASS`. Includes bug-fix-specific fields (regression-test commit, fails-on-parent, passes-on-head,
  observability_added) and operational hygiene flags (`no_no_verify`, `branch_starts_with_ticket_key`,
  `no_unrelated_files`).
- **`software-engineer` Phase 5.3 — Definition-of-Done artifact step.** The engineer now writes the
  DoD JSON before opening the PR; `--no-verify` is explicitly forbidden without a written waiver.
- **`software-engineer` Phase 1.4 + 1.5** persist the 5-line plan and reference the repro recipe
  path in the evidence pack.
- **`code-reviewer` hard handoff contract** now reads from the on-disk evidence pack and DoD
  artifact and surfaces specific missing fields as `major` findings; any `false` flag in the DoD
  without a waiver is itself a `blocker`.
- **`issue-investigator`** now persists the full investigation result and repro recipe to the cache
  so downstream skills can consume them directly.
- **`test-automation-engineer`** seeds regression tests directly from `repro-recipe.yml`
  (`prerequisites`, `steps`, `expected_observation`, `post_fix_observation`).
- **`manual-tester`** writes its repro recipe to the same shared file when the defect is
  reproducible.
- **`product-owner`** writes refined `acceptance_criteria` back to the shared evidence pack.

### Changed

- **README, CONTRIBUTING.md, GOVERNANCE.md, SUPPORT.md rewritten to drop the welcoming-but-ignored
  contradiction.** The project is solo-maintained and exists primarily for the maintainer's own
  engineering work, shared as a public good. Issues and PRs are not actively solicited; forking is the
  recommended path for divergent needs. The new files set realistic expectations up front instead of
  implying a contributor pipeline that does not exist.
- README status banner bumped to `0.5.0`.
- All six `SKILL.md` files: `metadata.version` bumped to `0.5.0`.

## 0.4.0 - Accuracy & Cross-Skill Collaboration

Anchored to the engineering fundamentals the skills are meant to enforce: full context awareness, no
guessing, real root-cause investigation, safe-environment reproduction, and engineer↔reviewer
pair-programming.

### Added

- **README cross-skill graph.** The skills table now shows _Reuses / collaborates with_ instead of
  just folder nesting, plus an ASCII collaboration diagram. Makes it explicit that
  `test-automation-engineer`, `manual-tester`, and `product-owner` all reuse the other roles — that
  information previously lived only inside each `SKILL.md`.
- **`software-engineer` Phase 1.5 — Reproduce-before-fix gate.** Bug fixes must now write a failing
  regression test FIRST, commit it as the first commit on the branch (verifiable by checking out the
  parent), and only then implement the fix. Refactors / formatting / docs / new features are
  explicitly exempt.
- **`software-engineer` 5-line plan structure** (Problem · Hypothesis · Smallest change · Risk ·
  Validation) so the reviewer can later check the diff against the stated intent.
- **`software-engineer` self-review item — fix-adds-observability.** If the defect was hard to
  investigate because evidence was missing, the fix must add the missing log/metric/correlation id.
- **`issue-investigator` safe reproduction protocol.** Operational ladder (local stack → ephemeral
  env → replayed input → read-only inspection of affected env), with a deterministic recipe captured
  for handoff to engineer/test-automation-engineer.
- **`issue-investigator` three-hypothesis discipline.** Top-3 candidate causes, falsifiable "what
  would change my mind" line per hypothesis, single cheapest discriminating experiment. Replaces the
  vague "avoid stopping at the first plausible explanation" guidance with a concrete technique.
- **`issue-investigator` regression triage** (`git log -L`, `git blame`, `git bisect`,
  deploy/feature-flag diff) before forming hypotheses for any reported regression.
- **`issue-investigator` confidence gate** mapping each recommended next-action (code fix / rollback
  / config change / monitoring / clarification) to the minimum root-cause confidence required to
  recommend it.
- **`code-reviewer` hard handoff contract** listing the evidence pack the engineer must supply
  (project entry, issue brief, root-cause confidence, failing-test commit for bug fixes, 5-line plan,
  risk areas). Missing handoff is a `major` finding.
- **`code-reviewer` `test-quality` review profile** for `manual` mode when reviewing test code
  (selector stability, deterministic data, condition-based waits, assertion meaningfulness,
  isolation).
- **`code-reviewer` iteration convergence rule (`CODE_REVIEWER_MAX_ROUNDS`, default `3`).**
  Blocker+major finding count must strictly decrease between rounds; non-converging loops escalate to
  the user instead of grinding indefinitely or silently downgrading blockers.
- **`code-reviewer` devil's-advocate self-rebuttal** before any `PASS` verdict, attacking your own
  conclusion against silent data loss, lost-update / race conditions, auth bypass, secret/PII leakage,
  broken migration, breaking API contract, and regression risk.
- **`test-automation-engineer` invokes `code-reviewer`** in `test-quality` mode on its own test
  code, plus a flake-budget rule (≥20 repeat executions in CI before merge), explicit anti-pattern
  list (`Thread.sleep`, `cy.wait(N)`, `time.sleep`, hard-coded dates, ordering-dependent fixtures,
  shared mutable test data, blind retries), and links to the originating `issue-investigator` recipe
  for regression-derived tests.
- **`manual-tester` safe reproduction protocol** mirroring `issue-investigator`, plus a
  defect-template _investigator handoff_ field, mandatory commit-SHA in defect reports, replayable
  artifact preference (HAR / Playwright trace / Cypress recording), and time-boxed exploratory
  charters.
- **`product-owner` routes bug-flavored input through `issue-investigator` first.** Support tickets,
  incidents, regression complaints, etc. are not turned into acceptance criteria until investigation
  results are in hand — closes a guessing path that previously let the PO invent "actual behavior".
- **`product-owner` Definition-of-Ready gate** before producing the Jira-ready output (goal stated,
  investigator result attached for bug-flavored input, observable/testable ACs with at least one
  negative criterion, scope explicit, feasibility note attached for
  API/migration/security/shared-library work, open questions listed).
- **`product-owner` requires at least one negative AC** (`Given X, the system MUST NOT Y`) per work
  item.
- **`product-owner` feasibility-note artifact** (effort tier, key risks, breaking-change y/n) from
  `software-engineer` before locking acceptance criteria.

### Changed

- README status banner bumped to `0.4.0`.
- All six `SKILL.md` files: `metadata.version` bumped to `0.4.0`.

## 0.3.0 - Spec Alignment And Slim README

### Added

- `compatibility:` and `metadata:` (author, version, homepage) frontmatter on every `SKILL.md`,
  conforming to the [Agent Skills specification](https://agentskills.io/specification).
- `scripts/validate_skills.py` — a self-contained validator that checks every `SKILL.md` against the
  spec (`name` 1-64 chars + matches parent dir, `description` 1-1024 chars, `compatibility` <= 500
  chars, `metadata` shape, `license` non-empty when present).
- GitHub Actions CI workflow at `.github/workflows/ci.yml` that runs the skill validator, exercises
  `setup.init --yes` and `--verify` end-to-end against a temp git workspace (including idempotency and
  `$HOME`-refusal assertions), and runs a markdown link check.
- `npx skills add wamalalawrence/agent-skills` documented as an alternative install path via the
  [skills.sh](https://skills.sh) ecosystem.
- `docs/` directory: `installation.md`, `configuration.md`, `assistants.md`, `prompts.md` —
  long-form material moved out of the README.

### Changed

- README rewritten to be short and scannable in the GitHub preview (~60 lines vs ~280 before):
  tagline, why-skills, install, skills table, links into `docs/`, principles, contributing, license.
  Inspired by `google/skills` README pacing.
- Skill internal links updated to point at `docs/` for installation/configuration/assistant
  compatibility/starter prompts.

## 0.2.0 - Onboarding And Positioning

### Added

- `setup.init`: bash automation for first-run workspace setup. Asks a short set of questions, then
  creates or refreshes `.env`, `.jira-config.yml` (optional), the `.skills` symlink, and an idempotent
  agent-skills block in the workspace `.gitignore`.
- `setup.init --verify`: re-checks an existing setup without writing — required env vars,
  `PROJECTS_JSON` shape, every project path resolves, `.skills` target valid, Jira credentials
  consistent.
- "Why Skills" section in the README explaining how a skill turns a generalist LLM into a specialist
  (general practitioner vs. dentist analogy).
- "Try A First Prompt" section in the README with one starter prompt per skill.
- Honest "Using With Your AI Assistant" compatibility table covering Claude Code,
  Cursor/Windsurf/Continue, GitHub Copilot Chat, and generic chat clients.

### Changed

- README Quick Start now leads with `./setup.init` and an explicit recommended workspace layout,
  with manual `cp` setup retained as a fallback.
- `.env.example` headers point at `setup.init` and ship safer bootstrap defaults.
- Nested `code-reviewer` README clarifies that `CODE_REVIEWER_MODEL` is optional, not required.

### Hardened

- `setup.init` refuses unsafe workspace roots (`$HOME`, `/`, and common system directories) so a
  fresh clone in the wrong place cannot pollute your shell environment. Explicit `--workspace-root`
  requires interactive confirmation to override.
- JSON validation prefers `python3` (universally present), falls back to `ruby`, and only skips with
  a warning when neither is installed.
- `GITHUB_ORG` is detected from sibling repository `remote.origin.url` first, then falls back to
  `gh api user --jq .login`, then leaves the field blank.
- Build and format commands are inferred per package manager: `pnpm`/`yarn`/`bun`/`npm` lockfiles
  plus `package.json` script presence; Poetry-aware Python; gradle fallback when no wrapper is
  present.
- The generated `.env` block carries an explicit warning that contents inside the markers are
  overwritten on rerun and that manual edits belong outside the markers.
- The generated workspace `.gitignore` block covers `.env`, `.env.local`, `.env.*.local`,
  `.jira-config.yml`, `.skills`, and `.cache/` so workspaces that are themselves git repos do not show
  those files as uncommitted changes (and `.env` does not risk leaking secrets). Idempotent on rerun.

### Documentation

- CONTRIBUTING.md documents the `setup.init` validation expectation for contributors.

## 0.1.0 - Initial Public Baseline

- Added the initial `software-engineer` role skill.
- Added nested review and Jira-driven issue resolution skills under `software-engineer`.
- Added reference checklists for code review, security, SonarQube-style quality gates, and
  architecture patterns.
- Added environment and Jira configuration templates.
