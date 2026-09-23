#!/usr/bin/env python3
"""Zoom adapter for the native transcript provider (Zoom REST API v2, cloud recordings).

Verified against developers.zoom.us on 2026-09-23 (admin steps:
docs/meeting-intelligence/SETUP-native-zoom.md):

  * `GET /v2/users/me` identifies the signed-in user; `GET /v2/meetings/{id}`
    returns the meeting's `host_id`.
  * `GET /v2/meetings/{meetingId}/recordings` lists `recording_files[]`; the
    audio transcript is the file with `file_type: TRANSCRIPT` (WebVTT) and a
    `download_url` that needs the OAuth access token as a Bearer header.
    Zoom answers code `3301` ("There is no recording for this meeting") until
    a recording exists. Granular user-level scopes:
    `cloud_recording:read:list_recording_files`, `meeting:read:meeting`,
    `user:read:user`.
  * Transcripts exist only for cloud recordings with "Create audio transcript"
    switched on, on a paid plan. Non-host API access to a meeting's recordings
    is not reliably available, so v1 serves the host's own meetings only.
  * The token endpoint requires the app's client secret (HTTP Basic), so each
    user stores it once with hidden input; it is never in the shared config.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional, Tuple
from urllib.parse import quote, urlsplit

import meeting_capture as mc
import meeting_http
import meeting_native as native
import meeting_oauth

_MEETING_NUMBER = re.compile(r"^/(?:j|w|s|wc/join)/(\d{9,12})/?$")
_SPEAKER_PREFIX = re.compile(r"^([^:]{1,80}):\s+(.*)$")
_DOWNLOAD_SUFFIXES = (".zoom.us",)


def parse_zoom_vtt(meeting_id: str, text: str) -> mc.NormalisedTranscript:
    """Zoom's transcript VTT carries the speaker as a "Name: text" prefix, not a <v> tag."""
    parsed = mc.parse_webvtt(meeting_id, "native", text)
    utterances = []
    for segment in parsed.segments:
        speaker, body = segment.speaker_label, segment.text
        if speaker == "Unknown speaker":
            match = _SPEAKER_PREFIX.match(body)
            if match:
                speaker, body = match.group(1).strip(), match.group(2)
        utterances.append((speaker, "", segment.start_ts, segment.end_ts, body))
    return mc.build_transcript(meeting_id, "native", utterances)


class ZoomAdapter(native.PlatformAdapter):
    platform = "zoom"
    label = "Zoom"
    api_env = "AGENT_SKILLS_ZOOM_BASE_URL"
    api_suffixes = (".zoom.us",)
    default_api = "https://api.zoom.us/v2"

    def oauth_client(self, transport=None) -> meeting_oauth.OAuthClient:
        if not self._client_secret:
            raise mc.ProviderAuthError("the Zoom app's client secret is not stored; run: " + self.fix_command)
        return meeting_oauth.OAuthClient(
            "Zoom", "https://zoom.us/oauth/authorize", "https://zoom.us/oauth/token", self.settings["client_id"],
            "", self.settings.get("redirect_uri") or native.DEFAULT_REDIRECT["zoom"],
            client_secret=self._client_secret, secret_in_basic_auth=True, transport=transport,
        )

    def resolve(self, meeting_url: str, display_url: str) -> Tuple[dict, Optional[bool], str]:
        parts = urlsplit(meeting_url)
        match = _MEETING_NUMBER.match(parts.path)
        if not match:
            raise mc.MeetingRefusal("unsupported_meeting", "Use the numeric Zoom meeting link "
                                    "(zoom.us/j/<meeting id>); personal link names cannot be looked up.")
        number = match.group(1)
        host = (parts.hostname or "").lower()
        ours = self.settings.get("account_domain", "")
        vanity = host[: -len(".zoom.us")] if host.endswith(".zoom.us") else ""
        if ours and vanity and not re.match(r"^us\d{2}web$|^www$", vanity) and not ours.startswith(vanity + "."):
            raise mc.MeetingRefusal("external_tenant", "This Zoom meeting is hosted on another organisation's "
                                    "account ({}). {}".format(host, native.EXTERNAL_HINT))
        status, me = self.get_json("{}/users/me".format(self.base))
        if status >= 400:
            raise mc.ProviderAuthError("Zoom did not accept the sign-in (HTTP {}); run: {}".format(
                status, self.fix_command))
        status, meeting = self.get_json("{}/meetings/{}".format(self.base, number))
        if status in (400, 404) or (status >= 400 and meeting.get("code") in (3001, 300)):
            raise mc.MeetingRefusal("no_access", "Zoom does not show this meeting to your account; it is "
                                    "probably hosted by someone else. " + native.EXTERNAL_HINT)
        if status >= 400:
            raise native.refusal_for_status(self.label, status, meeting, self.fix_command) or mc.MeetingRefusal(
                "no_access", "Zoom refused the request (HTTP {}).".format(status))
        if str(meeting.get("host_id", "")) != str(me.get("id", "")):
            raise mc.MeetingRefusal("no_access", "You are not the host of this Zoom meeting. Zoom does not "
                                    "reliably give attendees API access to transcripts, so v1 fetches only the "
                                    "host's own meetings. Use --via recall or --via desktop, or ask the host.")
        start = native.parse_time(meeting.get("start_time"))
        end = None
        if start and meeting.get("duration"):
            try:
                end = start + timedelta(minutes=int(meeting["duration"]))
            except (TypeError, ValueError):
                end = None
        has_ended = bool(end and end < self.now()) if end else None
        return {"id": number, "end": native._iso(end) if end else ""}, has_ended, ""

    def _recordings(self, ref: dict) -> Tuple[int, dict]:
        return self.get_json("{}/meetings/{}/recordings".format(self.base, quote(ref["id"], safe="")))

    def _transcript_file(self, body: dict) -> Optional[dict]:
        for item in body.get("recording_files") or []:
            if isinstance(item, dict) and str(item.get("file_type", "")).upper() == "TRANSCRIPT":
                return item
        return None

    def status(self, ref: dict) -> Tuple[str, Optional[datetime]]:
        status, body = self._recordings(ref)
        end = native.parse_time(ref.get("end"))
        now = self.now()
        if status == 404 or body.get("code") == 3301:
            return ("ended", end) if end and end < now else ("waiting", end)
        if status >= 400:
            raise native.refusal_for_status(self.label, status, body, self.fix_command) or mc.MeetingRefusal(
                "no_access", "Zoom refused the request (HTTP {}).".format(status))
        found = self._transcript_file(body)
        if found and str(found.get("status", "completed")).lower() == "completed":
            return "available", None
        # A recording exists, so the meeting ended; the transcript may still be
        # processing, or audio transcription was never switched on.
        return "ended", native.parse_time(body.get("start_time")) or end or now

    def fetch(self, ref: dict, meeting_id: str) -> mc.NormalisedTranscript:
        status, body = self._recordings(ref)
        found = self._transcript_file(body) if status < 400 else None
        if not found:
            raise mc.MeetingRefusal("not_enabled", native.NOT_ENABLED_HINT)
        url = str(found.get("download_url", ""))
        target = urlsplit(url)
        host = (target.hostname or "").lower()
        # The access token goes only to Zoom's own download host.
        if not (target.scheme == "https" and any(host == s.lstrip(".") or host.endswith(s)
                                                  for s in _DOWNLOAD_SUFFIXES)) and \
                not meeting_http.is_loopback(url):
            raise mc.ProviderPayloadError("Zoom returned a transcript download on an unexpected host")
        status, data = self.request("GET", url, accept="text/vtt", hosts=_DOWNLOAD_SUFFIXES)
        if status >= 400:
            raise mc.ProviderNetworkError("Zoom transcript download failed (HTTP {})".format(status))
        return parse_zoom_vtt(meeting_id, data.decode("utf-8", errors="replace"))

    def self_test(self) -> str:
        status, _ = self.get_json("{}/users/me".format(self.base))
        if status == 200:
            return "signed in; Zoom accepted the token (no recording was read)"
        raise mc.ProviderAuthError("Zoom refused the self-test (HTTP {}); check the app's scopes".format(status))
