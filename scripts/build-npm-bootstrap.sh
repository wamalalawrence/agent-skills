#!/usr/bin/env bash
# Build the npm bootstrap package from this repository.
#
# The package is a doorway, not a copy of the product. It carries the Node
# entry point, the installation engine, and the release providers, and nothing
# else — no skills, no docs, no runtime, no credentials. That distinction is
# what lets the bootstrap be published publicly while the product source is
# private: a published npm tarball is public forever regardless of who can read
# the git repository behind it.
#
# The engine is vendored rather than reimplemented. `scripts/test-npm-bootstrap.sh`
# asserts the vendored copy is byte-identical to the repository's, so the
# package can never drift into being a second installer.
#
# Usage: bash scripts/build-npm-bootstrap.sh [--pack]

set -euo pipefail

REPO_ROOT="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." >/dev/null 2>&1 && pwd)"
PKG_DIR="${REPO_ROOT}/npm"
VENDOR="${PKG_DIR}/vendor"
PACK="false"
[ "${1:-}" = "--pack" ] && PACK="true"

VERSION="$(head -n 1 "${REPO_ROOT}/VERSION" | tr -d '[:space:]')"
[ -n "${VERSION}" ] || { echo "FAIL: cannot read VERSION" >&2; exit 1; }

echo "Building the Agent Skills npm bootstrap v${VERSION}"

rm -rf "${VENDOR}"
mkdir -p "${VENDOR}/asrelease/providers"

cp "${REPO_ROOT}/scripts/install.py" "${VENDOR}/install.py"
cp "${REPO_ROOT}"/lib/asrelease/*.py "${VENDOR}/asrelease/"
cp "${REPO_ROOT}"/lib/asrelease/providers/*.py "${VENDOR}/asrelease/providers/"
cp "${REPO_ROOT}/LICENSE" "${PKG_DIR}/LICENSE"

# The package version and the repository version are one number. A mismatch
# means someone published a bootstrap that advertises a release it was not
# built from, so this is a hard failure rather than a fix-up.
PKG_VERSION="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["version"])' "${PKG_DIR}/package.json")"
if [ "${PKG_VERSION}" != "${VERSION}" ]; then
  echo "FAIL: npm/package.json says ${PKG_VERSION}, VERSION says ${VERSION}" >&2
  echo "      update npm/package.json before building." >&2
  exit 1
fi

# Compile every vendored file so a syntax error cannot reach a published
# tarball, where it would break the very command that is supposed to fix it.
python3 -m compileall -q "${VENDOR}" >/dev/null
find "${VENDOR}" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

COUNT="$(find "${VENDOR}" -type f -name '*.py' | wc -l | tr -d ' ')"
echo "  vendored ${COUNT} engine file(s) into npm/vendor"

if [ "${PACK}" = "true" ]; then
  echo ""
  (cd "${PKG_DIR}" && npm pack --silent)
  echo ""
  echo "Packed tarball:"
  ls -1 "${PKG_DIR}"/*.tgz
fi
