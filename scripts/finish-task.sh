#!/usr/bin/env bash
# agent-skills finish-task — single-command memory closeout for every task.
#
# Usage:
#   ./finish-task.sh [project] [issue-key] --summary "what happened" [options]
#
# The script writes project memory first, emits telemetry, then cleans per-task
# scratch only when the task reached a clean terminal state. Blocked and
# needs-context runs keep scratch so the next agent can resume.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/task-context.sh"

PYTHON3="${PYTHON3:-python3}"
PM_SCRIPT="${SCRIPT_DIR}/project-memory.py"
TELEMETRY_SCRIPT="${SCRIPT_DIR}/telemetry.py"
CACHE_ROOT="$(agent_skills_resolve_cache_root)"

PROJECT=""
ISSUE_KEY=""
SUMMARY=""
STATUS="complete"
PR_URL=""
CLEANUP="auto"
SKILL="${AGENT_SKILLS_ACTIVE_SKILL:-unknown}"
FACTS=()
BUILD_FACTS=()
GOTCHAS=()
LESSONS=()
REPO_FACTS=()
RECENT_TASK_ONLY="false"
SHOW_CANDIDATES="true"
KB_SCRIPT="${SCRIPT_DIR}/knowledge.py"
BB_SCRIPT="${SCRIPT_DIR}/blackboard.py"
BOUNDARY_SCRIPT="${SCRIPT_DIR}/boundary_safety.py"

usage() {
  cat <<'EOF'
Usage: ./finish-task.sh [project] [issue-key] --summary "what happened" [options]

Mandatory closeout helper for agent-skills tasks. It writes durable project
memory before deleting per-task scratch.

Arguments:
  project      Optional. Auto-detected when omitted.
  issue-key    Optional. Auto-detected when omitted.

Options:
  --summary T  Required. One-sentence outcome for Recent tasks.
  --status S   complete | pr-opened | blocked | needs-context | abandoned
               Default: complete.
  --pr-url U   Append a PR URL to the Recent tasks memory bullet.
  --skill N    Skill responsible for this closeout telemetry. Default:
               AGENT_SKILLS_ACTIVE_SKILL or "unknown". A skill name deprecated
               by a rename resolves to its current name, with a notice.
  --build-runtime T
               Append T under "Build & runtime". Repeatable.
  --gotcha T   Append T under "Common gotchas". Repeatable.
  --fact "Section::text"
               Append text under an arbitrary project-memory section.
               Repeatable.
  --repo-knowledge "Section::text"
               Append a durable fact to the COMMITTED repo knowledge base
               (.agent-skills/knowledge/project.md). Survives a fresh clone;
               shows up in the diff for review. Repeatable.
  --lesson "id::trigger::action[::domain]"
               Record a confidence-scored lesson in the repo knowledge base.
               Repeating an existing id reconfirms it and raises confidence.
               Repeatable.
  --no-candidates
               Skip the durable-fact suggestions drawn from the blackboard.
  --cleanup    Force cleanup even for blocked/needs-context runs.
  --no-cleanup Keep per-task scratch even for complete runs.
  --recent-task-only
               Write only the Recent tasks bullet and telemetry.
  --help       Show this help.

Examples:
  ./finish-task.sh --summary "PR opened for SonarQube cleanup"
  ./finish-task.sh example-api ABC-123 --status pr-opened --pr-url https://github.com/example-org/example-api/pull/12 --summary "fixed null handling"
  ./finish-task.sh --status blocked --summary "blocked waiting for staging credentials"
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --summary)
      SUMMARY="${2:-}"
      shift 2
      ;;
    --summary=*)
      SUMMARY="${1#*=}"
      shift
      ;;
    --status)
      STATUS="${2:-}"
      shift 2
      ;;
    --status=*)
      STATUS="${1#*=}"
      shift
      ;;
    --pr-url)
      PR_URL="${2:-}"
      shift 2
      ;;
    --pr-url=*)
      PR_URL="${1#*=}"
      shift
      ;;
    --skill)
      SKILL="$(agent_skills_resolve_skill_name "${2:-}")"
      shift 2
      ;;
    --skill=*)
      SKILL="$(agent_skills_resolve_skill_name "${1#*=}")"
      shift
      ;;
    --build-runtime)
      BUILD_FACTS+=("${2:-}")
      shift 2
      ;;
    --build-runtime=*)
      BUILD_FACTS+=("${1#*=}")
      shift
      ;;
    --gotcha)
      GOTCHAS+=("${2:-}")
      shift 2
      ;;
    --gotcha=*)
      GOTCHAS+=("${1#*=}")
      shift
      ;;
    --fact)
      FACTS+=("${2:-}")
      shift 2
      ;;
    --fact=*)
      FACTS+=("${1#*=}")
      shift
      ;;
    --lesson)
      LESSONS+=("${2:-}")
      shift 2
      ;;
    --lesson=*)
      LESSONS+=("${1#*=}")
      shift
      ;;
    --repo-knowledge)
      REPO_FACTS+=("${2:-}")
      shift 2
      ;;
    --repo-knowledge=*)
      REPO_FACTS+=("${1#*=}")
      shift
      ;;
    --no-candidates)
      SHOW_CANDIDATES="false"
      shift
      ;;
    --cleanup)
      CLEANUP="true"
      shift
      ;;
    --no-cleanup)
      CLEANUP="false"
      shift
      ;;
    --recent-task-only)
      RECENT_TASK_ONLY="true"
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    -*)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 3
      ;;
    *)
      if [[ -z "${PROJECT}" ]]; then
        PROJECT="$1"
      elif [[ -z "${ISSUE_KEY}" ]]; then
        ISSUE_KEY="$1"
      else
        echo "Too many arguments. Expected: [project] [issue-key] --summary ..." >&2
        usage >&2
        exit 3
      fi
      shift
      ;;
  esac
done

case "${STATUS}" in
  complete|pr-opened|blocked|needs-context|abandoned) ;;
  *)
    echo "ERROR: --status must be complete, pr-opened, blocked, needs-context, or abandoned." >&2
    exit 3
    ;;
esac

if [[ -z "${SUMMARY}" ]]; then
  echo "ERROR: --summary is required so project memory gets a useful Recent tasks bullet." >&2
  usage >&2
  exit 3
fi

if [[ -z "${PROJECT}" ]]; then
  PROJECT="$(agent_skills_last_context_value project || true)"
  if [[ -z "${PROJECT}" ]]; then
    PROJECT="$(agent_skills_detect_project)"
  fi
fi
if [[ -z "${ISSUE_KEY}" ]]; then
  ISSUE_KEY="$(agent_skills_last_context_value issue_key || true)"
  if [[ -z "${ISSUE_KEY}" ]]; then
    ISSUE_KEY="$(agent_skills_detect_issue_key)"
  fi
fi
ISSUE_KEY="$(agent_skills_normalise_issue_key "${ISSUE_KEY}")"

note() {
  local section="$1"
  local text="$2"
  [[ -n "${text}" ]] || return 0
  "${PYTHON3}" "${PM_SCRIPT}" --cache-root "${CACHE_ROOT}" note "${PROJECT}" \
    --section "${section}" --text "${text}"
}

SAFE_PROJECT="$(printf '%s' "${PROJECT}" | "${PYTHON3}" "${BOUNDARY_SCRIPT}")"
SAFE_ISSUE_KEY="$(printf '%s' "${ISSUE_KEY}" | "${PYTHON3}" "${BOUNDARY_SCRIPT}")"

echo "== agent-skills finish-task =="
echo "  project:   ${SAFE_PROJECT}"
echo "  issue-key: ${SAFE_ISSUE_KEY}"
echo "  status:    ${STATUS}"

recent="${ISSUE_KEY}: ${STATUS} - ${SUMMARY}"
if [[ -n "${PR_URL}" ]]; then
  recent="${recent} (${PR_URL})"
fi

echo "[1/3] project-memory: writing Recent tasks..."
note "Recent tasks" "${recent}"

if [[ "${RECENT_TASK_ONLY}" != "true" ]]; then
  for text in "${BUILD_FACTS[@]+"${BUILD_FACTS[@]}"}"; do
    note "Build & runtime" "${text}"
  done
  for text in "${GOTCHAS[@]+"${GOTCHAS[@]}"}"; do
    note "Common gotchas" "${text}"
  done
  for raw in "${FACTS[@]+"${FACTS[@]}"}"; do
    if [[ "${raw}" != *"::"* ]]; then
      echo "ERROR: --fact expects Section::text, got: ${raw}" >&2
      exit 3
    fi
    section="${raw%%::*}"
    text="${raw#*::}"
    note "${section}" "${text}"
  done

  # Committed tier. Unlike project memory this lands in the repository, so it
  # appears in the diff and a human approves it.
  for raw in "${REPO_FACTS[@]+"${REPO_FACTS[@]}"}"; do
    if [[ "${raw}" != *"::"* ]]; then
      echo "ERROR: --repo-knowledge expects Section::text, got: ${raw}" >&2
      exit 3
    fi
    "${PYTHON3}" "${KB_SCRIPT}" note --section "${raw%%::*}" --text "${raw#*::}" \
      || echo "  WARN: could not write repo knowledge (is this a git repo?)" >&2
  done

  for raw in "${LESSONS[@]+"${LESSONS[@]}"}"; do
    lesson_id="${raw%%::*}"
    lesson_rest="${raw#*::}"
    lesson_trigger="${lesson_rest%%::*}"
    lesson_rest="${lesson_rest#*::}"
    lesson_action="${lesson_rest%%::*}"
    lesson_domain="process"
    if [[ "${lesson_rest}" == *"::"* ]]; then
      lesson_domain="${lesson_rest##*::}"
    fi
    if [[ -z "${lesson_id}" || -z "${lesson_trigger}" || -z "${lesson_action}" ]]; then
      echo "ERROR: --lesson expects id::trigger::action[::domain], got: ${raw}" >&2
      exit 3
    fi
    "${PYTHON3}" "${KB_SCRIPT}" lesson add \
      --id "${lesson_id}" \
      --trigger "${lesson_trigger}" \
      --action "${lesson_action}" \
      --domain "${lesson_domain}" \
      --evidence "${ISSUE_KEY}" \
      || echo "  WARN: could not record lesson ${lesson_id}" >&2
  done
fi

# ---------------------------------------------------------------------------
# Durable-fact candidates.
#
# Writing the Recent tasks bullet is automatic; writing durable knowledge used
# to depend on the agent remembering to pass a flag, which meant the default
# path produced a task log rather than learning. Surfacing candidates from the
# blackboard inverts that: the agent rejects a suggestion instead of having to
# invent one.
# ---------------------------------------------------------------------------
if [[ "${SHOW_CANDIDATES}" == "true" && -f "${BB_SCRIPT}" ]]; then
CANDIDATES="$("${PYTHON3}" - "$@" <<PYEOF 2>/dev/null || true
import json
import pathlib
import sys

path = pathlib.Path("${CACHE_ROOT}") / "${ISSUE_KEY}" / "blackboard.json"
if not path.exists():
    sys.exit(0)
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except (OSError, ValueError):
    sys.exit(0)

seen = []
for section in ("facts", "decisions"):
    for entry in data.get(section, []) or []:
        text = entry.get("text") if isinstance(entry, dict) else str(entry)
        if not text:
            continue
        text = " ".join(str(text).split())
        if text not in seen:
            seen.append(text)

for text in seen[:8]:
    print(text)
PYEOF
)"
  CANDIDATES="$(printf '%s' "${CANDIDATES}" | "${PYTHON3}" "${BOUNDARY_SCRIPT}")"
  if [[ -n "${CANDIDATES}" ]]; then
    echo ""
    echo "Durable-fact candidates from this task's blackboard:"
    while IFS= read -r line; do
      [[ -n "${line}" ]] || continue
      echo "  - ${line}"
    done <<< "${CANDIDATES}"
    echo ""
    echo "  Anything above that will still be true next month belongs in the"
    echo "  COMMITTED repo knowledge base, not just the local cache:"
    echo "    ${PYTHON3} ${KB_SCRIPT} note --section Gotchas --text \"<fact>\""
    echo "    ${PYTHON3} ${KB_SCRIPT} lesson add --id <slug> --trigger \"<when>\" --action \"<do>\""
    echo "  Reject the rest — a task log is not knowledge."
  fi
fi

echo "[2/3] telemetry: recording outcome..."
event="completed"
if [[ "${STATUS}" == "blocked" || "${STATUS}" == "needs-context" ]]; then
  event="stopped"
fi
"${PYTHON3}" "${TELEMETRY_SCRIPT}" --cache-root "${CACHE_ROOT}" emit "${PROJECT}" "${event}" \
  --field "skill=${SKILL}" \
  --field "issue_key=${ISSUE_KEY}" \
  --field "status=${STATUS}" >/dev/null

if [[ "${CLEANUP}" == "auto" ]]; then
  case "${STATUS}" in
    blocked|needs-context) CLEANUP="false" ;;
    *) CLEANUP="true" ;;
  esac
fi

if [[ "${CLEANUP}" == "true" ]]; then
  echo "[3/3] cleanup: removing per-task scratch after memory write..."
  "${PYTHON3}" "${PM_SCRIPT}" --cache-root "${CACHE_ROOT}" cleanup-task "${ISSUE_KEY}"
else
  echo "[3/3] cleanup: skipped; per-task scratch preserved for resumption."
fi

echo "== Finish complete =="
