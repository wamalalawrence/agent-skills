#!/usr/bin/env python3
"""The meeting capture boundary, in Agent Skills terms only.

Agent Skills owns Meeting Intelligence. A capture provider is transport: it
puts a visible participant in a meeting, records, transcribes, and hands back a
transcript. Everything on this side of the boundary speaks the types below and
nothing else — no provider type, field name, status code, or identifier crosses
it. A provider's own identifier is carried as an opaque string in
`CaptureHandle.provider_ref` and is never interpreted outside the provider.

    MeetingCaptureProvider
        ├── RecallMeetingBotProvider        meeting_recall.py    id "recall"
        ├── NativeTranscriptProvider        meeting_native.py    id "native"
        │     (Teams / Google Meet / Zoom adapters: meeting_native_*.py)
        └── DesktopCaptureProvider          meeting_desktop.py   id "desktop"

The user chooses the provider (`meeting setup`, `join --via`); nothing here
picks one. `capabilities()` describes what a provider can do and what it costs
the user in money and data flow; `readiness()` says, without the network,
whether it can run and the one command that fixes it when it cannot;
`resolve()` turns a meeting link into a provider-neutral reference or a typed
refusal. `meeting_providers.py` is the only module that constructs providers.
`test-meeting.py` asserts that the Meeting Intelligence modules import nothing
provider-specific.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlsplit

# ---------------------------------------------------------------------------
# Lifecycle states. Providers map their own states onto these; nothing else is
# ever branched on.
# ---------------------------------------------------------------------------
CREATED = "CREATED"
JOINING = "JOINING"
WAITING_ROOM = "WAITING_ROOM"
IN_CALL_NOT_RECORDING = "IN_CALL_NOT_RECORDING"
RECORDING = "RECORDING"
ENDED = "ENDED"
MEDIA_READY = "MEDIA_READY"
TRANSCRIPT_READY = "TRANSCRIPT_READY"
PROCESSING = "PROCESSING"
PROCESSED = "PROCESSED"
PARTIAL = "PARTIAL"
REJECTED = "REJECTED"
PERMISSION_DENIED = "PERMISSION_DENIED"
TIMED_OUT = "TIMED_OUT"
FAILED = "FAILED"
PURGED = "PURGED"

# Progress order. A transition to a lower rank is refused: an older or
# duplicate observation can never move a meeting backwards.
RANK: Dict[str, int] = {
    CREATED: 0,
    JOINING: 1,
    WAITING_ROOM: 2,
    IN_CALL_NOT_RECORDING: 3,
    RECORDING: 4,
    ENDED: 5,
    MEDIA_READY: 6,
    TRANSCRIPT_READY: 7,
    PROCESSING: 8,
    PROCESSED: 9,
    PARTIAL: 9,
    REJECTED: 50,
    PERMISSION_DENIED: 50,
    TIMED_OUT: 50,
    FAILED: 50,
    PURGED: 60,
}
FAILURE_STATES = (REJECTED, PERMISSION_DENIED, TIMED_OUT, FAILED)
TERMINAL_STATES = FAILURE_STATES + (PROCESSED, PARTIAL, PURGED)
# States in which the provider still has something to tell us.
PROVIDER_ACTIVE_STATES = (CREATED, JOINING, WAITING_ROOM, IN_CALL_NOT_RECORDING, RECORDING)

SOURCE_METHODS = ("captions", "provider_transcription", "async", "native", "local_whisper")

# How the speakers in a transcript were told apart.
#   named    the platform or provider attributed each utterance to a participant
#   channel  audio channels only: the local microphone vs. everyone else
#   none     no attribution at all
ATTRIBUTIONS = ("named", "channel", "none")

# Readiness states. Computed locally: never a network call.
READY = "ready"
NOT_CONFIGURED = "not_configured"
BROKEN = "broken"

# Typed refusals from resolve(). A refusal is an answer, not a failure to
# retry, and it never triggers another provider.
REFUSALS = (
    "unsupported_platform",
    "external_tenant",
    "no_access",
    "not_found",
    "not_enabled",
    "not_yet_available",
    "unsupported_meeting",
)


class ProviderError(Exception):
    """A provider call failed. `kind` maps to the frozen exit-code contract."""

    kind = "provider"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ProviderAuthError(ProviderError):
    kind = "auth"


class ProviderNetworkError(ProviderError):
    kind = "network"


class ProviderPayloadError(ProviderError):
    kind = "integrity"


class ProviderRequestError(ProviderError):
    """The provider refused the request as invalid (not transient)."""

    kind = "usage"


class MeetingRefusal(Exception):
    """The chosen provider cannot serve this meeting. Maps to exit 2 (usage).

    `code` is one of REFUSALS. The message says why and what the user can do;
    the caller adds the alternatives. Never a reason to try another provider.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code if code in REFUSALS else "unsupported_meeting"
        self.message = message


@dataclass
class Capabilities:
    provider: str
    join_live: bool
    fetch_existing_transcript: bool
    diarization: str  # "platform" | "provider" | "none"
    retention_control: bool
    chat_notice: bool
    webhooks: bool
    transcription_methods: Tuple[str, ...]
    platforms: Tuple[str, ...]
    # Added in 1.4.0, defaulted so a provider written against 1.3.0 still builds.
    live_capture: bool = False
    post_meeting_fetch: bool = False
    visible_participant: bool = False
    speaker_attribution: str = "named"  # one of ATTRIBUTIONS
    third_party_processing: bool = False
    per_hour_cost: bool = False
    languages: Tuple[str, ...] = ("auto",)


@dataclass
class Readiness:
    state: str  # READY | NOT_CONFIGURED | BROKEN
    reason: str = ""
    fix_command: str = ""
    detail: str = ""  # a short, secret-free note ("Teams: ready; Zoom: not configured")

    @property
    def ready(self) -> bool:
        return self.state == READY

    def to_dict(self) -> dict:
        return {"state": self.state, "reason": self.reason, "fix_command": self.fix_command,
                "detail": self.detail}


@dataclass
class MeetingRef:
    """A provider-neutral reference to one meeting, from resolve()."""

    platform: str  # one of PLATFORMS, or "other" (desktop labels any meeting)
    display_url: str
    provider_ref: str = ""  # opaque, provider-owned (e.g. a platform meeting id)
    has_ended: Optional[bool] = None  # None when the provider cannot tell
    note: str = ""  # one line for the user, already worded


@dataclass
class CaptureOptions:
    bot_name: str
    chat_notice: str
    live_method: str  # "captions" | "provider_transcription"
    retention_hours: int
    waiting_room_timeout: int
    noone_joined_timeout: int
    everyone_left_timeout: int
    correlation_id: str  # Agent Skills' own meeting id, attached as metadata
    ref: Optional[MeetingRef] = None  # from resolve(), when the provider resolved one
    # The participants' consent attestation, when the provider requires one
    # (desktop): {"confirmed_at", "notice_version", "announcement"}.
    attestation: Optional[dict] = None


@dataclass
class CaptureHandle:
    provider: str
    provider_ref: str  # opaque; only the provider interprets it

    def to_dict(self) -> dict:
        return {"provider": self.provider, "provider_ref": self.provider_ref}

    @staticmethod
    def from_dict(data: dict) -> "CaptureHandle":
        return CaptureHandle(str(data.get("provider", "")), str(data.get("provider_ref", "")))


@dataclass
class LifecycleObservation:
    state: str
    reason: str = ""  # provider sub-code, redacted, for diagnosis only
    recording_seconds: Optional[float] = None
    has_media: bool = False


@dataclass
class Segment:
    meeting_id: str
    segment_id: str
    speaker_label: str
    participant_ref: str
    start_ts: float
    end_ts: float
    text: str
    source_method: str

    def to_dict(self) -> dict:
        return {
            "segment_id": self.segment_id,
            "speaker_label": self.speaker_label,
            "participant_ref": self.participant_ref,
            "start_ts": round(self.start_ts, 2),
            "end_ts": round(self.end_ts, 2),
            "text": self.text,
            "source_method": self.source_method,
        }

    @staticmethod
    def from_dict(meeting_id: str, data: dict) -> "Segment":
        return Segment(
            meeting_id=meeting_id,
            segment_id=str(data["segment_id"]),
            speaker_label=str(data.get("speaker_label", "")),
            participant_ref=str(data.get("participant_ref", "")),
            start_ts=float(data.get("start_ts", 0.0)),
            end_ts=float(data.get("end_ts", 0.0)),
            text=str(data.get("text", "")),
            source_method=str(data.get("source_method", "")),
        )


@dataclass
class NormalisedTranscript:
    meeting_id: str
    source_method: str
    segments: List[Segment] = field(default_factory=list)
    speaker_attribution: str = "named"  # one of ATTRIBUTIONS
    capture_provider: str = ""
    language: str = ""  # BCP-47-ish code the provider reported, or "auto"/""

    @property
    def usable(self) -> bool:
        return any(s.text.strip() for s in self.segments)

    def span_seconds(self) -> float:
        if not self.segments:
            return 0.0
        return max(s.end_ts for s in self.segments) - min(s.start_ts for s in self.segments)


@dataclass
class TranscriptResult:
    status: str  # "ready" | "pending" | "unavailable"
    method: str = ""
    transcript: Optional[NormalisedTranscript] = None
    reason: str = ""
    partial: bool = False  # the provider knows the capture itself was incomplete
    progress: str = ""  # while pending: a short, secret-free progress line


@dataclass
class ProviderEvent:
    """A verified provider notification. A hint to reconcile, never state."""

    event_id: str
    provider_ref: str
    correlation_id: str


class MeetingCaptureProvider:
    """The interface every capture provider implements."""

    name = "abstract"

    def capabilities(self) -> Capabilities:
        raise NotImplementedError

    def readiness(self) -> Readiness:
        """Can this provider run on this machine now? Local checks only."""
        return Readiness(READY)

    def resolve(self, meeting_url: str) -> MeetingRef:
        """A meeting reference, or MeetingRefusal. The default only classifies
        the link locally; a provider that must ask its platform overrides it."""
        try:
            platform, display = classify_meeting_url(meeting_url)
        except MeetingUrlError as exc:
            raise MeetingRefusal("unsupported_platform", str(exc)) from None
        return MeetingRef(platform=platform, display_url=display)

    def start(self, meeting_url: str, options: CaptureOptions) -> CaptureHandle:
        raise NotImplementedError

    def poll(self, handle: CaptureHandle) -> LifecycleObservation:
        raise NotImplementedError

    def stop(self, handle: CaptureHandle) -> None:
        raise NotImplementedError

    def activity(self, handle: CaptureHandle) -> str:
        """One secret-free line about work in progress (elapsed time, size, progress)."""
        return ""

    def fetch_transcript(self, handle: CaptureHandle, meeting_id: str, method: str) -> TranscriptResult:
        raise NotImplementedError

    def request_async_transcript(self, handle: CaptureHandle) -> bool:
        """Ask for post-meeting transcription of retained media. False if impossible."""
        return False

    def delete_media(self, handle: CaptureHandle) -> None:
        raise NotImplementedError

    def verify_event(self, headers: Dict[str, str], body: bytes, now: float) -> Optional[ProviderEvent]:
        """Authenticate a provider notification; None when it does not verify."""
        return None


# ---------------------------------------------------------------------------
# Meeting URLs. Validated locally, before any provider call: an unknown shape
# creates nothing.
# ---------------------------------------------------------------------------
PLATFORMS = ("zoom", "google_meet", "teams")
PLATFORM_LABELS = {"zoom": "Zoom", "google_meet": "Google Meet", "teams": "Microsoft Teams"}

_ZOOM_HOST = re.compile(r"^(?:[a-z0-9-]+\.)*zoom(?:gov)?\.(?:us|com)$")
_ZOOM_PATH = re.compile(r"^/(?:j|w|s|wc/join|my)/[A-Za-z0-9._-]{3,64}/?$")
_MEET_PATH = re.compile(r"^/[a-z]{3}-[a-z]{4}-[a-z]{3}/?$")
_TEAMS_HOSTS = ("teams.microsoft.com", "teams.live.com", "teams.microsoft.us", "gov.teams.microsoft.us")
_TEAMS_PATH = re.compile(r"^/(?:l/meetup-join/\S{8,}|meet/\d{6,20}/?)$")
MAX_URL_LENGTH = 2048


class MeetingUrlError(ValueError):
    pass


def classify_meeting_url(raw: str) -> Tuple[str, str]:
    """Return (platform, display_url) or raise MeetingUrlError.

    The display form drops the query and fragment: a Zoom `pwd=` is a meeting
    passcode, and nothing stored or printed needs it.
    """
    url = (raw or "").strip()
    if not url or len(url) > MAX_URL_LENGTH:
        raise MeetingUrlError("meeting URL is empty or too long")
    if any(ord(ch) < 33 or ord(ch) == 127 for ch in url):
        raise MeetingUrlError("meeting URL contains whitespace or control characters")
    try:
        parts = urlsplit(url)
    except ValueError:
        raise MeetingUrlError("meeting URL could not be parsed") from None
    if parts.scheme != "https":
        raise MeetingUrlError("meeting URL must use https")
    if parts.username or parts.password or parts.port not in (None, 443):
        raise MeetingUrlError("meeting URL must not carry credentials or a custom port")
    host = (parts.hostname or "").lower()
    path = parts.path or "/"
    platform = ""
    if _ZOOM_HOST.match(host) and _ZOOM_PATH.match(path):
        platform = "zoom"
    elif host == "meet.google.com" and _MEET_PATH.match(path):
        platform = "google_meet"
    elif host in _TEAMS_HOSTS and _TEAMS_PATH.match(path):
        platform = "teams"
    if not platform:
        raise MeetingUrlError(
            "not a recognised Microsoft Teams, Google Meet, or Zoom meeting link"
        )
    # A Teams join path embeds the thread and tenant; the display form keeps
    # only enough to recognise the link.
    shown_path = "/l/meetup-join/..." if path.startswith("/l/meetup-join/") else path
    return platform, "https://" + host + shown_path


# ---------------------------------------------------------------------------
# Transcript normalisation, shared by every provider.
# ---------------------------------------------------------------------------
MAX_SEGMENT_CHARS = 900


def segment_id(meeting_id: str, method: str, ordinal: int, start: float, speaker: str) -> str:
    """Stable and deterministic, so re-ingesting a transcript never duplicates facts."""
    raw = "{}|{}|{}|{:.2f}|{}".format(meeting_id, method, ordinal, start, speaker)
    return "s_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _split_long(text: str) -> List[str]:
    if len(text) <= MAX_SEGMENT_CHARS:
        return [text]
    pieces: List[str] = []
    current = ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        while len(sentence) > MAX_SEGMENT_CHARS:
            cut = sentence.rfind(" ", 0, MAX_SEGMENT_CHARS)
            cut = cut if cut > 0 else MAX_SEGMENT_CHARS
            if current:
                pieces.append(current)
                current = ""
            pieces.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if current and len(current) + 1 + len(sentence) > MAX_SEGMENT_CHARS:
            pieces.append(current)
            current = sentence
        else:
            current = (current + " " + sentence).strip()
    if current:
        pieces.append(current)
    return [p for p in pieces if p]


def build_transcript(
    meeting_id: str,
    method: str,
    utterances: List[Tuple[str, str, float, float, str]],
) -> NormalisedTranscript:
    """Utterances are (speaker_label, participant_ref, start, end, text), in order.

    Long utterances are split at sentence boundaries so every segment fits a
    window; the split pieces share the utterance's timing proportionally.
    """
    transcript = NormalisedTranscript(meeting_id=meeting_id, source_method=method)
    ordinal = 0
    for speaker, participant, start, end, text in utterances:
        text = " ".join(str(text).split())
        if not text:
            continue
        speaker = " ".join(str(speaker or "Unknown speaker").split())[:120]
        start = max(0.0, float(start))
        end = max(start, float(end))
        pieces = _split_long(text)
        total = sum(len(p) for p in pieces) or 1
        cursor = start
        for piece in pieces:
            piece_end = cursor + (end - start) * len(piece) / total
            transcript.segments.append(
                Segment(
                    meeting_id=meeting_id,
                    segment_id=segment_id(meeting_id, method, ordinal, cursor, speaker),
                    speaker_label=speaker,
                    participant_ref=str(participant or "")[:120],
                    start_ts=cursor,
                    end_ts=piece_end,
                    text=piece,
                    source_method=method,
                )
            )
            ordinal += 1
            cursor = piece_end
    return transcript


_VTT_TIME = re.compile(
    r"^(?:(\d+):)?(\d{2}):(\d{2})[.,](\d{3})\s+-->\s+(?:(\d+):)?(\d{2}):(\d{2})[.,](\d{3})"
)
_VTT_VOICE = re.compile(r"^<v(?:\.[^\s>]*)?\s+([^>]+)>(.*?)(?:</v>)?$")


def _vtt_seconds(h: Optional[str], m: str, s: str, ms: str) -> float:
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_webvtt(meeting_id: str, method: str, text: str) -> NormalisedTranscript:
    """WebVTT with `<v Speaker>` voice tags — the format native Teams and Meet
    transcripts export. Here so a native provider only has to fetch the file."""
    utterances: List[Tuple[str, str, float, float, str]] = []
    lines = text.replace("\r\n", "\n").split("\n")
    index = 0
    while index < len(lines):
        match = _VTT_TIME.match(lines[index].strip())
        index += 1
        if not match:
            continue
        g = match.groups()
        start = _vtt_seconds(g[0], g[1], g[2], g[3])
        end = _vtt_seconds(g[4], g[5], g[6], g[7])
        body: List[str] = []
        while index < len(lines) and lines[index].strip():
            body.append(lines[index].strip())
            index += 1
        speaker = "Unknown speaker"
        words: List[str] = []
        for line in body:
            voice = _VTT_VOICE.match(line)
            if voice:
                speaker = voice.group(1).strip()
                line = voice.group(2)
            words.append(re.sub(r"<[^>]+>", "", line))
        utterances.append((speaker, "", start, end, " ".join(words)))
    return build_transcript(meeting_id, method, utterances)


def format_ts(seconds: float) -> str:
    seconds = int(max(0, seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return "{}:{:02d}:{:02d}".format(hours, minutes, secs)
    return "{:02d}:{:02d}".format(minutes, secs)
