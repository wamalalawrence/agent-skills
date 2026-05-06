#!/usr/bin/env python3
"""Per-project memory store for agent-skills.

Project memory is the small, durable Markdown file an agent updates after every
successful task on a project. It lives next to (but **outside**) per-task evidence
packs so it survives task cleanup, and it is the first thing a skill should read
when starting a new task on the same project.

Layout:
  ${AGENT_SKILLS_CACHE_DIR:-${WORKSPACE_ROOT:-$REPO_ROOT}/.cache/agent-skills}/
    _projects/<project-slug>/
      memory.md         <- the human-readable accumulated knowledge
      memory.json       <- structured mirror used by tools (auto-merged)
    <issue-key>/        <- per-task scratch (cleaned up on task completion)

Subcommands:
  path     <project>                       Print the absolute memory.md path.
  init     <project> [--name N --repo R]   Create skeleton if missing.
  read     <project>                       Print memory.md to stdout.
  note     <project> --section S --text T  Append a bullet under section S.
  cleanup-task <issue-key>                 Delete only the per-task directory;
                                           never touches _projects/.

Rules:
  * Project memory is **never** deleted by this script.
  * Cleanup only removes `<issue-key>/` directories. Branch deletion is the
    caller's responsibility — this script will not run git commands.
  * The script writes to disk only inside the resolved cache root.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_SECTIONS = (
    "Project facts",
    "Build & runtime",
    "Common gotchas",
    "Recent tasks",
)


def slugify(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip("-").lower()
    return s or "project"


def resolve_cache_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    env = os.environ.get("AGENT_SKILLS_CACHE_DIR")
    if env:
        return Path(env).resolve()
    base = os.environ.get("WORKSPACE_ROOT") or os.getcwd()
    return (Path(base) / ".cache" / "agent-skills").resolve()


def project_dir(cache_root: Path, project: str) -> Path:
    return cache_root / "_projects" / slugify(project)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_skeleton(pdir: Path, project: str, repo: str | None) -> Path:
    pdir.mkdir(parents=True, exist_ok=True)
    md = pdir / "memory.md"
    if not md.exists():
        body = [f"# Project memory: {project}", ""]
        if repo:
            body.append(f"- Repo: {repo}")
        body.append(f"- Created: {now_iso()}")
        body.append("")
        for section in DEFAULT_SECTIONS:
            body.append(f"## {section}")
            body.append("")
            body.append("- _empty — populated as the agent learns._")
            body.append("")
        md.write_text("\n".join(body), encoding="utf-8")
    js = pdir / "memory.json"
    if not js.exists():
        js.write_text(
            json.dumps(
                {
                    "project": project,
                    "slug": slugify(project),
                    "repo": repo,
                    "created_at": now_iso(),
                    "updated_at": now_iso(),
                    "sections": {s: [] for s in DEFAULT_SECTIONS},
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    return md


def append_note(pdir: Path, section: str, text: str) -> None:
    md = pdir / "memory.md"
    if not md.exists():
        raise SystemExit(f"FAIL memory.md missing at {md}; run 'init' first")
    content = md.read_text(encoding="utf-8")
    section_re = re.compile(rf"(^## {re.escape(section)}\s*\n)", re.MULTILINE)
    bullet = f"- ({now_iso()}) {text.strip()}\n"
    if section_re.search(content):
        # Replace the placeholder line if present, else insert just under the heading.
        new_content, n = re.subn(
            rf"(^## {re.escape(section)}\s*\n)(- _empty[^\n]*\n)",
            rf"\1{bullet}",
            content,
            count=1,
            flags=re.MULTILINE,
        )
        if n == 0:
            new_content = section_re.sub(rf"\1{bullet}", content, count=1)
    else:
        new_content = content.rstrip() + f"\n\n## {section}\n\n{bullet}"
    md.write_text(new_content, encoding="utf-8")

    js = pdir / "memory.json"
    data = json.loads(js.read_text(encoding="utf-8")) if js.exists() else {}
    data.setdefault("sections", {}).setdefault(section, []).append(
        {"at": now_iso(), "text": text.strip()}
    )
    data["updated_at"] = now_iso()
    js.write_text(json.dumps(data, indent=2), encoding="utf-8")


def cleanup_task(cache_root: Path, issue_key: str) -> Path | None:
    if issue_key.startswith("_") or "/" in issue_key or ".." in issue_key:
        raise SystemExit(f"FAIL refusing to clean up unsafe path: {issue_key!r}")
    target = cache_root / issue_key
    if not target.exists():
        return None
    if not target.is_dir():
        raise SystemExit(f"FAIL not a directory: {target}")
    shutil.rmtree(target)
    return target


def cmd_path(args: argparse.Namespace) -> int:
    pdir = project_dir(resolve_cache_root(args.cache_root), args.project)
    print(pdir / "memory.md")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    pdir = project_dir(resolve_cache_root(args.cache_root), args.project)
    md = ensure_skeleton(pdir, args.project, args.repo)
    print(md)
    return 0


def cmd_read(args: argparse.Namespace) -> int:
    pdir = project_dir(resolve_cache_root(args.cache_root), args.project)
    md = pdir / "memory.md"
    if not md.exists():
        print(f"-- no project memory yet at {md}", file=sys.stderr)
        return 1
    print(md.read_text(encoding="utf-8"))
    return 0


def cmd_note(args: argparse.Namespace) -> int:
    pdir = project_dir(resolve_cache_root(args.cache_root), args.project)
    ensure_skeleton(pdir, args.project, None)
    append_note(pdir, args.section, args.text)
    return 0


def cmd_cleanup(args: argparse.Namespace) -> int:
    removed = cleanup_task(resolve_cache_root(args.cache_root), args.issue_key)
    if removed:
        print(f"removed: {removed}")
    else:
        print(f"absent: {args.issue_key}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-root",
        default=None,
        help="Override cache root (default: AGENT_SKILLS_CACHE_DIR or "
        "$WORKSPACE_ROOT/.cache/agent-skills).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("path")
    sp.add_argument("project")
    sp.set_defaults(func=cmd_path)

    sp = sub.add_parser("init")
    sp.add_argument("project")
    sp.add_argument("--repo", default=None)
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("read")
    sp.add_argument("project")
    sp.set_defaults(func=cmd_read)

    sp = sub.add_parser("note")
    sp.add_argument("project")
    sp.add_argument("--section", required=True)
    sp.add_argument("--text", required=True)
    sp.set_defaults(func=cmd_note)

    sp = sub.add_parser("cleanup-task")
    sp.add_argument("issue_key")
    sp.set_defaults(func=cmd_cleanup)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
