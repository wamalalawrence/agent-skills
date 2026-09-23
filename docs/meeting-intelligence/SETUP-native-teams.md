# Native capture for Microsoft Teams

Last verified against Microsoft Learn: **2026-09-23**.

Agent Skills reads the transcript Teams already made, through Microsoft Graph, with each user's
own delegated sign-in. No bot joins, and nothing leaves your tenant except to the user's machine.

## For the admin: register the app once

1. **Microsoft Entra admin center → App registrations → New registration.**
   - Name: `Agent Skills Meeting Transcripts` (any name; users see it on the consent screen).
   - Supported account types: **Accounts in this organizational directory only** (single tenant).
   - Redirect URI: platform **Public client/native (mobile & desktop)**, value `http://localhost`.
     The Microsoft identity platform accepts any port on a loopback redirect, so each user's
     sign-in can use a free local port.
2. **No client secret.** Agent Skills is a public client: it uses the authorization-code flow with
   PKCE and a loopback redirect, so do not create a secret for it. ("Allow public client flows" is
   needed only for device-code sign-in, which v1 does not use.)
3. **API permissions → Add a permission → Microsoft Graph → Delegated permissions**:

   | Permission | Why |
   | --- | --- |
   | `OnlineMeetings.Read` | Look up the meeting from its join link (`/me/onlineMeetings?$filter=JoinWebUrl eq '…'`) |
   | `OnlineMeetingTranscript.Read.All` | List and download that meeting's transcripts |
   | `offline_access` | A refresh token, so users do not sign in before every meeting |

   `OnlineMeetingTranscript.Read.All` requires **admin consent**: choose *Grant admin consent for
   <tenant>*. Do **not** add application permissions; v1 uses delegated access only, so Agent
   Skills can read exactly what the signed-in user can and nothing more.
4. **Tenant settings that must allow it:** Teams transcription must be enabled in the Teams admin
   center meeting policy. A tenant can also switch off Graph access to transcripts (Graph answers
   `403 GraphAccessToTranscriptsDisabled`) or speaker attribution (`SpeakerAttributionNotAllowed`;
   Agent Skills then fetches the unattributed format and marks the transcript "speakers not
   identified").
5. **Distribute the non-secret config** to your users, for example as
   `agent-skills-meetings.json` on your intranet:

   ```json
   {
     "schema": "agent-skills.meeting-native-config/v1",
     "teams": {
       "client_id": "<Application (client) ID>",
       "tenant_id": "<Directory (tenant) ID>"
     }
   }
   ```

   The file holds **no secret**. `setup --import` refuses a file that contains one.

## For each user

```bash
agent-skills meeting setup native --import agent-skills-meetings.json
agent-skills meeting setup native --platform teams
```

The second command shows the notice, opens your browser to sign in (authorization code + PKCE,
loopback redirect), stores the refresh token in your OS keychain (or a `0600` file under
`~/.config/agent-skills/secrets/`), and runs a self-test: a harmless Graph lookup that reads no
meeting. Run it yourself in a terminal; an assistant cannot sign in for you.

## Using it

```bash
agent-skills meeting join "<Teams join link>"      # before or during the meeting
agent-skills meeting fetch "<Teams join link>"     # a meeting that already ended
```

Switch on **Start transcription** in the meeting; everyone sees Teams' banner. After the meeting,
`agent-skills meeting status <id>` polls until Graph lists the transcript (it can appear in Teams a
few minutes before Graph exposes it), for up to `native.fetch_window_hours` (default 24) after the
meeting's end.

## Limitations and what you will see

| Situation | Result |
| --- | --- |
| Meeting hosted in another organisation's tenant (the link's `Tid` is not yours) | `external_tenant`: use `--via recall` or `--via desktop` |
| You received a single forwarded occurrence of a recurring meeting | `no_access` (Graph answers 403); ask the organiser to invite you directly |
| Meeting created without a calendar event (create-onlineMeeting API), or expired | `unsupported_meeting` |
| Graph transcript access switched off for the tenant | `no_access`, naming the admin setting |
| Teams (free) link on `teams.live.com` | `unsupported_platform`: Graph transcripts need a work or school account |
| Nobody switched transcription on | `not_enabled` once the fetch window closes |

## Removing it

`agent-skills access forget --profile meeting-teams` deletes the stored tokens. The admin can
revoke the app's consent in Entra at any time; the next fetch then reports "sign-in expired".
A publicly published, multi-tenant app (which would remove the per-organisation registration)
needs Microsoft publisher verification and is out of scope for v1.
