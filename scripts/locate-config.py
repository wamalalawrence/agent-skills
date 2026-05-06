#!/usr/bin/env python3
"""Locate agent-skills configuration files (.env, .env.local, .jira-config.yml,
.agent-skills.yml) across the documented discovery surfaces.

Why this exists: agents repeatedly tell users "I can't find .env / .jira-config.yml"
when the file is one or two directories away from the cwd, or living next to the
.skills symlink. This script walks every documented location once, deterministically,
without printing secrets.

Discovery order (first hit wins per file kind):
  1. Explicit path passed via --workspace-root (or WORKSPACE_ROOT env var)
  2. The cwd, and every parent directory up to the filesystem root or a .git
     boundary that is **not** the workspace root (we keep walking past the repo
     root because setup.init places .env in the *parent* workspace folder)
  3. The directory holding the resolved target of a `.skills` symlink, if one is
     found in the walked tree (this is exactly where setup.init writes .env)
  4. Sibling repositories' parent directory inferred from the cwd

Exit codes:
  0  every requested file was found
  1  at least one requested file is missing (paths searched are listed)
  2  setup error (bad arguments, unreadable directory)

The script never reads file contents. It only reports paths and existence.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Iterable

CONFIG_FILES = (
    ".env",
    ".env.local",
    ".jira-config.yml",
    ".agent-skills.yml",
)


def walk_up(start: Path) -> Iterable[Path]:
    """Yield `start` and every parent up to the filesystem root."""
    current = start.resolve()
    seen: set[Path] = set()
    while current not in seen:
        seen.add(current)
        yield current
        if current.parent == current:
            break
        current = current.parent


def find_skills_symlink_dir(roots: Iterable[Path]) -> Path | None:
    """Return the parent directory of any `.skills` symlink found in `roots`."""
    for root in roots:
        candidate = root / ".skills"
        if candidate.is_symlink() or candidate.exists():
            return root
    return None


def discover(workspace_root: Path | None, cwd: Path) -> dict:
    """Return a structured discovery report (no file contents read)."""
    searched: list[str] = []
    found: dict[str, str | None] = {name: None for name in CONFIG_FILES}

    candidates: list[Path] = []
    if workspace_root is not None:
        candidates.append(workspace_root)
    for parent in walk_up(cwd):
        candidates.append(parent)
    skills_dir = find_skills_symlink_dir(candidates)
    if skills_dir is not None and skills_dir not in candidates:
        candidates.append(skills_dir)

    # De-duplicate while preserving order.
    seen: set[Path] = set()
    ordered: list[Path] = []
    for c in candidates:
        try:
            r = c.resolve()
        except OSError:
            continue
        if r in seen or not r.is_dir():
            continue
        seen.add(r)
        ordered.append(r)

    for directory in ordered:
        searched.append(str(directory))
        for name in CONFIG_FILES:
            if found[name] is not None:
                continue
            candidate = directory / name
            if candidate.is_file():
                found[name] = str(candidate)

    workspace = workspace_root
    if workspace is None and found[".env"]:
        workspace = Path(found[".env"]).parent
    if workspace is None and found[".agent-skills.yml"]:
        workspace = Path(found[".agent-skills.yml"]).parent

    return {
        "cwd": str(cwd),
        "workspace_root": str(workspace) if workspace else None,
        "searched_directories": searched,
        "files": found,
        "missing": [name for name, p in found.items() if p is None],
    }


def render_human(report: dict, required: list[str]) -> str:
    lines: list[str] = []
    lines.append(f"cwd: {report['cwd']}")
    lines.append(f"workspace_root: {report['workspace_root'] or 'unresolved'}")
    lines.append("found:")
    for name, path in report["files"].items():
        marker = "OK " if path else "-- "
        lines.append(f"  {marker}{name}: {path or 'not found'}")
    if required:
        missing_required = [n for n in required if report["files"].get(n) is None]
        if missing_required:
            lines.append("required missing: " + ", ".join(missing_required))
    lines.append("searched:")
    for d in report["searched_directories"]:
        lines.append(f"  - {d}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace-root",
        default=os.environ.get("WORKSPACE_ROOT"),
        help="Explicit workspace root; falls back to WORKSPACE_ROOT env var.",
    )
    parser.add_argument(
        "--cwd",
        default=os.getcwd(),
        help="Override the starting cwd (default: process cwd).",
    )
    parser.add_argument(
        "--require",
        action="append",
        default=[],
        choices=list(CONFIG_FILES),
        help="Mark a file as required; missing required files force exit 1.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON only.")
    args = parser.parse_args(argv)

    cwd = Path(args.cwd)
    if not cwd.is_dir():
        print(f"FAIL cwd not a directory: {cwd}", file=sys.stderr)
        return 2

    workspace_root: Path | None = None
    if args.workspace_root:
        workspace_root = Path(args.workspace_root).resolve()
        if not workspace_root.is_dir():
            print(
                f"FAIL workspace root not a directory: {workspace_root}",
                file=sys.stderr,
            )
            return 2

    report = discover(workspace_root, cwd)
    output = (
        json.dumps(report, indent=2)
        if args.json
        else render_human(report, args.require)
    )
    print(output)

    required_missing = [n for n in args.require if report["files"].get(n) is None]
    if required_missing:
        return 1
    if not args.require and all(p is None for p in report["files"].values()):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
