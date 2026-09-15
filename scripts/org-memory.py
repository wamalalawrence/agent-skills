#!/usr/bin/env python3
"""Organisation-tier memory store for agent-skills.

Org memory is the third tier above per-task scratch and per-project memory. It
captures durable patterns, rules, and decisions that have been **observed in
more than one project** and are therefore worth carrying across the whole
workspace. See docs/org-memory.md for the full contract.

Layout (under the resolved cache root):

  _org/
    memory.md       <- human-readable accumulated knowledge across projects
    memory.json     <- structured mirror, updated by this script
    index.json      <- cross-project index (project -> [shared_libs], etc.)

Subcommands:
  path                              Print the absolute org memory.md path.
  init                              Create the skeleton files if missing.
  read                              Print memory.md to stdout.
  note   --section S --text T       Append a bullet under section S.
  search <query>                    Grep across org + every project memory.
  index-update <project> [--shared-lib NAME ...]
                                    Record/refresh a project's shared-library
                                    dependencies in index.json.
  index-show [--shared-lib NAME]    Print the cross-project index, optionally
                                    filtered by shared library.
  promote --from <project> --section S --text T
                                    Move (copy) a bullet from a project memory
                                    into org memory after the same fact has
                                    been confirmed in at least one other
                                    project. Records provenance.

Rules:
  * `_org/` is a reserved prefix. The project-memory cleanup contract already
    refuses any path starting with `_`, so org memory survives every per-task
    cleanup.
  * This script writes only inside `_org/` and `_org/index.json`. It never
    deletes anything and never runs git.
  * No secrets, no PII, no per-task scratch. Every free-text value written here
    is redacted first, at the one choke point in `append_note`.
  * Writes are atomic and serialised: a temporary file plus `os.replace` under an
    advisory lock, so two agents appending at once cannot lose a bullet and a
    crash cannot leave a half-written store.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# One redaction implementation for the whole project, in guard_audit. Org memory
# is the widest-reaching durable tier there is: `start-task` prints it into the
# context of every future task in every project, so a secret written here is a
# secret re-read indefinitely and across project boundaries. It was also the one
# durable tier that did not redact, which made `--promote-to-org` a path for a
# value to travel from a single project's notes into everyone's.
from cache_root import default_cache_root  # noqa: E402
from durable import LockTimeout, update_json, update_text, write_json, write_text  # noqa: E402
from guard_audit import redact  # noqa: E402

DEFAULT_SECTIONS = (
    "Org patterns",
    "Shared libraries",
    "Common gotchas",
    "Cross-project decisions",
    "Outcomes",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip("-").lower()
    return s or "project"


def resolve_cache_root(explicit: str | None) -> Path:
    # One resolution order for every helper and both wrappers; see cache_root.py.
    return default_cache_root(explicit)


def org_dir(cache_root: Path) -> Path:
    return cache_root / "_org"


def ensure_skeleton(odir: Path) -> Path:
    odir.mkdir(parents=True, exist_ok=True)
    md = odir / "memory.md"
    if not md.exists():
        body = ["# Org memory", "", f"- Created: {now_iso()}", ""]
        for section in DEFAULT_SECTIONS:
            body.append(f"## {section}")
            body.append("")
            body.append(
                "- _No facts yet. After patterns recur across 2+ projects, they are "
                "promoted here so every project benefits from cross-project learning._"
            )
            body.append("")
        write_text(md, "\n".join(body))
    js = odir / "memory.json"
    if not js.exists():
        write_json(
            js,
            {
                "created_at": now_iso(),
                "updated_at": now_iso(),
                "sections": {s: [] for s in DEFAULT_SECTIONS},
            },
        )
    idx = odir / "index.json"
    if not idx.exists():
        write_json(
            idx,
            {"updated_at": now_iso(), "projects": {}, "shared_libraries": {}},
        )
    return md


def append_note(odir: Path, section: str, text: str, provenance: str | None = None) -> None:
    md = odir / "memory.md"
    if not md.exists():
        ensure_skeleton(odir)
    # Redacted at the choke point, so `note`, `promote`, and every future writer
    # are covered by one guarantee rather than by each remembering to ask.
    text = redact(text)
    provenance = redact(provenance) if provenance else provenance
    suffix = f" (from: {provenance})" if provenance else ""
    bullet = f"- ({now_iso()}) {text.strip()}{suffix}\n"
    section_re = re.compile(rf"(^## {re.escape(section)}\s*\n)", re.MULTILINE)

    def transform(content: str) -> str:
        if section_re.search(content):
            # Any placeholder bullet, not just one spelled `- _empty`. The
            # skeleton says `- _No facts yet…`, so the narrower pattern never
            # matched and every section kept its placeholder forever — which in
            # turn made `promote-rules` treat a populated section as empty.
            replaced, n = re.subn(
                rf"(^## {re.escape(section)}\s*\n)(- _[^\n]*_\s*\n)",
                rf"\1{bullet}",
                content,
                count=1,
                flags=re.MULTILINE,
            )
            if n:
                return replaced
            return section_re.sub(rf"\1{bullet}", content, count=1)
        return content.rstrip() + f"\n\n## {section}\n\n{bullet}"

    update_text(md, transform)

    def bump(data: dict) -> dict:
        data.setdefault("sections", {}).setdefault(section, []).append(
            {"at": now_iso(), "text": text.strip(), "provenance": provenance}
        )
        data["updated_at"] = now_iso()
        return data

    update_json(odir / "memory.json", bump, default={"created_at": now_iso(), "sections": {}})


def search_all(cache_root: Path, query: str) -> list[tuple[str, int, str]]:
    hits: list[tuple[str, int, str]] = []
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    candidates: list[Path] = []
    org_md = org_dir(cache_root) / "memory.md"
    if org_md.exists():
        candidates.append(org_md)
    projects_root = cache_root / "_projects"
    if projects_root.exists():
        for child in sorted(projects_root.iterdir()):
            md = child / "memory.md"
            if md.exists():
                candidates.append(md)
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                hits.append((str(path), line_no, line.rstrip()))
    return hits


def index_update(odir: Path, project: str, shared_libs: list[str]) -> dict:
    ensure_skeleton(odir)
    pslug = slugify(project)

    def transform(data: dict) -> dict:
        projects = data.setdefault("projects", {})
        libs = data.setdefault("shared_libraries", {})
        projects[pslug] = {
            "name": project,
            "shared_libraries": sorted(set(shared_libs)),
            "updated_at": now_iso(),
        }
        for name, plist in list(libs.items()):
            if pslug in plist and name not in shared_libs:
                plist.remove(pslug)
                if not plist:
                    del libs[name]
        for name in shared_libs:
            plist = libs.setdefault(name, [])
            if pslug not in plist:
                plist.append(pslug)
                plist.sort()
        data["updated_at"] = now_iso()
        return data

    return update_json(
        odir / "index.json", transform, default={"projects": {}, "shared_libraries": {}}
    )


def index_show(odir: Path, shared_lib: str | None) -> dict:
    idx_path = odir / "index.json"
    if not idx_path.exists():
        return {}
    data = json.loads(idx_path.read_text(encoding="utf-8"))
    if shared_lib:
        return {
            "shared_library": shared_lib,
            "projects": data.get("shared_libraries", {}).get(shared_lib, []),
        }
    return data


def cmd_path(args: argparse.Namespace) -> int:
    print(org_dir(resolve_cache_root(args.cache_root)) / "memory.md")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    md = ensure_skeleton(org_dir(resolve_cache_root(args.cache_root)))
    print(md)
    return 0


def budgeted(text: str, budget_chars: int, path: Path) -> str:
    """Cut ``text`` to ``budget_chars`` including the notice that says so.

    Zero means unlimited. The read used to print the whole file, so the tier
    that every task loads first had no ceiling at all; a startup budget that
    the first tier can blow through is not a budget.
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
    md = org_dir(resolve_cache_root(args.cache_root)) / "memory.md"
    if not md.exists():
        print(f"-- no org memory yet at {md}", file=sys.stderr)
        return 1
    print(budgeted(md.read_text(encoding="utf-8"), args.budget_chars, md))
    return 0


def cmd_note(args: argparse.Namespace) -> int:
    append_note(org_dir(resolve_cache_root(args.cache_root)), args.section, args.text)
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    hits = search_all(resolve_cache_root(args.cache_root), args.query)
    if not hits:
        print("-- no matches", file=sys.stderr)
        return 1
    for path, line_no, line in hits:
        print(f"{path}:{line_no}: {line}")
    return 0


def cmd_index_update(args: argparse.Namespace) -> int:
    data = index_update(
        org_dir(resolve_cache_root(args.cache_root)),
        args.project,
        args.shared_lib or [],
    )
    print(json.dumps(data.get("projects", {}).get(slugify(args.project), {}), indent=2))
    return 0


def cmd_index_show(args: argparse.Namespace) -> int:
    data = index_show(org_dir(resolve_cache_root(args.cache_root)), args.shared_lib)
    if not data:
        print("-- no index yet", file=sys.stderr)
        return 1
    print(json.dumps(data, indent=2))
    return 0


def cmd_promote(args: argparse.Namespace) -> int:
    odir = org_dir(resolve_cache_root(args.cache_root))
    ensure_skeleton(odir)
    append_note(odir, args.section, args.text, provenance=args.from_project)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-root", default=None)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("path")
    sp.set_defaults(func=cmd_path)

    sp = sub.add_parser("init")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("read")
    sp.add_argument(
        "--budget-chars",
        type=int,
        default=0,
        help="Cap the output at N chars including the truncation notice (0 = unlimited).",
    )
    sp.set_defaults(func=cmd_read)

    sp = sub.add_parser("note")
    sp.add_argument("--section", required=True)
    sp.add_argument("--text", required=True)
    sp.set_defaults(func=cmd_note)

    sp = sub.add_parser("search")
    sp.add_argument("query")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("index-update")
    sp.add_argument("project")
    sp.add_argument("--shared-lib", action="append", default=[])
    sp.set_defaults(func=cmd_index_update)

    sp = sub.add_parser("index-show")
    sp.add_argument("--shared-lib", default=None)
    sp.set_defaults(func=cmd_index_show)

    sp = sub.add_parser("promote")
    sp.add_argument("--from", dest="from_project", required=True)
    sp.add_argument("--section", required=True)
    sp.add_argument("--text", required=True)
    sp.set_defaults(func=cmd_promote)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except LockTimeout as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
