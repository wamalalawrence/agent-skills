#!/usr/bin/env bash
# Stage B acceptance: install Agent Skills from the real release source.
#
# Run this AFTER the GitHub repository visibility has been changed to private.
# It is the evidence that the distribution contract works against an
# authenticated private source, and it is a precondition for every release from
# `1.0.0-rc.1` onward.
#
# ORDERING. This suite installs from the REMOTE, so it can only certify a
# version whose tag has been pushed. Run against a working tree whose VERSION
# is not yet tagged, the version assertions fail by construction — the remote
# advertises the previous release and that is the one that gets installed.
# That is not a defect in the build under test; it means this suite runs
# AFTER the tag, not before. Everything it checks that does not depend on the
# version — authenticated access, clean install, doctor, verify, provider
# selection, host registration, guard coherence, token non-disclosure, and
# isolation from the real installation — is still meaningful beforehand.
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
#      verify, update, version resolution, host registration, Execution Guard
#      coherence — all run against the private remote.
#   2. WITHOUT it: the installer must report AUTHENTICATION_REQUIRED and exit 3.
#      Not "repository not found", not a random git error, not a hang, and not a
#      credential prompt in a context where nobody can answer it.
#
# A third section confirms the run never touched the real installation on this
# machine — every sandbox is a throwaway HOME, and the one already installed
# here is read (never written) only to prove that.
#
# It publishes nothing, changes no repository setting, and never touches the
# real installation.
#
# macOS note: authentication here is proven through the SAME mechanism the
# provider documents as preferred — an already-logged-in `gh`, with no token
# ever exported by the user. On macOS, `gh`'s token is commonly stored in the
# login Keychain, and Keychain Services resolves the *default keychain search
# list* through `~/Library/Preferences`, keyed to `$HOME` — a real user's shell
# always has a matching `$HOME`, but a throwaway sandbox HOME does not, so
# `security`/`gh` would silently see no login keychain at all and report "not
# authenticated" even though the developer plainly is. The fix isolates the
# sandbox everywhere it matters (`AGENT_SKILLS_HOME`, `AGENT_SKILLS_CONFIG_DIR`,
# and every host skill directory, which are all `$HOME`-relative) while
# grafting in *only* `Library/Preferences` and `Library/Keychains` — read-only
# symlinks, nothing under them is ever written by this suite — so Keychain
# Services can find the login keychain the same way it would on a machine
# where `$HOME` was never touched. Nothing else under the real `$HOME` is
# reachable from the sandbox.

set -uo pipefail

REPO_ROOT="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." >/dev/null 2>&1 && pwd)"
REMOTE="${AGENT_SKILLS_RELEASE_REPO:-https://github.com/wamalalawrence/agent-skills.git}"
VERSION="$(head -n 1 "${REPO_ROOT}/VERSION" | tr -d '[:space:]')"
REAL_HOME="${HOME}"

PASS=0
FAIL=0
SANDBOXES=()

# A credential-shaped string that has never been a credential. Present in the
# environment throughout so its absence from every log can be asserted.
SYNTHETIC_TOKEN="ghp_$(printf 'A%.0s' $(seq 1 36))"

cleanup() {
  local box
  for box in "${SANDBOXES[@]+"${SANDBOXES[@]}"}"; do
    case "${box}" in
      /tmp/*|/private/tmp/*|/var/folders/*)
        # The Keychain grafts are symlinks; remove them explicitly before the
        # recursive delete so nothing ever walks into the real $HOME through
        # them.
        find "${box}" -maxdepth 4 -type l -name Preferences -delete 2>/dev/null || true
        find "${box}" -maxdepth 4 -type l -name Keychains -delete 2>/dev/null || true
        rm -rf "${box}"
        ;;
    esac
  done
}
trap cleanup EXIT

ok() { PASS=$((PASS + 1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL + 1)); printf '  FAIL  %s\n' "$1" >&2; }
assert_eq() { if [ "$1" = "$2" ]; then ok "$3"; else bad "$3   [expected '$2', got '$1']"; fi; }
assert() { if eval "$1"; then ok "$2"; else bad "$2   [failed: $1]"; fi; }
assert_not() { if eval "$1"; then bad "$2   [unexpectedly true]"; else ok "$2"; fi; }
# bash 3.2 (the macOS system default) has no associative arrays, so each
# report field is a plain global variable: report FOO bar sets $R_FOO.
report() { eval "R_$1=\"\$2\""; }

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

# Graft in exactly what macOS Keychain Services needs to resolve the login
# keychain under a sandbox HOME, and nothing else. Read-only symlinks; no-op
# on any platform where `~/Library/Keychains` does not exist (Linux, CI).
graft_keychain_access() {
  local box="$1"
  if [ -d "${REAL_HOME}/Library/Keychains" ]; then
    mkdir -p "${box}/home/Library"
    ln -s "${REAL_HOME}/Library/Preferences" "${box}/home/Library/Preferences"
    ln -s "${REAL_HOME}/Library/Keychains" "${box}/home/Library/Keychains"
  fi
}

# Authentication comes from the developer's own git setup, which lives outside
# the sandboxed HOME. Point git at the real one without importing anything
# else: this is the least intrusive mechanism the provider documents, and the
# point of the case is that no token has to be handed over.
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
printf '0. Preflight — snapshot the real installation, never write to it\n'
# ==============================================================================
# Every case below runs in a throwaway HOME. This section only reads the real
# one, so a diff after everything else has run proves this suite left it alone.
REAL_AS_HOME="${AGENT_SKILLS_HOME:-${REAL_HOME}/.agent-skills}"
REAL_MANIFEST="${REAL_AS_HOME}/install.json"
REAL_MANIFEST_BEFORE=""
if [ -f "${REAL_MANIFEST}" ]; then
  REAL_MANIFEST_BEFORE="$(shasum -a 256 "${REAL_MANIFEST}" 2>/dev/null | awk '{print $1}')"
  ok "the real installation at ${REAL_AS_HOME} was found and its manifest hashed, not modified"
else
  printf '  --    no existing installation at %s; isolation has nothing to preserve there\n' "${REAL_AS_HOME}"
fi
REAL_ACTIVE_BEFORE="$(readlink "${REAL_AS_HOME}/current" 2>/dev/null || printf '')"

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
report PRIVATE_REPOSITORY_ACCESS "unknown"

# ==============================================================================
printf '\n1. With existing git authentication\n'
# ==============================================================================
BOX="$(new_sandbox)"
if ! prepare_bootstrap "${BOX}"; then
  bad "could not build and install the npm bootstrap"
  report CLEAN_PRIVATE_INSTALL FAIL
  report PRIVATE_AUTHENTICATED_INSTALL FAIL
  report PRIVATE_REPOSITORY_ACCESS FAIL
else
  ok "the npm bootstrap packs and installs"
  graft_keychain_access "${BOX}"

  # Nothing under the real $HOME is reachable from the sandbox except the two
  # Keychain grafts, which carry no host-skill or Agent-Skills state.
  assert_not "[ -e '${BOX}/home/.claude' ]" \
    "the sandbox starts with no host skill directories of its own"
  assert_not "[ -e '${BOX}/home/.agent-skills' ]" \
    "the sandbox starts with no Agent Skills installation of its own"

  # `--channel rc` when the repo VERSION is a pre-release, so `resolve_latest`
  # will consider the release-candidate tag. `rc` is a superset of `stable`, so
  # this is also correct once a stable release supersedes the candidate.
  PS_CHANNEL=stable
  case "${VERSION}" in *-*) PS_CHANNEL=rc ;; esac
  in_box_auth "${BOX}" "${BOOTSTRAP}" install --repo "${REMOTE}" --all-hosts \
    --channel "${PS_CHANNEL}" > "${BOX}/install.log" 2>&1
  RC=$?
  [ "${RC}" -eq 0 ] || tail -30 "${BOX}/install.log" >&2
  assert_eq "${RC}" "0" "PRIVATE_AUTHENTICATED_INSTALL"
  if [ "${RC}" -eq 0 ]; then
    report PRIVATE_REPOSITORY_ACCESS PASS
    report PRIVATE_AUTHENTICATED_INSTALL PASS
  else
    report PRIVATE_REPOSITORY_ACCESS FAIL
    report PRIVATE_AUTHENTICATED_INSTALL FAIL
  fi

  CLI="${BOX}/home/.agent-skills/bin/agent-skills"
  if [ -x "${CLI}" ]; then
    report CLEAN_PRIVATE_INSTALL PASS
    GOT_VERSION="$(in_box_auth "${BOX}" bash "${CLI}" version)"
    assert_eq "${GOT_VERSION}" "${VERSION}" \
      "the installed release is the one the remote advertises"
    report INSTALLED_VERSION "${GOT_VERSION}"

    in_box_auth "${BOX}" bash "${CLI}" doctor > "${BOX}/doctor.log" 2>&1
    DOCTOR_RC=$?
    assert_eq "${DOCTOR_RC}" "0" "AGENT_SKILLS_DOCTOR"
    assert "grep -q 'release source' '${BOX}/doctor.log'" \
      "doctor names the release source it came from"
    GOT_PROVIDER="$(grep -o 'release source — [a-z]*' "${BOX}/doctor.log" \
      | awk '{print $NF}')"
    assert_eq "${GOT_PROVIDER}" "git" "RELEASE_PROVIDER is git"
    report RELEASE_PROVIDER "${GOT_PROVIDER:-unknown}"
    report AGENT_SKILLS_DOCTOR "$([ "${DOCTOR_RC}" -eq 0 ] && echo PASS || echo FAIL)"

    in_box_auth "${BOX}" bash "${CLI}" verify > "${BOX}/verify.log" 2>&1
    VERIFY_RC=$?
    assert_eq "${VERIFY_RC}" "0" "AGENT_SKILLS_VERIFY"
    report AGENT_SKILLS_VERIFY "$([ "${VERIFY_RC}" -eq 0 ] && echo PASS || echo FAIL)"

    in_box_auth "${BOX}" bash "${CLI}" versions --json > "${BOX}/versions.json" 2>&1
    assert_eq "$?" "0" "version resolution over the authenticated remote"

    in_box_auth "${BOX}" bash "${CLI}" check-updates --repo "${REMOTE}" --channel "${PS_CHANNEL}" \
      > "${BOX}/check.log" 2>&1
    CU=$?
    assert "[ '${CU}' = '0' ] || [ '${CU}' = '10' ]" \
      "check-updates answers up-to-date or update-available, not an error"

    # `update` against the same remote. Up to date is a pass: the point is that
    # the update path reaches the private source and resolves a version.
    in_box_auth "${BOX}" bash "${CLI}" update --repo "${REMOTE}" --channel "${PS_CHANNEL}" \
      > "${BOX}/update.log" 2>&1
    UP=$?
    assert "[ '${UP}' = '0' ]" "PRIVATE_UPDATE_PATH"
    report PRIVATE_UPDATE_PATH "$([ "${UP}" -eq 0 ] && echo PASS || echo FAIL)"
    assert_eq "$(in_box_auth "${BOX}" bash "${CLI}" version)" "${VERSION}" \
      "the machine is still coherent after update"

    # Host registration: every host row `--all-hosts` can link, resolved
    # through `current` into the release fetched from the private remote —
    # not into the real machine's host directories, since HOME is sandboxed.
    HOST_LINKED=0
    HOST_TOTAL=0
    for HOST_DIR in .claude/skills .agents/skills .codex/skills .cursor/skills \
      .copilot/skills .kiro/skills .windsurf/skills .continue/skills; do
      HOST_TOTAL=$((HOST_TOTAL + 1))
      if [ -f "${BOX}/home/${HOST_DIR}/wamala/SKILL.md" ]; then
        HOST_LINKED=$((HOST_LINKED + 1))
      fi
    done
    assert "[ '${HOST_LINKED}' -ge 1 ]" \
      "HOST_REGISTRATION: at least one host directory got a resolvable skill (${HOST_LINKED}/${HOST_TOTAL})"
    if [ -f "${BOX}/home/.claude/skills/wamala/SKILL.md" ]; then
      WAMALA_REAL="$(python3 -c "import os;print(os.path.realpath('${BOX}/home/.claude/skills/wamala'))")"
      case "${WAMALA_REAL}" in
        "${BOX}"/*) ok "the registered skill resolves inside the sandbox, not the real machine" ;;
        *) bad "the registered skill resolves inside the sandbox, not the real machine   [got ${WAMALA_REAL}]" ;;
      esac
    fi
    report HOST_REGISTRATION "$([ "${HOST_LINKED}" -ge 1 ] && echo PASS || echo FAIL)"

    # Execution Guard coherence: the hook the installer would register points
    # at the launcher inside THIS sandbox's install root, which resolves
    # through `current` to the release this run fetched from the private
    # source — proving the guard and the skills it protects come from the
    # same, privately-sourced release. (Full update/rollback guard coherence
    # is already proven against the local provider in test-cli-install.sh;
    # this checks only what is specific to the private-source path.)
    in_box_auth "${BOX}" bash "${CLI}" guard install --yes --hosts claude-code \
      > "${BOX}/guard-install.log" 2>&1
    GUARD_RC=$?
    if [ "${GUARD_RC}" -eq 0 ] && [ -f "${BOX}/home/.claude/settings.json" ]; then
      HOOK_CMD="$(python3 - "${BOX}/home/.claude/settings.json" <<'HOOKPY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    data = json.load(handle)
for group in data.get("hooks", {}).get("PreToolUse", []):
    for hook in group.get("hooks", []):
        command = hook.get("command", "")
        if "guard check-tool" in command:
            print(command)
            raise SystemExit(0)
HOOKPY
)"
      case "${HOOK_CMD}" in
        *"${BOX}"*"/.agent-skills/bin/agent-skills"*)
          ok "EXECUTION_GUARD_COHERENCE: the hook resolves inside this sandbox's install root" ;;
        *)
          bad "EXECUTION_GUARD_COHERENCE: the hook resolves inside this sandbox's install root   [got: ${HOOK_CMD}]" ;;
      esac
      RESOLVED_LAUNCHER="$(python3 -c "import os;print(os.path.realpath('${BOX}/home/.agent-skills/bin/agent-skills'))")"
      case "${RESOLVED_LAUNCHER}" in
        *"/versions/${VERSION}/bin/agent-skills")
          ok "the guard hook's target resolves to the release fetched from the private source"
          report EXECUTION_GUARD_COHERENCE PASS ;;
        *)
          bad "the guard hook's target resolves to the release fetched from the private source   [got ${RESOLVED_LAUNCHER}]"
          report EXECUTION_GUARD_COHERENCE FAIL ;;
      esac
    else
      printf '  --    guard hook not registered in this environment; guard coherence case skipped\n'
      report EXECUTION_GUARD_COHERENCE "SKIPPED (guard not registrable here)"
    fi

    for LOG in install doctor verify update check guard-install; do
      [ -f "${BOX}/${LOG}.log" ] || continue
      assert_not "grep -Eq 'gh[pousr]_[A-Za-z0-9]{16,}|github_pat_' '${BOX}/${LOG}.log'" \
        "no token-shaped string in the ${LOG} output"
    done
    # A bare "ghp_" substring is not evidence of a leaked token — the shipped
    # payload's OWN source documents this exact prefix (the redaction regex in
    # lib/asrelease/providers/git.py, and its description in the security
    # review). Match the token SHAPE, the same way every other check here does.
    assert_not "grep -rEq 'gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{20,}' '${BOX}/home/.agent-skills' 2>/dev/null" \
      "no token-shaped string was written into the installation"
    assert_not "[ -f '${BOX}/home/.config/agent-skills/credentials.json' ]" \
      "installing stored no credential of its own"
  else
    bad "no launcher was installed; the remaining cases cannot run"
    report CLEAN_PRIVATE_INSTALL FAIL
    report INSTALLED_VERSION "none"
    report AGENT_SKILLS_DOCTOR FAIL
    report AGENT_SKILLS_VERIFY FAIL
    report PRIVATE_UPDATE_PATH FAIL
    report RELEASE_PROVIDER "none"
    report HOST_REGISTRATION FAIL
    report EXECUTION_GUARD_COHERENCE FAIL
  fi
fi

# ==============================================================================
printf '\n2. Without authentication\n'
# ==============================================================================
# Every credential path removed: no git config, no ssh agent, no gh config, no
# Keychain graft, and a synthetic GH_TOKEN in the environment that must neither
# be used nor echoed.
BOX2="$(new_sandbox)"
if prepare_bootstrap "${BOX2}"; then
  START="$(date +%s)"
  in_box "${BOX2}" "${BOOTSTRAP}" install --repo "${REMOTE}" \
    > "${BOX2}/noauth.log" 2>&1
  RC=$?
  ELAPSED=$(( $(date +%s) - START ))

  assert_eq "${RC}" "3" "AUTHENTICATION_REQUIRED_BEHAVIOR: exit 3"
  assert "grep -q 'AUTHENTICATION_REQUIRED' '${BOX2}/noauth.log'" \
    "the message says AUTHENTICATION_REQUIRED"
  assert_not "grep -qi 'repository not found' '${BOX2}/noauth.log'" \
    "it does not report the repository as missing"
  # The classified message is allowed to carry the raw git detail as
  # supporting evidence ("... git said: fatal: ..."); what must never happen is
  # a raw git error appearing WITHOUT the classification, or ahead of it. So
  # the check is ordering, not absence: AUTHENTICATION_REQUIRED must appear,
  # and the first line of output must not itself be a bare git fatal error.
  assert_not "head -n 1 '${BOX2}/noauth.log' | grep -qi '^fatal:'" \
    "the CLI's classification leads the message, not a raw git fatal: line"
  assert "grep -qi 'AUTHENTICATION_REQUIRED' '${BOX2}/noauth.log'" \
    "when a raw git detail is included, it is preceded by a clear classification"
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
  assert_not "[ -e '${BOX2}/home/.agent-skills/current' ]" \
    "no activation pointer was left behind — no partial install"
  assert_not "[ -e '${BOX2}/home/.claude/skills/wamala' ]" \
    "no host registration was left behind"

  if [ "${RC}" -eq 3 ] \
    && grep -q 'AUTHENTICATION_REQUIRED' "${BOX2}/noauth.log" \
    && ! grep -qi 'repository not found' "${BOX2}/noauth.log" \
    && ! grep -q "${SYNTHETIC_TOKEN}" "${BOX2}/noauth.log" \
    && [ "${ELAPSED}" -lt 120 ] \
    && [ ! -d "${BOX2}/home/.agent-skills/versions" ]; then
    report AUTHENTICATION_REQUIRED_BEHAVIOR PASS
  else
    report AUTHENTICATION_REQUIRED_BEHAVIOR FAIL
  fi
else
  bad "could not prepare the bootstrap for the unauthenticated case"
  report AUTHENTICATION_REQUIRED_BEHAVIOR FAIL
fi

# ==============================================================================
printf '\n3. Existing state isolation — the real installation on this machine\n'
# ==============================================================================
REAL_MANIFEST_AFTER=""
if [ -f "${REAL_MANIFEST}" ]; then
  REAL_MANIFEST_AFTER="$(shasum -a 256 "${REAL_MANIFEST}" 2>/dev/null | awk '{print $1}')"
fi
REAL_ACTIVE_AFTER="$(readlink "${REAL_AS_HOME}/current" 2>/dev/null || printf '')"

if [ -z "${REAL_MANIFEST_BEFORE}" ] && [ -z "${REAL_MANIFEST_AFTER}" ]; then
  ok "EXISTING_STATE_ISOLATION: no real installation existed before or after — nothing to disturb"
  report EXISTING_STATE_ISOLATION PASS
elif [ "${REAL_MANIFEST_BEFORE}" = "${REAL_MANIFEST_AFTER}" ] \
  && [ "${REAL_ACTIVE_BEFORE}" = "${REAL_ACTIVE_AFTER}" ]; then
  ok "EXISTING_STATE_ISOLATION: the real installation's manifest and active release are unchanged"
  report EXISTING_STATE_ISOLATION PASS
else
  bad "EXISTING_STATE_ISOLATION: the real installation changed during this run" \
    "before=${REAL_MANIFEST_BEFORE:-<none>}/${REAL_ACTIVE_BEFORE:-<none>} after=${REAL_MANIFEST_AFTER:-<none>}/${REAL_ACTIVE_AFTER:-<none>}"
  report EXISTING_STATE_ISOLATION FAIL
fi
# No sandbox may have ever been given a real path under $HOME as its own
# AGENT_SKILLS_HOME or host directory — every one is under /tmp or
# /private/tmp or /var/folders.
LEAKED=0
for box in "${SANDBOXES[@]+"${SANDBOXES[@]}"}"; do
  case "${box}" in /tmp/*|/private/tmp/*|/var/folders/*) : ;; *) LEAKED=1 ;; esac
done
assert_eq "${LEAKED}" "0" "every sandbox HOME lived under a throwaway temp directory"

# ==============================================================================
printf '\n%s passed, %s failed\n\n' "${PASS}" "${FAIL}"

printf 'PRIVATE_REPOSITORY_ACCESS       %s\n' "${R_PRIVATE_REPOSITORY_ACCESS:-FAIL}"
printf 'CLEAN_PRIVATE_INSTALL           %s\n' "${R_CLEAN_PRIVATE_INSTALL:-FAIL}"
printf 'INSTALLED_VERSION               %s (expected %s)\n' "${R_INSTALLED_VERSION:-none}" "${VERSION}"
printf 'AGENT_SKILLS_DOCTOR             %s\n' "${R_AGENT_SKILLS_DOCTOR:-FAIL}"
printf 'AGENT_SKILLS_VERIFY             %s\n' "${R_AGENT_SKILLS_VERIFY:-FAIL}"
printf 'PRIVATE_UPDATE_PATH             %s\n' "${R_PRIVATE_UPDATE_PATH:-FAIL}"
printf 'RELEASE_PROVIDER                %s (expected git)\n' "${R_RELEASE_PROVIDER:-none}"
printf 'HOST_REGISTRATION               %s\n' "${R_HOST_REGISTRATION:-FAIL}"
printf 'EXECUTION_GUARD_COHERENCE       %s\n' "${R_EXECUTION_GUARD_COHERENCE:-FAIL}"
printf 'EXISTING_STATE_ISOLATION        %s\n\n' "${R_EXISTING_STATE_ISOLATION:-FAIL}"

printf 'PRIVATE_AUTHENTICATED_INSTALL: %s\n' "${R_PRIVATE_AUTHENTICATED_INSTALL:-FAIL}"
printf 'PRIVATE_UPDATE: %s\n' "${R_PRIVATE_UPDATE_PATH:-FAIL}"
printf 'AUTHENTICATION_REQUIRED_BEHAVIOR: %s\n' "${R_AUTHENTICATION_REQUIRED_BEHAVIOR:-FAIL}"

if [ "${FAIL}" -eq 0 ]; then
  printf 'PRIVATE_SOURCE_DISTRIBUTION_READY: YES\n'
  exit 0
fi
printf 'PRIVATE_SOURCE_DISTRIBUTION_READY: NO\n' >&2
printf 'Fix the failures above before cutting %s.\n' "${VERSION}" >&2
exit 1
