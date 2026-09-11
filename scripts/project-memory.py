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
  * When `<issue-key>/phased-plan/README.md` exists, cleanup preserves
    `phased-plan/` and `destination.md` so delivery-planner artifacts survive
    across executor phase boundaries.
  * The script writes to disk only inside the resolved cache root.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# One redaction implementation for the whole project, in guard_audit. Project
# memory outlives the task that wrote it and is read back into every later
# agent's starting context, so a credential landing here is a credential that
# keeps arriving.
from durable import LockTimeout, update_json, update_text, write_json, write_text
from guard_audit import redact

DEFAULT_SECTIONS = (
    "Project facts",
    "Build & runtime",
    "Common gotchas",
    "Recent tasks",
)


# A placeholder bullet is any italic-marked bullet the skeleton wrote, e.g.
# `- _No facts yet. ..._`. Matching only the literal `- _empty` (as this script
# did before v0.36.0) meant the real skeleton text was never recognised: the
# placeholder was never replaced by the first real fact, it lingered under every
# populated section, and because promotion scans used the same narrow filter, an
# identical placeholder shared by two projects surfaced as a false org-promotion
# candidate.
PLACEHOLDER_PREFIX = "- _"


def is_placeholder(line: str) -> bool:
    return line.startswith(PLACEHOLDER_PREFIX)


def slugify(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip("-").lower()
    return s or "project"


def git_toplevel() -> Path | None:
    """Return the git repository root, or None when not in a repository."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode == 0 and out.stdout.strip():
        return Path(out.stdout.strip())
    return None


def resolve_cache_root(explicit: str | None) -> Path:
    """Resolve the cache root.

    Order: explicit flag, `AGENT_SKILLS_CACHE_DIR`, `WORKSPACE_ROOT`, the git
    repository root, then cwd. The git root sits above cwd deliberately: with a
    bare cwd fallback, starting a task from a subdirectory silently created a
    second, empty memory store, so the agent read nothing and wrote somewhere
    the next run would not look.
    """
    if explicit:
        return Path(explicit).resolve()
    env = os.environ.get("AGENT_SKILLS_CACHE_DIR")
    if env:
        return Path(env).resolve()
    workspace = os.environ.get("WORKSPACE_ROOT")
    if workspace:
        return (Path(workspace) / ".cache" / "agent-skills").resolve()
    top = git_toplevel()
    base = top if top is not None else Path.cwd()
    return (base / ".cache" / "agent-skills").resolve()


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
            body.append(
                "- _No facts yet. After your first task, this section will "
                "contain verified build steps, runtime versions, gotchas, and "
                "outcomes — so the next agent skips re-discovery._"
            )
            body.append("")
        write_text(md, "\n".join(body))
    js = pdir / "memory.json"
    if not js.exists():
        write_json(
            js,
            {
                "project": project,
                "slug": slugify(project),
                "repo": repo,
                "created_at": now_iso(),
                "updated_at": now_iso(),
                "sections": {s: [] for s in DEFAULT_SECTIONS},
            },
        )
    else:
        warn_on_slug_collision(js, project)
    return md


def warn_on_slug_collision(js: Path, project: str) -> None:
    """Warn when two distinct project names resolve to the same slug.

    `slugify` squashes every non-alphanumeric run to a hyphen, so `acme/api` and
    `acme-api` collide into one memory file. Silently merging two projects'
    knowledge is worse than either project having none, because the facts
    contradict each other and neither agent can tell why.
    """
    try:
        data = json.loads(js.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    recorded = data.get("project")
    if recorded and recorded != project:
        print(
            f"WARN slug {slugify(project)!r} already holds memory for project "
            f"{recorded!r}, not {project!r}. Two names collide on one store; "
            f"pass a distinct project name or set AGENT_SKILLS_CACHE_DIR.",
            file=sys.stderr,
        )


def append_note(pdir: Path, section: str, text: str) -> None:
    # Redacted at the choke point rather than at each caller, so `finish-task
    # --summary`, `--gotcha`, `--build-runtime`, and `--fact` are all covered by
    # one guarantee instead of four that have to be remembered separately.
    text = redact(text)
    md = pdir / "memory.md"
    if not md.exists():
        raise SystemExit(f"FAIL memory.md missing at {md}; run 'init' first")
    section_re = re.compile(rf"(^## {re.escape(section)}\s*\n)", re.MULTILINE)
    bullet = f"- ({now_iso()}) {text.strip()}\n"

    def transform(content: str) -> str:
        if section_re.search(content):
            # Replace the placeholder line if present, else insert just under the heading.
            replaced, n = re.subn(
                rf"(^## {re.escape(section)}\s*\n)(- _[^\n]*\n)",
                rf"\1{bullet}",
                content,
                count=1,
                flags=re.MULTILINE,
            )
            if n:
                return replaced
            return section_re.sub(rf"\1{bullet}", content, count=1)
        return content.rstrip() + f"\n\n## {section}\n\n{bullet}"

    # The read and the write happen under one lock, and the write is a rename
    # rather than a truncate. Two `finish-task` runs appending at once used to
    # cost a bullet: both read the same file, and the second write replaced the
    # first. A crash mid-write used to cost the whole file.
    update_text(md, transform)

    def bump(data: dict) -> dict:
        data.setdefault("sections", {}).setdefault(section, []).append(
            {"at": now_iso(), "text": text.strip()}
        )
        data["updated_at"] = now_iso()
        return data

    update_json(pdir / "memory.json", bump, default={"sections": {}})


# Names directly under the cache root that are never task scratch. `_projects/`
# holds every project's durable memory and `_org/` holds org memory; a cleanup
# that reached either would destroy the Company Brain rather than one task.
RESERVED_CACHE_NAMES = ("_projects", "_org")


def _resolve_task_dir(cache_root: Path, issue_key: str) -> Path | None:
    """Resolve an issue key to the one directory cleanup is allowed to delete.

    Returns the directory, or `None` when there is nothing to clean. Raises
    `SystemExit` on anything ambiguous.

    This function exists because recursive deletion driven by a user-supplied
    string went wrong in the field. `finish-task` run with a lowercase issue key
    deleted the directory belonging to the uppercase key: macOS compares path
    components case-insensitively, so `(cache_root / "proj-805").exists()`
    answered True for a directory actually named `PROJ-805`, and the cleanup
    deleted whatever that resolved to. The log then named a path that had never
    existed on disk.

    So the key is matched against the **real directory entries**, by exact name.
    Two strings that a filesystem happens to treat as equivalent are not the
    same task, and cleanup fails closed on the difference: the thing it would
    otherwise guess away is the only copy of a task's working state.
    """
    key = issue_key.strip()
    if (
        not key
        or key in {".", ".."}
        or key.startswith("_")
        or "/" in key
        or "\\" in key
        or ".." in key
        or Path(key).name != key
    ):
        raise SystemExit(f"FAIL refusing to clean up unsafe path: {issue_key!r}")
    if key in RESERVED_CACHE_NAMES:
        raise SystemExit(f"FAIL refusing to clean up reserved directory: {key!r}")

    try:
        names = sorted(entry.name for entry in cache_root.iterdir())
    except OSError:
        return None

    exact = [name for name in names if name == key]
    folded = [name for name in names if name != key and name.lower() == key.lower()]

    if not exact:
        if folded:
            variants = ", ".join(repr(name) for name in folded)
            raise SystemExit(
                f"FAIL refusing to clean up {key!r}: no directory has that exact name, "
                f"but {variants} differs only in case. Nothing was removed. Re-run with "
                f"the exact name if that is genuinely the target."
            )
        return None
    if folded:
        variants = ", ".join(repr(name) for name in folded)
        raise SystemExit(
            f"FAIL refusing to clean up {key!r}: it is ambiguous with {variants}. "
            f"Nothing was removed."
        )

    target = cache_root / key
    if target.is_symlink():
        raise SystemExit(f"FAIL refusing to clean up a symlink: {target}")
    if not target.is_dir():
        raise SystemExit(f"FAIL not a directory: {target}")

    resolved = target.resolve()
    root = cache_root.resolve()
    if root not in resolved.parents:
        raise SystemExit(f"FAIL refusing to clean up outside the cache root: {resolved}")

    # Task scratch never contains a repository. If one is here, the cache root
    # is pointed somewhere it should not be, and a recursive delete would take
    # the user's work with it.
    if (target / ".git").exists():
        raise SystemExit(
            f"FAIL refusing to recursively delete a directory containing a git "
            f"repository: {target}"
        )
    return target


def cleanup_task(cache_root: Path, issue_key: str) -> Path | None:
    target = _resolve_task_dir(cache_root, issue_key)
    if target is None:
        return None

    # Preserve delivery-planner artifacts (destination.md + phased-plan/)
    # when a phased plan is present. The plan must survive across executor
    # phase boundaries so each phase can load destination.md + its
    # phase-NN.md from a fresh agent session.
    plan_index = target / "phased-plan" / "README.md"
    if plan_index.exists():
        for child in sorted(target.iterdir()):
            if child.name in ("phased-plan", "destination.md"):
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        return target

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


def budgeted(text: str, budget_chars: int, path: Path) -> str:
    """Cut ``text`` to ``budget_chars`` including the notice that says so.

    Zero means unlimited. `start-task` passes its share of the startup budget;
    before this the whole file was printed, so a project with a long history
    spent the context the budgeted tiers were saving.
    """
    if budget_chars <= 0 or len(text) <= budget_chars:
        return text
    notice = f"\n-- truncated: {{shown}} of {len(text)} chars shown; read {path} for the rest"
    room = max(0, budget_chars - len(notice.format(shown=len(text))))
    cut = text[:room]
    newline = cut.rfind("\n")
    if newline > room // 2:
        cut = cut[:newline]
    return cut.rstrip() + notice.format(shown=len(cut.rstrip()))


def cmd_read(args: argparse.Namespace) -> int:
    pdir = project_dir(resolve_cache_root(args.cache_root), args.project)
    md = pdir / "memory.md"
    if not md.exists():
        print(f"-- no project memory yet at {md}", file=sys.stderr)
        return 1
    print(budgeted(md.read_text(encoding="utf-8"), args.budget_chars, md))
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


_BULLET_RE = re.compile(r"^- (?:\([^)]+\)\s+)?(.*?)\s*$")


def _bullet_payload(line: str) -> str:
    m = _BULLET_RE.match(line)
    return (m.group(1) if m else line).strip().lower()


def dedup_memory(pdir: Path) -> int:
    md = pdir / "memory.md"
    if not md.exists():
        return 0
    lines = md.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    seen: set[tuple[str, str]] = set()
    current_section = ""
    removed = 0
    for line in lines:
        if line.startswith("## "):
            current_section = line[3:].strip()
            out.append(line)
            continue
        if line.startswith("- ") and not is_placeholder(line):
            key = (current_section, _bullet_payload(line))
            if key in seen:
                removed += 1
                continue
            seen.add(key)
        out.append(line)
    write_text(md, "\n".join(out).rstrip() + "\n")
    return removed


def compact_recent_tasks(pdir: Path, keep: int) -> int:
    """Collapse `Recent tasks` bullets beyond `keep` into a Trends summary."""
    md = pdir / "memory.md"
    if not md.exists():
        return 0
    text = md.read_text(encoding="utf-8")
    match = re.search(
        r"(^## Recent tasks\s*\n)((?:- .*\n)*)", text, re.MULTILINE
    )
    if not match:
        return 0
    bullets = [line for line in match.group(2).splitlines() if line.startswith("- ")]
    if len(bullets) <= keep:
        return 0
    kept = bullets[:keep]
    rolled = bullets[keep:]
    trend = (
        f"- ({now_iso()}) compacted {len(rolled)} older Recent tasks bullets "
        f"into Trends; see git history for original entries."
    )
    new_block = match.group(1) + "\n".join(kept) + "\n"
    text = text[: match.start()] + new_block + text[match.end() :]
    trends_re = re.compile(r"(^## Trends\s*\n)", re.MULTILINE)
    if trends_re.search(text):
        text = trends_re.sub(rf"\1{trend}\n", text, count=1)
    else:
        text = text.rstrip() + f"\n\n## Trends\n\n{trend}\n"
    write_text(md, text)
    return len(rolled)


def find_repeated_bullets(pdir: Path, section: str, min_count: int) -> list[dict]:
    """Find bullets in `section` whose payload appears `min_count` or more times.

    Used to surface promotion candidates for org memory.
    """
    md = pdir / "memory.md"
    if not md.exists():
        return []
    lines = md.read_text(encoding="utf-8").splitlines()
    in_section = False
    counts: dict[str, int] = {}
    samples: dict[str, str] = {}
    for line in lines:
        if line.startswith("## "):
            in_section = line[3:].strip() == section
            continue
        if not in_section or not line.startswith("- ") or is_placeholder(line):
            continue
        payload = _bullet_payload(line)
        counts[payload] = counts.get(payload, 0) + 1
        samples.setdefault(payload, line)
    return [
        {"payload": p, "count": counts[p], "sample": samples[p]}
        for p in counts
        if counts[p] >= min_count
    ]


def search_memory(pdir: Path, query: str) -> list[tuple[int, str]]:
    md = pdir / "memory.md"
    if not md.exists():
        return []
    pat = re.compile(re.escape(query), re.IGNORECASE)
    hits = []
    for i, line in enumerate(md.read_text(encoding="utf-8").splitlines(), start=1):
        if pat.search(line):
            hits.append((i, line.rstrip()))
    return hits


def cmd_dedup(args: argparse.Namespace) -> int:
    pdir = project_dir(resolve_cache_root(args.cache_root), args.project)
    removed = dedup_memory(pdir)
    print(f"removed {removed} duplicate bullets")
    return 0


def cmd_compact(args: argparse.Namespace) -> int:
    pdir = project_dir(resolve_cache_root(args.cache_root), args.project)
    rolled = compact_recent_tasks(pdir, args.keep)
    print(f"compacted {rolled} bullets into Trends")
    return 0


def cmd_promote_candidates(args: argparse.Namespace) -> int:
    pdir = project_dir(resolve_cache_root(args.cache_root), args.project)
    found = find_repeated_bullets(pdir, args.section, args.min_count)
    print(json.dumps(found, indent=2))
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    pdir = project_dir(resolve_cache_root(args.cache_root), args.project)
    hits = search_memory(pdir, args.query)
    if not hits:
        print("-- no matches", file=sys.stderr)
        return 1
    for line_no, line in hits:
        print(f"{line_no}: {line}")
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
    sp.add_argument(
        "--budget-chars",
        type=int,
        default=0,
        help="Cap the output at N chars including the truncation notice (0 = unlimited).",
    )
    sp.set_defaults(func=cmd_read)

    sp = sub.add_parser("note")
    sp.add_argument("project")
    sp.add_argument("--section", required=True)
    sp.add_argument("--text", required=True)
    sp.set_defaults(func=cmd_note)

    sp = sub.add_parser("cleanup-task")
    sp.add_argument("issue_key")
    sp.set_defaults(func=cmd_cleanup)

    sp = sub.add_parser("dedup")
    sp.add_argument("project")
    sp.set_defaults(func=cmd_dedup)

    sp = sub.add_parser("compact")
    sp.add_argument("project")
    sp.add_argument("--keep", type=int, default=20)
    sp.set_defaults(func=cmd_compact)

    sp = sub.add_parser("promote-candidates")
    sp.add_argument("project")
    sp.add_argument("--section", default="Common gotchas")
    sp.add_argument("--min-count", type=int, default=3)
    sp.set_defaults(func=cmd_promote_candidates)

    sp = sub.add_parser("search")
    sp.add_argument("project")
    sp.add_argument("query")
    sp.set_defaults(func=cmd_search)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except LockTimeout as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
