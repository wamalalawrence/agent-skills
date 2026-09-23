# Security review — v1.4.0

Follows [the v0.37.0 review](security-review-v0.37.0.md) as the shape. Each threat is labelled
**probed** (a test exercises it), **reasoned about** (argued from the design), or **unproven**.

`1.4.0` makes meeting capture a user choice among three providers. It is the first release that
holds OAuth tokens for third-party platforms (Microsoft Graph, Google Meet, Zoom), the first that
records audio on the user's own machine, and the first that downloads a large binary (a speech
model) at the user's request.

## Scope of this review

- **New:** `scripts/meeting_providers.py`, `meeting_setup.py`, `meeting_http.py`, `meeting_oauth.py`,
  `meeting_native.py`, `meeting_native_teams.py`, `meeting_native_meet.py`, `meeting_native_zoom.py`,
  `meeting_desktop.py`; fixtures `scripts/fixtures/meeting-native/` and the fakes in
  `scripts/fixtures/meeting-desktop/` (test only).
- **Changed:** `scripts/access.py` (`store_identity` / `fetch_identity` extracted from `access set`),
  `meeting.py`, `meeting_capture.py`, `meeting_store.py`, `meeting_intel.py`, `meeting_recall.py`
  (transport moved to `meeting_http.py`), `doctor.sh`, `bin/agent-skills`, the
  `meeting-intelligence` skill, Wamala's routing row.
- No change to the release engine, Execution Guard, the shared redaction pattern set, or the
  knowledge stores.

---

## Threat: an OAuth token or client secret leaks

**Probed.** C9 signs in against a fake authorization server and asserts the refresh token is only
in the credential store's `0600` file (the file backend in the suite; the OS keychain otherwise),
never in `~/.agent-skills/state/` or `meeting.json`. C15 runs every native flow and every read
command (`status`, `inspect --json`, `inspect --transcript --facts`, `status --providers --json`,
the doctor report) and asserts no access token, refresh token, or client secret appears in any
output or any file under the state directory, `meeting.json`, or `credentials.json` (which holds
only field names and expiry times).

Tokens are written through the same `access.store_identity` that `access set` uses, so they are
recorded per field and `access forget --profile meeting-<platform>` removes them. The provider's
handle stored on the meeting record holds only platform meeting ids.

## Threat: a token is sent to the wrong host

**Reasoned about, partly probed.** Every authenticated native request goes through
`PlatformAdapter.request`, which refuses any URL that is not https on the platform's own domain
(`*.microsoft.com`, `*.googleapis.com`, `*.zoom.us`) or loopback. Zoom's transcript `download_url`
comes from the API; it is accepted only on `*.zoom.us` (C7 asserts the Bearer header reaches the
download on `zoom.us`, and that the audio file is never requested). Base-URL overrides exist for
the offline suite and accept only loopback or the vendor's domain (`meeting_http.base_override`).
Redirects never carry `Authorization` to another host and never downgrade to http (the handler
moved unchanged from the Recall adapter; its 1.2.0 test still runs).

## Threat: the OAuth flow is hijacked

**Probed.** Authorization code + PKCE (S256); C9's server recomputes the challenge from the
verifier and a mismatched verifier is refused. `state` is random and compared in constant time;
the callback listener binds `127.0.0.1` only, answers only its redirect path, and never logs the
query. A revoked grant (`invalid_grant`) marks the identity expired, and readiness then says "sign
in again" (C9, C2). Scopes are delegated and read-only; no application permissions exist in v1.

## Threat: an admin's shared config carries a secret

**Probed.** C9 imports three hostile files — a `client_secret` key inside a platform, a secret at
the top level, and a token-shaped `client_id` — and asserts each is refused with `meeting.json`
byte-identical. The accepted keys are a closed list per platform.

## Threat: a meeting is recorded without the participants' knowledge

**Probed.** C11: `join --via desktop` without an interactive terminal is refused (exit `2`) and
prints the command for the user to run; a person who types anything but `everyone agreed` records
nothing; the attestation (time, notice version) is stored on the meeting; the recorder refuses to
run without the attestation file. C3 asserts the skill forbids starting it. There is no flag or
environment variable that skips the terminal check.

**Unproven by design:** a determined operator can drive a pseudo-terminal and type the phrase. The
control is against an assistant starting a recording through the documented CLI, not against the
machine's owner. Documented in `docs/known-limitations.md`.

## Threat: a provider is used, or paid for, without the user choosing it

**Probed.** C1: with nothing configured, `join` opens no socket (a guard fails the test on any
`connect`), creates no state, and prints the preflight. C4: a native refusal with Recall fully
configured never contacts Recall and creates no meeting. `default_provider` is set only by a
completed `meeting setup` (or by the 1.3.0 migration for a Recall key that already existed).

## Threat: argument injection into ffmpeg or whisper-cli

**Probed / reasoned about.** Both are run with argument lists, never a shell. The language is
`auto` or two-to-three lowercase letters; the model is from a fixed allow-list; paths are built
from a validated meeting id. A configured device name that starts with `-` or contains control
characters is discarded (C12 asserts it), so it cannot become an ffmpeg option.

## Threat: a tampered or oversized model

**Probed.** C14: a download whose SHA-1 differs from the digest pinned in the source is deleted and
refused; the URL is fixed to huggingface.co (there is no override); a verified file is `0600`.
Downloads stop at 4 GiB. SHA-1 is what whisper.cpp publishes; it is used only to compare against
that pinned value.

## Threat: local audio or transcripts are readable by others, or kept

**Probed.** C11 asserts the audio directory is `0700`, the raw PCM `0600`, and that the raw audio
(PCM and WAV) is gone once the transcript is stored. Logs and whisper output are `0600` inside the
same directory. A crashed recorder's stale pidfile is cleaned and its surviving `ffmpeg` (verified
by command line, never by pid alone) is stopped.

## Threat: a worker process is confused with another process

**Reasoned about.** Liveness checks require both a live pid and a command line containing
`meeting_desktop.py <role> <meeting id>` (or the meeting's PCM path for ffmpeg), so a recycled pid
is never signalled.

## Threat: API responses steer file or URL paths

**Reasoned about.** Graph ids are URL-quoted; Meet resource names must match
`conferenceRecords/<id>[/transcripts|participants/<id>]` before they become paths; Zoom meeting
numbers come from the local link, digits only.

## Residual risks

- The native adapters have not run against a live tenant; the setup self-test is the first live
  check.
- Transcript text still reaches the host assistant's model provider in every mode; this is
  disclosed in every notice, `join` output, and `PRIVACY.md`.
- Recall's own retention of bot metadata after media deletion is unchanged from 1.2.0 and
  documented.
