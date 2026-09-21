#!/usr/bin/env python3
"""RecallMeetingBotProvider — the Recall.ai Meeting Bot API behind the capture boundary.

This is the only module that knows Recall exists. Every Recall field name,
status code, sub-code, and identifier is mapped here into the provider-neutral
types in `meeting_capture.py`; `test-meeting.py` fails if any other meeting
module imports this one or names a Recall concept.

Contract verified against Recall's published reference (docs.recall.ai, read
for this release, not recalled from memory):

  * Region is a separate deployment (one host per region), with its own
    keys and its own resources. The API key, the bot, and its media must all be
    in one region. Region is therefore required configuration.
  * `Authorization: <key>` authenticates. The key is sent only to the region
    host, only as a header, and never to a download host.
  * Create bot: `POST /api/v1/bot/` with `meeting_url`, `bot_name`,
    `recording_config.transcript.provider`, `recording_config.retention`
    (`{"type": "timed", "hours": N}` — the provider's default keeps media
    indefinitely, so it is always sent), `automatic_leave`, `metadata`, and
    `chat.on_bot_join`.
  * Status: `GET /api/v1/bot/<id>/` → `status_changes[]` (`code`, `sub_code`,
    `created_at`) and `recordings[].media_shortcuts.transcript`.
  * Leave: `POST /api/v1/bot/<id>/leave_call/`. Delete media:
    `POST /api/v1/bot/<id>/delete_media/`.
  * Async transcription: `POST /api/v1/recording/<id>/create_transcript/` with
    `{"provider": {"recallai_async": {...}}}`.
  * Webhooks are Svix-signed: `HMAC-SHA256(base64decode(secret minus "whsec_"),
    "<id>.<timestamp>.<body>")`, header `v1,<base64> …`.

Only the standard library is used, as for the rest of the runtime.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import ssl
import urllib.error
import urllib.request
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

import meeting_capture as mc

PROVIDER_NAME = "recall"
REGIONS = ("us-west-2", "us-east-1", "eu-central-1", "ap-northeast-1")
MAX_RESPONSE_BYTES = 50 * 1024 * 1024
TIMEOUT_SECONDS = 20
WEBHOOK_TOLERANCE_SECONDS = 300
_ID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")
_CODE_RE = re.compile(r"^[a-z0-9_]{1,64}$")

# (method, url, headers, body) -> (status, body). Injectable so tests replay
# recorded fixtures and never touch the network.
Transport = Callable[[str, str, Dict[str, str], Optional[bytes]], Tuple[int, bytes]]

_REJECTED_SUBCODES = ("bot_kicked_from_waiting_room", "bot_kicked_from_call", "zoom_account_blocked")
_TIMEOUT_SUBCODES = ("timeout_exceeded_waiting_room", "timeout_exceeded_noone_joined")


def base_url_for(region: str) -> str:
    if region not in REGIONS:
        raise mc.ProviderRequestError(
            "unknown Recall region {!r}; choose one of {}".format(region, ", ".join(REGIONS))
        )
    override = os.environ.get("AGENT_SKILLS_RECALL_BASE_URL", "").strip().rstrip("/")
    if override:
        parts = urlsplit(override)
        loopback = parts.scheme == "http" and parts.hostname in ("127.0.0.1", "localhost")
        recall = parts.scheme == "https" and (parts.hostname or "").endswith(".recall.ai")
        # A base-URL override decides where the API key is sent, so it may only
        # point at Recall itself or at this machine (the offline test harness).
        if not (loopback or recall) or parts.username or parts.password:
            raise mc.ProviderRequestError(
                "AGENT_SKILLS_RECALL_BASE_URL must be an https *.recall.ai URL or loopback"
            )
        return override
    return "https://" + region + ".recall.ai"


class _CredentialSafeRedirect(urllib.request.HTTPRedirectHandler):
    """Follow redirects without carrying the API key anywhere it was not sent.

    urllib's default handler copies every non-content header onto the
    redirected request, `Authorization` included, whatever host the redirect
    points at. A redirect from the region API to any other host would hand it
    the key. So a cross-host hop drops the header, and a downgrade from https
    to http is refused outright.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401 - urllib API
        old, new = urlsplit(req.full_url), urlsplit(newurl)
        if old.scheme == "https" and new.scheme != "https":
            return None
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None and (new.hostname or "").lower() != (old.hostname or "").lower():
            for name in list(redirected.headers):
                if name.lower() == "authorization":
                    del redirected.headers[name]
            redirected.unredirected_hdrs.pop("Authorization", None)
        return redirected


def _default_transport(method: str, url: str, headers: Dict[str, str], body: Optional[bytes]) -> Tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    context = ssl.create_default_context()  # certificate verification stays on
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=context), _CredentialSafeRedirect()
    )
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            data = response.read(MAX_RESPONSE_BYTES + 1)
            return response.status, data
    except urllib.error.HTTPError as exc:
        try:
            data = exc.read(64 * 1024)
        except OSError:
            data = b""
        return exc.code, data
    except (urllib.error.URLError, OSError, ValueError):
        # The exception text can carry the URL; it is deliberately not kept.
        raise mc.ProviderNetworkError("Recall could not be reached") from None


def _clean_code(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if _CODE_RE.match(text) else ("unrecognised" if text else "")


def _parse_time(value: object) -> Optional[datetime]:
    text = str(value or "")
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


class RecallMeetingBotProvider(mc.MeetingCaptureProvider):
    name = PROVIDER_NAME

    def __init__(
        self,
        api_key: str,
        region: str,
        verification_secret: str = "",
        transport: Optional[Transport] = None,
    ) -> None:
        self._api_key = api_key or ""
        self._region = region
        self._secret = verification_secret or ""
        self._transport = transport or _default_transport
        self._base = base_url_for(region)

    # ---- plumbing -------------------------------------------------------------
    def _call(self, method: str, path: str, payload: Optional[dict] = None) -> dict:
        if not self._api_key:
            raise mc.ProviderAuthError("no Recall API key is configured")
        headers = {
            "Authorization": self._api_key,
            "Accept": "application/json",
            "User-Agent": "agent-skills-meeting",
        }
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        status, data = self._transport(method, self._base + path, headers, body)
        if status in (401, 403):
            raise mc.ProviderAuthError(
                "Recall rejected the API key for region {} (invalid, disabled, or from a "
                "different region)".format(self._region)
            )
        if status == 429 or status >= 500:
            raise mc.ProviderNetworkError("Recall is unavailable (HTTP {})".format(status))
        if status >= 400:
            # The body can echo the meeting URL; only the field names are kept.
            fields = ""
            try:
                parsed = json.loads(data.decode("utf-8"))
                if isinstance(parsed, dict):
                    fields = ", ".join(sorted(str(k) for k in parsed)[:6])
            except (ValueError, UnicodeDecodeError):
                pass
            raise mc.ProviderRequestError(
                "Recall refused the request (HTTP {}{})".format(
                    status, "; fields: " + fields if fields else ""
                )
            )
        if len(data) > MAX_RESPONSE_BYTES:
            raise mc.ProviderPayloadError("Recall response exceeded the size limit")
        if not data.strip():
            return {}
        try:
            parsed = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise mc.ProviderPayloadError("Recall returned a response that is not JSON") from None
        if not isinstance(parsed, (dict, list)):
            raise mc.ProviderPayloadError("Recall returned an unexpected response shape")
        return parsed if isinstance(parsed, dict) else {"results": parsed}

    def _bot_id(self, handle: mc.CaptureHandle) -> str:
        if handle.provider != PROVIDER_NAME or not _ID_RE.match(handle.provider_ref):
            raise mc.ProviderRequestError("capture handle does not belong to this provider")
        return handle.provider_ref

    # ---- interface --------------------------------------------------------------
    def capabilities(self) -> mc.Capabilities:
        return mc.Capabilities(
            provider=PROVIDER_NAME,
            join_live=True,
            fetch_existing_transcript=False,
            diarization="platform",
            retention_control=True,
            chat_notice=True,
            webhooks=True,
            transcription_methods=("captions", "provider_transcription", "async"),
            platforms=("zoom", "google_meet", "teams"),
        )

    def probe(self) -> None:
        """Cheap authenticated read: proves reachability and that key and region match."""
        self._call("GET", "/api/v1/bot/?page_size=1")

    def start(self, meeting_url: str, options: mc.CaptureOptions) -> mc.CaptureHandle:
        provider = (
            {"meeting_captions": {}}
            if options.live_method == "captions"
            else {"recallai_streaming": {}}
        )
        payload = {
            "meeting_url": meeting_url,
            "bot_name": options.bot_name,
            "metadata": {"agent_skills_meeting_id": options.correlation_id},
            "recording_config": {
                "transcript": {"provider": provider},
                "retention": {"type": "timed", "hours": int(options.retention_hours)},
            },
            "automatic_leave": {
                "waiting_room_timeout": int(options.waiting_room_timeout),
                "noone_joined_timeout": int(options.noone_joined_timeout),
                "everyone_left_timeout": {"timeout": int(options.everyone_left_timeout)},
            },
            "chat": {"on_bot_join": {"send_to": "everyone", "message": options.chat_notice}},
        }
        data = self._call("POST", "/api/v1/bot/", payload)
        bot_id = str(data.get("id", ""))
        if not _ID_RE.match(bot_id):
            raise mc.ProviderPayloadError("Recall did not return a bot identifier")
        return mc.CaptureHandle(PROVIDER_NAME, bot_id)

    def _bot(self, handle: mc.CaptureHandle) -> dict:
        return self._call("GET", "/api/v1/bot/{}/".format(self._bot_id(handle)))

    def poll(self, handle: mc.CaptureHandle) -> mc.LifecycleObservation:
        return observation_from_bot(self._bot(handle))

    def stop(self, handle: mc.CaptureHandle) -> None:
        try:
            self._call("POST", "/api/v1/bot/{}/leave_call/".format(self._bot_id(handle)))
        except mc.ProviderRequestError:
            # Already out of the call. Leaving is idempotent from our side.
            pass

    def _recording(self, bot: dict) -> dict:
        recordings = bot.get("recordings") or []
        return recordings[0] if recordings and isinstance(recordings[0], dict) else {}

    def fetch_transcript(self, handle: mc.CaptureHandle, meeting_id: str, method: str) -> mc.TranscriptResult:
        bot = self._bot(handle)
        recording = self._recording(bot)
        if not recording:
            return mc.TranscriptResult("unavailable", method, reason="no_recording")
        if method == "async":
            artifact = self._async_artifact(str(recording.get("id", "")))
        else:
            artifact = ((recording.get("media_shortcuts") or {}).get("transcript")) or {}
        if not artifact:
            return mc.TranscriptResult("unavailable", method, reason="no_transcript")
        code = _clean_code((artifact.get("status") or {}).get("code"))
        if code == "processing":
            return mc.TranscriptResult("pending", method)
        if code != "done":
            return mc.TranscriptResult("unavailable", method, reason=code or "unknown")
        url = str(((artifact.get("data") or {}).get("download_url")) or "")
        if not url:
            return mc.TranscriptResult("unavailable", method, reason="no_download")
        raw = self._download(url)
        return mc.TranscriptResult("ready", method, transcript=normalise_recall_transcript(meeting_id, method, raw))

    def _async_artifact(self, recording_id: str) -> dict:
        if not _ID_RE.match(recording_id):
            return {}
        data = self._call("GET", "/api/v1/transcript/?recording_id={}".format(recording_id))
        for item in data.get("results") or []:
            if isinstance(item, dict) and "recallai_async" in (item.get("provider") or {}):
                return item
        return {}

    def _download(self, url: str) -> object:
        parts = urlsplit(url)
        loopback_base = urlsplit(self._base).hostname in ("127.0.0.1", "localhost")
        if parts.scheme != "https" and not loopback_base:
            raise mc.ProviderPayloadError("transcript download is not https")
        headers = {"Accept": "application/json", "User-Agent": "agent-skills-meeting"}
        # A pre-signed download URL is usually a storage host. The API key goes
        # only to the region host it belongs to.
        if urlsplit(self._base).hostname == parts.hostname:
            headers["Authorization"] = self._api_key
        status, data = self._transport("GET", url, headers, None)
        if status >= 400:
            raise mc.ProviderNetworkError("transcript download failed (HTTP {})".format(status))
        if len(data) > MAX_RESPONSE_BYTES:
            raise mc.ProviderPayloadError("transcript exceeded the size limit")
        try:
            return json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise mc.ProviderPayloadError("transcript download is not JSON") from None

    def request_async_transcript(self, handle: mc.CaptureHandle) -> bool:
        recording = self._recording(self._bot(handle))
        recording_id = str(recording.get("id", ""))
        if not _ID_RE.match(recording_id):
            return False
        self._call(
            "POST",
            "/api/v1/recording/{}/create_transcript/".format(recording_id),
            {"provider": {"recallai_async": {"language_code": "auto"}}},
        )
        return True

    def delete_media(self, handle: mc.CaptureHandle) -> None:
        try:
            self._call("POST", "/api/v1/bot/{}/delete_media/".format(self._bot_id(handle)))
        except mc.ProviderRequestError as exc:
            if "HTTP 409" in exc.message:  # a deletion is already in progress
                return
            raise

    def verify_event(self, headers: Dict[str, str], body: bytes, now: float) -> Optional[mc.ProviderEvent]:
        return verify_webhook(self._secret, headers, body, now)


# ---------------------------------------------------------------------------
# Mapping, kept as pure functions so recorded fixtures exercise them directly.
# ---------------------------------------------------------------------------
_LIVE_STATES = {
    "joining_call": mc.JOINING,
    "in_waiting_room": mc.WAITING_ROOM,
    "in_call_not_recording": mc.IN_CALL_NOT_RECORDING,
    "recording_permission_allowed": mc.IN_CALL_NOT_RECORDING,
    "in_call_recording": mc.RECORDING,
    "call_ended": mc.ENDED,
}


def observation_from_bot(bot: dict) -> mc.LifecycleObservation:
    """Fold the whole status history into one internal observation.

    The history, not just its last entry, decides: "kicked from the waiting
    room" is a rejection only if the bot never recorded; after a recording it
    is simply the end of a meeting that has media to process.
    """
    changes = [c for c in (bot.get("status_changes") or []) if isinstance(c, dict)]
    state = mc.CREATED
    reason = ""
    recorded = False
    record_start: Optional[datetime] = None
    record_end: Optional[datetime] = None
    denied = False
    media_expired = False
    for change in changes:
        code = _clean_code(change.get("code"))
        sub = _clean_code(change.get("sub_code"))
        when = _parse_time(change.get("created_at"))
        if sub:
            reason = sub
        if code == "in_call_recording":
            recorded = True
            record_start = record_start or when
        if code in ("call_ended", "done", "fatal") and recorded and record_end is None:
            record_end = when
        if code == "recording_permission_denied":
            denied = True
            reason = sub or "recording_permission_denied"
        if code == "media_expired":
            media_expired = True
        if code in _LIVE_STATES and mc.RANK[_LIVE_STATES[code]] > mc.RANK.get(state, 0):
            state = _LIVE_STATES[code]
        if code == "call_ended" and not recorded:
            if sub in _REJECTED_SUBCODES:
                state = mc.REJECTED
            elif sub in _TIMEOUT_SUBCODES:
                state = mc.TIMED_OUT
        if code == "fatal" and not recorded:
            state = mc.FAILED
            reason = sub or "fatal"
    last = _clean_code(changes[-1].get("code")) if changes else ""
    has_recording = bool((bot.get("recordings") or [])) and recorded and not media_expired
    if denied and not recorded:
        state = mc.PERMISSION_DENIED
    elif last in ("done", "fatal", "call_ended", "media_expired") and state not in mc.FAILURE_STATES:
        if has_recording and last in ("done", "fatal", "media_expired"):
            state = mc.MEDIA_READY
        elif last == "call_ended":
            state = mc.ENDED
        elif not recorded:
            state = mc.FAILED
            reason = reason or "ended_without_media"
            if last == "done":
                reason = "ended_without_media"
        else:
            state = mc.FAILED
            reason = "media_unavailable"
    seconds = None
    if record_start and record_end:
        seconds = max(0.0, (record_end - record_start).total_seconds())
    return mc.LifecycleObservation(state=state, reason=reason, recording_seconds=seconds, has_media=has_recording)


def _relative(stamp: object) -> Optional[float]:
    if isinstance(stamp, dict):
        stamp = stamp.get("relative")
    try:
        return float(stamp) if stamp is not None else None
    except (TypeError, ValueError):
        return None


def normalise_recall_transcript(meeting_id: str, method: str, raw: object) -> mc.NormalisedTranscript:
    """Recall's transcript download: `[{participant: {id, name}, words: [...]}, …]`.

    Caption transcripts use the same envelope with one entry per caption line
    and may lack per-word timestamps; the entry's first and last timestamps are
    used, falling back to the previous segment's end.
    """
    if not isinstance(raw, list):
        raise mc.ProviderPayloadError("transcript is not a list of utterances")
    utterances: List[Tuple[str, str, float, float, str]] = []
    cursor = 0.0
    for entry in raw:
        if not isinstance(entry, dict):
            raise mc.ProviderPayloadError("transcript entry is not an object")
        participant = entry.get("participant") or {}
        if not isinstance(participant, dict):
            participant = {}
        words = entry.get("words") or []
        if not isinstance(words, list):
            raise mc.ProviderPayloadError("transcript words are not a list")
        texts = [str(w.get("text", "")) for w in words if isinstance(w, dict)]
        starts = [_relative(w.get("start_timestamp")) for w in words if isinstance(w, dict)]
        ends = [_relative(w.get("end_timestamp")) for w in words if isinstance(w, dict)]
        starts = [s for s in starts if s is not None]
        ends = [e for e in ends if e is not None]
        start = starts[0] if starts else cursor
        end = ends[-1] if ends else (starts[-1] if starts else start)
        cursor = max(cursor, end)
        name = str(participant.get("name") or "Unknown speaker")
        ref = str(participant.get("id") or "")
        utterances.append((name, ref, start, end, " ".join(t for t in texts if t)))
    return mc.build_transcript(meeting_id, method, utterances)


def verify_webhook(secret: str, headers: Dict[str, str], body: bytes, now: float) -> Optional[mc.ProviderEvent]:
    """Svix-style verification, before the body is parsed. None on any failure.

    The caller learns only "verified or not": which check failed is not
    returned, so a probe cannot use the listener as a signature oracle.
    """
    lowered = {str(k).lower(): str(v) for k, v in headers.items()}
    msg_id = lowered.get("webhook-id") or lowered.get("svix-id") or ""
    stamp = lowered.get("webhook-timestamp") or lowered.get("svix-timestamp") or ""
    signatures = lowered.get("webhook-signature") or lowered.get("svix-signature") or ""
    if not secret.startswith("whsec_") or not msg_id or not stamp or not signatures:
        return None
    if len(msg_id) > 128 or not re.match(r"^[A-Za-z0-9_.:-]+$", msg_id):
        return None
    try:
        sent = int(stamp)
        key = base64.b64decode(secret[len("whsec_"):], validate=True)
    except (ValueError, binascii.Error):
        return None
    if abs(now - sent) > WEBHOOK_TOLERANCE_SECONDS:
        return None
    signed = msg_id.encode("utf-8") + b"." + stamp.encode("utf-8") + b"." + body
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest())
    matched = False
    for entry in signatures.split():
        version, _, value = entry.partition(",")
        if version == "v1" and hmac.compare_digest(value.encode("utf-8"), expected):
            matched = True
    if not matched:
        return None
    try:
        payload = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    data = payload.get("data") if isinstance(payload, dict) else None
    bot = data.get("bot") if isinstance(data, dict) else None
    if not isinstance(bot, dict):
        return None
    bot_id = str(bot.get("id", ""))
    metadata = bot.get("metadata") if isinstance(bot.get("metadata"), dict) else {}
    correlation = str(metadata.get("agent_skills_meeting_id", ""))
    if not _ID_RE.match(bot_id):
        return None
    return mc.ProviderEvent(event_id=msg_id, provider_ref=bot_id, correlation_id=correlation)
