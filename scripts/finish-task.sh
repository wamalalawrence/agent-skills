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
RECENT_TASK_ONLY="false"

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
               AGENT_SKILLS_ACTIVE_SKILL or "unknown".
  --build-runtime T
               Append T under "Build & runtime". Repeatable.
  --gotcha T   Append T under "Common gotchas". Repeatable.
  --fact "Section::text"
               Append text under an arbitrary project-memory section.
               Repeatable.
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
      SKILL="${2:-}"
      shift 2
      ;;
    --skill=*)
      SKILL="${1#*=}"
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

echo "== agent-skills finish-task =="
echo "  project:   ${PROJECT}"
echo "  issue-key: ${ISSUE_KEY}"
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
