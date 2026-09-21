#!/usr/bin/env bash
# End-to-end acceptance for the Agent Skills CLI installation contract.
#
# Everything here runs against a throwaway HOME with a space in its path. It
# never touches the real installation, the real host skill directories, or the
# real credential store. Two things make that reliable rather than hopeful:
# every case runs under a fresh sandbox, and the sandbox root is asserted to be
# under a temporary directory before anything is written.
#
# The suite is the Stage A acceptance evidence. It answers, in order:
#
#   can a clean machine install without a manual clone?
#   does a release stay internally coherent across update and rollback?
#   does a failure before activation leave the previous release running?
#   do host registrations, guard hooks, and user state survive all of it?
#   does uninstall remove only what we own?
#   does the installer fail safely when it cannot read its own source?
#
# Usage: bash scripts/test-cli-install.sh [--only <substring>]

set -uo pipefail

REPO_ROOT="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." >/dev/null 2>&1 && pwd)"
VERSION="$(head -n 1 "${REPO_ROOT}/VERSION" | tr -d '[:space:]')"
ONLY=""
[ "${1:-}" = "--only" ] && ONLY="${2:-}"

PASS=0
FAIL=0
CURRENT=""
SANDBOXES=()

# A credential-shaped string that has never been a credential. Used to prove the
# installer neither reads nor echoes secrets from the environment it runs in.
SYNTHETIC_TOKEN="ghp_$(printf 'A%.0s' $(seq 1 36))"

cleanup() {
  local box
  for box in "${SANDBOXES[@]+"${SANDBOXES[@]}"}"; do
    case "${box}" in
      /tmp/*|/private/tmp/*|/var/folders/*) rm -rf "${box}" ;;
    esac
  done
}
trap cleanup EXIT

case_start() {
  CURRENT="$1"
  if [ -n "${ONLY}" ] && [ "${CURRENT#*${ONLY}}" = "${CURRENT}" ]; then
    return 1
  fi
  return 0
}

ok() { PASS=$((PASS + 1)); printf '  ok    %s\n' "$1"; }
bad() { FAIL=$((FAIL + 1)); printf '  FAIL  %s\n' "$1" >&2; }

assert() {
  if eval "$1"; then ok "${2}"; else bad "${2}   [failed: $1]"; fi
}

assert_not() {
  if eval "$1"; then bad "${2}   [unexpectedly true: $1]"; else ok "${2}"; fi
}

assert_eq() {
  if [ "$1" = "$2" ]; then ok "$3"; else bad "$3   [expected '$2', got '$1']"; fi
}

new_sandbox() {
  local box
  box="$(mktemp -d "${TMPDIR:-/tmp}/agent skills test.XXXXXX")"
  # Normalise. TMPDIR often ends in a slash, and on macOS /var is a symlink to
  # /private/var, so a path built by hand and a path from realpath disagree
  # about the same directory. Comparisons here need one canonical form.
  box="$(cd "${box}" && pwd -P)"
  SANDBOXES+=("${box}")
  mkdir -p "${box}/home"
  printf '%s' "${box}"
}

# Every invocation goes through this, so no test can accidentally reach the
# real environment. GH_TOKEN and friends are cleared: the installer must never
# depend on a token in the environment, and a synthetic one is injected instead
# so its absence from every log can be asserted.
in_box() {
  local box="$1"
  shift
  env -u AGENT_SKILLS_SOURCE \
    HOME="${box}/home" \
    AGENT_SKILLS_HOME="${box}/home/.agent-skills" \
    AGENT_SKILLS_CONFIG_DIR="${box}/home/.config/agent-skills" \
    XDG_CONFIG_HOME="${box}/home/.config" \
    PATH="${box}/home/.local/bin:${PATH}" \
    GH_TOKEN="${SYNTHETIC_TOKEN}" \
    GITHUB_TOKEN="${SYNTHETIC_TOKEN}" \
    "$@"
}

cli() {
  local box="$1"
  shift
  in_box "${box}" bash "${REPO_ROOT}/bin/agent-skills" "$@"
}

installed_cli() {
  local box="$1"
  shift
  in_box "${box}" bash "${box}/home/.agent-skills/bin/agent-skills" "$@"
}

install_from_source() {
  local box="$1"
  shift
  # --channel any: the repo VERSION may be a pre-release (RC); these tests
  # install exactly the tree they point at, regardless of its channel.
  cli "${box}" install --provider local --source "${REPO_ROOT}" --channel any "$@"
}

# A source tree whose VERSION has been bumped, so update and rollback have two
# genuinely different releases to move between.
make_next_release() {
  local box="$1"
  local next="$2"
  # One directory per version. Reusing a single scratch directory leaves the
  # previous release's `release.json` behind, which turns the next fixture into
  # a "prepared release" whose manifest describes a payload that is no longer
  # there — a fault in the test, wearing the costume of a real integrity
  # failure.
  local tree="${box}/next-${next}"
  rm -rf "${tree}"
  mkdir -p "${tree}"
  # Copy only the payload entries; this is a release, not a checkout.
  local entry
  for entry in VERSION bin lib scripts skills docs hooks README.md LICENSE; do
    [ -e "${REPO_ROOT}/${entry}" ] || continue
    cp -R "${REPO_ROOT}/${entry}" "${tree}/${entry}"
  done
  printf '%s\n' "${next}" > "${tree}/VERSION"
  printf '%s' "${tree}"
}

banner() { printf '\n%s\n' "$1"; }

# ==============================================================================
banner "1. Clean install from a clean HOME, with a space in every path"
# ==============================================================================
if case_start "clean-install"; then
  BOX="$(new_sandbox)"
  mkdir -p "${BOX}/home/.claude/skills/a-user-skill"
  printf -- '---\nname: a-user-skill\ndescription: not ours\n---\n# Mine\n' \
    > "${BOX}/home/.claude/skills/a-user-skill/SKILL.md"

  install_from_source "${BOX}" > "${BOX}/install.log" 2>&1
  RC=$?
  assert_eq "${RC}" "0" "install exits 0"
  assert "[ -f '${BOX}/home/.agent-skills/install.json' ]" "install manifest written"
  assert "[ -L '${BOX}/home/.agent-skills/current' ]" "current is a symlink"
  assert "[ -d '${BOX}/home/.agent-skills/versions/${VERSION}' ]" "release staged under versions/"
  assert "[ -f '${BOX}/home/.agent-skills/skills/wamala/SKILL.md' ]" "skills resolve through current"
  assert "[ -x '${BOX}/home/.agent-skills/bin/agent-skills' ]" "launcher is executable"
  assert "[ -L '${BOX}/home/.local/bin/agent-skills' ]" "launcher linked onto PATH"

  # The binding v0.37 rule, still binding: installation requests no credential.
  assert_not "grep -Eiq 'jira|confluence|sonar|paste your|api token' '${BOX}/install.log'" \
    "install never mentions a credential"
  assert_not "[ -f '${BOX}/home/.config/agent-skills/credentials.json' ]" \
    "no credential store is created by installing"
  assert_not "[ -e '${BOX}/home/.env' ]" "no .env is written"
  assert_not "[ -e '${BOX}/home/.skills' ]" "no legacy .skills symlink is written"

  # Secret hygiene: a synthetic token was in the environment throughout.
  assert_not "grep -q '${SYNTHETIC_TOKEN}' '${BOX}/install.log'" \
    "no environment token appears in the install log"

  assert "[ -f '${BOX}/home/.claude/skills/a-user-skill/SKILL.md' ]" \
    "an unrelated user skill is untouched"
  assert_not "[ -L '${BOX}/home/.claude/skills/a-user-skill' ]" \
    "an unrelated user skill was not replaced by a link"

  GOT="$(installed_cli "${BOX}" version)"
  assert_eq "${GOT}" "${VERSION}" "version reports the installed release"

  installed_cli "${BOX}" verify > "${BOX}/verify.log" 2>&1
  assert_eq "$?" "0" "verify passes"

  # The runtime must resolve from an unrelated repository several levels deep.
  mkdir -p "${BOX}/elsewhere/svc/src/main/java/deep"
  (cd "${BOX}/elsewhere/svc" && git init -q)
  GOT="$(cd "${BOX}/elsewhere/svc/src/main/java/deep" && in_box "${BOX}" agent-skills version)"
  assert_eq "${GOT}" "${VERSION}" "the CLI resolves from an unrelated deep directory"

  # Idempotency.
  BEFORE="$(ls -1 "${BOX}/home/.agents/skills" | wc -l | tr -d ' ')"
  install_from_source "${BOX}" > /dev/null 2>&1
  AFTER="$(ls -1 "${BOX}/home/.agents/skills" | wc -l | tr -d ' ')"
  assert_eq "${AFTER}" "${BEFORE}" "a second install adds no second registration"

  # Channel resolution for a local-source install of the tree under test:
  #   --dev            -> "any"    (a development install is not a channel choice)
  #   plain, no flag   -> "stable" (refuses a pre-release checkout, on purpose)
  #   explicit         -> honoured
  DEVBOX="$(new_sandbox)"
  in_box "${DEVBOX}" python3 "${REPO_ROOT}/scripts/install.py" install \
    --provider local --source "${REPO_ROOT}" --dev \
    --home "${DEVBOX}/home/.agent-skills" > "${DEVBOX}/dev.log" 2>&1
  assert_eq "$?" "0" "a --dev local install of the tree under test succeeds on any channel"
  PLAINBOX="$(new_sandbox)"
  in_box "${PLAINBOX}" python3 "${REPO_ROOT}/scripts/install.py" install \
    --provider local --source "${REPO_ROOT}" \
    --home "${PLAINBOX}/home/.agent-skills" > "${PLAINBOX}/plain.log" 2>&1
  PLAIN_RC=$?
  case "$(cat "${REPO_ROOT}/VERSION")" in
    *-*) assert "[ '${PLAIN_RC}' != '0' ]" \
           "a plain local install still refuses a pre-release checkout without --channel"
         assert "grep -q 'not a stable one' '${PLAINBOX}/plain.log'" \
           "the refusal names the channel mismatch" ;;
    *)   assert_eq "${PLAIN_RC}" "0" "a plain local install of a stable checkout succeeds" ;;
  esac
fi

# ==============================================================================
banner "2. Version coherence: skills, runtime, and manifest come from one release"
# ==============================================================================
if case_start "coherence"; then
  BOX="$(new_sandbox)"
  install_from_source "${BOX}" > /dev/null 2>&1
  ROOT="${BOX}/home/.agent-skills"
  MANIFEST_V="$(python3 -c "import json;print(json.load(open('${ROOT}/install.json'))['version'])")"
  CURRENT_V="$(basename "$(readlink "${ROOT}/current")")"
  PAYLOAD_V="$(head -n1 "${ROOT}/current/VERSION" | tr -d '[:space:]')"
  RELEASE_V="$(python3 -c "import json;print(json.load(open('${ROOT}/current/release.json'))['version'])")"
  SKILL_V="$(grep -m1 'version:' "${ROOT}/skills/wamala/SKILL.md" | tr -d ' "' | cut -d: -f2)"
  assert_eq "${MANIFEST_V}" "${VERSION}" "manifest version"
  assert_eq "${CURRENT_V}" "${VERSION}" "current -> versions/<version>"
  assert_eq "${PAYLOAD_V}" "${VERSION}" "payload VERSION"
  assert_eq "${RELEASE_V}" "${VERSION}" "release manifest version"
  assert_eq "${SKILL_V}" "${VERSION}" "skill metadata version"
  # A helper reached through the install must come from the same release.
  HELPER="$(python3 -c "import os;print(os.path.realpath('${ROOT}/scripts/doctor.sh'))")"
  case "${HELPER}" in
    "${ROOT}/versions/${VERSION}/"*|/private"${ROOT}/versions/${VERSION}/"*)
      ok "lifecycle helpers resolve inside the active release" ;;
    *) bad "lifecycle helpers resolve inside the active release   [got ${HELPER}]" ;;
  esac
fi

# ==============================================================================
banner "3. Update, rollback, and host coherence across both"
# ==============================================================================
if case_start "update"; then
  BOX="$(new_sandbox)"
  mkdir -p "${BOX}/home/.claude/skills"
  install_from_source "${BOX}" > /dev/null 2>&1
  NEXT="$(make_next_release "${BOX}" 99.0.0)"

  # Meeting state is durable data under state/, not part of any release. Plant
  # a record and prove update and rollback neither lose nor fork it.
  MEETING_DIR="${BOX}/home/.agent-skills/state/meetings/m_0123456789ab"
  HOME="${BOX}/home" AGENT_SKILLS_HOME="${BOX}/home/.agent-skills" python3 - "${REPO_ROOT}/scripts" <<'PLANT'
import sys
sys.path.insert(0, sys.argv[1])
import meeting_capture as mc
import meeting_store as store
record = store.new_record("m_0123456789ab", "zoom", "https://zoom.us/j/81234567890", "Planted",
                          {"kind": "unscoped"}, mc.CaptureHandle("recall", "7c1f0d52-3a4e-4b6f-9d21-0a1b2c3d4e5f"),
                          "captions", store.load_config())
record["state"] = mc.PROCESSED
store.save_record(record)
PLANT
  MEETING_SUM="$(cksum < "${MEETING_DIR}/record.json")"

  cli "${BOX}" update --provider local --source "${NEXT}" > "${BOX}/update.log" 2>&1
  assert_eq "$?" "0" "update exits 0"
  assert_eq "$(cksum < "${MEETING_DIR}/record.json" 2>/dev/null)" "${MEETING_SUM}" \
    "meeting state survives update untouched"
  assert_eq "$(installed_cli "${BOX}" version)" "99.0.0" "the new release is active"
  assert "[ -d '${BOX}/home/.agent-skills/versions/${VERSION}' ]" "the previous release is retained"

  # Host registrations follow the active release without being rewritten.
  TARGET="$(python3 -c "import os;print(os.path.realpath('${BOX}/home/.claude/skills/wamala'))")"
  case "${TARGET}" in
    *"/versions/99.0.0/skills/wamala") ok "host registrations resolve to the new release" ;;
    *) bad "host registrations resolve to the new release   [got ${TARGET}]" ;;
  esac

  cli "${BOX}" rollback > "${BOX}/rollback.log" 2>&1
  assert_eq "$?" "0" "rollback exits 0"
  assert_eq "$(installed_cli "${BOX}" version)" "${VERSION}" "the previous release is active again"
  TARGET="$(python3 -c "import os;print(os.path.realpath('${BOX}/home/.claude/skills/wamala'))")"
  case "${TARGET}" in
    *"/versions/${VERSION}/skills/wamala") ok "host registrations follow the rollback" ;;
    *) bad "host registrations follow the rollback   [got ${TARGET}]" ;;
  esac
  installed_cli "${BOX}" verify > /dev/null 2>&1
  assert_eq "$?" "0" "verify passes after rollback"
  assert_eq "$(cksum < "${MEETING_DIR}/record.json" 2>/dev/null)" "${MEETING_SUM}" \
    "meeting state survives rollback untouched"
  installed_cli "${BOX}" meeting list > "${BOX}/meeting-list.log" 2>&1
  assert_eq "$?" "0" "the installed launcher dispatches meeting list"
  assert "grep -q 'm_0123456789ab' '${BOX}/meeting-list.log'" "meeting list reads state that crossed update and rollback"
  installed_cli "${BOX}" meeting join https://example.com/not-a-meeting > /dev/null 2>&1
  assert_eq "$?" "2" "an unrecognised meeting link exits 2 through the launcher"
fi

# ==============================================================================
banner "4. A failed update leaves the previous release running"
# ==============================================================================
if case_start "failed-update"; then
  BOX="$(new_sandbox)"
  install_from_source "${BOX}" > /dev/null 2>&1

  # (a) Corrupt payload: the release manifest no longer describes the tree.
  NEXT="$(make_next_release "${BOX}" 99.0.0)"
  REPO_ROOT="${REPO_ROOT}" python3 - "${NEXT}" <<'PY'
import json
import os
import sys

sys.path.insert(0, os.path.join(os.environ["REPO_ROOT"], "lib"))
from asrelease.release import ReleaseRef, build_manifest, write_manifest

root = sys.argv[1]
manifest = build_manifest(root, ReleaseRef("99.0.0", "local", root))
write_manifest(root, manifest)
# Tamper AFTER the manifest was written: this is exactly the shape of a
# substituted payload.
with open(os.path.join(root, "skills", "wamala", "SKILL.md"), "a", encoding="utf-8") as handle:
    handle.write("\n<!-- tampered -->\n")
PY
  cli "${BOX}" update --provider local --source "${NEXT}" > "${BOX}/corrupt.log" 2>&1
  RC=$?
  assert_eq "${RC}" "5" "a tampered payload fails with the integrity exit code"
  assert "grep -qi 'hash mismatch' '${BOX}/corrupt.log'" "the failure names the integrity problem"
  assert_eq "$(installed_cli "${BOX}" version)" "${VERSION}" "the previous release is still active"
  assert_not "[ -d '${BOX}/home/.agent-skills/versions/99.0.0' ]" "nothing was staged"

  # (b) Broken payload: it verifies, but its runtime cannot answer.
  BROKEN="$(make_next_release "${BOX}" 98.0.0)"
  printf 'not a launcher\n' > "${BROKEN}/bin/agent-skills"
  cli "${BOX}" update --provider local --source "${BROKEN}" > "${BOX}/broken.log" 2>&1
  RC=$?
  assert_eq "${RC}" "6" "a release that fails its self-test fails with the install code"
  assert "grep -qi 'self-test' '${BOX}/broken.log'" "the failure names the self-test"
  assert_eq "$(installed_cli "${BOX}" version)" "${VERSION}" "the previous release is still active"
  installed_cli "${BOX}" verify > /dev/null 2>&1
  assert_eq "$?" "0" "verify still passes after two failed updates"

  # (c) verify has to answer with the code it publishes, and it has to actually
  # verify. Checking that release.json exists proved nothing about the tree it
  # describes: "Installation verified" was printed over an edited release,
  # because the payload hash was only ever re-computed at stage and rollback.
  ACTIVE_ROOT="${BOX}/home/.agent-skills/versions/${VERSION}"
  cp "${ACTIVE_ROOT}/skills/wamala/SKILL.md" "${BOX}/skill.orig"
  printf '\n<!-- edited in place after installation -->\n' >> "${ACTIVE_ROOT}/skills/wamala/SKILL.md"
  installed_cli "${BOX}" verify > "${BOX}/tampered-verify.log" 2>&1
  assert_eq "$?" "7" "verify on a tampered release exits 7, the published code"
  assert "grep -qi 'does not match its manifest' '${BOX}/tampered-verify.log'" \
    "verify names the integrity failure rather than reporting success"
  assert_not "grep -q 'Installation verified' '${BOX}/tampered-verify.log'" \
    "verify does not report a tampered release as verified"
  cp "${BOX}/skill.orig" "${ACTIVE_ROOT}/skills/wamala/SKILL.md"
  installed_cli "${BOX}" verify > /dev/null 2>&1
  assert_eq "$?" "0" "verify passes again once the tree is restored"

  # Drift between the manifest and the active release is the case the exit-code
  # contract calls out by name, and it used to fall out as the shell's default 1.
  python3 - "${BOX}/home/.agent-skills/install.json" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path) as handle:
    data = json.load(handle)
data["version"] = "0.0.1"
with open(path, "w") as handle:
    json.dump(data, handle, indent=2)
PY
  installed_cli "${BOX}" verify > "${BOX}/drift-verify.log" 2>&1
  assert_eq "$?" "7" "verify on a drifted manifest exits 7, not 1"
  assert "grep -qi 'version drift' '${BOX}/drift-verify.log'" "verify names the drift"

  # And the codes are readable without grepping the source.
  installed_cli "${BOX}" verify --explain-codes > "${BOX}/codes.log" 2>&1
  assert_eq "$?" "0" "verify --explain-codes is the flag the engine documents"
  assert "grep -q 'verification-failure' '${BOX}/codes.log'" \
    "the explanation lists the frozen names"
fi

# ==============================================================================
banner "5. An interrupted update leaves no mixed installation"
# ==============================================================================
if case_start "interrupted"; then
  BOX="$(new_sandbox)"
  install_from_source "${BOX}" > /dev/null 2>&1
  NEXT="$(make_next_release "${BOX}" 97.0.0)"
  # Interrupt after staging but before activation by removing the payload entry
  # the self-test requires. Every stage before ACTIVATE must be recoverable.
  rm -f "${NEXT}/scripts/hosts-reconcile.sh"
  cli "${BOX}" update --provider local --source "${NEXT}" > "${BOX}/int.log" 2>&1
  assert_not "[ '$?' = '0' ]" "an incomplete payload does not install"
  assert_eq "$(installed_cli "${BOX}" version)" "${VERSION}" "the machine is unchanged"
  ACTIVE="$(basename "$(readlink "${BOX}/home/.agent-skills/current")")"
  PAYLOAD="$(head -n1 "${BOX}/home/.agent-skills/current/VERSION" | tr -d '[:space:]')"
  assert_eq "${ACTIVE}" "${PAYLOAD}" "current and its payload agree: no mixed install"
  assert_not "[ -d '${BOX}/home/.agent-skills/cache/staging/97.0.0' ]" "staging was cleaned up"
fi

# ==============================================================================
banner "6. Downgrade is refused by update and offered by rollback"
# ==============================================================================
if case_start "downgrade"; then
  BOX="$(new_sandbox)"
  install_from_source "${BOX}" > /dev/null 2>&1
  NEXT="$(make_next_release "${BOX}" 99.0.0)"
  cli "${BOX}" update --provider local --source "${NEXT}" > /dev/null 2>&1

  cli "${BOX}" update --provider local --source "${REPO_ROOT}" --channel any > "${BOX}/down.log" 2>&1
  assert_eq "$?" "2" "an unrequested downgrade is refused"
  assert "grep -qi 'older' '${BOX}/down.log'" "the refusal explains what it refused"
  assert "grep -q 'rollback' '${BOX}/down.log'" "the refusal names the supported way back"
  assert_eq "$(installed_cli "${BOX}" version)" "99.0.0" "the newer release is still active"

  cli "${BOX}" update --provider local --source "${REPO_ROOT}" --channel any --allow-downgrade > /dev/null 2>&1
  assert_eq "$(installed_cli "${BOX}" version)" "${VERSION}" "an explicit downgrade is honoured"
fi

# ==============================================================================
banner "7. Migration from a pre-CLI (v0.37-v0.42) installation"
# ==============================================================================
if case_start "migration"; then
  BOX="$(new_sandbox)"
  ROOT="${BOX}/home/.agent-skills"
  OLD="${BOX}/old-clone"
  mkdir -p "${ROOT}" "${BOX}/home/.claude/skills" "${BOX}/home/.config/agent-skills"
  # Reconstruct the old layout exactly: absolute links straight into a clone,
  # and a v1 manifest. This is what every existing installation looks like.
  cp -R "${REPO_ROOT}" "${OLD}"
  rm -rf "${OLD}/.git"
  for tree in skills scripts lib bin docs hooks; do
    ln -s "${OLD}/${tree}" "${ROOT}/${tree}"
  done
  printf '0.42.0\n' > "${ROOT}/VERSION"
  cat > "${ROOT}/install.json" <<JSON
{"schema":"agent-skills.install/v1","version":"0.42.0","source_dir":"${OLD}",
 "home":"${ROOT}","canonical_skills_dir":"${ROOT}/skills","hosts":["claude-code"],
 "cli_link":"${BOX}/home/.local/bin/agent-skills"}
JSON
  ln -s "${ROOT}/skills/wamala" "${BOX}/home/.claude/skills/wamala"
  # User state that must survive: a credential identity and a project binding.
  printf '{"schema":"agent-skills.credentials/v1","profiles":{"work":{"service":"demo"}}}\n' \
    > "${BOX}/home/.config/agent-skills/credentials.json"
  printf '{"bindings":{"demo":"work"}}\n' > "${BOX}/home/.config/agent-skills/bindings.json"

  install_from_source "${BOX}" > "${BOX}/migrate.log" 2>&1
  assert_eq "$?" "0" "installing over a pre-CLI installation succeeds"
  assert_eq "$(readlink "${ROOT}/skills")" "current/skills" "top-level links now go through current"
  assert_eq "$(installed_cli "${BOX}" version)" "${VERSION}" "the new release is active"
  assert "[ -f '${BOX}/home/.config/agent-skills/credentials.json' ]" \
    "credential identities survived the migration"
  assert "grep -q 'work' '${BOX}/home/.config/agent-skills/credentials.json'" \
    "the identity itself is intact"
  assert "[ -f '${BOX}/home/.config/agent-skills/bindings.json' ]" "project bindings survived"
  TARGET="$(python3 -c "import os;print(os.path.realpath('${BOX}/home/.claude/skills/wamala'))")"
  case "${TARGET}" in
    *"/versions/${VERSION}/skills/wamala") ok "an existing host registration now resolves to the release" ;;
    *) bad "an existing host registration now resolves to the release   [got ${TARGET}]" ;;
  esac
fi

# ==============================================================================
banner "8. Uninstall removes what we own and nothing else"
# ==============================================================================
if case_start "uninstall"; then
  BOX="$(new_sandbox)"
  mkdir -p "${BOX}/home/.claude/skills/keep-me"
  printf -- '---\nname: keep-me\ndescription: mine\n---\n' \
    > "${BOX}/home/.claude/skills/keep-me/SKILL.md"
  install_from_source "${BOX}" > /dev/null 2>&1
  # User state that uninstall must not destroy.
  mkdir -p "${BOX}/home/.config/agent-skills"
  printf '{"profiles":{"work":{}}}\n' > "${BOX}/home/.config/agent-skills/credentials.json"
  mkdir -p "${BOX}/home/.claude" && printf '{"hooks":{"PreToolUse":[{"matcher":"X","hooks":[]}]}}\n' \
    > "${BOX}/home/.claude/settings.json"

  cli "${BOX}" uninstall --yes > "${BOX}/uninstall.log" 2>&1
  assert_eq "$?" "0" "uninstall exits 0"
  assert_not "[ -e '${BOX}/home/.agents/skills/wamala' ]" "our registrations are removed"
  assert_not "[ -d '${BOX}/home/.agent-skills/versions' ]" "installed release payloads are removed"
  assert_not "[ -f '${BOX}/home/.agent-skills/install.json' ]" "the manifest is removed"
  assert_not "[ -e '${BOX}/home/.local/bin/agent-skills' ]" "the launcher link is removed"
  assert "[ -f '${BOX}/home/.claude/skills/keep-me/SKILL.md' ]" "an unrelated user skill survives"
  assert "[ -f '${BOX}/home/.config/agent-skills/credentials.json' ]" \
    "credential identities survive an ordinary uninstall"
  assert "grep -q 'PreToolUse' '${BOX}/home/.claude/settings.json'" \
    "an unrelated host hook configuration survives"

  cli "${BOX}" uninstall --yes --purge > /dev/null 2>&1
  assert_not "[ -f '${BOX}/home/.config/agent-skills/credentials.json' ]" \
    "--purge removes credential metadata, and only when asked"
fi

# ==============================================================================
banner "9. Execution Guard hooks stay coherent across update and rollback"
# ==============================================================================
if case_start "guard"; then
  BOX="$(new_sandbox)"
  mkdir -p "${BOX}/home/.claude"
  install_from_source "${BOX}" > /dev/null 2>&1
  # A pre-existing hook of the user's own, which must survive everything.
  cat > "${BOX}/home/.claude/settings.json" <<'JSON'
{"hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"type":"command","command":"echo mine"}]}]}}
JSON
  installed_cli "${BOX}" guard install --yes > "${BOX}/guard.log" 2>&1
  if grep -q '"agent-skills' "${BOX}/home/.claude/settings.json" 2>/dev/null \
    || grep -q 'guard check-tool' "${BOX}/home/.claude/settings.json" 2>/dev/null; then
    ok "the guard registered a hook"
    assert "grep -q 'echo mine' '${BOX}/home/.claude/settings.json'" \
      "the user's own hook was preserved"
    NEXT="$(make_next_release "${BOX}" 99.0.0)"
    cli "${BOX}" update --provider local --source "${NEXT}" > /dev/null 2>&1
    # Read the hook out of the JSON rather than grepping it: the command is a
    # quoted path inside a JSON string, so a character-class grep stops at the
    # first escaped quote and silently reports half of it.
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
      *"/.agent-skills/bin/agent-skills"*)
        ok "the guard hook points at the install root, so it follows the active release" ;;
      *) bad "the guard hook points at the install root   [got ${HOOK_CMD}]" ;;
    esac
    # The hook must resolve to the release that is actually active.
    RESOLVED="$(python3 -c "import os;print(os.path.realpath('${BOX}/home/.agent-skills/bin/agent-skills'))")"
    case "${RESOLVED}" in
      *"/versions/99.0.0/bin/agent-skills") ok "the guard hook resolves to the updated release" ;;
      *) bad "the guard hook resolves to the updated release   [got ${RESOLVED}]" ;;
    esac
    cli "${BOX}" rollback > /dev/null 2>&1
    RESOLVED="$(python3 -c "import os;print(os.path.realpath('${BOX}/home/.agent-skills/bin/agent-skills'))")"
    case "${RESOLVED}" in
      *"/versions/${VERSION}/bin/agent-skills") ok "the guard hook follows the rollback" ;;
      *) bad "the guard hook follows the rollback   [got ${RESOLVED}]" ;;
    esac
    cli "${BOX}" uninstall --yes > /dev/null 2>&1
    assert "grep -q 'echo mine' '${BOX}/home/.claude/settings.json'" \
      "uninstall left the user's own hook alone"
    assert_not "grep -q 'guard check-tool' '${BOX}/home/.claude/settings.json'" \
      "uninstall removed the agent-skills hook"
  else
    printf '  --    guard hook not registered in this environment; guard cases skipped\n'
  fi
fi

# ==============================================================================
banner "10. Context Optimizer travels with the release"
# ==============================================================================
if case_start "context"; then
  BOX="$(new_sandbox)"
  install_from_source "${BOX}" > /dev/null 2>&1
  assert "[ -f '${BOX}/home/.agent-skills/skills/context-optimizer/SKILL.md' ]" \
    "the context-optimizer skill is installed"
  assert "[ -f '${BOX}/home/.agent-skills/scripts/context.py' ]" \
    "the context runtime is installed"
  printf 'line one\nline two failed: BadState\nline three\n' > "${BOX}/sample.log"
  installed_cli "${BOX}" context inspect "${BOX}/sample.log" > "${BOX}/ctx.log" 2>&1
  assert_eq "$?" "0" "the context runtime runs from the installed release"
fi

# ==============================================================================
banner "11. The installed product works offline"
# ==============================================================================
if case_start "offline"; then
  BOX="$(new_sandbox)"
  install_from_source "${BOX}" > /dev/null 2>&1
  # Simulated: no provider is contacted, and the git binary is hidden from PATH
  # so anything that reached for the network would fail loudly.
  mkdir -p "${BOX}/nogit"
  OFFLINE_PATH="${BOX}/home/.local/bin:${BOX}/nogit"
  env -u AGENT_SKILLS_SOURCE HOME="${BOX}/home" \
    AGENT_SKILLS_HOME="${BOX}/home/.agent-skills" \
    AGENT_SKILLS_CONFIG_DIR="${BOX}/home/.config/agent-skills" \
    PATH="/usr/bin:/bin:${OFFLINE_PATH}" \
    bash "${BOX}/home/.agent-skills/bin/agent-skills" doctor > "${BOX}/offline.log" 2>&1
  assert_eq "$?" "0" "doctor runs offline"
  assert "grep -q 'Installation' '${BOX}/offline.log'" "doctor still reports the installation"
  installed_cli "${BOX}" verify > /dev/null 2>&1
  assert_eq "$?" "0" "verify runs offline"
  installed_cli "${BOX}" versions --local > "${BOX}/versions.log" 2>&1
  assert_eq "$?" "0" "versions --local runs offline"
  installed_cli "${BOX}" memory --help > /dev/null 2>&1
  assert_eq "$?" "0" "a runtime helper runs offline"
fi

# ==============================================================================
banner "12. Missing distribution access fails cleanly, and says so"
# ==============================================================================
if case_start "auth"; then
  BOX="$(new_sandbox)"
  # A remote that exists but cannot be read without credentials. Reached over a
  # file:// URL to a directory that is not a repository, with every credential
  # path disabled, which is how an unauthenticated private fetch presents.
  PRIVATE="https://github.com/wamalalawrence/agent-skills-private-does-not-exist.git"
  in_box "${BOX}" env PATH="/usr/bin:/bin:/usr/local/bin" \
    bash "${REPO_ROOT}/bin/agent-skills" install --provider git --repo "${PRIVATE}" \
    > "${BOX}/auth.log" 2>&1
  RC=$?
  assert_eq "${RC}" "3" "an unreadable release source exits with the authentication code"
  assert "grep -q 'AUTHENTICATION_REQUIRED' '${BOX}/auth.log'" \
    "the failure says authentication required, not 'repository not found'"
  assert "grep -qi 'distribution access' '${BOX}/auth.log'" \
    "the failure distinguishes distribution access from project access"
  assert_not "grep -q '${SYNTHETIC_TOKEN}' '${BOX}/auth.log'" \
    "no token from the environment is echoed"
  assert_not "grep -Eq 'gh[pousr]_[A-Za-z0-9]{16,}' '${BOX}/auth.log'" \
    "no token-shaped string appears in the failure output"
  assert_not "[ -d '${BOX}/home/.agent-skills/versions' ]" "nothing was installed"
  # It must fail rather than block: a hung installer inside an editor terminal
  # is invisible. Ten seconds is generous for a refusal.
  START="$(date +%s)"
  in_box "${BOX}" bash "${REPO_ROOT}/bin/agent-skills" provider --repo "${PRIVATE}" \
    > /dev/null 2>&1
  ELAPSED=$(( $(date +%s) - START ))
  assert "[ '${ELAPSED}' -lt 60 ]" "the provider never blocks on a credential prompt"
fi

# ==============================================================================
banner "13. Installing from the packed npm artifact, with no manual clone"
# ==============================================================================
if case_start "npm"; then
  if command -v npm >/dev/null 2>&1 && command -v node >/dev/null 2>&1; then
    BOX="$(new_sandbox)"
    bash "${REPO_ROOT}/scripts/build-npm-bootstrap.sh" --pack > "${BOX}/pack.log" 2>&1
    # Absolute, and it has to stay absolute. `npm install npm/<file>.tgz` is read
    # as the GitHub shorthand `github:npm/<file>.tgz` — a bare `<org>/<name>` is
    # a repository reference to npm — so it clones instead of installing and git
    # exits 128.
    TARBALL="$(ls -1t "${REPO_ROOT}"/npm/*.tgz 2>/dev/null | head -1)"
    if [ -z "${TARBALL}" ]; then
      bad "the npm bootstrap could not be packed"
    else
      ok "the npm bootstrap packs"
      # Package-content gate: a published tarball is public forever.
      LISTING="$(tar -tzf "${TARBALL}")"
      assert_not "printf '%s' \"\${LISTING}\" | grep -qE 'package/(skills|docs|evals|eval-runs|hooks)/'" \
        "the package carries no product content"
      assert_not "printf '%s' \"\${LISTING}\" | grep -qE '\\.env|credentials|\\.pem|\\.key|id_rsa|\\.tgz'" \
        "the package carries no credential-shaped file"
      assert "printf '%s' \"\${LISTING}\" | grep -q 'package/vendor/install.py'" \
        "the package carries the installation engine"
      COUNT="$(printf '%s' "${LISTING}" | grep -c .)"
      assert "[ \"${COUNT}\" -lt 30 ]" "the package is small enough to audit by eye (${COUNT} files)"

      mkdir -p "${BOX}/npmroot"
      npm install --silent --prefix "${BOX}/npmroot" "${TARBALL}" > /dev/null 2>&1
      BOOT="${BOX}/npmroot/node_modules/.bin/agent-skills-bootstrap"
      assert "[ -x '${BOOT}' ]" "the packed artifact installs and exposes its bootstrap"

      # A real git remote, so the git provider's full path is exercised without
      # anything having been published yet.
      REMOTE="${BOX}/remote.git"
      git init -q --bare "${REMOTE}"
      WORK="${BOX}/work"
      mkdir -p "${WORK}"
      for entry in VERSION bin lib scripts skills docs hooks README.md LICENSE; do
        [ -e "${REPO_ROOT}/${entry}" ] && cp -R "${REPO_ROOT}/${entry}" "${WORK}/${entry}"
      done
      # This fixture repository has nothing to do with the developer's own git
      # setup, so it is deliberately insulated from it: no global hooks path,
      # and a branch name no protected-branch policy would recognise.
      mkdir -p "${BOX}/nohooks"
      # A function, not a variable: the sandbox path contains spaces, and a
      # word-split command string would break apart on them and fail silently.
      gitfx() {
        git -c "core.hooksPath=${BOX}/nohooks" \
          -c user.email=t@example.invalid -c user.name=test "$@"
      }
      (cd "${WORK}" && gitfx -c init.defaultBranch=as-fixture init -q \
        && gitfx add -A \
        && gitfx commit -qm "release ${VERSION}" \
        && gitfx tag -a "v${VERSION}" -m "v${VERSION}" \
        && gitfx remote add box "${REMOTE}" \
        && gitfx push -q box HEAD:refs/heads/as-fixture --tags) > "${BOX}/fixture.log" 2>&1
      assert_eq "$?" "0" "the git release fixture publishes a tagged release"

      in_box "${BOX}" "${BOOT}" install --repo "${REMOTE}" --channel rc > "${BOX}/npm-install.log" 2>&1
      RC=$?
      [ "${RC}" -eq 0 ] || tail -20 "${BOX}/npm-install.log" >&2
      assert_eq "${RC}" "0" "install from the packed artifact over a git remote succeeds"
      assert_eq "$(installed_cli "${BOX}" version)" "${VERSION}" \
        "the release is active, with no manual clone anywhere in the flow"
      assert_not "grep -q '${SYNTHETIC_TOKEN}' '${BOX}/npm-install.log'" \
        "no environment token appears in the bootstrap log"
      PROVIDER="$(python3 -c "import json;print(json.load(open('${BOX}/home/.agent-skills/install.json'))['provider']['id'])")"
      assert_eq "${PROVIDER}" "git" "the manifest records the provider it came from"

      # Update over the same remote, from the installed CLI, with no clone.
      (cd "${WORK}" && printf '99.0.0\n' > VERSION && gitfx add -A \
        && gitfx commit -qm "release 99.0.0" \
        && gitfx tag -a "v99.0.0" -m "v99.0.0" \
        && gitfx push -q box HEAD:refs/heads/as-fixture --tags) > /dev/null 2>&1
      installed_cli "${BOX}" update --repo "${REMOTE}" --channel rc > "${BOX}/npm-update.log" 2>&1
      assert_eq "$?" "0" "update over a git remote succeeds"
      assert_eq "$(installed_cli "${BOX}" version)" "99.0.0" "the newer release is active"
      installed_cli "${BOX}" check-updates --repo "${REMOTE}" --channel rc > /dev/null 2>&1
      assert_eq "$?" "0" "check-updates reports up to date"
    fi
  else
    printf '  --    node or npm unavailable; npm bootstrap cases skipped\n'
  fi
fi

# ==============================================================================
banner "14. The vendored engine is the repository's engine, not a second one"
# ==============================================================================
if case_start "vendor"; then
  bash "${REPO_ROOT}/scripts/build-npm-bootstrap.sh" > /dev/null 2>&1
  DRIFT=0
  if ! diff -q "${REPO_ROOT}/scripts/install.py" "${REPO_ROOT}/npm/vendor/install.py" > /dev/null; then
    DRIFT=1
  fi
  for file in "${REPO_ROOT}"/lib/asrelease/*.py; do
    diff -q "${file}" "${REPO_ROOT}/npm/vendor/asrelease/$(basename "${file}")" > /dev/null || DRIFT=1
  done
  for file in "${REPO_ROOT}"/lib/asrelease/providers/*.py; do
    diff -q "${file}" "${REPO_ROOT}/npm/vendor/asrelease/providers/$(basename "${file}")" > /dev/null \
      || DRIFT=1
  done
  assert_eq "${DRIFT}" "0" "the vendored engine is byte-identical to the repository's"
  PKG_V="$(python3 -c "import json;print(json.load(open('${REPO_ROOT}/npm/package.json'))['version'])")"
  assert_eq "${PKG_V}" "${VERSION}" "npm package version matches VERSION"
  assert_not "grep -q '\"preinstall\"\\|\"postinstall\"\\|\"prepare\"' '${REPO_ROOT}/npm/package.json'" \
    "the package runs no npm lifecycle script"
fi

# ==============================================================================
banner "15. The release line a machine follows survives its next update"
# ==============================================================================
# A machine that opted into `rc` must keep being offered release candidates
# without re-typing `--channel rc` on every command. Two distinct faults are
# covered here, both of which shipped:
#
#   - the effective channel was resolved from the flags of the current
#     invocation only, so a bare `update` on an rc machine resolved `stable`;
#   - the manifest recorded the channel the installed *version* belongs to, so
#     an rc machine that took the stable release superseding its candidate
#     recorded `stable` and fell off the rc line permanently.
#
# The git provider is used rather than the local one because only it implements
# the superset rule, and the superset is where the second fault lives.
if case_start "channel-persistence"; then
  if ! command -v git > /dev/null 2>&1; then
    printf '  --    git unavailable; channel-persistence cases skipped\n'
  else
    BOX="$(new_sandbox)"
    CP_REMOTE="${BOX}/releases.git"
    CP_WORK="${BOX}/releases"
    git init -q --bare "${CP_REMOTE}"
    mkdir -p "${CP_WORK}" "${BOX}/nohooks-cp"
    for entry in VERSION bin lib scripts skills docs hooks README.md LICENSE; do
      [ -e "${REPO_ROOT}/${entry}" ] && cp -R "${REPO_ROOT}/${entry}" "${CP_WORK}/${entry}"
    done
    cpgit() {
      git -c "core.hooksPath=${BOX}/nohooks-cp" \
        -c user.email=t@example.invalid -c user.name=test "$@"
    }
    # Publish one more release onto the fixture remote.
    cp_publish() {
      local v="$1"
      (cd "${CP_WORK}" && printf '%s\n' "${v}" > VERSION \
        && cpgit add -A \
        && cpgit commit -qm "release ${v}" \
        && cpgit tag -a "v${v}" -m "v${v}" \
        && cpgit push -q box HEAD:refs/heads/as-fixture --tags) > /dev/null 2>&1
    }
    cp_manifest() {
      python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get(sys.argv[2],''))" \
        "${BOX}/home/.agent-skills/install.json" "$1"
    }

    (cd "${CP_WORK}" && cpgit -c init.defaultBranch=as-fixture init -q \
      && cpgit remote add box "${CP_REMOTE}") > /dev/null 2>&1
    cp_publish "2.0.0-rc.1"

    cli "${BOX}" install --repo "${CP_REMOTE}" --channel rc > "${BOX}/cp-install.log" 2>&1
    RC=$?
    [ "${RC}" -eq 0 ] || tail -20 "${BOX}/cp-install.log" >&2
    assert_eq "${RC}" "0" "installing with --channel rc succeeds"
    assert_eq "$(installed_cli "${BOX}" version)" "2.0.0-rc.1" "the candidate is active"
    assert_eq "$(cp_manifest follow_channel)" "rc" \
      "the manifest records the release line the machine follows"

    # --- the reported fault: a bare check-updates on an rc machine -----------
    cp_publish "2.0.0-rc.2"
    installed_cli "${BOX}" check-updates --repo "${CP_REMOTE}" > "${BOX}/cp-check.log" 2>&1
    assert_eq "$?" "10" "a bare check-updates offers the next candidate to an rc machine"
    assert "grep -q '2.0.0-rc.2' '${BOX}/cp-check.log'" "it names the candidate"
    assert_not "grep -q 'ahead' '${BOX}/cp-check.log'" \
      "an rc machine is not told it is ahead of its own line"

    # The apply line has to be a command that actually performs that update —
    # including against the source this check was pointed at. A hint that drops
    # `--repo` describes an update from the default remote, which is not the one
    # whose answer is printed above it.
    CP_APPLY="$(sed -n 's/^ *apply *: *//p' "${BOX}/cp-check.log" | head -n 1)"
    assert "printf '%s' \"${CP_APPLY}\" | grep -q '^agent-skills update'" \
      "the apply hint is an update command"
    assert "printf '%s' \"${CP_APPLY}\" | grep -qF \"${CP_REMOTE}\"" \
      "the apply hint carries the source this check looked at"
    assert_not "printf '%s' \"${CP_APPLY}\" | grep -q -- '--channel'" \
      "the apply hint adds no channel flag when the machine's own line was used"

    # Run it verbatim. The hint is shell-quoted, so eval is what a user pasting
    # it into a terminal would get.
    eval "installed_cli \"${BOX}\" ${CP_APPLY#agent-skills }" > "${BOX}/cp-update.log" 2>&1
    assert_eq "$?" "0" "a bare update on an rc machine succeeds"
    assert_eq "$(installed_cli "${BOX}" version)" "2.0.0-rc.2" \
      "a bare update moves an rc machine along its own line"

    # --- the superset fault: taking the stable release must not drop the line
    cp_publish "2.0.0"
    installed_cli "${BOX}" update --repo "${CP_REMOTE}" > /dev/null 2>&1
    assert_eq "$(installed_cli "${BOX}" version)" "2.0.0" \
      "an rc machine is offered the stable release that supersedes its candidate"
    assert_eq "$(cp_manifest channel)" "stable" \
      "the manifest still records the channel the installed version belongs to"
    assert_eq "$(cp_manifest follow_channel)" "rc" \
      "taking a stable release does not move the machine off the rc line"

    cp_publish "2.0.1-rc.1"
    installed_cli "${BOX}" check-updates --repo "${CP_REMOTE}" > "${BOX}/cp-check2.log" 2>&1
    assert_eq "$?" "10" "the next candidate after a stable release is still offered"

    # --- an explicit flag still wins over the recorded line ------------------
    installed_cli "${BOX}" check-updates --repo "${CP_REMOTE}" --channel stable \
      > "${BOX}/cp-check3.log" 2>&1
    assert_eq "$?" "0" "--channel stable overrides the recorded line"
    assert_not "grep -q '2.0.1-rc.1' '${BOX}/cp-check3.log'" \
      "the override narrows what the rc machine is offered"

    # --- rollback does not choose a channel, so it must not change one -------
    installed_cli "${BOX}" rollback > /dev/null 2>&1
    assert_eq "$(cp_manifest follow_channel)" "rc" "rollback leaves the followed line alone"

    # --- a manifest written before this field existed still resolves rc ------
    python3 - "${BOX}/home/.agent-skills/install.json" <<'PY'
import json, sys
path = sys.argv[1]
with open(path) as handle:
    data = json.load(handle)
data.pop("follow_channel", None)
data["channel"] = "rc"
with open(path, "w") as handle:
    json.dump(data, handle, indent=2, sort_keys=True)
PY
    CP_LEGACY="$(installed_cli "${BOX}" check-updates --repo "${CP_REMOTE}" --json 2>/dev/null \
      | python3 -c "import json,sys;print(json.load(sys.stdin)['requested_channel'])")"
    assert_eq "${CP_LEGACY}" "rc" "a pre-field manifest still resolves the rc line"

    # --- and an unrecognised value fails closed onto stable ------------------
    python3 - "${BOX}/home/.agent-skills/install.json" <<'PY'
import json, sys
path = sys.argv[1]
with open(path) as handle:
    data = json.load(handle)
data["follow_channel"] = "../../etc"
data["channel"] = "nonsense"
with open(path, "w") as handle:
    json.dump(data, handle, indent=2, sort_keys=True)
PY
    installed_cli "${BOX}" check-updates --repo "${CP_REMOTE}" > "${BOX}/cp-bad.log" 2>&1
    CP_BAD="$(installed_cli "${BOX}" check-updates --repo "${CP_REMOTE}" --json 2>/dev/null \
      | python3 -c "import json,sys;print(json.load(sys.stdin)['requested_channel'])")"
    assert_eq "${CP_BAD}" "stable" "an unrecognised recorded channel falls back to stable"
    assert_not "grep -q '2.0.1-rc.1' '${BOX}/cp-bad.log'" \
      "a malformed manifest cannot widen the channel"

    # --- a stable machine is unaffected in either direction ------------------
    BOX2="$(new_sandbox)"
    cli "${BOX2}" install --repo "${CP_REMOTE}" --channel stable > "${BOX2}/cp-install.log" 2>&1
    assert_eq "$(installed_cli "${BOX2}" version)" "2.0.0" "a stable machine installs the release"
    installed_cli "${BOX2}" check-updates --repo "${CP_REMOTE}" > "${BOX2}/cp-check.log" 2>&1
    assert_eq "$?" "0" "a stable machine is not offered a candidate"
    assert_not "grep -q 'rc' '${BOX2}/cp-check.log'" "no candidate is named to a stable machine"

    # Opting in from a stable machine is the one case where the apply hint has
    # to carry a flag, because a bare update there would resolve stable. This
    # is the exact wall a user hits when they go looking for a candidate.
    installed_cli "${BOX2}" check-updates --repo "${CP_REMOTE}" --channel rc \
      > "${BOX2}/cp-optin.log" 2>&1
    assert_eq "$?" "10" "asking a stable machine about rc offers the candidate"
    CP_APPLY2="$(sed -n 's/^ *apply *: *//p' "${BOX2}/cp-optin.log" | head -n 1)"
    assert "printf '%s' \"${CP_APPLY2}\" | grep -q -- '--channel rc'" \
      "the apply hint carries the flag when the check overrode the machine's line"
    assert "printf '%s' \"${CP_APPLY2}\" | grep -qF \"${CP_REMOTE}\"" \
      "the apply hint carries the source alongside the channel"
    # And that hint, run verbatim and with nothing added, does what the check
    # said it would. Anything the test has to append is something the user would
    # have had to work out for themselves.
    eval "installed_cli \"${BOX2}\" ${CP_APPLY2#agent-skills }" > /dev/null 2>&1
    assert_eq "$(installed_cli "${BOX2}" version)" "2.0.1-rc.1" \
      "running the printed hint performs the update it described"

    # --- mutation probe: the fix has to be what makes this pass -------------
    # A copy of the engine with the manifest lookup removed from channel
    # resolution must fail the bare-update case. A probe that passes against a
    # build with the property removed proves nothing.
    # Put the manifest back on the rc line the malformed-manifest case left.
    python3 - "${BOX}/home/.agent-skills/install.json" <<'PY'
import json, sys
path = sys.argv[1]
with open(path) as handle:
    data = json.load(handle)
data["follow_channel"] = "rc"
data["channel"] = "rc"
with open(path, "w") as handle:
    json.dump(data, handle, indent=2, sort_keys=True)
PY
    CP_PROBE="${BOX}/probe"
    mkdir -p "${CP_PROBE}"
    cp -R "${REPO_ROOT}/lib" "${CP_PROBE}/lib"
    cp "${REPO_ROOT}/scripts/install.py" "${CP_PROBE}/install.py"
    python3 - "${CP_PROBE}/install.py" <<'PY'
import sys
path = sys.argv[1]
text = open(path).read()
start = text.index("def resolve_channel(")
end = text.index("\ndef ", start + 1)
weakened = (
    "def resolve_channel(args, layout=None) -> str:\n"
    '    """The pre-fix resolution: this invocation\'s flags and nothing else."""\n'
    '    if getattr(args, "channel", None):\n'
    "        return args.channel\n"
    '    return "any" if getattr(args, "dev", False) else "stable"\n'
)
if weakened == text[start:end]:
    raise SystemExit("probe did not change resolve_channel")
open(path, "w").write(text[:start] + weakened + text[end:])
PY
    assert_eq "$?" "0" "the probe build actually removed the manifest lookup"
    in_box "${BOX}" python3 "${CP_PROBE}/install.py" check-updates \
      --home "${BOX}/home/.agent-skills" --repo "${CP_REMOTE}" > "${BOX}/cp-probe.log" 2>&1
    PROBE_RC=$?
    assert_not "[ '${PROBE_RC}' = '10' ] && grep -q '2.0.1-rc.1' '${BOX}/cp-probe.log'" \
      "without the manifest lookup, an rc machine is not offered its own line"
    # And the real engine, against that same manifest, is.
    installed_cli "${BOX}" check-updates --repo "${CP_REMOTE}" > "${BOX}/cp-real.log" 2>&1
    assert_eq "$?" "10" "the engine under test does offer it against the same manifest"
  fi
fi

# ==============================================================================
printf '\n%s passed, %s failed\n' "${PASS}" "${FAIL}"
[ "${FAIL}" -eq 0 ] || exit 1
