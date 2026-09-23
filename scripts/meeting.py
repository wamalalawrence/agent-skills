#!/usr/bin/env python3
"""agent-skills meeting — Meeting Intelligence, from a meeting link to scoped facts.

    agent-skills meeting setup [native|recall|desktop] [--compare] [--import <file>]
    agent-skills meeting join <meeting-url> [--via native|recall|desktop] [--scope <repo>] [--title <text>]
    agent-skills meeting fetch <meeting-url> [--scope <repo>]      (native: a meeting that already ended)
    agent-skills meeting status [<id>] [--providers] [--wait] [--listen <host:port>]
    agent-skills meeting stop <id>
    agent-skills meeting list
    agent-skills meeting inspect <id> [--transcript] [--facts] [--next-window]
                                      [--submit <file|->] [--reprocess]
                                      [--accept all|<fact-ids>] [--purge [--yes]]

That is the whole surface. Natural language ("Listen to this meeting: <url>")
arrives through the `meeting-intelligence` skill, which calls this command.

Capture is the user's choice among three providers (`meeting_providers.py`):
`native` downloads the transcript the platform already made, `recall` sends a
visible bot, `desktop` records on this computer and transcribes locally. The
user picks a default in `meeting setup` and may override it per meeting with
`--via`. With nothing chosen, `join` runs no provider at all: it prints the
preflight that explains the three options. A provider that cannot serve a
meeting stops with the reason and the alternatives; nothing ever falls back to
another provider on its own.

How a meeting moves:

    join       validates the link, checks the chosen provider is ready (local
               checks, no network), resolves the scope, starts the capture,
               persists the meeting, and returns. The terminal does not have to
               stay open.
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
import meeting_providers as providers  # noqa: E402  (the one place providers are built; 1.4.0)
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
    def __init__(self, message: str, code: int, hint: str = "", plain: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.hint = hint
        self.plain = plain  # a complete, user-facing text (the preflight): printed as is


def out(text: str = "") -> None:
    print(text)


def err(text: str) -> None:
    print(text, file=sys.stderr)


# ---------------------------------------------------------------------------
# Providers: chosen by the user, built by meeting_providers.py
# ---------------------------------------------------------------------------
def provider_for_record(record: dict) -> str:
    """Records from 1.2.0/1.3.0 carry only the handle; its provider is the id."""
    return str(record.get("capture_provider") or (record.get("handle") or {}).get("provider") or "recall")


def build_provider(config: Dict[str, object], need_secret: bool = False,
                   provider: str = "recall") -> mc.MeetingCaptureProvider:
    if PROVIDER_FACTORY is not None:
        return PROVIDER_FACTORY(config, need_secret)
    try:
        return providers.build(config, provider, need_secret)
    except mc.ProviderError as exc:
        raise CliError(exc.message, _KIND_TO_EXIT.get(exc.kind, EXIT_USAGE)) from None


def provider_failure(exc: mc.ProviderError) -> CliError:
    return CliError(exc.message, _KIND_TO_EXIT.get(exc.kind, EXIT_NETWORK))


def _readiness_exit(state: mc.Readiness) -> int:
    lowered = state.reason.lower()
    auth = ("key", "sign", "secret", "region", "credential", "token")
    return EXIT_AUTH if any(word in lowered for word in auth) else EXIT_USAGE


def choose_provider(config: Dict[str, object], via: Optional[str]) -> str:
    """The provider the user chose, ready to run; otherwise stop and say exactly why.

    No network call happens before this returns: readiness is local.
    """
    chosen = via or providers.default_provider(config)
    if chosen is None:
        raise CliError(providers.preflight_text(config), EXIT_USAGE, plain=True)
    if chosen not in providers.PROVIDERS:
        raise CliError("unknown capture provider {!r}; choose native, recall, or desktop".format(chosen), EXIT_USAGE)
    if PROVIDER_FACTORY is not None:
        return chosen  # the test harness injected a provider in place of the real one
    state = providers.readiness(config, chosen)
    if state.state == mc.NOT_CONFIGURED:
        raise CliError(
            "the {} provider is not set up on this machine ({}).".format(chosen, state.reason),
            EXIT_USAGE,
            "set it up: {}\ncompare the options: agent-skills meeting setup --compare".format(state.fix_command),
        )
    if not state.ready:
        raise CliError("the {} provider is not ready: {}".format(chosen, state.reason), _readiness_exit(state),
                       "fix: " + state.fix_command)
    return chosen


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
    record["transcription"]["speaker_attribution"] = transcript.speaker_attribution
    record["transcription"]["language"] = transcript.language
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
        "speaker_attribution": transcript.speaker_attribution,
        "capture_provider": transcript.capture_provider,
        "language": transcript.language,
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
        speaker_attribution=str(data.get("speaker_attribution") or "named"),
        capture_provider=str(data.get("capture_provider") or ""),
        language=str(data.get("language") or ""),
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
        if result.progress:
            record["reason"] = redact(result.progress)[:120]
        return
    transcript = result.transcript if result.status == "ready" else None
    # "Clearly partial" is a heuristic for a live transcript that a post-meeting
    # pass could still improve; a provider without one reports partial itself.
    can_retry = "async" in provider.capabilities().transcription_methods
    good = transcript is not None and transcript.usable and (
        result.partial or not can_retry or not _clearly_partial(transcript, record))
    if good:
        _store_transcript(record, transcript, partial=result.partial)  # type: ignore[arg-type]
        store.transition(record, mc.TRANSCRIPT_READY, ("partial transcript via " if result.partial
                                                       else "transcript via ") + transcript.source_method)
        return
    if transcript is not None and transcript.usable:
        _save_candidate(record, transcript)
    can_fallback = (
        can_retry
        and "async" in info["preference"]
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
    named = mc.REFUSALS + ("local_transcription_failed", "audio_missing", "nothing_was_said", "empty_transcript")
    store.transition(record, mc.FAILED, result.reason if result.reason in named else "transcription_unavailable")


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


def _desktop_settings(config: Dict[str, object]) -> dict:
    return config.get("desktop") if isinstance(config.get("desktop"), dict) else {}  # type: ignore[return-value]


def media_pending(record: dict, config: Dict[str, object]) -> bool:
    """Is there captured media left to delete for this meeting, now?

    recall: the provider's recording, once the transcript is stored (config
    `delete_media_after_transcript`). desktop: the raw local audio, at once by
    default, else after `desktop.raw_audio_retention_days` (at most 7).
    native: never — no media was downloaded, and the platform's transcript
    stays under the organisation's own retention.
    """
    if record["media"].get("deleted_at") or not record["transcript"].get("stored_at"):
        return False
    kind = provider_for_record(record)
    if kind == "native":
        return False
    if kind == "desktop":
        desktop = _desktop_settings(config)
        if desktop.get("delete_audio_after_transcript", True):
            return True
        try:
            days = max(1, min(7, int(desktop.get("raw_audio_retention_days", 1))))
        except (TypeError, ValueError):
            days = 1
        return store.transcript_expired(record, days)
    return bool(config.get("delete_media_after_transcript"))


def _maybe_delete_media(record: dict, provider: mc.MeetingCaptureProvider, config: Dict[str, object]) -> None:
    if not media_pending(record, config):
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
        or media_pending(record, config)
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
        "capture_provider": provider_for_record(record),
        "speaker_attribution": transcript.speaker_attribution,
        "language": transcript.language,
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
            fact, fact_notes = intel.check_fact(raw, meeting_id, window_ids, segments, transcript.source_method,
                                                transcript.speaker_attribution)
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


def _status_line(record: dict, config: Optional[Dict[str, object]] = None) -> str:
    title = record.get("title") or "(untitled)"
    extra = ""
    activity = _activity(record, config) if config is not None else ""
    if activity:
        # A persistent indicator for as long as this computer is recording.
        extra += "  ● " + activity
    if record["state"] == mc.PROCESSING:
        processing = record["processing"]
        done = len(processing["completed"]) + len(processing["failed"])
        extra = "  extraction {}/{} window(s)".format(done, processing["windows"])
    if record.get("reason") and record["state"] in mc.FAILURE_STATES:
        extra += "  reason: " + record["reason"]
    if (record.get("reconcile") or {}).get("last_error"):
        extra += "  (last check failed: {}; will retry)".format(record["reconcile"]["last_error"])
    return "{}  {:<22} {:<8} {:<16} {:<18} {}{}".format(
        record["id"], record["state"], provider_for_record(record),
        mc.PLATFORM_LABELS.get(record["platform"], record["platform"]),
        scope_label(record["scope"]), title[:40], extra,
    )


def _next_step(record: dict) -> str:
    state = record["state"]
    if state == mc.PROCESSING:
        return ("Transcript ready. Extraction runs in your assistant: ask it to process meeting {id}, "
                "or read `agent-skills meeting inspect {id} --next-window`.").format(id=record["id"])
    if provider_for_record(record) == "desktop" and state == mc.RECORDING:
        return "RECORDING — stop with: agent-skills meeting stop {}".format(record["id"])
    if state in mc.PROVIDER_ACTIVE_STATES or state in (mc.ENDED, mc.MEDIA_READY):
        return "Check progress: agent-skills meeting status {}".format(record["id"])
    if state == mc.FAILED and record.get("reason") in mc.REFUSALS:
        return _refusal_hint(record)
    return ""


def _refusal_hint(record: dict) -> str:
    reason = record.get("reason")
    if reason == "not_enabled":
        return ("No transcript exists for this meeting. Next time switch on transcription, or use another "
                "provider. " + providers.alternatives(provider_for_record(record)))
    if reason == "external_tenant":
        return ("The transcript belongs to the other organisation. Use --via recall or --via desktop for "
                "meetings you don't host.")
    return providers.alternatives(provider_for_record(record))


def print_summary(record: dict) -> None:
    payload = _facts_for(record)
    facts = payload.get("facts", []) if payload else []
    out(intel.summarize(record, facts))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def _classify(url: str) -> tuple:
    try:
        return mc.classify_meeting_url(url)
    except mc.MeetingUrlError as exc:
        raise CliError(str(exc), EXIT_USAGE, "supported: Microsoft Teams, Google Meet, and Zoom meeting links") from None


def _refused(provider: str, refusal: mc.MeetingRefusal) -> CliError:
    """A typed refusal: say why and what else exists. Never switch providers."""
    return CliError("{} cannot capture this meeting [{}]: {}".format(provider, refusal.code, refusal.message),
                    EXIT_USAGE, providers.alternatives(provider))


def _show_notice_once(config: Dict[str, object], provider: str) -> None:
    """Existing users (and notice text changes) see the current notice without being blocked."""
    if providers.notice_current(config, provider):
        return
    out(providers.notice_text(config, provider))
    out("")
    providers.record_notice(config, provider, "shown on join", store.now_iso())
    store.save_config(config)


def _interactive() -> bool:
    """A person at a terminal. Tests replace this; no flag or variable skips it."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def _recall_consent(config: Dict[str, object], args: argparse.Namespace) -> None:
    if store.consent_current(config):
        return
    out(store.consent_text(config))
    if args.acknowledge_recording_notice:
        store.record_consent(config)
    elif _interactive():
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


def _active_duplicate(display_url: str, provider: str) -> Optional[str]:
    for meeting_id in store.list_meeting_ids():
        try:
            record = store.load_record(meeting_id)
        except store.StateError:
            continue
        if (provider_for_record(record) == provider and record.get("meeting_url_display") == display_url
                and record["state"] in mc.PROVIDER_ACTIVE_STATES):
            return meeting_id
    return None


def _desktop_attestation(config: Dict[str, object], meeting_id: str, url: str) -> dict:
    """The consent step for local recording. Only a person at a terminal can pass it."""
    if not _interactive():
        raise CliError(
            "local desktop recording can only be started by you, in an interactive terminal. Nothing was started.",
            EXIT_USAGE,
            "run it yourself in a terminal:\n    agent-skills meeting join {} --via desktop\n"
            "An assistant must not start a local recording; no one in the meeting is notified automatically.".format(
                url.split("?")[0]),
        )
    _show_notice_once(config, "desktop")
    desktop = _desktop_settings(config)
    announcement = " ".join(str(desktop.get("announcement") or "").split()) or (
        "I'm recording and transcribing this meeting locally for my engineering notes. Tell me if you object.")
    out("No one in this meeting will be notified automatically. Before recording:")
    out("  1. Tell everyone that you are recording and transcribing, for example by pasting")
    out("     this into the meeting chat:")
    out("")
    out("       " + announcement)
    out("")
    out("  2. Make sure every participant agrees. Recording people without their knowledge can be")
    out("     unlawful (e.g. §201 StGB in Germany); your organisation may require more.")
    out("")
    reply = input("Type 'everyone agreed' to start recording: ").strip().lower()
    if reply != "everyone agreed":
        raise CliError("consent not confirmed; nothing was recorded", EXIT_USAGE)
    return {"confirmed_at": store.now_iso(), "notice_version": providers.NOTICE_VERSIONS["desktop"],
            "announcement": announcement[:400], "by": "typed confirmation at an interactive terminal"}


def _capture_options(config: Dict[str, object], meeting_id: str, live: str,
                     ref: Optional[mc.MeetingRef] = None, attestation: Optional[dict] = None) -> mc.CaptureOptions:
    leave = config["automatic_leave"]
    return mc.CaptureOptions(
        bot_name=str(config["bot_name"]),
        chat_notice=str(config["chat_notice"]),
        live_method=live,
        retention_hours=int(config["media_retention_hours"]),  # type: ignore[arg-type]
        waiting_room_timeout=int(leave["waiting_room_timeout"]),  # type: ignore[index]
        noone_joined_timeout=int(leave["noone_joined_timeout"]),  # type: ignore[index]
        everyone_left_timeout=int(leave["everyone_left_timeout"]),  # type: ignore[index]
        correlation_id=meeting_id,
        ref=ref,
        attestation=attestation,
    )


def cmd_join(args: argparse.Namespace) -> int:
    config = store.load_config()
    via = getattr(args, "via", None)
    fetch_only = bool(getattr(args, "fetch_only", False))
    if fetch_only:
        via = "native"
    # Which provider, and is it ready: local checks only, before anything else.
    provider_id = choose_provider(config, via)
    # The link is checked before any provider call, so a bad one never reaches
    # a provider. Desktop only labels the meeting, so it accepts other platforms.
    platform, display = ("other", "") if provider_id == "desktop" else _classify(args.url)
    scope = resolve_scope(args.scope)
    meeting_id = store.new_meeting_id()

    if provider_id == "recall":
        _recall_consent(config, args)
        duplicate = _active_duplicate(display, "recall")
        if duplicate:
            raise CliError("a Recall bot is already active for this meeting ({}); no second bot was started".format(
                duplicate), EXIT_USAGE, "check it: agent-skills meeting status {}".format(duplicate))
        _show_notice_once(config, "recall")
        provider = build_provider(config, provider=provider_id)
        live = next((m for m in config["transcription_preference"] if m != "async"), "captions")  # type: ignore[union-attr]
        try:
            handle = provider.start(args.url.strip(), _capture_options(config, meeting_id, live))
        except mc.ProviderError as exc:
            raise provider_failure(exc) from None
        record = store.new_record(meeting_id, platform, display, args.title or "", scope, handle, live, config)
        record["capture_provider"] = provider_id
        store.save_record(record)
        out("Provider: recall. {} → joining ({})".format(config["bot_name"], mc.PLATFORM_LABELS[platform]))
        out("Meeting id: {}   Scope: {}".format(meeting_id, scope_label(scope)))
        out('The assistant will appear in the participant list as "{}".'.format(config["bot_name"]))
        out("Tell participants that recording and transcription are active.")
        out("Cost: " + providers.cost_line(config, "recall"))
        out("Data: " + providers.data_line("recall"))
    elif provider_id == "native":
        _show_notice_once(config, "native")
        provider = build_provider(config, provider=provider_id)
        try:
            ref = provider.resolve(args.url.strip())
            handle = provider.start(args.url.strip(), _capture_options(
                config, meeting_id, "post_meeting" if fetch_only else "native", ref=ref))
        except mc.MeetingRefusal as refusal:
            raise _refused("native", refusal) from None
        except mc.ProviderError as exc:
            raise provider_failure(exc) from None
        record = store.new_record(meeting_id, ref.platform, ref.display_url, args.title or "", scope, handle,
                                  "native", config, initial_state=mc.CREATED,
                                  initial_reason="waiting for the platform transcript")
        record["capture_provider"] = provider_id
        store.save_record(record)
        label = mc.PLATFORM_LABELS[ref.platform]
        out("Provider: native ({}). No bot will join.".format(label))
        out("Meeting id: {}   Scope: {}".format(meeting_id, scope_label(scope)))
        if not fetch_only and ref.has_ended is not True:
            out('→ Switch on "Start transcription" in the meeting. Participants will see {}\'s banner.'.format(label))
        out("Cost: " + providers.cost_line(config, "native"))
        out("Data: " + providers.data_line("native"))
    else:
        provider = build_provider(config, provider=provider_id)
        try:
            ref = provider.resolve(args.url.strip())
        except mc.MeetingRefusal as refusal:
            raise _refused("desktop", refusal) from None
        platform, display = ref.platform, ref.display_url
        attestation = _desktop_attestation(config, meeting_id, args.url.strip())
        try:
            handle = provider.start(args.url.strip(), _capture_options(
                config, meeting_id, "local_whisper", ref=ref, attestation=attestation))
        except mc.ProviderError as exc:
            raise provider_failure(exc) from None
        record = store.new_record(meeting_id, platform, display, args.title or "", scope, handle, "local_whisper",
                                  config, initial_state=mc.RECORDING, initial_reason="local recording started",
                                  attribution="channel")
        record["attestation"] = attestation
        record["capture_provider"] = provider_id
        store.save_record(record)
        out("Provider: desktop. Nothing joins the meeting; this computer is recording it.")
        out("RECORDING — stop with: agent-skills meeting stop {}".format(meeting_id))
        out("Meeting id: {}   Scope: {}".format(meeting_id, scope_label(scope)))
        out("Cost: " + providers.cost_line(config, "desktop"))
        out("Data: " + providers.data_line("desktop"))
    out("Extraction: " + providers.HOST_MODEL_NOTE)
    if scope.get("kind") != "repository":
        out("No repository scope: extracted facts will wait for review (inspect --accept --scope <repo>).")
    if provider_id == "native":
        if fetch_only:
            _reconcile_many([meeting_id], config, explicit=True)
            record = store.load_record(meeting_id)
            out(_status_line(record, config))
            if _next_step(record):
                out(_next_step(record))
            return EXIT_OK
        out("After the meeting, run: agent-skills meeting status {}   (transcripts can take a few minutes "
            "to appear)".format(meeting_id))
    elif provider_id == "recall":
        out("Check progress: agent-skills meeting status {}".format(meeting_id))
    return EXIT_OK


def cmd_fetch(args: argparse.Namespace) -> int:
    args.fetch_only = True
    args.via = "native"
    return cmd_join(args)


def _reconcile_many(ids: List[str], config: Dict[str, object], explicit: bool) -> int:
    built: Dict[str, Optional[mc.MeetingCaptureProvider]] = {}
    code = EXIT_OK
    for meeting_id in ids:
        try:
            record = store.load_record(meeting_id)
        except store.StateError as exc:
            err("{}: {}".format(meeting_id, exc))
            code = max(code, EXIT_STATE)
            continue
        kind = provider_for_record(record)
        if kind not in built and needs_provider(record, config):
            try:
                built[kind] = build_provider(config, provider=kind)
            except CliError as exc:
                built[kind] = None
                if explicit:
                    raise
                # Local work (retention, a pending commit) still runs below.
                err("{} provider unavailable: {}".format(kind, exc.message))
        try:
            reconcile(meeting_id, config, built.get(kind), honour_backoff=not explicit)
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


def print_providers(config: Dict[str, object], as_json: bool) -> int:
    """`status --providers`: what the host skill runs before any join."""
    rows = providers.status_rows(config)
    default = providers.default_provider(config)
    if as_json:
        out(json.dumps({"default_provider": default, "providers": rows,
                        "preflight": None if default else providers.preflight_text(config)}, sort_keys=True))
        return EXIT_OK
    if default is None:
        out(providers.preflight_text(config))
        out("")
    out("Capture providers (default: {}):".format(default or "none chosen"))
    for row in rows:
        out("  " + providers.status_line(row))
    return EXIT_OK


def cmd_status(args: argparse.Namespace) -> int:
    config = store.load_config()
    if args.providers:
        return print_providers(config, args.json)
    if args.listen:
        return run_listener(args.listen, config)
    ids = [store.resolve_meeting_id(args.id)] if args.id else store.list_meeting_ids()
    if not ids:
        if providers.default_provider(config) is None:
            out(providers.preflight_text(config))
            return EXIT_OK
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
        out(_status_line(record, config))
        if args.id and _next_step(record):
            out(_next_step(record))
    return code


def _activity(record: dict, config: Dict[str, object]) -> str:
    """The live line for work in progress on this machine (desktop recording or transcription)."""
    if provider_for_record(record) != "desktop" or record["state"] not in (mc.RECORDING, mc.ENDED, mc.MEDIA_READY):
        return ""
    if PROVIDER_FACTORY is not None:
        return ""
    try:
        return build_provider(config, provider="desktop").activity(mc.CaptureHandle.from_dict(record["handle"]))
    except (CliError, mc.ProviderError, OSError):
        return ""


def cmd_stop(args: argparse.Namespace) -> int:
    meeting_id = store.resolve_meeting_id(args.id)
    config = store.load_config()
    with store.meeting_lock(meeting_id):
        record = store.load_record(meeting_id)
        kind = provider_for_record(record)
        if record["state"] not in mc.PROVIDER_ACTIVE_STATES:
            out("{} is {}; nothing is capturing it any more.".format(meeting_id, record["state"]))
            return EXIT_OK
        if kind == "native":
            out("Nothing joined {}: the platform transcribes it, and the transcript is fetched after the "
                "meeting. Nothing to stop.".format(meeting_id))
            return EXIT_OK
        provider = build_provider(config, provider=kind)
        try:
            provider.stop(mc.CaptureHandle.from_dict(record["handle"]))
        except mc.ProviderError as exc:
            raise provider_failure(exc) from None
        record.setdefault("history", []).append({"at": store.now_iso(), "state": record["state"], "reason": "stop requested"})
        store.save_record(record)
    if kind != "desktop":
        out("Asked the assistant to leave {}. What was recorded so far will still be processed.".format(meeting_id))
        out("Check progress: agent-skills meeting status {}".format(meeting_id))
        return EXIT_OK
    out("Stopping the local recording of {} …".format(meeting_id))
    return _follow_desktop(meeting_id, config, provider, wait=not args.no_wait)


def _follow_desktop(meeting_id: str, config: Dict[str, object], provider: mc.MeetingCaptureProvider,
                    wait: bool, poll_seconds: float = 2.0) -> int:
    """Finalise → transcribe (with progress) → store; the transcript keeps going if this is interrupted."""
    last = ""
    while True:
        try:
            record = reconcile(meeting_id, config, provider)
        except mc.ProviderError as exc:
            raise provider_failure(exc) from None
        line = record.get("reason") or ""
        if line and line != last:
            out("  " + line)
            last = line
        if record["state"] not in (mc.RECORDING, mc.ENDED, mc.MEDIA_READY) or not wait:
            break
        time.sleep(poll_seconds)
    out(_status_line(record, config))
    if record["state"] in (mc.RECORDING, mc.ENDED, mc.MEDIA_READY):
        out("Transcription continues in the background. Check: agent-skills meeting status {}".format(meeting_id))
    elif _next_step(record):
        out(_next_step(record))
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
            out(_status_line(store.load_record(meeting_id), config))
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
    out(_status_line(record, config))
    kind = provider_for_record(record)
    out("  provider: {}   scope: {}   created: {}{}".format(
        kind, scope_label(record["scope"]), record["created_at"],
        "   bot: " + record["bot_name"] if kind == "recall" else ""))
    info = record["transcription"]
    out("  transcript: {} (speakers: {}; language: {}; partial: {})".format(
        info.get("final_method") or "not yet", info.get("speaker_attribution", "named"),
        info.get("language") or "-", info["partial"]))
    if record.get("attestation"):
        out("  consent: participants informed and agreed, confirmed {} (notice v{})".format(
            record["attestation"].get("confirmed_at", "?"), record["attestation"].get("notice_version", "?")))
    media = record["media"]
    if kind == "native":
        out("  platform transcript: stays with the platform under your organisation's retention; no media downloaded")
    else:
        out("  {}: {}".format(
            "provider media (retention {}h)".format(record["media_retention_hours"]) if kind == "recall"
            else "local raw audio",
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
        if provider_for_record(record) != "native":
            raise CliError("the meeting is still in progress; stop it and let it finish first", EXIT_USAGE)
    if not assume_yes:
        if not sys.stdin.isatty():
            raise CliError("purge deletes the captured media and the local transcript; pass --yes to confirm",
                           EXIT_USAGE)
        reply = input("Delete provider media and the local transcript for {}? Facts are kept. [y/N] ".format(
            meeting_id)).strip().lower()
        if reply not in ("y", "yes"):
            out("Cancelled.")
            return EXIT_OK
    code = EXIT_OK
    with store.meeting_lock(meeting_id):
        record = store.load_record(meeting_id)
        if not record["media"].get("deleted_at") and provider_for_record(record) != "native":
            try:
                build_provider(config, provider=provider_for_record(record)).delete_media(
                    mc.CaptureHandle.from_dict(record["handle"]))
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
    kind = provider_for_record(record)
    if kind == "native":
        out("The platform's own transcript is untouched; it follows your organisation's retention policy.")
    elif kind == "desktop" and code == EXIT_OK:
        out("Local raw audio deleted.")
    elif code == EXIT_OK:
        out("Provider media deleted. Recall may still keep bot metadata and logs for a limited period;"
            " see docs/meeting-intelligence/PRIVACY.md.")
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
    """Local by default. `probe` (doctor --probe-meeting) may contact Recall once and,
    for desktop, record one second from the loopback input only (never the microphone)."""
    report: Dict[str, object] = {}
    try:
        config = store.load_config()
    except store.ConfigError as exc:
        return {"config": "invalid: {}".format(exc)}
    rows = providers.status_rows(config)
    report["providers"] = {row["provider"]: providers.status_line(row) for row in rows}
    report["default_provider"] = providers.default_provider(config) or "none"
    ready_default = any(row["default"] and row["state"] == mc.READY for row in rows)
    report["capture"] = "ready" if ready_default else (
        "not set up (run: agent-skills meeting setup --compare)" if report["default_provider"] == "none"
        else "default provider not ready")
    # The Recall keys keep their 1.2.0 names and meanings for scripts that read them.
    report["consent"] = "acknowledged" if store.consent_current(config) else "not yet acknowledged"
    report["listener"] = (
        "configured (run: agent-skills meeting status --listen 127.0.0.1:<port>)"
        if config.get("listener_url") else "not configured (polling only)"
    )
    recall_row = next(row for row in rows if row["provider"] == "recall")
    report["credentials"] = "api key resolves" if recall_row["state"] == mc.READY or (
        "region" in recall_row["reason"]) else "api key missing"
    report["region"] = ("MISMATCH: " + recall_row["reason"]) if "mismatch" in recall_row["reason"] else (
        recall_row["detail"].replace("region ", "") if recall_row["state"] == mc.READY else "not configured")
    stuck = []
    unreadable = 0
    for meeting_id in store.list_meeting_ids():
        try:
            record = store.load_record(meeting_id)
        except store.StateError:
            unreadable += 1
            continue
        updated = store.parse_iso(record.get("updated_at", ""))
        if not store.is_terminal(record) and updated and provider_for_record(record) != "native" and (
            datetime.now(timezone.utc) - updated
        ).total_seconds() > STUCK_AFTER_HOURS * 3600:
            stuck.append("{} ({})".format(meeting_id, record["state"]))
    report["meetings"] = len(store.list_meeting_ids())
    report["stuck"] = stuck
    report["unreadable"] = unreadable
    report["provider"] = "not probed (doctor stays offline; use doctor --probe-meeting)"
    if probe:
        probes = []
        if recall_row["state"] == mc.READY:
            try:
                provider = build_provider(config, provider="recall")
                getattr(provider, "probe")()
                probes.append("recall: reachable; key and region accepted")
            except CliError as exc:
                probes.append("recall: not probed: " + exc.message)
            except mc.ProviderError as exc:
                probes.append("recall: FAILED: " + exc.message)
        desktop_row = next(row for row in rows if row["provider"] == "desktop")
        if desktop_row["state"] != mc.NOT_CONFIGURED:
            probes.append("desktop: " + providers.probe_desktop_loopback(config))
        report["provider"] = "; ".join(probes) or "nothing to probe (no provider configured)"
    return report


def cmd_doctor(args: argparse.Namespace) -> int:
    report = doctor_report(args.probe)
    if args.json:
        out(json.dumps(report, sort_keys=True))
        return EXIT_OK
    out("  default provider: {}".format(report.get("default_provider", "none")))
    for line in (report.get("providers") or {}).values():  # type: ignore[union-attr]
        out("  " + line)
    out("  probe: {}".format(report.get("provider", "")))
    stuck = report.get("stuck") or []
    out("  meetings: {} total; {} stuck{}{}".format(
        report.get("meetings", 0), len(stuck),  # type: ignore[arg-type]
        (" — " + ", ".join(stuck)) if stuck else "",  # type: ignore[arg-type]
        "; {} unreadable".format(report["unreadable"]) if report.get("unreadable") else ""))
    return EXIT_OK


def cmd_setup(args: argparse.Namespace) -> int:
    import meeting_setup

    return meeting_setup.run(args)


# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-skills meeting", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True,
                                metavar="{setup,join,fetch,status,stop,list,inspect}")

    sp = sub.add_parser("setup", help="Choose and set up how meetings are captured (guided, re-runnable).")
    sp.add_argument("provider", nargs="?", choices=providers.PROVIDERS)
    sp.add_argument("--compare", action="store_true", help="show the three providers side by side")
    sp.add_argument("--import", dest="import_file", default=None,
                    help="native: an admin's non-secret app-registration config (JSON)")
    sp.add_argument("--platform", default=None, choices=mc.PLATFORMS, help="native: set up one platform")
    sp.add_argument("--region", default=None, help="recall: the region to use")
    sp.add_argument("--model", default=None, help="desktop: the whisper.cpp model to use")
    sp.add_argument("--language", default=None, help="desktop: transcription language (auto, de, en, ...)")
    sp.add_argument("--no-default", action="store_true", help="set up without making it the default")
    sp.set_defaults(func=cmd_setup)

    sp = sub.add_parser("join", help="Capture a meeting with the chosen provider.")
    sp.add_argument("url")
    sp.add_argument("--via", default=None, choices=providers.PROVIDERS,
                    help="use this provider for this meeting instead of the default")
    sp.add_argument("--scope", default=None, help="repo:<path> (default: this repository); 'none' for unscoped")
    sp.add_argument("--title", default="")
    sp.add_argument("--acknowledge-recording-notice", action="store_true",
                    help="recall: record the user's explicit acknowledgement of the one-time notice")
    sp.set_defaults(func=cmd_join)

    sp = sub.add_parser("fetch", help="native: fetch the platform transcript of a meeting that already ended.")
    sp.add_argument("url")
    sp.add_argument("--scope", default=None)
    sp.add_argument("--title", default="")
    sp.set_defaults(func=cmd_fetch, acknowledge_recording_notice=False)

    sp = sub.add_parser("status", help="Reconcile and show meetings; --providers shows capture readiness.")
    sp.add_argument("--providers", action="store_true", help="each provider: ready / not configured / broken")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("id", nargs="?")
    sp.add_argument("--wait", action="store_true", help="poll until the recording is transcribed")
    sp.add_argument("--interval", type=int, default=30)
    sp.add_argument("--timeout", type=int, default=4 * 3600)
    sp.add_argument("--listen", default="", help="optional webhook listener on loopback host:port")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("stop", help="Stop capturing; what was recorded is processed.")
    sp.add_argument("id")
    sp.add_argument("--no-wait", action="store_true", help="desktop: do not follow local transcription")
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
        if exc.plain:
            out(exc.message)
        else:
            err("agent-skills meeting: {}".format(redact(exc.message)))
        if exc.hint:
            err("  " + exc.hint.replace("\n", "\n  "))
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
