#!/usr/bin/env bash
# Point every supported agent host on this machine at the active release.
#
# Called by the install transaction (lib/asrelease/transaction.py) after an
# activation and after a rollback. It is a thin entry point: all the logic, and
# in particular every predicate that decides whether a file in a user's own
# skills directory may be touched, lives in lib/install.sh.
#
# Reads these from the environment, because the CLI is the only place that
# parses flags:
#   AGENT_SKILLS_HOME    install root
#   AS_OPT_HOSTS         comma-separated host ids, empty means auto-detect
#   AS_OPT_ALL_HOSTS     "true" registers every linkable host
#   AS_OPT_NO_PATH       "true" skips linking the launcher onto PATH
#
# Writes two machine-readable result lines on stdout:
#   AS_RESULT_HOSTS=<space-separated ids>
#   AS_RESULT_CLI_LINK=<absolute path or empty>

set -uo pipefail

AS_SELF_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
AS_LIB_DIR="$(cd -P "${AS_SELF_DIR}/../lib" >/dev/null 2>&1 && pwd)"
export AS_LIB_DIR

# shellcheck source=lib/runtime.sh
. "${AS_LIB_DIR}/runtime.sh"
# shellcheck source=lib/install.sh
. "${AS_LIB_DIR}/install.sh"

as_reconcile_hosts
