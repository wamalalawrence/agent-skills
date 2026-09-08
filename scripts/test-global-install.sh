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

# `test -e` follows symlinks, so it calls a dangling link absent — which is
# exactly the state a botched rename leaves behind. Assert on the entry itself.
no_entry() {
  [ ! -e "$1" ] && [ ! -L "$1" ]
}

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
check "standard dir registered" test -L "${H1}/.agents/skills/wamala"
check "registered skill resolves to a SKILL.md" test -f "${H1}/.agents/skills/wamala/SKILL.md"

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

check "host with an existing skills dir is registered" test -L "${H2}/.claude/skills/wamala"
check "host with only a config dir is registered" test -L "${H2}/.kiro/skills/wamala"
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
mkdir -p "${H3}/.claude/skills/wamala"
printf -- '---\nname: wamala\ndescription: not ours\n---\n# Not ours\n' \
  > "${H3}/.claude/skills/wamala/SKILL.md"
OUT4="$(as_run "${H3}" install --yes 2>&1)"
if [ -L "${H3}/.claude/skills/wamala" ]; then
  bad "a colliding unrelated skill directory is never replaced"
else
  ok "a colliding unrelated skill directory is never replaced"
fi
if grep -q 'not ours' "${H3}/.claude/skills/wamala/SKILL.md" 2>/dev/null; then
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
    path = os.path.join(home, rel, "wamala")
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
  test -L "${HDUP}/.copilot/skills/wamala"

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
rm -f "${H5}/.agents/skills/wamala"
VERIFY5="$(as_run "${H5}" verify 2>&1 || true)"
if printf '%s' "${VERIFY5}" | grep -q 'rerun install'; then
  ok "verify notices a missing host registration and says how to fix it"
else
  bad "verify notices a missing host registration and says how to fix it" "${VERIFY5}"
fi

# Ownership must survive the source tree disappearing. Otherwise uninstall
# cannot recognise its own registrations on exactly the machine that most needs
# cleaning up: one where the clone was deleted or moved.
H5B="$(new_home)"
SRC_COPY="${H5B}/source copy"
mkdir -p "${SRC_COPY}"
cp -R "${REPO_ROOT}/." "${SRC_COPY}/" 2>/dev/null || true
mkdir -p "${H5B}/.claude/skills/unrelated-user-skill"
printf -- '---\nname: unrelated-user-skill\ndescription: keep\n---\n# Keep\n' \
  > "${H5B}/.claude/skills/unrelated-user-skill/SKILL.md"
env -i HOME="${H5B}" AGENT_SKILLS_HOME="${H5B}/.agent-skills" \
  AGENT_SKILLS_CONFIG_DIR="${H5B}/.config/agent-skills" \
  PATH="${H5B}/.local/bin:/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin" TERM=dumb \
  bash "${SRC_COPY}/bin/agent-skills" install --yes >/dev/null 2>&1
if [ -L "${H5B}/.claude/skills/wamala" ]; then
  ok "pre-condition: installed from a throwaway source copy"
else
  bad "pre-condition: installed from a throwaway source copy"
fi
rm -rf "${SRC_COPY}"
UNINST="$(as_run "${H5B}" uninstall --yes 2>&1 || true)"
if printf '%s' "${UNINST}" | grep -q 'removed 8 registration(s)'; then
  ok "uninstall still recognises its registrations after the source tree is deleted"
else
  bad "uninstall still recognises its registrations after the source tree is deleted" "${UNINST}"
fi
refute "the orphaned registration is removed" test -e "${H5B}/.claude/skills/wamala"
check "the unrelated user skill still survives an orphaned uninstall" \
  test -f "${H5B}/.claude/skills/unrelated-user-skill/SKILL.md"

# ------------------------------------------------------------------------------
section "skill rename migration (v0.37.0 front door -> wamala)"
# ------------------------------------------------------------------------------
# v0.37.0 registered the front door as `tech-lead`. Upgrading must end with one
# `wamala` registration per host and no agent-skills-owned `tech-lead` left
# behind, while anything named `tech-lead` that the user owns survives.
H14="$(new_home)"
OLD_SRC="${H14}/v0.37.0 source"
mkdir -p "${OLD_SRC}"
cp -R "${REPO_ROOT}/." "${OLD_SRC}/" 2>/dev/null || true
rm -rf "${OLD_SRC}/.git" "${OLD_SRC}/.venv" "${OLD_SRC}/.cache"
mv "${OLD_SRC}/skills/wamala" "${OLD_SRC}/skills/tech-lead"
python3 - "${OLD_SRC}/skills/tech-lead/SKILL.md" <<'RENAME_PY'
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as handle:
    text = handle.read()
with open(path, "w", encoding="utf-8") as handle:
    handle.write(text.replace("\nname: wamala\n", "\nname: tech-lead\n", 1))
RENAME_PY

# Two things of the user's own that share the old name, in two different hosts:
# a real directory, and a symlink into their own tree. Neither is ours.
mkdir -p "${H14}/.claude/skills/tech-lead"
printf -- '---\nname: tech-lead\ndescription: mine\n---\n# My own lead\n' \
  > "${H14}/.claude/skills/tech-lead/SKILL.md"
mkdir -p "${H14}/my-skills/tech-lead" "${H14}/.kiro/skills"
printf -- '---\nname: tech-lead\ndescription: also mine\n---\n# Also mine\n' \
  > "${H14}/my-skills/tech-lead/SKILL.md"
ln -s "${H14}/my-skills/tech-lead" "${H14}/.kiro/skills/tech-lead"

env -i HOME="${H14}" AGENT_SKILLS_HOME="${H14}/.agent-skills" \
  AGENT_SKILLS_CONFIG_DIR="${H14}/.config/agent-skills" \
  PATH="${H14}/.local/bin:/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin" TERM=dumb \
  bash "${OLD_SRC}/bin/agent-skills" install --yes >/dev/null 2>&1

check "pre-upgrade: the old front door is registered" \
  test -L "${H14}/.agents/skills/tech-lead"
check "pre-upgrade: the new name is not registered yet" \
  no_entry "${H14}/.agents/skills/wamala"

# `agent-skills update` changes the CONTENT of the installed clone, not its
# path, so the upgrade is simulated the same way: same source directory, new
# release inside it.
rm -rf "${OLD_SRC}/skills" "${OLD_SRC}/lib" "${OLD_SRC}/bin" "${OLD_SRC}/scripts"
cp -R "${REPO_ROOT}/skills" "${OLD_SRC}/skills"
cp -R "${REPO_ROOT}/lib" "${OLD_SRC}/lib"
cp -R "${REPO_ROOT}/bin" "${OLD_SRC}/bin"
cp -R "${REPO_ROOT}/scripts" "${OLD_SRC}/scripts"
cp "${REPO_ROOT}/VERSION" "${OLD_SRC}/VERSION"

OUT14="$(as_run "${H14}" install --yes 2>&1)"
check "upgrade registers wamala in the standard dir" test -L "${H14}/.agents/skills/wamala"
check "the wamala registration resolves to a SKILL.md" \
  test -f "${H14}/.agents/skills/wamala/SKILL.md"
check "upgrade removes our own tech-lead registration" \
  no_entry "${H14}/.agents/skills/tech-lead"
if printf '%s' "${OUT14}" | grep -q 'no longer ships: tech-lead'; then
  ok "upgrade reports which stale registration it removed"
else
  bad "upgrade reports which stale registration it removed" \
    "$(printf '%s' "${OUT14}" | grep -i 'tech-lead' | head -3)"
fi

check "a user directory named tech-lead survives the upgrade" \
  test -f "${H14}/.claude/skills/tech-lead/SKILL.md"
if [ -L "${H14}/.claude/skills/tech-lead" ]; then
  bad "the user's tech-lead directory was not replaced by a link"
else
  ok "the user's tech-lead directory was not replaced by a link"
fi
check "a user symlink named tech-lead survives the upgrade" \
  test -L "${H14}/.kiro/skills/tech-lead"
check "that user symlink still points into the user's own tree" \
  test -f "${H14}/my-skills/tech-lead/SKILL.md"

# Idempotency of the migration itself.
BEFORE14="$(find "${H14}/.agents/skills" -maxdepth 1 | sort | wc -l | tr -d ' ')"
OUT14B="$(as_run "${H14}" install --yes 2>&1)"
AFTER14="$(find "${H14}/.agents/skills" -maxdepth 1 | sort | wc -l | tr -d ' ')"
if [ "${BEFORE14}" = "${AFTER14}" ]; then
  ok "re-running the upgrade adds nothing (${BEFORE14} entries before and after)"
else
  bad "re-running the upgrade adds nothing" "${BEFORE14} -> ${AFTER14}"
fi
WAMALA_COUNT="$(find "${H14}/.agents/skills" -maxdepth 1 -name wamala | wc -l | tr -d ' ')"
if [ "${WAMALA_COUNT}" = "1" ]; then
  ok "exactly one wamala registration exists after two upgrades"
else
  bad "exactly one wamala registration exists after two upgrades" "found ${WAMALA_COUNT}"
fi
if printf '%s' "${OUT14B}" | grep -q 'no longer ships'; then
  bad "a second upgrade run re-reports a prune it already did"
else
  ok "a second upgrade run has nothing left to prune"
fi
check "verify passes after the migration" as_run "${H14}" verify

# Verify must also SEE an unmigrated stale registration rather than ignore it.
ln -s "${H14}/.agent-skills/skills/tech-lead" "${H14}/.agents/skills/tech-lead"
VERIFY14="$(as_run "${H14}" verify 2>&1 || true)"
if printf '%s' "${VERIFY14}" | grep -q 'stale registration(s) for renamed or removed skills'; then
  ok "verify reports a stale registration for a renamed skill"
else
  bad "verify reports a stale registration for a renamed skill" \
    "$(printf '%s' "${VERIFY14}" | tail -6)"
fi
as_run "${H14}" install --yes >/dev/null 2>&1
check "install clears the stale registration verify complained about" \
  no_entry "${H14}/.agents/skills/tech-lead"

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

# An inherited WORKSPACE_ROOT means the caller is already running the legacy
# model. setup.init must honour it instead of quietly installing globally into
# their real home directory, which is the kind of surprise this release exists
# to remove rather than introduce.
H8B="$(new_home)"
LEGACY_B="${H8B}/work"
mkdir -p "${LEGACY_B}/agent-skills"
cp -R "${REPO_ROOT}/." "${LEGACY_B}/agent-skills/" 2>/dev/null || true
printf 'JIRA_HOST="https://example.atlassian.net"\n' > "${LEGACY_B}/.env"
MODE_OUT="$(
  cd "${LEGACY_B}/agent-skills" && env -i HOME="${H8B}" \
    AGENT_SKILLS_HOME="${H8B}/.agent-skills" \
    AGENT_SKILLS_CONFIG_DIR="${H8B}/.config/agent-skills" \
    WORKSPACE_ROOT="${LEGACY_B}" \
    PATH="/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin" TERM=dumb \
    ./setup.init --yes --no-jira 2>&1 || true
)"
if printf '%s' "${MODE_OUT}" | grep -q 'legacy workspace model'; then
  ok "an inherited WORKSPACE_ROOT with a .env selects the legacy model"
else
  bad "an inherited WORKSPACE_ROOT with a .env selects the legacy model" \
    "$(printf '%s' "${MODE_OUT}" | head -5)"
fi
refute "an inherited WORKSPACE_ROOT does not trigger a global install" \
  test -f "${H8B}/.agent-skills/install.json"
check "the legacy run still produced its workspace artifacts" test -L "${LEGACY_B}/.skills"

# ------------------------------------------------------------------------------
section "uninstall"
# ------------------------------------------------------------------------------
H9="$(new_home)"
mkdir -p "${H9}/.claude/skills/keep-me"
printf -- '---\nname: keep-me\ndescription: keep\n---\n# Keep\n' \
  > "${H9}/.claude/skills/keep-me/SKILL.md"
as_run "${H9}" install --yes >/dev/null 2>&1
check "pre-uninstall: our registration exists" test -L "${H9}/.claude/skills/wamala"
as_run "${H9}" uninstall --yes >/dev/null 2>&1
refute "uninstall removes our host registration" test -e "${H9}/.claude/skills/wamala"
check "uninstall keeps an unrelated user skill" test -f "${H9}/.claude/skills/keep-me/SKILL.md"
refute "uninstall removes the install manifest" test -f "${H9}/.agent-skills/install.json"
check "uninstall leaves the source clone alone" test -f "${REPO_ROOT}/skills/wamala/SKILL.md"

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
section "a flag given without its value fails instead of hanging"
# ------------------------------------------------------------------------------
# `shift 2` shifts nothing when the flag is the last argument, so the parse loop
# used to spin forever printing nothing. A timeout is the assertion: a hang is a
# different failure from a rejection, and only the timeout tells them apart.
H11="$(new_home)"
for FLAG in --hosts --source --branch; do
  FLAG_OUT="$(
    env -i HOME="${H11}" AGENT_SKILLS_HOME="${H11}/.agent-skills" \
      PATH="/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin" TERM=dumb \
      timeout 10 bash "${CLI}" install "${FLAG}" 2>&1
  )"
  FLAG_RC=$?
  if [ "${FLAG_RC}" -eq 124 ]; then
    bad "install ${FLAG} with no value fails fast" "timed out: still looping"
  elif [ "${FLAG_RC}" -eq 0 ]; then
    bad "install ${FLAG} with no value fails fast" "exited 0, should have refused"
  else
    ok "install ${FLAG} with no value fails fast"
  fi
  case "${FLAG_OUT}" in
    *"requires a value"*) ok "install ${FLAG} says the value is missing" ;;
    *) bad "install ${FLAG} says the value is missing" "${FLAG_OUT}" ;;
  esac
done

# ------------------------------------------------------------------------------
section "a foreign DANGLING link in a host directory is not adopted"
# ------------------------------------------------------------------------------
# A live foreign link is already covered above. A dangling one was the broken
# case: ownership was skipped for any link whose target was missing, so a user's
# link to an unmounted volume was replaced, then deleted by uninstall.
H12="$(new_home)"
mkdir -p "${H12}/.claude/skills"
ln -s "${H12}/not-mounted-volume/my-skills/wamala" "${H12}/.claude/skills/wamala"
as_run "${H12}" install --yes >/dev/null 2>&1
FOREIGN_TARGET="$(readlink "${H12}/.claude/skills/wamala" 2>/dev/null || printf '')"
case "${FOREIGN_TARGET}" in
  *not-mounted-volume*) ok "a dangling link we did not write still points where it did" ;;
  *) bad "a dangling link we did not write still points where it did" \
       "now points at: ${FOREIGN_TARGET}" ;;
esac
check "install still registered a skill it does own" \
  test -L "${H12}/.claude/skills/software-engineer"
as_run "${H12}" uninstall --yes >/dev/null 2>&1
check "uninstall did not delete the foreign dangling link" \
  test -L "${H12}/.claude/skills/wamala"

# ------------------------------------------------------------------------------
section "verify agrees with install about a name collision"
# ------------------------------------------------------------------------------
# Install preserves a user's own same-named skill on purpose. Verify used to call
# that preserved state a FAIL and exit 1, so verify could never go green without
# deleting the user's own work.
H13="$(new_home)"
mkdir -p "${H13}/.claude/skills/wamala"
printf -- '---\nname: wamala\n---\nmy own skill\n' \
  > "${H13}/.claude/skills/wamala/SKILL.md"
as_run "${H13}" install --yes >/dev/null 2>&1
V13="$(as_run "${H13}" verify 2>&1)"
V13_RC=$?
if [ "${V13_RC}" -eq 0 ]; then
  ok "verify exits 0 when the only oddity is a user skill install kept"
else
  bad "verify exits 0 when the only oddity is a user skill install kept" "${V13}"
fi
case "${V13}" in
  *"are yours, not ours"*) ok "verify says whose the preserved entry is" ;;
  *) bad "verify says whose the preserved entry is" "${V13}" ;;
esac
check "the user's own skill file was never touched" \
  test -f "${H13}/.claude/skills/wamala/SKILL.md"

# ------------------------------------------------------------------------------
section "an incomplete source tree fails loudly, not silently"
# ------------------------------------------------------------------------------
# A missing host registry used to register nothing, print "installed globally",
# and exit 0, because the host loop runs inside $(...) where the exit status of
# whatever it contains is discarded.
H14="$(new_home)"
BROKEN_SRC="${H14}/broken-source"
mkdir -p "${BROKEN_SRC}"
for ITEM in bin lib scripts skills docs hooks VERSION; do
  [ -e "${REPO_ROOT}/${ITEM}" ] && cp -R "${REPO_ROOT}/${ITEM}" "${BROKEN_SRC}/" 2>/dev/null
done
rm -f "${BROKEN_SRC}/lib/hosts.registry"
B14="$(
  env -i HOME="${H14}" AGENT_SKILLS_HOME="${H14}/.agent-skills" \
    AGENT_SKILLS_SOURCE="${BROKEN_SRC}" \
    PATH="/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin" TERM=dumb \
    bash "${BROKEN_SRC}/bin/agent-skills" install --yes 2>&1
)"
B14_RC=$?
if [ "${B14_RC}" -ne 0 ]; then
  ok "install fails when the host registry is missing"
else
  bad "install fails when the host registry is missing" "exit 0: ${B14}"
fi
case "${B14}" in
  *"installed globally"*) bad "install does not claim success without a registry" "${B14}" ;;
  *) ok "install does not claim success without a registry" ;;
esac
case "${B14}" in
  *registry*) ok "install names the registry as the missing piece" ;;
  *) bad "install names the registry as the missing piece" "${B14}" ;;
esac

# ------------------------------------------------------------------------------
section "task scratch does not dirty the repository it runs in"
# ------------------------------------------------------------------------------
# The cache moved inside the repo being worked on, so start-task left an
# untracked .cache/ behind and an agent running `git add -A` would commit it.
H15="$(new_home)"
as_run "${H15}" install --yes >/dev/null 2>&1
SCRATCH_REPO="${H15}/scratch-repo"
mkdir -p "${SCRATCH_REPO}"
(
  cd "${SCRATCH_REPO}" || exit 1
  git init --quiet 2>/dev/null
  git config user.email t@example.com 2>/dev/null
  git config user.name tester 2>/dev/null
  printf 'hello\n' > README.md
  git add README.md 2>/dev/null
  git commit --quiet -m init 2>/dev/null
)
env -i HOME="${H15}" AGENT_SKILLS_HOME="${H15}/.agent-skills" \
  PATH="/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin" TERM=dumb \
  bash -c "cd '${SCRATCH_REPO}' && bash '${CLI}' start-task --skill software-engineer" \
  >/dev/null 2>&1
DIRT="$(cd "${SCRATCH_REPO}" && git status --porcelain 2>/dev/null)"
case "${DIRT}" in
  *.cache*) bad "start-task leaves the repository clean" "git status shows: ${DIRT}" ;;
  *) ok "start-task leaves the repository clean" ;;
esac
if grep -qx '\.cache/' "${SCRATCH_REPO}/.git/info/exclude" 2>/dev/null; then
  ok "the cache is excluded locally, without editing a tracked .gitignore"
else
  bad "the cache is excluded locally, without editing a tracked .gitignore"
fi
refute "no tracked .gitignore was created in the user repo" \
  test -f "${SCRATCH_REPO}/.gitignore"


# ------------------------------------------------------------------------------
section "an existing legacy workspace is not silently migrated"
# ------------------------------------------------------------------------------
# resolve_install_mode consulted the legacy .env beside the clone only when
# --verify was passed, so the same machine answered "legacy" for
# `./setup.init --verify` and "global" for a bare run or --update. An existing
# user typing the v0.36-documented command was converted without being told.
H16="$(new_home)"
LEGACY_WS="${H16}/legacy workspace"
LEGACY_CLONE="${LEGACY_WS}/agent-skills"
mkdir -p "${LEGACY_CLONE}"
for ITEM in bin lib scripts skills docs hooks VERSION setup.init .env.example; do
  [ -e "${REPO_ROOT}/${ITEM}" ] && cp -R "${REPO_ROOT}/${ITEM}" "${LEGACY_CLONE}/" 2>/dev/null
done
# A v0.36-shaped workspace: a managed .env beside the clone, plus the artifacts
# that model created.
cat > "${LEGACY_WS}/.env" <<'ENVEOF'
# >>> agent-skills setup.init
JIRA_HOST=
JIRA_LOGIN=
# <<< agent-skills setup.init
ENVEOF
ln -s "${LEGACY_CLONE}/skills" "${LEGACY_WS}/.skills"
printf '0.36.0\n' > "${LEGACY_WS}/.agent-skills.lock"

as_setup() {
  env -i HOME="${H16}" \
    PATH="/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin" \
    TERM=dumb \
    bash "${LEGACY_CLONE}/setup.init" "$@" 2>&1
}

for INVOCATION in "--verify" "--yes --no-connectivity-check --no-credential-probe"; do
  # shellcheck disable=SC2086
  ROUTE_OUT="$(as_setup ${INVOCATION})"
  case "${ROUTE_OUT}" in
    *"legacy workspace model"*)
      ok "setup.init ${INVOCATION} keeps the legacy workspace model" ;;
    *)
      bad "setup.init ${INVOCATION} keeps the legacy workspace model" \
        "$(printf '%s' "${ROUTE_OUT}" | head -5)" ;;
  esac
done
refute "no global install root was created behind the user's back" \
  test -e "${H16}/.agent-skills/install.json"
refute "no launcher was put on PATH behind the user's back" \
  test -e "${H16}/.local/bin/agent-skills"
check "the legacy .skills symlink is still there" test -L "${LEGACY_WS}/.skills"

# Opting in explicitly must still work.
ROUTE_OUT="$(as_setup --global --yes)"
case "${ROUTE_OUT}" in
  *"installed globally"*) ok "--global still opts in to the new model" ;;
  *) bad "--global still opts in to the new model" \
       "$(printf '%s' "${ROUTE_OUT}" | tail -5)" ;;
esac
check "opting in created the global install" test -f "${H16}/.agent-skills/install.json"

# ------------------------------------------------------------------------------
printf '\n'
if [ "${FAIL}" -eq 0 ]; then
  printf 'ok: global-install tests passed (%s assertions)\n' "${PASS}"
  exit 0
fi
printf 'FAIL: %s of %s assertions failed:%s\n' \
  "${FAIL}" "$((PASS + FAIL))" "${FAILED_CASES}" >&2
exit 1
