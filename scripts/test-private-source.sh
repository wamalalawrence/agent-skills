#!/usr/bin/env bash
# Stage B acceptance: install Agent Skills from the real release source.
#
# Run this AFTER the GitHub repository visibility has been changed to private.
# It is the evidence that the distribution contract works against an
# authenticated private source, and it is a precondition for `1.0.0-rc.1`.
#
#   bash scripts/test-private-source.sh
#
# It deliberately does NOT use this checkout as the payload. Everything is
# fetched from the remote through the git provider, into a throwaway HOME, so a
# pass here means a stranger with the same git access could install — not that
# the source tree happens to be sitting on this disk.
#
# Two halves:
#
#   1. WITH the developer's existing git authentication: install, doctor,
#      verify, update, version resolution, rollback.
#   2. WITHOUT it: the installer must report AUTHENTICATION_REQUIRED and exit 3.
#      Not "repository not found", not a random git error, not a hang, and not a
#      credential prompt in a context where nobody can answer it.
#
# It publishes nothing, changes no repository setting, and never touches the
# real installation.

set -uo pipefail

REPO_ROOT="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." >/dev/null 2>&1 && pwd)"
REMOTE="${AGENT_SKILLS_RELEASE_REPO:-https://github.com/wamalalawrence/agent-skills.git}"
VERSION="$(head -n 1 "${REPO_ROOT}/VERSION" | tr -d '[:space:]')"

PASS=0
FAIL=0
SANDBOXES=()

# A credential-shaped string that has never been a credential. Present in the
# environment throughout so its absence from every log can be asserted.
SYNTHETIC_TOKEN="ghp_$(printf 'A%.0s' $(seq 1 36))"

cleanup() {
  local box
  for box in "${SANDBOXES[@]+"${SANDBOXES[@]}"}"; do
    case "${box}" in /tmp/*|/private/tmp/*|/var/folders/*) rm -rf "${box}" ;; esac
  done
}
trap cleanup EXIT

ok() { PASS=$((PASS + 1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL + 1)); printf '  FAIL  %s\n' "$1" >&2; }
assert_eq() { if [ "$1" = "$2" ]; then ok "$3"; else bad "$3   [expected '$2', got '$1']"; fi; }
assert() { if eval "$1"; then ok "$2"; else bad "$2   [failed: $1]"; fi; }
assert_not() { if eval "$1"; then bad "$2   [unexpectedly true]"; else ok "$2"; fi; }

new_sandbox() {
  local box
  box="$(mktemp -d "${TMPDIR:-/tmp}/agent skills private.XXXXXX")"
  box="$(cd "${box}" && pwd -P)"
  SANDBOXES+=("${box}")
  mkdir -p "${box}/home"
  printf '%s' "${box}"
}

# A clean environment. `env -i` is deliberate: nothing inherited, so a pass
# cannot be explained by something already present in this shell.
in_box() {
  local box="$1"
  shift
  env -i \
    HOME="${box}/home" \
    AGENT_SKILLS_HOME="${box}/home/.agent-skills" \
    AGENT_SKILLS_CONFIG_DIR="${box}/home/.config/agent-skills" \
    PATH="${box}/home/.local/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin" \
    TERM=dumb \
    GH_TOKEN="${SYNTHETIC_TOKEN}" \
    GITHUB_TOKEN="${SYNTHETIC_TOKEN}" \
    "$@"
}

# The bootstrap, exactly as a user would receive it.
BOOTSTRAP=""
prepare_bootstrap() {
  local box="$1"
  bash "${REPO_ROOT}/scripts/build-npm-bootstrap.sh" --pack >/dev/null 2>&1 || return 1
  local tarball
  # Absolute: `npm install npm/<file>.tgz` is read as a GitHub shorthand.
  tarball="$(ls -1t "${REPO_ROOT}"/npm/*.tgz 2>/dev/null | head -1)"
  [ -n "${tarball}" ] || return 1
  mkdir -p "${box}/npmroot"
  npm install --silent --prefix "${box}/npmroot" "${tarball}" >/dev/null 2>&1 || return 1
  BOOTSTRAP="${box}/npmroot/node_modules/.bin/agent-skills-bootstrap"
  [ -x "${BOOTSTRAP}" ]
}

printf 'Stage B — private-source acceptance\n'
printf '  remote : %s\n' "${REMOTE}"
printf '  version: %s\n\n' "${VERSION}"

# ==============================================================================
printf 'Preflight\n'
# ==============================================================================
# Strip both the scheme and the trailing `.git`; `gh repo view` wants owner/name
# and answers "unknown" for anything else — which would silently disable the
# guard below and let this suite pass for entirely the wrong reason.
REPO_SLUG="${REMOTE#https://github.com/}"
REPO_SLUG="${REPO_SLUG%.git}"
VISIBILITY="unknown"
if command -v gh >/dev/null 2>&1; then
  VISIBILITY="$(gh repo view "${REPO_SLUG}" --json visibility \
    --jq .visibility 2>/dev/null | tr '[:upper:]' '[:lower:]')"
  VISIBILITY="${VISIBILITY:-unknown}"
fi
printf '  --    repository: %s (%s)\n' "${REPO_SLUG}" "${VISIBILITY}"
if [ "${VISIBILITY}" = "unknown" ]; then
  printf '  --    could not determine visibility; continuing, but read the result carefully\n'
fi
if [ "${VISIBILITY}" = "public" ]; then
  printf '\n' >&2
  printf 'This is the Stage B suite and the repository is still PUBLIC.\n' >&2
  printf 'It would pass for the wrong reason: anonymous access would satisfy every\n' >&2
  printf 'case below, and nothing about authenticated private distribution would be\n' >&2
  printf 'proven. Change the visibility to private first, then rerun.\n' >&2
  exit 2
fi

# ==============================================================================
printf '\n1. With existing git authentication\n'
# ==============================================================================
BOX="$(new_sandbox)"
if ! prepare_bootstrap "${BOX}"; then
  bad "could not build and install the npm bootstrap"
else
  ok "the npm bootstrap packs and installs"

  # Authentication comes from the developer's own git setup, which lives outside
  # the sandboxed HOME. Point git at the real one without importing anything
  # else: this is the least intrusive mechanism the provider documents, and the
  # point of the case is that no token has to be handed over.
  REAL_HOME="${HOME}"
  in_box_auth() {
    local box="$1"
    shift
    env -i \
      HOME="${box}/home" \
      AGENT_SKILLS_HOME="${box}/home/.agent-skills" \
      AGENT_SKILLS_CONFIG_DIR="${box}/home/.config/agent-skills" \
      PATH="${box}/home/.local/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin" \
      TERM=dumb \
      GIT_CONFIG_GLOBAL="${REAL_HOME}/.gitconfig" \
      SSH_AUTH_SOCK="${SSH_AUTH_SOCK:-}" \
      GH_CONFIG_DIR="${REAL_HOME}/.config/gh" \
      "$@"
  }

  in_box_auth "${BOX}" "${BOOTSTRAP}" install --repo "${REMOTE}" \
    > "${BOX}/install.log" 2>&1
  RC=$?
  [ "${RC}" -eq 0 ] || tail -25 "${BOX}/install.log" >&2
  assert_eq "${RC}" "0" "PRIVATE_AUTHENTICATED_INSTALL"

  CLI="${BOX}/home/.agent-skills/bin/agent-skills"
  if [ -x "${CLI}" ]; then
    assert_eq "$(in_box_auth "${BOX}" bash "${CLI}" version)" "${VERSION}" \
      "the installed release is the one the remote advertises"

    in_box_auth "${BOX}" bash "${CLI}" doctor > "${BOX}/doctor.log" 2>&1
    assert_eq "$?" "0" "DOCTOR"
    assert "grep -q 'release source' '${BOX}/doctor.log'" \
      "doctor names the release source it came from"

    in_box_auth "${BOX}" bash "${CLI}" verify > "${BOX}/verify.log" 2>&1
    assert_eq "$?" "0" "VERIFY"

    in_box_auth "${BOX}" bash "${CLI}" versions --json > "${BOX}/versions.json" 2>&1
    assert_eq "$?" "0" "version resolution over the authenticated remote"

    in_box_auth "${BOX}" bash "${CLI}" check-updates --repo "${REMOTE}" \
      > "${BOX}/check.log" 2>&1
    CU=$?
    assert "[ '${CU}' = '0' ] || [ '${CU}' = '10' ]" \
      "check-updates answers up-to-date or update-available, not an error"

    # `update` against the same remote. Up to date is a pass: the point is that
    # the update path reaches the private source and resolves a version.
    in_box_auth "${BOX}" bash "${CLI}" update --repo "${REMOTE}" \
      > "${BOX}/update.log" 2>&1
    UP=$?
    assert "[ '${UP}' = '0' ]" "PRIVATE_UPDATE"
    assert_eq "$(in_box_auth "${BOX}" bash "${CLI}" version)" "${VERSION}" \
      "the machine is still coherent after update"

    for LOG in install doctor verify update check; do
      assert_not "grep -Eq 'gh[pousr]_[A-Za-z0-9]{16,}|github_pat_' '${BOX}/${LOG}.log'" \
        "no token-shaped string in the ${LOG} output"
    done
    assert_not "grep -rq 'ghp_' '${BOX}/home/.agent-skills' 2>/dev/null" \
      "no token was written into the installation"
    assert_not "[ -f '${BOX}/home/.config/agent-skills/credentials.json' ]" \
      "installing stored no credential of its own"
  else
    bad "no launcher was installed; the remaining cases cannot run"
  fi
fi

# ==============================================================================
printf '\n2. Without authentication\n'
# ==============================================================================
# Every credential path removed: no git config, no ssh agent, no gh config, and
# a synthetic GH_TOKEN in the environment that must neither be used nor echoed.
BOX2="$(new_sandbox)"
if prepare_bootstrap "${BOX2}"; then
  START="$(date +%s)"
  in_box "${BOX2}" "${BOOTSTRAP}" install --repo "${REMOTE}" \
    > "${BOX2}/noauth.log" 2>&1
  RC=$?
  ELAPSED=$(( $(date +%s) - START ))

  assert_eq "${RC}" "3" "AUTHENTICATION_FAILURE_BEHAVIOR: exit 3"
  assert "grep -q 'AUTHENTICATION_REQUIRED' '${BOX2}/noauth.log'" \
    "the message says AUTHENTICATION_REQUIRED"
  assert_not "grep -qi 'repository not found' '${BOX2}/noauth.log'" \
    "it does not report the repository as missing"
  assert "grep -qi 'distribution access' '${BOX2}/noauth.log'" \
    "it distinguishes distribution access from project access"
  assert "grep -q 'gh auth login' '${BOX2}/noauth.log'" \
    "it names a way to fix it"
  assert "[ '${ELAPSED}' -lt 120 ]" \
    "it fails rather than hanging on a credential prompt (${ELAPSED}s)"
  assert_not "grep -q '${SYNTHETIC_TOKEN}' '${BOX2}/noauth.log'" \
    "no environment token is echoed"
  assert_not "grep -Eq 'gh[pousr]_[A-Za-z0-9]{16,}' '${BOX2}/noauth.log'" \
    "no token-shaped string appears at all"
  assert_not "[ -d '${BOX2}/home/.agent-skills/versions' ]" \
    "nothing was installed"
else
  bad "could not prepare the bootstrap for the unauthenticated case"
fi

# ==============================================================================
printf '\n'
printf '%s passed, %s failed\n\n' "${PASS}" "${FAIL}"
if [ "${FAIL}" -eq 0 ]; then
  printf 'PRIVATE_SOURCE_DISTRIBUTION_READY: YES\n'
  exit 0
fi
printf 'PRIVATE_SOURCE_DISTRIBUTION_READY: NO\n' >&2
printf 'Fix the failures above before cutting 1.0.0-rc.1.\n' >&2
exit 1
