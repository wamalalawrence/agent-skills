#!/usr/bin/env python3
"""Outcome recorder for agent-skills tasks.

This closes the self-improving loop. After a PR's fate is known, this script
takes the per-task evidence (project, issue key, blackboard, contributing
skill versions) plus the outcome (`merged`, `reverted`, `hotfixed`, `blocked`,
`abandoned`) and writes:

  1. A bullet to the project's `memory.md` under "Outcomes".
  2. A telemetry event (`outcome`) carrying the structured payload.
  3. (For non-success outcomes) a `Lesson` line in project memory under
     "Common gotchas" so the next task on the same project sees it on read.
  4. (When --promote-to-org is set with --confirmed-in N>=2) a copy into org
     memory under "Outcomes" with provenance attribution.

It does **not** open issues, push code, or run git. Callers feed the outcome.

Subcommands:
  record --project P --issue K --outcome O --skills S=v[,S=v...]
         [--summary "one-line"] [--blast-radius N] [--lesson "text"]
         [--promote-to-org --confirmed-in N]

  list   --project P [--since ISO]
                              Print recent outcomes for one project.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

OUTCOME_VALUES = {"merged", "reverted", "hotfixed", "blocked", "abandoned"}
NEGATIVE = {"reverted", "hotfixed"}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip("-").lower()
    return s or "project"


SCRIPT_DIR = Path(__file__).resolve().parent


def call_project_memory(project: str, section: str, text: str, cache_root: str | None) -> None:
    args = [sys.executable, str(SCRIPT_DIR / "project-memory.py")]
    if cache_root:
        args += ["--cache-root", cache_root]
    args += ["note", project, "--section", section, "--text", text]
    subprocess.run(args, check=True)


def call_telemetry(project: str, fields: list[str], cache_root: str | None) -> None:
    args = [sys.executable, str(SCRIPT_DIR / "telemetry.py")]
    if cache_root:
        args += ["--cache-root", cache_root]
    args += ["emit", project, "outcome"]
    for f in fields:
        args += ["--field", f]
    subprocess.run(args, check=True)


def call_org_promote(
    project: str, section: str, text: str, cache_root: str | None
) -> None:
    args = [sys.executable, str(SCRIPT_DIR / "org-memory.py")]
    if cache_root:
        args += ["--cache-root", cache_root]
    args += [
        "promote",
        "--from",
        project,
        "--section",
        section,
        "--text",
        text,
    ]
    subprocess.run(args, check=True)


def parse_skills(spec: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise SystemExit(f"FAIL --skills entry must be name=version, got {part!r}")
        name, _, version = part.partition("=")
        out[name.strip()] = version.strip()
    return out


def cmd_record(args: argparse.Namespace) -> int:
    if args.outcome not in OUTCOME_VALUES:
        raise SystemExit(f"FAIL --outcome must be one of {sorted(OUTCOME_VALUES)}")
    skills = parse_skills(args.skills)
    summary = args.summary or "(no summary supplied)"
    skills_str = ", ".join(f"{k}@{v}" for k, v in sorted(skills.items())) or "(none)"
    bullet = (
        f"{args.issue} -> {args.outcome}; "
        f"summary: {summary}; skills: {skills_str}"
    )
    call_project_memory(args.project, "Outcomes", bullet, args.cache_root)

    fields = [
        f"issue={args.issue}",
        f"outcome={args.outcome}",
        f"skills={skills_str.replace(' ', '')}",
    ]
    if args.blast_radius is not None:
        fields.append(f"blast_radius={args.blast_radius}")
    call_telemetry(args.project, fields, args.cache_root)

    if args.outcome in NEGATIVE:
        lesson = args.lesson or (
            f"Outcome {args.outcome} on {args.issue}: review {skills_str} "
            f"contracts; add eval if missing."
        )
        call_project_memory(args.project, "Common gotchas", lesson, args.cache_root)

    if args.promote_to_org:
        if args.confirmed_in is None or args.confirmed_in < 2:
            raise SystemExit(
                "FAIL --promote-to-org requires --confirmed-in N where N >= 2"
            )
        call_org_promote(
            args.project,
            "Outcomes",
            f"{args.outcome} pattern observed in {args.confirmed_in} projects: {summary}",
            args.cache_root,
        )

    print(
        json.dumps(
            {
                "recorded_at": now_iso(),
                "project": args.project,
                "issue": args.issue,
                "outcome": args.outcome,
                "skills": skills,
                "lesson_written": args.outcome in NEGATIVE,
                "org_promoted": bool(args.promote_to_org),
            },
            indent=2,
        )
    )
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    base = args.cache_root or os.environ.get("AGENT_SKILLS_CACHE_DIR")
    if not base:
        base = str(Path(os.environ.get("WORKSPACE_ROOT") or os.getcwd()) / ".cache" / "agent-skills")
    md = Path(base) / "_projects" / slugify(args.project) / "memory.md"
    if not md.exists():
        print(f"-- no memory yet at {md}", file=sys.stderr)
        return 1
    text = md.read_text(encoding="utf-8")
    in_section = False
    for line in text.splitlines():
        if line.strip().startswith("## "):
            in_section = line.strip() == "## Outcomes"
            continue
        if in_section and line.startswith("- "):
            print(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-root", default=None)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("record")
    sp.add_argument("--project", required=True)
    sp.add_argument("--issue", required=True)
    sp.add_argument("--outcome", required=True)
    sp.add_argument(
        "--skills",
        required=True,
        help="Comma-separated name=version pairs, e.g. software-engineer=0.31.0,code-reviewer=0.31.0",
    )
    sp.add_argument("--summary", default=None)
    sp.add_argument("--blast-radius", type=int, default=None)
    sp.add_argument("--lesson", default=None)
    sp.add_argument("--promote-to-org", action="store_true")
    sp.add_argument("--confirmed-in", type=int, default=None)
    sp.set_defaults(func=cmd_record)

    sp = sub.add_parser("list")
    sp.add_argument("--project", required=True)
    sp.add_argument("--since", default=None)
    sp.set_defaults(func=cmd_list)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
