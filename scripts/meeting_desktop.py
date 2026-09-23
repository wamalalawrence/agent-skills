#!/usr/bin/env python3
"""DesktopCaptureProvider — record the meeting on this computer, transcribe it locally.

No bot joins and no audio leaves the machine. The user's own computer records
two channels with `ffmpeg` (left = microphone, "You"; right = system audio,
"Remote participants"), and `whisper.cpp` (`whisper-cli`) transcribes each
channel separately after the meeting. The channel *is* the diarization: no
model guesses who spoke, so remote speakers stay one unidentified group.

Because nobody in the meeting is notified automatically, this provider is
stricter than the others, and the rules live in code, not only in docs:

  * It is started only by a person at an interactive terminal. `start()`
    refuses without one, and without the typed attestation that everyone was
    told and agreed (collected by `meeting join`, stored on the meeting).
  * The recorder is a visible, named process (`meeting_desktop.py record
    m_…`), supervised, with a pidfile under the meeting's state directory. It
    stops on `meeting stop`, or at the configured maximum duration, whichever
    comes first. No auto-start, no meeting detection, no calendar trigger.
  * Raw audio is written as headerless 16 kHz s16le PCM, so a crash loses at
    most the last buffer and what was recorded stays processable (PARTIAL).
    It is mode 0600 and deleted once the transcript is stored, by default.

Lifecycle, as the reconciler sees it (all through the ordinary interface):

    start      spawn the supervised recorder          → RECORDING
    poll       read capture.json; clean a stale pid    → RECORDING | MEDIA_READY | FAILED
    fetch      transcription runs in a background      → pending (with progress) | ready
               worker, one chunk at a time, resumable
    delete     remove the raw audio

macOS system audio needs a loopback input (BlackHole, a Multi-Output Device);
a native ScreenCaptureKit / Core Audio tap would replace `capture_inputs()` for
darwin and nothing else — that seam is deliberate. Windows and WSL are not
supported.

Standard library only; `ffmpeg` and `whisper-cli` are the user's own installs.
"""
from __future__ import annotations

import array
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import meeting_capture as mc  # noqa: E402
import meeting_store as store  # noqa: E402

PROVIDER_NAME = "desktop"
SETUP_COMMAND = "agent-skills meeting setup desktop"
SAMPLE_RATE = 16000
CHANNELS = 2
BYTES_PER_SECOND = SAMPLE_RATE * CHANNELS * 2
LABEL_YOU = "You"
LABEL_REMOTE = "Remote participants (unidentified)"
MAX_TRANSCRIBE_ATTEMPTS = 3

# whisper.cpp ggml models. SHA-1 digests as published in whisper.cpp's
# models/README.md (verified 2026-09-23); the download is refused on mismatch.
MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{name}.bin"
MODELS: Dict[str, Tuple[str, str]] = {
    "base": ("465707469ff3a37a2b9b8d8f89f2f99de7299dac", "142 MiB"),
    "base.en": ("137c40403d78fd54d454da0f9bd998f78703390c", "142 MiB"),
    "small": ("55356645c2b361a969dfd0ef2c5a50d530afd8d5", "466 MiB"),
    "small.en": ("db8a495a91d927739e50b3fc1cc4c6b8f6c2d022", "466 MiB"),
    "medium": ("fd9727b6e1217c2f614f9b698455c4ffd82463b4", "1.5 GiB"),
    "medium.en": ("8c30f0e44ce9560643ebd10bbe50cd20eafd3723", "1.5 GiB"),
    "large-v3-turbo-q5_0": ("e050f7970618a659205450ad97eb95a18d69c9ee", "547 MiB"),
    "large-v3-turbo": ("4af2b29d7ec73d781377bfd1758ca957a807e941", "1.5 GiB"),
}
DEFAULT_MODEL = "small"  # multilingual (German and English), usable on a CPU laptop
MAX_MODEL_BYTES = 4 * 1024 ** 3

DEFAULT_ANNOUNCEMENT = ("I'm recording and transcribing this meeting locally for my engineering notes. "
                        "Tell me if you object.")
DEFAULTS: Dict[str, object] = {
    "model": DEFAULT_MODEL,
    "language": "auto",
    "max_duration_minutes": 180,
    "delete_audio_after_transcript": True,
    "raw_audio_retention_days": 1,
    "announcement": DEFAULT_ANNOUNCEMENT,
    "mic_device": "",
    "system_device": "",
    "threads": 0,
    "chunk_seconds": 600,
    "configured_at": "",
}
_LANGUAGE = re.compile(r"^(auto|[a-z]{2,3})$")
_NOISE = re.compile(r"^\s*[\[(][^\])]{0,40}[\])]\s*$")  # [BLANK_AUDIO], (music), [Applause]


# ---------------------------------------------------------------------------
# Configuration and environment
# ---------------------------------------------------------------------------
def settings(config: Dict[str, object]) -> Dict[str, object]:
    raw = config.get("desktop") if isinstance(config.get("desktop"), dict) else {}
    out = dict(DEFAULTS)
    for key in DEFAULTS:
        if key in raw:  # type: ignore[operator]
            out[key] = raw[key]  # type: ignore[index]
    if out["model"] not in MODELS:
        out["model"] = DEFAULT_MODEL
    language = str(out["language"] or "auto").lower()
    out["language"] = language if _LANGUAGE.match(language) else "auto"
    for key, low, high, default in (("max_duration_minutes", 5, 720, 180), ("raw_audio_retention_days", 1, 7, 1),
                                    ("threads", 0, 64, 0), ("chunk_seconds", 60, 1800, 600)):
        try:
            out[key] = max(low, min(high, int(out[key])))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            out[key] = default
    out["delete_audio_after_transcript"] = bool(out["delete_audio_after_transcript"])
    # The announcement may be reworded, never emptied.
    text = " ".join(str(out["announcement"] or "").split())[:400]
    out["announcement"] = text or DEFAULT_ANNOUNCEMENT
    for key in ("mic_device", "system_device"):
        value = str(out[key] or "")[:120]
        # A device name is passed to ffmpeg as an argument: one that starts
        # with "-" or carries control characters could become an option.
        out[key] = "" if value.startswith("-") or any(ord(c) < 32 for c in value) else value
    return out


def unsupported_reason() -> str:
    """Why this OS cannot capture, or "" when it can."""
    if sys.platform.startswith("win") or sys.platform == "cygwin":
        return "desktop capture is not supported on Windows"
    if sys.platform.startswith("linux"):
        try:
            release = Path("/proc/version").read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            release = ""
        if "microsoft" in release or os.environ.get("WSL_DISTRO_NAME"):
            return "desktop capture is not supported on WSL (no access to the Windows audio devices)"
        return ""
    if sys.platform == "darwin":
        return ""
    return "desktop capture is not supported on {}".format(sys.platform)


def ffmpeg_path() -> str:
    return shutil.which("ffmpeg") or ""


def whisper_path() -> str:
    return shutil.which("whisper-cli") or shutil.which("whisper-cpp") or ""


def models_dir() -> Path:
    return store.home_dir() / "cache" / "models"


def model_path(name: str) -> Path:
    return models_dir() / "ggml-{}.bin".format(name)


def _verified_marker(name: str) -> Path:
    return models_dir() / "ggml-{}.bin.sha1".format(name)


def model_verified(name: str) -> bool:
    path, marker = model_path(name), _verified_marker(name)
    if not path.is_file() or not marker.is_file():
        return False
    try:
        return marker.read_text(encoding="utf-8").strip() == MODELS[name][0]
    except OSError:
        return False


def install_hint(tool: str) -> str:
    if tool == "ffmpeg":
        return "brew install ffmpeg" if sys.platform == "darwin" else "sudo apt install ffmpeg (or your distro's package)"
    return ("brew install whisper-cpp" if sys.platform == "darwin"
            else "build whisper.cpp (github.com/ggml-org/whisper.cpp) and put whisper-cli on PATH")


def readiness(config: Dict[str, object]) -> mc.Readiness:
    """Local only. Never records audio (that needs an explicit probe)."""
    reason = unsupported_reason()
    if reason:
        return mc.Readiness(mc.BROKEN, reason, "agent-skills meeting setup --compare")
    opts = settings(config)
    configured = bool(opts.get("configured_at"))
    if not configured and not model_path(str(opts["model"])).exists():
        return mc.Readiness(mc.NOT_CONFIGURED, "local capture is not set up", SETUP_COMMAND)
    if not ffmpeg_path():
        return mc.Readiness(mc.BROKEN, "ffmpeg is not installed", install_hint("ffmpeg") + "; then " + SETUP_COMMAND)
    if not whisper_path():
        return mc.Readiness(mc.BROKEN, "whisper-cli (whisper.cpp) is not installed",
                            install_hint("whisper") + "; then " + SETUP_COMMAND)
    if not model_verified(str(opts["model"])):
        return mc.Readiness(mc.BROKEN, "the whisper model {!r} is missing or unverified".format(opts["model"]),
                            "{} --model {}".format(SETUP_COMMAND, opts["model"]))
    if sys.platform == "darwin" and not opts["system_device"]:
        return mc.Readiness(mc.BROKEN, "no system-audio loopback input is configured (e.g. BlackHole)",
                            SETUP_COMMAND)
    if sys.platform.startswith("linux") and not shutil.which("pactl"):
        return mc.Readiness(mc.BROKEN, "pactl (PulseAudio/PipeWire) is not available", SETUP_COMMAND)
    if not configured:
        return mc.Readiness(mc.BROKEN, "setup did not finish its self-test", SETUP_COMMAND)
    return mc.Readiness(mc.READY, detail="model {}, language {}".format(opts["model"], opts["language"]))


# ---------------------------------------------------------------------------
# Devices
# ---------------------------------------------------------------------------
_AVF_DEVICE = re.compile(r"\]\s*\[(\d+)\]\s+(.+?)\s*$")
LOOPBACK_NAMES = re.compile(r"(?i)blackhole|loopback|soundflower|vb-cable|background music")


def list_audio_devices() -> List[Tuple[str, str]]:
    """[(index, name)] of audio inputs. macOS: from ffmpeg; Linux: from pactl."""
    if sys.platform == "darwin":
        binary = ffmpeg_path()
        if not binary:
            return []
        done = subprocess.run([binary, "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
                              capture_output=True, text=True, timeout=20, check=False)
        devices, audio = [], False
        for line in (done.stderr or "").splitlines():
            if "audio devices" in line.lower():
                audio = True
                continue
            if "video devices" in line.lower():
                audio = False
                continue
            match = _AVF_DEVICE.search(line)
            if audio and match:
                devices.append((match.group(1), match.group(2)))
        return devices
    if shutil.which("pactl"):
        done = subprocess.run(["pactl", "list", "short", "sources"], capture_output=True, text=True,
                              timeout=20, check=False)
        return [(line.split("\t")[1], line.split("\t")[1]) for line in done.stdout.splitlines() if "\t" in line]
    return []


def _pactl_default(kind: str) -> str:
    done = subprocess.run(["pactl", "get-default-" + kind], capture_output=True, text=True, timeout=10, check=False)
    return done.stdout.strip() if done.returncode == 0 else ""


def capture_inputs(opts: Dict[str, object]) -> List[str]:
    """ffmpeg input arguments: first the microphone, then system audio.

    The seam for a native macOS audio helper: replace this for darwin.
    """
    if sys.platform == "darwin":
        devices = {name: index for index, name in list_audio_devices()}
        mic = str(opts["mic_device"])
        system = str(opts["system_device"])
        mic_index = devices.get(mic, "default") if mic else "default"
        if system not in devices:
            raise mc.ProviderRequestError("the loopback input {!r} is not present; run: {}".format(
                system, SETUP_COMMAND))
        return ["-f", "avfoundation", "-i", ":" + str(mic_index), "-f", "avfoundation", "-i", ":" + devices[system]]
    mic = str(opts["mic_device"]) or _pactl_default("source")
    sink = _pactl_default("sink")
    system = str(opts["system_device"]) or (sink + ".monitor" if sink else "")
    if not mic or not system or mic.startswith("-") or system.startswith("-"):
        raise mc.ProviderRequestError("no usable default microphone or output device was found; run: " + SETUP_COMMAND)
    return ["-f", "pulse", "-i", mic, "-f", "pulse", "-i", system]


def ffmpeg_command(opts: Dict[str, object], output: Path, seconds: int) -> List[str]:
    graph = ("[0:a]aresample={r},aformat=channel_layouts=mono[m];"
             "[1:a]aresample={r},aformat=channel_layouts=mono[s];"
             "[m][s]amerge=inputs=2[a]").format(r=SAMPLE_RATE)
    return ([ffmpeg_path(), "-hide_banner", "-nostdin", "-loglevel", "error"] + capture_inputs(opts) +
            ["-filter_complex", graph, "-map", "[a]", "-t", str(int(seconds)), "-ac", str(CHANNELS),
             "-ar", str(SAMPLE_RATE), "-f", "s16le", "-y", str(output)])


# ---------------------------------------------------------------------------
# Files under state/meetings/<id>/
# ---------------------------------------------------------------------------
def audio_dir(meeting_id: str) -> Path:
    return store.meeting_dir(meeting_id) / "audio"


def _file(meeting_id: str, name: str) -> Path:
    return audio_dir(meeting_id) / name


def _private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def _write_json(path: Path, payload: dict) -> None:
    _private_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
    os.replace(str(tmp), str(path))


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _process_matches(pid: int, needle: str) -> bool:
    """Is `pid` alive *and* our own process (not a recycled pid)?"""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return False
    try:
        done = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True,
                              timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return needle in done.stdout


def _pid(meeting_id: str, name: str) -> int:
    try:
        return int(_file(meeting_id, name).read_text(encoding="utf-8").strip() or 0)
    except (OSError, ValueError):
        return 0


def worker_alive(meeting_id: str, role: str) -> bool:
    return _process_matches(_pid(meeting_id, role + ".pid"), "meeting_desktop.py {} {}".format(role, meeting_id))


def _spawn(role: str, meeting_id: str) -> None:
    """Start a detached, visibly named worker: `meeting_desktop.py <role> <id>`."""
    _private_dir(audio_dir(meeting_id))
    fd = os.open(str(_file(meeting_id, role + ".log")), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    log = os.fdopen(fd, "ab")
    try:
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), role, meeting_id],
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True,
                         close_fds=True)
    finally:
        log.close()


# ---------------------------------------------------------------------------
# PCM helpers
# ---------------------------------------------------------------------------
def pcm_seconds(path: Path) -> float:
    try:
        return path.stat().st_size / float(BYTES_PER_SECOND)
    except OSError:
        return 0.0


def channel_rms(pcm: bytes) -> Tuple[float, float]:
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % 4)])
    if sys.byteorder == "big":
        samples.byteswap()
    left, right = samples[0::2], samples[1::2]

    def rms(values) -> float:
        return (sum(v * v for v in values) / len(values)) ** 0.5 if len(values) else 0.0

    return rms(left), rms(right)


def write_stereo_wav(pcm_path: Path, wav_path: Path) -> None:
    """The finalised two-channel WAV (left = microphone, right = system audio)."""
    fd = os.open(str(wav_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as raw, wave.open(raw, "wb") as out, pcm_path.open("rb") as source:
        out.setnchannels(CHANNELS)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        while True:
            block = source.read(BYTES_PER_SECOND * 30)
            block = block[: len(block) - (len(block) % 4)]
            if not block:
                break
            out.writeframes(block)


def write_channel_chunk(wav_path: Path, channel: int, start_s: int, seconds: int, out_path: Path) -> bool:
    """One mono chunk of one channel. False when the chunk holds no audio."""
    with wave.open(str(wav_path), "rb") as source:
        total = source.getnframes()
        first = start_s * SAMPLE_RATE
        if first >= total:
            return False
        source.setpos(first)
        frames = source.readframes(min(seconds * SAMPLE_RATE, total - first))
    samples = array.array("h")
    samples.frombytes(frames)
    mono = samples[channel::2]
    fd = os.open(str(out_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as raw, wave.open(raw, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(mono.tobytes())
    return True


# ---------------------------------------------------------------------------
# Transcription (whisper.cpp)
# ---------------------------------------------------------------------------
def whisper_command(opts: Dict[str, object], wav: Path, prefix: Path) -> List[str]:
    command = [whisper_path(), "-m", str(model_path(str(opts["model"]))), "-f", str(wav),
               "-l", str(opts["language"]), "-oj", "-of", str(prefix), "-np"]
    if int(opts["threads"]):  # type: ignore[arg-type]
        command += ["-t", str(opts["threads"])]
    return command


def parse_whisper_json(path: Path, offset: float) -> Tuple[List[Tuple[float, float, str]], str]:
    data = _read_json(path)
    rows: List[Tuple[float, float, str]] = []
    for item in data.get("transcription") or []:
        if not isinstance(item, dict):
            continue
        text = " ".join(str(item.get("text", "")).split())
        if not text or _NOISE.match(text):
            continue
        offsets = item.get("offsets") if isinstance(item.get("offsets"), dict) else {}
        start = float(offsets.get("from", 0) or 0) / 1000.0 + offset
        end = float(offsets.get("to", 0) or 0) / 1000.0 + offset
        rows.append((start, max(start, end), text))
    result = data.get("result") if isinstance(data.get("result"), dict) else {}
    return rows, str(result.get("language", ""))[:8]


def merge_channels(channels: Dict[int, List[Tuple[float, float, str]]]) -> List[Tuple[str, str, float, float, str]]:
    """Channel 0 → "You", channel 1 → remote. Ordered by start, then channel."""
    labels = {0: (LABEL_YOU, "channel-mic"), 1: (LABEL_REMOTE, "channel-system")}
    rows = []
    for channel, items in channels.items():
        label, ref = labels[channel]
        for start, end, text in items:
            rows.append((start, channel, (label, ref, start, end, text)))
    rows.sort(key=lambda r: (r[0], r[1]))
    return [r[2] for r in rows]


def run_transcription(meeting_id: str, opts: Dict[str, object], progress=None) -> dict:
    """Finalise the audio and transcribe it, chunk by chunk. Resumable.

    Every chunk's whisper output is kept until the transcript is stored, so a
    crash resumes at the first missing chunk. Returns the local transcript.
    """
    folder = audio_dir(meeting_id)
    pcm, wav = folder / "meeting.pcm", folder / "meeting.wav"
    chunks = folder / "chunks"
    _private_dir(chunks)
    if not wav.exists() or wav.stat().st_mtime < pcm.stat().st_mtime:
        write_stereo_wav(pcm, wav)
    seconds = int(pcm_seconds(pcm)) + 1
    step = int(opts["chunk_seconds"])  # type: ignore[arg-type]
    starts = list(range(0, seconds, step))
    total = len(starts) * CHANNELS
    channels: Dict[int, List[Tuple[float, float, str]]] = {0: [], 1: []}
    languages: Dict[str, int] = {}
    done = 0
    for channel in range(CHANNELS):
        for index, start in enumerate(starts):
            prefix = chunks / "c{}_{:04d}".format(channel, index)
            output = prefix.with_suffix(".json")
            if not output.exists():
                chunk = prefix.with_suffix(".wav")
                if write_channel_chunk(wav, channel, start, step, chunk):
                    run = subprocess.run(whisper_command(opts, chunk, prefix), stdin=subprocess.DEVNULL,
                                         capture_output=True, timeout=max(600, step * 20), check=False)
                    try:
                        chunk.unlink()
                    except OSError:
                        pass
                    if run.returncode != 0 or not output.exists():
                        raise RuntimeError("whisper-cli failed on chunk {} (exit {})".format(prefix.name, run.returncode))
                    os.chmod(str(output), 0o600)
                else:
                    _write_json(output, {"transcription": []})
            rows, language = parse_whisper_json(output, float(start))
            channels[channel].extend(rows)
            if language:
                languages[language] = languages.get(language, 0) + len(rows)
            done += 1
            state = _read_json(folder / "progress.json")
            state.update({"done": done, "total": total, "updated_at": _now_iso()})
            _write_json(folder / "progress.json", state)
            if progress:
                progress(done, total)
    language = str(opts["language"])
    if language == "auto" and languages:
        language = max(languages, key=languages.get)
    capture = _read_json(folder / "capture.json")
    result = {
        "utterances": merge_channels(channels),
        "language": language,
        "partial": bool(capture.get("partial")),
        "seconds": pcm_seconds(pcm),
        "model": opts["model"],
    }
    _write_json(folder / "transcript-local.json", result)
    return result


# ---------------------------------------------------------------------------
# Workers: `meeting_desktop.py record|transcribe <meeting-id>`
# ---------------------------------------------------------------------------
_STOP = {"requested": False}


def _on_term(_signum, _frame) -> None:
    _STOP["requested"] = True


def record_worker(meeting_id: str) -> int:
    folder = audio_dir(meeting_id)
    _private_dir(folder)
    capture_file = folder / "capture.json"
    if not (folder / "attestation.json").exists():
        _write_json(capture_file, {"state": "ended", "reason": "no_attestation", "bytes": 0, "ended_at": _now_iso()})
        return 2
    opts = settings(store.load_config())
    limit = int(opts["max_duration_minutes"]) * 60  # type: ignore[arg-type]
    pcm = folder / "meeting.pcm"
    (folder / "record.pid").write_text(str(os.getpid()), encoding="utf-8")
    signal.signal(signal.SIGTERM, _on_term)
    signal.signal(signal.SIGINT, _on_term)
    started = time.monotonic()
    try:
        command = ffmpeg_command(opts, pcm, limit)
        fd = os.open(str(pcm), os.O_WRONLY | os.O_CREAT, 0o600)  # 0600 before ffmpeg writes a byte
        os.close(fd)
        log_fd = os.open(str(folder / "ffmpeg.log"), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(log_fd, "ab") as log:
            child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=log)
    except (OSError, mc.ProviderError) as exc:
        _write_json(capture_file, {"state": "ended", "reason": "recorder_failed", "bytes": 0,
                                   "ended_at": _now_iso(), "error": str(getattr(exc, "message", type(exc).__name__))[:200]})
        return 1
    _write_json(capture_file, {"state": "recording", "started_at": _now_iso(), "ffmpeg_pid": child.pid,
                               "max_seconds": limit})
    reason = "stopped"
    while True:
        if child.poll() is not None:
            # ffmpeg ends on its own with status 0 only when its `-t` limit is
            # reached; anything else before a stop request is a crash.
            if child.returncode == 0:
                reason = "stopped" if _STOP["requested"] else "max_duration"
            else:
                reason = "stopped" if _STOP["requested"] else "crashed"
            break
        if _STOP["requested"]:
            reason = "stopped"
            break
        if time.monotonic() - started >= limit:
            reason = "max_duration"
            break
        time.sleep(0.5)
    if child.poll() is None:
        child.send_signal(signal.SIGINT)  # ffmpeg flushes and exits cleanly on SIGINT
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)
    size = pcm.stat().st_size if pcm.exists() else 0
    _write_json(capture_file, {"state": "ended", "reason": reason, "bytes": size, "ended_at": _now_iso(),
                               "partial": reason == "crashed", "seconds": round(size / float(BYTES_PER_SECOND), 1)})
    try:
        (folder / "record.pid").unlink()
    except OSError:
        pass
    if size:
        return transcribe_worker(meeting_id)
    return 0


def transcribe_worker(meeting_id: str) -> int:
    folder = audio_dir(meeting_id)
    (folder / "transcribe.pid").write_text(str(os.getpid()), encoding="utf-8")
    try:
        state = _read_json(folder / "progress.json")
        attempts = int(state.get("attempts", 0)) + 1
        state["attempts"] = attempts
        _write_json(folder / "progress.json", state)
        try:
            run_transcription(meeting_id, settings(store.load_config()))
        except (RuntimeError, OSError, subprocess.SubprocessError, wave.Error) as exc:
            state = _read_json(folder / "progress.json")
            state.update({"attempts": attempts, "error": str(exc)[:200]})
            _write_json(folder / "progress.json", state)
            return 1
        return 0
    finally:
        try:
            (folder / "transcribe.pid").unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# The provider
# ---------------------------------------------------------------------------
def interactive() -> bool:
    """A person at a terminal. Tests replace this; there is no flag to skip it."""
    return os.isatty(0) and os.isatty(1)


class DesktopCaptureProvider(mc.MeetingCaptureProvider):
    name = PROVIDER_NAME

    def __init__(self, config: Dict[str, object]) -> None:
        self._config = config
        self._opts = settings(config)

    def capabilities(self) -> mc.Capabilities:
        return mc.Capabilities(
            provider=PROVIDER_NAME, join_live=False, fetch_existing_transcript=False, diarization="none",
            retention_control=True, chat_notice=False, webhooks=False,
            transcription_methods=("local_whisper",), platforms=mc.PLATFORMS + ("other",),
            live_capture=False, post_meeting_fetch=True, visible_participant=False,
            speaker_attribution="channel", third_party_processing=False, per_hour_cost=False,
            languages=("auto", "de", "en", "fr", "es", "it", "nl", "pl", "pt"),
        )

    def readiness(self) -> mc.Readiness:
        return readiness(self._config)

    def resolve(self, meeting_url: str) -> mc.MeetingRef:
        """The URL only labels the meeting; any https meeting link will do."""
        try:
            platform, display = mc.classify_meeting_url(meeting_url)
        except mc.MeetingUrlError:
            url = (meeting_url or "").strip()
            host = ""
            if url.startswith("https://") and len(url) <= mc.MAX_URL_LENGTH and not any(ord(c) < 33 for c in url):
                from urllib.parse import urlsplit

                parts = urlsplit(url)
                host = (parts.hostname or "") if not (parts.username or parts.password) else ""
            if not re.match(r"^[a-z0-9.-]{3,253}$", host):
                raise mc.MeetingRefusal("unsupported_platform", "give the meeting's https link; it is used only "
                                        "to label the recording") from None
            platform, display = "other", "https://" + host + "/..."
        return mc.MeetingRef(platform=platform, display_url=display,
                             note="Nothing joins the meeting; this computer records it locally.")

    def start(self, meeting_url: str, options: mc.CaptureOptions) -> mc.CaptureHandle:
        if not interactive():
            raise mc.ProviderRequestError("desktop recording can only be started by a person at an interactive "
                                          "terminal")
        attestation = getattr(options, "attestation", None)
        if not isinstance(attestation, dict) or not attestation.get("confirmed_at"):
            raise mc.ProviderRequestError("desktop recording needs the participants' consent attestation first")
        meeting_id = options.correlation_id
        folder = audio_dir(meeting_id)
        _private_dir(folder)
        _write_json(folder / "attestation.json", attestation)
        _spawn("record", meeting_id)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            capture = _read_json(folder / "capture.json")
            if capture.get("state") == "recording":
                return mc.CaptureHandle(PROVIDER_NAME, meeting_id)
            if capture.get("state") == "ended":
                raise mc.ProviderRequestError("the recorder did not start ({}); see {}".format(
                    capture.get("reason", "unknown"), _file(meeting_id, "record.log")))
            time.sleep(0.2)
        raise mc.ProviderRequestError("the recorder did not report within 10 s; see {}".format(
            _file(meeting_id, "record.log")))

    def _id(self, handle: mc.CaptureHandle) -> str:
        if handle.provider != PROVIDER_NAME or not store.MEETING_ID_RE.match(handle.provider_ref):
            raise mc.ProviderRequestError("capture handle does not belong to this provider")
        return handle.provider_ref

    def poll(self, handle: mc.CaptureHandle) -> mc.LifecycleObservation:
        meeting_id = self._id(handle)
        folder = audio_dir(meeting_id)
        capture = _read_json(folder / "capture.json")
        if capture.get("state") == "recording" and not worker_alive(meeting_id, "record"):
            # The supervisor died without finishing: stop a surviving ffmpeg of
            # ours, keep what was recorded, and mark it partial.
            ffmpeg = int(capture.get("ffmpeg_pid") or 0)
            if _process_matches(ffmpeg, str(folder / "meeting.pcm")):
                try:
                    os.kill(ffmpeg, signal.SIGINT)
                except OSError:
                    pass
            size = (folder / "meeting.pcm").stat().st_size if (folder / "meeting.pcm").exists() else 0
            capture = {"state": "ended", "reason": "crashed", "bytes": size, "partial": True,
                       "ended_at": _now_iso(), "seconds": round(size / float(BYTES_PER_SECOND), 1)}
            _write_json(folder / "capture.json", capture)
            try:
                (folder / "record.pid").unlink()
            except OSError:
                pass
        if capture.get("state") == "recording":
            return mc.LifecycleObservation(mc.RECORDING)
        if capture.get("state") != "ended":
            return mc.LifecycleObservation(mc.FAILED, reason="recorder_did_not_start")
        size = int(capture.get("bytes") or 0)
        if size <= 0:
            return mc.LifecycleObservation(mc.FAILED, reason="ended_without_media")
        return mc.LifecycleObservation(mc.MEDIA_READY, reason=str(capture.get("reason", ""))[:40],
                                       recording_seconds=size / float(BYTES_PER_SECOND), has_media=True)

    def activity(self, handle: mc.CaptureHandle) -> str:
        meeting_id = self._id(handle)
        folder = audio_dir(meeting_id)
        capture = _read_json(folder / "capture.json")
        if capture.get("state") == "recording":
            seconds = pcm_seconds(folder / "meeting.pcm")
            size = (folder / "meeting.pcm").stat().st_size if (folder / "meeting.pcm").exists() else 0
            return "RECORDING locally {} ({:.1f} MB) — stop with: agent-skills meeting stop {}".format(
                mc.format_ts(seconds), size / 1e6, meeting_id)
        progress = _read_json(folder / "progress.json")
        if progress.get("total") and not _file(meeting_id, "transcript-local.json").exists():
            return "transcribing locally: {}/{} chunk(s)".format(progress.get("done", 0), progress["total"])
        return ""

    def stop(self, handle: mc.CaptureHandle) -> None:
        meeting_id = self._id(handle)
        pid = _pid(meeting_id, "record.pid")
        if _process_matches(pid, "meeting_desktop.py record " + meeting_id):
            os.kill(pid, signal.SIGTERM)

    def fetch_transcript(self, handle: mc.CaptureHandle, meeting_id: str, method: str) -> mc.TranscriptResult:
        self._id(handle)
        folder = audio_dir(meeting_id)
        result = _read_json(folder / "transcript-local.json")
        if result:
            transcript = mc.build_transcript(meeting_id, "local_whisper",
                                             [tuple(u) for u in result.get("utterances") or []])  # type: ignore[misc]
            transcript.speaker_attribution = "channel"
            transcript.capture_provider = PROVIDER_NAME
            transcript.language = str(result.get("language", ""))
            if not transcript.usable:
                return mc.TranscriptResult("unavailable", "local_whisper", reason="nothing_was_said")
            return mc.TranscriptResult("ready", "local_whisper", transcript=transcript,
                                       partial=bool(result.get("partial")))
        if worker_alive(meeting_id, "record") or worker_alive(meeting_id, "transcribe"):
            return mc.TranscriptResult("pending", "local_whisper", progress=self.activity(handle))
        progress = _read_json(folder / "progress.json")
        if int(progress.get("attempts", 0)) >= MAX_TRANSCRIBE_ATTEMPTS:
            return mc.TranscriptResult("unavailable", "local_whisper", reason="local_transcription_failed")
        if not (folder / "meeting.pcm").exists():
            return mc.TranscriptResult("unavailable", "local_whisper", reason="audio_missing")
        _spawn("transcribe", meeting_id)
        return mc.TranscriptResult("pending", "local_whisper", progress="local transcription started")

    def delete_media(self, handle: mc.CaptureHandle) -> None:
        meeting_id = self._id(handle)
        if worker_alive(meeting_id, "record") or worker_alive(meeting_id, "transcribe"):
            raise mc.ProviderRequestError("the recorder or transcriber is still running")
        folder = audio_dir(meeting_id)
        for name in ("meeting.pcm", "meeting.wav", "transcript-local.json"):
            try:
                (folder / name).unlink()
            except FileNotFoundError:
                pass
        shutil.rmtree(str(folder / "chunks"), ignore_errors=True)


# ---------------------------------------------------------------------------
# Setup helpers: model download, self-test
# ---------------------------------------------------------------------------
def download_model(name: str, report=print, opener=None) -> Path:
    """Download one model from the official source and verify its SHA-1. Refuses a mismatch."""
    if name not in MODELS:
        raise ValueError("unknown model {!r}; choose one of {}".format(name, ", ".join(MODELS)))
    expected = MODELS[name][0]
    target = model_path(name)
    _private_dir(models_dir())
    if model_verified(name):
        return target
    partial = target.with_suffix(".bin.part")
    url = MODEL_URL.format(name=name)  # the official source only; there is no override
    digest = hashlib.sha1()  # noqa: S324 - compared to the digest upstream publishes, not used as a key
    report("Downloading ggml-{}.bin ({}) from huggingface.co".format(name, MODELS[name][1]))
    fetch = opener or (lambda target_url: urllib.request.urlopen(target_url, timeout=60))
    fd = os.open(str(partial), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    written = 0
    with fetch(url) as response, os.fdopen(fd, "wb") as out:  # type: ignore[operator]
        while True:
            block = response.read(1 << 20)
            if not block:
                break
            written += len(block)
            if written > MAX_MODEL_BYTES:
                break  # the checksum below then refuses it
            digest.update(block)
            out.write(block)
    if digest.hexdigest() != expected:
        partial.unlink()
        raise ValueError("checksum mismatch for ggml-{}.bin: the download was deleted, nothing is used".format(name))
    os.replace(str(partial), str(target))
    _verified_marker(name).write_text(expected + "\n", encoding="utf-8")
    return target


def self_test(config: Dict[str, object], work: Path, seconds: int = 5, report=print) -> dict:
    """Record `seconds` from both channels, check both carry signal, transcribe each."""
    opts = settings(config)
    _private_dir(work)
    pcm = work / "self-test.pcm"
    command = ffmpeg_command(opts, pcm, seconds)
    begin = time.monotonic()
    run = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, timeout=seconds + 30, check=False)
    if run.returncode != 0 or not pcm.exists():
        raise RuntimeError("ffmpeg could not record from the configured devices (exit {})".format(run.returncode))
    left, right = channel_rms(pcm.read_bytes())
    result = {"mic_rms": round(left, 1), "system_rms": round(right, 1), "record_seconds": round(time.monotonic() - begin, 1)}
    wav = work / "self-test.wav"
    write_stereo_wav(pcm, wav)
    texts = {}
    start = time.monotonic()
    for channel, label in ((0, "microphone"), (1, "system audio")):
        chunk = work / "self-test-c{}.wav".format(channel)
        write_channel_chunk(wav, channel, 0, seconds + 1, chunk)
        prefix = work / "self-test-c{}".format(channel)
        done = subprocess.run(whisper_command(opts, chunk, prefix), stdin=subprocess.DEVNULL, capture_output=True,
                              timeout=600, check=False)
        if done.returncode != 0:
            raise RuntimeError("whisper-cli failed (exit {}); check the model and the binary".format(done.returncode))
        rows, _ = parse_whisper_json(prefix.with_suffix(".json"), 0.0)
        texts[label] = " ".join(r[2] for r in rows)
    result["transcribe_seconds"] = round(time.monotonic() - start, 1)
    result["texts"] = texts
    shutil.rmtree(str(work), ignore_errors=True)
    return result


SIGNAL_FLOOR = 30.0  # RMS on 16-bit samples; silence from a live device sits well below this


def probe_loopback(config: Dict[str, object], seconds: int = 1) -> str:
    """Is the system-audio input present and receiving audio? Records ONLY that input.

    For `doctor --probe-meeting`: one second from the loopback (macOS) or the
    output monitor (Linux), never the microphone, written nowhere.
    """
    reason = unsupported_reason()
    if reason:
        return reason
    if not ffmpeg_path():
        return "ffmpeg is not installed"
    opts = settings(config)
    inputs = capture_inputs(opts)[4:]  # the second input: system audio only
    command = [ffmpeg_path(), "-hide_banner", "-nostdin", "-loglevel", "error"] + inputs + [
        "-t", str(seconds), "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "-"]
    done = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, timeout=seconds + 20, check=False)
    if done.returncode != 0:
        return "the system-audio input could not be opened"
    samples = array.array("h")
    samples.frombytes(done.stdout[: len(done.stdout) - (len(done.stdout) % 2)])
    level = (sum(v * v for v in samples) / len(samples)) ** 0.5 if len(samples) else 0.0
    if level < SIGNAL_FLOOR:
        return "system-audio input present but silent (play something and re-run, or check the Multi-Output Device)"
    return "system-audio input present and receiving audio"


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2 or argv[0] not in ("record", "transcribe") or not store.MEETING_ID_RE.match(argv[1]):
        print("usage: meeting_desktop.py record|transcribe <meeting-id> (internal; started by agent-skills meeting)",
              file=sys.stderr)
        return 2
    return record_worker(argv[1]) if argv[0] == "record" else transcribe_worker(argv[1])


if __name__ == "__main__":
    sys.exit(main())
