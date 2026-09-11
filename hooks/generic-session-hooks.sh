#!/usr/bin/env bash
# OPTIONAL agent-skills lifecycle hook, for any host that can run a shell command
# on session start and session stop.
#
# This is a template. Nothing in agent-skills requires it — see hooks/README.md
# for why the hooks are not installed for you.
#
# Usage from your host's hook mechanism:
#   generic-session-hooks.sh start
#   generic-session-hooks.sh stop
#
# Both subcommands are deliberately non-fatal. A hook that fails a session
# because memory could not be read is worse than a session without memory.
#
# Set AGENT_SKILLS_ACTIVE_SKILL for honest per-skill telemetry attribution;
# without it, events are recorded against "unknown".

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL="${AGENT_SKILLS_ACTIVE_SKILL:-unknown}"

# Prefer the stable CLI, which resolves the installed release from anywhere.
# Fall back to the absolute launcher, then to the scripts directory beside this
# file, so the template also works in a clone with nothing installed yet.
as_lifecycle() {
  local subcommand="$1"
  shift
  if command -v agent-skills >/dev/null 2>&1; then
    agent-skills "${subcommand}" "$@"
    return $?
  fi
  local launcher="${AGENT_SKILLS_HOME:-${HOME}/.agent-skills}/bin/agent-skills"
  if [[ -x "${launcher}" ]]; then
    "${launcher}" "${subcommand}" "$@"
    return $?
  fi
  local scripts_dir=""
  scripts_dir="$(cd "${SCRIPT_DIR}/../scripts" 2>/dev/null && pwd || true)"
  if [[ -n "${scripts_dir}" && -f "${scripts_dir}/${subcommand}.sh" ]]; then
    bash "${scripts_dir}/${subcommand}.sh" "$@"
    return $?
  fi
  echo "agent-skills: cannot locate the ${subcommand} helper" >&2
  return 1
}

usage() {
  cat <<'EOF'
Usage: generic-session-hooks.sh {start|stop}

  start  Load org memory, project memory, the repo knowledge base, and the
         capability report. Reads only; writes no knowledge.

  stop   Record a conservative closeout so a crashed or abandoned session does
         not lose what it learned. Uses --status needs-context, which PRESERVES
         per-task scratch and the working branch.

Neither subcommand replaces the agent's own finish-task.sh call with a real
summary and status. This is a floor, not a substitute.
EOF
}

case "${1:-}" in
  start)
    as_lifecycle start-task --skill "${SKILL}" || {
      echo "agent-skills: start-task hook failed; continuing without memory" >&2
    }
    ;;
  stop)
    # A hook cannot know whether the work finished, so it must not claim it did.
    # needs-context preserves scratch; the real status comes from the agent.
    as_lifecycle finish-task --if-open \
      --skill "${SKILL}" \
      --status needs-context \
      --no-cleanup \
      --no-candidates \
      --summary "session stopped before an explicit finish-task call" || {
      echo "agent-skills: finish-task hook failed; scratch left in place" >&2
    }
    ;;
  --help | -h | "")
    usage
    ;;
  *)
    echo "Unknown subcommand: ${1}" >&2
    usage >&2
    exit 2
    ;;
esac

exit 0
