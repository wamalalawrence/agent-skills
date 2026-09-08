#!/usr/bin/env bash
# agent-skills runtime locator.
#
# Sourced by `bin/agent-skills`, `lib/install.sh`, and the lifecycle wrappers.
# It answers four questions, and nothing else:
#
#   1. Where is the canonical install?          AGENT_SKILLS_HOME
#   2. Where is the source tree behind it?      AGENT_SKILLS_SOURCE
#   3. Where does non-secret user state live?   AGENT_SKILLS_CONFIG_DIR
#   4. Which version is installed?              as_installed_version
#
# The whole point of this file is that a skill discovered from an arbitrary
# repository can find the exact same-version scripts and references that belong
# to the release it was loaded from. Before v0.37.0 that was done with relative
# paths like `agent-skills/scripts/start-task.sh`, which only resolved when the
# clone happened to be a sibling of the current directory.
#
# Compatible with bash 3.2 (the system bash on macOS): no associative arrays,
# no `mapfile`, no `${var,,}`. Every path expansion is quoted so directories
# with spaces work.

# ------------------------------------------------------------------------------
# Path helpers
# ------------------------------------------------------------------------------

# Resolve a path to its physical location, following every symlink.
# Prefers python3 (always present for the rest of the toolchain), then GNU/BSD
# realpath, then a pure-shell walk.
as_realpath() {
  local target="$1"
  [ -n "${target}" ] || return 1

  if command -v python3 >/dev/null 2>&1; then
    AS_REALPATH_TARGET="${target}" python3 -c \
      'import os, sys; sys.stdout.write(os.path.realpath(os.environ["AS_REALPATH_TARGET"]))'
    return 0
  fi
  if command -v realpath >/dev/null 2>&1; then
    realpath "${target}" 2>/dev/null && return 0
  fi

  # Pure-shell fallback: walk symlinks by hand, bounded to avoid a link loop.
  local dir base hops=0
  while [ -L "${target}" ] && [ "${hops}" -lt 40 ]; do
    dir="$(cd -P "$(dirname "${target}")" >/dev/null 2>&1 && pwd)"
    base="$(readlink "${target}")"
    case "${base}" in
      /*) target="${base}" ;;
      *) target="${dir}/${base}" ;;
    esac
    hops=$((hops + 1))
  done
  dir="$(cd -P "$(dirname "${target}")" >/dev/null 2>&1 && pwd)" || return 1
  base="$(basename "${target}")"
  if [ "${base}" = "." ] || [ "${base}" = "/" ]; then
    printf '%s' "${dir}"
  else
    printf '%s' "${dir%/}/${base}"
  fi
}

# True when both arguments resolve to the same physical path.
as_same_path() {
  local left right
  left="$(as_realpath "$1" 2>/dev/null || printf '%s' "$1")"
  right="$(as_realpath "$2" 2>/dev/null || printf '%s' "$2")"
  [ "${left}" = "${right}" ]
}

# ------------------------------------------------------------------------------
# Locations
# ------------------------------------------------------------------------------

# The install root. `AGENT_SKILLS_HOME` overrides it, which is what the test
# suite uses to install into a throwaway directory.
as_home() {
  if [ -n "${AGENT_SKILLS_HOME:-}" ]; then
    printf '%s' "${AGENT_SKILLS_HOME%/}"
    return 0
  fi
  printf '%s' "${HOME}/.agent-skills"
}

# Non-secret user configuration and state: credential profile metadata (never
# values), project bindings, and the file-backed secret fallback when no OS
# store is available. Deliberately separate from the install root so
# `uninstall` can remove the install without touching a user's identities.
as_config_dir() {
  if [ -n "${AGENT_SKILLS_CONFIG_DIR:-}" ]; then
    printf '%s' "${AGENT_SKILLS_CONFIG_DIR%/}"
    return 0
  fi
  if [ -n "${XDG_CONFIG_HOME:-}" ]; then
    printf '%s' "${XDG_CONFIG_HOME%/}/agent-skills"
    return 0
  fi
  printf '%s' "${HOME}/.config/agent-skills"
}

as_manifest_path() {
  printf '%s/install.json' "$(as_home)"
}

# The source tree the install points at.
#
# Resolution order:
#   1. AGENT_SKILLS_SOURCE, when it looks like a source tree.
#   2. The realpath of `<home>/skills`, minus the trailing `skills` — this is
#      the normal answer once installed, and it survives the CLI being invoked
#      through two layers of symlink.
#   3. The tree containing this very file, for a not-yet-installed clone.
as_source_dir() {
  local candidate resolved

  if [ -n "${AGENT_SKILLS_SOURCE:-}" ] && as_is_source_tree "${AGENT_SKILLS_SOURCE}"; then
    as_realpath "${AGENT_SKILLS_SOURCE}"
    return 0
  fi

  candidate="$(as_home)/skills"
  if [ -e "${candidate}" ]; then
    resolved="$(as_realpath "${candidate}" 2>/dev/null || true)"
    if [ -n "${resolved}" ] && as_is_source_tree "$(dirname "${resolved}")"; then
      printf '%s' "$(dirname "${resolved}")"
      return 0
    fi
  fi

  if [ -n "${AS_LIB_DIR:-}" ] && as_is_source_tree "${AS_LIB_DIR}/.." ; then
    as_realpath "${AS_LIB_DIR}/.."
    return 0
  fi
  return 1
}

# A source tree is a checkout of this repository: it has VERSION, skills/, and
# scripts/. Checked rather than assumed so a stray directory cannot be adopted.
as_is_source_tree() {
  local dir="$1"
  [ -n "${dir}" ] || return 1
  [ -f "${dir}/VERSION" ] || return 1
  [ -d "${dir}/skills" ] || return 1
  [ -d "${dir}/scripts" ] || return 1
  return 0
}

# ------------------------------------------------------------------------------
# Versions
# ------------------------------------------------------------------------------

as_read_version_file() {
  local file="$1"
  [ -f "${file}" ] || return 1
  head -n 1 "${file}" | tr -d '[:space:]'
}

# Version of the source tree on disk.
as_source_version() {
  local source_dir
  source_dir="$(as_source_dir 2>/dev/null || true)"
  [ -n "${source_dir}" ] || return 1
  as_read_version_file "${source_dir}/VERSION"
}

# Version recorded in the install manifest. Differs from the source version
# when the clone was updated without re-running install; that is drift, and
# `verify` reports it rather than hiding it.
as_installed_version() {
  local manifest
  manifest="$(as_manifest_path)"
  [ -f "${manifest}" ] || return 1
  as_json_field "${manifest}" version
}

as_is_installed() {
  [ -f "$(as_manifest_path)" ]
}

# ------------------------------------------------------------------------------
# Minimal JSON field reader
#
# The manifest is written by this repository and is flat, so a targeted read is
# enough and keeps the shell side dependency-free. Anything structural uses
# python3 instead.
# ------------------------------------------------------------------------------
as_json_field() {
  local file="$1"
  local key="$2"
  [ -f "${file}" ] || return 1
  if command -v python3 >/dev/null 2>&1; then
    AS_JSON_FILE="${file}" AS_JSON_KEY="${key}" python3 -c '
import json
import os
import sys

try:
    with open(os.environ["AS_JSON_FILE"], encoding="utf-8") as handle:
        data = json.load(handle)
except Exception:
    sys.exit(1)
value = data.get(os.environ["AS_JSON_KEY"])
if value is None:
    sys.exit(1)
if isinstance(value, (list, dict)):
    sys.stdout.write(json.dumps(value))
else:
    sys.stdout.write(str(value))
'
    return $?
  fi
  awk -v key="\"${key}\"" '
    index($0, key) {
      line = $0
      sub(/^[^:]*:[[:space:]]*/, "", line)
      gsub(/^"|",?$|,$/, "", line)
      print line
      exit
    }
  ' "${file}"
}

# ------------------------------------------------------------------------------
# Output helpers. Status lines are stable enough to grep in tests.
# ------------------------------------------------------------------------------
as_ok() { printf '  ok    %s\n' "$1"; }
as_warn() { printf '  WARN  %s\n' "$1" >&2; }
as_fail() { printf '  FAIL  %s\n' "$1" >&2; }
as_info() { printf '  --    %s\n' "$1"; }

as_die() {
  printf 'agent-skills: %s\n' "$1" >&2
  exit "${2:-1}"
}
