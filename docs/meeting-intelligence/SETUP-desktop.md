# Desktop (local) capture

Your own computer records the meeting and transcribes it locally with whisper.cpp. No bot joins
and no audio leaves the machine. **Nobody in the meeting is notified automatically**, so this is
the strictest mode: you start every recording yourself, in a terminal, after telling everyone.

Supported: **macOS** and **Linux** (PulseAudio or PipeWire). Not supported: Windows and WSL.

## How it works

- `ffmpeg` records **two channels**: left = your microphone ("You"), right = the system audio,
  i.e. everyone else ("Remote participants").
- After you stop, `whisper-cli` transcribes **each channel separately** and the segments are
  merged by time. The channel is the only speaker attribution: remote speakers are not told apart,
  and Meeting Intelligence never guesses names (an action owner is kept only when someone is named
  in what was said, e.g. "Anna will draft the plan").
- Raw audio is headerless 16 kHz PCM, `0600`, under `~/.agent-skills/state/meetings/<id>/audio/`,
  so a crash loses at most the last second and what was recorded is still processed (`PARTIAL`).
  It is **deleted once the transcript is stored** (keep it longer with
  `desktop.delete_audio_after_transcript: false`, for at most `desktop.raw_audio_retention_days`,
  1–7 days).

Use headphones: with speakers, your microphone also picks up the other participants, and their
words appear twice (once as "You").

## Setup

```bash
agent-skills meeting setup desktop [--model small] [--language auto|de|en|…]
```

Run it yourself in a terminal. It checks each step and stops at the first missing one:

1. **ffmpeg** — macOS: `brew install ffmpeg`; Linux: your distribution's `ffmpeg` package.
2. **whisper.cpp** — macOS: `brew install whisper-cpp` (provides `whisper-cli`); Linux: build it
   from github.com/ggml-org/whisper.cpp and put `whisper-cli` on your `PATH`.
3. **A model**, downloaded only when you confirm, from huggingface.co (the whisper.cpp source),
   verified against the SHA-1 whisper.cpp publishes, stored under
   `~/.agent-skills/cache/models/`. Never shipped in a release or the npm package.

   | Model | Size | Notes |
   | --- | --- | --- |
   | `small` (default) | 466 MiB | Multilingual; good German and English on a CPU laptop |
   | `base` | 142 MiB | Faster, less accurate |
   | `large-v3-turbo-q5_0` | 547 MiB | Much better accuracy; wants a GPU / Apple Silicon |
   | `medium`, `large-v3-turbo` | 1.5 GiB | Best accuracy, slowest |
   | `*.en` variants | — | English only |

   `language` defaults to `auto`; set `de`, `en`, … when you know it.
4. **System audio.**
   - **macOS** needs a loopback input in v1. Install a free virtual audio driver such as
     **BlackHole 2ch** (`brew install --cask blackhole-2ch`). Then, in **Audio MIDI Setup**, click **+ →
     Create Multi-Output Device**, tick your headphones/speakers **and** BlackHole, and choose that
     Multi-Output Device as the system output (and in your meeting app's speaker setting). You keep
     hearing the meeting; BlackHole receives a copy. Setup finds the BlackHole input by name.
     macOS asks once for microphone permission for your terminal app.
   - **Linux** uses your default microphone and the default output's `.monitor` source (`pactl
     get-default-source`, `pactl get-default-sink`). Nothing extra to install.
5. **Notice.** The consent notice; type `yes`.
6. **Self-test.** Play some audio (a video will do) and say a sentence: setup records 5 seconds
   from both channels, checks that **both** carry signal, transcribes them with your model, and
   shows the text and how long it took. A silent channel is named with what to check.

`agent-skills doctor` reports whether desktop capture is ready. `doctor --probe-meeting` also
records one second from the **system-audio input only** (never the microphone) to confirm the
loopback is actually receiving audio; nothing is kept.

## Recording a meeting

```bash
agent-skills meeting join <meeting link> --via desktop     # or just `join` if desktop is your default
```

1. It refuses unless you run it in an **interactive terminal** — an AI assistant cannot start it,
   and is instructed to give you this command instead.
2. It prints an announcement to paste into the meeting chat (configurable as
   `desktop.announcement`, never empty):

   > I'm recording and transcribing this meeting locally for my engineering notes. Tell me if you object.

3. You type `everyone agreed` to confirm that all participants were told and agreed. The
   confirmation (time and notice version) is stored on the meeting record.
4. A supervised background recorder starts (`meeting_desktop.py record m_…`, visible in your
   process list, pidfile under the meeting's state directory) and `join` returns:
   `RECORDING — stop with: agent-skills meeting stop <id>`.

`status` and `list` show `● RECORDING locally 00:12:31 (48.1 MB)` for as long as it runs. It stops
on `agent-skills meeting stop <id>` or after `desktop.max_duration_minutes` (default 180, at most
720), whichever is first. Then it finalises the audio, transcribes it chunk by chunk (progress in
`status`; resumable after a crash), deletes the raw audio, and hands the transcript to Meeting
Intelligence. The meeting link only labels the recording; nothing joins anything.

There is no automatic meeting detection, no auto-start, and no calendar trigger.

## Seams

A native macOS capture helper (ScreenCaptureKit or a Core Audio process tap, which would remove the
BlackHole step) is out of scope for this release. It would replace `capture_inputs()` in
`scripts/meeting_desktop.py` for macOS and nothing else.
