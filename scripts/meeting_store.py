#!/usr/bin/env python3
"""Durable meeting state, configuration, and the lifecycle state machine.

State lives under `~/.agent-skills/state/meetings/` — the directory the install
layout documents as surviving every update and rollback — never inside a
version directory:

    state/meetings/
      <meeting-id>/record.json        schema agent-skills.meeting/v1
      <meeting-id>/transcript.json    redacted before it is written; purgeable
      <meeting-id>/windows/<n>.json   per-window extraction checkpoints
      webhook-events.json             recent provider event ids, for dedupe

Releases before this one never read `state/meetings/`, so rolling back ignores
it. This release reads only records whose schema major version it knows and
reports any other as unreadable instead of guessing.

Non-secret configuration is `~/.config/agent-skills/meeting.json`. Credentials
are not here; they belong to the Access Resolver.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import meeting_capture as mc
from durable import locked, update_json, write_text
from guard_audit import redact

RECORD_SCHEMA = "agent-skills.meeting/v1"
TRANSCRIPT_SCHEMA = "agent-skills.meeting-transcript/v1"
CONFIG_SCHEMA = "agent-skills.meeting-config/v1"
KNOWN_MAJOR = "agent-skills.meeting/v1"

MEETING_ID_RE = re.compile(r"^m_[0-9a-f]{12}$")
REQUIRED_RECORD_KEYS = {
    "id": str, "state": str, "platform": str, "scope": dict, "handle": dict, "history": list,
    "created_at": str, "transcription": dict, "transcript": dict, "processing": dict,
    "media": dict, "reconcile": dict,
}
CONSENT_NOTICE_VERSION = 1

CONSENT_NOTICE = """\
Before Agent Skills joins a meeting, please confirm you understand:

  1. The assistant joins VISIBLY, as a named participant ("{bot_name}"),
     and posts a chat message saying it is recording and transcribing.
  2. You must tell participants that recording and transcription are active.
  3. Your organisation's policies and local law still apply — including
     all-party/two-party consent jurisdictions and GDPR — and meeting them
     is your responsibility.
  4. Audio, video, and transcripts are processed by the capture provider
     (Recall.ai, region {region}); media is kept there for at most
     {retention_hours} hours and deleted sooner once the transcript is stored.

Agent Skills never joins automatically, never records covertly, and never
hides the assistant's name.
"""

DEFAULT_CONFIG: Dict[str, object] = {
    "schema": CONFIG_SCHEMA,
    "provider": "recall",
    "region": "",
    "bot_name": "Agent Skills Meeting Assistant",
    "chat_notice": (
        "Agent Skills Meeting Assistant is recording and transcribing this meeting "
        "to capture engineering decisions. Tell the organiser if you object."
    ),
    "transcription_preference": ["captions", "provider_transcription", "async"],
    "automatic_leave": {
        "waiting_room_timeout": 600,
        "noone_joined_timeout": 600,
        "everyone_left_timeout": 30,
    },
    "media_retention_hours": 48,
    "delete_media_after_transcript": True,
    "transcript_retention_days": 30,
    "window_budget_chars": 12000,
    "window_overlap_chars": 1200,
    "listener_url": "",
    "consent": {},
    # 1.4.0: the user's choice among capture providers, and what they were told.
    # `provider` above keeps its 1.2.0 meaning ("recall") so a rollback to 1.3.0
    # reads this file unchanged; the choice lives in `default_provider`.
    "default_provider": "",
    "provider_notices": {},
    "recall": {"cost_per_hour_usd": 0.65},
    "native": {},
    "desktop": {},
}

BOUNDS = {
    "media_retention_hours": (1, 168),
    "transcript_retention_days": (1, 365),
    "window_budget_chars": (4000, 60000),
    "window_overlap_chars": (0, 8000),
    "waiting_room_timeout": (30, 3600),
    "noone_joined_timeout": (30, 3600),
    "everyone_left_timeout": (1, 3600),
}


class StateError(Exception):
    """A record is unreadable or from an unknown schema. Maps to exit 7."""


class ConfigError(Exception):
    """Configuration is invalid. Maps to exit 2."""


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str) -> Optional[datetime]:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------
def home_dir() -> Path:
    home = os.environ.get("AGENT_SKILLS_HOME")
    return Path(home).expanduser() if home else Path.home() / ".agent-skills"


def state_root() -> Path:
    return home_dir() / "state" / "meetings"


def config_dir() -> Path:
    override = os.environ.get("AGENT_SKILLS_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg).expanduser() / "agent-skills"
    return Path.home() / ".config" / "agent-skills"


def config_path() -> Path:
    return config_dir() / "meeting.json"


def meeting_dir(meeting_id: str) -> Path:
    if not MEETING_ID_RE.match(meeting_id):
        raise StateError("not a meeting id: {!r}".format(meeting_id))
    return state_root() / meeting_id


def _private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def _write_private_json(path: Path, payload: object) -> None:
    _private_dir(path.parent)
    write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n", mode=0o600)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
def _clamp(name: str, value: object, default: int) -> int:
    low, high = BOUNDS[name]
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def load_config() -> Dict[str, object]:
    path = config_path()
    data: Dict[str, object] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise ConfigError("{} is not valid JSON".format(path)) from None
        if isinstance(loaded, dict):
            data = loaded
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    for key in DEFAULT_CONFIG:
        if key in data:
            config[key] = data[key]
    leave = dict(DEFAULT_CONFIG["automatic_leave"])  # type: ignore[arg-type]
    if isinstance(data.get("automatic_leave"), dict):
        for key in leave:
            leave[key] = _clamp(key, data["automatic_leave"].get(key), leave[key])  # type: ignore[union-attr]
    config["automatic_leave"] = leave
    for key in ("media_retention_hours", "transcript_retention_days", "window_budget_chars", "window_overlap_chars"):
        config[key] = _clamp(key, config.get(key), int(DEFAULT_CONFIG[key]))  # type: ignore[arg-type]
    # The assistant's name and its recording notice may be changed, never
    # emptied: a nameless participant or a silent recorder is the covert
    # capture this feature refuses to do.
    for key in ("bot_name", "chat_notice"):
        text = " ".join(str(config.get(key) or "").split())
        config[key] = text[:100 if key == "bot_name" else 500] or DEFAULT_CONFIG[key]
    preference = config.get("transcription_preference")
    if not isinstance(preference, list):
        preference = list(DEFAULT_CONFIG["transcription_preference"])  # type: ignore[arg-type]
    preference = [p for p in preference if p in ("captions", "provider_transcription", "async")]
    config["transcription_preference"] = preference or list(DEFAULT_CONFIG["transcription_preference"])  # type: ignore[arg-type]
    config["delete_media_after_transcript"] = bool(config.get("delete_media_after_transcript", True))
    config["listener_url"] = str(config.get("listener_url") or "")
    if not isinstance(config.get("consent"), dict):
        config["consent"] = {}
    for key in ("provider_notices", "recall", "native", "desktop"):
        if not isinstance(config.get(key), dict):
            config[key] = json.loads(json.dumps(DEFAULT_CONFIG[key]))
    config["provider"] = "recall"
    if config.get("default_provider") not in ("", "native", "recall", "desktop"):
        config["default_provider"] = ""
    return config


def save_config(config: Dict[str, object]) -> None:
    stored = {key: config[key] for key in DEFAULT_CONFIG if key in config}
    _write_private_json(config_path(), stored)


def consent_current(config: Dict[str, object]) -> bool:
    consent = config.get("consent") or {}
    return isinstance(consent, dict) and consent.get("notice_version") == CONSENT_NOTICE_VERSION


def record_consent(config: Dict[str, object]) -> None:
    config["consent"] = {"notice_version": CONSENT_NOTICE_VERSION, "acknowledged_at": now_iso()}
    save_config(config)


def consent_text(config: Dict[str, object]) -> str:
    return CONSENT_NOTICE.format(
        bot_name=config["bot_name"],
        region=config.get("region") or "<not configured>",
        retention_hours=config["media_retention_hours"],
    )


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------
def new_meeting_id() -> str:
    return "m_" + secrets.token_hex(6)


def record_path(meeting_id: str) -> Path:
    return meeting_dir(meeting_id) / "record.json"


def load_record(meeting_id: str) -> dict:
    path = record_path(meeting_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise StateError("no such meeting: {}".format(meeting_id)) from None
    except (OSError, ValueError):
        raise StateError("meeting record {} is unreadable".format(meeting_id)) from None
    if not isinstance(data, dict) or data.get("schema") != KNOWN_MAJOR:
        raise StateError(
            "meeting record {} uses schema {!r}, which this release does not read".format(
                meeting_id, data.get("schema") if isinstance(data, dict) else None
            )
        )
    missing = [key for key in REQUIRED_RECORD_KEYS if not isinstance(data.get(key), REQUIRED_RECORD_KEYS[key])]
    if missing or data.get("id") != meeting_id:
        raise StateError("meeting record {} is incomplete ({})".format(meeting_id, ", ".join(missing) or "id"))
    return data


def save_record(record: dict) -> None:
    record["updated_at"] = now_iso()
    _write_private_json(record_path(record["id"]), record)


def list_meeting_ids() -> List[str]:
    root = state_root()
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and MEETING_ID_RE.match(p.name))


def resolve_meeting_id(prefix: str) -> str:
    prefix = (prefix or "").strip()
    if not re.match(r"^m_[0-9a-f]{1,12}$", prefix):
        raise ConfigError("not a meeting id: {!r}".format(prefix))
    matches = [m for m in list_meeting_ids() if m.startswith(prefix)]
    if not matches:
        raise ConfigError("no meeting matches {}".format(prefix))
    if len(matches) > 1:
        raise ConfigError("{} is ambiguous: {}".format(prefix, ", ".join(matches)))
    return matches[0]


def meeting_lock(meeting_id: str):
    _private_dir(meeting_dir(meeting_id))
    return locked(meeting_dir(meeting_id) / "record.json")


def new_record(
    meeting_id: str,
    platform: str,
    display_url: str,
    title: str,
    scope: dict,
    handle: mc.CaptureHandle,
    live_method: str,
    config: Dict[str, object],
    initial_state: str = mc.JOINING,
    initial_reason: str = "bot requested",
    attribution: str = "named",
) -> dict:
    return {
        "schema": RECORD_SCHEMA,
        "id": meeting_id,
        "title": redact(title)[:200] if title else "",
        "platform": platform,
        "meeting_url_display": display_url,
        "scope": scope,
        "handle": handle.to_dict(),
        "state": initial_state,
        "reason": "",
        "history": [{"at": now_iso(), "state": initial_state, "reason": initial_reason}],
        "capture_provider": handle.provider,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "bot_name": config["bot_name"],
        "region": config.get("region", ""),
        "media_retention_hours": config["media_retention_hours"],
        "transcription": {
            "preference": list(config["transcription_preference"]),  # type: ignore[arg-type]
            "live_method": live_method,
            "attempts": [],
            "async_requested": False,
            "final_method": "",
            "partial": False,
            "speaker_attribution": attribution,
            "language": "",
        },
        "recording_seconds": None,
        "media": {"deleted_at": "", "delete_error": ""},
        "transcript": {"stored_at": "", "purged_at": "", "segments": 0, "redactions": 0},
        "processing": {
            "windows": 0,
            "completed": [],
            "failed": [],
            "attempts": {},
            "committed_at": "",
            "knowledge_file": "",
            "summary": {},
        },
        "reconcile": {"last_attempt_at": "", "last_error": "", "failures": 0},
    }


def transition(record: dict, state: str, reason: str = "") -> bool:
    """Apply a lifecycle transition monotonically. Returns whether it moved.

    Lower-ranked states are refused, and so is anything after a terminal state
    other than PURGED. This is what makes a duplicate, stale, or out-of-order
    observation harmless: it can only ever restate progress already recorded.
    """
    current = str(record.get("state", mc.CREATED))
    if state == current:
        return False
    if current in mc.TERMINAL_STATES and state != mc.PURGED:
        return False
    if mc.RANK.get(state, -1) <= mc.RANK.get(current, -1):
        return False
    record["state"] = state
    record["reason"] = redact(reason)[:120] if reason else ""
    record.setdefault("history", []).append(
        {"at": now_iso(), "state": state, "reason": record["reason"]}
    )
    return True


def is_terminal(record: dict) -> bool:
    return str(record.get("state")) in mc.TERMINAL_STATES


# ---------------------------------------------------------------------------
# Transcript storage (always already redacted by the caller)
# ---------------------------------------------------------------------------
def transcript_path(meeting_id: str) -> Path:
    return meeting_dir(meeting_id) / "transcript.json"


def save_transcript(transcript: mc.NormalisedTranscript) -> None:
    _write_private_json(
        transcript_path(transcript.meeting_id),
        {
            "schema": TRANSCRIPT_SCHEMA,
            "meeting_id": transcript.meeting_id,
            "source_method": transcript.source_method,
            "speaker_attribution": transcript.speaker_attribution,
            "capture_provider": transcript.capture_provider,
            "language": transcript.language,
            "segments": [s.to_dict() for s in transcript.segments],
        },
    )


def load_transcript(meeting_id: str) -> Optional[mc.NormalisedTranscript]:
    path = transcript_path(meeting_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise StateError("stored transcript for {} is unreadable".format(meeting_id)) from None
    if not isinstance(data, dict) or data.get("schema") != TRANSCRIPT_SCHEMA:
        raise StateError("stored transcript for {} has an unknown schema".format(meeting_id))
    return mc.NormalisedTranscript(
        meeting_id=meeting_id,
        source_method=str(data.get("source_method", "")),
        segments=[mc.Segment.from_dict(meeting_id, s) for s in data.get("segments", [])],
        speaker_attribution=str(data.get("speaker_attribution") or "named"),
        capture_provider=str(data.get("capture_provider") or ""),
        language=str(data.get("language") or ""),
    )


def windows_dir(meeting_id: str) -> Path:
    return meeting_dir(meeting_id) / "windows"


def save_window_checkpoint(meeting_id: str, index: int, payload: dict) -> None:
    _write_private_json(windows_dir(meeting_id) / "{:04d}.json".format(index), payload)


def load_window_checkpoints(meeting_id: str) -> Dict[int, dict]:
    out: Dict[int, dict] = {}
    folder = windows_dir(meeting_id)
    if not folder.is_dir():
        return out
    for path in sorted(folder.glob("*.json")):
        try:
            out[int(path.stem)] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return out


def clear_window_checkpoints(meeting_id: str) -> None:
    shutil.rmtree(windows_dir(meeting_id), ignore_errors=True)


def pending_facts_path(meeting_id: str) -> Path:
    return meeting_dir(meeting_id) / "facts.json"


def save_pending_facts(meeting_id: str, payload: dict) -> None:
    _write_private_json(pending_facts_path(meeting_id), payload)


def load_pending_facts(meeting_id: str) -> Optional[dict]:
    path = pending_facts_path(meeting_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def purge_local_transcript(meeting_id: str) -> bool:
    removed = False
    path = transcript_path(meeting_id)
    if path.exists():
        path.unlink()
        removed = True
    if windows_dir(meeting_id).exists():
        clear_window_checkpoints(meeting_id)
        removed = True
    return removed


def transcript_expired(record: dict, retention_days: int, now: Optional[datetime] = None) -> bool:
    stored = parse_iso(str((record.get("transcript") or {}).get("stored_at", "")))
    if stored is None:
        return False
    now = now or datetime.now(timezone.utc)
    return now - stored > timedelta(days=retention_days)


# ---------------------------------------------------------------------------
# Webhook event dedupe
# ---------------------------------------------------------------------------
EVENT_LOG_LIMIT = 5000
EVENT_TTL_HOURS = 48


def remember_event(event_id: str) -> bool:
    """Record a provider event id. False when it was already seen (a duplicate)."""
    _private_dir(state_root())
    path = state_root() / "webhook-events.json"
    seen = {"duplicate": False}
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=EVENT_TTL_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def transform(data: dict) -> dict:
        events = data.get("events") if isinstance(data.get("events"), dict) else {}
        events = {k: v for k, v in events.items() if str(v) >= cutoff}
        if event_id in events:
            seen["duplicate"] = True
        else:
            events[event_id] = now_iso()
        if len(events) > EVENT_LOG_LIMIT:
            events = dict(sorted(events.items(), key=lambda kv: kv[1])[-EVENT_LOG_LIMIT:])
        return {"schema": "agent-skills.meeting-events/v1", "events": events}

    update_json(path, transform, default={})
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return not seen["duplicate"]
