# Meeting Intelligence

Tell your assistant:

```text
Listen to this meeting:
https://meet.google.com/abc-defg-hij
```

and Agent Skills sends a visible, named assistant into the Microsoft Teams, Zoom, or Google Meet
call, retrieves the speaker-attributed transcript when the recording ends, extracts engineering
knowledge from it in bounded windows, shows a short result, and stores the facts — with status,
scope, and timestamped evidence — in the repository knowledge base. A later question in the same
repository ("why does payments-service publish to retry-events?") finds the decision, labelled as
meeting evidence.

Added in `1.2.0`. The design decisions and what they are built on are in
[meeting-intelligence/DISCOVERY.md](meeting-intelligence/DISCOVERY.md).

## Setup

1. A [Recall.ai](https://www.recall.ai/) account. Recall is the capture provider: it runs the bot,
   records, and transcribes. Pick a region and keep everything in it — keys, bots, and media are
   region-local. `eu-central-1` keeps data in the EU.
2. Store the key through the Access Resolver (hidden input, OS keychain where available):

   ```bash
   agent-skills access set --profile recall --service recall \
     --field region=eu-central-1 --secret-field api_key
   ```

   Or set `AGENT_SKILLS_RECALL_API_KEY` and `AGENT_SKILLS_RECALL_REGION` in the environment. The key
   is never written to meeting state, logs, transcripts, facts, or a process argument.
3. `agent-skills doctor` shows a **Meetings** section: credentials, region consistency, consent,
   listener mode, and stuck meetings. `agent-skills doctor --probe-meeting` also contacts Recall
   once to prove the key works in its region; without the flag, doctor stays offline.

## Using it

```bash
agent-skills meeting join <meeting-url> [--scope repo:<path>] [--title <text>]
agent-skills meeting status [<id>] [--wait]
agent-skills meeting stop <id>
agent-skills meeting list
agent-skills meeting inspect <id> [--transcript] [--facts]
```

`join` validates the link locally (unknown shapes are refused and nothing is created), binds the
scope, creates the bot, and returns — the terminal does not need to stay open.

```text
Agent Skills Meeting Assistant → joining (Zoom)
Meeting id: m_7f3c12ab34cd   Scope: repo:payments-service
The assistant will appear in the participant list as "Agent Skills Meeting Assistant".
Tell participants that recording and transcription are active.
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
all|<ids> [--scope repo:<path>]` (accept facts pending review), `--purge --yes` (delete provider
media and the local transcript, keep facts), `--json`.

## Consent and safety

- The first `join` shows a one-time notice and requires explicit acknowledgement (interactively,
  or `--acknowledge-recording-notice` after the user agreed in their assistant). It is shown again
  whenever the notice text changes.
- The assistant always joins as a named participant (`Agent Skills Meeting Assistant` by default;
  configurable, never empty) and posts a chat message saying it is recording and transcribing
  (configurable, never empty).
- Organisational policy and local law — including all-party consent jurisdictions and GDPR —
  still apply. Telling participants is your responsibility.
- No auto-joining, no calendar attendance, no hidden participants, no local microphone capture.
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

Preference order, configurable in `meeting.json` (`transcription_preference`):

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
from the start), `text`, `source_method`. **Speaker names are display names, not identities.**
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

| Data | Where | Default |
| --- | --- | --- |
| Recording media | At the provider only; never downloaded | 48 h retention set on every bot (`media_retention_hours`, 1–168); deleted once the transcript is stored |
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

## State, updates, and rollback

Meeting state lives under `~/.agent-skills/state/meetings/`, never inside a version directory, so
`update` and `rollback` neither lose nor fork it. Records carry a schema version
(`agent-skills.meeting/v1`); releases before `1.2.0` never read this directory, and this release
refuses — without rewriting — any record whose schema it does not know. `uninstall` keeps it unless
`--purge`.

## Provider boundary

Meeting Intelligence speaks only its own types. `MeetingCaptureProvider` (`start`, `poll`, `stop`,
`fetch_transcript`, `request_async_transcript`, `delete_media`, `verify_event`, `capabilities`) is
implemented by `RecallMeetingBotProvider` in `scripts/meeting_recall.py`, the only module that
knows Recall exists; a test fails if any other meeting module imports it or names a Recall field.
`capabilities()` describes join-live, existing-transcript retrieval, diarization quality, and
retention control, so a native Teams or Meet transcript provider can be preferred later without
changing Meeting Intelligence. A WebVTT normaliser (the format those platforms export) already
exists.

## Limitations

- Live, in-meeting help and live transcript streaming are out of scope.
- Extraction quality depends on the host model; the mechanical checks bound the damage (no
  invented evidence, no hedge confirmed, no scope widened) but cannot supply missed facts.
- The Recall adapter was built against Recall's published API reference and tested against
  fixtures derived from it, not against a live account. Run
  `AGENT_SKILLS_MEETING_LIVE_SMOKE=1 python3 scripts/test-meeting.py` with real credentials before
  relying on it; it authenticates and lists bots and never creates one.
- Spoken-secret detection is heuristic. It errs toward redaction, and it can still miss a secret
  said in an unusual way.
