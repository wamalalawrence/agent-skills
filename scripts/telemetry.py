#!/usr/bin/env python3
"""Append-only telemetry log for agent-skills.

Telemetry exists so that "the brain is improving" stops being a feeling and
becomes a number. Each event is one JSON object on one line (NDJSON) under the
project's cache, with no PII, no secrets, and no free-form messages — only a
fixed event name plus a small structured payload.

Storage:
  <cache-root>/_projects/<slug>/telemetry.ndjson

Subcommands:
  emit  <project> <event> [--field K=V ...]    Append one event.
  report <project> [--since ISO]               Print a per-skill summary.
  report --all [--since ISO]                   Aggregate across all projects.

Recognised event names (others are accepted but flagged in reports):
  invoked, loop_round, handoff, finding, stopped, completed,
  artifact, outcome

Recognised performance fields, all optional. They exist so "the skills got
faster" can be checked rather than asserted, and so the thing being checked is
the right one. Total runtime is the wrong measure: a faster wrong answer is a
regression. What matters is *time to verified useful result*, which is why the
two duration fields below are anchored to the first useful artifact and to the
point a result was verified, not to when the process exited.

  profile               LIGHT | STANDARD | RIGOROUS
  first_artifact_minutes  minutes until the first useful artifact was written
  verified_minutes        minutes until the result was verified
  dispatches              fresh-context agents opened for this task
  context_loads           full context reloads paid
  review_rounds           independent review rounds run
  parallel_used           true when work ran concurrently
  no_output               true when the run produced no artifact at all

Everything stays in the local project cache. Nothing is transmitted anywhere,
and no repository or task content is recorded — only counters and enums.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from cache_root import default_cache_root
from guard_audit import redact

KNOWN_EVENTS = {
    "invoked",
    "loop_round",
    "handoff",
    "finding",
    "stopped",
    "completed",
    "artifact",
    "outcome",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip("-").lower()
    return s or "project"


def resolve_cache_root(explicit: str | None) -> Path:
    # One resolution order for every helper and both wrappers; see cache_root.py.
    return default_cache_root(explicit)


def telemetry_path(cache_root: Path, project: str) -> Path:
    return cache_root / "_projects" / slugify(project) / "telemetry.ndjson"


def emit(cache_root: Path, project: str, event: str, fields: dict) -> Path:
    path = telemetry_path(cache_root, project)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"at": now_iso(), "project": project, "event": event}
    # Counters and enums are the intended content and nothing here should ever
    # be free-form. `--field` accepts arbitrary text, though, so the string
    # values are redacted rather than trusted: this log is append-only, so a
    # value written by mistake cannot be edited out afterwards.
    payload.update(
        {key: redact(value) if isinstance(value, str) else value for key, value in fields.items()}
    )
    with path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload, separators=(",", ":")) + "\n")
    return path


def read_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def filter_since(events: list[dict], since: str | None) -> list[dict]:
    if not since:
        return events
    threshold = datetime.fromisoformat(since.replace("Z", "+00:00"))
    out = []
    for ev in events:
        at = ev.get("at", "")
        try:
            ts = datetime.fromisoformat(at.replace("Z", "+00:00"))
        except ValueError:
            continue
        if ts >= threshold:
            out.append(ev)
    return out


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return round(ordered[middle], 1)
    return round((ordered[middle - 1] + ordered[middle]) / 2, 1)


def performance(events: list[dict]) -> dict:
    """Aggregate the optional performance fields.

    Median rather than mean throughout: one pathological run — the hour that
    produced nothing — would drag a mean far enough to hide what the typical
    run costs, and the typical run is the thing a change is trying to move.

    Only what was actually emitted is counted. A field nobody sets reports
    `null` rather than `0`, because "no data" and "zero" answer different
    questions and conflating them is how a counter starts looking like evidence.
    """
    first_artifact: list[float] = []
    verified: list[float] = []
    totals = {
        "dispatches": 0,
        "context_loads": 0,
        "review_rounds": 0,
        "parallel_runs": 0,
        "no_output_runs": 0,
    }
    profiles: dict[str, int] = defaultdict(int)
    runs = 0

    for ev in events:
        if ev.get("event") in {"completed", "stopped"}:
            runs += 1
        profile = ev.get("profile")
        if isinstance(profile, str) and profile:
            profiles[profile] += 1
        for key, target in (
            ("first_artifact_minutes", first_artifact),
            ("verified_minutes", verified),
        ):
            value = ev.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                target.append(float(value))
        for key in ("dispatches", "context_loads", "review_rounds"):
            value = ev.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                totals[key] += value
        if ev.get("parallel_used") is True:
            totals["parallel_runs"] += 1
        if ev.get("no_output") is True:
            totals["no_output_runs"] += 1

    return {
        "runs": runs,
        "median_minutes_to_first_artifact": _median(first_artifact),
        "median_minutes_to_verified_result": _median(verified),
        "profiles": dict(profiles),
        **totals,
        "dispatches_per_run": round(totals["dispatches"] / runs, 2) if runs else None,
        "context_loads_per_run": round(totals["context_loads"] / runs, 2) if runs else None,
    }


def summarise(events: list[dict]) -> dict:
    by_skill: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    unknown_events: dict[str, int] = defaultdict(int)
    for ev in events:
        name = ev.get("event", "")
        skill = ev.get("skill", "<unknown>")
        by_skill[skill][name] += 1
        if name not in KNOWN_EVENTS:
            unknown_events[name] += 1
    return {
        "total_events": len(events),
        "skills": {k: dict(v) for k, v in by_skill.items()},
        "unknown_events": dict(unknown_events),
        "performance": performance(events),
    }


def parse_fields(pairs: list[str]) -> dict:
    out: dict[str, object] = {}
    for raw in pairs:
        if "=" not in raw:
            raise SystemExit(f"FAIL --field expects K=V, got {raw!r}")
        key, _, value = raw.partition("=")
        key = key.strip()
        value = value.strip()
        if value.isdigit():
            out[key] = int(value)
        elif value.lower() in {"true", "false"}:
            out[key] = value.lower() == "true"
        else:
            out[key] = value
    return out


def cmd_emit(args: argparse.Namespace) -> int:
    fields = parse_fields(args.field or [])
    path = emit(resolve_cache_root(args.cache_root), args.project, args.event, fields)
    print(path)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    cache_root = resolve_cache_root(args.cache_root)
    if args.all:
        projects_root = cache_root / "_projects"
        events: list[dict] = []
        if projects_root.exists():
            for child in sorted(projects_root.iterdir()):
                events.extend(read_events(child / "telemetry.ndjson"))
    else:
        if not args.project:
            raise SystemExit("FAIL provide <project> or --all")
        events = read_events(telemetry_path(cache_root, args.project))
    events = filter_since(events, args.since)
    print(json.dumps(summarise(events), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-root", default=None)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("emit")
    sp.add_argument("project")
    sp.add_argument("event")
    sp.add_argument("--field", action="append", default=[])
    sp.set_defaults(func=cmd_emit)

    sp = sub.add_parser("report")
    sp.add_argument("project", nargs="?", default=None)
    sp.add_argument("--all", action="store_true")
    sp.add_argument("--since", default=None)
    sp.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
