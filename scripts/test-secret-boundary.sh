#!/usr/bin/env bash
# Secret boundary verification.
#
# The boundary this suite defends is:
#
#     credential store / environment -> authorized process -> remote system
#
# and specifically NOT:
#
#     credential -> stdout/stderr -> agent context -> conversation
#
# It exists because the second path was taken. A script printed two database
# passwords into a chat transcript. Once a value reaches model context it is in
# the transcript, in any summary of it, and in whatever the agent writes next;
# there is no recall.
#
# So redaction is defence in depth, not the only control. Skills route database
# access through the Access Resolver and never inline a credential. This suite
# asserts what survives when that discipline fails anyway: a credential must not
# reach durable memory, telemetry, a knowledge base, an artifact record, or
# stdout, through any normal execution path.
#
# Two properties are asserted together throughout, because either alone is
# useless:
#
#   1. the secret VALUE is gone;
#   2. enough SHAPE remains to debug the failure — `password=[redacted]` still
#      names which setting was wrong. A scrubber that emits an opaque hash has
#      moved the problem to the on-call engineer.
#
# The mutation probes remove one pattern each and assert the matching case then
# leaks. A redaction test that passes against a build with the pattern deleted
# is asserting nothing.
#
# Usage:
#   bash scripts/test-secret-boundary.sh
#
# Exit 0 when every check passes, 1 otherwise.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 2
PYTHON3="${PYTHON3:-python3}"
REDACT="${REPO}/scripts/redact.py"
BB="${REPO}/scripts/blackboard.py"
PM="${REPO}/scripts/project-memory.py"
KB="${REPO}/scripts/knowledge.py"
TM="${REPO}/scripts/telemetry.py"

PASS=0
FAIL=0
BOX="$(mktemp -d)"
cleanup() { rm -rf "$BOX" 2>/dev/null; }
trap cleanup EXIT

ok() { PASS=$((PASS + 1)); printf '  ok    %s\n' "$1"; }
bad() {
  FAIL=$((FAIL + 1))
  printf '  FAIL  %s\n' "$1" >&2
  [ -n "${2:-}" ] && printf '        %s\n' "$2" >&2
  return 0
}
sec() { printf '\n== %s ==\n' "$1"; }

contains() {
  case "$1" in
    *"$2"*) return 0 ;;
    *) return 1 ;;
  esac
}

# ---------------------------------------------------------------------------
# Fixtures are GENERATED, never committed.
#
# A contiguous secret-shaped literal in a tracked file trips every scanner that
# reads this repository — including this project's own — and a scanner cannot
# know that a secret is fake. Generating them per run also means a copied
# transcript of a failing assertion carries nothing reusable.
#
# Two lengths, on purpose:
#   SHORT is under the high-entropy threshold, so a case using it can only pass
#         because the pattern for its SHAPE fired. That is what makes the
#         `password: <value>` and `-p<value>` cases meaningful.
#   LONG  is long and mixed enough to exercise the entropy backstop.
# ---------------------------------------------------------------------------
SHORT="$("$PYTHON3" -c "import secrets; print('Pw' + secrets.token_hex(5))")"
LONG="$("$PYTHON3" -c "import secrets; print('Tok' + secrets.token_hex(20))")"

CACHE="$BOX/cache"
mkdir -p "$CACHE"

printf 'secret boundary\n'

# ---------------------------------------------------------------------------
sec "The redact filter removes each credential shape"
# ---------------------------------------------------------------------------
# Each case is a shape a database or API workflow actually emits. The names come
# from the tools that print them, not from a generic list.

# `filter_case LABEL TEXT` — pipe TEXT through the filter, assert no value survives.
filter_case() {
  local label="$1" text="$2" out
  out="$(printf '%s\n' "$text" | "$PYTHON3" "$REDACT" 2>&1)"
  if contains "$out" "$SHORT" || contains "$out" "$LONG"; then
    bad "$label" "value survived: $out"
  else
    ok "$label"
  fi
}

filter_case "connection URL with an inline password" \
  "postgresql://svc:${SHORT}@db.internal:5432/payments"
filter_case "PGPASSWORD in the environment prefix" \
  "PGPASSWORD=${SHORT} psql -h db.internal -U svc -c 'select 1'"
filter_case "MYSQL_PWD in the environment prefix" \
  "MYSQL_PWD=${SHORT} mysql -u svc payments"
filter_case "a DB_PASS style environment variable" \
  "export DB_PASS=${SHORT}"
filter_case "mysql attached -p flag" \
  "mysql -u root -p${SHORT} payments"
filter_case "libpq keyword connection string" \
  "psql \"host=db.internal user=svc password=${SHORT}\""
filter_case "JDBC URL with a password parameter" \
  "jdbc:postgresql://db.internal/payments?user=svc&password=${SHORT}"
filter_case "JSON body with a quoted password" \
  "{\"user\": \"svc\", \"password\": \"${SHORT}\"}"
filter_case "JSON body with a prefixed key name" \
  "{\"db_password\":\"${SHORT}\",\"host\":\"db.internal\"}"
filter_case "YAML style password with a colon" \
  "password: ${SHORT}"
filter_case "a bearer token in an Authorization header" \
  "curl -H 'Authorization: Bearer ${LONG}' https://api.internal/v1/payments"
# SHORT on purpose: it is below the entropy backstop, so this can only pass
# because the prose pattern fired.
filter_case "a generated password named in prose" \
  "connection failed using password ${SHORT} against db.internal"
filter_case "a --password long flag" \
  "pg_dump --password=${SHORT} --host db.internal payments"
filter_case "a client secret" \
  "client_secret=${SHORT}"

# ---------------------------------------------------------------------------
sec "Diagnostics survive redaction"
# ---------------------------------------------------------------------------
# A failure has to stay debuggable. These assert the shape that tells an
# engineer WHICH setting was wrong is still there after the value is gone.

FILTERED="$(printf 'PGPASSWORD=%s psql -h db.internal -U svc\n' "$SHORT" | "$PYTHON3" "$REDACT")"
if contains "$FILTERED" "PGPASSWORD=" && contains "$FILTERED" "db.internal" \
   && contains "$FILTERED" "redacted"; then
  ok "the variable name, the host, and a redaction marker all survive"
else
  bad "the variable name, the host, and a redaction marker all survive" "$FILTERED"
fi

FILTERED="$(printf 'postgresql://svc:%s@db.internal:5432/payments\n' "$SHORT" | "$PYTHON3" "$REDACT")"
if contains "$FILTERED" "postgresql://svc:" && contains "$FILTERED" "@db.internal:5432/payments"; then
  ok "a connection URL keeps its scheme, user, host, port, and database"
else
  bad "a connection URL keeps its scheme, user, host, port, and database" "$FILTERED"
fi

UNTOUCHED="$(printf 'password rotation is due next Tuesday\n' | "$PYTHON3" "$REDACT")"
if contains "$UNTOUCHED" "rotation is due next Tuesday"; then
  ok "ordinary prose mentioning passwords is not mangled"
else
  bad "ordinary prose mentioning passwords is not mangled" "$UNTOUCHED"
fi

UNTOUCHED="$(printf 'git clone https://github.com/example-org/example-api.git\n' | "$PYTHON3" "$REDACT")"
if contains "$UNTOUCHED" "github.com/example-org/example-api.git"; then
  ok "an ordinary URL is left alone"
else
  bad "an ordinary URL is left alone" "$UNTOUCHED"
fi

UNTOUCHED="$(printf 'the password field is required\n' | "$PYTHON3" "$REDACT")"
if contains "$UNTOUCHED" "field is required"; then
  ok "a sentence about a password field keeps its words"
else
  bad "a sentence about a password field keeps its words" "$UNTOUCHED"
fi

# ---------------------------------------------------------------------------
sec "The --check mode reports rather than transforms"
# ---------------------------------------------------------------------------
# This is the mode a pre-flight or a CI step uses to fail a build.

printf 'PGPASSWORD=%s psql\n' "$SHORT" | "$PYTHON3" "$REDACT" --check >/dev/null 2>&1
if [ $? -ne 0 ]; then
  ok "--check exits non-zero when something was redacted"
else
  bad "--check exits non-zero when something was redacted"
fi

printf 'select count(*) from payments;\n' | "$PYTHON3" "$REDACT" --check >/dev/null 2>&1
if [ $? -eq 0 ]; then
  ok "--check exits zero on clean input"
else
  bad "--check exits zero on clean input"
fi

CHECK_OUT="$(printf 'PGPASSWORD=%s psql\n' "$SHORT" | "$PYTHON3" "$REDACT" --check 2>&1)"
if ! contains "$CHECK_OUT" "$SHORT"; then
  ok "--check never prints the value it found"
else
  bad "--check never prints the value it found" "$CHECK_OUT"
fi

# ---------------------------------------------------------------------------
sec "A child process cannot leak through a pipe"
# ---------------------------------------------------------------------------
# The reported incident was a script printing passwords. Both streams count: a
# tool that writes its connection string to stderr on failure is the common case.

cat > "$BOX/leaky.sh" <<EOF
#!/usr/bin/env bash
echo "connecting: postgresql://svc:${SHORT}@db.internal/payments"
echo "PGPASSWORD=${SHORT} was exported" >&2
exit 0
EOF
chmod +x "$BOX/leaky.sh"

COMBINED="$(bash "$BOX/leaky.sh" 2>&1 | "$PYTHON3" "$REDACT")"
if ! contains "$COMBINED" "$SHORT"; then
  ok "stdout and stderr of a child process are both redacted through the filter"
else
  bad "stdout and stderr of a child process are both redacted through the filter" "$COMBINED"
fi
if contains "$COMBINED" "db.internal"; then
  ok "the child process's diagnostic context survives the filter"
else
  bad "the child process's diagnostic context survives the filter" "$COMBINED"
fi

# ---------------------------------------------------------------------------
sec "Durable writes redact before they land"
# ---------------------------------------------------------------------------
# Redaction at the filter is opt-in and an agent can forget. These paths are
# where a forgotten secret comes to rest and gets read back into the NEXT
# agent's context, so they redact on write whether or not anyone remembered.

"$PYTHON3" "$BB" --cache-root "$CACHE" init --project demo proj-900 >/dev/null 2>&1
"$PYTHON3" "$BB" --cache-root "$CACHE" append proj-900 --section facts \
  --by issue-investigator --text "connected with postgresql://svc:${SHORT}@db.internal/payments" \
  >/dev/null 2>&1
"$PYTHON3" "$BB" --cache-root "$CACHE" artifact proj-900 --by issue-investigator \
  --path "https://reports.internal/r/1?sig=${LONG}" --kind report \
  --note "PGPASSWORD=${SHORT} used" >/dev/null 2>&1
"$PYTHON3" "$BB" --cache-root "$CACHE" progress proj-900 --by issue-investigator \
  --kind query --note "ran psql with password ${LONG}" >/dev/null 2>&1
"$PYTHON3" "$BB" --cache-root "$CACHE" handoff proj-900 --from issue-investigator \
  --to software-engineer --reason "creds were DB_PASS=${SHORT}" >/dev/null 2>&1

BB_FILE="$CACHE/proj-900/blackboard.json"
if [ -f "$BB_FILE" ] && ! grep -qF "$SHORT" "$BB_FILE" && ! grep -qF "$LONG" "$BB_FILE"; then
  ok "no blackboard write path retains a credential value"
else
  bad "no blackboard write path retains a credential value" "see $BB_FILE"
fi
if grep -q "db.internal" "$BB_FILE" 2>/dev/null; then
  ok "the blackboard keeps the surrounding facts"
else
  bad "the blackboard keeps the surrounding facts"
fi

"$PYTHON3" "$PM" --cache-root "$CACHE" init demo >/dev/null 2>&1
"$PYTHON3" "$PM" --cache-root "$CACHE" note demo --section "Common gotchas" \
  --text "staging needs PGPASSWORD=${SHORT} exported" >/dev/null 2>&1
if ! grep -rqF "$SHORT" "$CACHE/_projects" 2>/dev/null; then
  ok "project memory does not retain a credential value"
else
  bad "project memory does not retain a credential value"
fi

"$PYTHON3" "$TM" --cache-root "$CACHE" emit demo completed \
  --field "skill=issue-investigator" \
  --field "note=used password ${LONG}" >/dev/null 2>&1
if ! grep -rqF "$LONG" "$CACHE/_projects" 2>/dev/null; then
  ok "telemetry does not retain a credential value"
else
  bad "telemetry does not retain a credential value"
fi

# The committed knowledge base is the worst case: it lands in a git repository
# and survives a fresh clone, so a secret written here is published.
KBREPO="$BOX/kbrepo"
mkdir -p "$KBREPO"
git -C "$KBREPO" init -q >/dev/null 2>&1
git -C "$KBREPO" config user.email t@example.com >/dev/null 2>&1
git -C "$KBREPO" config user.name test >/dev/null 2>&1
(
  cd "$KBREPO" || exit 0
  "$PYTHON3" "$KB" init >/dev/null 2>&1
  "$PYTHON3" "$KB" note --section Gotchas \
    --text "the staging DB uses password ${LONG}" >/dev/null 2>&1
)
if ! grep -rqF "$LONG" "$KBREPO" 2>/dev/null; then
  ok "the committed knowledge base does not retain a credential value"
else
  bad "the committed knowledge base does not retain a credential value"
fi

# ---------------------------------------------------------------------------
sec "Mutation probes"
# ---------------------------------------------------------------------------
# Each probe deletes one pattern from a sandboxed copy and asserts the case it
# covers then leaks. Without this, a redaction suite passes on patterns that
# never fire.

PROBE_DIR="$BOX/probe"
mkdir -p "$PROBE_DIR"

# `probe LABEL ANCHOR TEXT` — delete the `(pattern, replacement)` tuple whose
# source contains ANCHOR, then assert TEXT leaks through the weakened build.
probe() {
  local label="$1" anchor="$2" text="$3" out
  cp "$REPO/scripts/guard_audit.py" "$PROBE_DIR/guard_audit.py"
  cp "$REPO/scripts/redact.py" "$PROBE_DIR/redact.py"
  "$PYTHON3" - "$PROBE_DIR/guard_audit.py" "$anchor" <<'PY'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
anchor = sys.argv[2]
text = path.read_text(encoding="utf-8")
start = text.find(anchor)
if start == -1:
    sys.exit(3)
# The anchor comment sits ABOVE the tuple it names, so the opening paren is the
# next one forward. Searching backwards finds the previous pattern and removes
# the wrong thing, which reads as "the guard held" when nothing was tested.
open_at = text.find("    (\n", start)
if open_at == -1:
    sys.exit(3)
depth = 0
index = open_at + 4
while index < len(text):
    if text[index] == "(":
        depth += 1
    elif text[index] == ")":
        depth -= 1
        if depth == 0:
            break
    index += 1
end = text.find("\n", index) + 1
path.write_text(text[:open_at] + text[end:], encoding="utf-8")
PY
  if [ $? -ne 0 ]; then
    bad "$label" "probe could not remove the pattern (anchor not found: $anchor)"
    return 0
  fi
  out="$(printf '%s\n' "$text" | "$PYTHON3" "$PROBE_DIR/redact.py" 2>&1)"
  if contains "$out" "$SHORT" || contains "$out" "$LONG"; then
    ok "$label"
  else
    bad "$label" "the weakened build still redacted it, so the pattern is untested"
  fi
}

probe "probe: without the URL-credential pattern a connection URL leaks" \
  "scheme://user:secret@host form" \
  "postgresql://svc:${SHORT}@db.internal:5432/payments"

probe "probe: without the structured-key pattern a JSON password leaks" \
  "PROBE_ANCHOR_JSON_CREDENTIAL_KEY" \
  "{\"password\": \"${SHORT}\"}"

probe "probe: without the assignment pattern PGPASSWORD leaks" \
  "PROBE_ANCHOR_CREDENTIAL_ASSIGNMENT" \
  "PGPASSWORD=${SHORT} psql -h db.internal"

probe "probe: without the attached-flag pattern mysql -p leaks" \
  "PROBE_ANCHOR_ATTACHED_PASSWORD_FLAG" \
  "mysql -u root -p${SHORT} payments"

# ---------------------------------------------------------------------------
printf '\n== summary ==\n'
printf '  passed: %d\n' "$PASS"
printf '  failed: %d\n' "$FAIL"
if [ "$FAIL" -ne 0 ]; then
  printf '\nSECRET_BOUNDARY: FAIL\n'
  exit 1
fi
printf '\nSECRET_BOUNDARY: PASS\n'
exit 0
