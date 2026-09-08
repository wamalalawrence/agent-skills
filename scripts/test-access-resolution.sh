#!/usr/bin/env bash
# Regression tests for the generic access resolver (v0.37.0).
#
# The interesting cases are the security ones. In particular:
#
#   * a committed file must never be able to select a credential profile;
#   * a secret value must never appear in any output, in any mode;
#   * a profile stored in the OS keychain must not silently start reading from
#     the weaker file fallback.
#
# Every case runs against a throwaway HOME and config dir. The file backend is
# forced where a test needs to assert storage behaviour, so the suite does not
# write to the developer's real keychain.
#
# Usage: bash scripts/test-access-resolution.sh
# Exit 0 when every case passes, 1 otherwise.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACCESS="${REPO_ROOT}/scripts/access.py"

PASS=0
FAIL=0
FAILED_CASES=""
SANDBOXES=""

cleanup() {
  local box
  for box in ${SANDBOXES}; do
    [ -n "${box}" ] || continue
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

section() { printf '\n== %s ==\n' "$1"; }

# A canary token. If this string ever appears in output, a secret leaked.
CANARY="canary-secret-value-do-not-print-8471"

new_box() {
  local base
  base="$(mktemp -d)"
  SANDBOXES="${SANDBOXES} ${base}"
  mkdir -p "${base}/home" "${base}/repo"
  ( cd "${base}/repo" && git init -q && git config user.email "test@example.com" \
      && git config user.name "Test" ) >/dev/null 2>&1
  printf '%s' "${base}"
}

# Run the resolver with an isolated environment. Extra env assignments may be
# passed before the subcommand using NAME=value pairs in AS_EXTRA_ENV.
run_access() {
  local box="$1"
  shift
  env -i \
    HOME="${box}/home" \
    AGENT_SKILLS_CONFIG_DIR="${box}/home/.config/agent-skills" \
    AGENT_SKILLS_SECRET_BACKEND="${AS_BACKEND:-file}" \
    PATH="/usr/bin:/bin:/usr/sbin:/sbin" \
    TERM=dumb \
    ${AS_EXTRA_ENV:-} \
    python3 "${ACCESS}" --cwd "${box}/repo" "$@"
}

# ------------------------------------------------------------------------------
section "backend reporting"
# ------------------------------------------------------------------------------
BOX="$(new_box)"
OUT="$(AS_BACKEND="" run_access "${BOX}" backend 2>&1)"
if printf '%s' "${OUT}" | grep -q 'secret storage:'; then
  ok "backend reports the active store"
else
  bad "backend reports the active store" "${OUT}"
fi
JSON="$(AS_BACKEND="" run_access "${BOX}" backend --json 2>&1)"
if printf '%s' "${JSON}" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert "active" in d' 2>/dev/null; then
  ok "backend --json is valid and reports the active store"
else
  bad "backend --json is valid and reports the active store" "${JSON}"
fi
OUT="$(AS_BACKEND="file" run_access "${BOX}" backend 2>&1)"
if printf '%s' "${OUT}" | grep -q 'WARN'; then
  ok "the file fallback is reported as a warning, never silently"
else
  bad "the file fallback is reported as a warning, never silently" "${OUT}"
fi
if printf '%s' "${OUT}" | grep -q '0600'; then
  ok "the fallback report states the restricted mode"
else
  bad "the fallback report states the restricted mode"
fi

# ------------------------------------------------------------------------------
section "no credentials exist yet: lazy setup, not a crash"
# ------------------------------------------------------------------------------
BOX="$(new_box)"
OUT="$(run_access "${BOX}" resolve --service jira --resource https://example.atlassian.net \
  --require host,login,token --secret token --no-capability 2>&1)"
RC=$?
if [ "${RC}" -eq 1 ]; then
  ok "unresolved access exits 1 (distinguishable from a crash)"
else
  bad "unresolved access exits 1" "exit ${RC}"
fi
if printf '%s' "${OUT}" | grep -q 'status: needs-setup'; then
  ok "unresolved access reports needs-setup"
else
  bad "unresolved access reports needs-setup" "${OUT}"
fi
if printf '%s' "${OUT}" | grep -q 'missing fields'; then
  ok "the report names the missing fields"
else
  bad "the report names the missing fields"
fi
if printf '%s' "${OUT}" | grep -qi 'hidden input'; then
  ok "the guidance points at hidden input rather than asking for the value"
else
  bad "the guidance points at hidden input rather than asking for the value" "${OUT}"
fi
if printf '%s' "${OUT}" | grep -q 'does not authorize destructive action'; then
  ok "resolution explicitly disclaims authorization"
else
  bad "resolution explicitly disclaims authorization"
fi
# The resource the caller supplied is a resolved field, not a missing one.
if printf '%s' "${OUT}" | grep -q 'host: set (hidden)'; then
  ok "a caller-supplied resource satisfies the host field"
else
  bad "a caller-supplied resource satisfies the host field" "${OUT}"
fi

# ------------------------------------------------------------------------------
section "arbitrary custom service, arbitrary fields"
# ------------------------------------------------------------------------------
BOX="$(new_box)"
AS_EXTRA_ENV="AGENT_SKILLS_SECRET_VALUE_CLIENT_SECRET=${CANARY}" \
  run_access "${BOX}" set --profile acme-orders-api --service internal-orders-api \
  --resource https://orders.example.com --account svc-orders \
  --field base_url=https://orders.example.com --field client_id=abc123 \
  --secret-field client_secret >/dev/null 2>&1
RC=$?
if [ "${RC}" -eq 0 ]; then
  ok "an identity can be created for a service the installer never heard of"
else
  bad "an identity can be created for a service the installer never heard of" "exit ${RC}"
fi
OUT="$(run_access "${BOX}" resolve --service internal-orders-api \
  --require base_url,client_id,client_secret --secret client_secret --no-capability 2>&1)"
if printf '%s' "${OUT}" | grep -q 'status: resolved'; then
  ok "the custom service resolves with its own field names"
else
  bad "the custom service resolves with its own field names" "${OUT}"
fi
if printf '%s' "${OUT}" | grep -q "${CANARY}"; then
  bad "the custom-service secret value never appears in output"
else
  ok "the custom-service secret value never appears in output"
fi
JSON="$(run_access "${BOX}" resolve --service internal-orders-api \
  --require base_url,client_id,client_secret --secret client_secret --no-capability --json 2>&1)"
if printf '%s' "${JSON}" | grep -q "${CANARY}"; then
  bad "--json output never contains a secret value"
else
  ok "--json output never contains a secret value"
fi
if printf '%s' "$(run_access "${BOX}" profiles 2>&1)" | grep -q "${CANARY}"; then
  bad "profiles listing never contains a secret value"
else
  ok "profiles listing never contains a secret value"
fi
if printf '%s' "$(run_access "${BOX}" profiles --json 2>&1)" | grep -q "${CANARY}"; then
  bad "profiles --json never contains a secret value"
else
  ok "profiles --json never contains a secret value"
fi

# ------------------------------------------------------------------------------
section "secret storage permissions"
# ------------------------------------------------------------------------------
# `stat` flags differ between BSD and GNU, and both exist on developer machines.
# python3 is already a hard dependency, so use it and stay portable.
file_mode() {
  python3 -c 'import os, stat, sys; print(oct(stat.S_IMODE(os.stat(sys.argv[1]).st_mode))[2:])' "$1"
}

SECRET_FILE="${BOX}/home/.config/agent-skills/secrets/acme-orders-api.json"
if [ -f "${SECRET_FILE}" ]; then
  ok "the file backend wrote the secret outside every repository"
  MODE="$(file_mode "${SECRET_FILE}")"
  if [ "${MODE}" = "600" ]; then
    ok "the secret file is mode 0600"
  else
    bad "the secret file is mode 0600" "got ${MODE}"
  fi
  DIRMODE="$(file_mode "$(dirname "${SECRET_FILE}")")"
  if [ "${DIRMODE}" = "700" ]; then
    ok "the secrets directory is mode 0700"
  else
    bad "the secrets directory is mode 0700" "got ${DIRMODE}"
  fi
  METAMODE="$(file_mode "${BOX}/home/.config/agent-skills/credentials.json")"
  if [ "${METAMODE}" = "600" ]; then
    ok "the profile metadata file is mode 0600"
  else
    bad "the profile metadata file is mode 0600" "got ${METAMODE}"
  fi
else
  bad "the file backend wrote the secret outside every repository" "no ${SECRET_FILE}"
fi
META="${BOX}/home/.config/agent-skills/credentials.json"
if grep -q "${CANARY}" "${META}" 2>/dev/null; then
  bad "profile metadata contains no secret value"
else
  ok "profile metadata contains no secret value"
fi
if run_access "${BOX}" check-permissions >/dev/null 2>&1; then
  ok "check-permissions passes on freshly written state"
else
  bad "check-permissions passes on freshly written state"
fi
chmod 644 "${SECRET_FILE}"
if run_access "${BOX}" check-permissions >/dev/null 2>&1; then
  bad "check-permissions fails on a world-readable secret file"
else
  ok "check-permissions fails on a world-readable secret file"
fi
chmod 600 "${SECRET_FILE}"

# ------------------------------------------------------------------------------
section "environment variable override wins"
# ------------------------------------------------------------------------------
BOX="$(new_box)"
AS_EXTRA_ENV="AGENT_SKILLS_SECRET_VALUE_TOKEN=stored-token-value" \
  run_access "${BOX}" set --profile work-jira --service jira \
  --resource https://work.atlassian.net --account person@example.com \
  --field host=https://work.atlassian.net --field login=person@example.com \
  --secret-field token >/dev/null 2>&1
OUT="$(AS_EXTRA_ENV="JIRA_API_TOKEN=${CANARY}" run_access "${BOX}" resolve --service jira \
  --require host,login,token --secret token --no-capability 2>&1)"
if printf '%s' "${OUT}" | grep -q 'token: set (hidden) \[process-env:JIRA_API_TOKEN\]'; then
  ok "an explicit process environment variable outranks a stored identity"
else
  bad "an explicit process environment variable outranks a stored identity" "${OUT}"
fi
if printf '%s' "${OUT}" | grep -q "${CANARY}"; then
  bad "the env-provided secret is not echoed"
else
  ok "the env-provided secret is not echoed"
fi
OUT="$(AS_EXTRA_ENV="AGENT_SKILLS_JIRA_TOKEN=${CANARY}" run_access "${BOX}" resolve \
  --service jira --require host,login,token --secret token --no-capability 2>&1)"
if printf '%s' "${OUT}" | grep -q 'process-env:AGENT_SKILLS_JIRA_TOKEN'; then
  ok "the generic AGENT_SKILLS_<SERVICE>_<FIELD> form is honoured"
else
  bad "the generic AGENT_SKILLS_<SERVICE>_<FIELD> form is honoured" "${OUT}"
fi

# ------------------------------------------------------------------------------
section "exactly one compatible identity is used without asking"
# ------------------------------------------------------------------------------
OUT="$(run_access "${BOX}" resolve --service jira --require host,login,token \
  --secret token --no-capability 2>&1)"
if printf '%s' "${OUT}" | grep -q 'status: resolved'; then
  ok "a single compatible identity resolves without a prompt"
else
  bad "a single compatible identity resolves without a prompt" "${OUT}"
fi
if printf '%s' "${OUT}" | grep -q 'the only compatible identity'; then
  ok "the report says why that identity was chosen"
else
  bad "the report says why that identity was chosen" "${OUT}"
fi

# ------------------------------------------------------------------------------
section "two projects share one global identity"
# ------------------------------------------------------------------------------
mkdir -p "${BOX}/repo-b"
( cd "${BOX}/repo-b" && git init -q ) >/dev/null 2>&1
OUT_B="$(
  env -i HOME="${BOX}/home" \
    AGENT_SKILLS_CONFIG_DIR="${BOX}/home/.config/agent-skills" \
    AGENT_SKILLS_SECRET_BACKEND=file PATH="/usr/bin:/bin" TERM=dumb \
    python3 "${ACCESS}" --cwd "${BOX}/repo-b" resolve --service jira \
    --require host,login,token --secret token --no-capability 2>&1
)"
if printf '%s' "${OUT_B}" | grep -q 'status: resolved'; then
  ok "a second repository reuses the same identity with no re-entry"
else
  bad "a second repository reuses the same identity with no re-entry" "${OUT_B}"
fi
COUNT="$(python3 -c '
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    data = json.load(handle)
print(len(data.get("profiles", {})))
' "${BOX}/home/.config/agent-skills/credentials.json")"
if [ "${COUNT}" = "1" ]; then
  ok "sharing an identity did not duplicate the stored credential"
else
  bad "sharing an identity did not duplicate the stored credential" "profiles=${COUNT}"
fi

# ------------------------------------------------------------------------------
section "two accounts for one service"
# ------------------------------------------------------------------------------
BOX="$(new_box)"
AS_EXTRA_ENV="AGENT_SKILLS_SECRET_VALUE_TOKEN=tok-personal" \
  run_access "${BOX}" set --profile personal-github --service github \
  --resource https://github.com --account personal-user \
  --field host=https://github.com --secret-field token >/dev/null 2>&1
AS_EXTRA_ENV="AGENT_SKILLS_SECRET_VALUE_TOKEN=tok-work" \
  run_access "${BOX}" set --profile work-github --service github \
  --resource https://github.com --account work-user \
  --field host=https://github.com --secret-field token >/dev/null 2>&1
OUT="$(run_access "${BOX}" resolve --service github --require host,token \
  --secret token --no-capability 2>&1)"
if printf '%s' "${OUT}" | grep -q 'status: needs-setup'; then
  ok "two compatible identities do not silently pick one"
else
  bad "two compatible identities do not silently pick one" "${OUT}"
fi
if printf '%s' "${OUT}" | grep -q 'personal-github' \
  && printf '%s' "${OUT}" | grep -q 'work-github'; then
  ok "both candidate identities are named so the user can choose"
else
  bad "both candidate identities are named so the user can choose" "${OUT}"
fi
run_access "${BOX}" bind --service github --profile work-github >/dev/null 2>&1
OUT="$(run_access "${BOX}" resolve --service github --require host,token \
  --secret token --no-capability 2>&1)"
if printf '%s' "${OUT}" | grep -q 'identity: work-github'; then
  ok "binding resolves the ambiguity for this repository"
else
  bad "binding resolves the ambiguity for this repository" "${OUT}"
fi
BINDINGS="${BOX}/home/.config/agent-skills/bindings.json"
if grep -qE 'tok-work|tok-personal' "${BINDINGS}" 2>/dev/null; then
  bad "the binding registry holds no secret"
else
  ok "the binding registry holds no secret"
fi

# Resource-based separation: an identity for a different host is not offered.
AS_EXTRA_ENV="AGENT_SKILLS_SECRET_VALUE_TOKEN=tok-selfhosted" \
  run_access "${BOX}" set --profile client-acme-gitlab --service gitlab \
  --resource https://gitlab.example.com --account acme \
  --field host=https://gitlab.example.com --secret-field token >/dev/null 2>&1
OUT="$(run_access "${BOX}" resolve --service gitlab --resource https://gitlab.example.org \
  --require host,token --secret token --no-capability 2>&1)"
if printf '%s' "${OUT}" | grep -q 'client-acme-gitlab'; then
  bad "an identity for a different host is not used for another host" "${OUT}"
else
  ok "an identity for a different host is not used for another host"
fi

# ------------------------------------------------------------------------------
section "SECURITY: a committed file cannot select a credential profile"
# ------------------------------------------------------------------------------
BOX="$(new_box)"
# Two identities for one service, so nothing can be auto-selected. That isolates
# the property under test: whether a committed file can steer the choice.
AS_EXTRA_ENV="AGENT_SKILLS_SECRET_VALUE_PASSWORD=${CANARY}" \
  run_access "${BOX}" set --profile production-readonly-db --service postgres \
  --resource db.example.com --account readonly \
  --field host=db.example.com --field port=5432 --field database=orders \
  --field username=readonly --secret-field password >/dev/null 2>&1
AS_EXTRA_ENV="AGENT_SKILLS_SECRET_VALUE_PASSWORD=sandbox-password" \
  run_access "${BOX}" set --profile sandbox-db --service postgres \
  --resource db.example.com --account sandbox \
  --field host=db.example.com --field port=5432 --field database=sandbox \
  --field username=sandbox --secret-field password >/dev/null 2>&1

# A hostile repository commits a config that tries to name someone else's
# identity. This is the critical acceptance criterion for this release.
cat > "${BOX}/repo/.agent-skills.local.yml" <<'YML'
credentials:
  postgres: production-readonly-db
YML
( cd "${BOX}/repo" && git add -f .agent-skills.local.yml \
    && git commit -q -m "hostile: try to claim a credential" ) >/dev/null 2>&1

OUT="$(run_access "${BOX}" resolve --service postgres \
  --require host,port,database,username,password --secret password --no-capability 2>&1)"
if printf '%s' "${OUT}" | grep -q 'tracked by git and was ignored'; then
  ok "a git-tracked .agent-skills.local.yml is refused with an explanation"
else
  bad "a git-tracked .agent-skills.local.yml is refused with an explanation" "${OUT}"
fi
if printf '%s' "${OUT}" | grep -q 'identity: production-readonly-db'; then
  bad "a committed file cannot select a credential profile" "${OUT}"
else
  ok "a committed file cannot select a credential profile"
fi
if printf '%s' "${OUT}" | grep -q 'status: needs-setup'; then
  ok "the hostile repository is left unresolved, not silently served"
else
  bad "the hostile repository is left unresolved, not silently served" "${OUT}"
fi
if printf '%s' "${OUT}" | grep -q "${CANARY}"; then
  bad "the hostile repository obtained no secret value"
else
  ok "the hostile repository obtained no secret value"
fi

# The same file, untracked, is trusted — that is the supported override.
( cd "${BOX}/repo" && git rm -q --cached .agent-skills.local.yml \
    && printf '.agent-skills.local.yml\n' > .gitignore \
    && git add .gitignore && git commit -q -m "ignore local overrides" ) >/dev/null 2>&1
OUT="$(run_access "${BOX}" resolve --service postgres \
  --require host,port,database,username,password --secret password --no-capability 2>&1)"
if printf '%s' "${OUT}" | grep -q 'identity: production-readonly-db'; then
  ok "an untracked .agent-skills.local.yml is honoured as a project override"
else
  bad "an untracked .agent-skills.local.yml is honoured as a project override" "${OUT}"
fi
if printf '%s' "${OUT}" | grep -q 'status: resolved'; then
  ok "the project override resolves every required field"
else
  bad "the project override resolves every required field" "${OUT}"
fi

# Strict binding removes the last automatic path: a lone compatible identity is
# no longer used unless the user bound it. For a machine holding several
# customers' credentials this is the safe posture.
BOXS="$(new_box)"
AS_EXTRA_ENV="AGENT_SKILLS_SECRET_VALUE_TOKEN=strict-token" \
  run_access "${BOXS}" set --profile lone-jira --service jira \
  --resource https://one.atlassian.net --field host=https://one.atlassian.net \
  --field login=one@example.com --secret-field token >/dev/null 2>&1
OUT="$(run_access "${BOXS}" resolve --service jira --require host,login,token \
  --secret token --no-capability 2>&1)"
if printf '%s' "${OUT}" | grep -q 'identity: lone-jira'; then
  ok "by default a lone compatible identity is used (shared-account UX)"
else
  bad "by default a lone compatible identity is used" "${OUT}"
fi
OUT="$(AS_EXTRA_ENV="AGENT_SKILLS_STRICT_BINDING=1" run_access "${BOXS}" resolve \
  --service jira --require host,login,token --secret token --no-capability 2>&1)"
if printf '%s' "${OUT}" | grep -q 'strict binding is on'; then
  ok "strict binding refuses to auto-select a lone identity"
else
  bad "strict binding refuses to auto-select a lone identity" "${OUT}"
fi
if printf '%s' "${OUT}" | grep -q 'status: needs-setup'; then
  ok "strict binding leaves the request unresolved until bound"
else
  bad "strict binding leaves the request unresolved until bound" "${OUT}"
fi
run_access "${BOXS}" bind --service jira --profile lone-jira >/dev/null 2>&1
OUT="$(AS_EXTRA_ENV="AGENT_SKILLS_STRICT_BINDING=1" run_access "${BOXS}" resolve \
  --service jira --require host,login,token --secret token --no-capability 2>&1)"
if printf '%s' "${OUT}" | grep -q 'status: resolved'; then
  ok "strict binding resolves once an explicit binding exists"
else
  bad "strict binding resolves once an explicit binding exists" "${OUT}"
fi

# A committed .agent-skills.yml may describe a service but never choose an identity.
BOX2="$(new_box)"
AS_EXTRA_ENV="AGENT_SKILLS_SECRET_VALUE_TOKEN=${CANARY}" \
  run_access "${BOX2}" set --profile someone-elses-jira --service jira \
  --resource https://victim.atlassian.net --field host=https://victim.atlassian.net \
  --field login=victim@example.com --secret-field token >/dev/null 2>&1
cat > "${BOX2}/repo/.agent-skills.yml" <<'YML'
mode: in-repo
credentials:
  jira: someone-elses-jira
jira:
  host: "https://attacker.example.com"
YML
( cd "${BOX2}/repo" && git add .agent-skills.yml \
    && git commit -q -m "committed config" ) >/dev/null 2>&1
OUT="$(run_access "${BOX2}" resolve --service jira --resource https://attacker.example.com \
  --require host,login,token --secret token --no-capability 2>&1)"
if printf '%s' "${OUT}" | grep -q 'someone-elses-jira'; then
  bad "a committed .agent-skills.yml credentials block is never read" "${OUT}"
else
  ok "a committed .agent-skills.yml credentials block is never read"
fi
if printf '%s' "${OUT}" | grep -q "${CANARY}"; then
  bad "the committed config obtained no secret value"
else
  ok "the committed config obtained no secret value"
fi

# ------------------------------------------------------------------------------
section "SECURITY: invalid and hostile names are rejected, not sanitised"
# ------------------------------------------------------------------------------
BOX="$(new_box)"
if run_access "${BOX}" set --profile "../../etc/passwd" --service jira \
  --field host=x >/dev/null 2>&1; then
  bad "a path-traversal profile name is rejected"
else
  ok "a path-traversal profile name is rejected"
fi
if run_access "${BOX}" set --profile "ok-name" --service "jira; rm -rf /" \
  --field host=x >/dev/null 2>&1; then
  bad "a shell-metacharacter service name is rejected"
else
  ok "a shell-metacharacter service name is rejected"
fi
if run_access "${BOX}" resolve --service jira --require 'token;whoami' \
  --no-capability >/dev/null 2>&1; then
  bad "a shell-metacharacter field name is rejected"
else
  ok "a shell-metacharacter field name is rejected"
fi
if run_access "${BOX}" set --profile ok-name --service jira \
  --field token=plain-text-token >/dev/null 2>&1; then
  bad "a secret-looking value passed as a plain --field is refused"
else
  ok "a secret-looking value passed as a plain --field is refused"
fi
# A hostile binding naming a nonexistent profile must not crash or invent one.
mkdir -p "${BOX}/home/.config/agent-skills"
cat > "${BOX}/repo/.agent-skills.local.yml" <<'YML'
credentials:
  jira: no-such-identity
YML
OUT="$(run_access "${BOX}" resolve --service jira --require host,token \
  --secret token --no-capability 2>&1)"
if printf '%s' "${OUT}" | grep -q 'does not exist on this machine'; then
  ok "a binding naming a nonexistent identity is reported, not invented"
else
  bad "a binding naming a nonexistent identity is reported, not invented" "${OUT}"
fi

# ------------------------------------------------------------------------------
section "SECURITY: no silent downgrade from a secure store"
# ------------------------------------------------------------------------------
BOX="$(new_box)"
AS_EXTRA_ENV="AGENT_SKILLS_SECRET_VALUE_TOKEN=${CANARY}" \
  run_access "${BOX}" set --profile keychain-only --service demo-service \
  --field host=https://demo.example.com --secret-field token >/dev/null 2>&1
# Rewrite the recorded backend to one that cannot possibly be available here.
python3 - "${BOX}/home/.config/agent-skills/credentials.json" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as handle:
    data = json.load(handle)
data["profiles"]["keychain-only"]["backend"] = "secret-service"
with open(path, "w", encoding="utf-8") as handle:
    json.dump(data, handle, indent=2)
PY
OUT="$(run_access "${BOX}" resolve --service demo-service --require host,token \
  --secret token --no-capability 2>&1)"
if printf '%s' "${OUT}" | grep -qi 'refusing to fall back to weaker storage'; then
  ok "an unavailable secure store is reported instead of downgraded"
else
  bad "an unavailable secure store is reported instead of downgraded" "${OUT}"
fi
if printf '%s' "${OUT}" | grep -q 'status: needs-setup'; then
  ok "the downgrade refusal leaves the request unresolved rather than half-resolved"
else
  bad "the downgrade refusal leaves the request unresolved" "${OUT}"
fi
if run_access "${BOX}" set --profile x --service y --backend no-such-backend \
  --field host=z >/dev/null 2>&1; then
  bad "an unknown forced backend is rejected"
else
  ok "an unknown forced backend is rejected"
fi

# ------------------------------------------------------------------------------
section "SECURITY: a secret is never solicited without a terminal"
# ------------------------------------------------------------------------------
BOX="$(new_box)"
OUT="$(
  env -i HOME="${BOX}/home" \
    AGENT_SKILLS_CONFIG_DIR="${BOX}/home/.config/agent-skills" \
    AGENT_SKILLS_SECRET_BACKEND=file PATH="/usr/bin:/bin" TERM=dumb \
    python3 "${ACCESS}" --cwd "${BOX}/repo" set --profile p1 --service svc \
    --secret-field token < /dev/null 2>&1
)"
if printf '%s' "${OUT}" | grep -q 'cannot read secret'; then
  ok "with no TTY the resolver refuses rather than asking an agent to relay a secret"
else
  bad "with no TTY the resolver refuses rather than asking an agent to relay a secret" "${OUT}"
fi
if printf '%s' "${OUT}" | grep -q 'must not be relayed through an agent conversation'; then
  ok "the refusal explains why"
else
  bad "the refusal explains why"
fi

# ------------------------------------------------------------------------------
section "legacy .env compatibility"
# ------------------------------------------------------------------------------
BOX="$(new_box)"
cat > "${BOX}/.env" <<EOF
# >>> agent-skills setup.init
JIRA_HOST="https://legacy.atlassian.net"
JIRA_LOGIN="legacy@example.com"
JIRA_AUTH_TYPE="bearer"
JIRA_API_TOKEN="${CANARY}"
# <<< agent-skills setup.init
EOF
OUT="$(
  env -i HOME="${BOX}/home" \
    AGENT_SKILLS_CONFIG_DIR="${BOX}/home/.config/agent-skills" \
    AGENT_SKILLS_SECRET_BACKEND=file \
    WORKSPACE_ROOT="${BOX}" PATH="/usr/bin:/bin" TERM=dumb \
    python3 "${ACCESS}" --cwd "${BOX}/repo" resolve --service jira \
    --require host,login,token --secret token --no-capability 2>&1
)"
if printf '%s' "${OUT}" | grep -q 'status: resolved'; then
  ok "a pre-0.37 workspace .env still resolves access"
else
  bad "a pre-0.37 workspace .env still resolves access" "${OUT}"
fi
if printf '%s' "${OUT}" | grep -q 'legacy-config:JIRA_API_TOKEN'; then
  ok "the report says the value came from legacy configuration"
else
  bad "the report says the value came from legacy configuration" "${OUT}"
fi
if printf '%s' "${OUT}" | grep -q "${CANARY}"; then
  bad "the legacy secret value is not echoed"
else
  ok "the legacy secret value is not echoed"
fi

# An unresolved ${VAR} placeholder is incomplete configuration, not a value.
cat > "${BOX}/.jira-config.yml" <<'YML'
installation: cloud
server: ${JIRA_HOST}
login: ${JIRA_LOGIN}
auth_type: ${JIRA_AUTH_TYPE}
YML
OUT="$(
  env -i HOME="${BOX}/home" \
    AGENT_SKILLS_CONFIG_DIR="${BOX}/home/.config/agent-skills" \
    AGENT_SKILLS_SECRET_BACKEND=file PATH="/usr/bin:/bin" TERM=dumb \
    python3 "${ACCESS}" --cwd "${BOX}/repo" resolve --service jira \
    --require host --no-capability --json 2>&1
)"
if printf '%s' "${OUT}" | grep -q '\${JIRA_HOST}'; then
  bad "an unresolved placeholder is never treated as a value" "${OUT}"
else
  ok "an unresolved placeholder is never treated as a value"
fi

# import-legacy is read-only until asked.
OUT="$(
  env -i HOME="${BOX}/home" \
    AGENT_SKILLS_CONFIG_DIR="${BOX}/home/.config/agent-skills" \
    AGENT_SKILLS_SECRET_BACKEND=file \
    WORKSPACE_ROOT="${BOX}" PATH="/usr/bin:/bin" TERM=dumb \
    python3 "${ACCESS}" --cwd "${BOX}/repo" import-legacy 2>&1
)"
if printf '%s' "${OUT}" | grep -q 'read-only report'; then
  ok "import-legacy is read-only by default"
else
  bad "import-legacy is read-only by default" "${OUT}"
fi
if printf '%s' "${OUT}" | grep -q "${CANARY}"; then
  bad "import-legacy never displays a secret value"
else
  ok "import-legacy never displays a secret value"
fi
if [ -f "${BOX}/home/.config/agent-skills/credentials.json" ]; then
  bad "import-legacy wrote nothing without --apply"
else
  ok "import-legacy wrote nothing without --apply"
fi
env -i HOME="${BOX}/home" \
  AGENT_SKILLS_CONFIG_DIR="${BOX}/home/.config/agent-skills" \
  AGENT_SKILLS_SECRET_BACKEND=file \
  WORKSPACE_ROOT="${BOX}" PATH="/usr/bin:/bin" TERM=dumb \
  python3 "${ACCESS}" --cwd "${BOX}/repo" import-legacy --apply >/dev/null 2>&1
if [ -f "${BOX}/home/.config/agent-skills/credentials.json" ]; then
  ok "import-legacy --apply creates the identity"
else
  bad "import-legacy --apply creates the identity"
fi
check_legacy_kept() { test -f "${BOX}/.env"; }
if check_legacy_kept; then
  ok "import-legacy never deletes the legacy file"
else
  bad "import-legacy never deletes the legacy file"
fi

# ------------------------------------------------------------------------------
section "capability preference beats storing a secret"
# ------------------------------------------------------------------------------
BOX="$(new_box)"
FAKE_BIN="${BOX}/fakebin"
mkdir -p "${FAKE_BIN}"
cat > "${FAKE_BIN}/gh" <<'SH'
#!/bin/sh
# Minimal stand-in for an authenticated gh CLI.
if [ "$1" = "auth" ] && [ "$2" = "status" ]; then
  echo "github.com: logged in"
  exit 0
fi
exit 1
SH
chmod +x "${FAKE_BIN}/gh"
OUT="$(
  env -i HOME="${BOX}/home" \
    AGENT_SKILLS_CONFIG_DIR="${BOX}/home/.config/agent-skills" \
    AGENT_SKILLS_SECRET_BACKEND=file \
    PATH="${FAKE_BIN}:/usr/bin:/bin" TERM=dumb \
    python3 "${ACCESS}" --cwd "${BOX}/repo" resolve --service github \
    --require host,token --secret token 2>&1
)"
if printf '%s' "${OUT}" | grep -q 'status: resolved'; then
  ok "an authenticated CLI resolves access with no stored secret"
else
  bad "an authenticated CLI resolves access with no stored secret" "${OUT}"
fi
if printf '%s' "${OUT}" | grep -q 'via: authenticated-cli'; then
  ok "the report names the capability that satisfied the request"
else
  bad "the report names the capability that satisfied the request" "${OUT}"
fi
if printf '%s' "${OUT}" | grep -q 'No credential was read or stored'; then
  ok "the capability path states that nothing was stored"
else
  bad "the capability path states that nothing was stored"
fi
if [ -f "${BOX}/home/.config/agent-skills/credentials.json" ]; then
  bad "the capability path created no credential state"
else
  ok "the capability path created no credential state"
fi

# ------------------------------------------------------------------------------
section "forget removes secrets and bindings"
# ------------------------------------------------------------------------------
BOX="$(new_box)"
AS_EXTRA_ENV="AGENT_SKILLS_SECRET_VALUE_TOKEN=${CANARY}" \
  run_access "${BOX}" set --profile temp-identity --service demo \
  --field host=https://demo.example.com --secret-field token >/dev/null 2>&1
run_access "${BOX}" bind --service demo --profile temp-identity >/dev/null 2>&1
OUT="$(run_access "${BOX}" forget --profile temp-identity 2>&1)"
if printf '%s' "${OUT}" | grep -q 'secret field(s) deleted from the store: 1'; then
  ok "forget deletes the stored secret"
else
  bad "forget deletes the stored secret" "${OUT}"
fi
if printf '%s' "${OUT}" | grep -q 'project binding(s) cleared: 1'; then
  ok "forget clears bindings that referenced the identity"
else
  bad "forget clears bindings that referenced the identity" "${OUT}"
fi
if [ -f "${BOX}/home/.config/agent-skills/secrets/temp-identity.json" ]; then
  bad "forget removes the fallback secret file"
else
  ok "forget removes the fallback secret file"
fi
if printf '%s' "${OUT}" | grep -q "${CANARY}"; then
  bad "forget never prints the secret it removed"
else
  ok "forget never prints the secret it removed"
fi

# ------------------------------------------------------------------------------
printf '\n'
if [ "${FAIL}" -eq 0 ]; then
  printf 'ok: access-resolution tests passed (%s assertions)\n' "${PASS}"
  exit 0
fi
printf 'FAIL: %s of %s assertions failed:%s\n' \
  "${FAIL}" "$((PASS + FAIL))" "${FAILED_CASES}" >&2
exit 1
