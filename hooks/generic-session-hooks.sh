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
SCRIPTS_DIR="$(cd "${SCRIPT_DIR}/../scripts" && pwd)"
SKILL="${AGENT_SKILLS_ACTIVE_SKILL:-unknown}"

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
    bash "${SCRIPTS_DIR}/start-task.sh" --skill "${SKILL}" || {
      echo "agent-skills: start-task hook failed; continuing without memory" >&2
    }
    ;;
  stop)
    # A hook cannot know whether the work finished, so it must not claim it did.
    # needs-context preserves scratch; the real status comes from the agent.
    bash "${SCRIPTS_DIR}/finish-task.sh" \
      --skill "${SKILL}" \
      --status needs-context \
      --no-cleanup \
      --no-candidates \
      --summary "session ended without an explicit finish-task call" || {
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
