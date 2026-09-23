#!/usr/bin/env python3
"""Google Meet adapter for the native transcript provider (Meet REST API v2).

Verified against developers.google.com on 2026-09-23 (admin steps:
docs/meeting-intelligence/SETUP-native-google-meet.md):

  * Space: `GET /v2/spaces/{meetingCode}` — the meeting code is accepted as an
    alias of the space name; 403/404 when the user cannot access the space.
  * Conferences: `GET /v2/conferenceRecords?filter=space.meeting_code="abc-mnop-xyz"`
    (fields `space.meeting_code`, `space.name`, `start_time`, `end_time`).
  * Transcripts: `GET /v2/{conferenceRecord}/transcripts`, state `STARTED` |
    `ENDED` | `FILE_GENERATED`; entries: `GET /v2/{transcript}/entries`,
    `pageSize` ≤ 100, `pageToken`; each entry has `participant`, `text`,
    `languageCode`, `startTime`, `endTime`.
  * Names: `GET /v2/{participant}` → `signedinUser.displayName`,
    `anonymousUser.displayName`, or `phoneUser.displayName`.
  * Scope: `https://www.googleapis.com/auth/meetings.space.readonly`. Only an
    owner or participant of the space can read its artifacts; transcripts exist
    only on Workspace editions that include transcription.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote, urlsplit

import meeting_capture as mc
import meeting_native as native
import meeting_oauth

SCOPES = "https://www.googleapis.com/auth/meetings.space.readonly"
# Resource names come from the API and become URL paths: accept only their documented shape.
_RECORD = re.compile(r"^conferenceRecords/[A-Za-z0-9_-]{1,128}$")
_TRANSCRIPT = re.compile(r"^conferenceRecords/[A-Za-z0-9_-]{1,128}/transcripts/[A-Za-z0-9_-]{1,128}$")
_PARTICIPANT = re.compile(r"^conferenceRecords/[A-Za-z0-9_-]{1,128}/participants/[A-Za-z0-9_-]{1,128}$")
MAX_PAGES = 500  # 50,000 entries: far beyond any meeting, bounded all the same


class MeetAdapter(native.PlatformAdapter):
    platform = "google_meet"
    label = "Google Meet"
    api_env = "AGENT_SKILLS_MEET_BASE_URL"
    api_suffixes = (".googleapis.com",)
    default_api = "https://meet.googleapis.com/v2"

    def oauth_client(self, transport=None) -> meeting_oauth.OAuthClient:
        extra = {"access_type": "offline", "prompt": "consent"}
        if self.settings.get("workspace_domain"):
            extra["hd"] = self.settings["workspace_domain"]
        return meeting_oauth.OAuthClient(
            "Google", "https://accounts.google.com/o/oauth2/v2/auth", "https://oauth2.googleapis.com/token",
            self.settings["client_id"], SCOPES,
            self.settings.get("redirect_uri") or native.DEFAULT_REDIRECT["google_meet"],
            client_secret=self._client_secret, extra_authorize=extra, transport=transport,
        )

    def resolve(self, meeting_url: str, display_url: str) -> Tuple[dict, Optional[bool], str]:
        code = urlsplit(meeting_url).path.strip("/")
        status, body = self.get_json("{}/spaces/{}".format(self.base, quote(code, safe="")))
        if status in (403, 404):
            raise mc.MeetingRefusal("no_access", "Google Meet did not let you read this meeting space (HTTP {}). "
                                    "Meet artifacts are readable only by the space's owner or participants in "
                                    "your Workspace, and in practice often only the organiser. {}".format(
                                        status, native.EXTERNAL_HINT))
        if status >= 400:
            raise native.refusal_for_status(self.label, status, body, self.fix_command) or mc.MeetingRefusal(
                "no_access", "Google Meet refused the request (HTTP {}).".format(status))
        return {"code": code}, None, ""

    def _records(self, ref: dict) -> List[dict]:
        query = 'space.meeting_code = "{}"'.format(ref["code"])
        status, body = self.get_json("{}/conferenceRecords?pageSize=25&filter={}".format(
            self.base, quote(query, safe="")))
        if status >= 400:
            raise native.refusal_for_status(self.label, status, body, self.fix_command) or mc.MeetingRefusal(
                "no_access", "Google Meet refused the request (HTTP {}).".format(status))
        records = [r for r in (body.get("conferenceRecords") or [])
                   if isinstance(r, dict) and _RECORD.match(str(r.get("name", "")))]
        since = native.parse_time(ref.get("after"))
        if since:
            # A Meet link is reused by recurring meetings; only conferences that
            # started around or after the join count.
            records = [r for r in records if (native.parse_time(r.get("startTime")) or since) >= since - timedelta(hours=1)]
        return sorted(records, key=lambda r: str(r.get("startTime", "")), reverse=True)

    def _latest_ended(self, ref: dict) -> Tuple[Optional[dict], bool]:
        records = self._records(ref)
        ended = [r for r in records if r.get("endTime")]
        return (ended[0] if ended else None), bool(records)

    def _transcripts(self, record: dict) -> List[dict]:
        status, body = self.get_json("{}/{}/transcripts".format(self.base, record["name"]))
        if status >= 400:
            raise native.refusal_for_status(self.label, status, body, self.fix_command) or mc.MeetingRefusal(
                "no_access", "Google Meet refused the request (HTTP {}).".format(status))
        return [t for t in (body.get("transcripts") or [])
                if isinstance(t, dict) and _TRANSCRIPT.match(str(t.get("name", "")))]

    def status(self, ref: dict) -> Tuple[str, Optional[datetime]]:
        record, any_record = self._latest_ended(ref)
        if record is None:
            return "waiting", None
        transcripts = self._transcripts(record)
        # Entries are readable once the transcript has ENDED; the Docs file
        # (FILE_GENERATED) is not needed.
        if any(t.get("state") in ("ENDED", "FILE_GENERATED") for t in transcripts):
            return "available", None
        return "ended", native.parse_time(record.get("endTime"))

    def _participant_name(self, name: str, cache: Dict[str, str]) -> str:
        if not _PARTICIPANT.match(name):
            return "Unknown speaker"
        if name not in cache:
            status, body = self.get_json("{}/{}".format(self.base, name))
            label = ""
            if status < 400:
                for kind in ("signedinUser", "anonymousUser", "phoneUser"):
                    entry = body.get(kind)
                    if isinstance(entry, dict) and entry.get("displayName"):
                        label = str(entry["displayName"])
                        break
            cache[name] = label or "Unknown speaker"
        return cache[name]

    def fetch(self, ref: dict, meeting_id: str) -> mc.NormalisedTranscript:
        record, _ = self._latest_ended(ref)
        if record is None:
            raise mc.MeetingRefusal("not_yet_available", "Google Meet has not finished this conference yet.")
        transcripts = [t for t in self._transcripts(record) if t.get("state") in ("ENDED", "FILE_GENERATED")]
        if not transcripts:
            raise mc.MeetingRefusal("not_enabled", native.NOT_ENABLED_HINT)
        start = native.parse_time(record.get("startTime")) or self.now()
        names: Dict[str, str] = {}
        utterances: List[Tuple[str, str, float, float, str]] = []
        languages: Dict[str, int] = {}
        for transcript in sorted(transcripts, key=lambda t: str(t.get("startTime", ""))):
            token = ""
            for _ in range(MAX_PAGES):
                url = "{}/{}/entries?pageSize=100".format(self.base, transcript["name"])
                if token:
                    url += "&pageToken=" + quote(token, safe="")
                status, body = self.get_json(url)
                if status >= 400:
                    raise native.refusal_for_status(self.label, status, body, self.fix_command) or \
                        mc.MeetingRefusal("no_access", "Google Meet refused the request (HTTP {}).".format(status))
                for entry in body.get("transcriptEntries") or []:
                    if not isinstance(entry, dict):
                        continue
                    begin = native.parse_time(entry.get("startTime")) or start
                    end = native.parse_time(entry.get("endTime")) or begin
                    participant = str(entry.get("participant", ""))
                    lang = str(entry.get("languageCode", ""))[:16]
                    if lang:
                        languages[lang] = languages.get(lang, 0) + 1
                    utterances.append((self._participant_name(participant, names), participant.rsplit("/", 1)[-1],
                                       (begin - start).total_seconds(), (end - start).total_seconds(),
                                       str(entry.get("text", ""))))
                token = str(body.get("nextPageToken") or "")
                if not token:
                    break
        utterances.sort(key=lambda u: u[2])
        result = mc.build_transcript(meeting_id, "native", utterances)
        result.language = max(languages, key=languages.get) if languages else ""
        return result

    def self_test(self) -> str:
        status, _ = self.get_json("{}/conferenceRecords?pageSize=1".format(self.base))
        if status == 200:
            return "signed in; Meet accepted the delegated token (no transcript was read)"
        raise mc.ProviderAuthError("Google Meet refused the self-test (HTTP {}); check the OAuth consent "
                                   "screen and the {} scope".format(status, SCOPES))
