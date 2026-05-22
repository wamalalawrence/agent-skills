#!/usr/bin/env bash
# Shared task-context helpers for agent-skills lifecycle scripts.

agent_skills_slugify() {
  printf '%s' "$1" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -E 's/[^a-z0-9._-]+/-/g; s/^-+//; s/-+$//'
}

agent_skills_git_root() {
  git rev-parse --show-toplevel 2>/dev/null || pwd
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
  printf '%s\n' "${PWD}/.cache/agent-skills"
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
