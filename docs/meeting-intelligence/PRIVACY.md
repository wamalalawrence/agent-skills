# Meeting Intelligence: privacy, retention, and your responsibility

**This is not legal advice.** It describes what Agent Skills does with meeting data so that you,
and your organisation's data-protection officer, can decide whether and how to use it.

## Your responsibility

Recording or transcribing a conversation is regulated in many places. Recording people without
their knowledge can be a criminal offence — for example **§201 StGB** (Verletzung der
Vertraulichkeit des Wortes) in Germany — and all-party-consent rules apply in several US states and
other countries. Under the GDPR, a meeting transcript is personal data of every participant.
Before you capture meetings, your organisation may need:

- a **data processing agreement (DPA)** with any third party that processes the audio (Recall.ai,
  if you use the `recall` provider), and a transfer assessment if data leaves the EU;
- in Germany, frequently a **works-council agreement** (Betriebsvereinbarung), because recording
  and analysing meetings can be used to monitor employees' behaviour or performance;
- an entry in its records of processing and, depending on use, a data-protection impact assessment.

Telling participants is always your responsibility. The `recall` bot announces itself and native
platforms show their own banner, but the `desktop` provider notifies **nobody**: you must.

## Every mode: extraction runs in your AI assistant

The `agent-skills` CLI never calls a model. Facts are extracted by the AI assistant you run it in
(Claude Code, Cursor, Codex, Copilot, …), so the transcript windows you extract from are sent to
**that assistant's model provider**, under your agreement with it. No mode is fully local unless
the assistant's model is. Transcripts are redacted (typed and spoken secrets) before any window is
shown to the assistant.

## What each provider stores, where, and for how long

| Data | `native` | `recall` | `desktop` |
| --- | --- | --- | --- |
| Audio / video | Platform only; **never downloaded** | Recall, your region; ≤ 48 h, deleted once transcribed | This computer, `0600`; deleted once transcribed (or ≤ 7 days) |
| Platform / provider transcript | Stays in your tenant under your retention; Agent Skills never deletes it | At Recall with the recording | — |
| Local transcript copy | `~/.agent-skills/state/meetings/<id>/transcript.json`, redacted, `0600`, 30 days (`transcript_retention_days`) | same | same |
| Extracted facts | The repository knowledge base (committed, reviewed like code); durable | same | same |
| Credentials | Refresh/access tokens and any client secret in the OS keychain (or `0600` file) | API key (and optional verification secret), same store | none |
| Consent record | — | The recording-notice acknowledgement in `meeting.json` | Per meeting: time and notice version of your "everyone agreed" |

`inspect <id> --purge --yes` deletes the captured media still held (Recall's recording, or local
raw audio) and the local transcript at once; facts are kept and keep their timestamps. It never
touches a platform's own transcript.

**What Recall keeps after deletion.** Deleting media removes Recall's recording media for the bot.
Recall's documentation does not state that bot metadata, status history, and operational logs go
with it; assume they persist for Recall's own retention period and check your agreement with
Recall before telling participants the data is gone.

## Who can read what

- `native`: delegated sign-in only. Agent Skills can read what the signed-in user can read in
  their own tenant — no organisation-wide application permissions in v1, and no other
  organisation's meetings (`external_tenant`).
- `recall`: Recall processes every participant's voice as your processor.
- `desktop`: only this computer's user account (files are `0600` in `0700` directories).

Speaker names are display names, never mapped to people, e-mail addresses, or tracker accounts.
With `desktop`, remote speakers are not identified at all.
