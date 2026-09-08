#!/usr/bin/env bash
# agent-skills migrate — explain and, on request, tidy a pre-v0.37.0 install.
#
# Read-only by default. Nothing here deletes a file that might hold the user's
# only copy of a credential, and nothing copies a secret anywhere without an
# explicit instruction. `--remove-obsolete` removes only the two artifacts that
# carry no information: the `.skills` symlink and `.agent-skills.lock`.
#
# Invoked as: agent-skills migrate [--workspace-root DIR] [--remove-obsolete]

set -uo pipefail

AS_MIGRATE_LIB="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
AS_LIB_DIR="${AS_MIGRATE_LIB}"
export AS_LIB_DIR
# shellcheck source=lib/runtime.sh
. "${AS_LIB_DIR}/runtime.sh"

WORKSPACE_ROOT_ARG=""
REMOVE_OBSOLETE="false"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --workspace-root) WORKSPACE_ROOT_ARG="${2:-}"; shift 2 ;;
    --workspace-root=*) WORKSPACE_ROOT_ARG="${1#*=}"; shift ;;
    --remove-obsolete) REMOVE_OBSOLETE="true"; shift ;;
    --help|-h)
      printf 'Usage: agent-skills migrate [--workspace-root DIR] [--remove-obsolete]\n'
      exit 0
      ;;
    *) as_die "unknown option: $1" 2 ;;
  esac
done

# Where the legacy workspace probably is: the explicit flag, then WORKSPACE_ROOT
# from the environment, then the parent of the clone (setup.init's old default).
resolve_legacy_root() {
  if [ -n "${WORKSPACE_ROOT_ARG}" ]; then
    printf '%s' "${WORKSPACE_ROOT_ARG%/}"
    return 0
  fi
  if [ -n "${WORKSPACE_ROOT:-}" ]; then
    printf '%s' "${WORKSPACE_ROOT%/}"
    return 0
  fi
  local source_dir
  source_dir="$(as_source_dir 2>/dev/null || true)"
  [ -n "${source_dir}" ] || return 1
  dirname "${source_dir}"
}

LEGACY_ROOT="$(resolve_legacy_root || true)"

# True when `link` points into an agent-skills source tree.
#
# The legacy `.skills` symlink pointed at `<clone>/skills`, not into the install
# home, so the install-root ownership test alone would reject a genuine one. Both
# tests together are what let `--remove-obsolete` delete our own link and only
# our own link.
as_link_points_into_source() {
  local link="$1"
  local source_dir source_real target target_real dir
  [ -L "${link}" ] || return 1
  source_dir="$(as_source_dir 2>/dev/null || true)"
  [ -n "${source_dir}" ] || return 1
  source_real="$(as_realpath "${source_dir}" 2>/dev/null || printf '%s' "${source_dir}")"
  target="$(readlink "${link}" 2>/dev/null || true)"
  [ -n "${target}" ] || return 1
  case "${target}" in
    /*) : ;;
    *)
      dir="$(cd -P "$(dirname "${link}")" >/dev/null 2>&1 && pwd)" || return 1
      target="${dir}/${target}"
      ;;
  esac
  # Compare both the literal and resolved forms of both sides. A workspace under
  # a temp dir is reached as /var/... but resolves to /private/var/... on macOS,
  # and a plain string compare of one form against the other never matches.
  target_real="$(as_realpath "${target}" 2>/dev/null || printf '%s' "${target}")"
  case "${target}" in
    "${source_dir}"|"${source_dir}"/*) return 0 ;;
    "${source_real}"|"${source_real}"/*) return 0 ;;
  esac
  case "${target_real}" in
    "${source_dir}"|"${source_dir}"/*) return 0 ;;
    "${source_real}"|"${source_real}"/*) return 0 ;;
  esac
  return 1
}

printf 'agent-skills migrate\n'
printf '  Upgrading from a v0.36.x workspace installation to the global install.\n\n'

if [ -z "${LEGACY_ROOT}" ] || [ ! -d "${LEGACY_ROOT}" ]; then
  printf 'No legacy workspace directory could be located.\n'
  printf 'Nothing to migrate. Run: agent-skills verify\n'
  exit 0
fi

printf 'Legacy workspace: %s\n\n' "${LEGACY_ROOT}"

FOUND_ANY="false"
FOUND_CREDS="false"

printf 'Obsolete artifacts (safe to remove)\n'
for artifact in .skills .agent-skills.lock; do
  if [ -e "${LEGACY_ROOT}/${artifact}" ]; then
    FOUND_ANY="true"
    as_warn "${artifact} is obsolete under the global install"
  fi
done
if [ "${FOUND_ANY}" = "false" ]; then
  as_ok "none found"
fi

printf '\nConfiguration still read for backwards compatibility\n'
for artifact in .env .env.local .jira-config.yml .agent-skills.yml; do
  if [ -f "${LEGACY_ROOT}/${artifact}" ]; then
    FOUND_CREDS="true"
    as_info "${artifact} is still discovered and used by the access resolver"
  fi
done
if [ "${FOUND_CREDS}" = "false" ]; then
  as_ok "none found"
fi

printf '\nWhat changed\n'
printf '  * Skills now come from one global install, not a workspace .skills link.\n'
printf '  * Lifecycle helpers are invoked as `agent-skills start-task`, from any repo.\n'
printf '  * Projects are inferred from each repository; PROJECTS_JSON is no longer needed.\n'
printf '  * Credentials belong to named identities, not to a workspace .env file.\n'

printf '\nRecommended steps\n'
printf '  1. ./setup.init                       install globally (asks for no credentials)\n'
printf '  2. agent-skills verify                confirm every host sees the skills\n'
if [ "${FOUND_CREDS}" = "true" ]; then
  printf '  3. agent-skills access import-legacy  review legacy .env credentials and,\n'
  printf '                                        only if you choose to, store them as\n'
  printf '                                        named identities in the OS keychain\n'
  printf '  4. agent-skills migrate --remove-obsolete\n'
else
  printf '  3. agent-skills migrate --remove-obsolete\n'
fi

printf '\nNot done automatically, on purpose\n'
printf '  * No secret is copied anywhere. `access import-legacy` is opt-in and\n'
printf '    reports what it found before writing anything.\n'
printf '  * .env is never deleted. It may be your only copy of a token, and the\n'
printf '    resolver still reads it, so leaving it in place costs nothing.\n'

if [ "${REMOVE_OBSOLETE}" = "true" ]; then
  printf '\nRemoving obsolete artifacts\n'
  # shellcheck source=lib/install.sh
  . "${AS_LIB_DIR}/install.sh"
  removed=0
  for artifact in .skills .agent-skills.lock; do
    target="${LEGACY_ROOT}/${artifact}"
    if [ -L "${target}" ]; then
      # `.skills` is a symlink agent-skills wrote, but the name is not proof of
      # that: the path comes from --workspace-root or the environment, so a
      # same-named link pointing somewhere else is somebody else's. Every other
      # deletion in this release checks ownership before unlinking; this one used
      # to trust the filename alone.
      if as_is_owned_link "${target}" || as_link_points_into_source "${target}"; then
        rm -f "${target}"
        as_ok "removed ${artifact}"
        removed=$((removed + 1))
      else
        as_warn "left ${artifact} alone: it does not point into an agent-skills tree"
      fi
    elif [ -f "${target}" ]; then
      rm -f "${target}"
      as_ok "removed ${artifact}"
      removed=$((removed + 1))
    fi
  done
  [ "${removed}" -eq 0 ] && as_ok "nothing to remove"
  printf '\nLeft in place: .env, .env.local, .jira-config.yml, .agent-skills.yml\n'
fi

exit 0
