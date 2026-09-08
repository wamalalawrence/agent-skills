#!/usr/bin/env bash
# Regression tests for the machine-global installation (v0.37.0).
#
# Every case runs against a throwaway HOME under mktemp. Nothing here reads or
# writes the real home directory, and no test needs a credential — which is
# itself one of the assertions.
#
# Usage: bash scripts/test-global-install.sh [-v]
#
# Exit 0 when every case passes, 1 otherwise.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLI="${REPO_ROOT}/bin/agent-skills"
VERBOSE="false"
[ "${1:-}" = "-v" ] && VERBOSE="true"

PASS=0
FAIL=0
FAILED_CASES=""
SANDBOXES=""

cleanup() {
  local box
  for box in ${SANDBOXES}; do
    [ -n "${box}" ] || continue
    chmod -R u+w "${box}" 2>/dev/null || true
    rm -rf "${box}" 2>/dev/null || true
  done
}
trap cleanup EXIT

ok() {
  PASS=$((PASS + 1))
  printf '  ok   %s\n' "$1"
}

bad() {
  FAIL=$((FAIL + 1))
  FAILED_CASES="${FAILED_CASES}
    - $1"
  printf '  FAIL %s\n' "$1" >&2
  [ -n "${2:-}" ] && printf '       %s\n' "$2" >&2
}

check() {
  # check <description> <command...>
  local description="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    ok "${description}"
  else
    bad "${description}" "command failed: $*"
  fi
}

refute() {
  local description="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    bad "${description}" "command unexpectedly succeeded: $*"
  else
    ok "${description}"
  fi
}

# Create an isolated fake HOME. The directory name contains a space on purpose:
# quoting regressions are the most common shell bug in an installer.
new_home() {
  local base
  base="$(mktemp -d)"
  SANDBOXES="${SANDBOXES} ${base}"
  mkdir -p "${base}/fake home"
  printf '%s' "${base}/fake home"
}

# Run the CLI with an isolated HOME and install root.
as_run() {
  local home="$1"
  shift
  env -i \
    HOME="${home}" \
    AGENT_SKILLS_HOME="${home}/.agent-skills" \
    AGENT_SKILLS_CONFIG_DIR="${home}/.config/agent-skills" \
    PATH="${home}/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin" \
    TERM="dumb" \
    bash "${CLI}" "$@"
}

section() { printf '\n== %s ==\n' "$1"; }

# ------------------------------------------------------------------------------
section "clean first install"
# ------------------------------------------------------------------------------
H1="$(new_home)"
OUT1="$(as_run "${H1}" install --yes 2>&1)"
RC1=$?

if [ "${RC1}" -eq 0 ]; then
  ok "install exits 0 on a clean machine"
else
  bad "install exits 0 on a clean machine" "exit ${RC1}"
fi
[ "${VERBOSE}" = "true" ] && printf '%s\n' "${OUT1}"

check "install manifest written" test -f "${H1}/.agent-skills/install.json"
check "canonical skills tree linked" test -L "${H1}/.agent-skills/skills"
check "canonical scripts tree linked" test -L "${H1}/.agent-skills/scripts"
check "launcher reachable in the install root" test -x "${H1}/.agent-skills/bin/agent-skills"
check "standard dir registered" test -L "${H1}/.agents/skills/tech-lead"
check "registered skill resolves to a SKILL.md" test -f "${H1}/.agents/skills/tech-lead/SKILL.md"

# The binding requirement: first install must not ask for, or store, anything
# credential-shaped.
if printf '%s' "${OUT1}" | grep -qiE 'jira|confluence|sonar|token|password|api key|credential'; then
  # "No credentials were requested" is the one allowed mention.
  if printf '%s' "${OUT1}" | grep -iE 'jira|confluence|sonar|token|password|api key' \
    | grep -vqi 'no credentials were requested'; then
    bad "first install never mentions a credential prompt" \
      "$(printf '%s' "${OUT1}" | grep -iE 'jira|confluence|sonar|token|password' | head -3)"
  else
    ok "first install never mentions a credential prompt"
  fi
else
  ok "first install never mentions a credential prompt"
fi

refute "first install creates no credential metadata" \
  test -f "${H1}/.config/agent-skills/credentials.json"
refute "first install creates no legacy workspace .env" test -f "${H1}/.env"
refute "first install creates no workspace .skills link" test -e "${H1}/.skills"

if printf '%s' "${OUT1}" | grep -qE 'ghp_|AKIA[0-9A-Z]{16}|-----BEGIN'; then
  bad "install output contains no secret-shaped string"
else
  ok "install output contains no secret-shaped string"
fi

# ------------------------------------------------------------------------------
section "path with spaces"
# ------------------------------------------------------------------------------
case "${H1}" in
  *" "*) ok "sandbox home path contains a space (all cases exercise quoting)" ;;
  *) bad "sandbox home path contains a space" "got ${H1}" ;;
esac
check "skills resolve through a path with spaces" \
  test -f "${H1}/.agent-skills/skills/software-engineer/SKILL.md"

# ------------------------------------------------------------------------------
section "idempotency"
# ------------------------------------------------------------------------------
BEFORE="$(find "${H1}/.agents/skills" -maxdepth 1 | sort | wc -l | tr -d ' ')"
OUT2="$(as_run "${H1}" install --yes 2>&1)"
AFTER="$(find "${H1}/.agents/skills" -maxdepth 1 | sort | wc -l | tr -d ' ')"
if [ "${BEFORE}" = "${AFTER}" ]; then
  ok "rerun does not add registrations (${BEFORE} before and after)"
else
  bad "rerun does not add registrations" "${BEFORE} -> ${AFTER}"
fi
if printf '%s' "${OUT2}" | grep -q 'already current'; then
  ok "rerun reports existing registrations as already current"
else
  bad "rerun reports existing registrations as already current"
fi
MANIFEST_COUNT="$(grep -c '"schema"' "${H1}/.agent-skills/install.json" | tr -d ' ')"
if [ "${MANIFEST_COUNT}" = "1" ]; then
  ok "manifest is rewritten, not appended"
else
  bad "manifest is rewritten, not appended" "found ${MANIFEST_COUNT} schema keys"
fi

# ------------------------------------------------------------------------------
section "hosts absent, hosts present, unrelated skills preserved"
# ------------------------------------------------------------------------------
H2="$(new_home)"
# Claude Code present with a skill the user installed themselves.
mkdir -p "${H2}/.claude/skills/my-own-skill"
printf -- '---\nname: my-own-skill\ndescription: mine\n---\n# Mine\n' \
  > "${H2}/.claude/skills/my-own-skill/SKILL.md"
# A pre-existing empty config dir for a host with no skills dir yet.
mkdir -p "${H2}/.kiro"
# Cursor deliberately absent.
OUT3="$(as_run "${H2}" install --yes 2>&1)"

check "host with an existing skills dir is registered" test -L "${H2}/.claude/skills/tech-lead"
check "host with only a config dir is registered" test -L "${H2}/.kiro/skills/tech-lead"
refute "absent host is not created" test -d "${H2}/.cursor/skills"
if printf '%s' "${OUT3}" | grep -q 'not detected on this machine, skipped'; then
  ok "absent hosts are reported as skipped, not failed"
else
  bad "absent hosts are reported as skipped, not failed"
fi

check "unrelated user skill survives install" test -f "${H2}/.claude/skills/my-own-skill/SKILL.md"
if [ -L "${H2}/.claude/skills/my-own-skill" ]; then
  bad "unrelated user skill is not converted to a symlink"
else
  ok "unrelated user skill is not converted to a symlink"
fi

# A name collision with an unrelated real directory must be left alone, not
# replaced. Simulate one by pre-creating a directory named like one of ours.
H3="$(new_home)"
mkdir -p "${H3}/.claude/skills/tech-lead"
printf -- '---\nname: tech-lead\ndescription: not ours\n---\n# Not ours\n' \
  > "${H3}/.claude/skills/tech-lead/SKILL.md"
OUT4="$(as_run "${H3}" install --yes 2>&1)"
if [ -L "${H3}/.claude/skills/tech-lead" ]; then
  bad "a colliding unrelated skill directory is never replaced"
else
  ok "a colliding unrelated skill directory is never replaced"
fi
if grep -q 'not ours' "${H3}/.claude/skills/tech-lead/SKILL.md" 2>/dev/null; then
  ok "the colliding skill's content is untouched"
else
  bad "the colliding skill's content is untouched"
fi
if printf '%s' "${OUT4}" | grep -q 'left existing non-agent-skills entries alone'; then
  ok "the collision is reported to the user"
else
  bad "the collision is reported to the user"
fi

# ------------------------------------------------------------------------------
section "symlink strategy and duplicate resolution"
# ------------------------------------------------------------------------------
# Several hosts scan each other's directories, so one host can list a skill
# twice. That is only dangerous if the copies differ. Assert they cannot.
HDUP="$(new_home)"
as_run "${HDUP}" install --yes --all-hosts >/dev/null 2>&1
DUP_REPORT="$(
  env HOME="${HDUP}" python3 - <<'PY'
import os
import sys

home = os.environ["HOME"]
dirs = [".claude/skills", ".agents/skills", ".cursor/skills", ".kiro/skills"]
targets = set()
present = 0
for rel in dirs:
    path = os.path.join(home, rel, "tech-lead")
    if not os.path.exists(path):
        continue
    present += 1
    targets.add(os.path.realpath(path))
print("present=%d distinct=%d" % (present, len(targets)))
sys.exit(0 if present >= 2 and len(targets) == 1 else 1)
PY
)"
if [ $? -eq 0 ]; then
  ok "every host registration resolves to one canonical path (${DUP_REPORT})"
else
  bad "every host registration resolves to one canonical path" "${DUP_REPORT}"
fi

# --all-hosts must register every linkable host, so the covering set is testable.
check "--all-hosts registers a host that is absent from the machine" \
  test -L "${HDUP}/.copilot/skills/tech-lead"

# Nested support skills travel inside their parent, so they are reachable
# without a second top-level registration that would duplicate a name.
check "nested support skill reachable through its parent" \
  test -f "${H1}/.agents/skills/software-engineer/skills/code-reviewer/SKILL.md"
refute "nested support skill is not registered a second time at top level" \
  test -e "${H1}/.agents/skills/code-reviewer"

# ------------------------------------------------------------------------------
section "verify"
# ------------------------------------------------------------------------------
if as_run "${H1}" verify >/dev/null 2>&1; then
  ok "verify passes on a healthy install"
else
  bad "verify passes on a healthy install" "$(as_run "${H1}" verify 2>&1 | tail -20)"
fi

VERIFY_OUT="$(as_run "${H1}" verify 2>&1)"
if printf '%s' "${VERIFY_OUT}" | grep -qE 'ghp_|AKIA[0-9A-Z]{16}'; then
  bad "verify output contains no secret-shaped string"
else
  ok "verify output contains no secret-shaped string"
fi
for expected in "install manifest present" "canonical source" "Host integrations" \
  "Credential storage" "Legacy installation remnants" "Cloud and remote agents"; do
  if printf '%s' "${VERIFY_OUT}" | grep -q "${expected}"; then
    ok "verify reports: ${expected}"
  else
    bad "verify reports: ${expected}"
  fi
done

# ------------------------------------------------------------------------------
section "broken and missing links"
# ------------------------------------------------------------------------------
H4="$(new_home)"
as_run "${H4}" install --yes >/dev/null 2>&1
rm -f "${H4}/.agent-skills/scripts"
ln -s "${H4}/nowhere-at-all" "${H4}/.agent-skills/scripts"
if as_run "${H4}" verify >/dev/null 2>&1; then
  bad "verify fails when a canonical tree is a broken symlink"
else
  ok "verify fails when a canonical tree is a broken symlink"
fi
# Reinstall must repair it rather than refuse.
as_run "${H4}" install --yes >/dev/null 2>&1
if as_run "${H4}" verify >/dev/null 2>&1; then
  ok "reinstall repairs a broken canonical link"
else
  bad "reinstall repairs a broken canonical link"
fi

H5="$(new_home)"
as_run "${H5}" install --yes >/dev/null 2>&1
rm -f "${H5}/.agents/skills/tech-lead"
VERIFY5="$(as_run "${H5}" verify 2>&1 || true)"
if printf '%s' "${VERIFY5}" | grep -q 'rerun install'; then
  ok "verify notices a missing host registration and says how to fix it"
else
  bad "verify notices a missing host registration and says how to fix it" "${VERIFY5}"
fi

# ------------------------------------------------------------------------------
section "version drift"
# ------------------------------------------------------------------------------
H6="$(new_home)"
as_run "${H6}" install --yes >/dev/null 2>&1
python3 - "${H6}/.agent-skills/install.json" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as handle:
    data = json.load(handle)
data["version"] = "0.0.1"
with open(path, "w", encoding="utf-8") as handle:
    json.dump(data, handle, indent=2)
PY
DRIFT="$(as_run "${H6}" verify 2>&1 || true)"
if printf '%s' "${DRIFT}" | grep -q 'version drift'; then
  ok "verify detects version drift between manifest and source"
else
  bad "verify detects version drift between manifest and source" "${DRIFT}"
fi

# ------------------------------------------------------------------------------
section "global runtime from an unrelated repository"
# ------------------------------------------------------------------------------
H7="$(new_home)"
as_run "${H7}" install --yes >/dev/null 2>&1
UNRELATED="${H7}/code/some-service/src/main/java/deep/nested/pkg"
mkdir -p "${UNRELATED}"
(cd "${H7}/code/some-service" && git init -q 2>/dev/null || true)
printf '[project]\nname = "some-service"\n' > "${H7}/code/some-service/pyproject.toml"

run_in() {
  local dir="$1"
  shift
  ( cd "${dir}" && env -i \
      HOME="${H7}" \
      AGENT_SKILLS_HOME="${H7}/.agent-skills" \
      AGENT_SKILLS_CONFIG_DIR="${H7}/.config/agent-skills" \
      PATH="${H7}/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin" \
      TERM=dumb \
      "$@" )
}

VERSION_FROM_REPO="$(run_in "${H7}/code/some-service" agent-skills version 2>&1)"
if [ "${VERSION_FROM_REPO}" = "$(cat "${REPO_ROOT}/VERSION")" ]; then
  ok "the launcher runs from an unrelated repository via PATH"
else
  bad "the launcher runs from an unrelated repository via PATH" "got '${VERSION_FROM_REPO}'"
fi

VERSION_DEEP="$(run_in "${UNRELATED}" agent-skills version 2>&1)"
if [ "${VERSION_DEEP}" = "$(cat "${REPO_ROOT}/VERSION")" ]; then
  ok "the launcher runs several directory levels deep"
else
  bad "the launcher runs several directory levels deep" "got '${VERSION_DEEP}'"
fi

# No PATH at all: the documented fallback must still work.
FALLBACK="$(
  cd "${UNRELATED}" && env -i HOME="${H7}" AGENT_SKILLS_HOME="${H7}/.agent-skills" \
    PATH="/usr/bin:/bin" TERM=dumb \
    bash "${H7}/.agent-skills/bin/agent-skills" version 2>&1
)"
if [ "${FALLBACK}" = "$(cat "${REPO_ROOT}/VERSION")" ]; then
  ok "the AGENT_SKILLS_HOME fallback works without PATH"
else
  bad "the AGENT_SKILLS_HOME fallback works without PATH" "got '${FALLBACK}'"
fi

# The helper the skills actually call must be reachable from the unrelated repo.
HELPER="$(run_in "${UNRELATED}" bash -c 'command -v agent-skills >/dev/null && echo found')"
if [ "${HELPER}" = "found" ]; then
  ok "lifecycle entry point is on PATH inside an unrelated repository"
else
  bad "lifecycle entry point is on PATH inside an unrelated repository"
fi

# ------------------------------------------------------------------------------
section "progressive project context (zero-config repositories work)"
# ------------------------------------------------------------------------------
CTX="${REPO_ROOT}/scripts/project-context.py"

# A repository with no agent-skills configuration of any kind.
HZ="$(new_home)"
ZERO="${HZ}/code/zero config repo"
mkdir -p "${ZERO}"
( cd "${ZERO}" && git init -q && git config user.email "t@example.com" \
    && git config user.name T && git commit -q --allow-empty -m init ) >/dev/null 2>&1
printf '<project/>\n' > "${ZERO}/pom.xml"
ZJSON="$(python3 "${CTX}" --cwd "${ZERO}" --json 2>&1)"
if printf '%s' "${ZJSON}" | python3 -c 'import json,sys; json.load(sys.stdin)' 2>/dev/null; then
  ok "project context emits valid JSON for a zero-config repository"
else
  bad "project context emits valid JSON for a zero-config repository" "${ZJSON}"
fi
ZSTACK="$(python3 "${CTX}" --cwd "${ZERO}" --field stack 2>&1)"
if [ "${ZSTACK}" = "java" ]; then
  ok "stack inferred from the build manifest with no config file"
else
  bad "stack inferred from the build manifest with no config file" "got ${ZSTACK}"
fi
ZBUILD="$(python3 "${CTX}" --cwd "${ZERO}" --field build 2>&1)"
if [ -n "${ZBUILD}" ]; then
  ok "a build command is offered for a zero-config repository (${ZBUILD})"
else
  bad "a build command is offered for a zero-config repository"
fi
if python3 "${CTX}" --cwd "${ZERO}" --field needs_confirmation | grep -q 'inferred'; then
  ok "an inferred build command is flagged for confirmation rather than asserted"
else
  bad "an inferred build command is flagged for confirmation rather than asserted"
fi
if python3 "${CTX}" --cwd "${ZERO}" >/dev/null 2>&1; then
  ok "project context exits 0 with no configuration present (sparse is not an error)"
else
  bad "project context exits 0 with no configuration present"
fi
ZNAME="$(python3 "${CTX}" --cwd "${ZERO}" --field slug 2>&1)"
if [ "${ZNAME}" = "zero-config-repo" ]; then
  ok "project slug derives from a directory name containing spaces"
else
  bad "project slug derives from a directory name containing spaces" "got ${ZNAME}"
fi

# Committed configuration wins over inference, because a human wrote it.
printf 'mode: in-repo\nproject:\n  name: "declared-name"\n  build: "make verify"\n' \
  > "${ZERO}/.agent-skills.yml"
if [ "$(python3 "${CTX}" --cwd "${ZERO}" --field build)" = "make verify" ]; then
  ok "committed .agent-skills.yml build command outranks inference"
else
  bad "committed .agent-skills.yml build command outranks inference"
fi
if [ "$(python3 "${CTX}" --cwd "${ZERO}" --field mode)" = "in-repo" ]; then
  ok "committed mode: in-repo is honoured"
else
  bad "committed mode: in-repo is honoured"
fi
rm -f "${ZERO}/.agent-skills.yml"

# Inference works from a nested directory, not just the repository root.
NESTED="${ZERO}/src/main/java/deep"
mkdir -p "${NESTED}"
if [ "$(python3 "${CTX}" --cwd "${NESTED}" --field stack)" = "java" ]; then
  ok "project context resolves from a nested directory"
else
  bad "project context resolves from a nested directory"
fi

# ------------------------------------------------------------------------------
section "legacy workspace migration"
# ------------------------------------------------------------------------------
H8="$(new_home)"
LEGACY="${H8}/work"
mkdir -p "${LEGACY}"
ln -s "${REPO_ROOT}/skills" "${LEGACY}/.skills"
printf '{ "schema": "agent-skills.lock/v1", "version": "0.36.0" }\n' \
  > "${LEGACY}/.agent-skills.lock"
printf 'JIRA_HOST="https://example.atlassian.net"\n' > "${LEGACY}/.env"
MIG="$(
  env -i HOME="${H8}" AGENT_SKILLS_HOME="${H8}/.agent-skills" \
    AGENT_SKILLS_CONFIG_DIR="${H8}/.config/agent-skills" \
    WORKSPACE_ROOT="${LEGACY}" PATH="/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin" TERM=dumb \
    bash "${CLI}" migrate 2>&1
)"
if printf '%s' "${MIG}" | grep -q '\.skills is obsolete'; then
  ok "migrate reports the legacy .skills symlink as obsolete"
else
  bad "migrate reports the legacy .skills symlink as obsolete" "${MIG}"
fi
if printf '%s' "${MIG}" | grep -q '\.env is still discovered'; then
  ok "migrate says the legacy .env is still read for compatibility"
else
  bad "migrate says the legacy .env is still read for compatibility"
fi
MIG2="$(
  env -i HOME="${H8}" AGENT_SKILLS_HOME="${H8}/.agent-skills" \
    AGENT_SKILLS_CONFIG_DIR="${H8}/.config/agent-skills" \
    WORKSPACE_ROOT="${LEGACY}" PATH="/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin" TERM=dumb \
    bash "${CLI}" migrate --remove-obsolete 2>&1
)"
refute "migrate --remove-obsolete removes the .skills symlink" test -e "${LEGACY}/.skills"
refute "migrate --remove-obsolete removes the stale lock file" test -e "${LEGACY}/.agent-skills.lock"
check "migrate --remove-obsolete never deletes .env" test -f "${LEGACY}/.env"

# ------------------------------------------------------------------------------
section "uninstall"
# ------------------------------------------------------------------------------
H9="$(new_home)"
mkdir -p "${H9}/.claude/skills/keep-me"
printf -- '---\nname: keep-me\ndescription: keep\n---\n# Keep\n' \
  > "${H9}/.claude/skills/keep-me/SKILL.md"
as_run "${H9}" install --yes >/dev/null 2>&1
check "pre-uninstall: our registration exists" test -L "${H9}/.claude/skills/tech-lead"
as_run "${H9}" uninstall --yes >/dev/null 2>&1
refute "uninstall removes our host registration" test -e "${H9}/.claude/skills/tech-lead"
check "uninstall keeps an unrelated user skill" test -f "${H9}/.claude/skills/keep-me/SKILL.md"
refute "uninstall removes the install manifest" test -f "${H9}/.agent-skills/install.json"
check "uninstall leaves the source clone alone" test -f "${REPO_ROOT}/skills/tech-lead/SKILL.md"

# ------------------------------------------------------------------------------
section "hosts report"
# ------------------------------------------------------------------------------
HOSTS_JSON="$(as_run "${H1}" hosts --json 2>&1)"
if printf '%s' "${HOSTS_JSON}" | python3 -c 'import json,sys; json.load(sys.stdin)' 2>/dev/null; then
  ok "hosts --json emits valid JSON"
else
  bad "hosts --json emits valid JSON" "${HOSTS_JSON}"
fi
if printf '%s' "${HOSTS_JSON}" | grep -q '"sync_to_cloud"'; then
  ok "hosts report records cloud reachability per host"
else
  bad "hosts report records cloud reachability per host"
fi

# ------------------------------------------------------------------------------
section "in-repo (cloud) mode is unaffected"
# ------------------------------------------------------------------------------
H10="$(new_home)"
CLOUD_REPO="${H10}/cloud-repo"
mkdir -p "${CLOUD_REPO}/.agent-skills"
cp -R "${REPO_ROOT}/skills" "${CLOUD_REPO}/.agent-skills/skills"
cp "${REPO_ROOT}/.agent-skills.example.yml" "${CLOUD_REPO}/.agent-skills.yml"
check "vendored in-repo skills remain loadable with no global install" \
  test -f "${CLOUD_REPO}/.agent-skills/skills/software-engineer/SKILL.md"
check "committed in-repo config remains present" test -f "${CLOUD_REPO}/.agent-skills.yml"
if grep -q '^mode: in-repo' "${CLOUD_REPO}/.agent-skills.yml"; then
  ok "in-repo mode marker still shipped in the example config"
else
  bad "in-repo mode marker still shipped in the example config"
fi
refute "no global install was needed for the in-repo case" \
  test -f "${H10}/.agent-skills/install.json"

# ------------------------------------------------------------------------------
printf '\n'
if [ "${FAIL}" -eq 0 ]; then
  printf 'ok: global-install tests passed (%s assertions)\n' "${PASS}"
  exit 0
fi
printf 'FAIL: %s of %s assertions failed:%s\n' \
  "${FAIL}" "$((PASS + FAIL))" "${FAILED_CASES}" >&2
exit 1
