#!/usr/bin/env bash
# agent-skills doctor — one answer to "what can I actually do here?"
#
# Setup used to provision credentials it could not validate, and every skill then
# carried prose telling the agent to fall back when a tool was missing. Prose is
# not detection. This script probes the environment once and prints the result, so
# a skill plans around what exists instead of discovering it mid-task.
#
# It aggregates the checks that already existed but never ran together:
#   agent-skills verify                installation integrity and host wiring
#   scripts/auth-preflight.py          tracker / document-store config
#   scripts/github-access.sh           the GitHub access ladder
# plus tool detection, build-tool inference, MCP availability, and the state of
# the installation itself: which release is active, where it came from, whether
# anything has drifted, and what a rollback would return to.
#
# It never contacts the network. Everything it reports about the installation
# comes from the local manifest, because "am I offline" is one of the questions
# people run it to answer.
#
# Usage:
#   ./doctor.sh                 full report
#   ./doctor.sh --brief         compact form embedded in start-task.sh output
#   ./doctor.sh --json          machine-readable
#   ./doctor.sh --repo <o/r>    also walk the GitHub access ladder for that repo
#
# Exit codes:
#   0  report produced (this is a report, not a gate)
#   1  a --require-* capability is unavailable
#   2  invalid arguments
#
# It never prints a secret value: only whether one resolves.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON3="${PYTHON3:-python3}"

MODE="full"
TARGET_REPO=""
REQUIRE_TRACKER="false"
REQUIRE_GITHUB="false"

usage() {
  cat <<'EOF'
Usage: ./doctor.sh [--brief|--json] [--repo owner/name] [--require-tracker]
                   [--require-github] [--help]

Probes what this environment can actually do and prints a capability report.

  --brief             Compact one-line-per-capability form.
  --json              JSON object instead of text.
  --repo owner/name   Also walk the GitHub access ladder against this repo.
  --require-tracker   Exit 1 when tracker configuration does not resolve.
  --require-github    Exit 1 when no GitHub access path works.
  --help              Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --brief) MODE="brief"; shift ;;
    --json) MODE="json"; shift ;;
    --repo) TARGET_REPO="${2:-}"; shift 2 ;;
    --repo=*) TARGET_REPO="${1#*=}"; shift ;;
    --require-tracker) REQUIRE_TRACKER="true"; shift ;;
    --require-github) REQUIRE_GITHUB="true"; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

# ---------------------------------------------------------------------------
# Probes. Each sets a `<name>_STATE` of yes|no|unknown and a short detail line.
# ---------------------------------------------------------------------------
have() { command -v "$1" >/dev/null 2>&1; }

tool_version() {
  # First line of `<tool> --version`, trimmed. Never fatal.
  local tool="$1"
  local raw=""
  raw="$("${tool}" --version 2>/dev/null | head -n 1 || true)"
  printf '%s' "${raw//$'\n'/ }"
}

probe_tools() {
  TOOLS_PRESENT=""
  TOOLS_MISSING=""
  local tool
  for tool in git gh jira docker "${PYTHON3}"; do
    if have "${tool}"; then
      TOOLS_PRESENT="${TOOLS_PRESENT}${tool} "
    else
      TOOLS_MISSING="${TOOLS_MISSING}${tool} "
    fi
  done
}

probe_build_tool() {
  # Infer the build entry point from whatever manifest is in the working repo.
  BUILD_TOOL="unknown"
  BUILD_DETAIL="no recognised build manifest in $(pwd)"
  local root
  root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

  if [[ -f "${root}/pom.xml" ]]; then
    BUILD_TOOL="maven"
    BUILD_DETAIL="pom.xml"
    have mvn || BUILD_DETAIL="pom.xml present but mvn is NOT installed"
  elif [[ -f "${root}/build.gradle" || -f "${root}/build.gradle.kts" ]]; then
    BUILD_TOOL="gradle"
    BUILD_DETAIL="build.gradle"
    if [[ ! -x "${root}/gradlew" ]] && ! have gradle; then
      BUILD_DETAIL="build.gradle present but neither ./gradlew nor gradle found"
    fi
  elif [[ -f "${root}/package.json" ]]; then
    BUILD_TOOL="node"
    if [[ -f "${root}/pnpm-lock.yaml" ]]; then BUILD_DETAIL="package.json + pnpm-lock.yaml"
    elif [[ -f "${root}/yarn.lock" ]]; then BUILD_DETAIL="package.json + yarn.lock"
    elif [[ -f "${root}/bun.lockb" ]]; then BUILD_DETAIL="package.json + bun.lockb"
    else BUILD_DETAIL="package.json + npm"; fi
    have node || BUILD_DETAIL="${BUILD_DETAIL} (node is NOT installed)"
  elif [[ -f "${root}/pyproject.toml" || -f "${root}/requirements.txt" ]]; then
    BUILD_TOOL="python"
    BUILD_DETAIL="pyproject.toml / requirements.txt"
  elif [[ -f "${root}/go.mod" ]]; then
    BUILD_TOOL="go"
    BUILD_DETAIL="go.mod"
    have go || BUILD_DETAIL="go.mod present but go is NOT installed"
  elif [[ -f "${root}/Cargo.toml" ]]; then
    BUILD_TOOL="cargo"
    BUILD_DETAIL="Cargo.toml"
    have cargo || BUILD_DETAIL="Cargo.toml present but cargo is NOT installed"
  fi
}

probe_docker() {
  DOCKER_STATE="no"
  DOCKER_DETAIL="docker not installed"
  if have docker; then
    if docker info >/dev/null 2>&1; then
      DOCKER_STATE="yes"
      DOCKER_DETAIL="daemon reachable"
    else
      DOCKER_STATE="no"
      DOCKER_DETAIL="docker installed but the daemon is not reachable"
    fi
  fi
}

probe_tracker() {
  TRACKER_STATE="unknown"
  TRACKER_DETAIL="auth-preflight.py not found"
  local script="${SCRIPT_DIR}/auth-preflight.py"
  [[ -f "${script}" ]] || return 0

  local out=""
  out="$(${PYTHON3} "${script}" 2>&1)"
  local rc=$?
  case "${rc}" in
    0)
      TRACKER_STATE="yes"
      TRACKER_DETAIL="configuration resolves"
      ;;
    1)
      TRACKER_STATE="no"
      # Surface the specific missing field, never a value.
      TRACKER_DETAIL="$(printf '%s' "${out}" | grep -m1 -E '^\s+- ' | sed 's/^[[:space:]]*-[[:space:]]*//')"
      [[ -n "${TRACKER_DETAIL}" ]] || TRACKER_DETAIL="configuration incomplete"
      ;;
    *)
      TRACKER_STATE="unknown"
      TRACKER_DETAIL="preflight could not run (exit ${rc})"
      ;;
  esac
}

probe_github() {
  GITHUB_STATE="unknown"
  GITHUB_DETAIL="no target repo supplied; pass --repo owner/name to test access"
  if have gh; then
    if gh auth status >/dev/null 2>&1; then
      GITHUB_DETAIL="gh is authenticated; access to a specific repo untested"
      GITHUB_STATE="unknown"
    else
      GITHUB_STATE="no"
      GITHUB_DETAIL="gh installed but not logged in"
    fi
  else
    GITHUB_DETAIL="gh not installed; git credential helpers may still work"
  fi

  [[ -n "${TARGET_REPO}" ]] || return 0
  local ladder="${SCRIPT_DIR}/github-access.sh"
  if [[ ! -x "${ladder}" ]]; then
    GITHUB_DETAIL="github-access.sh not executable"
    return 0
  fi
  local out=""
  out="$(bash "${ladder}" "${TARGET_REPO}" 2>&1)"
  if printf '%s' "${out}" | grep -q '^result:'; then
    GITHUB_STATE="yes"
    GITHUB_DETAIL="$(printf '%s' "${out}" | grep -m1 '^result:' | sed 's/^result:[[:space:]]*/via /') for ${TARGET_REPO}"
  else
    GITHUB_STATE="no"
    GITHUB_DETAIL="no access path worked for ${TARGET_REPO}"
  fi
}

probe_mcp() {
  # MCP is host-owned configuration. agent-skills ships none and enables none;
  # this only reports whether the host has any, so a skill can prefer an MCP
  # tool over shelling out. See docs/mcp.md.
  MCP_STATE="no"
  MCP_DETAIL="no MCP configuration found (agent-skills ships none by design)"
  local found=""
  local candidate
  local root
  root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  for candidate in \
    "${root}/.mcp.json" \
    "${root}/mcp.json" \
    "${root}/.cursor/mcp.json" \
    "${root}/.kiro/settings/mcp.json" \
    "${root}/.vscode/mcp.json" \
    "${HOME}/.kiro/settings/mcp.json" \
    "${HOME}/.cursor/mcp.json" \
    "${HOME}/.claude.json"; do
    [[ -f "${candidate}" ]] && found="${found}${candidate} "
  done
  if [[ -n "${found}" ]]; then
    MCP_STATE="yes"
    MCP_DETAIL="config present: ${found%% }"
  fi
}

probe_memory() {
  KNOWLEDGE_STATE="no"
  KNOWLEDGE_DETAIL="no committed knowledge base in this repository"
  local root
  root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  if [[ -d "${root}/.agent-skills/knowledge" ]]; then
    local lessons=0
    lessons="$(find "${root}/.agent-skills/knowledge/lessons" -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"
    KNOWLEDGE_STATE="yes"
    KNOWLEDGE_DETAIL="${root}/.agent-skills/knowledge (${lessons} lesson(s))"
  fi
}

# Where the skills came from and which model is in force. A skill that knows
# this can name the right remediation instead of guessing at a layout.
probe_install() {
  INSTALL_STATE="no"
  INSTALL_DETAIL="not installed; run: npx @wamalalawrence/agent-skills install"
  INSTALL_VERSION=""
  INSTALL_ROOT=""
  INSTALL_MODE=""
  INSTALL_CHANNEL=""
  INSTALL_PROVIDER=""
  INSTALL_PROVIDER_SOURCE=""
  INSTALL_ROLLBACK=""
  INSTALL_SKILLS=""
  INSTALL_HOSTS=""
  INSTALL_FOLLOW=""
  INSTALL_PATH_STATE="no"
  INSTALL_PATH_DETAIL="agent-skills is not on PATH"
  INSTALL_DRIFT=""
  INSTALL_BROKEN=""

  local lib_dir="${AS_LIB_DIR:-${REPO_ROOT}/lib}"
  if [[ ! -f "${lib_dir}/runtime.sh" ]]; then
    INSTALL_DETAIL="lib/runtime.sh not reachable; this release looks incomplete"
    return 0
  fi
  # shellcheck source=lib/runtime.sh
  AS_LIB_DIR="${lib_dir}" . "${lib_dir}/runtime.sh"
  INSTALL_ROOT="$(as_home)"

  if as_is_installed; then
    INSTALL_VERSION="$(as_installed_version 2>/dev/null || printf 'unknown')"
    INSTALL_STATE="yes"
    INSTALL_DETAIL="v${INSTALL_VERSION} at ${INSTALL_ROOT}"
  fi

  # Everything below reads the install manifest, which records where this
  # machine's releases come from. Nothing here contacts the network: doctor must
  # work offline, because the machine being offline is one of the things people
  # run it to find out about.
  local manifest
  manifest="$(as_manifest_path)"
  if [[ -f "${manifest}" ]]; then
    local fields
    fields="$(AS_MF="${manifest}" ${PYTHON3} -c '
import json
import os

try:
    with open(os.environ["AS_MF"], encoding="utf-8") as handle:
        data = json.load(handle)
except Exception:
    raise SystemExit(0)
provider = data.get("provider", {}) or {}
print(data.get("mode", ""))
print(data.get("channel", ""))
print(provider.get("id", ""))
print(provider.get("description", ""))
print(" ".join(data.get("hosts", []) or []))
# The line this machine follows, which is what decides what the next update
# offers. It differs from "channel" whenever an rc machine is running the
# stable release that superseded its candidate.
follow = data.get("follow_channel") or data.get("channel") or ""
print(follow if follow in ("stable", "rc", "any") else "stable")
' 2>/dev/null || true)"
    INSTALL_MODE="$(printf '%s\n' "${fields}" | sed -n '1p')"
    INSTALL_CHANNEL="$(printf '%s\n' "${fields}" | sed -n '2p')"
    INSTALL_PROVIDER="$(printf '%s\n' "${fields}" | sed -n '3p')"
    INSTALL_PROVIDER_SOURCE="$(printf '%s\n' "${fields}" | sed -n '4p')"
    INSTALL_HOSTS="$(printf '%s\n' "${fields}" | sed -n '5p')"
    INSTALL_FOLLOW="$(printf '%s\n' "${fields}" | sed -n '6p')"
  fi

  local active source_version
  active="$(as_active_version 2>/dev/null || printf '')"
  source_version="$(as_source_version 2>/dev/null || true)"
  if [[ -n "${source_version}" && -n "${INSTALL_VERSION}" && "${source_version}" != "${INSTALL_VERSION}" ]]; then
    INSTALL_DRIFT="manifest v${INSTALL_VERSION}, active release v${source_version}"
  elif [[ -n "${active}" && -n "${INSTALL_VERSION}" && "${active}" != "${INSTALL_VERSION}" ]]; then
    INSTALL_DRIFT="current -> ${active}, manifest v${INSTALL_VERSION}"
  fi

  INSTALL_ROLLBACK="$(as_rollback_candidate 2>/dev/null || printf '')"

  # A broken link here is the difference between "installed" and "installed and
  # usable", and it is invisible until a skill fails to load.
  local tree
  for tree in current skills scripts lib bin docs hooks; do
    local path="${INSTALL_ROOT}/${tree}"
    if [[ -L "${path}" && ! -e "${path}" ]]; then
      INSTALL_BROKEN="${INSTALL_BROKEN}${tree} "
    fi
  done

  local skills_dir="${INSTALL_ROOT}/skills"
  if [[ -d "${skills_dir}" ]]; then
    local count=0 entry
    for entry in "${skills_dir}"/*; do
      [[ -f "${entry}/SKILL.md" ]] && count=$((count + 1))
    done
    INSTALL_SKILLS="${count}"
  fi

  if have agent-skills; then
    INSTALL_PATH_STATE="yes"
    INSTALL_PATH_DETAIL="$(command -v agent-skills)"
  elif [[ -x "${INSTALL_ROOT}/bin/agent-skills" ]]; then
    INSTALL_PATH_DETAIL="not on PATH; use ${INSTALL_ROOT}/bin/agent-skills"
  fi

  # Context Optimizer travels inside the release, so its availability is a
  # property of the active release rather than a separate installation.
  CONTEXT_STATE="no"
  CONTEXT_DETAIL="context runtime not reachable in the active release"
  local context_script="${REPO_ROOT}/scripts/context.py"
  [[ -f "${context_script}" ]] || context_script="${INSTALL_ROOT}/scripts/context.py"
  if [[ -f "${context_script}" ]]; then
    if ${PYTHON3} "${context_script}" --help >/dev/null 2>&1; then
      CONTEXT_STATE="yes"
      CONTEXT_DETAIL="context-optimizer skill and runtime present, same release"
    else
      CONTEXT_DETAIL="scripts/context.py present but not runnable"
    fi
  fi

  MODE_STATE="unknown"
  MODE_DETAIL="could not determine the execution mode"
  local ctx="${REPO_ROOT}/scripts/project-context.py"
  if [[ -f "${ctx}" ]]; then
    local mode=""
    mode="$(${PYTHON3} "${ctx}" --field mode 2>/dev/null || true)"
    if [[ -n "${mode}" ]]; then
      MODE_STATE="yes"
      MODE_DETAIL="${mode}"
    fi
  fi
}

# Execution Guard: which hosts on this machine will actually stop a dangerous
# command before it runs. A user needs to know this per host, because the answer
# genuinely differs — some hosts can block, some can only be given static rules,
# and some offer no pre-execution interception point at all.
probe_execution_guard() {
  GUARD_STATE="unknown"
  GUARD_DETAIL="scripts/guard.py not reachable"
  GUARD_ROWS=""
  local guard="${REPO_ROOT}/scripts/guard.py"
  [[ -f "${guard}" ]] || return 0
  local out=""
  out="$(${PYTHON3} "${guard}" doctor --format json 2>/dev/null || true)"
  [[ -n "${out}" ]] || return 0
  GUARD_ROWS="$(printf '%s' "${out}" | ${PYTHON3} -c '
import json
import sys

try:
    hosts = json.load(sys.stdin)["hosts"]
except Exception:
    sys.exit(0)
for host in hosts:
    print("%s\t%s" % (host["label"], host["effective"]))
' 2>/dev/null || true)"
  local enforced
  enforced="$(printf '%s' "${GUARD_ROWS}" | grep -c "enforced$" || true)"
  if [[ "${enforced}" -gt 0 ]]; then
    GUARD_STATE="yes"
    GUARD_DETAIL="${enforced} host(s) enforce before execution"
  else
    GUARD_STATE="no"
    GUARD_DETAIL="no host enforces here; run: agent-skills guard install"
  fi
}

# Which credential backend would be used. Reports availability only — this must
# never read or print a secret value.
probe_secret_backend() {
  SECRET_BACKEND_STATE="unknown"
  SECRET_BACKEND_DETAIL="scripts/access.py not reachable"
  local access="${REPO_ROOT}/scripts/access.py"
  [[ -f "${access}" ]] || return 0
  local out=""
  out="$(${PYTHON3} "${access}" backend --json 2>/dev/null || true)"
  [[ -n "${out}" ]] || return 0
  local name secure
  name="$(printf '%s' "${out}" | ${PYTHON3} -c \
    'import json,sys; print(json.load(sys.stdin).get("active_label",""))' 2>/dev/null || true)"
  secure="$(printf '%s' "${out}" | ${PYTHON3} -c \
    'import json,sys; print("yes" if json.load(sys.stdin).get("secure") else "no")' \
    2>/dev/null || true)"
  [[ -n "${name}" ]] || return 0
  if [[ "${secure}" == "yes" ]]; then
    SECRET_BACKEND_STATE="yes"
    SECRET_BACKEND_DETAIL="${name}"
  else
    SECRET_BACKEND_STATE="no"
    SECRET_BACKEND_DETAIL="${name} — no OS credential store available here"
  fi
}

run_probes() {
  probe_install
  probe_secret_backend
  probe_execution_guard
  probe_tools
  probe_build_tool
  probe_docker
  probe_tracker
  probe_github
  probe_mcp
  probe_memory
}

# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------
mark() {
  case "$1" in
    yes) printf 'ok  ' ;;
    no) printf 'NO  ' ;;
    *) printf '?   ' ;;
  esac
}

render_brief() {
  echo "  capability report:"
  printf '    %sinstall          %s\n' "$(mark "${INSTALL_STATE}")" "${INSTALL_DETAIL}"
  if [[ -n "${INSTALL_DRIFT}" ]]; then
    printf '    NO  version drift    %s\n' "${INSTALL_DRIFT}"
  fi
  printf '    %smode             %s\n' "$(mark "${MODE_STATE}")" "${MODE_DETAIL}"
  printf '    %ssecret store     %s\n' "$(mark "${SECRET_BACKEND_STATE}")" "${SECRET_BACKEND_DETAIL}"
  printf '    %stracker config   %s\n' "$(mark "${TRACKER_STATE}")" "${TRACKER_DETAIL}"
  printf '    %sgithub access    %s\n' "$(mark "${GITHUB_STATE}")" "${GITHUB_DETAIL}"
  printf '    %sbuild tool       %s (%s)\n' "$(mark "$([[ "${BUILD_TOOL}" == "unknown" ]] && echo no || echo yes)")" \
    "${BUILD_TOOL}" "${BUILD_DETAIL}"
  printf '    %sdocker           %s\n' "$(mark "${DOCKER_STATE}")" "${DOCKER_DETAIL}"
  printf '    %smcp              %s\n' "$(mark "${MCP_STATE}")" "${MCP_DETAIL}"
  printf '    %srepo knowledge   %s\n' "$(mark "${KNOWLEDGE_STATE}")" "${KNOWLEDGE_DETAIL}"
  printf '    %sexecution guard  %s\n' "$(mark "${GUARD_STATE}")" "${GUARD_DETAIL}"
  if [[ -n "${TOOLS_MISSING// /}" ]]; then
    printf '    --  not installed: %s\n' "${TOOLS_MISSING% }"
  fi
  echo "    Plan around this. Do not propose a path the report says is unavailable."
}

render_full() {
  echo "== agent-skills doctor =="
  echo "  repo root:  $(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  echo "  skills src: ${REPO_ROOT}/skills"
  echo ""
  echo "Installation"
  printf '  %sinstalled — %s\n' "$(mark "${INSTALL_STATE}")" "${INSTALL_DETAIL}"
  [[ -n "${INSTALL_MODE}" ]] && printf '  --  install kind — %s\n' "${INSTALL_MODE}"
  [[ -n "${INSTALL_CHANNEL}" ]] && printf '  --  release channel — %s\n' "${INSTALL_CHANNEL}"
  if [[ -n "${INSTALL_FOLLOW}" && "${INSTALL_FOLLOW}" != "${INSTALL_CHANNEL}" ]]; then
    printf '  --  following — %s channel (what the next update offers)\n' "${INSTALL_FOLLOW}"
  fi
  if [[ -n "${INSTALL_PROVIDER}" ]]; then
    printf '  --  release source — %s (%s)\n' "${INSTALL_PROVIDER}" "${INSTALL_PROVIDER_SOURCE}"
  fi
  printf '  --  skills installed — %s\n' "${INSTALL_SKILLS:-0}"
  printf '  --  host registrations — %s\n' "${INSTALL_HOSTS:-none}"
  printf '  %sagent-skills on PATH — %s\n' "$(mark "${INSTALL_PATH_STATE}")" "${INSTALL_PATH_DETAIL}"
  if [[ -n "${INSTALL_DRIFT}" ]]; then
    printf '  NO  version drift — %s\n' "${INSTALL_DRIFT}"
    echo "      Run: agent-skills install"
  elif [[ "${INSTALL_STATE}" == "yes" ]]; then
    printf '  ok  version coherence — runtime, skills, and manifest agree\n'
  fi
  if [[ -n "${INSTALL_BROKEN}" ]]; then
    printf '  NO  broken links — %s\n' "${INSTALL_BROKEN% }"
  fi
  if [[ -n "${INSTALL_ROLLBACK}" ]]; then
    printf '  --  previous release — v%s (agent-skills rollback)\n' "${INSTALL_ROLLBACK}"
  else
    printf '  --  previous release — none retained yet\n'
  fi
  printf '  %scontext optimizer — %s\n' "$(mark "${CONTEXT_STATE}")" "${CONTEXT_DETAIL}"
  printf '  %sexecution mode — %s\n' "$(mark "${MODE_STATE}")" "${MODE_DETAIL}"
  printf '  %ssecret storage — %s\n' "$(mark "${SECRET_BACKEND_STATE}")" "${SECRET_BACKEND_DETAIL}"
  echo ""
  echo "Tools"
  echo "  present: ${TOOLS_PRESENT:-none}"
  echo "  missing: ${TOOLS_MISSING:-none}"
  echo "  capability view: agent-skills tools status  (per engineering tool, no secrets)"
  echo ""
  echo "Build"
  printf '  %s%s — %s\n' "$(mark "$([[ "${BUILD_TOOL}" == "unknown" ]] && echo no || echo yes)")" \
    "${BUILD_TOOL}" "${BUILD_DETAIL}"
  printf '  %sdocker — %s\n' "$(mark "${DOCKER_STATE}")" "${DOCKER_DETAIL}"
  echo ""
  echo "Access"
  printf '  %stracker / document store — %s\n' "$(mark "${TRACKER_STATE}")" "${TRACKER_DETAIL}"
  printf '  %sgithub — %s\n' "$(mark "${GITHUB_STATE}")" "${GITHUB_DETAIL}"
  printf '  %smcp — %s\n' "$(mark "${MCP_STATE}")" "${MCP_DETAIL}"
  echo ""
  echo "Memory"
  printf '  %srepo knowledge base — %s\n' "$(mark "${KNOWLEDGE_STATE}")" "${KNOWLEDGE_DETAIL}"
  echo ""
  echo "Execution Guard"
  if [[ -n "${GUARD_ROWS}" ]]; then
    printf '%s\n' "${GUARD_ROWS}" | while IFS=$'\t' read -r label level; do
      [[ -n "${label}" ]] || continue
      printf '  %-30s %s\n' "${label}" "$(printf '%s' "${level}" | tr '[:lower:]' '[:upper:]')"
    done
    echo "  enforced = the host consults the guard before the tool call and honours"
    echo "  the answer; available = it can, but is not registered here yet; partial ="
    echo "  static rules only; advisory = no pre-execution hook, wrapper mode only."
    if [[ "${GUARD_STATE}" != "yes" ]]; then
      echo "  Register with: agent-skills guard install"
    fi
  else
    printf '  %s%s\n' "$(mark "${GUARD_STATE}")" "${GUARD_DETAIL}"
  fi
  echo ""
  echo "Notes"
  echo "  This report says what is possible, not what is permitted. The"
  echo "  destructive-action safety floor still applies to everything marked ok."
  echo "  Execution Guard enforces part of that floor at the moment of execution;"
  echo "  it does not replace the policy, and no host makes the machine safe."
  echo "  No secret value is read or printed — only whether one resolves."
  if [[ "${TRACKER_STATE}" != "yes" ]]; then
    echo "  Tracker unavailable: use the user's description as the issue brief"
    echo "  rather than guessing ticket intent from a key or branch name."
  fi
}

json_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

render_json() {
  printf '{\n'
  printf '  "install": "%s",\n' "${INSTALL_STATE}"
  printf '  "install_detail": "%s",\n' "$(json_escape "${INSTALL_DETAIL}")"
  printf '  "installed_version": "%s",\n' "$(json_escape "${INSTALL_VERSION}")"
  printf '  "install_root": "%s",\n' "$(json_escape "${INSTALL_ROOT}")"
  printf '  "install_kind": "%s",\n' "$(json_escape "${INSTALL_MODE}")"
  printf '  "release_channel": "%s",\n' "$(json_escape "${INSTALL_CHANNEL}")"
  printf '  "follow_channel": "%s",\n' "$(json_escape "${INSTALL_FOLLOW}")"
  printf '  "release_provider": "%s",\n' "$(json_escape "${INSTALL_PROVIDER}")"
  printf '  "release_source": "%s",\n' "$(json_escape "${INSTALL_PROVIDER_SOURCE}")"
  printf '  "skills_installed": "%s",\n' "$(json_escape "${INSTALL_SKILLS}")"
  printf '  "host_registrations": "%s",\n' "$(json_escape "${INSTALL_HOSTS}")"
  printf '  "cli_on_path": "%s",\n' "${INSTALL_PATH_STATE}"
  printf '  "version_drift": "%s",\n' "$(json_escape "${INSTALL_DRIFT}")"
  printf '  "broken_links": "%s",\n' "$(json_escape "${INSTALL_BROKEN% }")"
  printf '  "rollback_candidate": "%s",\n' "$(json_escape "${INSTALL_ROLLBACK}")"
  printf '  "context_optimizer": "%s",\n' "${CONTEXT_STATE}"
  printf '  "mode": "%s",\n' "$(json_escape "${MODE_DETAIL}")"
  printf '  "secret_backend": "%s",\n' "${SECRET_BACKEND_STATE}"
  printf '  "secret_backend_detail": "%s",\n' "$(json_escape "${SECRET_BACKEND_DETAIL}")"
  printf '  "tools_present": "%s",\n' "$(json_escape "${TOOLS_PRESENT% }")"
  printf '  "tools_missing": "%s",\n' "$(json_escape "${TOOLS_MISSING% }")"
  printf '  "build_tool": "%s",\n' "$(json_escape "${BUILD_TOOL}")"
  printf '  "build_detail": "%s",\n' "$(json_escape "${BUILD_DETAIL}")"
  printf '  "docker": "%s",\n' "${DOCKER_STATE}"
  printf '  "tracker": "%s",\n' "${TRACKER_STATE}"
  printf '  "tracker_detail": "%s",\n' "$(json_escape "${TRACKER_DETAIL}")"
  printf '  "github": "%s",\n' "${GITHUB_STATE}"
  printf '  "github_detail": "%s",\n' "$(json_escape "${GITHUB_DETAIL}")"
  printf '  "mcp": "%s",\n' "${MCP_STATE}"
  printf '  "repo_knowledge": "%s",\n' "${KNOWLEDGE_STATE}"
  printf '  "execution_guard": "%s",\n' "${GUARD_STATE}"
  printf '  "execution_guard_detail": "%s"\n' "$(json_escape "${GUARD_DETAIL}")"
  printf '}\n'
}

run_probes

case "${MODE}" in
  brief) render_brief ;;
  json) render_json ;;
  *) render_full ;;
esac

EXIT=0
if [[ "${REQUIRE_TRACKER}" == "true" && "${TRACKER_STATE}" != "yes" ]]; then
  echo "FAIL required capability unavailable: tracker configuration" >&2
  EXIT=1
fi
if [[ "${REQUIRE_GITHUB}" == "true" && "${GITHUB_STATE}" != "yes" ]]; then
  echo "FAIL required capability unavailable: GitHub access" >&2
  EXIT=1
fi
exit "${EXIT}"
