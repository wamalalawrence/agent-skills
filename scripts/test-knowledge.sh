#!/usr/bin/env bash
# Memory integrity verification.
#
# The pre-1.0 architecture review probed the memory tiers with inputs the
# other suites never sent and found that the boundary between "an agent said
# so" and "this is recorded knowledge" was mostly missing:
#
#   * confidence rose on every repeated submission of the same evidence, so a
#     retried closeout manufactured a 0.9 rule from one observation;
#   * a contradiction refreshed `verified_at` and the lesson stayed in recall;
#   * decay took another step on every run past 90 days;
#   * recall preferred the OLDEST verification among equals;
#   * the character budget counted the payload but not the frame around it;
#   * the read-modify-write on a lesson ran outside its lock;
#   * a lock that timed out ran the body anyway, and a body error surfaced as
#     "generator didn't stop after throw()";
#   * a closeout recorded `completed` with no evidence artifact at all;
#   * the stop hook recorded a false "unfinished" after a normal finish;
#   * `--promote-to-org --confirmed-in 2` promoted on a number the caller typed.
#
# Every case below fails against the pre-fix code. Mutation probes at the end
# remove one guarantee each from a sandboxed copy and assert the matching case
# then fails, so no check can pass against a property the code does not have.
#
# Usage:
#   bash scripts/test-knowledge.sh
#
# Exit 0 when every check passes, 1 otherwise.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 2
PYTHON3="${PYTHON3:-python3}"
KB="${REPO}/scripts/knowledge.py"
PM="${REPO}/scripts/project-memory.py"
OM="${REPO}/scripts/org-memory.py"
OR="${REPO}/scripts/outcome-recorder.py"
BB="${REPO}/scripts/blackboard.py"
FT="${REPO}/scripts/finish-task.sh"
DOD="${REPO}/scripts/dod-check.py"

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
contains() { case "$1" in *"$2"*) return 0 ;; *) return 1 ;; esac; }

# A fresh git repository to host a knowledge base.
new_repo() {
  local dir="$BOX/repo-$1"
  mkdir -p "$dir"
  git -C "$dir" init -q >/dev/null 2>&1
  printf '%s\n' "$dir"
}
lesson_file() { printf '%s/.agent-skills/knowledge/lessons/%s.md\n' "$1" "$2"; }
field() { sed -n "s/^$2: *\"\{0,1\}\([^\"]*\)\"\{0,1\}$/\1/p" "$1" | head -1; }
set_field() {
  "$PYTHON3" - "$1" "$2" "$3" <<'PY'
import pathlib, re, sys
path, key, value = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
text = path.read_text(encoding="utf-8")
new, n = re.subn(rf'^{re.escape(key)}: .*$', f'{key}: "{value}"', text, count=1, flags=re.M)
if n == 0:
    new = text.replace("\n---\n", f'\n{key}: "{value}"\n---\n', 1)
path.write_text(new, encoding="utf-8")
PY
}

printf 'memory integrity\n'

# ---------------------------------------------------------------------------
sec "Confidence rises only on a distinct observation"
# ---------------------------------------------------------------------------
R="$(new_repo observation)"
cd "$R" || exit 2
"$PYTHON3" "$KB" lesson add --id docker-socket --trigger "before the integration profile" \
  --action "export DOCKER_HOST" --domain build-runtime --evidence TASK-1 >/dev/null 2>&1
for _ in 1 2 3 4; do
  "$PYTHON3" "$KB" lesson add --id docker-socket --trigger "before the integration profile" \
    --action "export DOCKER_HOST" --domain build-runtime --evidence TASK-1 >/dev/null 2>&1
done
F="$(lesson_file "$R" docker-socket)"
if [ "$(field "$F" confidence)" = "0.5" ] && [ "$(field "$F" confirmations)" = "1" ]; then
  ok "five submissions of the same evidence are one observation (0.5, 1 confirmation)"
else
  bad "five submissions of the same evidence are one observation" \
      "confidence=$(field "$F" confidence) confirmations=$(field "$F" confirmations)"
fi

OUT="$("$PYTHON3" "$KB" lesson add --id docker-socket --trigger "before the integration profile" \
  --action "export DOCKER_HOST" --domain build-runtime --evidence TASK-2 2>&1)"
if contains "$OUT" "reconfirmed" && [ "$(field "$F" confidence)" = "0.6" ] \
   && [ "$(field "$F" confirmations)" = "2" ]; then
  ok "new evidence is a new observation (0.6, 2 confirmations)"
else
  bad "new evidence is a new observation" "$OUT / confidence=$(field "$F" confidence)"
fi

OUT="$("$PYTHON3" "$KB" lesson add --id docker-socket --trigger "before the integration profile" \
  --action "something entirely different" --domain build-runtime --evidence TASK-3 2>&1)"
if contains "$OUT" "not reconfirmed" && [ "$(field "$F" confidence)" = "0.6" ] \
   && [ "$(field "$F" action)" = "export DOCKER_HOST" ] && ! grep -q "TASK-3" "$F"; then
  ok "a changed proposition is a conflict: nothing written, nothing reinforced"
else
  bad "a changed proposition is a conflict: nothing written, nothing reinforced" "$OUT"
fi

if "$PYTHON3" "$KB" lesson confirm docker-socket >/dev/null 2>&1; then
  bad "confirm without --evidence is refused"
else
  ok "confirm without --evidence is refused"
fi
OUT="$("$PYTHON3" "$KB" lesson confirm docker-socket --evidence TASK-2 2>&1)"
if contains "$OUT" "unchanged" && [ "$(field "$F" confidence)" = "0.6" ]; then
  ok "confirm with already-recorded evidence is idempotent"
else
  bad "confirm with already-recorded evidence is idempotent" "$OUT"
fi
"$PYTHON3" "$KB" lesson confirm docker-socket --evidence TASK-4 >/dev/null 2>&1
if [ "$(field "$F" confidence)" = "0.7" ] && [ "$(field "$F" confirmations)" = "3" ]; then
  ok "confirm with new evidence raises confidence (0.7, 3 confirmations)"
else
  bad "confirm with new evidence raises confidence" "confidence=$(field "$F" confidence)"
fi
if "$PYTHON3" "$KB" lesson add --id no-evidence --trigger t --action a >/dev/null 2>&1; then
  bad "a lesson cannot be added without evidence"
else
  ok "a lesson cannot be added without evidence"
fi

# ---------------------------------------------------------------------------
sec "A contradiction disputes a lesson instead of refreshing it"
# ---------------------------------------------------------------------------
"$PYTHON3" "$KB" lesson add --id stale-claim --trigger "before review" \
  --action "run the old linter" --evidence TASK-9 >/dev/null 2>&1
F="$(lesson_file "$R" stale-claim)"
set_field "$F" verified_at "2025-01-01"
"$PYTHON3" "$KB" lesson contradict stale-claim --evidence TASK-10 >/dev/null 2>&1
if [ "$(field "$F" verified_at)" = "2025-01-01" ]; then
  ok "contradict leaves verified_at alone"
else
  bad "contradict leaves verified_at alone" "verified_at=$(field "$F" verified_at)"
fi
if [ "$(field "$F" status)" = "disputed" ] && [ -n "$(field "$F" last_contradicted_at)" ]; then
  ok "one contradiction against one confirmation marks the lesson disputed"
else
  bad "one contradiction against one confirmation marks the lesson disputed" \
      "status=$(field "$F" status)"
fi
READ="$("$PYTHON3" "$KB" read 2>&1)"
if ! contains "$READ" "stale-claim" && contains "$READ" "disputed"; then
  ok "a disputed lesson is withheld from recall and the withholding is reported"
else
  bad "a disputed lesson is withheld from recall and the withholding is reported" "$READ"
fi
if "$PYTHON3" "$KB" lesson list 2>&1 | grep -q "\[disputed\] stale-claim"; then
  ok "lesson list still shows it, marked disputed"
else
  bad "lesson list still shows it, marked disputed"
fi
"$PYTHON3" "$KB" lesson confirm stale-claim --evidence TASK-11 >/dev/null 2>&1
if [ "$(field "$F" status)" = "active" ]; then
  ok "a further distinct confirmation outweighs the contradiction and reactivates it"
else
  bad "a further distinct confirmation outweighs the contradiction and reactivates it" \
      "status=$(field "$F" status)"
fi
if "$PYTHON3" "$KB" doctor >/dev/null 2>&1; then
  ok "doctor accepts the new fields"
else
  bad "doctor accepts the new fields" "$("$PYTHON3" "$KB" doctor 2>&1 | tail -3)"
fi

# ---------------------------------------------------------------------------
sec "Decay is idempotent within its window"
# ---------------------------------------------------------------------------
"$PYTHON3" "$KB" lesson add --id old-lesson --trigger t --action a --evidence T-1 >/dev/null 2>&1
F="$(lesson_file "$R" old-lesson)"
set_field "$F" confidence "0.8"
set_field "$F" verified_at "2025-01-01"
"$PYTHON3" "$KB" decay --apply >/dev/null 2>&1
"$PYTHON3" "$KB" decay --apply >/dev/null 2>&1
"$PYTHON3" "$KB" decay --apply >/dev/null 2>&1
if [ "$(field "$F" confidence)" = "0.7" ] && [ -n "$(field "$F" last_decay_at)" ]; then
  ok "three decay runs on one day are one decay step (0.8 -> 0.7)"
else
  bad "three decay runs on one day are one decay step" "confidence=$(field "$F" confidence)"
fi
set_field "$F" last_decay_at "2025-06-01"
"$PYTHON3" "$KB" decay --apply >/dev/null 2>&1
if [ "$(field "$F" confidence)" = "0.6" ]; then
  ok "a decay window later it decays again"
else
  bad "a decay window later it decays again" "confidence=$(field "$F" confidence)"
fi

# ---------------------------------------------------------------------------
sec "Recall orders equals by recency, most recent first"
# ---------------------------------------------------------------------------
R2="$(new_repo recency)"
cd "$R2" || exit 2
"$PYTHON3" "$KB" lesson add --id older --trigger "when building" --action "a" --evidence T >/dev/null 2>&1
"$PYTHON3" "$KB" lesson add --id newer --trigger "when building" --action "b" --evidence T >/dev/null 2>&1
set_field "$(lesson_file "$R2" older)" verified_at "2025-01-01"
set_field "$(lesson_file "$R2" newer)" verified_at "2026-01-01"
FIRST="$("$PYTHON3" "$KB" read --brief "building" 2>/dev/null | grep -o '\] [a-z]* (' | head -1)"
if contains "$FIRST" "newer"; then
  ok "the more recently verified lesson is shown first"
else
  bad "the more recently verified lesson is shown first" "first=$FIRST"
fi

# ---------------------------------------------------------------------------
sec "The budget is the rendered length, frame included"
# ---------------------------------------------------------------------------
R3="$(new_repo budget)"
cd "$R3" || exit 2
for i in $(seq 1 40); do
  "$PYTHON3" "$KB" lesson add --id "lesson-$i" --trigger "when doing thing number $i in the module" \
    --action "do the corresponding action $i carefully" --evidence "T-$i" >/dev/null 2>&1
done
for i in $(seq 1 30); do
  "$PYTHON3" "$KB" note --section Gotchas \
    --text "gotcha number $i about the build that is fairly long to say in one line" >/dev/null 2>&1
done
for budget in 400 700 1500 4000; do
  OUT="$("$PYTHON3" "$KB" read --budget-chars "$budget" 2>/dev/null)"
  if [ "${#OUT}" -le "$budget" ]; then
    ok "budget $budget: rendered ${#OUT} chars"
  else
    bad "budget $budget: rendered ${#OUT} chars" "over by $(( ${#OUT} - budget ))"
  fi
done
OUT="$("$PYTHON3" "$KB" read --budget-chars 4000 2>/dev/null)"
if contains "$OUT" "did not fit the character budget"; then
  ok "lessons that did not fit are reported"
else
  bad "lessons that did not fit are reported" "$(printf '%s' "$OUT" | tail -3)"
fi
OUT="$("$PYTHON3" "$KB" read --budget-chars 1500 2>/dev/null)"
if contains "$OUT" "project.md truncated"; then
  ok "a truncated project.md is reported with its path"
else
  bad "a truncated project.md is reported with its path" "$(printf '%s' "$OUT" | tail -3)"
fi
# Small budgets, just above the minimum, used to overrun: once every entry was
# trimmed, the withheld notice alone could exceed what was left. Sweep every
# budget from the minimum up, with and without meeting facts in the tier.
R3S="$(new_repo budget-sweep)"
cp -R "$R3/.agent-skills" "$R3S/"
SWEEP="$(cd "$R3S" && "$PYTHON3" - "$(dirname "$KB")" <<'PY'
import json, subprocess, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import knowledge
repo = Path.cwd().resolve()

def overruns():
    return [b for b in range(250, 1200) if len(knowledge.render_read(repo, "thing module", b, 0.3)[0]) > b]

before = overruns()
subprocess.run(["git", "remote", "add", "origin", "https://github.com/example/budget.git"], check=True)
facts = [{"id": "f_%016x" % i, "type": "DECISION", "status": "CONFIRMED", "review_state": "ACCEPTED" if i % 4 else "PENDING_REVIEW",
          "statement": "Decision number %d about the module thing, long enough to matter" % i, "speakers": [],
          "owner": None, "due": None, "meeting_id": "m_000000000001", "confidence": 0.8,
          "evidence": [{"segment_id": "s_000000000001", "start_ts": i, "end_ts": i + 1}],
          "source": {"kind": "meeting", "method": "captions"}, "supersedes": [], "created_at": "2026-09-21"}
         for i in range(60)]
knowledge.write_meeting_facts(repo, {"schema": knowledge.MEETING_FACTS_SCHEMA, "meeting_id": "m_000000000001",
    "title": "Budget", "date": "2026-09-21", "platform": "zoom", "scope": knowledge.repository_scope(repo),
    "source_method": "captions", "partial": False, "transcript_available": True, "facts": facts,
    "notes": [], "committed_at": "2026-09-21T00:00:00Z"})
print(json.dumps({"without": before, "with": overruns()}))
PY
)"
case "$SWEEP" in
  '{"without": [], "with": []}') ok "no budget from 250 to 1199 overruns, with or without meeting facts" ;;
  *) bad "no budget from 250 to 1199 overruns" "$SWEEP" ;;
esac
PM_CACHE="$BOX/pmcache"
"$PYTHON3" "$PM" --cache-root "$PM_CACHE" init demo >/dev/null 2>&1
for i in $(seq 1 60); do
  "$PYTHON3" "$PM" --cache-root "$PM_CACHE" note demo --section "Common gotchas" \
    --text "gotcha $i that is long enough to add up to something over the budget" >/dev/null 2>&1
done
OUT="$("$PYTHON3" "$PM" --cache-root "$PM_CACHE" read demo --budget-chars 1200 2>/dev/null)"
if [ "${#OUT}" -le 1200 ] && contains "$OUT" "truncated"; then
  ok "project memory read honours --budget-chars and says so (${#OUT} chars)"
else
  bad "project memory read honours --budget-chars and says so" "rendered ${#OUT}"
fi
"$PYTHON3" "$OM" --cache-root "$PM_CACHE" init >/dev/null 2>&1
for i in $(seq 1 40); do
  "$PYTHON3" "$OM" --cache-root "$PM_CACHE" note --section "Org patterns" \
    --text "pattern $i that is long enough to add up to something over the budget" >/dev/null 2>&1
done
OUT="$("$PYTHON3" "$OM" --cache-root "$PM_CACHE" read --budget-chars 900 2>/dev/null)"
if [ "${#OUT}" -le 900 ] && contains "$OUT" "truncated"; then
  ok "org memory read honours --budget-chars and says so (${#OUT} chars)"
else
  bad "org memory read honours --budget-chars and says so" "rendered ${#OUT}"
fi

# ---------------------------------------------------------------------------
sec "Lesson updates are serialised under the lock"
# ---------------------------------------------------------------------------
# Deterministic rather than a race: hold the lesson's lock from a helper
# process, start a confirm, and assert it neither writes nor gives up until
# the lock is released.
R4="$(new_repo locking)"
cd "$R4" || exit 2
"$PYTHON3" "$KB" lesson add --id locked-lesson --trigger t --action a --evidence T-0 >/dev/null 2>&1
F="$(lesson_file "$R4" locked-lesson)"
"$PYTHON3" - "$F.lock" 2.5 <<'PY' &
import fcntl, sys, time
handle = open(sys.argv[1], "a+")
fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
time.sleep(float(sys.argv[2]))
fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
PY
HOLDER=$!
sleep 0.4
"$PYTHON3" "$KB" lesson confirm locked-lesson --evidence T-1 >/dev/null 2>&1 &
CONFIRMER=$!
sleep 0.8
if [ "$(field "$F" confirmations)" = "1" ]; then
  ok "a confirm waits while another process holds the lesson's lock"
else
  bad "a confirm waits while another process holds the lesson's lock" \
      "confirmations=$(field "$F" confirmations) while the lock was held"
fi
wait "$HOLDER" "$CONFIRMER" 2>/dev/null
if [ "$(field "$F" confirmations)" = "2" ]; then
  ok "and lands once the lock is released"
else
  bad "and lands once the lock is released" "confirmations=$(field "$F" confirmations)"
fi

"$PYTHON3" - "$F.lock" 3 <<'PY' &
import fcntl, sys, time
handle = open(sys.argv[1], "a+")
fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
time.sleep(float(sys.argv[2]))
PY
HOLDER=$!
sleep 0.4
OUT="$(AGENT_SKILLS_LOCK_TIMEOUT_SECONDS=1 "$PYTHON3" "$KB" lesson confirm locked-lesson --evidence T-2 2>&1)"
RC=$?
wait "$HOLDER" 2>/dev/null
if [ "$RC" -ne 0 ] && contains "$OUT" "could not lock" && [ "$(field "$F" confirmations)" = "2" ]; then
  ok "a lock that times out is reported as retryable and nothing is written"
else
  bad "a lock that times out is reported as retryable and nothing is written" "rc=$RC $OUT"
fi

# ---------------------------------------------------------------------------
sec "durable: body errors propagate, corrupt state is preserved"
# ---------------------------------------------------------------------------
cd "$REPO/scripts" || exit 2
OUT="$("$PYTHON3" - "$BOX/durable-body.json" <<'PY' 2>&1
import pathlib, sys
import durable
path = pathlib.Path(sys.argv[1])
try:
    with durable.locked(path):
        raise OSError("body failure")
except OSError as exc:
    print("OSError:", exc)
except Exception as exc:
    print("WRONG:", type(exc).__name__, exc)
PY
)"
if contains "$OUT" "OSError: body failure"; then
  ok "an OSError inside the locked body reaches the caller intact"
else
  bad "an OSError inside the locked body reaches the caller intact" "$OUT"
fi
CORRUPT="$BOX/corrupt.json"
printf '{"half": ' > "$CORRUPT"
OUT="$("$PYTHON3" - "$CORRUPT" <<'PY' 2>&1
import json, pathlib, sys
import durable
path = pathlib.Path(sys.argv[1])
result = durable.update_json(path, lambda d: {**d, "written": True}, default={"seed": 1})
print(json.dumps(result))
PY
)"
if contains "$OUT" '"written": true' && ls "$BOX"/corrupt.json.corrupt-* >/dev/null 2>&1 \
   && grep -q '"half"' "$BOX"/corrupt.json.corrupt-*; then
  ok "an unreadable JSON store is moved aside, reported, and the tier continues"
else
  bad "an unreadable JSON store is moved aside, reported, and the tier continues" "$OUT"
fi
OUT="$("$PYTHON3" - "$BOX/missing/store.json" <<'PY' 2>&1
import json, pathlib, sys
import durable
result = durable.update_json(pathlib.Path(sys.argv[1]), lambda d: {**d, "n": d.get("n", 0) + 1}, default={"n": 0})
print(json.dumps(result))
PY
)"
if contains "$OUT" '"n": 1' && ! ls "$BOX/missing"/*.corrupt-* >/dev/null 2>&1; then
  ok "a missing store starts from the default without a quarantine file"
else
  bad "a missing store starts from the default without a quarantine file" "$OUT"
fi
cd "$REPO" || exit 2

# ---------------------------------------------------------------------------
sec "dod-check: evidence, not claims"
# ---------------------------------------------------------------------------
DODDIR="$BOX/dod"
mkdir -p "$DODDIR"
write_dod() {
  # name head_sha build_result build_revision waiver_authority bug_fix red_assertion
  local name="$1" head="$2" build="$3" rev="$4" authority="$5" bugfix="$6" assertion="$7"
  local waivers="[]"
  if [ -n "$authority" ]; then
    waivers="[{\"check\": \"build\", \"reason\": \"generated code\", \"authority\": \"$authority\"}]"
  fi
  local red=""
  if [ "$bugfix" = "true" ]; then
    red=",\"regression_red\": {\"result\": \"pass\", \"command\": \"pytest -k t\", \"cwd\": \".\", \"revision\": \"$head\", \"exit_code\": 0, \"assertion\": \"$assertion\"},
      \"regression_green\": {\"result\": \"pass\", \"command\": \"pytest -k t\", \"cwd\": \".\", \"revision\": \"$head\", \"exit_code\": 0}"
  fi
  cat > "$DODDIR/$name.json" <<EOF
{
  "issue_key": "PROJ-1",
  "head_sha": "$head",
  "classification": {"is_bug_fix": $bugfix, "shared_library_changed": false, "safety_applies": false},
  "checks": {
    "build": {"result": "$build", "command": "make build", "cwd": ".", "revision": "$rev", "exit_code": 0},
    "tests": {"result": "pass", "command": "make test", "cwd": ".", "revision": "$head", "exit_code": 0},
    "format": {"result": "pass", "command": "make fmt-check", "cwd": ".", "revision": "$head", "exit_code": 0},
    "lint_or_static_analysis": {"result": "not_applicable", "reason": "docs-only change"},
    "security_scan": {"result": "pass", "command": "make scan", "cwd": ".", "revision": "$head", "exit_code": 0}
    $red
  },
  "waivers": $waivers
}
EOF
}
write_dod verified abc123 pass abc123 "" false ""
if "$PYTHON3" "$DOD" "$DODDIR/verified.json" >/dev/null 2>&1; then
  ok "a complete execution record on the reviewed revision verifies"
else
  bad "a complete execution record on the reviewed revision verifies" "$("$PYTHON3" "$DOD" "$DODDIR/verified.json" 2>&1)"
fi
write_dod failed abc123 fail abc123 "" false ""
"$PYTHON3" "$DOD" "$DODDIR/failed.json" >/dev/null 2>&1; RC=$?
if [ "$RC" -eq 1 ]; then ok "a failed required check without a waiver does not verify"; else bad "a failed required check without a waiver does not verify" "rc=$RC"; fi
write_dod agentwaived abc123 fail abc123 agent false ""
"$PYTHON3" "$DOD" "$DODDIR/agentwaived.json" >/dev/null 2>&1; RC=$?
if [ "$RC" -eq 1 ]; then ok "a waiver signed by the agent is not an authorization"; else bad "a waiver signed by the agent is not an authorization" "rc=$RC"; fi
write_dod userwaived abc123 fail abc123 user false ""
if "$PYTHON3" "$DOD" "$DODDIR/userwaived.json" >/dev/null 2>&1; then
  ok "a waiver with a named authority verifies"
else
  bad "a waiver with a named authority verifies"
fi
write_dod stale abc123 pass 0ld5ha "" false ""
"$PYTHON3" "$DOD" "$DODDIR/stale.json" >/dev/null 2>&1; RC=$?
if [ "$RC" -eq 1 ]; then ok "a pass recorded on another revision is stale evidence"; else bad "a pass recorded on another revision is stale evidence" "rc=$RC"; fi
write_dod bugfix abc123 pass abc123 "" true "expected 302 to /login, got 200"
if "$PYTHON3" "$DOD" "$DODDIR/bugfix.json" >/dev/null 2>&1; then
  ok "a bug fix with RED (behavioural assertion) and GREEN verifies"
else
  bad "a bug fix with RED (behavioural assertion) and GREEN verifies" "$("$PYTHON3" "$DOD" "$DODDIR/bugfix.json" 2>&1)"
fi
write_dod bugfix-noassert abc123 pass abc123 "" true ""
"$PYTHON3" "$DOD" "$DODDIR/bugfix-noassert.json" >/dev/null 2>&1; RC=$?
if [ "$RC" -eq 1 ]; then ok "RED without the failed assertion is not RED"; else bad "RED without the failed assertion is not RED" "rc=$RC"; fi
printf '{"issue_key": "PROJ-1", "build": {"passed": true}, "scope": {"shared_library_changed": false}}\n' > "$DODDIR/legacy.json"
"$PYTHON3" "$DOD" "$DODDIR/legacy.json" >/dev/null 2>&1; RC=$?
if [ "$RC" -eq 1 ]; then ok "the pre-1.0 boolean schema is reported as unverifiable, not verified"; else bad "the pre-1.0 boolean schema is reported as unverifiable, not verified" "rc=$RC"; fi
OUT="$("$PYTHON3" "$DOD" "$DODDIR/verified.json" 2>&1)"
if ! contains "$OUT" "shared_library_changed"; then
  ok "a false classification needs no waiver"
else
  bad "a false classification needs no waiver" "$OUT"
fi

# ---------------------------------------------------------------------------
sec "finish-task: closeout is not verified delivery, and the fallback is idempotent"
# ---------------------------------------------------------------------------
CACHE="$BOX/ft-cache"
mkdir -p "$CACHE"
"$PYTHON3" "$BB" --cache-root "$CACHE" init --project demo proj-700 >/dev/null 2>&1
printf 'project=demo\nissue_key=proj-700\n' > "$CACHE/.last-task-context"
OUT="$(AGENT_SKILLS_CACHE_DIR="$CACHE" bash "$FT" demo proj-700 --skill software-engineer \
  --summary "done with no evidence" 2>&1)"
if contains "$OUT" "NOT verified" && grep -rq '"verified_delivery":"no"' "$CACHE/_projects" 2>/dev/null; then
  ok "a complete closeout with no artifact is recorded and marked not verified"
else
  bad "a complete closeout with no artifact is recorded and marked not verified" "$OUT"
fi
if grep -q "^closed=proj-700$" "$CACHE/.last-task-context"; then
  ok "a successful closeout marks the task closed"
else
  bad "a successful closeout marks the task closed" "$(cat "$CACHE/.last-task-context")"
fi
OUT="$(AGENT_SKILLS_CACHE_DIR="$CACHE" bash "$FT" --if-open --skill software-engineer \
  --status needs-context --no-cleanup --no-candidates --summary "session stopped" 2>&1)"
RC=$?
BULLETS="$(grep -c "proj-700" "$CACHE/_projects/demo/memory.md" 2>/dev/null || echo 0)"
if [ "$RC" -eq 0 ] && contains "$OUT" "already closed out" && [ "$BULLETS" -eq 1 ]; then
  ok "the stop-hook fallback after a normal finish is a no-op"
else
  bad "the stop-hook fallback after a normal finish is a no-op" "rc=$RC bullets=$BULLETS $OUT"
fi
if ! grep -q '"event":"stopped"' "$CACHE/_projects/demo/telemetry.ndjson" 2>/dev/null; then
  ok "no false stopped event was emitted"
else
  bad "no false stopped event was emitted"
fi

"$PYTHON3" "$BB" --cache-root "$CACHE" init --project demo proj-701 >/dev/null 2>&1
printf 'project=demo\nissue_key=proj-701\n' > "$CACHE/.last-task-context"
OUT="$(AGENT_SKILLS_CACHE_DIR="$CACHE" bash "$FT" --if-open --skill software-engineer \
  --status needs-context --no-cleanup --no-candidates --summary "session stopped" 2>&1)"
RC=$?
if [ "$RC" -eq 0 ] && grep -q "proj-701: needs-context" "$CACHE/_projects/demo/memory.md" \
   && [ -d "$CACHE/proj-701" ]; then
  ok "the fallback closes out a task that was never finished, preserving scratch"
else
  bad "the fallback closes out a task that was never finished, preserving scratch" "rc=$RC $OUT"
fi
if grep -rq '"closeout":"fallback"' "$CACHE/_projects/demo" 2>/dev/null; then
  ok "the fallback closeout is attributed as such in telemetry"
else
  bad "the fallback closeout is attributed as such in telemetry"
fi
rm -f "$CACHE/.last-task-context"
OUT="$(AGENT_SKILLS_CACHE_DIR="$CACHE" bash "$FT" --if-open --skill software-engineer \
  --status needs-context --no-cleanup --no-candidates --summary "session stopped" 2>&1)"
if [ $? -eq 0 ] && contains "$OUT" "no task in flight"; then
  ok "with no task identity the fallback records nothing"
else
  bad "with no task identity the fallback records nothing" "$OUT"
fi

"$PYTHON3" "$BB" --cache-root "$CACHE" init --project demo proj-702 >/dev/null 2>&1
printf 'project=demo\nissue_key=proj-702\n' > "$CACHE/.last-task-context"
cp "$DODDIR/verified.json" "$CACHE/proj-702/definition-of-done.json"
OUT="$(AGENT_SKILLS_CACHE_DIR="$CACHE" bash "$FT" demo proj-702 --skill software-engineer \
  --status pr-opened --summary "verified" 2>&1)"
if contains "$OUT" "definition-of-done: verified" && grep -rq '"verified_delivery":"yes"' "$CACHE/_projects" 2>/dev/null; then
  ok "a closeout with a verifiable definition of done is recorded as verified"
else
  bad "a closeout with a verifiable definition of done is recorded as verified" "$OUT"
fi

# ---------------------------------------------------------------------------
sec "Promotion counts are derived from project memories on disk"
# ---------------------------------------------------------------------------
ORC="$BOX/or-cache"
"$PYTHON3" "$PM" --cache-root "$ORC" init alpha >/dev/null 2>&1
"$PYTHON3" "$PM" --cache-root "$ORC" init beta >/dev/null 2>&1
if "$PYTHON3" "$OR" --cache-root "$ORC" record --project alpha --issue A-1 --outcome reverted \
     --skills software-engineer=1 --promote-to-org --confirmed-in 2 >/dev/null 2>&1; then
  bad "a typed count is refused"
else
  ok "a typed count is refused"
fi
if "$PYTHON3" "$OR" --cache-root "$ORC" record --project alpha --issue A-1 --outcome reverted \
     --skills software-engineer=1 --promote-to-org --confirmed-in gamma >/dev/null 2>&1; then
  bad "a project with no memory on disk cannot have confirmed anything"
else
  ok "a project with no memory on disk cannot have confirmed anything"
fi
if "$PYTHON3" "$OR" --cache-root "$ORC" record --project alpha --issue A-1 --outcome reverted \
     --skills software-engineer=1 --summary "flaky retry loop" --promote-to-org --confirmed-in beta >/dev/null 2>&1 \
   && grep -q "alpha, beta" "$ORC/_org/memory.md"; then
  ok "two projects with memories on disk promote, with both named as provenance"
else
  bad "two projects with memories on disk promote, with both named as provenance" \
      "$(cat "$ORC/_org/memory.md" 2>/dev/null | tail -3)"
fi

# ---------------------------------------------------------------------------
sec "Mutation probes"
# ---------------------------------------------------------------------------
PROBE="$BOX/probe"
mkdir -p "$PROBE"
cp "$KB" "$REPO/scripts/durable.py" "$REPO/scripts/guard_audit.py" "$PROBE/"

# Probe 1: remove the evidence-identity check and the same evidence must inflate.
"$PYTHON3" - "$PROBE/knowledge.py" <<'PY'
import pathlib, sys
path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
needle = "            new_evidence = [e for e in evidence if e not in lesson.evidence]\n"
if needle not in text:
    sys.exit(3)
path.write_text(text.replace(needle, "            new_evidence = list(evidence)\n", 1), encoding="utf-8")
PY
if [ $? -ne 0 ]; then
  bad "probe 1 could weaken the build" "the evidence-identity check was not found"
else
  R5="$(new_repo probe1)"
  (
    cd "$R5" || exit 0
    for _ in 1 2 3; do
      "$PYTHON3" "$PROBE/knowledge.py" lesson add --id probe-lesson --trigger t --action a --evidence T >/dev/null 2>&1
    done
  )
  if [ "$(field "$(lesson_file "$R5" probe-lesson)" confirmations)" = "3" ]; then
    ok "probe 1: without evidence identity, repeated submission inflates confirmations"
  else
    bad "probe 1: without evidence identity, repeated submission inflates confirmations" \
        "the weakened build still refused, so the check is untested"
  fi
fi

# Probe 2: let a contradiction refresh verified_at and it must show as fresh.
cp "$KB" "$PROBE/knowledge.py"
"$PYTHON3" - "$PROBE/knowledge.py" <<'PY'
import pathlib, sys
path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
needle = '        data["last_contradicted_at"] = today()\n'
if needle not in text:
    sys.exit(3)
path.write_text(text.replace(needle, needle + '        data["verified_at"] = today()\n', 1), encoding="utf-8")
PY
if [ $? -ne 0 ]; then
  bad "probe 2 could weaken the build" "the contradiction path was not found"
else
  R6="$(new_repo probe2)"
  (
    cd "$R6" || exit 0
    "$PYTHON3" "$PROBE/knowledge.py" lesson add --id probe-lesson --trigger t --action a --evidence T >/dev/null 2>&1
  )
  set_field "$(lesson_file "$R6" probe-lesson)" verified_at "2025-01-01"
  (cd "$R6" && "$PYTHON3" "$PROBE/knowledge.py" lesson contradict probe-lesson >/dev/null 2>&1)
  if [ "$(field "$(lesson_file "$R6" probe-lesson)" verified_at)" != "2025-01-01" ]; then
    ok "probe 2: without the guard a contradiction refreshes verified_at"
  else
    bad "probe 2: without the guard a contradiction refreshes verified_at" \
        "the weakened build still held, so the property is untested"
  fi
fi

# Probe 3: count only the payload again and the frame must overrun the budget.
cp "$KB" "$PROBE/knowledge.py"
"$PYTHON3" - "$PROBE/knowledge.py" <<'PY'
import pathlib, sys
path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
needle = "            if rendered_length(parts + [line]) + notice_reserve > budget_chars:\n"
if needle not in text:
    sys.exit(3)
weak = "            if sum(len(p) for p in parts[1:] + [line]) > budget_chars:\n"
text = text.replace(needle, weak, 1)
needle2 = "    while rendered_length(parts) > budget_chars and shown > 0:\n"
if needle2 not in text:
    sys.exit(3)
text = text.replace(needle2, "    while False:\n", 1)
path.write_text(text, encoding="utf-8")
PY
if [ $? -ne 0 ]; then
  bad "probe 3 could weaken the build" "the budget accounting was not found"
else
  OUT="$(cd "$R3" && "$PYTHON3" "$PROBE/knowledge.py" read --budget-chars 4000 2>/dev/null)"
  if [ "${#OUT}" -gt 4000 ]; then
    ok "probe 3: counting only the payload overruns the budget (${#OUT} chars)"
  else
    bad "probe 3: counting only the payload overruns the budget" \
        "the weakened build still fit, so the accounting is untested"
  fi
fi

# ---------------------------------------------------------------------------
printf '\n== summary ==\n'
printf '  passed: %d\n' "$PASS"
printf '  failed: %d\n' "$FAIL"
if [ "$FAIL" -ne 0 ]; then
  printf '\nMEMORY_INTEGRITY: FAIL\n'
  exit 1
fi
printf '\nMEMORY_INTEGRITY: PASS\n'
exit 0
