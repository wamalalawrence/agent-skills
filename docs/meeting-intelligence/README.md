# Meeting Intelligence: choosing how meetings are captured

"Listen to this meeting: <link>" needs one thing the rest of Agent Skills does not: a way to get
a transcript of the meeting. From `1.4.0` you choose among three **capture providers**. Each one
is explained before it is used, and nothing is captured until you have picked one.

```bash
agent-skills meeting setup --compare              # this page's table, in the terminal
agent-skills meeting setup native|recall|desktop  # guided setup, ends with a self-test
agent-skills meeting status --providers           # ready / not configured / broken, and the fix
```

What happens to the transcript afterwards — redaction, bounded windows, fact extraction, the
knowledge base — is the same for all three and is described in
[meeting-intelligence.md](../meeting-intelligence.md).

## The three providers

| | `native` | `recall` | `desktop` |
| --- | --- | --- | --- |
| What happens | The platform transcribes; Agent Skills downloads it after the meeting | A visible bot joins and transcribes | Your computer records; whisper.cpp transcribes locally |
| Bot in the meeting | No | Yes, named and visible, with a chat notice | No |
| Extra cost | None beyond your existing platform licence | Per hour, billed to **your** Recall account (≈ $0.65/h) | None (your CPU/GPU time) |
| Audio or transcript leaves your organisation | No: it stays in your tenant | Yes, to Recall.ai as your processor | No |
| Setup | An admin registers one app per platform; each user signs in | Each user: Recall account, API key, region | Each user: ffmpeg, whisper.cpp, a model, system audio |
| Meetings hosted by another organisation | No | Yes | Yes |
| Speaker names | Yes (the platform's attribution) | Yes | No: only "You" and "Remote participants" |
| When the transcript is ready | After the meeting | After the meeting | After you stop (transcribed locally) |
| How participants are told | The platform's own "transcription started" banner | The visible bot and its chat notice | **Nobody is told automatically**: you must announce it |
| Platforms | Teams, Google Meet, Zoom (host's meetings) | Teams, Google Meet, Zoom | Any meeting app, on macOS or Linux |

**In every mode, fact extraction runs in your AI assistant** (Claude Code, Cursor, Codex, Copilot,
…), where all Agent Skills reasoning runs. The CLI never calls a model. So the transcript text you
extract from is sent to *that assistant's* model provider, under whatever agreement you have with
it. No mode is "fully local" unless your assistant's model is local too.

### Which one?

- Your own organisation's meetings, and your admin can register an app: **native**. No bot, no
  cost, no new processor.
- Other companies' meetings, or no admin help: **recall**, if your organisation accepts Recall as
  a processor (see [PRIVACY.md](PRIVACY.md)).
- Nothing may leave the machine and you can tell everyone yourself: **desktop**. You trade speaker
  names for it.

You set a default during setup and can override it per meeting with `--via`. Agent Skills never
switches providers on its own: when the chosen one cannot serve a meeting (a meeting in another
tenant, no access, transcription never switched on), it stops, says why, and names the
alternatives. You decide.

## Data flow

```text
native
  platform (your tenant) ── transcribes, participants see its banner
        │  delegated API read, with YOUR sign-in (read-only scopes)
        ▼
  this computer: ~/.agent-skills/state/meetings/<id>/transcript.json (redacted, 0600)
        │  one bounded window at a time
        ▼
  your AI assistant ── its model provider ──▶ facts ──▶ repository knowledge base

recall
  meeting ◀── visible bot "Agent Skills Meeting Assistant" + chat notice
        │  audio, video, transcript
        ▼
  Recall.ai, in your chosen region (media kept ≤ 48 h, deleted once the transcript is stored)
        │  transcript download
        ▼
  this computer (redacted, 0600) ──▶ your AI assistant ──▶ facts ──▶ knowledge base

desktop
  your microphone ──┐
  system audio ─────┴─▶ ffmpeg ──▶ raw audio (0600, this computer only)
                                     │ whisper.cpp, per channel, locally
                                     ▼
  this computer: transcript (redacted, 0600); raw audio deleted
        ▼
  your AI assistant ── its model provider ──▶ facts ──▶ knowledge base
```

## Costs

| Provider | What you pay | Who bills you |
| --- | --- | --- |
| `native` | Nothing extra. Transcription must be included in your Teams / Google Workspace / Zoom plan. | Your platform, as today |
| `recall` | About $0.50 per hour of recording plus $0.15 per hour of Recall transcription, ≈ $0.65 per meeting hour; the first hours at signup are free | Recall.ai, to the account you open |
| `desktop` | Nothing. Local CPU/GPU time; a model download of 142 MiB–1.5 GiB | Nobody |

Recall prices were last verified on **2026-09-23** at recall.ai/pricing. The figure Agent Skills
prints comes from `recall.cost_per_hour_usd` in `~/.config/agent-skills/meeting.json` (default
`0.65`), so you can correct it without a new release. Agent Skills never sees your Recall bill.

## Setup guides

- Native: [Microsoft Teams](SETUP-native-teams.md) · [Google Meet](SETUP-native-google-meet.md) ·
  [Zoom](SETUP-native-zoom.md) — for the admin who registers the app, and the user who signs in.
- [Recall](SETUP-recall.md) — account, region, key, verification secret.
- [Desktop](SETUP-desktop.md) — macOS and Linux.
- [Privacy and legal responsibility](PRIVACY.md) — what each provider stores, where, for how long.

## Commands

```bash
agent-skills meeting setup [native|recall|desktop] [--compare] [--import <file>]
agent-skills meeting join <url> [--via native|recall|desktop] [--scope repo:<path>] [--title <text>]
agent-skills meeting fetch <url> [--scope repo:<path>]    # native: a meeting that already ended
agent-skills meeting stop <id>
agent-skills meeting status [<id>] [--providers]
agent-skills meeting list
agent-skills meeting inspect <id> [--transcript] [--facts] [--purge]
```

`join` always says which provider it used, what will happen, what it costs, where the data goes,
and the next command:

```text
Provider: native (Microsoft Teams). No bot will join.
Meeting id: m_91a2c3d4e5f6   Scope: repo:payments-service
→ Switch on "Start transcription" in the meeting. Participants will see Microsoft Teams's banner.
Cost: No extra cost beyond your existing Teams / Google Workspace / Zoom licence.
Data: The transcript stays in your organisation's tenant; Agent Skills downloads a copy with your own sign-in.
Extraction: In every mode, fact extraction runs in your AI assistant (...), so transcript text is sent to that
assistant's model provider during extraction.
After the meeting, run: agent-skills meeting status m_91a2c3d4e5f6   (transcripts can take a few minutes to appear)
```

With no provider set up, `join` contacts nothing, records nothing, prints the three options, and
exits `2`. `agent-skills doctor` lists every provider as `ready`, `not configured`, or
`broken: <reason> → <fix command>`, and the default.

## Exit codes

Unchanged from `1.0`: `2` for a provider that is not set up, a meeting it refuses, or a consent
step not completed; `3` for a missing or rejected key, secret, or sign-in; `4` for an API that
cannot be reached. No new code was added.

## Upgrading from 1.3.0

If Recall was configured, `recall` becomes your default automatically and keeps working; the new
cost and data notice is shown once on your next `join`, without blocking it. Meetings already in
flight continue. Meeting state keeps its `agent-skills.meeting/v1` schema and only gains fields,
so `agent-skills rollback` to `1.3.0` reads it without crashing (1.3.0 reports a native or desktop
meeting as not its provider's and leaves it alone).
