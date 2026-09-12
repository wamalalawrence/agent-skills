#!/usr/bin/env bash
# Audit exactly what the npm bootstrap package would publish.
#
# A published npm tarball is public permanently and cannot be recalled, so the
# question "what is in it" has to be answered before every publish rather than
# after the first one. This inspects the packed tarball itself, not the file
# list in package.json, because those two disagree the moment a glob is wrong.
#
# It fails the release if the package contains:
#   * product content — skills, docs, evals, hooks. The product arrives from the
#     release source; putting it here would publish it irrevocably, and would
#     defeat the point of a private source.
#   * anything credential-shaped, or a developer's absolute home path.
#   * an npm lifecycle script. Nothing may run on `npm install`; installation
#     happens only when a human types a command.
#
# It also fails if the vendored engine is not byte-identical to the
# repository's, because two copies of an installer is exactly the outcome
# v0.43.0 exists to prevent.
#
# Usage: bash scripts/audit-npm-package.sh [path/to/tarball]

set -euo pipefail

REPO_ROOT="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." >/dev/null 2>&1 && pwd)"
cd "${REPO_ROOT}"

TARBALL="${1:-}"
if [ -z "${TARBALL}" ]; then
  bash scripts/build-npm-bootstrap.sh --pack >/dev/null
  TARBALL="$(ls -1t npm/*.tgz 2>/dev/null | head -1)"
fi
[ -n "${TARBALL}" ] && [ -f "${TARBALL}" ] \
  || { echo "FAIL: no packed tarball to audit" >&2; exit 1; }

FAILURES=0
fail() { printf 'FAIL  %s\n' "$1" >&2; FAILURES=$((FAILURES + 1)); }
pass() { printf 'ok    %s\n' "$1"; }

printf 'Auditing %s\n\n' "${TARBALL}"
LISTING="$(tar -tzf "${TARBALL}")"
printf '%s\n\n' "${LISTING}"

if printf '%s\n' "${LISTING}" | grep -qE 'package/(skills|docs|evals|eval-runs|hooks)/'; then
  fail "the package carries product content (skills, docs, evals, or hooks)"
else
  pass "no product content"
fi

if printf '%s\n' "${LISTING}" | grep -qE '(^|/)(\.env|\.netrc|\.npmrc|id_rsa|.*\.pem|.*\.key|credentials.*)$'; then
  fail "the package carries a credential-shaped file"
else
  pass "no credential-shaped file"
fi

if printf '%s\n' "${LISTING}" | grep -qE 'package/(\.git|\.github|\.venv|node_modules)/'; then
  fail "the package carries repository internals"
else
  pass "no repository internals"
fi

if printf '%s\n' "${LISTING}" | grep -q 'package/vendor/install.py'; then
  pass "the installation engine is present"
else
  fail "the installation engine is missing; the package would not work"
fi

# The verifier and the trust bundle are the gate a signed release passes
# before anything opens it. A package that ships without them cannot verify a
# release at all, which is a worse outcome than failing to publish.
for required in package/lib/verify.js package/lib/trust-bundle.json; do
  if printf '%s\n' "${LISTING}" | grep -q "${required}\$"; then
    pass "${required#package/} is present"
  else
    fail "${required#package/} is missing; a signed release could not be verified"
  fi
done

# Absolute developer paths inside the shipped files. A packed tarball that
# names someone's home directory both leaks and breaks.
EXTRACT="$(mktemp -d)"
trap 'rm -rf "${EXTRACT}"' EXIT
tar -xzf "${TARBALL}" -C "${EXTRACT}"
if grep -rIlE '/(Users|home)/[a-z0-9_.-]+/' "${EXTRACT}/package" >/dev/null 2>&1; then
  fail "a shipped file contains an absolute developer home path"
  grep -rIlE '/(Users|home)/[a-z0-9_.-]+/' "${EXTRACT}/package" >&2 || true
else
  pass "no absolute developer paths"
fi
if grep -rIqE 'gh[pousr]_[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|BEGIN [A-Z ]*PRIVATE KEY' \
  "${EXTRACT}/package" 2>/dev/null; then
  fail "a shipped file contains a secret-shaped string"
else
  pass "no secret-shaped strings"
fi

# `set -e` would abort on a non-zero exit here, so the check is the condition of
# an `if` rather than a bare call followed by `$?`.
if python3 - "${REPO_ROOT}" <<'PYEOF'
import json
import os
import sys

root = sys.argv[1]
with open(os.path.join(root, "npm", "package.json"), encoding="utf-8") as handle:
    data = json.load(handle)
with open(os.path.join(root, "VERSION"), encoding="utf-8") as handle:
    version = handle.read().strip()

problems = []
forbidden = {"preinstall", "install", "postinstall", "prepare", "prepublish"}
present = forbidden & set(data.get("scripts", {}))
if present:
    problems.append("npm lifecycle scripts present: %s" % sorted(present))
if data.get("version") != version:
    problems.append("package.json %s does not match VERSION %s" % (data.get("version"), version))
if data.get("publishConfig", {}).get("access") != "public":
    problems.append("publishConfig.access is not 'public'")

for line in problems:
    sys.stderr.write("FAIL  %s\n" % line)
sys.exit(1 if problems else 0)
PYEOF
then
  pass "no npm lifecycle scripts; package version matches VERSION"
else
  FAILURES=$((FAILURES + 1))
fi

DRIFT=0
diff -q scripts/install.py npm/vendor/install.py >/dev/null || DRIFT=1
for file in lib/asrelease/*.py; do
  diff -q "${file}" "npm/vendor/asrelease/$(basename "${file}")" >/dev/null || DRIFT=1
done
for file in lib/asrelease/providers/*.py; do
  diff -q "${file}" "npm/vendor/asrelease/providers/$(basename "${file}")" >/dev/null || DRIFT=1
done
if [ "${DRIFT}" -eq 0 ]; then
  pass "the vendored engine is byte-identical to the repository's"
else
  fail "the vendored engine has drifted from the repository's"
fi

SIZE="$(printf '%s\n' "${LISTING}" | grep -c .)"
printf '\n%s file(s) in the package.\n' "${SIZE}"
if [ "${FAILURES}" -gt 0 ]; then
  printf '%s package-content failure(s). Do not publish.\n' "${FAILURES}" >&2
  exit 1
fi
printf 'Package content audit passed.\n'
