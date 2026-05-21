#!/usr/bin/env python3
"""Rule-promotion helper.

Scans every project's `memory.md` under the cache root for bullets that recur
across at least `--min-projects` projects and prints a suggestion list: each
suggestion is a candidate to promote into org memory (so every future task on
every project sees it on read) and/or to lift into a skill's pre-implementation
checklist.

This script never edits skill files. It only proposes. Promotion to org
memory must be done explicitly via `scripts/org-memory.py promote ...`. Skill
edits must be done by a human maintainer.

Usage:
  python3 scripts/promote-rules.py [--min-projects N] [--section S]

Output: JSON list of candidate dicts:
  {
    "payload": "<normalised bullet text>",
    "projects": ["proj-a", "proj-b"],
    "samples": {"proj-a": "<raw bullet>", "proj-b": "..."}
  }
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

DEFAULT_SECTION = "Common gotchas"
_BULLET_RE = re.compile(r"^- (?:\([^)]+\)\s+)?(.*?)\s*$")


def resolve_cache_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    env = os.environ.get("AGENT_SKILLS_CACHE_DIR")
    if env:
        return Path(env).resolve()
    base = os.environ.get("WORKSPACE_ROOT") or os.getcwd()
    return (Path(base) / ".cache" / "agent-skills").resolve()


def collect_section_bullets(memory_md: Path, section: str) -> list[tuple[str, str]]:
    if not memory_md.exists():
        return []
    out: list[tuple[str, str]] = []
    in_section = False
    for line in memory_md.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            in_section = line[3:].strip() == section
            continue
        if not in_section or not line.startswith("- ") or line.startswith("- _empty"):
            continue
        m = _BULLET_RE.match(line)
        payload = (m.group(1) if m else line).strip().lower()
        out.append((payload, line.strip()))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-root", default=None)
    parser.add_argument("--section", default=DEFAULT_SECTION)
    parser.add_argument("--min-projects", type=int, default=2)
    args = parser.parse_args(argv)

    cache_root = resolve_cache_root(args.cache_root)
    projects_root = cache_root / "_projects"
    if not projects_root.exists():
        print("-- no projects under cache root yet", file=sys.stderr)
        return 1

    payload_to_projects: dict[str, set[str]] = defaultdict(set)
    payload_to_samples: dict[str, dict[str, str]] = defaultdict(dict)

    for child in sorted(projects_root.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        memory = child / "memory.md"
        for payload, raw in collect_section_bullets(memory, args.section):
            payload_to_projects[payload].add(child.name)
            payload_to_samples[payload].setdefault(child.name, raw)

    candidates = []
    for payload, projects in payload_to_projects.items():
        if len(projects) >= args.min_projects:
            candidates.append(
                {
                    "payload": payload,
                    "projects": sorted(projects),
                    "samples": payload_to_samples[payload],
                }
            )
    candidates.sort(key=lambda c: (-len(c["projects"]), c["payload"]))
    print(json.dumps(candidates, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
