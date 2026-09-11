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
OM="${REPO}/scripts/org-memory.py"
OR="${REPO}/scripts/outcome-recorder.py"

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

# Line numbers must be the ORIGINAL file's. Some patterns span lines and
# collapse them — a PEM private key block becomes one token — so a pairwise
# comparison of the before and after line lists silently misreports every line
# after the first collapse. Sending someone hunting for a credential to the
# wrong line is worse than telling them nothing.
# The PEM markers are assembled rather than written out, for the same reason the
# credentials are generated: a contiguous private-key header in a tracked file
# trips every scanner that reads this repository, including this project's own
# pre-commit hook, and no scanner can tell a fixture from the real thing.
PEM_LABEL="PRIV""ATE KEY"
{
  printf 'line one is clean\n'
  printf -- '-----BEGIN RSA %s-----\nAAAA\nBBBB\n-----END RSA %s-----\n' \
    "$PEM_LABEL" "$PEM_LABEL"
  printf 'trailing line with PGPASSWORD=%s here\n' "$SHORT"
} > "$BOX/multiline.txt"
CHECK_OUT="$("$PYTHON3" "$REDACT" --check "$BOX/multiline.txt" 2>&1)"
if contains "$CHECK_OUT" "6"; then
  ok "--check reports the original file's line numbers across a collapsing block"
else
  bad "--check reports the original file's line numbers across a collapsing block" \
      "the trailing credential is on line 6; got: $CHECK_OUT"
fi
if ! contains "$CHECK_OUT" "$SHORT"; then
  ok "--check still prints no value when reporting a multi-line file"
else
  bad "--check still prints no value when reporting a multi-line file" "$CHECK_OUT"
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
# The lesson's evidence field was merged and stored verbatim while trigger and
# action were redacted, so a token-shaped locator reached the committed file.
# Every field now passes through one boundary in `Lesson.write`.
(
  cd "$KBREPO" || exit 0
  "$PYTHON3" "$KB" lesson add --id evidence-probe --trigger "before the deploy" \
    --action "export the socket path" --domain build-runtime \
    --evidence "run 12: PGPASSWORD=${SHORT} was exported" \
    --evidence "api_key=${LONG}" >/dev/null 2>&1
  "$PYTHON3" "$KB" lesson confirm evidence-probe \
    --evidence "run 13 with password: \"${SHORT}\"" >/dev/null 2>&1
  "$PYTHON3" "$KB" lesson contradict evidence-probe \
    --evidence "run 14 token=${LONG}" >/dev/null 2>&1
)
LESSON_FILE="$KBREPO/.agent-skills/knowledge/lessons/evidence-probe.md"
if [ -f "$LESSON_FILE" ] && ! grep -qF "$SHORT" "$LESSON_FILE" && ! grep -qF "$LONG" "$LESSON_FILE"; then
  ok "lesson evidence — add, confirm, and contradict — does not retain a credential value"
else
  bad "lesson evidence — add, confirm, and contradict — does not retain a credential value" \
      "see $LESSON_FILE"
fi
if grep -q "run 12" "$LESSON_FILE" 2>/dev/null && grep -q "run 14" "$LESSON_FILE" 2>/dev/null; then
  ok "the evidence locators survive redaction"
else
  bad "the evidence locators survive redaction"
fi
# Org memory is the widest-reaching tier of the four: `start-task` prints it into
# every future task in every project, so a secret here is re-read indefinitely
# and across project boundaries. It was the one durable path with no redaction.
"$PYTHON3" "$OM" --cache-root "$CACHE" init >/dev/null 2>&1
"$PYTHON3" "$OM" --cache-root "$CACHE" note --section "Common gotchas" \
  --text "every project's staging DB uses password: \"${SHORT}\"" >/dev/null 2>&1
"$PYTHON3" "$OM" --cache-root "$CACHE" promote --from demo --section "Org patterns" \
  --text "CI needs PGPASSWORD=${LONG} exported" >/dev/null 2>&1
if ! grep -rqF "$SHORT" "$CACHE/_org" 2>/dev/null \
   && ! grep -rqF "$LONG" "$CACHE/_org" 2>/dev/null; then
  ok "org memory does not retain a credential value"
else
  bad "org memory does not retain a credential value" "see $CACHE/_org"
fi
if grep -rq "staging DB" "$CACHE/_org" 2>/dev/null; then
  ok "org memory keeps the surrounding fact"
else
  bad "org memory keeps the surrounding fact"
fi
# `--promote-to-org` is the route by which a value travels from one project's
# notes into every project's, so it is checked on its own rather than assumed
# to inherit the guarantee above.
if [ -f "$OR" ]; then
  "$PYTHON3" "$OR" --cache-root "$CACHE" record \
    --project demo --issue proj-901 --outcome merged \
    --skills software-engineer=1.0.0 \
    --summary "shipped with db_password = '${SHORT}' in the staging config" \
    --lesson "rotate db_password = '${SHORT}' after every deploy" \
    --promote-to-org --confirmed-in 2 >/dev/null 2>&1
  if ! grep -rqF "$SHORT" "$CACHE/_org" 2>/dev/null; then
    ok "promoting an outcome to org memory does not carry a credential value"
  else
    bad "promoting an outcome to org memory does not carry a credential value" \
        "see $CACHE/_org"
  fi
fi
# A quoted value under a credential-shaped key is how a YAML file, a .env, and a
# config dump all spell it, and the unquoted rule stopped at the first quote.
for spelling in "password: \"${SHORT}\"" "db_password = '${SHORT}'" "mariadb -u root -p${SHORT}"; do
  OUT="$(printf '%s\n' "$spelling" | "$PYTHON3" "$REDACT" 2>&1)"
  if contains "$OUT" "$SHORT"; then
    bad "redaction covers: ${spelling%%[:= ]*}" "$OUT"
  else
    ok "redaction covers: $spelling"
  fi
done

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
probe "probe: without the quoted-value pattern a YAML password leaks" \
  "PROBE_ANCHOR_QUOTED_CREDENTIAL_VALUE" \
  "db_password = '${SHORT}'"

# Org memory's guarantee is that it calls redact at all — a different failure
# from a pattern that does not fire, and the one that actually shipped. This
# probe removes the call and asserts the value then lands on disk.
ORG_PROBE="$BOX/org-probe"
mkdir -p "$ORG_PROBE"
cp "$REPO/scripts/org-memory.py" "$ORG_PROBE/org-memory.py"
cp "$REPO/scripts/guard_audit.py" "$ORG_PROBE/guard_audit.py"
cp "$REPO/scripts/durable.py" "$ORG_PROBE/durable.py"
if "$PYTHON3" - "$ORG_PROBE/org-memory.py" <<'PY'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
weakened = text.replace("    text = redact(text)\n", "", 1)
if weakened == text:
    sys.exit(3)
path.write_text(weakened, encoding="utf-8")
PY
then
  ORG_CACHE="$BOX/org-probe-cache"
  "$PYTHON3" "$ORG_PROBE/org-memory.py" --cache-root "$ORG_CACHE" init >/dev/null 2>&1
  "$PYTHON3" "$ORG_PROBE/org-memory.py" --cache-root "$ORG_CACHE" note \
    --section "Common gotchas" --text "PGPASSWORD=${SHORT} is needed" >/dev/null 2>&1
  if grep -rqF "$SHORT" "$ORG_CACHE" 2>/dev/null; then
    ok "probe: without the redact call org memory retains the value"
  else
    bad "probe: without the redact call org memory retains the value" \
        "the weakened build still redacted it, so the call is untested"
  fi
else
  bad "probe: org-memory redaction call" "the redact call could not be removed"
fi

# The knowledge base redacts every input at the one point it is cleaned and
# again at the one point a lesson is serialised. Remove the redactor from the
# module and the evidence field must leak, or neither layer is being tested.
KB_PROBE="$(mktemp -d "$BOX/kbprobe.XXXX")"
cp "$REPO/scripts/knowledge.py" "$REPO/scripts/durable.py" "$REPO/scripts/guard_audit.py" "$KB_PROBE/"
"$PYTHON3" - "$KB_PROBE/knowledge.py" <<'PY'
import pathlib
import sys
path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
needle = "from guard_audit import redact\n"
if needle not in text:
    sys.exit(3)
path.write_text(text.replace(needle, "redact = lambda text: text\n", 1), encoding="utf-8")
PY
if [ $? -ne 0 ]; then
  bad "probe: knowledge-base field redaction" "the redactor import could not be replaced"
else
  KB_PROBE_REPO="$(mktemp -d "$BOX/kbproberepo.XXXX")"
  git -C "$KB_PROBE_REPO" init -q >/dev/null 2>&1
  (
    cd "$KB_PROBE_REPO" || exit 0
    "$PYTHON3" "$KB_PROBE/knowledge.py" lesson add --id leak-probe --trigger t --action a \
      --evidence "api_key=${LONG}" >/dev/null 2>&1
  )
  if grep -rqF "$LONG" "$KB_PROBE_REPO/.agent-skills" 2>/dev/null; then
    ok "probe: without the serialisation boundary the evidence field retains the value"
  else
    bad "probe: without the serialisation boundary the evidence field retains the value" \
        "the weakened build still redacted it, so the boundary is untested"
  fi
fi

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
