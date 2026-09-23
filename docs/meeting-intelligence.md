# Meeting Intelligence

Tell your assistant:

```text
Listen to this meeting:
https://meet.google.com/abc-defg-hij
```

and Agent Skills captures the Microsoft Teams, Zoom, or Google Meet meeting the way you chose —
the platform's own transcript, a visible named Recall bot, or a local recording on your computer —
retrieves the transcript when the meeting ends, extracts engineering
knowledge from it in bounded windows, shows a short result, and stores the facts — with status,
scope, and timestamped evidence — in the repository knowledge base. A later question in the same
repository ("why does payments-service publish to retry-events?") finds the decision, labelled as
meeting evidence.

Added in `1.2.0`; the choice of capture provider was added in `1.4.0`. The design decisions and
what they are built on are in [meeting-intelligence/DISCOVERY.md](meeting-intelligence/DISCOVERY.md).

## Setup: choose how meetings are captured

Nothing is captured until you choose one of three capture providers. The comparison (cost, data
flow, consent, what each needs), the per-provider setup guides, and the privacy page are in
[meeting-intelligence/README.md](meeting-intelligence/README.md).

```bash
agent-skills meeting setup --compare                  # native vs recall vs desktop
agent-skills meeting setup native|recall|desktop      # guided; ends with a self-test
```

| Provider | In one line |
| --- | --- |
| `native` | Teams / Meet / Zoom already transcribes; Agent Skills downloads it with your sign-in. No bot, no cost, stays in your tenant. |
| `recall` | A visible "Agent Skills Meeting Assistant" bot joins; Recall bills you ≈ $0.65 per meeting hour and processes the audio. |
| `desktop` | Your computer records and whisper.cpp transcribes locally. No bot, no cost; **you** must tell participants. |

In every mode the facts are extracted by your AI assistant, so transcript text reaches its model
provider. With no provider set up, `join` contacts nothing and prints these options instead.
`agent-skills doctor` lists each provider as `ready`, `not configured`, or `broken: <reason> → <fix>`;
`doctor --probe-meeting` additionally contacts Recall once and checks that the desktop system-audio
input receives sound. Without the flag, doctor stays offline.

## Using it

```bash
agent-skills meeting join <meeting-url> [--via native|recall|desktop] [--scope repo:<path>] [--title <text>]
agent-skills meeting fetch <meeting-url> [--scope repo:<path>]     # native: after the meeting
agent-skills meeting status [<id>] [--providers] [--wait]
agent-skills meeting stop <id>
agent-skills meeting list
agent-skills meeting inspect <id> [--transcript] [--facts]
```

`join` uses your default provider, or the one `--via` names for this meeting. It checks that the
provider is ready (locally, before any network call), validates the link, binds the scope, starts
the capture, and returns — the terminal does not need to stay open. A provider that cannot serve
the meeting stops with the reason and the alternatives; nothing ever switches providers for you.

```text
Provider: recall. Agent Skills Meeting Assistant → joining (Zoom)
Meeting id: m_7f3c12ab34cd   Scope: repo:payments-service
The assistant will appear in the participant list as "Agent Skills Meeting Assistant".
Tell participants that recording and transcription are active.
Cost: Billed by Recall to your account, ≈ $0.65/meeting hour.
Data: Audio and transcript are processed by Recall.ai (a third party) in your chosen region; ...
Extraction: In every mode, fact extraction runs in your AI assistant (...)
Check progress: agent-skills meeting status m_7f3c12ab34cd
```

`status`, `list`, and `inspect` **reconcile**: they poll the provider, advance the lifecycle,
retrieve and redact the transcript once the recording is done, and prepare extraction windows.
Every step is idempotent, so running one twice, or after a crash, is always safe.

When the transcript is ready, extraction runs in **your assistant** (the runtime never calls a
model): the `meeting-intelligence` skill reads each window with `inspect <id> --next-window` and
returns strict JSON with `inspect <id> --submit <file>`. When the last window is in:

```text
Payments Architecture — processed   (58 min, transcript: captions)

Decisions:       3   (2 confirmed, 1 proposed)
Actions:         4
Risks:           1
Open questions:  2

Key decisions:
- [CONFIRMED] Move payment retries to Kafka.                     @12:41
- [PROPOSED]  Deprecate the synchronous retry endpoint.          @44:10

Actions:
- Lawrence: Create the implementation ticket.                    @51:20

Full details: agent-skills meeting inspect m_7f3c12ab34cd --facts
```

Other `inspect` flags: `--reprocess` (extract again from the stored transcript), `--accept
all|<ids> [--scope repo:<path>]` (accept facts pending review), `--purge --yes` (delete captured
media and the local transcript, keep facts), `--json`.

## Consent and safety

- Each provider has a versioned cost, data-flow, and consent notice that `meeting setup` shows and
  records; when its text changes, it is shown again.
- `recall`: the first `join` shows a one-time recording notice and requires explicit
  acknowledgement (interactively, or `--acknowledge-recording-notice` after the user agreed in
  their assistant). It is shown again whenever the notice text changes.
- `native`: participants see the platform's own transcription banner; nothing else joins.
- `desktop`: nobody is notified automatically, so it is started only by the user at an interactive
  terminal, after typing a confirmation that everyone was told and agreed (stored on the meeting),
  with a ready-to-paste chat announcement. An assistant cannot start it. See
  [SETUP-desktop.md](meeting-intelligence/SETUP-desktop.md).
- The assistant always joins as a named participant (`Agent Skills Meeting Assistant` by default;
  configurable, never empty) and posts a chat message saying it is recording and transcribing
  (configurable, never empty).
- Organisational policy and local law — including all-party consent jurisdictions and GDPR —
  still apply. Telling participants is your responsibility.
- No auto-joining, no calendar attendance, no hidden participants, no meeting auto-detection.
  Local capture happens only in the `desktop` mode, started by the user.
- A platform that refuses recording (a Zoom host denying permission) ends the meeting as
  `PERMISSION_DENIED` and the assistant is asked to leave. There is no retry loop.

## Lifecycle

```text
CREATED → JOINING → WAITING_ROOM → IN_CALL_NOT_RECORDING → RECORDING
        → ENDED → MEDIA_READY → TRANSCRIPT_READY → PROCESSING → PROCESSED
Terminal failures: REJECTED | PERMISSION_DENIED | TIMED_OUT | FAILED
Also: PARTIAL (processed from an incomplete transcript), PURGED
```

Transitions are monotonic: a duplicate, stale, or out-of-order observation can never move a
meeting backwards. The provider's own sub-code is kept beside the state, redacted, for diagnosis.
`inspect --reprocess` is the one sanctioned backward move, and only because the user asked.

| Situation | Outcome |
| --- | --- |
| No capture provider set up | exit `2`, the three options printed, nothing contacted or created |
| Chosen provider not ready (`broken`) | exit `2`, or `3` for a key / sign-in problem, with the one fix command |
| Chosen provider refuses the meeting | exit `2`: `external_tenant`, `no_access`, `unsupported_platform`, `unsupported_meeting`, with alternatives |
| Native: transcription never switched on | `FAILED` (`not_enabled`) once the fetch window (24 h) closes |
| Desktop started without a terminal, or consent not confirmed | exit `2`, the command to run yourself; nothing recorded |
| Desktop recorder crashed | what was recorded is transcribed and processed as `PARTIAL` |
| Unrecognised meeting link | exit `2`, nothing created |
| Missing or rejected Recall key, missing region | exit `3`, nothing created |
| Region in `meeting.json` differs from the credential's | exit `3`; doctor reports `MISMATCH` |
| Recall unreachable or 5xx | exit `4`; state kept, retried with backoff on the next reconcile |
| Host removes the bot before it recorded | `REJECTED` |
| Recording permission denied | `PERMISSION_DENIED` |
| Waiting room or no-one-joined timeout | `TIMED_OUT` |
| Meeting ends before anything was recorded | `FAILED` (`ended_without_media`) |
| No usable transcript by any method | `FAILED` (`transcription_unavailable`) |
| Incomplete transcript | processed, marked `PARTIAL` |
| Failure while committing facts | nothing committed; resumes from the last window checkpoint |
| Local meeting record from an unknown schema | exit `7` for that meeting; never rewritten |

## Transcription

`native` uses the platform's transcript (WebVTT from Teams and Zoom, transcript entries from Meet).
`desktop` transcribes each audio channel with whisper.cpp; its speakers are only "You" and "Remote
participants (unidentified)" (`speaker_attribution: channel`), so owners are never guessed and the
confidence of agreements and actions is capped at 0.6. For `recall`, the preference order is
configurable in `meeting.json` (`transcription_preference`):

1. `captions` — the platform's own captions through the provider (best speaker attribution;
   depends on the host's caption settings).
2. `provider_transcription` — Recall's streaming transcription.
3. `async` — post-meeting transcription of the retained recording.

Recall runs one live transcription method per bot, so the first of `captions` /
`provider_transcription` in the list is chosen at join. If it yields an empty or clearly partial
transcript and the recording is still retained, post-meeting transcription is requested before
giving up. The method that produced the final transcript is recorded.

Every provider format is normalised to one model: `segment_id` (stable, deterministic),
`speaker_label` (the display name), `participant_ref` (opaque), `start_ts` / `end_ts` (seconds
from the start), `text`, `source_method`; per transcript, `speaker_attribution`
(`named | channel | none`), `capture_provider`, and `language`. **Speaker names are display names,
not identities.**
Nothing maps them to people, emails, or tracker accounts.

## Webhooks (optional)

Polling needs no inbound network access and is always sufficient. If you already run a stable
public URL (your own tunnel or host), point it at a loopback listener and configure the same URL
as a webhook endpoint in the Recall dashboard:

```bash
agent-skills meeting status --listen 127.0.0.1:8787
# path: /agent-skills/meeting/webhook
```

The listener needs the workspace verification secret (`--secret-field verification_secret` on
the `recall` profile). Every request is size-bounded, then its Svix signature is verified over the
raw body with a constant-time comparison **before** the body is parsed, then its signed timestamp
must be within five minutes, then its event id is deduplicated. Only then is it acknowledged, and a
verified event only schedules a reconcile of the matching meeting — the reconciler asks the
provider what is true, so an event can never carry state. Headers, signatures, secrets, and bodies
are never logged. The listener binds to loopback only.

## Facts

Types: `DECISION`, `ARCHITECTURE_DECISION`, `ACTION`, `REQUIREMENT`, `CONSTRAINT`, `RISK`,
`ASSUMPTION`, `OPEN_QUESTION`, `DEPENDENCY`, `INCIDENT_FACT`.

Each fact has a deterministic `id` (from meeting, type, and normalised statement), `type`,
`statement` (one paraphrased, redacted sentence), `status`, `scope`, `speakers`, `owner` and `due`
(actions only, only as spoken), `meeting_id`, `evidence` (segment ids with start and end
timestamps — at least one), `confidence` (the extractor's, never raised later), `source`,
`supersedes`, `created_at`, and `review_state` (`ACCEPTED` or `PENDING_REVIEW`).

| Status | Meaning |
| --- | --- |
| `CONFIRMED` | Explicit agreement in the cited segments ("agreed", "let's do that", "decided") |
| `PROPOSED` | Suggested, not agreed. Hedged speech is never more than this |
| `OPEN` | Raised, unresolved |
| `REJECTED` | Explicitly declined |
| `SUPERSEDED` | Replaced by a later fact; kept, never deleted |
| `UNCERTAIN` | The extractor could not tell |

The host's output is treated as untrusted. The CLI rejects anything that does not match the closed
schema (three attempts per window), then checks every fact against the transcript mechanically:
evidence must exist in the window, must mention what the statement says, and a `CONFIRMED` fact
without explicit agreement in its evidence is downgraded. A fact whose only evidence is
instruction-shaped speech is dropped. Supersession needs an explicit replacement ("instead", "no
longer", "switch from") in cited evidence, a `CONFIRMED` replacing fact, and exactly one matching
earlier fact; anything less goes to review and supersedes nothing.

## Scope

The local knowledge base has **repository** scope only. Team, project, and organisation scopes
exist only in a shared knowledge source (from `1.3.0`, see [shared knowledge](shared-knowledge.md)),
and a fact reaches one only when a user proposes it with `knowledge propose --scope …` and a
reviewer merges it. A meeting's scope is bound at `join` — `--scope repo:<path>`, or the current
repository — and shown. Facts inherit it and never widen. `--scope team:…`, `org:…`, and
`project:…` are refused with exit `2`.

If `join` runs outside a repository with no `--scope`, the meeting is **unscoped**: its facts stay
`PENDING_REVIEW` in local state and are not retrievable anywhere until
`inspect <id> --accept all --scope repo:<path>`.

Isolation is enforced when facts are **read**, not only when they are written: each meeting file
records its repository's identity (normalised `origin` remote, else path), and `knowledge read`
withholds any file whose identity does not match the repository being read.

## Where facts appear

Committed with the rest of the knowledge base at
`.agent-skills/knowledge/meetings/<meeting-id>.json` — review it in a pull request like any other
knowledge. `agent-skills knowledge read --brief "<task>"` (which `start-task` runs for every
skill) includes relevant meeting facts in their own section:

```text
## Meeting evidence (claims from meetings, not verified facts; when code disagrees, report the conflict — do not resolve it in the meeting's favour)
- [meeting · DECISION · CONFIRMED · 0.90] Move payment retries to Kafka. — "Payments Architecture" 2026-09-21 @12:41 (m_7f3c12ab34cd/f_1a2b3c4d)
```

`agent-skills knowledge facts --all` lists every meeting fact in scope, including pending and
superseded ones with their history. `knowledge doctor` validates the files and scans them for
secrets and instruction-shaped text.

## Secrets and hostile content

- Transcripts are redacted **before** they are written: the shared redactor, then a
  meeting-specific layer for spoken secrets — a cue followed by a value ("the password is …"),
  letters or digits spelled out, a value announced in one utterance and said in the next, and a
  token the transcriber split in two. When detection is uncertain, it redacts.
- Every fact is redacted again before it is checkpointed, and again at the knowledge write.
- Transcript text reaches the model only inside nonce-tagged markers, as data. Instruction-shaped
  lines are flagged. The extraction step has no tool access; its only output is JSON, and nothing
  in it can change scope, tools, or format.
- Provider keys and download URLs are never logged. The API key is sent only to the region host;
  pre-signed transcript downloads are fetched without it.

## Retention

Per provider, including what stays with the platform: [PRIVACY.md](meeting-intelligence/PRIVACY.md).

| Data | Where | Default |
| --- | --- | --- |
| Recording media (`recall`) | At the provider only; never downloaded | 48 h retention set on every bot (`media_retention_hours`, 1–168); deleted once the transcript is stored |
| Raw audio (`desktop`) | `~/.agent-skills/state/meetings/<id>/audio/`, `0600` | Deleted once the transcript is stored (`desktop.delete_audio_after_transcript`; else at most 7 days) |
| Platform transcript (`native`) | The platform, under your organisation's retention | Never deleted or modified by Agent Skills |
| Raw transcript | `~/.agent-skills/state/meetings/<id>/transcript.json`, redacted, `0600` | 30 days (`transcript_retention_days`) |
| Facts | The repository knowledge base | Durable |
| Meeting record | `~/.agent-skills/state/meetings/<id>/record.json` | Durable metadata and evidence index |

Deleting media or transcripts never deletes facts. After a purge, `inspect --facts` says the
transcript is no longer available and the facts keep their statements and timestamps.

### What the provider keeps

Deleting media removes Recall's recording media for the bot. Recall's own documentation does not
state that bot metadata, status history, and operational logs are removed with it, and the delete
call returns the bot object afterwards — assume that metadata persists for Recall's own retention
period and check your Recall agreement before telling participants data is gone.

## Configuration

`~/.config/agent-skills/meeting.json` (created with defaults when consent is recorded):

| Key | Default |
| --- | --- |
| `region` | empty — taken from the credential; if both are set they must agree |
| `bot_name` | `Agent Skills Meeting Assistant` (never empty) |
| `chat_notice` | a recording notice (never empty) |
| `transcription_preference` | `["captions", "provider_transcription", "async"]` |
| `automatic_leave` | waiting room 600 s, no-one joined 600 s, everyone left 30 s |
| `media_retention_hours` | 48 |
| `delete_media_after_transcript` | `true` |
| `transcript_retention_days` | 30 |
| `window_budget_chars` / `window_overlap_chars` | 12000 / 1200 |
| `listener_url` | empty (polling only) |
| `default_provider` | empty until `meeting setup`; a 1.3.0 installation with Recall configured is treated as `recall` |
| `provider_notices` | the notice version each provider was acknowledged at |
| `recall.cost_per_hour_usd` | `0.65` (printed in the cost disclosure) |
| `native.<teams\|google_meet\|zoom>` | client id, tenant / domain, redirect URI — imported with `setup native --import`; never a secret |
| `native.fetch_window_hours` | 24 (1–168): how long after the meeting to wait for a transcript |
| `desktop.model` / `desktop.language` | `small` / `auto` |
| `desktop.max_duration_minutes` | 180 (5–720) |
| `desktop.announcement` | the chat announcement (never empty) |
| `desktop.delete_audio_after_transcript` / `desktop.raw_audio_retention_days` | `true` / 1 (1–7) |
| `desktop.mic_device` / `desktop.system_device` | empty (default microphone) / the loopback input setup found |

## State, updates, and rollback

Meeting state lives under `~/.agent-skills/state/meetings/`, never inside a version directory, so
`update` and `rollback` neither lose nor fork it. Records carry a schema version
(`agent-skills.meeting/v1`); releases before `1.2.0` never read this directory, and this release
refuses — without rewriting — any record whose schema it does not know. `uninstall` keeps it unless
`--purge`.

## Provider boundary

Meeting Intelligence speaks only its own types. `MeetingCaptureProvider` (`capabilities`,
`readiness`, `resolve`, `start`, `poll`, `stop`, `fetch_transcript`, `request_async_transcript`,
`delete_media`, `verify_event`, `activity`) has three implementations:

| Provider | Module |
| --- | --- |
| `recall` | `scripts/meeting_recall.py` (`RecallMeetingBotProvider`) — the only module that knows Recall |
| `native` | `scripts/meeting_native.py`, with `meeting_native_teams.py`, `meeting_native_meet.py`, `meeting_native_zoom.py`, and `meeting_oauth.py` (PKCE) |
| `desktop` | `scripts/meeting_desktop.py` (ffmpeg recorder, whisper.cpp transcriber) |

`scripts/meeting_providers.py` is the one composition root: it builds providers, computes their
readiness locally, and holds the preflight, comparison, and notice texts. A test fails if
`meeting.py`, `meeting_intel.py`, `meeting_store.py`, or `knowledge.py` imports any provider
module. `capabilities()` states live capture, post-meeting fetch, visible participant, speaker
attribution (`named | channel | none`), third-party processing, per-hour cost, platforms, and
languages; `resolve()` returns a provider-neutral reference or a typed refusal (`unsupported_platform`,
`external_tenant`, `no_access`, `not_found`, `not_enabled`, `not_yet_available`,
`unsupported_meeting`). A self-hosted bot server (for example Vexa) would be a fourth
implementation of the same interface.

## Limitations

- Live, in-meeting help and live transcript streaming are out of scope.
- Extraction quality depends on the host model; the mechanical checks bound the damage (no
  invented evidence, no hedge confirmed, no scope widened) but cannot supply missed facts.
- The Recall adapter was built against Recall's published API reference and tested against
  fixtures derived from it, not against a live account. Run
  `AGENT_SKILLS_MEETING_LIVE_SMOKE=1 python3 scripts/test-meeting.py` with real credentials before
  relying on it; it authenticates and lists bots and never creates one.
- The native adapters (Graph, Meet REST, Zoom) were built against the vendors' documentation as
  read on 2026-09-23 and tested against sanitised fixtures, not a live tenant. The setup self-test
  is the first live check; run it before relying on a platform.
- Desktop capture was tested with a fake `ffmpeg` and `whisper-cli`, and the ffmpeg filter graph
  against real ffmpeg with synthetic inputs; transcription quality depends on the model you pick.
- Spoken-secret detection is heuristic. It errs toward redaction, and it can still miss a secret
  said in an unusual way.
