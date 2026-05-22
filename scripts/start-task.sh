#!/usr/bin/env bash
# agent-skills start-task — single-command preflight for every task.
#
# This is the ONE command every agent MUST run before any context discovery,
# implementation, review, or testing on a task. It loads the Company Brain
# so the agent starts with durable project knowledge instead of re-discovering
# the same facts every session.
#
# Usage:
#   ./start-task.sh [project] [issue-key] [--no-org] [--skill name=version]
#
# What it does:
#   1. Reads org memory (non-fatal if missing — org memory is built up over time).
#   2. Reads project memory; initialises the skeleton if none exists yet.
#   3. Initialises the per-task blackboard so every skill in this task shares
#      working memory instead of re-deriving context.
#   4. Prints a consolidated summary the agent can treat as its starting context.
#
# Exit codes:
#   0 — preflight complete, context printed.
#   1 — project memory missing and could not be initialised (fatal).
#   2 — blackboard init failed (fatal).
#   3 — invalid arguments.
#
# This script is idempotent: running it again on the same task re-prints the
# current state without duplicating records.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${SCRIPT_DIR}/task-context.sh"

# ---------------------------------------------------------------------------
# Resolve the cache root (same logic as the Python scripts)
# ---------------------------------------------------------------------------
resolve_cache_root() {
  if [[ -n "${AGENT_SKILLS_CACHE_DIR:-}" ]]; then
    echo "${AGENT_SKILLS_CACHE_DIR}"
    return
  fi
  if [[ -n "${WORKSPACE_ROOT:-}" ]]; then
    echo "${WORKSPACE_ROOT}/.cache/agent-skills"
    return
  fi
  echo "${HOME}/.cache/agent-skills"
}

# ---------------------------------------------------------------------------
# Determine python3 command (prefer the one that can import the scripts)
# ---------------------------------------------------------------------------
PYTHON3="${PYTHON3:-python3}"

print_separator() {
  echo ""
  echo "---"
  echo ""
}

usage() {
  cat <<'EOF'
Usage: ./start-task.sh [project] [issue-key] [--no-org] [--skill name=version]

Mandatory preflight for every agent-skills task. Run this before any context
discovery, implementation, review, or testing.

Arguments:
  project      Optional. Project slug matching PROJECTS_JSON or .agent-skills.yml.
               If omitted, auto-detect from AGENT_SKILLS_PROJECT,
               .agent-skills.yml, PROJECTS_JSON, git root, or cwd.
  issue-key    Optional. Tracker key, PR URL, or task identifier. If omitted,
               auto-detect from AGENT_SKILLS_ISSUE_KEY, GitHub env, branch
               name, or generate an ad-hoc task id.
  --no-org     Skip org-memory read (useful when no org memory exists yet).
  --project P  Same as positional project.
  --issue-key K, --task K
               Same as positional issue-key.
  --skill name=version
               Record a participating skill version on the blackboard. Repeat
               for multiple skills.

Examples:
  ./start-task.sh
  ./start-task.sh example-api ABC-156
  ./start-task.sh checkout-svc gh-pr-789 --skill software-engineer=0.33.0
  ./start-task.sh --project my-project --task refactor-auth --no-org
EOF
}

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
PROJECT=""
ISSUE_KEY=""
SKIP_ORG="false"
PROJECT_SOURCE="auto"
ISSUE_SOURCE="auto"
SKILLS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-org)
      SKIP_ORG="true"
      shift
      ;;
    --project)
      PROJECT="${2:-}"
      PROJECT_SOURCE="explicit"
      shift 2
      ;;
    --project=*)
      PROJECT="${1#*=}"
      PROJECT_SOURCE="explicit"
      shift
      ;;
    --issue-key|--task)
      ISSUE_KEY="${2:-}"
      ISSUE_SOURCE="explicit"
      shift 2
      ;;
    --issue-key=*|--task=*)
      ISSUE_KEY="${1#*=}"
      ISSUE_SOURCE="explicit"
      shift
      ;;
    --skill)
      SKILLS+=("${2:-}")
      shift 2
      ;;
    --skill=*)
      SKILLS+=("${1#*=}")
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
        PROJECT_SOURCE="explicit"
      elif [[ -z "${ISSUE_KEY}" ]]; then
        ISSUE_KEY="$1"
        ISSUE_SOURCE="explicit"
      else
        echo "Too many arguments. Expected: [project] [issue-key] [--no-org]" >&2
        usage >&2
        exit 3
      fi
      shift
      ;;
  esac
done

if [[ -z "${PROJECT}" ]]; then
  PROJECT="$(agent_skills_detect_project)"
fi

if [[ -z "${ISSUE_KEY}" ]]; then
  ISSUE_KEY="$(agent_skills_detect_issue_key)"
fi

NORMALIZED_ISSUE_KEY="$(agent_skills_normalise_issue_key "${ISSUE_KEY}")"
if [[ "${NORMALIZED_ISSUE_KEY}" != "${ISSUE_KEY}" ]]; then
  ISSUE_KEY="${NORMALIZED_ISSUE_KEY}"
  ISSUE_SOURCE="${ISSUE_SOURCE}+normalized"
fi

CACHE_ROOT="$(resolve_cache_root)"
PM_SCRIPT="${SCRIPT_DIR}/project-memory.py"
OM_SCRIPT="${SCRIPT_DIR}/org-memory.py"
BB_SCRIPT="${SCRIPT_DIR}/blackboard.py"
LAST_CONTEXT="${CACHE_ROOT}/.last-task-context"

# ---------------------------------------------------------------------------
# Validate the scripts exist
# ---------------------------------------------------------------------------
for script in "${PM_SCRIPT}" "${OM_SCRIPT}" "${BB_SCRIPT}"; do
  if [[ ! -f "${script}" ]]; then
    echo "ERROR: Required script not found: ${script}" >&2
    echo "Make sure you are running from the agent-skills repository." >&2
    exit 2
  fi
done

echo "== agent-skills start-task =="
echo "  project:    ${PROJECT} (${PROJECT_SOURCE})"
echo "  issue-key:  ${ISSUE_KEY} (${ISSUE_SOURCE})"
echo "  cache-root: ${CACHE_ROOT}"
if [[ ${#SKILLS[@]} -gt 0 ]]; then
  echo "  skills:     ${SKILLS[*]}"
fi
print_separator

mkdir -p "${CACHE_ROOT}"
{
  printf 'project=%s\n' "${PROJECT}"
  printf 'issue_key=%s\n' "${ISSUE_KEY}"
} > "${LAST_CONTEXT}"

HAD_ERRORS=0

# ---------------------------------------------------------------------------
# Step 1: Org memory (non-fatal if missing)
# ---------------------------------------------------------------------------
if [[ "${SKIP_ORG}" == "true" ]]; then
  echo "[1/3] org-memory: SKIPPED (--no-org)"
else
  echo "[1/3] org-memory: reading..."
  if ${PYTHON3} "${OM_SCRIPT}" --cache-root "${CACHE_ROOT}" read 2>/dev/null; then
    echo "[1/3] org-memory: read OK"
  else
    echo "[1/3] org-memory: none yet (this is fine — org memory builds up over time)"
  fi
fi

print_separator

# ---------------------------------------------------------------------------
# Step 2: Project memory (fatal if cannot init)
# ---------------------------------------------------------------------------
echo "[2/3] project-memory: reading ${PROJECT}..."
PM_OUTPUT="$(${PYTHON3} "${PM_SCRIPT}" --cache-root "${CACHE_ROOT}" read "${PROJECT}" 2>&1)" && PM_OK=0 || PM_OK=$?

if [[ ${PM_OK} -ne 0 ]]; then
  echo "[2/3] project-memory: no memory file yet — initialising skeleton..."
  if ${PYTHON3} "${PM_SCRIPT}" --cache-root "${CACHE_ROOT}" init "${PROJECT}" 2>&1; then
    echo "[2/3] project-memory: skeleton created — reading it back..."
    ${PYTHON3} "${PM_SCRIPT}" --cache-root "${CACHE_ROOT}" read "${PROJECT}" 2>&1 || {
      echo "FATAL: project-memory init succeeded but read failed." >&2
      exit 1
    }
  else
    echo "FATAL: Could not initialise project memory for '${PROJECT}'." >&2
    echo "Check that the cache root is writable: ${CACHE_ROOT}" >&2
    exit 1
  fi
else
  echo "${PM_OUTPUT}"
  echo "[2/3] project-memory: read OK"
fi

print_separator

# ---------------------------------------------------------------------------
# Step 3: Blackboard init (fatal if fails)
# ---------------------------------------------------------------------------
echo "[3/3] blackboard: initialising ${ISSUE_KEY} (project: ${PROJECT})..."
BB_PATH="$(${PYTHON3} "${BB_SCRIPT}" --cache-root "${CACHE_ROOT}" path "${ISSUE_KEY}" 2>&1)"

BB_ARGS=("${BB_SCRIPT}" --cache-root "${CACHE_ROOT}" init --project "${PROJECT}" "${ISSUE_KEY}")
for skill in "${SKILLS[@]}"; do
  BB_ARGS+=(--skill "${skill}")
done

if ${PYTHON3} "${BB_ARGS[@]}" 2>&1; then
  echo "[3/3] blackboard: ready at ${BB_PATH}"
else
  echo "FATAL: Could not initialise blackboard for '${ISSUE_KEY}'." >&2
  exit 2
fi

print_separator

echo "== Preflight complete =="
echo ""
echo "Next steps per the Company Brain contract (docs/company-brain.md):"
echo "  1. The project memory above IS your starting context. Use it."
echo "  2. Append facts to project memory AS you verify them:"
echo "     ${PYTHON3} ${PM_SCRIPT} note ${PROJECT} --section \"Build & runtime\" --text \"...\""
echo "  3. Append a Recent tasks bullet when the task finishes."
echo "  4. Prefer the finish wrapper so memory is written before cleanup:"
echo "     bash ${SCRIPT_DIR}/finish-task.sh ${PROJECT} ${ISSUE_KEY} --summary \"...\""
echo "     # or manually, after writing memory:"
echo "     ${PYTHON3} ${PM_SCRIPT} cleanup-task ${ISSUE_KEY}"
echo ""
echo "  org-memory search (cross-project):"
echo "     ${PYTHON3} ${OM_SCRIPT} search \"<query>\""
echo "  blackboard read (current working memory):"
echo "     ${PYTHON3} ${BB_SCRIPT} read ${ISSUE_KEY}"
echo ""
echo "Do NOT skip these steps. The next agent on this project depends on them."
