#!/usr/bin/env bash
# agent-skills start-task — single-command preflight for every task.
#
# This is the ONE command every agent MUST run before any context discovery,
# implementation, review, or testing on a task. It loads the Company Brain
# so the agent starts with durable project knowledge instead of re-discovering
# the same facts every session.
#
# Usage:
#   ./start-task.sh <project> <issue-key> [--no-org]
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
Usage: ./start-task.sh <project> <issue-key> [--no-org]

Mandatory preflight for every agent-skills task. Run this before any context
discovery, implementation, review, or testing.

Arguments:
  project      Project slug matching an entry in PROJECTS_JSON or
               .agent-skills.yml (e.g. "my-api", "checkout-service").
  issue-key    Tracker ticket key or task identifier (e.g. "ABC-123",
               "gh-456", "refactor-auth").
  --no-org     Skip org-memory read (useful when no org memory exists yet).

Examples:
  ./start-task.sh example-api ABC-156
  ./start-task.sh checkout-svc KVB-5263
  ./start-task.sh my-project gh-789 --no-org
EOF
}

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
PROJECT=""
ISSUE_KEY=""
SKIP_ORG="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-org)
      SKIP_ORG="true"
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
        echo "Too many arguments. Expected: <project> <issue-key> [--no-org]" >&2
        usage >&2
        exit 3
      fi
      shift
      ;;
  esac
done

if [[ -z "${PROJECT}" || -z "${ISSUE_KEY}" ]]; then
  echo "ERROR: Both <project> and <issue-key> are required." >&2
  usage >&2
  exit 3
fi

CACHE_ROOT="$(resolve_cache_root)"
PM_SCRIPT="${SCRIPT_DIR}/project-memory.py"
OM_SCRIPT="${SCRIPT_DIR}/org-memory.py"
BB_SCRIPT="${SCRIPT_DIR}/blackboard.py"

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
echo "  project:    ${PROJECT}"
echo "  issue-key:  ${ISSUE_KEY}"
echo "  cache-root: ${CACHE_ROOT}"
print_separator

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

if ${PYTHON3} "${BB_SCRIPT}" --cache-root "${CACHE_ROOT}" init --project "${PROJECT}" "${ISSUE_KEY}" 2>&1; then
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
echo "  4. Run cleanup-task AFTER writing memory (never before):"
echo "     ${PYTHON3} ${PM_SCRIPT} cleanup-task ${ISSUE_KEY}"
echo ""
echo "  org-memory search (cross-project):"
echo "     ${PYTHON3} ${OM_SCRIPT} search \"<query>\""
echo "  blackboard read (current working memory):"
echo "     ${PYTHON3} ${BB_SCRIPT} read ${ISSUE_KEY}"
echo ""
echo "Do NOT skip these steps. The next agent on this project depends on them."
