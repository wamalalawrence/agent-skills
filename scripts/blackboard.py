#!/usr/bin/env python3
"""Per-task shared blackboard for agent-skills.

The blackboard is the single canonical working-memory file for one task. Every
skill that runs in service of a task reads and appends to it, so handoffs
between skills are not lossy re-derivations. It is per-task scratch (lives
under `<issue-key>/blackboard.json`) and is cleaned up by
`scripts/project-memory.py cleanup-task <issue-key>` alongside the rest of the
per-task evidence pack.

Shape (JSON):
  {
    "issue_key": "ABC-123",
    "project": "acme-checkout",
    "created_at": "...",
    "updated_at": "...",
    "skill_versions": {"software-engineer": "0.31.0", ...},
    "facts":        [ {at, by, text}, ... ],
    "assumptions":  [ {at, by, text}, ... ],
    "unknowns":     [ {at, by, text}, ... ],
    "decisions":    [ {at, by, text}, ... ],
    "artifacts":    [ {at, by, path, kind, note}, ... ],
    "handoffs":     [ {at, from, to, reason}, ... ],
    "progress":     [ {at, by, kind, note}, ... ]
  }

Subcommands:
  path  <issue-key>                           Print blackboard path.
  init  <issue-key> --project P [--skill name=ver ...]
                                              Create or refresh.
  read  <issue-key> [--section S]             Print whole blackboard or one
                                              section as JSON.
  append <issue-key> --section S --by SKILL --text T
                                              Add a bullet to facts /
                                              assumptions / unknowns /
                                              decisions.
  artifact <issue-key> --by SKILL --path P --kind K [--note N]
                                              Record an artifact reference.
  progress <issue-key> --by SKILL --kind K [--note N]
                                              Record a meaningful milestone so
                                              an interrupted run is recoverable
                                              and the watchdog can see motion.
  handoff <issue-key> --from SKILL --to SKILL --reason R
                                              Record a skill -> skill handoff.
  record-skill <issue-key> --name N --version V
                                              Pin the version of a skill that
                                              participated in this task.

Rules:
  * The blackboard is always under `<cache-root>/<issue-key>/` so the existing
    cleanup contract handles it. `<issue-key>` must not start with `_`.
  * This script writes only to `<cache-root>/<issue-key>/blackboard.json`. It
    never writes to `_projects/` or `_org/`.
  * Every free-text value written here is redacted first. The blackboard is the
    file skills paste tool output into, which makes it the most likely place for
    a credential to come to rest, and it is read back into the next agent's
    context by design. See `docs/secret-boundary.md`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# One redaction implementation for the whole project, in guard_audit. A second
# pattern set would drift from the first and the weaker one would decide.
from guard_audit import redact

SECTIONS = ("facts", "assumptions", "unknowns", "decisions")

# What counts as meaningful progress. Deliberately short: the ledger is a record
# of milestones a human would recognise as movement, not a keystroke log. A
# checkpoint every few seconds is noise that hides the stall it was meant to
# reveal.
PROGRESS_KINDS = (
    "artifact",    # something durable was written or updated
    "hypothesis",  # a candidate explanation was recorded
    "query",       # a query or probe completed and returned something
    "test",        # a test or check was executed
    "file",        # a source file was changed
    "evidence",    # evidence was captured
    "checkpoint",  # an explicit resumable checkpoint
)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_cache_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    env = os.environ.get("AGENT_SKILLS_CACHE_DIR")
    if env:
        return Path(env).resolve()
    base = os.environ.get("WORKSPACE_ROOT") or os.getcwd()
    return (Path(base) / ".cache" / "agent-skills").resolve()


def check_issue_key(issue_key: str) -> None:
    if issue_key.startswith("_") or "/" in issue_key or ".." in issue_key:
        raise SystemExit(f"FAIL refusing unsafe issue key: {issue_key!r}")


def blackboard_path(cache_root: Path, issue_key: str) -> Path:
    check_issue_key(issue_key)
    return cache_root / issue_key / "blackboard.json"


def load(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"FAIL blackboard missing: {path}; run 'init' first")
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = now_iso()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def cmd_path(args: argparse.Namespace) -> int:
    print(blackboard_path(resolve_cache_root(args.cache_root), args.issue_key))
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    path = blackboard_path(resolve_cache_root(args.cache_root), args.issue_key)
    if path.exists():
        data = load(path)
    else:
        data = {
            "issue_key": args.issue_key,
            "project": args.project,
            "created_at": now_iso(),
            "skill_versions": {},
            "facts": [],
            "assumptions": [],
            "unknowns": [],
            "decisions": [],
            "artifacts": [],
            "handoffs": [],
            "progress": [],
        }
    for pair in args.skill or []:
        if "=" not in pair:
            raise SystemExit(f"FAIL --skill expects name=version, got {pair!r}")
        name, _, version = pair.partition("=")
        data.setdefault("skill_versions", {})[name.strip()] = version.strip()
    if args.project:
        data["project"] = args.project
    save(path, data)
    print(path)
    return 0


def cmd_read(args: argparse.Namespace) -> int:
    path = blackboard_path(resolve_cache_root(args.cache_root), args.issue_key)
    data = load(path)
    if args.section:
        print(json.dumps(data.get(args.section, []), indent=2))
    else:
        print(json.dumps(data, indent=2))
    return 0


def cmd_append(args: argparse.Namespace) -> int:
    if args.section not in SECTIONS:
        raise SystemExit(f"FAIL --section must be one of {SECTIONS}")
    path = blackboard_path(resolve_cache_root(args.cache_root), args.issue_key)
    data = load(path)
    data.setdefault(args.section, []).append(
        {"at": now_iso(), "by": args.by, "text": redact(args.text.strip())}
    )
    save(path, data)
    return 0


def cmd_artifact(args: argparse.Namespace) -> int:
    path = blackboard_path(resolve_cache_root(args.cache_root), args.issue_key)
    data = load(path)
    data.setdefault("artifacts", []).append(
        {
            "at": now_iso(),
            "by": args.by,
            # A path can carry a credential too — a signed URL keeps its
            # signature in the query string.
            "path": redact(args.path),
            "kind": args.kind,
            "note": redact(args.note or ""),
        }
    )
    save(path, data)
    return 0


def cmd_progress(args: argparse.Namespace) -> int:
    """Record one milestone.

    This exists because a long execution used to leave nothing behind. A
    mechanism-selection dispatch ran for roughly an hour, was terminated, and
    had written no artifact at all — so the retry restarted from zero and the
    hour bought nothing. The ledger makes partial work recoverable and gives
    `agent-skills watchdog` something to measure other than elapsed time.
    """
    if args.kind not in PROGRESS_KINDS:
        raise SystemExit(f"FAIL --kind must be one of {PROGRESS_KINDS}")
    path = blackboard_path(resolve_cache_root(args.cache_root), args.issue_key)
    data = load(path)
    data.setdefault("progress", []).append(
        {
            "at": now_iso(),
            "by": args.by,
            "kind": args.kind,
            "note": redact((args.note or "").strip()),
        }
    )
    save(path, data)
    return 0


def cmd_handoff(args: argparse.Namespace) -> int:
    path = blackboard_path(resolve_cache_root(args.cache_root), args.issue_key)
    data = load(path)
    data.setdefault("handoffs", []).append(
        {
            "at": now_iso(),
            "from": args.from_skill,
            "to": args.to_skill,
            "reason": redact(args.reason),
        }
    )
    save(path, data)
    return 0


def cmd_record_skill(args: argparse.Namespace) -> int:
    path = blackboard_path(resolve_cache_root(args.cache_root), args.issue_key)
    data = load(path)
    data.setdefault("skill_versions", {})[args.name] = args.version
    save(path, data)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-root", default=None)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("path")
    sp.add_argument("issue_key")
    sp.set_defaults(func=cmd_path)

    sp = sub.add_parser("init")
    sp.add_argument("issue_key")
    sp.add_argument("--project", default=None)
    sp.add_argument("--skill", action="append", default=[])
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("read")
    sp.add_argument("issue_key")
    sp.add_argument("--section", default=None)
    sp.set_defaults(func=cmd_read)

    sp = sub.add_parser("append")
    sp.add_argument("issue_key")
    sp.add_argument("--section", required=True)
    sp.add_argument("--by", required=True)
    sp.add_argument("--text", required=True)
    sp.set_defaults(func=cmd_append)

    sp = sub.add_parser("artifact")
    sp.add_argument("issue_key")
    sp.add_argument("--by", required=True)
    sp.add_argument("--path", required=True)
    sp.add_argument("--kind", required=True)
    sp.add_argument("--note", default=None)
    sp.set_defaults(func=cmd_artifact)

    sp = sub.add_parser("progress")
    sp.add_argument("issue_key")
    sp.add_argument("--by", required=True)
    sp.add_argument("--kind", required=True, choices=PROGRESS_KINDS)
    sp.add_argument("--note", default=None)
    sp.set_defaults(func=cmd_progress)

    sp = sub.add_parser("handoff")
    sp.add_argument("issue_key")
    sp.add_argument("--from", dest="from_skill", required=True)
    sp.add_argument("--to", dest="to_skill", required=True)
    sp.add_argument("--reason", required=True)
    sp.set_defaults(func=cmd_handoff)

    sp = sub.add_parser("record-skill")
    sp.add_argument("issue_key")
    sp.add_argument("--name", required=True)
    sp.add_argument("--version", required=True)
    sp.set_defaults(func=cmd_record_skill)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
