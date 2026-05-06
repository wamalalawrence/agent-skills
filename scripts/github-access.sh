#!/usr/bin/env bash
# github-access.sh — verify the agent can actually reach GitHub before declaring
# "no GitHub access". Walks the documented ladder so an agent does not give up
# at the first 401.
#
# Ladder (each step's exit short-circuits when it succeeds):
#   1. `gh auth status` — does the local gh CLI have any account at all?
#   2. List logged-in accounts (gh exposes one account per host). When more
#      than one account is configured for github.com, surface them so the
#      caller can call `gh auth switch -h github.com -u <login>` instead of
#      assuming the active one is the right one for the target org/repo.
#   3. Probe the target repo with `gh repo view <owner>/<repo>` — this
#      catches the "active account has no access to this org" case the user
#      reported.
#   4. Fall back to git's own HTTPS path — `git ls-remote https://...` — to
#      detect credential-helper / netrc auth that gh does not see.
#   5. Fall back to SSH — `git ls-remote git@github.com:<owner>/<repo>.git`.
#
# Exit codes:
#   0  at least one path proved access to the target
#   1  no path worked; the script printed the next-step suggestion
#   2  required input missing (no repo passed and no $GIT_TARGET_REPO)
#   3  `gh` CLI is not installed and no other path worked
#
# Output is intentionally agent-friendly: short, machine-greppable lines like
# `step1: ok`, `step3: 404`, `suggest: gh auth switch -h github.com -u alice`.
# No tokens are printed.

set -u

TARGET_REPO="${1:-${GIT_TARGET_REPO:-}}"
if [[ -z "${TARGET_REPO}" ]]; then
  echo "FAIL no target repo. Pass owner/repo or set GIT_TARGET_REPO." >&2
  echo "usage: github-access.sh <owner>/<repo>" >&2
  exit 2
fi

OWNER="${TARGET_REPO%%/*}"
NAME="${TARGET_REPO##*/}"

have_gh="false"
if command -v gh >/dev/null 2>&1; then
  have_gh="true"
fi

# Step 1 — gh auth status
if [[ "${have_gh}" == "true" ]]; then
  if gh auth status >/tmp/gh-auth-status.$$ 2>&1; then
    echo "step1: ok"
  else
    echo "step1: not-logged-in"
  fi
  # Step 2 — enumerate accounts on github.com
  ACTIVE_USER="$(gh api user -q .login 2>/dev/null || true)"
  if [[ -n "${ACTIVE_USER}" ]]; then
    echo "step2: active=${ACTIVE_USER}"
  fi
  # gh >= 2.40 lists multiple accounts in `gh auth status`. We grep them out.
  ALT_USERS="$(grep -E 'Logged in to github\.com account' /tmp/gh-auth-status.$$ 2>/dev/null \
    | sed -E 's/.*account ([^ ]+).*/\1/' \
    | grep -v -F -x "${ACTIVE_USER}" \
    | tr '\n' ' ')"
  if [[ -n "${ALT_USERS}" ]]; then
    echo "step2: other-accounts=${ALT_USERS}"
  fi
  rm -f /tmp/gh-auth-status.$$

  # Step 3 — actually attempt the target repo
  if gh repo view "${OWNER}/${NAME}" --json name >/dev/null 2>&1; then
    echo "step3: ok"
    echo "result: gh-cli"
    exit 0
  fi
  echo "step3: gh repo view failed"
  if [[ -n "${ALT_USERS}" ]]; then
    SUGGEST_USER="$(echo "${ALT_USERS}" | awk '{print $1}')"
    echo "suggest: gh auth switch -h github.com -u ${SUGGEST_USER}"
    echo "suggest: re-run github-access.sh ${OWNER}/${NAME} after switching"
  else
    echo "suggest: gh auth login -h github.com (the active account cannot see ${OWNER}/${NAME})"
  fi
fi

# Step 4 — HTTPS via git directly (uses credential helpers / netrc / token)
if git ls-remote "https://github.com/${OWNER}/${NAME}.git" >/dev/null 2>&1; then
  echo "step4: ok"
  echo "result: git-https"
  exit 0
fi
echo "step4: https failed"

# Step 5 — SSH
if git ls-remote "git@github.com:${OWNER}/${NAME}.git" >/dev/null 2>&1; then
  echo "step5: ok"
  echo "result: git-ssh"
  exit 0
fi
echo "step5: ssh failed"

if [[ "${have_gh}" != "true" ]]; then
  echo "FAIL gh CLI not installed and HTTPS/SSH paths also failed." >&2
  echo "suggest: install gh (https://cli.github.com/) or fix git credentials." >&2
  exit 3
fi

echo "FAIL all access paths exhausted for ${OWNER}/${NAME}." >&2
echo "suggest: confirm the repo name and that one of your GitHub accounts has access." >&2
exit 1
