#!/bin/sh
# A stand-in for the GitHub CLI, used by test-shared-knowledge.py. It never
# contacts a network: it logs its arguments and answers from the environment.
echo "$*" >> "$FAKE_GH_LOG"
case "$1 $2" in
  "auth status")
    exit 0
    ;;
  "pr create")
    echo "https://example.com/acme/engineering-knowledge/pull/42"
    ;;
  "pr view")
    echo "${FAKE_GH_PR_STATE:-OPEN}"
    ;;
  "repo fork")
    exit 0
    ;;
  "api user")
    echo "forker"
    ;;
  "repo view")
    echo "${FAKE_GH_FORK_URL}"
    ;;
  *)
    exit 1
    ;;
esac
