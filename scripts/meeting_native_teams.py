#!/usr/bin/env python3
"""Microsoft Teams adapter for the native transcript provider (Microsoft Graph v1.0).

Verified against Microsoft Learn on 2026-09-23 (see
docs/meeting-intelligence/SETUP-native-teams.md for the admin steps):

  * Lookup: `GET /me/onlineMeetings?$filter=JoinWebUrl eq '<url-encoded join URL>'`,
    or `joinMeetingIdSettings/joinMeetingId eq '<id>'` for `/meet/<id>` links.
    Delegated `OnlineMeetings.Read`.
  * Transcripts: `GET /me/onlineMeetings/{id}/transcripts`, then
    `.../transcripts/{tid}/content` with `Accept: text/vtt` (WebVTT with
    `<v Speaker>` tags). Delegated `OnlineMeetingTranscript.Read.All`.
  * Not supported for meetings created with the create-onlineMeeting API that
    have no calendar event, nor for expired meetings.
  * A tenant can switch off Graph access to transcripts:
    403 `GraphAccessToTranscriptsDisabled` — no request-side workaround.
  * A tenant can switch off speaker attribution: 403 `SpeakerAttributionNotAllowed`
    on `text/vtt`; the unattributed `application/vnd.microsoft.graph.transcript+text`
    format still works, and the transcript is then marked `speaker_attribution: none`.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import List, Optional, Tuple
from urllib.parse import parse_qs, quote, urlsplit

import meeting_capture as mc
import meeting_native as native
import meeting_oauth

SCOPES = "offline_access OnlineMeetings.Read OnlineMeetingTranscript.Read.All"
UNATTRIBUTED = "application/vnd.microsoft.graph.transcript+text"
_MEETING_ID = re.compile(r"^[A-Za-z0-9_=+/-]{8,512}$")


def _inner_code(body: dict) -> str:
    error = body.get("error") if isinstance(body.get("error"), dict) else {}
    inner = error.get("innerError") if isinstance(error.get("innerError"), dict) else {}
    return str(inner.get("code") or error.get("code") or "")[:64]


class TeamsAdapter(native.PlatformAdapter):
    platform = "teams"
    label = "Microsoft Teams"
    api_env = "AGENT_SKILLS_GRAPH_BASE_URL"
    api_suffixes = (".microsoft.com",)
    default_api = "https://graph.microsoft.com/v1.0"

    def oauth_client(self, transport=None) -> meeting_oauth.OAuthClient:
        tenant = self.settings["tenant_id"]
        root = "https://login.microsoftonline.com/{}/oauth2/v2.0".format(tenant)
        return meeting_oauth.OAuthClient(
            "Microsoft Entra", root + "/authorize", root + "/token", self.settings["client_id"], SCOPES,
            self.settings.get("redirect_uri") or native.DEFAULT_REDIRECT["teams"],
            extra_authorize={"prompt": "select_account"}, transport=transport,
        )

    def _refusal(self, status: int, body: dict) -> mc.MeetingRefusal:
        code = _inner_code(body)
        if code == "GraphAccessToTranscriptsDisabled":
            return mc.MeetingRefusal("no_access", "Your Microsoft 365 administrator has switched off Graph API "
                                     "access to Teams transcripts for this tenant. Ask them to enable it, or use "
                                     "--via recall or --via desktop.")
        if status == 403:
            return mc.MeetingRefusal("no_access", "Teams did not let you read this meeting (HTTP 403). This happens "
                                     "when you received a single forwarded occurrence of a recurring meeting, or "
                                     "were not invited. Ask the organiser to invite you directly, or use --via "
                                     "recall or --via desktop.")
        return native.refusal_for_status(self.label, status, body, self.fix_command) or mc.MeetingRefusal(
            "no_access", "Teams refused the request (HTTP {}).".format(status))

    def resolve(self, meeting_url: str, display_url: str) -> Tuple[dict, Optional[bool], str]:
        parts = urlsplit(meeting_url)
        host = (parts.hostname or "").lower()
        if host == "teams.live.com":
            raise mc.MeetingRefusal("unsupported_platform", "This is a Teams (free) meeting for personal accounts; "
                                    "Graph transcripts need a work or school account. Use --via recall or "
                                    "--via desktop.")
        context = (parse_qs(parts.query).get("context") or [""])[0]
        tenant = ""
        if context:
            try:
                tenant = str((json.loads(context) or {}).get("Tid", ""))
            except (ValueError, AttributeError):
                tenant = ""
        ours = self.settings.get("tenant_id", "").lower()
        if tenant and ours and tenant.lower() != ours:
            raise mc.MeetingRefusal("external_tenant", "This Teams meeting is hosted by another organisation. "
                                    + native.EXTERNAL_HINT)
        match = re.match(r"^/meet/(\d{6,20})/?$", parts.path)
        if match:
            query = "joinMeetingIdSettings/joinMeetingId eq '{}'".format(match.group(1))
        else:
            query = "JoinWebUrl eq '{}'".format(meeting_url.replace("'", "''"))
        status, body = self.get_json("{}/me/onlineMeetings?$filter={}".format(self.base, quote(query, safe="")))
        if status >= 400:
            raise self._refusal(status, body)
        values = body.get("value") if isinstance(body.get("value"), list) else []
        if not values or not isinstance(values[0], dict):
            raise mc.MeetingRefusal("no_access", "Teams found no meeting for this link that you can read. Only "
                                    "calendar-backed meetings you organise or were invited to are visible. "
                                    + native.EXTERNAL_HINT)
        meeting = values[0]
        meeting_id = str(meeting.get("id", ""))
        if not _MEETING_ID.match(meeting_id):
            raise mc.ProviderPayloadError("Teams returned a meeting without a usable id")
        end = native.parse_time(meeting.get("endDateTime"))
        has_ended = bool(end and end < self.now()) if end else None
        return {"id": meeting_id, "end": native._iso(end) if end else ""}, has_ended, ""

    def _transcripts(self, ref: dict) -> List[dict]:
        status, body = self.get_json("{}/me/onlineMeetings/{}/transcripts".format(self.base, quote(ref["id"], safe="")))
        if status == 404:
            raise mc.MeetingRefusal("unsupported_meeting", "Teams has no transcript list for this meeting. Graph "
                                    "supports only calendar-backed meetings that have not expired; meetings "
                                    "created without a calendar event are not supported.")
        if status >= 400:
            raise self._refusal(status, body)
        items = [t for t in (body.get("value") or []) if isinstance(t, dict) and t.get("id")]
        return sorted(items, key=lambda t: str(t.get("createdDateTime", "")))

    def status(self, ref: dict) -> Tuple[str, Optional[datetime]]:
        if self._transcripts(ref):
            return "available", None
        end = native.parse_time(ref.get("end"))
        if end and end < self.now():
            return "ended", end
        return "waiting", end

    def fetch(self, ref: dict, meeting_id: str) -> mc.NormalisedTranscript:
        items = self._transcripts(ref)
        if not items:
            raise mc.MeetingRefusal("not_yet_available", "Teams has not published the transcript yet.")
        first = native.parse_time(items[0].get("createdDateTime")) or self.now()
        utterances: List[Tuple[str, str, float, float, str]] = []
        attribution = "named"
        for item in items:
            url = "{}/me/onlineMeetings/{}/transcripts/{}/content".format(
                self.base, quote(ref["id"], safe=""), quote(str(item["id"]), safe=""))
            status, body = self.request("GET", url, accept="text/vtt")
            if status == 403 and _inner_code(_json(body)) == "SpeakerAttributionNotAllowed":
                status, body = self.request("GET", url, accept=UNATTRIBUTED)
                attribution = "none"
            if status >= 400:
                raise self._refusal(status, _json(body))
            offset = ((native.parse_time(item.get("createdDateTime")) or first) - first).total_seconds()
            part = mc.parse_webvtt(meeting_id, "native", body.decode("utf-8", errors="replace"))
            for segment in part.segments:
                speaker = segment.speaker_label if attribution == "named" else "Unattributed"
                utterances.append((speaker, "", segment.start_ts + offset, segment.end_ts + offset, segment.text))
        transcript = mc.build_transcript(meeting_id, "native", utterances)
        transcript.speaker_attribution = attribution
        return transcript

    def self_test(self) -> str:
        # A lookup for a join URL that cannot exist: proves the token and consent
        # work without reading any meeting.
        probe = "JoinWebUrl eq 'https://teams.microsoft.com/l/meetup-join/agent-skills-self-test'"
        status, body = self.get_json("{}/me/onlineMeetings?$filter={}".format(self.base, quote(probe, safe="")))
        if status in (200, 404):
            return "signed in; Graph accepted the delegated token (no meeting was read)"
        raise mc.ProviderAuthError("Graph refused the self-test (HTTP {}{}); check admin consent for {}".format(
            status, ", " + _inner_code(body) if _inner_code(body) else "", SCOPES))


def _json(body: bytes) -> dict:
    try:
        data = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}
