#!/usr/bin/env python3
"""NativeTranscriptProvider — fetch the transcript Teams, Meet, or Zoom already made.

No bot joins and nothing is recorded here. The meeting platform transcribes
(participants see its own "transcription started" banner); after the meeting,
this provider downloads that transcript with the signed-in user's delegated
access and hands it to Meeting Intelligence like any other.

    join <url> --via native   → resolve the link with the platform's API,
                                remind the user to switch transcription on
    reconcile (status/list)   → poll, with the reconciler's backoff, until the
                                transcript is listed or the fetch window closes
    fetch_transcript          → download, normalise (WebVTT, or Meet's entries)

One provider, three platform adapters (`meeting_native_teams.py`,
`meeting_native_meet.py`, `meeting_native_zoom.py`). Each platform needs a
one-time app registration by the organisation's admin and a browser sign-in by
each user (`meeting setup native`). What the admin distributes is non-secret:
client id, tenant or domain, redirect URI. A client secret, where a platform
insists on one, goes to the credential store like any other secret.

Every platform limitation is a typed refusal (`MeetingRefusal`), never a
silent switch to another provider: a meeting hosted in another organisation is
`external_tenant`, one the user cannot read is `no_access`, one where nobody
switched transcription on is `not_enabled` once the fetch window closes.

The platform's transcript stays under the organisation's own retention; this
provider deletes nothing there and never downloads recording media.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple
from urllib.parse import urlsplit

import meeting_capture as mc
import meeting_http
import meeting_oauth

PROVIDER_NAME = "native"
SETUP_COMMAND = "agent-skills meeting setup native"
IMPORT_SCHEMA = "agent-skills.meeting-native-config/v1"
DEFAULT_FETCH_WINDOW_HOURS = 24
MAX_WAIT_FOR_MEETING_DAYS = 7

# Non-secret, per-platform configuration an admin may distribute. A key outside
# this list is refused by --import; so is any value that looks like a secret.
PLATFORM_KEYS = {
    "teams": ("client_id", "tenant_id", "redirect_uri"),
    "google_meet": ("client_id", "workspace_domain", "redirect_uri"),
    "zoom": ("client_id", "account_domain", "redirect_uri"),
}
DEFAULT_REDIRECT = {
    "teams": "http://localhost:0/",
    "google_meet": "http://127.0.0.1:0/",
    "zoom": "http://localhost:8765/agent-skills/oauth/callback",
}
# The platform insists on a client secret at its token endpoint (Zoom always;
# a Google "Desktop app" client usually), so it is collected as a secret.
CLIENT_SECRET = {"teams": "never", "google_meet": "optional", "zoom": "required"}
_GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_CLIENT_ID = re.compile(r"^[A-Za-z0-9._-]{6,200}$")
_DOMAIN = re.compile(r"^[a-z0-9]([a-z0-9-]{0,62}\.)+[a-z]{2,24}$")


def profile_name(platform: str) -> str:
    return "meeting-" + platform.replace("_", "-")


def platform_config(config: Dict[str, object], platform: str) -> Dict[str, str]:
    native = config.get("native") if isinstance(config.get("native"), dict) else {}
    section = native.get(platform) if isinstance(native.get(platform), dict) else {}  # type: ignore[union-attr]
    return {k: str(v) for k, v in section.items() if k in PLATFORM_KEYS[platform] and v not in (None, "")}  # type: ignore[union-attr]


def fetch_window_hours(config: Dict[str, object]) -> int:
    native = config.get("native") if isinstance(config.get("native"), dict) else {}
    try:
        hours = int(native.get("fetch_window_hours", DEFAULT_FETCH_WINDOW_HOURS))  # type: ignore[union-attr]
    except (TypeError, ValueError):
        hours = DEFAULT_FETCH_WINDOW_HOURS
    return max(1, min(168, hours))


def validate_platform_config(platform: str, values: Dict[str, object]) -> Dict[str, str]:
    """Closed, non-secret. Raises ValueError naming the first problem (never a value)."""
    from guard_audit import contains_secret_shape
    from access import is_secret_field

    if platform not in PLATFORM_KEYS:
        raise ValueError("unknown platform {!r}; use teams, google_meet, or zoom".format(platform))
    out: Dict[str, str] = {}
    for key, value in values.items():
        if is_secret_field(key, set()) or "secret" in key.lower():
            raise ValueError("the config contains {!r}, which looks like a secret; a shared config must "
                             "never carry one — each user enters it with hidden input".format(key))
        if key not in PLATFORM_KEYS[platform]:
            raise ValueError("unexpected key {!r} for {}".format(key, platform))
        text = str(value or "").strip()
        if contains_secret_shape(text):
            raise ValueError("the value of {!r} looks like a secret; refused".format(key))
        if key == "client_id" and not _CLIENT_ID.match(text):
            raise ValueError("client_id is not a plausible client identifier")
        if key == "tenant_id" and not _GUID.match(text):
            raise ValueError("tenant_id must be the directory (tenant) GUID")
        if key in ("workspace_domain", "account_domain") and text and not _DOMAIN.match(text.lower()):
            raise ValueError("{} must be a domain name".format(key))
        if key == "redirect_uri":
            parts = urlsplit(text)
            if parts.scheme != "http" or parts.hostname not in ("127.0.0.1", "localhost"):
                raise ValueError("redirect_uri must be an http loopback URI")
        if text:
            out[key] = text.lower() if key.endswith("_domain") else text
    if "client_id" not in out:
        raise ValueError("client_id is required")
    if platform == "teams" and "tenant_id" not in out:
        raise ValueError("tenant_id is required for Teams (single-tenant app)")
    return out


def parse_import(text: str) -> Dict[str, Dict[str, str]]:
    """An admin's shareable config file → {platform: settings}. Rejects secrets."""
    try:
        data = json.loads(text)
    except ValueError:
        raise ValueError("the import file is not valid JSON") from None
    if not isinstance(data, dict) or data.get("schema") != IMPORT_SCHEMA:
        raise ValueError("the import file must be a JSON object with schema {!r}".format(IMPORT_SCHEMA))
    out: Dict[str, Dict[str, str]] = {}
    for key, value in data.items():
        if key == "schema":
            continue
        if key == "fetch_window_hours":
            continue
        if not isinstance(value, dict):
            if "secret" in key.lower() or "token" in key.lower() or "password" in key.lower():
                raise ValueError("the config contains {!r}, which looks like a secret; refused".format(key))
            raise ValueError("unexpected top-level key {!r}".format(key))
        out[key] = validate_platform_config(key, value)
    if not out:
        raise ValueError("the import file configures no platform")
    return out


# ---------------------------------------------------------------------------
# Readiness: local only
# ---------------------------------------------------------------------------
def platform_readiness(config: Dict[str, object], platform: str) -> mc.Readiness:
    settings = platform_config(config, platform)
    label = mc.PLATFORM_LABELS[platform]
    fix = "{} --platform {}".format(SETUP_COMMAND, platform)
    if not settings.get("client_id"):
        return mc.Readiness(mc.NOT_CONFIGURED, "{}: no app registration imported".format(label), fix)
    try:
        store = meeting_oauth.TokenStore(profile_name(platform), profile_name(platform))
        meta = store.metadata()
    except Exception:  # noqa: BLE001 - a report, never a crash
        return mc.Readiness(mc.BROKEN, "{}: the credential store could not be read".format(label), fix)
    secrets_present = set(meta.get("secret_fields") or [])
    if CLIENT_SECRET[platform] == "required" and "client_secret" not in secrets_present:
        return mc.Readiness(mc.BROKEN, "{}: the app's client secret is not stored".format(label), fix)
    if "refresh_token" not in secrets_present:
        return mc.Readiness(mc.BROKEN, "{}: not signed in".format(label), fix)
    if (meta.get("fields") or {}).get("auth_state") == "expired":
        return mc.Readiness(mc.BROKEN, "{}: sign-in expired or was revoked".format(label), fix)
    return mc.Readiness(mc.READY, detail="{}: signed in".format(label))


def readiness(config: Dict[str, object]) -> mc.Readiness:
    per = {p: platform_readiness(config, p) for p in mc.PLATFORMS}
    ready = [mc.PLATFORM_LABELS[p] for p, r in per.items() if r.ready]
    configured = {p: r for p, r in per.items() if r.state != mc.NOT_CONFIGURED}
    detail = "; ".join(
        "{}: {}".format(mc.PLATFORM_LABELS[p], "ready" if r.ready else r.state.replace("_", " "))
        for p, r in per.items()
    )
    if ready:
        return mc.Readiness(mc.READY, detail=detail)
    if not configured:
        return mc.Readiness(mc.NOT_CONFIGURED, "no platform app registration is imported", SETUP_COMMAND,
                            detail=detail)
    first = next(iter(configured.values()))
    reason = "; ".join(r.reason for r in configured.values())
    return mc.Readiness(mc.BROKEN, reason, first.fix_command, detail=detail)


# ---------------------------------------------------------------------------
# Adapter plumbing shared by the three platforms
# ---------------------------------------------------------------------------
class PlatformAdapter:
    platform = "abstract"
    label = "abstract"
    api_env = ""
    api_suffixes: Tuple[str, ...] = ()
    default_api = ""

    def __init__(self, settings: Dict[str, str], transport: Optional[meeting_http.Transport] = None,
                 client_secret: str = "") -> None:
        self.settings = settings
        self._transport = transport or meeting_http.make_transport(self.label)
        self._client_secret = client_secret
        self.store = meeting_oauth.TokenStore(profile_name(self.platform), profile_name(self.platform))
        self.base = meeting_http.base_override(self.api_env, self.api_suffixes) or self.default_api
        self._token: Optional[str] = None
        self.now = lambda: datetime.now(timezone.utc)  # the provider shares its clock

    # Each platform supplies its OAuth client.
    def oauth_client(self, transport: Optional[meeting_http.Transport] = None) -> meeting_oauth.OAuthClient:
        raise NotImplementedError

    @property
    def fix_command(self) -> str:
        return "{} --platform {}".format(SETUP_COMMAND, self.platform)

    def token(self, force_refresh: bool = False) -> str:
        if force_refresh:
            self._token = None
            stored = self.store.load()
            if stored.get("refresh_token"):
                try:
                    tokens = self.oauth_client(self._transport).refresh(stored["refresh_token"])
                except meeting_oauth.ExpiredGrant:
                    self.store.mark_expired()
                    raise mc.ProviderAuthError("{} sign-in has expired; run: {}".format(
                        self.label, self.fix_command)) from None
                self.store.save(tokens)
                self._token = str(tokens["access_token"])
        if self._token is None:
            self._token = self.store.access_token(self.oauth_client(self._transport), self.fix_command)
        return self._token

    def request(self, method: str, url: str, accept: str = "application/json",
                hosts: Optional[Tuple[str, ...]] = None) -> Tuple[int, bytes]:
        """One authenticated call. The token goes only to the API host (or loopback in tests)."""
        target = urlsplit(url)
        host = (target.hostname or "").lower()
        suffixes = hosts or self.api_suffixes
        allowed = meeting_http.is_loopback(url) or (
            target.scheme == "https" and any(host == s.lstrip(".") or host.endswith(s) for s in suffixes))
        if not allowed:
            raise mc.ProviderPayloadError("{} pointed at an unexpected host; nothing was sent".format(self.label))
        for attempt in (0, 1):
            headers = {"Authorization": "Bearer " + self.token(force_refresh=attempt == 1),
                       "Accept": accept, "User-Agent": "agent-skills-meeting"}
            status, body = self._transport(method, url, headers, None)
            if status != 401:
                break
        if status == 401:
            raise mc.ProviderAuthError("{} rejected the sign-in; run: {}".format(self.label, self.fix_command))
        if status == 429 or status >= 500:
            raise mc.ProviderNetworkError("{} is unavailable (HTTP {})".format(self.label, status))
        if len(body) > meeting_http.MAX_RESPONSE_BYTES:
            raise mc.ProviderPayloadError("{} response exceeded the size limit".format(self.label))
        return status, body

    def get_json(self, url: str) -> Tuple[int, dict]:
        status, body = self.request("GET", url)
        if not body.strip():
            return status, {}
        try:
            data = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            if status >= 400:
                return status, {}
            raise mc.ProviderPayloadError("{} returned a response that is not JSON".format(self.label)) from None
        return status, data if isinstance(data, dict) else {"value": data}

    # The platform-specific part.
    def resolve(self, meeting_url: str, display_url: str) -> Tuple[dict, Optional[bool], str]:
        """(ref dict, has_ended, note) or MeetingRefusal."""
        raise NotImplementedError

    def status(self, ref: dict) -> Tuple[str, Optional[datetime]]:
        """("waiting" | "ended" | "available", meeting end if known), or MeetingRefusal."""
        raise NotImplementedError

    def fetch(self, ref: dict, meeting_id: str) -> mc.NormalisedTranscript:
        raise NotImplementedError

    def self_test(self) -> str:
        """A harmless authenticated read. Returns a one-line, secret-free result."""
        raise NotImplementedError


def _adapter_class(platform: str):
    if platform == "teams":
        from meeting_native_teams import TeamsAdapter

        return TeamsAdapter
    if platform == "google_meet":
        from meeting_native_meet import MeetAdapter

        return MeetAdapter
    if platform == "zoom":
        from meeting_native_zoom import ZoomAdapter

        return ZoomAdapter
    raise mc.MeetingRefusal("unsupported_platform", "no native adapter for {}".format(platform))


def build_adapter(config: Dict[str, object], platform: str,
                  transport: Optional[meeting_http.Transport] = None) -> PlatformAdapter:
    settings = platform_config(config, platform)
    client_secret = ""
    if CLIENT_SECRET[platform] != "never":
        import access

        try:
            client_secret = access.fetch_identity(profile_name(platform), ["client_secret"]).get("client_secret", "")
        except access.BackendError as exc:
            raise mc.ProviderAuthError(str(exc)) from None
    return _adapter_class(platform)(settings, transport=transport, client_secret=client_secret)


def parse_time(value: object) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    text = re.sub(r"(\.\d{6})\d+", r"\1", text.replace("Z", "+00:00"))
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def _iso(stamp: datetime) -> str:
    return stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# The provider
# ---------------------------------------------------------------------------
EXTERNAL_HINT = ("The transcript belongs to the other organisation. Use --via recall or --via desktop "
                 "for meetings you don't host.")
NOT_ENABLED_HINT = ("No transcript exists for this meeting. Next time switch on transcription, "
                    "or use another provider.")


class NativeTranscriptProvider(mc.MeetingCaptureProvider):
    name = PROVIDER_NAME

    def __init__(self, config: Dict[str, object],
                 transports: Optional[Dict[str, meeting_http.Transport]] = None,
                 now=None) -> None:
        self._config = config
        self._transports = transports or {}
        self._adapters: Dict[str, PlatformAdapter] = {}
        self._now = now or (lambda: datetime.now(timezone.utc))

    def adapter(self, platform: str) -> PlatformAdapter:
        if platform not in self._adapters:
            state = platform_readiness(self._config, platform)
            if not state.ready:
                raise mc.ProviderAuthError("{}; run: {}".format(state.reason, state.fix_command))
            adapter = build_adapter(self._config, platform, self._transports.get(platform))
            adapter.now = self._now
            self._adapters[platform] = adapter
        return self._adapters[platform]

    def capabilities(self) -> mc.Capabilities:
        return mc.Capabilities(
            provider=PROVIDER_NAME,
            join_live=False,
            fetch_existing_transcript=True,
            diarization="platform",
            retention_control=False,
            chat_notice=False,
            webhooks=False,
            transcription_methods=("native",),
            platforms=mc.PLATFORMS,
            live_capture=False,
            post_meeting_fetch=True,
            visible_participant=False,
            speaker_attribution="named",
            third_party_processing=False,
            per_hour_cost=False,
            languages=("auto",),
        )

    def readiness(self) -> mc.Readiness:
        return readiness(self._config)

    def resolve(self, meeting_url: str) -> mc.MeetingRef:
        try:
            platform, display = mc.classify_meeting_url(meeting_url)
        except mc.MeetingUrlError as exc:
            raise mc.MeetingRefusal("unsupported_platform", str(exc)) from None
        state = platform_readiness(self._config, platform)
        if state.state == mc.NOT_CONFIGURED:
            raise mc.MeetingRefusal(
                "unsupported_platform",
                "native capture is not set up for {} on this machine ({}); run: {}".format(
                    mc.PLATFORM_LABELS[platform], state.reason, state.fix_command))
        ref, has_ended, note = self.adapter(platform).resolve(meeting_url.strip(), display)
        ref["p"] = platform
        return mc.MeetingRef(platform=platform, display_url=display, provider_ref=json.dumps(ref, sort_keys=True),
                             has_ended=has_ended, note=note)

    def start(self, meeting_url: str, options: mc.CaptureOptions) -> mc.CaptureHandle:
        ref = options.ref or self.resolve(meeting_url)
        data = json.loads(ref.provider_ref)
        now = self._now()
        data["since"] = _iso(now)
        if options.live_method != "post_meeting":
            # Joined ahead of the meeting: only a conference from now on counts
            # (a recurring link's older conferences are not this meeting).
            data["after"] = data["since"]
        data["window_h"] = fetch_window_hours(self._config)
        return mc.CaptureHandle(PROVIDER_NAME, json.dumps(data, sort_keys=True))

    def _ref(self, handle: mc.CaptureHandle) -> dict:
        if handle.provider != PROVIDER_NAME or not handle.provider_ref:
            raise mc.ProviderRequestError("capture handle does not belong to this provider")
        try:
            data = json.loads(handle.provider_ref)
        except ValueError:
            raise mc.ProviderRequestError("capture handle is unreadable") from None
        if not isinstance(data, dict) or data.get("p") not in mc.PLATFORMS:
            raise mc.ProviderRequestError("capture handle is unreadable")
        return data

    def poll(self, handle: mc.CaptureHandle) -> mc.LifecycleObservation:
        ref = self._ref(handle)
        now = self._now()
        since = parse_time(ref.get("since")) or now
        window = timedelta(hours=int(ref.get("window_h") or DEFAULT_FETCH_WINDOW_HOURS))
        try:
            status, ended_at = self.adapter(ref["p"]).status(ref)
        except mc.MeetingRefusal as refusal:
            return mc.LifecycleObservation(mc.FAILED, reason=refusal.code)
        if status == "available":
            return mc.LifecycleObservation(mc.MEDIA_READY, reason="transcript listed by the platform",
                                           has_media=True)
        if status == "ended":
            deadline = (ended_at or since) + window
            if now > deadline:
                return mc.LifecycleObservation(mc.FAILED, reason="not_enabled")
            return mc.LifecycleObservation(mc.ENDED, reason="not_yet_available")
        if now > since + timedelta(days=MAX_WAIT_FOR_MEETING_DAYS):
            return mc.LifecycleObservation(mc.FAILED, reason="not_found")
        return mc.LifecycleObservation(mc.CREATED)

    def stop(self, handle: mc.CaptureHandle) -> None:
        return None  # nothing joined the meeting

    def fetch_transcript(self, handle: mc.CaptureHandle, meeting_id: str, method: str) -> mc.TranscriptResult:
        ref = self._ref(handle)
        try:
            transcript = self.adapter(ref["p"]).fetch(ref, meeting_id)
        except mc.MeetingRefusal as refusal:
            return mc.TranscriptResult("unavailable", "native", reason=refusal.code)
        transcript.capture_provider = PROVIDER_NAME
        if not transcript.usable:
            return mc.TranscriptResult("unavailable", "native", reason="empty_transcript")
        return mc.TranscriptResult("ready", "native", transcript=transcript)

    def delete_media(self, handle: mc.CaptureHandle) -> None:
        # The platform transcript stays under the organisation's own retention;
        # no recording media was ever downloaded. Nothing to delete here.
        return None

    def self_test(self, platform: str) -> str:
        return self.adapter(platform).self_test()


def from_config(config: Dict[str, object]) -> NativeTranscriptProvider:
    state = readiness(config)
    if state.state == mc.NOT_CONFIGURED:
        raise mc.ProviderRequestError("native capture is not set up; run: " + SETUP_COMMAND)
    return NativeTranscriptProvider(config)


def refusal_for_status(label: str, status: int, body: dict, fix: str) -> Optional[mc.MeetingRefusal]:
    """Common HTTP → typed refusal mapping; None when the status is not a refusal."""
    if status in (403, 404):
        return mc.MeetingRefusal("no_access", "{} did not let you read this meeting (HTTP {}). Only meetings "
                                 "you can open yourself are readable. {}".format(label, status, EXTERNAL_HINT))
    if status == 400:
        return mc.MeetingRefusal("unsupported_meeting", "{} refused the request for this meeting (HTTP 400)."
                                 .format(label))
    return None
