#!/usr/bin/env python3
"""One answer to "where is this task's cache?" for every Python helper.

The lifecycle wrappers resolved the cache at the git root and every Python
helper resolved it at the current directory. The two agreed only when an agent
happened to run from the repository root. A dispatched agent that ran
`agent-skills blackboard progress` from `src/` wrote to `src/.cache/agent-skills`
and was told the blackboard `start-task` had just created did not exist.

Resolution order, identical to `agent_skills_resolve_cache_root` in
`scripts/task-context.sh`:

1. `AGENT_SKILLS_CACHE_DIR`
2. `${WORKSPACE_ROOT}/.cache/agent-skills`
3. `<git root>/.cache/agent-skills`
4. the nearest parent directory, below `$HOME`, that already holds
   `.agent-skills.yml` or `.cache/agent-skills/.last-task-context`
5. `<cwd>/.cache/agent-skills`

Step 4 exists for workspaces that are not git repositories. Without it, running
from a subdirectory created a second cache and a second project name for the
same task. `$HOME` itself is never an anchor: a stray `~/.cache/agent-skills`
would otherwise capture every non-git directory underneath it.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

CACHE_PARTS = (".cache", "agent-skills")


def git_toplevel(cwd: Path) -> Path | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    top = out.stdout.strip()
    return Path(top) if out.returncode == 0 and top else None


def anchor_root(cwd: Path) -> Path | None:
    """Nearest parent below `$HOME` that already anchors an agent-skills workspace."""
    home = Path(os.environ.get("HOME", "/nonexistent")).resolve()
    current = cwd.resolve()
    for candidate in (current, *current.parents):
        if candidate == home or candidate == Path(candidate.anchor):
            return None
        if (candidate / ".agent-skills.yml").is_file():
            return candidate
        if (candidate.joinpath(*CACHE_PARTS) / ".last-task-context").is_file():
            return candidate
    return None


def workspace_root(cwd: Path | None = None) -> Path:
    """The directory the cache and the default project name belong to."""
    here = (cwd or Path.cwd()).resolve()
    return git_toplevel(here) or anchor_root(here) or here


def default_cache_root(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("AGENT_SKILLS_CACHE_DIR")
    if env:
        return Path(env).expanduser().resolve()
    base = os.environ.get("WORKSPACE_ROOT")
    if base:
        return Path(base).joinpath(*CACHE_PARTS).resolve()
    return workspace_root().joinpath(*CACHE_PARTS)


if __name__ == "__main__":
    print(default_cache_root())
