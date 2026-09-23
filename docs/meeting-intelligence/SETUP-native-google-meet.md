# Native capture for Google Meet

Last verified against developers.google.com: **2026-09-23**.

Agent Skills reads Meet's transcript entries through the Meet REST API (v2), with each user's own
delegated sign-in. No bot joins, and nothing leaves your Workspace except to the user's machine.

## Requirements

- A Google Workspace edition that **includes Meet transcription** (not every edition does), with
  transcription allowed for your users in the Admin console.
- Artifacts are readable only by the meeting space's owner or participants in your Workspace; in
  practice, reliably the organiser.

## For the admin: register the app once

1. **Google Cloud console → create a project** for Agent Skills (or reuse an internal one).
2. **APIs & Services → Library → Google Meet REST API → Enable.**
3. **OAuth consent screen (Google Auth Platform → Branding / Audience):** user type **Internal**.
   An internal app is limited to your Workspace and needs no public app verification.
4. **Data access → Add scopes:** `https://www.googleapis.com/auth/meetings.space.readonly` only.
5. **Clients → Create client → Application type: Desktop app.** Desktop clients use a loopback
   redirect (`http://127.0.0.1:<port>`) with PKCE, so no redirect URI has to be registered.
   Google issues a client secret for desktop clients; its own documentation treats it as not
   confidential for installed apps, but Agent Skills still handles it as a credential: each user
   enters it once with hidden input, and it is never in the shared config.
6. **Distribute the non-secret config:**

   ```json
   {
     "schema": "agent-skills.meeting-native-config/v1",
     "google_meet": {
       "client_id": "<client id>.apps.googleusercontent.com",
       "workspace_domain": "example.com"
     }
   }
   ```

   `workspace_domain` (optional) pre-selects accounts from your domain on the sign-in screen.
   Share the client secret the way you share any credential (a password manager), not in this
   file: `setup --import` refuses a file that contains one.

## For each user

```bash
agent-skills meeting setup native --import agent-skills-meetings.json
agent-skills meeting setup native --platform google_meet
```

Setup asks for the client secret (hidden; Enter if your admin says there is none), opens the
browser to sign in, stores the refresh token in the credential store, and self-tests with a
one-record `conferenceRecords` list that reads no transcript.

## Using it

```bash
agent-skills meeting join https://meet.google.com/abc-defg-hij    # before or during
agent-skills meeting fetch https://meet.google.com/abc-defg-hij   # after it ended
```

Switch on **Transcripts** in the meeting (Activities → Transcripts); participants see Meet's
notice. Agent Skills finds the conference by meeting code (`space.meeting_code`); for a joined
meeting it considers only conferences from the join time on, because a Meet link is reused by
recurring meetings. It reads the transcript **entries** (paged, 100 at a time) with each
participant's display name, not the Google Docs file.

## Limitations and what you will see

| Situation | Result |
| --- | --- |
| A space you cannot read (another organisation's, or not yours) | `no_access`, with `--via recall` / `--via desktop` |
| Conference ended, no transcript | `not_enabled` once the fetch window closes |
| Edition without transcription | `not_enabled` (the API never lists a transcript) |

Entries can differ slightly from the Docs transcript when speakers overlap; Agent Skills uses the
entries because they carry per-utterance speakers and timestamps.

## Removing it

`agent-skills access forget --profile meeting-google-meet`. Admins can remove the app's access in
the Admin console (Security → API controls).
