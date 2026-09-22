#!/usr/bin/env python3
"""agent-skills meeting — Meeting Intelligence, from a meeting link to scoped facts.

    agent-skills meeting join <meeting-url> [--scope <repo>] [--title <text>]
    agent-skills meeting status [<id>] [--wait] [--listen <host:port>]
    agent-skills meeting stop <id>
    agent-skills meeting list
    agent-skills meeting inspect <id> [--transcript] [--facts] [--next-window]
                                      [--submit <file|->] [--reprocess]
                                      [--accept all|<fact-ids>] [--purge [--yes]]

That is the whole surface. Natural language ("Listen to this meeting: <url>")
arrives through the `meeting-intelligence` skill, which calls this command.

How a meeting moves:

    join       validates the link locally, resolves the scope, sends a visible,
               named bot, persists the meeting, and returns. The terminal does
               not have to stay open.
    status     reconciles: polls the provider for any meeting not yet finished,
    list       advances the lifecycle monotonically, retrieves and redacts the
    inspect    transcript once the recording is done, and prepares bounded
               windows. Every step is idempotent and checkpointed, so running it
               twice, or after a crash, is always safe.
    (host)     the skill reads each window with `inspect --next-window` and
               returns strict JSON with `inspect --submit`. The CLI validates it;
               when the last window is in, the meeting's facts are committed to
               the repository knowledge base in one write, or not at all.

Polling alone takes a meeting from join to facts. `status --listen` is an
optional accelerator for users with their own public URL: verified webhooks
only schedule a reconcile, they never carry state.

Exit codes follow the frozen contract in lib/asrelease/exits.py:
  0 ok, 2 usage, 3 authentication required, 4 network, 5 integrity,
  7 local meeting state unreadable.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import knowledge_resolver as knowledge  # noqa: E402  (the Knowledge Resolver; 1.3.0)
import meeting_capture as mc  # noqa: E402
import meeting_intel as intel  # noqa: E402
import meeting_secrets  # noqa: E402
import meeting_store as store  # noqa: E402
from durable import LockTimeout  # noqa: E402
from guard_audit import redact  # noqa: E402

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_AUTH = 3
EXIT_NETWORK = 4
EXIT_INTEGRITY = 5
EXIT_STATE = 7

_KIND_TO_EXIT = {"auth": EXIT_AUTH, "network": EXIT_NETWORK, "integrity": EXIT_INTEGRITY, "usage": EXIT_USAGE}

WEBHOOK_PATH = "/agent-skills/meeting/webhook"
MAX_WEBHOOK_BYTES = 1024 * 1024
STUCK_AFTER_HOURS = 6
BACKOFF_MAX_SECONDS = 1800

# Tests replace this with a factory returning a fake provider. Production
# resolves Recall through the Access Resolver.
PROVIDER_FACTORY: Optional[Callable[[Dict[str, object], bool], mc.MeetingCaptureProvider]] = None


class CliError(Exception):
    def __init__(self, message: str, code: int, hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.hint = hint


def out(text: str = "") -> None:
    print(text)


def err(text: str) -> None:
    print(text, file=sys.stderr)


# ---------------------------------------------------------------------------
# Provider and credentials
# ---------------------------------------------------------------------------
RECALL_SETUP_HINT = (
    "store it with: agent-skills access set --profile recall --service recall "
    "--field region=<region> --secret-field api_key   (hidden input; or set "
    "AGENT_SKILLS_RECALL_API_KEY in the environment)"
)


def resolve_recall_credentials(need_secret: bool) -> Dict[str, str]:
    from access import resolve_access

    fields = ["api_key", "region"] + (["verification_secret"] if need_secret else [])
    values: Dict[str, str] = {}
    resolve_access(
        "recall", "", fields, {"api_key", "verification_secret"}, Path.cwd(),
        allow_capability=False, values_out=values,
    )
    return values


def recall_credential_presence() -> tuple:
    """(api key configured?, region) from metadata only — no secret is read.

    `doctor` runs inside every `start-task`; fetching a keychain secret there
    just to report that it exists would read a credential on every task.
    """
    from access import env_candidates, load_profiles

    present = any(os.environ.get(name) for name in env_candidates("recall", "api_key"))
    region = next((os.environ[n] for n in env_candidates("recall", "region") if os.environ.get(n)), "")
    for entry in (load_profiles().get("profiles") or {}).values():
        if not isinstance(entry, dict) or entry.get("service") != "recall":
            continue
        present = present or "api_key" in (entry.get("secret_fields") or [])
        fields = entry.get("fields") if isinstance(entry.get("fields"), dict) else {}
        region = region or str(fields.get("region") or "")
    return present, region


def effective_region(config: Dict[str, object], credentials: Dict[str, str]) -> str:
    configured = str(config.get("region") or "").strip()
    stored = str(credentials.get("region") or "").strip()
    if configured and stored and configured != stored:
        raise CliError(
            "region mismatch: meeting config says {} but the Recall credential is for {}".format(configured, stored),
            EXIT_AUTH,
            "Recall keys, bots, and media are region-local; make them agree",
        )
    return configured or stored


def build_provider(config: Dict[str, object], need_secret: bool = False) -> mc.MeetingCaptureProvider:
    if PROVIDER_FACTORY is not None:
        return PROVIDER_FACTORY(config, need_secret)
    if config.get("provider") != "recall":
        raise CliError("unknown capture provider {!r}".format(config.get("provider")), EXIT_USAGE)
    import meeting_recall

    credentials = resolve_recall_credentials(need_secret)
    region = effective_region(config, credentials)
    if not region:
        raise CliError(
            "no Recall region is configured",
            EXIT_AUTH,
            "set one of {} as the credential's region field (or AGENT_SKILLS_RECALL_REGION)".format(
                ", ".join(meeting_recall.REGIONS)
            ),
        )
    if not credentials.get("api_key"):
        raise CliError("no Recall API key is available", EXIT_AUTH, RECALL_SETUP_HINT)
    if need_secret and not credentials.get("verification_secret"):
        raise CliError(
            "listener mode needs the Recall workspace verification secret",
            EXIT_AUTH,
            "add it with --secret-field verification_secret on the recall profile",
        )
    try:
        return meeting_recall.RecallMeetingBotProvider(
            credentials["api_key"], region, credentials.get("verification_secret", "")
        )
    except mc.ProviderError as exc:
        raise CliError(exc.message, _KIND_TO_EXIT.get(exc.kind, EXIT_USAGE)) from None


def provider_failure(exc: mc.ProviderError) -> CliError:
    return CliError(exc.message, _KIND_TO_EXIT.get(exc.kind, EXIT_NETWORK))


# ---------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------
def _git_root(path: Path) -> Optional[Path]:
    try:
        done = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], cwd=str(path),
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    top = done.stdout.strip()
    return Path(top).resolve() if done.returncode == 0 and top else None


def resolve_scope(raw: Optional[str]) -> dict:
    """A meeting has no inherent repository; the scope is bound here, once."""
    if raw is not None:
        value = raw.strip()
        kind, _, rest = value.partition(":")
        if kind in ("team", "org", "organization", "project"):
            raise CliError(
                "scope {!r} is not supported: the knowledge system has repository scope only".format(kind),
                EXIT_USAGE,
                "no team or organisation store exists; see docs/meeting-intelligence.md#scope",
            )
        if value in ("none", "unscoped"):
            return {"kind": "unscoped"}
        target = rest if kind in ("repo", "repository") else value
        path = Path(target).expanduser()
        root = _git_root(path) if path.is_dir() else None
        if root is None:
            raise CliError("scope {!r} is not a git repository on this machine".format(value), EXIT_USAGE)
    else:
        root = _git_root(Path.cwd())
        if root is None:
            return {"kind": "unscoped"}
    scope = knowledge.repository_scope(root)
    scope["root"] = str(root)
    return scope


def scope_label(scope: dict) -> str:
    return scope.get("label") or "unscoped"


# ---------------------------------------------------------------------------
# Reconcile: the only thing that advances a meeting
# ---------------------------------------------------------------------------
def _clearly_partial(transcript: mc.NormalisedTranscript, record: dict) -> bool:
    seconds = record.get("recording_seconds") or 0
    if seconds < 300:
        return False
    words = sum(len(s.text.split()) for s in transcript.segments)
    return transcript.span_seconds() < 0.5 * seconds or words < 20


def _store_transcript(record: dict, transcript: mc.NormalisedTranscript, partial: bool) -> None:
    texts, hits = meeting_secrets.redact_segments(
        [s.text for s in transcript.segments], [s.speaker_label for s in transcript.segments]
    )
    for segment, text in zip(transcript.segments, texts):
        segment.text = text
        segment.speaker_label = redact(segment.speaker_label)
    store.save_transcript(transcript)
    record["transcript"].update(
        {"stored_at": store.now_iso(), "segments": len(transcript.segments), "redactions": hits, "purged_at": ""}
    )
    record["transcription"]["final_method"] = transcript.source_method
    record["transcription"]["partial"] = bool(partial)
    candidate = store.meeting_dir(record["id"]) / "transcript-candidate.json"
    if candidate.exists():
        candidate.unlink()


def _candidate_path(record: dict) -> Path:
    return store.meeting_dir(record["id"]) / "transcript-candidate.json"


def _save_candidate(record: dict, transcript: mc.NormalisedTranscript) -> None:
    # A thin live transcript kept while async transcription runs, so a failed
    # fallback still leaves something to process. Redacted like the real one.
    texts, _ = meeting_secrets.redact_segments(
        [s.text for s in transcript.segments], [s.speaker_label for s in transcript.segments]
    )
    for segment, text in zip(transcript.segments, texts):
        segment.text = text
    payload = {
        "schema": store.TRANSCRIPT_SCHEMA,
        "meeting_id": transcript.meeting_id,
        "source_method": transcript.source_method,
        "segments": [s.to_dict() for s in transcript.segments],
    }
    store._write_private_json(_candidate_path(record), payload)


def _load_candidate(record: dict) -> Optional[mc.NormalisedTranscript]:
    path = _candidate_path(record)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return mc.NormalisedTranscript(
        meeting_id=record["id"],
        source_method=str(data.get("source_method", "")),
        segments=[mc.Segment.from_dict(record["id"], s) for s in data.get("segments", [])],
    )


def _retrieve_transcript(record: dict, provider: mc.MeetingCaptureProvider) -> None:
    handle = mc.CaptureHandle.from_dict(record["handle"])
    info = record["transcription"]
    method = "async" if info["async_requested"] else info["live_method"]
    result = provider.fetch_transcript(handle, record["id"], method)
    info["attempts"] = (info.get("attempts") or [])[-19:] + [
        {"at": store.now_iso(), "method": method, "status": result.status, "reason": redact(result.reason)[:60]}
    ]
    if result.status == "pending":
        return
    transcript = result.transcript if result.status == "ready" else None
    good = transcript is not None and transcript.usable and not _clearly_partial(transcript, record)
    if good:
        _store_transcript(record, transcript, partial=False)  # type: ignore[arg-type]
        store.transition(record, mc.TRANSCRIPT_READY, "transcript via " + method)
        return
    if transcript is not None and transcript.usable:
        _save_candidate(record, transcript)
    can_fallback = (
        "async" in info["preference"]
        and not info["async_requested"]
        and not record["media"].get("deleted_at")
    )
    if can_fallback and provider.request_async_transcript(handle):
        info["async_requested"] = True
        record["reason"] = "live transcript empty or partial; post-meeting transcription requested"
        return
    candidate = _load_candidate(record)
    if candidate is not None and candidate.usable:
        _store_transcript(record, candidate, partial=True)
        store.transition(record, mc.TRANSCRIPT_READY, "partial transcript via " + candidate.source_method)
        return
    store.transition(record, mc.FAILED, "transcription_unavailable")


def _plan_path(meeting_id: str) -> Path:
    return store.windows_dir(meeting_id) / "plan.json"


def _load_plan(meeting_id: str) -> List[dict]:
    path = _plan_path(meeting_id)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("windows", [])


def _prepare_processing(record: dict, config: Dict[str, object]) -> None:
    transcript = store.load_transcript(record["id"])
    if transcript is None:
        store.transition(record, mc.FAILED, "transcript missing")
        return
    plan = intel.plan_windows(
        transcript, int(config["window_budget_chars"]), int(config["window_overlap_chars"])  # type: ignore[arg-type]
    )
    store._write_private_json(_plan_path(record["id"]), {"windows": plan, "budget_chars": config["window_budget_chars"]})
    record["processing"].update({"windows": len(plan), "completed": [], "failed": [], "attempts": {}})
    store.transition(record, mc.PROCESSING, "{} window(s) ready for extraction".format(len(plan)))


def _maybe_delete_media(record: dict, provider: mc.MeetingCaptureProvider, config: Dict[str, object]) -> None:
    if not config.get("delete_media_after_transcript") or record["media"].get("deleted_at"):
        return
    if not record["transcript"].get("stored_at"):
        return
    try:
        provider.delete_media(mc.CaptureHandle.from_dict(record["handle"]))
    except mc.ProviderError as exc:
        record["media"]["delete_error"] = redact(exc.message)[:120]
        return
    record["media"]["deleted_at"] = store.now_iso()
    record["media"]["delete_error"] = ""


def _backoff_active(record: dict) -> bool:
    info = record.get("reconcile") or {}
    failures = int(info.get("failures") or 0)
    last = store.parse_iso(str(info.get("last_attempt_at") or ""))
    if not failures or last is None:
        return False
    wait = min(BACKOFF_MAX_SECONDS, 30 * (2 ** min(failures, 10)))
    return (datetime.now(timezone.utc) - last).total_seconds() < wait


def needs_provider(record: dict, config: Dict[str, object]) -> bool:
    """Whether reconciling this record has anything to ask the provider."""
    state = record["state"]
    return bool(
        state in mc.PROVIDER_ACTIVE_STATES
        or state in (mc.ENDED, mc.MEDIA_READY)
        or (
            record["transcript"].get("stored_at")
            and config.get("delete_media_after_transcript")
            and not record["media"].get("deleted_at")
        )
    )


def reconcile(meeting_id: str, config: Dict[str, object], provider: Optional[mc.MeetingCaptureProvider],
              honour_backoff: bool = False) -> dict:
    """Advance one meeting as far as it can go right now. Idempotent.

    Each stage persists before the next begins, so a crash at any point
    resumes from the last saved stage. Provider failures are recorded on the
    meeting and retried later; they never lose or regress state.
    """
    with store.meeting_lock(meeting_id):
        record = store.load_record(meeting_id)
        use_provider = needs_provider(record, config) and provider is not None and not (
            honour_backoff and _backoff_active(record)
        )
        if use_provider:
            record["reconcile"]["last_attempt_at"] = store.now_iso()
        try:
            if use_provider and (record["state"] in mc.PROVIDER_ACTIVE_STATES or record["state"] == mc.ENDED):
                obs = provider.poll(mc.CaptureHandle.from_dict(record["handle"]))  # type: ignore[union-attr]
                if obs.recording_seconds:
                    record["recording_seconds"] = obs.recording_seconds
                moved = store.transition(record, obs.state, obs.reason)
                if moved and obs.state == mc.PERMISSION_DENIED:
                    # A clean failure, not a retry loop: ask the bot to leave.
                    try:
                        provider.stop(mc.CaptureHandle.from_dict(record["handle"]))  # type: ignore[union-attr]
                    except mc.ProviderError:
                        pass
                store.save_record(record)
            if use_provider and record["state"] == mc.MEDIA_READY:
                _retrieve_transcript(record, provider)  # type: ignore[arg-type]
                store.save_record(record)
            if record["state"] == mc.TRANSCRIPT_READY:
                _prepare_processing(record, config)
                store.save_record(record)
            if use_provider:
                _maybe_delete_media(record, provider, config)  # type: ignore[arg-type]
                record["reconcile"].update({"last_error": "", "failures": 0})
        except mc.ProviderError as exc:
            record["reconcile"]["last_error"] = redact(exc.message)[:160]
            record["reconcile"]["failures"] = int(record["reconcile"].get("failures") or 0) + 1
            store.save_record(record)
            raise
        if record["state"] == mc.PROCESSING and _all_windows_done(record):
            _finalize(record)
        _retention_sweep(record, config)
        store.save_record(record)
        return record


def _retention_sweep(record: dict, config: Dict[str, object]) -> None:
    days = int(config["transcript_retention_days"])  # type: ignore[arg-type]
    if record["state"] == mc.PROCESSING:
        return  # never pull the transcript out from under an extraction in progress
    if store.transcript_expired(record, days) and not record["transcript"].get("purged_at"):
        store.purge_local_transcript(record["id"])
        record["transcript"]["purged_at"] = store.now_iso()
        _mark_transcript_unavailable(record)


def _all_windows_done(record: dict) -> bool:
    processing = record["processing"]
    done = set(processing.get("completed", [])) | set(processing.get("failed", []))
    return processing.get("windows", 0) > 0 and len(done) >= processing["windows"]


# ---------------------------------------------------------------------------
# Extraction submission and the per-meeting commit
# ---------------------------------------------------------------------------
def _prior_facts(scope: dict) -> List[dict]:
    if scope.get("kind") != "repository" or not scope.get("root") or not Path(scope["root"]).is_dir():
        return []
    return knowledge.prior_facts(Path(scope["root"]))


def _finalize(record: dict) -> None:
    transcript = store.load_transcript(record["id"])
    if transcript is None:
        raise CliError("the transcript is gone; run inspect --reprocess after a new transcript", EXIT_STATE)
    plan = _load_plan(record["id"])
    checkpoints = store.load_window_checkpoints(record["id"])
    scope = record["scope"]
    root = Path(scope["root"]) if scope.get("root") else None
    scope_known = scope.get("kind") == "repository" and root is not None and root.is_dir()
    prior = [f for f in _prior_facts(scope) if f.get("meeting_id") != record["id"]]
    facts, notes = intel.finalize(
        record["id"], transcript, plan, checkpoints, scope_known, record["created_at"][:10], prior
    )
    partial = bool(record["transcription"].get("partial") or record["processing"].get("failed"))
    payload = {
        "schema": intel.FACTS_SCHEMA,
        "meeting_id": record["id"],
        "title": record.get("title", ""),
        "date": record["created_at"][:10],
        "platform": record["platform"],
        "scope": {k: scope[k] for k in ("kind", "key", "label") if k in scope},
        "source_method": record["transcription"].get("final_method", ""),
        "partial": partial,
        "transcript_available": True,
        "facts": facts,
        "notes": notes[:50],
        "committed_at": store.now_iso(),
    }
    if scope_known:
        path = knowledge.write_meeting_facts(root, payload)  # type: ignore[arg-type]
        record["processing"]["knowledge_file"] = str(path)
    else:
        if scope.get("kind") == "repository":
            for fact in payload["facts"]:
                fact["review_state"] = intel.PENDING_REVIEW
                fact["review_note"] = "bound repository not found at commit time; accept with --scope"
        store.save_pending_facts(record["id"], payload)
    record["processing"]["committed_at"] = payload["committed_at"]
    record["processing"]["summary"] = {
        "facts": len(facts),
        "pending_review": sum(1 for f in facts if f.get("review_state") == intel.PENDING_REVIEW),
    }
    store.transition(record, mc.PARTIAL if partial else mc.PROCESSED, "facts committed")


def submit_extraction(meeting_id: str, payload: object) -> dict:
    with store.meeting_lock(meeting_id):
        record = store.load_record(meeting_id)
        if record["state"] != mc.PROCESSING:
            raise CliError("meeting {} is {}, not awaiting extraction".format(meeting_id, record["state"]), EXIT_USAGE)
        plan = _load_plan(meeting_id)
        index = payload.get("window") if isinstance(payload, dict) else None
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(plan):
            raise CliError("submission names no valid window (0..{})".format(len(plan) - 1), EXIT_USAGE)
        processing = record["processing"]
        if index in processing["completed"]:
            return record  # idempotent: a retried submission is not a second extraction
        if index in processing["failed"]:
            raise CliError("window {} already failed validation {} times".format(index, intel.MAX_ATTEMPTS_PER_WINDOW),
                           EXIT_USAGE, "run inspect --reprocess to start the meeting's extraction again")
        transcript = store.load_transcript(meeting_id)
        if transcript is None:
            raise CliError("the transcript is no longer stored", EXIT_STATE)
        window_ids = plan[index]["segment_ids"]
        try:
            raw_facts = intel.validate_submission(payload, meeting_id, index, window_ids)
        except intel.ExtractionRejected as exc:
            attempts = processing["attempts"]
            attempts[str(index)] = int(attempts.get(str(index), 0)) + 1
            if attempts[str(index)] >= intel.MAX_ATTEMPTS_PER_WINDOW:
                processing["failed"].append(index)
                store.save_window_checkpoint(meeting_id, index, {"status": "failed", "errors": exc.errors[:20]})
            store.save_record(record)
            left = intel.MAX_ATTEMPTS_PER_WINDOW - attempts[str(index)]
            raise CliError(
                "extraction for window {} rejected: {}".format(index, "; ".join(exc.errors[:8])),
                EXIT_USAGE,
                "{} attempt(s) left; resubmit valid JSON — output is never repaired".format(max(0, left)),
            ) from None
        segments = {s.segment_id: s for s in transcript.segments}
        facts: List[dict] = []
        notes: List[str] = []
        for raw in raw_facts:
            fact, fact_notes = intel.check_fact(raw, meeting_id, window_ids, segments, transcript.source_method)
            notes.extend("window {}: {}".format(index, n) for n in fact_notes)
            if fact is not None:
                facts.append(fact)
        store.save_window_checkpoint(meeting_id, index, {"status": "accepted", "facts": facts, "notes": notes})
        processing["completed"].append(index)
        store.save_record(record)
        if _all_windows_done(record):
            _finalize(record)
            store.save_record(record)
        return record


def _mark_transcript_unavailable(record: dict) -> None:
    path = record["processing"].get("knowledge_file")
    if not path or not Path(path).exists():
        pending = store.load_pending_facts(record["id"])
        if pending is not None:
            pending["transcript_available"] = False
            store.save_pending_facts(record["id"], pending)
        return
    data = knowledge.read_meeting_file(Path(path))
    data["transcript_available"] = False
    knowledge.write_meeting_facts(Path(record["scope"]["root"]), data)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def _facts_for(record: dict) -> Optional[dict]:
    path = record["processing"].get("knowledge_file")
    if path and Path(path).exists():
        return knowledge.read_meeting_file(Path(path))
    return store.load_pending_facts(record["id"])


def _status_line(record: dict) -> str:
    title = record.get("title") or "(untitled)"
    extra = ""
    if record["state"] == mc.PROCESSING:
        processing = record["processing"]
        done = len(processing["completed"]) + len(processing["failed"])
        extra = "  extraction {}/{} window(s)".format(done, processing["windows"])
    if record.get("reason") and record["state"] in mc.FAILURE_STATES:
        extra += "  reason: " + record["reason"]
    if (record.get("reconcile") or {}).get("last_error"):
        extra += "  (last check failed: {}; will retry)".format(record["reconcile"]["last_error"])
    return "{}  {:<22} {:<16} {:<18} {}{}".format(
        record["id"], record["state"], mc.PLATFORM_LABELS.get(record["platform"], record["platform"]),
        scope_label(record["scope"]), title[:40], extra,
    )


def _next_step(record: dict) -> str:
    state = record["state"]
    if state == mc.PROCESSING:
        return ("Transcript ready. Extraction runs in your assistant: ask it to process meeting {id}, "
                "or read `agent-skills meeting inspect {id} --next-window`.").format(id=record["id"])
    if state in mc.PROVIDER_ACTIVE_STATES or state in (mc.ENDED, mc.MEDIA_READY):
        return "Check progress: agent-skills meeting status {}".format(record["id"])
    return ""


def print_summary(record: dict) -> None:
    payload = _facts_for(record)
    facts = payload.get("facts", []) if payload else []
    out(intel.summarize(record, facts))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def cmd_join(args: argparse.Namespace) -> int:
    try:
        platform, display = mc.classify_meeting_url(args.url)
    except mc.MeetingUrlError as exc:
        raise CliError(str(exc), EXIT_USAGE, "supported: Microsoft Teams, Google Meet, and Zoom meeting links") from None
    scope = resolve_scope(args.scope)
    config = store.load_config()
    if not store.consent_current(config):
        out(store.consent_text(config))
        if args.acknowledge_recording_notice:
            store.record_consent(config)
        elif sys.stdin.isatty():
            reply = input("Type 'I understand' to continue: ").strip().lower()
            if reply != "i understand":
                raise CliError("recording notice not acknowledged; nothing was created", EXIT_USAGE)
            store.record_consent(config)
        else:
            raise CliError(
                "the one-time recording notice has not been acknowledged; nothing was created",
                EXIT_USAGE,
                "show the notice above to the user; once they explicitly agree, re-run with "
                "--acknowledge-recording-notice",
            )
    provider = build_provider(config)
    live = next((m for m in config["transcription_preference"] if m != "async"), "captions")  # type: ignore[union-attr]
    meeting_id = store.new_meeting_id()
    leave = config["automatic_leave"]
    options = mc.CaptureOptions(
        bot_name=str(config["bot_name"]),
        chat_notice=str(config["chat_notice"]),
        live_method=live,
        retention_hours=int(config["media_retention_hours"]),  # type: ignore[arg-type]
        waiting_room_timeout=int(leave["waiting_room_timeout"]),  # type: ignore[index]
        noone_joined_timeout=int(leave["noone_joined_timeout"]),  # type: ignore[index]
        everyone_left_timeout=int(leave["everyone_left_timeout"]),  # type: ignore[index]
        correlation_id=meeting_id,
    )
    try:
        handle = provider.start(args.url.strip(), options)
    except mc.ProviderError as exc:
        raise provider_failure(exc) from None
    record = store.new_record(meeting_id, platform, display, args.title or "", scope, handle, live, config)
    store.save_record(record)
    label = mc.PLATFORM_LABELS[platform]
    out("{} → joining ({})".format(config["bot_name"], label))
    out("Meeting id: {}   Scope: {}".format(meeting_id, scope_label(scope)))
    out('The assistant will appear in the participant list as "{}".'.format(config["bot_name"]))
    out("Tell participants that recording and transcription are active.")
    if scope.get("kind") != "repository":
        out("No repository scope: extracted facts will wait for review (inspect --accept --scope <repo>).")
    out("Check progress: agent-skills meeting status {}".format(meeting_id))
    return EXIT_OK


def _reconcile_many(ids: List[str], config: Dict[str, object], explicit: bool) -> int:
    provider: Optional[mc.MeetingCaptureProvider] = None
    code = EXIT_OK
    for meeting_id in ids:
        try:
            record = store.load_record(meeting_id)
        except store.StateError as exc:
            err("{}: {}".format(meeting_id, exc))
            code = max(code, EXIT_STATE)
            continue
        if provider is None and needs_provider(record, config):
            try:
                provider = build_provider(config)
            except CliError as exc:
                if explicit:
                    raise
                # Local work (retention, a pending commit) still runs below.
                err("provider unavailable: {}".format(exc.message))
        try:
            reconcile(meeting_id, config, provider, honour_backoff=not explicit)
        except mc.ProviderError as exc:
            err("{}: {} (state kept; will retry)".format(meeting_id, exc.message))
            code = max(code, _KIND_TO_EXIT.get(exc.kind, EXIT_NETWORK)) if explicit else code
        except CliError as exc:
            err("{}: {}".format(meeting_id, exc.message))
            code = max(code, exc.code)
        except (OSError, LockTimeout, knowledge.UsageError, store.StateError) as exc:
            # One meeting's local failure must not stop the others. Nothing was
            # committed for it; the next reconcile resumes from its checkpoint.
            err("{}: could not finish this step ({}); state kept, will retry".format(
                meeting_id, type(exc).__name__))
            code = max(code, EXIT_STATE)
    return code


def cmd_status(args: argparse.Namespace) -> int:
    config = store.load_config()
    if args.listen:
        return run_listener(args.listen, config)
    ids = [store.resolve_meeting_id(args.id)] if args.id else store.list_meeting_ids()
    if not ids:
        out("No meetings yet. Start one: agent-skills meeting join <meeting-url>")
        return EXIT_OK
    deadline = time.monotonic() + args.timeout
    while True:
        code = _reconcile_many(ids, config, explicit=bool(args.id))
        records = []
        for meeting_id in ids:
            try:
                records.append(store.load_record(meeting_id))
            except store.StateError:
                continue
        waiting = [r for r in records if r["state"] in mc.PROVIDER_ACTIVE_STATES or r["state"] in (mc.ENDED, mc.MEDIA_READY)]
        if not args.wait or not waiting or time.monotonic() >= deadline:
            break
        time.sleep(args.interval)
    for record in records:
        if args.id and record["state"] in (mc.PROCESSED, mc.PARTIAL):
            print_summary(record)
            continue
        out(_status_line(record))
        if args.id and _next_step(record):
            out(_next_step(record))
    return code


def cmd_stop(args: argparse.Namespace) -> int:
    meeting_id = store.resolve_meeting_id(args.id)
    config = store.load_config()
    with store.meeting_lock(meeting_id):
        record = store.load_record(meeting_id)
        if record["state"] not in mc.PROVIDER_ACTIVE_STATES:
            out("{} is {}; the assistant is no longer in the meeting.".format(meeting_id, record["state"]))
            return EXIT_OK
        provider = build_provider(config)
        try:
            provider.stop(mc.CaptureHandle.from_dict(record["handle"]))
        except mc.ProviderError as exc:
            raise provider_failure(exc) from None
        record.setdefault("history", []).append({"at": store.now_iso(), "state": record["state"], "reason": "stop requested"})
        store.save_record(record)
    out("Asked the assistant to leave {}. What was recorded so far will still be processed.".format(meeting_id))
    out("Check progress: agent-skills meeting status {}".format(meeting_id))
    return EXIT_OK


def cmd_list(args: argparse.Namespace) -> int:
    config = store.load_config()
    ids = store.list_meeting_ids()
    if not ids:
        out("No meetings yet.")
        return EXIT_OK
    _reconcile_many(ids, config, explicit=False)
    for meeting_id in ids:
        try:
            out(_status_line(store.load_record(meeting_id)))
        except store.StateError as exc:
            out("{}  UNREADABLE  {}".format(meeting_id, exc))
    return EXIT_OK


def _read_submission(source: str) -> object:
    try:
        text = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    except OSError:
        raise CliError("cannot read submission {}".format(source), EXIT_USAGE) from None
    if len(text) > 2 * 1024 * 1024:
        raise CliError("submission is larger than 2 MB", EXIT_USAGE)
    try:
        return json.loads(text)
    except ValueError:
        raise CliError("submission is not valid JSON; output is never repaired — resubmit", EXIT_USAGE) from None


def _print_facts(record: dict) -> None:
    payload = _facts_for(record)
    if not payload:
        out("No facts recorded for {} yet (state {}).".format(record["id"], record["state"]))
        return
    if not payload.get("transcript_available", True) or record["transcript"].get("purged_at"):
        out("The underlying transcript is no longer available; facts keep their timestamps.")
    for fact in payload.get("facts", []):
        stamps = ", ".join(
            "@{}-{}".format(mc.format_ts(e["start_ts"]), mc.format_ts(e["end_ts"])) for e in fact["evidence"][:4]
        )
        line = "[{}] {} {} (conf {:.2f}; {}; {})".format(
            fact["status"], fact["type"], fact["statement"], fact["confidence"], fact["review_state"], stamps
        )
        if fact.get("owner"):
            line += " owner: " + fact["owner"]
        if fact.get("due"):
            line += " due: " + fact["due"]
        if fact.get("superseded_by"):
            line += " superseded by " + fact["superseded_by"]
        for link in fact.get("supersedes", []):
            line += " supersedes " + link["fact_id"]
        if fact.get("review_note"):
            line += " — " + fact["review_note"]
        out("- " + line)
        out("    id {}  speakers: {}".format(fact["id"], ", ".join(fact.get("speakers", [])) or "-"))
    out("-- Meeting facts are evidence, not truth: verify them against the code.")


def _accept(record: dict, which: str, scope_arg: Optional[str]) -> None:
    payload = store.load_pending_facts(record["id"])
    committed = False
    if payload is None:
        path = record["processing"].get("knowledge_file")
        if not path or not Path(path).exists():
            raise CliError("no facts are waiting for review on {}".format(record["id"]), EXIT_USAGE)
        payload = knowledge.read_meeting_file(Path(path))
        committed = True
    wanted = None if which == "all" else {w.strip() for w in which.split(",") if w.strip()}
    if committed:
        root = Path(record["scope"]["root"])
    else:
        if scope_arg is None and record["scope"].get("kind") == "repository":
            scope_arg = record["scope"].get("root")
        if scope_arg is None:
            raise CliError("this meeting has no repository scope; pass --scope <repo>", EXIT_USAGE)
        scope = resolve_scope(scope_arg)
        if scope.get("kind") != "repository":
            raise CliError("--accept needs a repository scope", EXIT_USAGE)
        bound = record["scope"]
        if bound.get("kind") == "repository" and bound.get("key") != scope["key"]:
            raise CliError("this meeting is bound to {}; its facts cannot move to another repository".format(
                bound.get("label")), EXIT_USAGE)
        root = Path(scope["root"])
        payload["scope"] = {k: scope[k] for k in ("kind", "key", "label")}
        record["scope"] = scope
    changed = 0
    for fact in payload.get("facts", []):
        if fact.get("review_state") == intel.PENDING_REVIEW and (wanted is None or fact["id"] in wanted):
            fact["review_state"] = intel.ACCEPTED
            fact["review_note"] = "accepted by the user on {}".format(store.now_iso()[:10])
            changed += 1
    if not changed:
        raise CliError("nothing matched; see inspect --facts for pending fact ids", EXIT_USAGE)
    path = knowledge.write_meeting_facts(root, payload)
    record["processing"]["knowledge_file"] = str(path)
    if not committed:
        store.pending_facts_path(record["id"]).unlink()
    out("Accepted {} fact(s) into {}.".format(changed, path))


def cmd_inspect(args: argparse.Namespace) -> int:
    meeting_id = store.resolve_meeting_id(args.id)
    config = store.load_config()
    if args.submit:
        record = submit_extraction(meeting_id, _read_submission(args.submit))
        if record["state"] in (mc.PROCESSED, mc.PARTIAL):
            print_summary(record)
        else:
            processing = record["processing"]
            done = len(processing["completed"]) + len(processing["failed"])
            out("Window accepted ({}/{}). Next: agent-skills meeting inspect {} --next-window".format(
                done, processing["windows"], meeting_id))
        return EXIT_OK
    if args.purge:
        return _purge(meeting_id, config, args.yes)
    if args.reprocess:
        with store.meeting_lock(meeting_id):
            record = store.load_record(meeting_id)
            if store.load_transcript(meeting_id) is None:
                raise CliError("the transcript is no longer stored, so the meeting cannot be reprocessed", EXIT_USAGE)
            if record["state"] not in (mc.PROCESSING, mc.PROCESSED, mc.PARTIAL):
                raise CliError("only a transcribed meeting can be reprocessed", EXIT_USAGE)
            store.clear_window_checkpoints(meeting_id)
            # An explicit user action, so the one sanctioned backward move.
            record["state"] = mc.TRANSCRIPT_READY
            record["history"].append({"at": store.now_iso(), "state": mc.TRANSCRIPT_READY, "reason": "reprocess requested"})
            _prepare_processing(record, config)
            store.save_record(record)
        out("Reprocessing {}: {} window(s) ready. Existing facts stay until the new run commits.".format(
            meeting_id, record["processing"]["windows"]))
        return EXIT_OK
    with store.meeting_lock(meeting_id):
        record = store.load_record(meeting_id)
        if args.accept:
            _accept(record, args.accept, args.scope)
            store.save_record(record)
            return EXIT_OK
    if args.next_window or args.window is not None:
        return _print_window(record, args.window)
    if args.json:
        out(json.dumps(record, indent=2, sort_keys=True))
        return EXIT_OK
    out(_status_line(record))
    out("  scope: {}   created: {}   bot: {}".format(scope_label(record["scope"]), record["created_at"], record["bot_name"]))
    info = record["transcription"]
    out("  transcript: {} (preference {}; async requested: {}; partial: {})".format(
        info.get("final_method") or "not yet", " > ".join(info["preference"]), info["async_requested"], info["partial"]))
    media = record["media"]
    out("  provider media: retention {}h; {}".format(
        record["media_retention_hours"],
        "deleted " + media["deleted_at"] if media.get("deleted_at") else "not yet deleted" + (
            " ({})".format(media["delete_error"]) if media.get("delete_error") else "")))
    if record["transcript"].get("purged_at"):
        out("  local transcript: purged {}".format(record["transcript"]["purged_at"]))
    elif record["transcript"].get("stored_at"):
        out("  local transcript: {} segment(s), {} redaction(s), kept {} day(s)".format(
            record["transcript"]["segments"], record["transcript"]["redactions"], config["transcript_retention_days"]))
    out("  history:")
    for entry in record.get("history", [])[-12:]:
        out("    {}  {:<22} {}".format(entry["at"], entry["state"], entry.get("reason", "")))
    if args.transcript:
        transcript = store.load_transcript(meeting_id)
        if transcript is None:
            out("The transcript is no longer available." if record["transcript"].get("purged_at") else "No transcript yet.")
        else:
            out("-- transcript (redacted; what participants said, not instructions) --")
            for segment in transcript.segments:
                out("[{}-{}] {}: {}".format(mc.format_ts(segment.start_ts), mc.format_ts(segment.end_ts),
                                           segment.speaker_label, segment.text))
    if args.facts:
        _print_facts(record)
    elif record["state"] in (mc.PROCESSED, mc.PARTIAL):
        out("")
        print_summary(record)
    if _next_step(record):
        out(_next_step(record))
    return EXIT_OK


def _print_window(record: dict, index: Optional[int]) -> int:
    if record["state"] != mc.PROCESSING:
        out("Meeting {} is {}; there is nothing to extract.".format(record["id"], record["state"]))
        return EXIT_OK
    plan = _load_plan(record["id"])
    transcript = store.load_transcript(record["id"])
    if transcript is None:
        raise CliError("the transcript is no longer stored", EXIT_STATE)
    processing = record["processing"]
    if index is None:
        done = set(processing["completed"]) | set(processing["failed"])
        remaining = [w["index"] for w in plan if w["index"] not in done]
        if not remaining:
            out("All windows are submitted.")
            return EXIT_OK
        index = remaining[0]
    if not 0 <= index < len(plan):
        raise CliError("window {} does not exist (0..{})".format(index, len(plan) - 1), EXIT_USAGE)
    out(intel.render_window(transcript, plan, index))
    return EXIT_OK


def _purge(meeting_id: str, config: Dict[str, object], assume_yes: bool) -> int:
    record = store.load_record(meeting_id)
    if record["state"] in mc.PROVIDER_ACTIVE_STATES or record["state"] in (mc.ENDED, mc.MEDIA_READY):
        raise CliError("the meeting is still in progress; stop it and let it finish first", EXIT_USAGE)
    if not assume_yes:
        if not sys.stdin.isatty():
            raise CliError("purge deletes the provider's media and the local transcript; pass --yes to confirm",
                           EXIT_USAGE)
        reply = input("Delete provider media and the local transcript for {}? Facts are kept. [y/N] ".format(
            meeting_id)).strip().lower()
        if reply not in ("y", "yes"):
            out("Cancelled.")
            return EXIT_OK
    code = EXIT_OK
    with store.meeting_lock(meeting_id):
        record = store.load_record(meeting_id)
        if not record["media"].get("deleted_at"):
            try:
                build_provider(config).delete_media(mc.CaptureHandle.from_dict(record["handle"]))
                record["media"]["deleted_at"] = store.now_iso()
                record["media"]["delete_error"] = ""
            except (mc.ProviderError, CliError) as exc:
                message = exc.message
                record["media"]["delete_error"] = redact(message)[:120]
                err("provider media NOT deleted: {} — run the purge again later".format(message))
                code = exc.code if isinstance(exc, CliError) else _KIND_TO_EXIT.get(exc.kind, EXIT_NETWORK)
        store.purge_local_transcript(meeting_id)
        if _candidate_path(record).exists():
            _candidate_path(record).unlink()
        record["transcript"]["purged_at"] = store.now_iso()
        _mark_transcript_unavailable(record)
        if record["state"] != mc.PROCESSING:
            store.transition(record, mc.PURGED, "media and transcript purged by the user")
        store.save_record(record)
    out("Local transcript for {} deleted; facts are kept and still cite their timestamps.".format(meeting_id))
    if code == EXIT_OK:
        out("Provider media deleted. Recall may still keep bot metadata and logs for a limited period;"
            " see docs/meeting-intelligence.md#what-the-provider-keeps.")
    return code


# ---------------------------------------------------------------------------
# Optional listener
# ---------------------------------------------------------------------------
def run_listener(bind: str, config: Dict[str, object], max_events: Optional[int] = None) -> int:
    import meeting_webhook

    host, _, port_text = bind.rpartition(":")
    host = host.strip("[]") or "127.0.0.1"
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise CliError("the listener binds to loopback only; expose it with your own tunnel", EXIT_USAGE)
    try:
        port = int(port_text)
    except ValueError:
        raise CliError("--listen takes host:port, e.g. 127.0.0.1:8787", EXIT_USAGE) from None
    provider = build_provider(config, need_secret=True)
    events: "queue.Queue[mc.ProviderEvent]" = queue.Queue()

    def worker() -> None:
        while True:
            event = events.get()
            meeting_id = _meeting_for_event(event)
            if meeting_id:
                try:
                    reconcile(meeting_id, config, provider)
                except Exception:  # noqa: BLE001 - never let one event kill the listener
                    err("reconcile after webhook failed for {}; polling will recover".format(meeting_id))
            events.task_done()

    threading.Thread(target=worker, daemon=True).start()
    out("Listening on {}:{}{} (loopback). Point your tunnel at it; polling remains the fallback.".format(
        host, port, WEBHOOK_PATH))
    meeting_webhook.serve(host, port, WEBHOOK_PATH, provider, events.put, MAX_WEBHOOK_BYTES, max_events)
    events.join()
    return EXIT_OK


def _meeting_for_event(event: mc.ProviderEvent) -> str:
    if event.correlation_id and store.MEETING_ID_RE.match(event.correlation_id):
        try:
            record = store.load_record(event.correlation_id)
            if record["handle"].get("provider_ref") == event.provider_ref:
                return event.correlation_id
        except store.StateError:
            pass
    for meeting_id in store.list_meeting_ids():
        try:
            if store.load_record(meeting_id)["handle"].get("provider_ref") == event.provider_ref:
                return meeting_id
        except store.StateError:
            continue
    return ""


# ---------------------------------------------------------------------------
# doctor section (internal; called by scripts/doctor.sh)
# ---------------------------------------------------------------------------
def doctor_report(probe: bool) -> dict:
    report: Dict[str, object] = {}
    try:
        config = store.load_config()
    except store.ConfigError as exc:
        return {"config": "invalid: {}".format(exc)}
    report["consent"] = "acknowledged" if store.consent_current(config) else "not yet acknowledged"
    report["listener"] = (
        "configured (run: agent-skills meeting status --listen 127.0.0.1:<port>)"
        if config.get("listener_url") else "not configured (polling only)"
    )
    try:
        present, stored_region = recall_credential_presence()
        report["credentials"] = "api key resolves" if present else "api key missing"
        try:
            region = effective_region(config, {"region": stored_region})
            report["region"] = region or "not configured"
        except CliError as exc:
            report["region"] = "MISMATCH: " + exc.message
    except Exception:  # noqa: BLE001 - a report, never a crash
        report["credentials"] = "could not be resolved"
        report["region"] = "unknown"
    stuck = []
    unreadable = 0
    for meeting_id in store.list_meeting_ids():
        try:
            record = store.load_record(meeting_id)
        except store.StateError:
            unreadable += 1
            continue
        updated = store.parse_iso(record.get("updated_at", ""))
        if not store.is_terminal(record) and updated and (
            datetime.now(timezone.utc) - updated
        ).total_seconds() > STUCK_AFTER_HOURS * 3600:
            stuck.append("{} ({})".format(meeting_id, record["state"]))
    report["meetings"] = len(store.list_meeting_ids())
    report["stuck"] = stuck
    report["unreadable"] = unreadable
    if probe:
        try:
            provider = build_provider(config)
            probe_fn = getattr(provider, "probe", None)
            if probe_fn:
                probe_fn()
            report["provider"] = "reachable; key and region accepted"
        except CliError as exc:
            report["provider"] = "not probed: " + exc.message
        except mc.ProviderError as exc:
            report["provider"] = "FAILED: " + exc.message
    else:
        report["provider"] = "not probed (doctor stays offline; use doctor --probe-meeting)"
    return report


def cmd_doctor(args: argparse.Namespace) -> int:
    report = doctor_report(args.probe)
    if args.json:
        out(json.dumps(report, sort_keys=True))
        return EXIT_OK
    for key in ("credentials", "region", "provider", "consent", "listener"):
        out("  {:<12}: {}".format(key, report.get(key, "")))
    stuck = report.get("stuck") or []
    out("  {:<12}: {} total; {} stuck{}{}".format(
        "meetings", report.get("meetings", 0), len(stuck),  # type: ignore[arg-type]
        (" — " + ", ".join(stuck)) if stuck else "",  # type: ignore[arg-type]
        "; {} unreadable".format(report["unreadable"]) if report.get("unreadable") else ""))
    return EXIT_OK


# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-skills meeting", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True, metavar="{join,status,stop,list,inspect}")

    sp = sub.add_parser("join", help="Send the visible assistant into a meeting.")
    sp.add_argument("url")
    sp.add_argument("--scope", default=None, help="repo:<path> (default: this repository); 'none' for unscoped")
    sp.add_argument("--title", default="")
    sp.add_argument("--acknowledge-recording-notice", action="store_true",
                    help="record the user's explicit acknowledgement of the one-time notice")
    sp.set_defaults(func=cmd_join)

    sp = sub.add_parser("status", help="Reconcile and show meetings.")
    sp.add_argument("id", nargs="?")
    sp.add_argument("--wait", action="store_true", help="poll until the recording is transcribed")
    sp.add_argument("--interval", type=int, default=30)
    sp.add_argument("--timeout", type=int, default=4 * 3600)
    sp.add_argument("--listen", default="", help="optional webhook listener on loopback host:port")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("stop", help="Ask the assistant to leave; what was recorded is processed.")
    sp.add_argument("id")
    sp.set_defaults(func=cmd_stop)

    sp = sub.add_parser("list", help="Reconcile and list all meetings.")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("inspect", help="Details, transcript, facts, and the extraction steps.")
    sp.add_argument("id")
    sp.add_argument("--transcript", action="store_true")
    sp.add_argument("--facts", action="store_true")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--next-window", action="store_true")
    sp.add_argument("--window", type=int, default=None)
    sp.add_argument("--submit", default=None, help="extraction JSON for one window (file or -)")
    sp.add_argument("--reprocess", action="store_true")
    sp.add_argument("--accept", default=None, help="all, or comma-separated fact ids")
    sp.add_argument("--scope", default=None)
    sp.add_argument("--purge", action="store_true")
    sp.add_argument("--yes", action="store_true")
    sp.set_defaults(func=cmd_inspect)

    # Internal, for scripts/doctor.sh. Not part of the user surface.
    sp = sub.add_parser("_doctor")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--probe", action="store_true")
    sp.set_defaults(func=cmd_doctor)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return EXIT_USAGE if exc.code else EXIT_OK
    try:
        return int(args.func(args))
    except CliError as exc:
        err("agent-skills meeting: {}".format(redact(exc.message)))
        if exc.hint:
            err("  " + exc.hint)
        return exc.code
    except store.ConfigError as exc:
        err("agent-skills meeting: {}".format(exc))
        return EXIT_USAGE
    except store.StateError as exc:
        err("agent-skills meeting: {}".format(exc))
        return EXIT_USAGE if "no such meeting" in str(exc) or "not a meeting id" in str(exc) else EXIT_STATE
    except knowledge.UsageError as exc:
        err("agent-skills meeting: {}".format(exc))
        return EXIT_USAGE
    except mc.ProviderError as exc:
        err("agent-skills meeting: {}".format(exc.message))
        return _KIND_TO_EXIT.get(exc.kind, EXIT_NETWORK)
    except LockTimeout as exc:
        err("agent-skills meeting: {}".format(exc))
        return EXIT_STATE
    except OSError as exc:
        err("agent-skills meeting: a local write failed ({}); nothing was committed".format(type(exc).__name__))
        return EXIT_STATE
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
