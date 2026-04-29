#!/usr/bin/env python3
"""Check whether a newer agent-skills release is available.

Modes:

  * Default (clone mode): inspect the local agent-skills git checkout. Compare the local
    ``VERSION`` and HEAD commit against the latest release tag on ``origin`` (resolved with
    ``git ls-remote --tags``, no GitHub API call, no token required).
  * Vendored mode (``--vendored PATH``): the user has copied ``skills/`` into a downstream repo.
    Read the highest ``metadata.version`` declared by any ``SKILL.md`` under ``PATH`` and compare
    it against the latest release tag fetched from the GitHub Releases API. Falls back to the
    git ls-remote path when ``--remote`` is a local clone.

Exit codes (scripting-friendly):

  * ``0`` — up to date (or ahead of remote, e.g. contributor branch).
  * ``10`` — update available. Distinct from generic failure so shells / CI can branch on it.
  * ``2`` — setup error (no git, network failure, malformed VERSION).

Secret hygiene:

  * Never prints a token value. ``--token`` is read but only used in the ``Authorization``
    header.
  * Honors ``GITHUB_TOKEN`` from the environment when ``--token`` is not passed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_REPO = "wamalalawrence/agent-skills"
DEFAULT_REMOTE = "origin"
SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?$")
EXIT_OK = 0
EXIT_UPDATE = 10
EXIT_ERROR = 2


def parse_semver(value: str) -> tuple[int, int, int] | None:
    match = SEMVER_RE.match(value.strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def run_git(args: list[str], cwd: Path) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def latest_remote_tag_via_git(remote: str, cwd: Path) -> str | None:
    """Return the highest semver tag advertised by ``remote`` via ``git ls-remote``."""
    try:
        raw = run_git(["ls-remote", "--tags", "--refs", remote], cwd=cwd)
    except (OSError, subprocess.CalledProcessError):
        return None
    best: tuple[int, int, int] | None = None
    best_tag: str | None = None
    for line in raw.splitlines():
        ref = line.split("\t", 1)[-1]
        tag = ref.rsplit("/", 1)[-1]
        parsed = parse_semver(tag)
        if parsed is None:
            continue
        if best is None or parsed > best:
            best = parsed
            best_tag = tag
    return best_tag


def latest_remote_tag_via_api(repo: str, token: str | None) -> str | None:
    """Return the latest release tag from the GitHub Releases API."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None
    tag = payload.get("tag_name")
    return tag if isinstance(tag, str) else None


def read_local_version(repo_root: Path) -> str | None:
    version_path = repo_root / "VERSION"
    if not version_path.exists():
        return None
    text = version_path.read_text(encoding="utf-8").strip()
    return text or None


def highest_skill_version(skills_dir: Path) -> str | None:
    best: tuple[int, int, int] | None = None
    best_str: str | None = None
    for path in skills_dir.rglob("SKILL.md"):
        text = path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r'^\s*version:\s*"?([^"\s]+)"?\s*$', text, re.MULTILINE)
        if not match:
            continue
        parsed = parse_semver(match.group(1))
        if parsed is None:
            continue
        if best is None or parsed > best:
            best = parsed
            best_str = match.group(1)
    return best_str


def compare(local: str, remote: str) -> int:
    """Return -1 if local < remote, 0 if equal, 1 if local > remote."""
    parsed_local = parse_semver(local) or (0, 0, 0)
    parsed_remote = parse_semver(remote) or (0, 0, 0)
    if parsed_local < parsed_remote:
        return -1
    if parsed_local > parsed_remote:
        return 1
    return 0


def emit(payload: dict[str, object], json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    status = payload.get("status", "unknown")
    local = payload.get("local_version", "?")
    remote = payload.get("remote_version", "?")
    detail = payload.get("detail", "")
    print(f"status: {status}")
    print(f"local : {local}")
    print(f"remote: {remote}")
    if detail:
        print(f"detail: {detail}")


def check_clone(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root or Path(__file__).resolve().parent.parent).resolve()
    local = read_local_version(repo_root)
    if local is None:
        emit(
            {"status": "error", "detail": f"VERSION not found under {repo_root}"},
            args.json,
        )
        return EXIT_ERROR

    remote = latest_remote_tag_via_git(args.remote, repo_root)
    if remote is None and args.use_api:
        remote = latest_remote_tag_via_api(args.repo, _resolve_token(args))
    if remote is None:
        emit(
            {
                "status": "error",
                "local_version": local,
                "detail": (
                    f"could not resolve latest tag from {args.remote!r}; "
                    "pass --use-api or check network"
                ),
            },
            args.json,
        )
        return EXIT_ERROR

    cmp = compare(local, remote)
    payload: dict[str, object] = {
        "local_version": local,
        "remote_version": remote.lstrip("v"),
        "remote_ref": args.remote,
        "mode": "clone",
    }
    if cmp < 0:
        payload["status"] = "update-available"
        payload["detail"] = (
            f"v{local} -> {remote}; run ./setup.init --update to apply"
        )
        emit(payload, args.json)
        return EXIT_UPDATE
    if cmp > 0:
        payload["status"] = "ahead"
        payload["detail"] = "local VERSION is ahead of latest remote tag"
        emit(payload, args.json)
        return EXIT_OK
    payload["status"] = "up-to-date"
    emit(payload, args.json)
    return EXIT_OK


def check_vendored(args: argparse.Namespace) -> int:
    skills_dir = Path(args.vendored).resolve()
    if not skills_dir.is_dir():
        emit(
            {"status": "error", "detail": f"vendored skills dir not found: {skills_dir}"},
            args.json,
        )
        return EXIT_ERROR
    local = highest_skill_version(skills_dir)
    if local is None:
        emit(
            {
                "status": "error",
                "detail": (
                    f"no SKILL.md with metadata.version found under {skills_dir}; "
                    "is this an agent-skills vendor copy?"
                ),
            },
            args.json,
        )
        return EXIT_ERROR

    remote = latest_remote_tag_via_api(args.repo, _resolve_token(args))
    if remote is None:
        emit(
            {
                "status": "error",
                "local_version": local,
                "detail": (
                    f"could not reach GitHub releases API for {args.repo}; "
                    "rate-limited or offline. Pass --token to lift the rate limit."
                ),
            },
            args.json,
        )
        return EXIT_ERROR

    cmp = compare(local, remote)
    payload: dict[str, object] = {
        "local_version": local,
        "remote_version": remote.lstrip("v"),
        "vendored_dir": str(skills_dir),
        "repo": args.repo,
        "mode": "vendored",
    }
    if cmp < 0:
        payload["status"] = "update-available"
        payload["detail"] = (
            f"vendored v{local} -> {remote}; refresh the vendored copy "
            "(submodule update / re-vendor) to apply"
        )
        emit(payload, args.json)
        return EXIT_UPDATE
    if cmp > 0:
        payload["status"] = "ahead"
        payload["detail"] = "vendored version is ahead of latest release tag"
        emit(payload, args.json)
        return EXIT_OK
    payload["status"] = "up-to-date"
    emit(payload, args.json)
    return EXIT_OK


def _resolve_token(args: argparse.Namespace) -> str | None:
    if args.token:
        return args.token
    return os.environ.get("GITHUB_TOKEN") or None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check whether a newer agent-skills release is available.",
    )
    parser.add_argument(
        "--vendored",
        metavar="PATH",
        help="Path to a vendored skills directory inside a downstream repo.",
    )
    parser.add_argument(
        "--repo-root",
        metavar="PATH",
        help="Path to the agent-skills clone (defaults to this script's parent repo).",
    )
    parser.add_argument(
        "--remote",
        default=DEFAULT_REMOTE,
        help=f"Git remote to query (default: {DEFAULT_REMOTE}).",
    )
    parser.add_argument(
        "--repo",
        default=DEFAULT_REPO,
        help=f"GitHub owner/name for API queries (default: {DEFAULT_REPO}).",
    )
    parser.add_argument(
        "--use-api",
        action="store_true",
        help="Fall back to the GitHub Releases API if git ls-remote fails (clone mode only).",
    )
    parser.add_argument(
        "--token",
        help="GitHub token for the API call. Falls back to GITHUB_TOKEN. Never echoed.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.vendored:
        return check_vendored(args)
    return check_clone(args)


if __name__ == "__main__":
    sys.exit(main())
