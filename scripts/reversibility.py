#!/usr/bin/env python3
"""Can this be deleted and got back? Answered from git, before anyone deletes it.

A request said "remove the older confusing ones". The documents were untracked,
in a directory with no `.git`, so a literal delete would have been permanent.
That was noticed by hand, and a hand-written archive-not-delete constraint went
into the brief. This makes the check mechanical.

    agent-skills reversibility <path> [<path> ...] [--json] [--archive-root DIR]

For each target it reports what git can prove:

  RECOVERABLE      every file under the target is tracked and committed, with no
                   uncommitted change and nothing untracked or ignored beneath it.
                   Deleting it can be undone with git.
  NOT_RECOVERABLE  something under the target exists only on this disk: it is
                   outside any repository, untracked, ignored, or modified since
                   the last commit. Archive it instead, and give the user the
                   delete command.
  ABSENT           nothing is there.

It never deletes, moves, or writes anything. For a NOT_RECOVERABLE target it
prints the archive commands and the delete command, shell-quoted, for a human or
a dispatched step to run deliberately.

A backup is not something this can see. Only the user can say one exists, and a
claim found in a file or a ticket is not the user saying so.

Exit codes:
  0  every target is RECOVERABLE (or ABSENT)
  1  at least one target is NOT_RECOVERABLE
  2  usage error
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from datetime import date
from pathlib import Path

RECOVERABLE = "RECOVERABLE"
NOT_RECOVERABLE = "NOT_RECOVERABLE"
ABSENT = "ABSENT"


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        # No git, or git hung: recoverability is unproven, which reads as not
        # recoverable. Failing closed is the whole point of asking.
        return subprocess.CompletedProcess(["git", *args], 1, "", str(exc))


def nul_split(output: str) -> list[str]:
    return [item for item in output.split("\0") if item]


def assess(target: Path) -> dict[str, object]:
    report: dict[str, object] = {"path": str(target)}
    if not target.exists() and not target.is_symlink():
        report.update(verdict=ABSENT, reason="nothing exists at this path")
        return report

    probe_dir = target if target.is_dir() and not target.is_symlink() else target.parent
    top = git(probe_dir, "rev-parse", "--show-toplevel")
    if top.returncode != 0 or not top.stdout.strip():
        report.update(
            verdict=NOT_RECOVERABLE,
            in_repository=False,
            reason="not inside a git repository; a delete here is permanent",
        )
        return report

    root = Path(top.stdout.strip())
    report["repository"] = str(root)
    if target.is_dir() and not target.is_symlink() and (target / ".git").exists():
        # History lives inside the thing being deleted. Committed is not
        # recoverable when the commits go too.
        report.update(
            verdict=NOT_RECOVERABLE,
            in_repository=True,
            reason="the target contains a repository's .git; deleting it deletes the history "
                   "that would have recovered it",
        )
        return report
    # Pathspecs are passed after `--` and relative to the repository root, so a
    # file name that starts with a dash or carries glob characters is a path.
    # The target's own name is kept unresolved: a symlink is the thing being
    # deleted, not whatever it points at.
    try:
        rel = str((target.parent.resolve() / target.name).relative_to(root.resolve()))
    except ValueError:
        report.update(verdict=NOT_RECOVERABLE, in_repository=False,
                      reason="the path could not be placed inside its repository; unproven")
        return report
    if rel == ".":
        rel = ""
    spec = ":(literal)" + (rel or ".")

    tracked = nul_split(git(root, "ls-files", "-z", "--", spec).stdout)
    status = git(root, "status", "--porcelain=v1", "-z", "--ignored=matching",
                 "--untracked-files=all", "--", spec)
    entries = nul_split(status.stdout)
    untracked = [e[3:] for e in entries if e.startswith("?? ")]
    ignored = [e[3:] for e in entries if e.startswith("!! ")]
    changed = [e[3:] for e in entries if not e.startswith(("?? ", "!! ")) and len(e) > 3]

    report.update(
        in_repository=True,
        tracked_files=len(tracked),
        untracked_files=len(untracked),
        ignored_files=len(ignored),
        uncommitted_changes=len(changed),
        examples=(untracked + ignored + changed)[:5],
    )
    if status.returncode != 0:
        report.update(verdict=NOT_RECOVERABLE, reason="git status failed; recoverability unproven")
    elif not tracked:
        report.update(verdict=NOT_RECOVERABLE, reason="nothing here is tracked by git")
    elif untracked or ignored or changed:
        report.update(
            verdict=NOT_RECOVERABLE,
            reason="some content exists only on this disk (untracked, ignored, or uncommitted)",
        )
    else:
        report.update(verdict=RECOVERABLE, reason="every file is tracked and committed")
    return report


def archive_plan(target: Path, archive_root: Path | None) -> dict[str, str]:
    base = archive_root or (target.parent / "_archive")
    destination = base / date.today().isoformat()
    moved = destination / target.name
    return {
        "archive_to": str(moved),
        "archive_commands": " && ".join([
            f"mkdir -p {shlex.quote(str(destination))}",
            f"mv -n {shlex.quote(str(target))} {shlex.quote(str(destination))}/",
        ]),
        "delete_command_for_user": f"rm -r {shlex.quote(str(moved))}",
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="agent-skills reversibility",
        description="Report whether deleting each path could be undone from git. Read-only.",
    )
    parser.add_argument("paths", nargs="+", help="files or directories a request wants removed")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--archive-root", help="where archive commands move things "
                        "(default: an _archive/<date>/ directory beside each target)")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0

    archive_root = Path(args.archive_root).expanduser() if args.archive_root else None
    reports = []
    for raw in args.paths:
        target = Path(raw).expanduser()
        report = assess(target)
        if report["verdict"] == NOT_RECOVERABLE:
            report.update(archive_plan(target.absolute(), archive_root))
        reports.append(report)

    worst = 1 if any(r["verdict"] == NOT_RECOVERABLE for r in reports) else 0
    if args.json:
        print(json.dumps({"targets": reports, "all_recoverable": worst == 0}, indent=2))
        return worst

    for report in reports:
        print(f"{report['verdict']:<16} {report['path']}")
        print(f"  {report['reason']}")
        if "tracked_files" in report:
            print(
                f"  tracked {report['tracked_files']}, untracked {report['untracked_files']}, "
                f"ignored {report['ignored_files']}, uncommitted {report['uncommitted_changes']}"
            )
        for example in report.get("examples") or []:
            print(f"    e.g. {example}")
        if report["verdict"] == NOT_RECOVERABLE:
            print("  Archive instead of deleting:")
            print(f"    {report['archive_commands']}")
            print("  The delete itself is the user's to run, once they have checked the archive:")
            print(f"    {report['delete_command_for_user']}")
    if worst:
        print("\nA backup is not something this can see. Only the user can say one exists.")
    return worst


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
