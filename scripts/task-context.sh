#!/usr/bin/env bash
# Shared task-context helpers for agent-skills lifecycle scripts.

agent_skills_slugify() {
  printf '%s' "$1" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -E 's/[^a-z0-9._-]+/-/g; s/^-+//; s/-+$//'
}

# ---------------------------------------------------------------------------
# Deprecated skill names.
#
# Currently empty, and that is the healthy state. The table exists so a rename
# can be carried for one deprecation window instead of breaking every saved
# prompt, shell alias, and CI script written against the old name.
#
# Deprecation policy: an alias is carried for three minor releases and is then
# removed on schedule, as part of that release's checklist. `tech-lead=wamala`
# was added in v0.38.0 and removed here in v0.41.0 on exactly that schedule.
# Adding an entry is a commitment to carry it for that long AND to delete it when
# the release arrives; see docs/versioning.md.
#
# Format: one `old=new` pair per line.
# ---------------------------------------------------------------------------
AGENT_SKILLS_DEPRECATED_SKILLS=""

# Map a possibly-deprecated skill name to its canonical name, printing a
# one-line migration notice on stderr so it never contaminates stdout that a
# caller may be capturing.
agent_skills_resolve_skill_name() {
  local requested="$1"
  local pair old new
  for pair in ${AGENT_SKILLS_DEPRECATED_SKILLS}; do
    old="${pair%%=*}"
    new="${pair#*=}"
    if [[ "${requested}" == "${old}" ]]; then
      printf '%s was renamed to %s; using %s\n' "${old}" "${new}" "${new}" >&2
      printf '%s\n' "${new}"
      return 0
    fi
  done
  printf '%s\n' "${requested}"
}

# The nearest parent directory, below $HOME, that already anchors an
# agent-skills workspace: it holds `.agent-skills.yml`, or a cache that a
# previous start-task wrote. Mirrors `anchor_root` in scripts/cache_root.py.
#
# Only consulted outside a git repository. Without it a workspace with no `.git`
# produced one cache and one project name per working directory, so an agent that
# changed into a subdirectory started a second, unrelated task. $HOME itself is
# never an anchor: a stray ~/.cache/agent-skills would otherwise capture every
# non-git directory beneath it. An anchor must also belong to the current user:
# in a shared directory such as /tmp, another account could otherwise plant one
# and have this task's memory and blackboard written where it can read them.
agent_skills_anchor_root() {
  local dir home
  dir="$(pwd -P)"
  home="$(cd "${HOME:-/nonexistent}" 2>/dev/null && pwd -P || printf '/nonexistent')"
  while [[ -n "${dir}" && "${dir}" != "/" && "${dir}" != "${home}" ]]; do
    if [[ -O "${dir}" ]] && { [[ -f "${dir}/.agent-skills.yml" && -O "${dir}/.agent-skills.yml" ]] \
         || [[ -f "${dir}/.cache/agent-skills/.last-task-context" && -O "${dir}/.cache/agent-skills" ]]; }; then
      printf '%s\n' "${dir}"
      return 0
    fi
    dir="$(dirname "${dir}")"
  done
  return 1
}

agent_skills_git_root() {
  git rev-parse --show-toplevel 2>/dev/null || agent_skills_anchor_root || pwd
}

agent_skills_repo_name() {
  basename "$(agent_skills_git_root)"
}

agent_skills_resolve_cache_root() {
  if [[ -n "${AGENT_SKILLS_CACHE_DIR:-}" ]]; then
    printf '%s\n' "${AGENT_SKILLS_CACHE_DIR}"
    return 0
  fi
  if [[ -n "${WORKSPACE_ROOT:-}" ]]; then
    printf '%s\n' "${WORKSPACE_ROOT}/.cache/agent-skills"
    return 0
  fi
  # Under the global install the cache belongs to the repository, anchored at
  # its root so a nested working directory does not create a second cache.
  printf '%s\n' "$(agent_skills_git_root)/.cache/agent-skills"
}

# Keep the cache out of the user's `git status` without touching their repo.
#
# Under the global install the cache lands inside the repository being worked on,
# so `agent-skills start-task` used to leave an untracked `.cache/` behind in an
# arbitrary repo — and an agent running `git add -A` would commit ticket notes and
# investigation state. Writing to a tracked `.gitignore` would be its own
# surprise (an edit to a file the user owns, in a diff they did not ask for), so
# the entry goes in `.git/info/exclude`: local to that clone, never committed,
# never shown as a change.
agent_skills_ensure_cache_ignored() {
  local cache_root="$1"
  local git_root=""
  git_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
  [[ -n "${git_root}" ]] || return 0
  # Only when the cache is actually inside this repository.
  case "${cache_root}" in
    "${git_root}"/*) : ;;
    *) return 0 ;;
  esac
  # Already ignored, by .gitignore or by a previous run.
  git -C "${git_root}" check-ignore -q .cache 2>/dev/null && return 0
  local exclude="${git_root}/.git/info/exclude"
  [[ -d "${git_root}/.git" ]] || return 0
  mkdir -p "$(dirname "${exclude}")" 2>/dev/null || return 0
  if [[ -f "${exclude}" ]] && grep -qx '\.cache/' "${exclude}" 2>/dev/null; then
    return 0
  fi
  {
    printf '\n# added by agent-skills: task scratch, safe to delete\n'
    printf '.cache/\n'
  } >> "${exclude}" 2>/dev/null || return 0
  return 0
}

agent_skills_last_context_path() {
  printf '%s/.last-task-context\n' "$(agent_skills_resolve_cache_root)"
}

agent_skills_last_context_value() {
  local key="$1"
  local path=""
  path="$(agent_skills_last_context_path)"
  [[ -f "${path}" ]] || return 1
  sed -n "s/^${key}=//p" "${path}" | tail -n 1
}

# Every per-task scratch directory in this cache root, one per line.
#
# `.last-task-context` records one task, and `start-task` rewrites it on every
# run. That is right for one agent in one repository and wrong for two: the
# second `start-task` overwrites the marker, and a bare `finish-task` from the
# first agent then resolves to the second agent's issue key — writing its memory
# under the wrong task and, with cleanup on, deleting the wrong scratch.
#
# Rather than invent a session identity that nothing else has, the ambiguity is
# made visible: a caller resolving a task implicitly can ask how many there are
# and refuse to guess.
agent_skills_active_tasks() {
  local root=""
  root="$(agent_skills_resolve_cache_root)"
  [[ -d "${root}" ]] || return 0
  local entry name
  for entry in "${root}"/*; do
    [[ -d "${entry}" ]] || continue
    name="$(basename "${entry}")"
    # `_projects` and `_org` are the durable tiers, not tasks.
    case "${name}" in _*) continue ;; esac
    # A task is in flight while its blackboard exists: start-task creates it and
    # a clean closeout removes it. A directory holding only what cleanup kept on
    # purpose — a phased plan between phases, an `artifacts/` directory — is not
    # a task anyone is running, and counting it made an implicit finish-task in a
    # long-lived cache refuse because "15 tasks are in flight".
    [[ -f "${entry}/blackboard.json" ]] || continue
    printf '%s\n' "${name}"
  done
}

# The coordinator skills. They dispatch other skills into fresh agents that share
# the coordinator's work key, so the coordinator — not each step — owns the
# task's scratch. See the coordinated-run check in finish-task.sh.
AGENT_SKILLS_COORDINATOR_SKILLS="wamala delivery-runner"

agent_skills_is_coordinator() {
  local candidate
  for candidate in ${AGENT_SKILLS_COORDINATOR_SKILLS}; do
    [[ "$1" == "${candidate}" ]] && return 0
  done
  return 1
}

# Print the coordinator skill recorded on a task's blackboard, if any. The JSON
# is parsed rather than grepped, so a note that merely mentions "wamala" cannot
# pass for a participant.
agent_skills_task_coordinator() {
  local blackboard="$1"
  local python_cmd="${PYTHON3:-python3}"
  [[ -f "${blackboard}" ]] || return 1
  AGENT_SKILLS_COORDINATORS="${AGENT_SKILLS_COORDINATOR_SKILLS}" \
    "${python_cmd}" - "${blackboard}" <<'PY' 2>/dev/null
import json
import os
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        data = json.load(handle)
except (OSError, ValueError):
    raise SystemExit(1)
versions = data.get("skill_versions") if isinstance(data, dict) else None
if not isinstance(versions, dict):
    raise SystemExit(1)
for name in os.environ["AGENT_SKILLS_COORDINATORS"].split():
    if name in versions:
        print(name)
        raise SystemExit(0)
raise SystemExit(1)
PY
}

agent_skills_active_task_count() {
  agent_skills_active_tasks | grep -c . || true
}

agent_skills_project_from_in_repo_config() {
  local python_cmd="${PYTHON3:-python3}"
  command -v "${python_cmd}" >/dev/null 2>&1 || return 1

  AGENT_SKILLS_CWD="${PWD}" "${python_cmd}" - <<'PY' 2>/dev/null
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

cwd = Path(os.environ["AGENT_SKILLS_CWD"]).resolve()
roots = [cwd]
try:
    git_root = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=str(cwd),
        stderr=subprocess.DEVNULL,
        text=True,
    ).strip()
    if git_root:
        roots.insert(0, Path(git_root).resolve())
except Exception:
    pass

for root in roots:
    cfg = root / ".agent-skills.yml"
    if not cfg.exists():
        continue
    in_project = False
    for line in cfg.read_text(encoding="utf-8").splitlines():
        if re.match(r"^project:\s*(?:#.*)?$", line):
            in_project = True
            continue
        if in_project and line and not line.startswith((" ", "\t")):
            break
        if in_project:
            match = re.match(r"\s+name:\s*[\"']?([^\"'#]+)", line)
            if match and match.group(1).strip():
                print(match.group(1).strip())
                raise SystemExit(0)
raise SystemExit(1)
PY
}

agent_skills_project_from_projects_json() {
  local python_cmd="${PYTHON3:-python3}"
  [[ -n "${PROJECTS_JSON:-}" ]] || return 1
  command -v "${python_cmd}" >/dev/null 2>&1 || return 1

  AGENT_SKILLS_CWD="${PWD}" \
  AGENT_SKILLS_PROJECTS_JSON="${PROJECTS_JSON}" \
  AGENT_SKILLS_WORKSPACE_ROOT="${WORKSPACE_ROOT:-}" \
    "${python_cmd}" - <<'PY' 2>/dev/null
from __future__ import annotations

import json
import os
from pathlib import Path

cwd = Path(os.environ["AGENT_SKILLS_CWD"]).resolve()
workspace = Path(os.environ.get("AGENT_SKILLS_WORKSPACE_ROOT") or cwd).resolve()
try:
    projects = json.loads(os.environ["AGENT_SKILLS_PROJECTS_JSON"])
except Exception:
    raise SystemExit(1)

matches: list[tuple[int, str]] = []
for item in projects if isinstance(projects, list) else []:
    if not isinstance(item, dict):
        continue
    name = str(item.get("name") or "").strip()
    rel_path = str(item.get("path") or ".").strip()
    if not name:
        continue
    project_path = (workspace / rel_path).resolve()
    try:
        cwd.relative_to(project_path)
    except ValueError:
        continue
    matches.append((len(str(project_path)), name))

if not matches:
    raise SystemExit(1)
matches.sort(reverse=True)
print(matches[0][1])
PY
}

agent_skills_detect_project() {
  if [[ -n "${AGENT_SKILLS_PROJECT:-}" ]]; then
    printf '%s\n' "${AGENT_SKILLS_PROJECT}"
    return 0
  fi

  local detected=""
  detected="$(agent_skills_project_from_in_repo_config || true)"
  if [[ -n "${detected}" ]]; then
    printf '%s\n' "${detected}"
    return 0
  fi

  detected="$(agent_skills_project_from_projects_json || true)"
  if [[ -n "${detected}" ]]; then
    printf '%s\n' "${detected}"
    return 0
  fi

  agent_skills_repo_name
}

agent_skills_issue_from_text() {
  local text="$1"
  local regex="${JIRA_KEY_REGEX:-[A-Z][A-Z0-9_]+-[0-9]+}"

  if [[ -n "${text}" && "${text}" =~ ${regex} ]]; then
    printf '%s\n' "${BASH_REMATCH[0]}"
    return 0
  fi
  if [[ -n "${text}" && "${text}" =~ [A-Z][A-Z0-9_]+-[0-9]+ ]]; then
    printf '%s\n' "${BASH_REMATCH[0]}"
    return 0
  fi
  return 1
}

agent_skills_normalise_issue_key() {
  local raw="$1"
  local normalized=""
  normalized="$(agent_skills_slugify "${raw}")"
  if [[ -z "${normalized}" || "${normalized}" == _* || "${normalized}" == *..* ]]; then
    normalized="ad-hoc-$(date -u +%Y%m%dt%H%M%Sz)"
  fi
  printf '%s\n' "${normalized}"
}

agent_skills_detect_issue_key() {
  if [[ -n "${AGENT_SKILLS_ISSUE_KEY:-}" ]]; then
    agent_skills_normalise_issue_key "${AGENT_SKILLS_ISSUE_KEY}"
    return 0
  fi

  local candidate=""
  candidate="$(agent_skills_issue_from_text "${GITHUB_HEAD_REF:-}" || true)"
  [[ -n "${candidate}" ]] && { printf '%s\n' "${candidate}"; return 0; }

  candidate="$(agent_skills_issue_from_text "${GITHUB_REF_NAME:-}" || true)"
  [[ -n "${candidate}" ]] && { printf '%s\n' "${candidate}"; return 0; }

  local branch=""
  branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  candidate="$(agent_skills_issue_from_text "${branch}" || true)"
  [[ -n "${candidate}" ]] && { printf '%s\n' "${candidate}"; return 0; }

  case "${branch}" in
    ""|"HEAD"|"main"|"master"|"develop"|"dev")
      printf 'ad-hoc-%s\n' "$(date -u +%Y%m%dt%H%M%Sz)"
      ;;
    *)
      agent_skills_normalise_issue_key "${branch}"
      ;;
  esac
}
