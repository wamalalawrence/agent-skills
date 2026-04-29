#!/usr/bin/env bash
# Regression test for the v0.21.0 fix: ./setup.init --update must NOT blank
# the user's Jira / Confluence / Sonar credentials in the workspace .env.
#
# Background: in v0.20.0 and earlier, run_self_update hardcoded
# JIRA_MODE=no / CONFLUENCE_MODE=no / SONAR_MODE=no before falling through to
# the rerun. The rerun then wrote empty values into the marker block,
# silently wiping any credentials the user had previously configured. This
# caused issue-aware code review to report "no Jira access" on workspaces
# that had a fully-populated .env immediately before --update.
#
# This test:
#  1. Builds a throwaway clone of agent-skills with a tag.
#  2. Writes a workspace .env populated with realistic Jira+Confluence values.
#  3. Runs ./setup.init --update --branch main against that clone.
#  4. Verifies the .env still contains the original Jira/Confluence values
#     and that a user-edited line outside the marker block is preserved.
#
# Exit 0 on pass, non-zero on failure.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

mkdir -p "${TMP}/agent-skills"
cp -R "${REPO_ROOT}/." "${TMP}/agent-skills/"
cd "${TMP}/agent-skills"
rm -rf .git
git init -q -b main
git add -A 2>/dev/null
git -c user.email=t@t -c user.name=t commit -q -m "init"
git tag v0.99.0 >/dev/null
git remote add origin "${TMP}/agent-skills"
git fetch --tags origin -q 2>/dev/null

cat > "${TMP}/.env" <<EOF
USER_EDIT_OUTSIDE_BLOCK="keep-me"
# >>> agent-skills setup.init
ORG_NAME="acme"
ORG_DOMAIN="acme.example.com"
WORKSPACE_ROOT="${TMP}"
GITHUB_ORG="acme"
GITHUB_DEFAULT_BRANCH="main"
PROJECTS_JSON='[{"name":"repo-a","path":"repo-a","stack":"java","base_branch":"main"}]'
JIRA_CONFIG_FILE="\${WORKSPACE_ROOT}/.jira-config.yml"
JIRA_HOST="https://jira.acme.example.com"
JIRA_AUTH_TYPE="bearer"
JIRA_LOGIN="alice@acme.example.com"
JIRA_API_TOKEN="SECRET-TOKEN-xyz123"
JIRA_PROJECT_KEYS="ABC,KVB"
JIRA_KEY_REGEX="[A-Z][A-Z0-9_]+-[0-9]+"
CONFLUENCE_HOST="https://acme.example.com/wiki"
CONFLUENCE_LOGIN="alice@acme.example.com"
CONFLUENCE_API_TOKEN="CONF-TOKEN-abc456"
CONFLUENCE_SPACE_KEYS="ENG"
SONAR_HOST_URL=""
SONAR_TOKEN=""
ENVIRONMENTS_JSON='[]'
# <<< agent-skills setup.init
EOF
mkdir -p "${TMP}/repo-a"

WORKSPACE_ROOT="${TMP}" ./setup.init --update --branch main >/dev/null 2>&1
RC=$?
if [[ "${RC}" -ne 0 ]]; then
  echo "FAIL: setup.init --update exited ${RC}" >&2
  exit 1
fi

errors=0
expect_line() {
  local line="$1"
  if ! grep -qxF "${line}" "${TMP}/.env"; then
    echo "FAIL: expected line missing from .env: ${line}" >&2
    errors=$((errors + 1))
  fi
}

expect_line 'JIRA_HOST="https://jira.acme.example.com"'
expect_line 'JIRA_LOGIN="alice@acme.example.com"'
expect_line 'JIRA_API_TOKEN="SECRET-TOKEN-xyz123"'
expect_line 'JIRA_PROJECT_KEYS="ABC,KVB"'
expect_line 'JIRA_AUTH_TYPE="bearer"'
expect_line 'CONFLUENCE_HOST="https://acme.example.com/wiki"'
expect_line 'CONFLUENCE_LOGIN="alice@acme.example.com"'
expect_line 'CONFLUENCE_API_TOKEN="CONF-TOKEN-abc456"'
expect_line 'CONFLUENCE_SPACE_KEYS="ENG"'
expect_line 'USER_EDIT_OUTSIDE_BLOCK="keep-me"'

if [[ "${errors}" -ne 0 ]]; then
  echo "" >&2
  echo "FAIL: ${errors} expected line(s) missing from .env after --update" >&2
  echo "Resulting .env:" >&2
  sed 's/^/  /' "${TMP}/.env" >&2
  exit 1
fi

echo "ok: setup.init --update preserved Jira / Confluence credentials and user-edited lines"
