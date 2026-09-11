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
IF_OPEN="false"
KB_SCRIPT="${SCRIPT_DIR}/knowledge.py"
BB_SCRIPT="${SCRIPT_DIR}/blackboard.py"
DOD_SCRIPT="${SCRIPT_DIR}/dod-check.py"

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
  --if-open    Fallback closeout for a session-stop hook. Runs ONLY when the
               task recorded by the last start-task has not already been
               closed out; otherwise prints one line and exits 0 without
               writing. A hook cannot know whether work finished, so this is
               what makes the fallback idempotent instead of a second, false
               "unfinished" record after a normal finish.
  --help       Show this help.

Closeout is not verified delivery. This command records what happened. For
complete / pr-opened it also reports whether a definition-of-done.json exists
for the task and whether `dod-check.py` verifies it; that result goes into
telemetry as verified_delivery=yes|no|n/a and is printed, never enforced here.

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
    --if-open)
      IF_OPEN="true"
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

# ---------------------------------------------------------------------------
# --if-open: the session-stop fallback. A host's Stop event is a turn ending,
# not proof a task was abandoned, so the fallback closes out only a task that
# start-task recorded and finish-task has not yet closed. Anything else is a
# session event with no task identity behind it, and recording it as a task
# outcome would put a false "stopped" into history and telemetry.
# ---------------------------------------------------------------------------
if [[ "${IF_OPEN}" == "true" ]]; then
  CTX_ISSUE="$(agent_skills_last_context_value issue_key || true)"
  CTX_CLOSED="$(agent_skills_last_context_value closed || true)"
  if [[ -z "${CTX_ISSUE}" ]]; then
    echo "== agent-skills finish-task: no task in flight; nothing to close out =="
    exit 0
  fi
  if [[ "${CTX_CLOSED}" == "${CTX_ISSUE}" ]]; then
    echo "== agent-skills finish-task: ${CTX_ISSUE} already closed out; fallback skipped =="
    exit 0
  fi
  if [[ -z "${ISSUE_KEY}" && "$(agent_skills_active_task_count)" -gt 1 ]]; then
    echo "== agent-skills finish-task: several tasks in flight; fallback cannot pick one =="
    exit 0
  fi
  ISSUE_KEY="${ISSUE_KEY:-${CTX_ISSUE}}"
fi

if [[ -z "${PROJECT}" ]]; then
  PROJECT="$(agent_skills_last_context_value project || true)"
  if [[ -z "${PROJECT}" ]]; then
    PROJECT="$(agent_skills_detect_project)"
  fi
fi
if [[ -z "${ISSUE_KEY}" ]]; then
  # Resolved implicitly. That is only safe while there is one task in flight:
  # `.last-task-context` holds whichever task started most recently, which for
  # two agents in one repository is not necessarily this one. Guessing here
  # writes memory under another task's key and, with cleanup on, deletes its
  # scratch — so when the answer is ambiguous, say so instead.
  ACTIVE_TASK_COUNT="$(agent_skills_active_task_count)"
  if [[ "${ACTIVE_TASK_COUNT}" -gt 1 ]]; then
    echo "ERROR: --issue-key is required here: ${ACTIVE_TASK_COUNT} tasks are in flight" >&2
    echo "       under ${CACHE_ROOT}, so the most recent start-task is not necessarily" >&2
    echo "       yours. Nothing was written." >&2
    echo "       In flight:" >&2
    agent_skills_active_tasks | sed 's/^/         - /' >&2
    exit 3
  fi
  ISSUE_KEY="$(agent_skills_last_context_value issue_key || true)"
  if [[ -z "${ISSUE_KEY}" ]]; then
    ISSUE_KEY="$(agent_skills_detect_issue_key)"
  fi
fi
ISSUE_KEY="$(agent_skills_normalise_issue_key "${ISSUE_KEY}")"
# ---------------------------------------------------------------------------
# Validate every structured flag BEFORE writing anything.
#
# The Recent tasks bullet used to be written first and the `Section::text` shapes
# checked as each one was reached, so a typo in the third `--fact` exited 3 after
# the bullet had already landed. The obvious response is to fix the typo and
# rerun, which appends the bullet a second time. Memory writes are not
# transactional, so the shapes are checked while nothing has been written yet.
# ---------------------------------------------------------------------------
for raw in "${FACTS[@]+"${FACTS[@]}"}"; do
  if [[ "${raw}" != *"::"* ]]; then
    echo "ERROR: --fact expects Section::text, got: ${raw}" >&2
    echo "       Nothing was written; fix the flag and rerun." >&2
    exit 3
  fi
done
for raw in "${REPO_FACTS[@]+"${REPO_FACTS[@]}"}"; do
  if [[ "${raw}" != *"::"* ]]; then
    echo "ERROR: --repo-knowledge expects Section::text, got: ${raw}" >&2
    echo "       Nothing was written; fix the flag and rerun." >&2
    exit 3
  fi
done
for raw in "${LESSONS[@]+"${LESSONS[@]}"}"; do
  lesson_rest="${raw#*::}"
  if [[ "${raw}" != *"::"* || -z "${raw%%::*}" || -z "${lesson_rest%%::*}" \
        || "${lesson_rest}" != *"::"* || -z "${lesson_rest#*::}" ]]; then
    echo "ERROR: --lesson expects id::trigger::action[::domain], got: ${raw}" >&2
    echo "       Nothing was written; fix the flag and rerun." >&2
    exit 3
  fi
done

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
    section="${raw%%::*}"
    text="${raw#*::}"
    note "${section}" "${text}"
  done

  # Committed tier. Unlike project memory this lands in the repository, so it
  # appears in the diff and a human approves it.
  for raw in "${REPO_FACTS[@]+"${REPO_FACTS[@]}"}"; do
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
    echo "    ${PYTHON3} ${KB_SCRIPT} lesson add --id <slug> --trigger \"<when>\" --action \"<do>\" --evidence ${ISSUE_KEY}"
    echo "  Reject the rest — a task log is not knowledge."
  fi
fi

# ---------------------------------------------------------------------------
# Delivery evidence. A closeout records what happened; it does not establish
# that delivery checks passed. Before this, `--status complete` with nothing
# but a summary was recorded as `completed` and nothing distinguished it from
# a change with a verified definition of done. The distinction is now carried
# into telemetry and printed. It is reported, not enforced: closeout must stay
# usable for reviews, planning, blocked work, and recovery.
# ---------------------------------------------------------------------------
TASK_DIR="${CACHE_ROOT}/${ISSUE_KEY}"
EVIDENCE="none"
VERIFIED="n/a"
if [[ "${STATUS}" == "complete" || "${STATUS}" == "pr-opened" ]]; then
  if [[ -f "${TASK_DIR}/definition-of-done.json" ]]; then
    EVIDENCE="definition-of-done"
    if [[ -f "${DOD_SCRIPT}" ]]; then
      DOD_OUT="$("${PYTHON3}" "${DOD_SCRIPT}" "${TASK_DIR}/definition-of-done.json" 2>&1)" \
        && VERIFIED="yes" || VERIFIED="no"
      echo "[2/3] delivery evidence: definition-of-done.json present — ${DOD_OUT##*$'\n'}"
      if [[ "${VERIFIED}" == "no" ]]; then
        printf '%s\n' "${DOD_OUT}" | grep '^FAIL' | sed 's/^/        /'
      fi
    fi
  elif [[ -f "${TASK_DIR}/evidence-pack.yml" ]]; then
    EVIDENCE="evidence-pack"
    VERIFIED="no"
    echo "[2/3] delivery evidence: evidence-pack.yml present, no definition-of-done.json"
  else
    VERIFIED="no"
    echo "[2/3] delivery evidence: none on disk for ${ISSUE_KEY}"
  fi
  if [[ "${VERIFIED}" != "yes" ]]; then
    echo "        closeout recorded as '${STATUS}', but delivery is NOT verified —"
    echo "        an engineering handoff needs a definition-of-done.json that dod-check.py accepts."
  fi
fi

echo "[2/3] telemetry: recording outcome..."
event="completed"
if [[ "${STATUS}" == "blocked" || "${STATUS}" == "needs-context" ]]; then
  event="stopped"
fi
TELEMETRY_ARGS=(
  --field "skill=${SKILL}"
  --field "issue_key=${ISSUE_KEY}"
  --field "status=${STATUS}"
  --field "evidence=${EVIDENCE}"
  --field "verified_delivery=${VERIFIED}"
)
if [[ "${IF_OPEN}" == "true" ]]; then
  TELEMETRY_ARGS+=(--field "closeout=fallback")
fi
"${PYTHON3}" "${TELEMETRY_SCRIPT}" --cache-root "${CACHE_ROOT}" emit "${PROJECT}" "${event}" \
  "${TELEMETRY_ARGS[@]}" >/dev/null

# Mark the task closed so a later `--if-open` fallback is a no-op. The marker
# lives beside the project/issue lines start-task writes, and start-task
# overwrites the file, so a new task clears it.
LAST_CONTEXT="$(agent_skills_last_context_path)"
if [[ -n "${LAST_CONTEXT}" && -f "${LAST_CONTEXT}" ]]; then
  printf 'closed=%s\n' "${ISSUE_KEY}" >> "${LAST_CONTEXT}"
fi

if [[ "${CLEANUP}" == "auto" ]]; then
  case "${STATUS}" in
    blocked|needs-context) CLEANUP="false" ;;
    *) CLEANUP="true" ;;
  esac
fi

if [[ "${CLEANUP}" == "true" ]]; then
  echo "[3/3] cleanup: removing per-task scratch after memory write..."
  # A refusal is reported, not fatal. Cleanup fails closed on an ambiguous
  # target — most often a cache directory created before issue keys were
  # normalised, whose name differs from this key only in case. By the time we
  # get here the durable work is already done: memory was written in step 1 and
  # telemetry in step 2. Failing the whole closeout over undeleted scratch would
  # report a lost task when nothing was lost, and would do it on every task for
  # anyone holding a legacy directory.
  if ! "${PYTHON3}" "${PM_SCRIPT}" --cache-root "${CACHE_ROOT}" cleanup-task "${ISSUE_KEY}"; then
    echo ""
    echo "  NOTE: scratch was NOT removed, and memory was already written, so"
    echo "        nothing durable was lost. Cleanup refuses anything ambiguous"
    echo "        rather than guessing which directory you meant."
    echo "        Remove it by its exact name once you have checked it:"
    echo "          ${PYTHON3} ${PM_SCRIPT} cleanup-task <exact-directory-name>"
  fi
else
  echo "[3/3] cleanup: skipped; per-task scratch preserved for resumption."
fi

echo "== Finish complete =="
