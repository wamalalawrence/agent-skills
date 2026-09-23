# Native capture for Zoom

Last verified against developers.zoom.us: **2026-09-23**.

Agent Skills downloads the audio transcript of a Zoom **cloud recording** with the host's own
delegated sign-in. No bot joins; recording media is never downloaded.

## Requirements

- A paid Zoom plan with **cloud recording**, and **Create audio transcript** switched on
  (Settings → Recording → Cloud recording → Advanced cloud recording settings).
- v1 fetches the **host's own meetings**. Zoom does not reliably give attendees API access to a
  meeting's recordings, so a non-host gets a clear `no_access` refusal.

## For the admin: register the app once

1. **Zoom App Marketplace → Develop → Build App → General App.** Management: **Admin-managed**
   (account level), and keep it **unpublished** — an internal app needs no Marketplace review.
2. **Basic information → OAuth redirect URL:** `http://localhost:8765/agent-skills/oauth/callback`
   (and add it to the OAuth allow list). Zoom matches the redirect URL exactly, so it includes a
   fixed port. If 8765 is taken on your users' machines, pick another and put the same URL in the
   shared config below.
3. **Scopes** (granular, user level), read-only. The recording scope was checked against Zoom's
   API reference on the date above; confirm the two others by name in the Marketplace scope
   picker, which is the authority for your account:

   | Scope | Why |
   | --- | --- |
   | `user:read:user` | Identify the signed-in user (`GET /users/me`) |
   | `meeting:read:meeting` | Look up a meeting's host (`GET /meetings/{id}`) |
   | `cloud_recording:read:list_recording_files` | List the meeting's recording files, including the transcript (`GET /meetings/{id}/recordings`) |

4. **Client secret.** Zoom's token endpoint always requires the app's client secret (HTTP Basic
   authentication), even with PKCE. Distribute it to users like any credential (a password
   manager), never in the shared file. Each user enters it once, with hidden input.
5. **Distribute the non-secret config:**

   ```json
   {
     "schema": "agent-skills.meeting-native-config/v1",
     "zoom": {
       "client_id": "<Client ID>",
       "account_domain": "acme.zoom.us",
       "redirect_uri": "http://localhost:8765/agent-skills/oauth/callback"
     }
   }
   ```

   `account_domain` (optional) is your Zoom vanity domain; a link on another organisation's vanity
   domain is then refused as `external_tenant` before any API call.

## For each user

```bash
agent-skills meeting setup native --import agent-skills-meetings.json
agent-skills meeting setup native --platform zoom
```

Setup asks for the client secret (hidden), opens the browser to authorise the app, stores the
tokens in the credential store, and self-tests with `GET /users/me` (no recording is read).

## Using it

```bash
agent-skills meeting join https://zoom.us/j/81234567890    # before or during
agent-skills meeting fetch https://zoom.us/j/81234567890   # after it ended
```

Record to the cloud; Zoom shows its own recording notice. After the meeting Zoom processes the
recording, then the transcript (`file_type: TRANSCRIPT`, WebVTT); Agent Skills polls until it is
`completed`, downloads it with the access token as a Bearer header (only to a `*.zoom.us` host),
and reads the speaker from each line's `Name:` prefix. Use the numeric meeting link; a personal
link name (`/my/<name>`) cannot be looked up.

## Limitations and what you will see

| Situation | Result |
| --- | --- |
| You are not the meeting's host | `no_access` |
| The meeting is not visible to your account (another organisation's) | `no_access`, or `external_tenant` when `account_domain` is set |
| No cloud recording, or audio transcript switched off | `not_enabled` once the fetch window closes |

## Removing it

`agent-skills access forget --profile meeting-zoom` (tokens and the client secret). Users can also
remove the app under Zoom → Apps → Manage.
