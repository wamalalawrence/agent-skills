#!/usr/bin/env bash
# Adaptive execution verification.
#
# The change under test is that workflow depth now varies with what the work
# actually is. That is a useful change and a dangerous one, because the failure
# mode is silent: nothing looks wrong when a security fix quietly runs at the
# depth meant for a read-only lookup. The output is still confident, still
# formatted correctly, and simply less true.
#
# So the assertions are lopsided on purpose. Relaxation is tested to be narrow —
# LIGHT only when every condition holds — and escalation is tested to be
# absolute. There is no signal, flag, or combination that lowers a floor.
#
# Four properties:
#
#   1. the profile is a deterministic function of its signals;
#   2. escalation cannot be overridden, including by an explicit request;
#   3. concurrency requires proven independence and stays bounded;
#   4. stagnation is detected by absence of progress, not by elapsed time.
#
# The mutation probes remove one condition each and assert the matching check
# then fails.
#
# Usage:
#   bash scripts/test-adaptive-execution.sh
#
# Exit 0 when every check passes, 1 otherwise.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 2
PYTHON3="${PYTHON3:-python3}"
PROFILE="${REPO}/scripts/execution-profile.py"
WATCHDOG="${REPO}/scripts/execution-watchdog.py"
PLANNEXT="${REPO}/scripts/delivery-run-next.py"
BB="${REPO}/scripts/blackboard.py"

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

# `profile_of ARGS...` — the decided profile as a bare word.
profile_of() {
  "$PYTHON3" "$PROFILE" --json "$@" 2>/dev/null \
    | "$PYTHON3" -c 'import json,sys; print(json.load(sys.stdin)["profile"])'
}

# `field_of FIELD ARGS...` — one top-level field of the decision, as JSON.
field_of() {
  local field="$1"; shift
  "$PYTHON3" "$PROFILE" --json "$@" 2>/dev/null \
    | "$PYTHON3" -c "import json,sys; print(json.dumps(json.load(sys.stdin)['$field']))"
}

# `expect_profile EXPECTED LABEL ARGS...`
expect_profile() {
  local expected="$1" label="$2"; shift 2
  local got
  got="$(profile_of "$@")"
  if [ "$got" = "$expected" ]; then
    ok "$label"
  else
    bad "$label" "expected $expected, got ${got:-<none>}"
  fi
}

printf 'adaptive execution\n'

# ---------------------------------------------------------------------------
sec "Relaxation is narrow"
# ---------------------------------------------------------------------------
# The reported incident: "give me the failed-payment counts from these three
# systems" was treated as three root-cause investigations.

LIGHT_ARGS=(--reads-only --size S --uncertainty low --blast-radius contained
            --verification-cost low)

expect_profile LIGHT "a bounded read-only lookup is LIGHT" "${LIGHT_ARGS[@]}"
expect_profile STANDARD "an unclassified task is STANDARD, not LIGHT"

# Each of these removes exactly one LIGHT condition. All must fall back to
# STANDARD: LIGHT is granted only when the whole set holds.
expect_profile STANDARD "writing anything is not LIGHT" \
  --mutates --size S --uncertainty low --blast-radius contained --verification-cost low
expect_profile STANDARD "size M is not LIGHT" \
  --reads-only --size M --uncertainty low --blast-radius contained --verification-cost low
expect_profile STANDARD "medium uncertainty is not LIGHT" \
  --reads-only --size S --uncertainty medium --blast-radius contained --verification-cost low
expect_profile STANDARD "shared state is not LIGHT" \
  --reads-only --size S --uncertainty low --blast-radius contained --verification-cost low \
  --shared-state
expect_profile STANDARD "a service-wide blast radius is not LIGHT" \
  --reads-only --size S --uncertainty low --blast-radius service --verification-cost low
expect_profile STANDARD "expensive verification is not LIGHT" \
  --reads-only --size S --uncertainty low --blast-radius contained --verification-cost high
expect_profile STANDARD "having dependents is not LIGHT" \
  "${LIGHT_ARGS[@]}" --dependencies 2
expect_profile STANDARD "--reads-only with --mutates is not LIGHT" \
  --reads-only --mutates --size S --uncertainty low --blast-radius contained \
  --verification-cost low

# ---------------------------------------------------------------------------
sec "Escalation is absolute"
# ---------------------------------------------------------------------------
# Every one of these is given the full set of LIGHT-qualifying signals as well.
# If any single escalation can be argued down by surrounding context, the floor
# is not a floor.

for domain in security crypto auth migration infrastructure payments credentials \
              data-loss cross-system; do
  expect_profile RIGOROUS "domain '$domain' forces RIGOROUS despite LIGHT signals" \
    "${LIGHT_ARGS[@]}" --domain "$domain"
done

expect_profile RIGOROUS "an irreversible change forces RIGOROUS" \
  "${LIGHT_ARGS[@]}" --reversible no
expect_profile RIGOROUS "a production blast radius forces RIGOROUS" \
  --reads-only --size S --uncertainty low --verification-cost low --blast-radius production
expect_profile RIGOROUS "a cross-system blast radius forces RIGOROUS" \
  --reads-only --size S --uncertainty low --verification-cost low --blast-radius cross-system

# The load-bearing one: an explicit request must not be able to buy a discount.
expect_profile RIGOROUS "--require LIGHT cannot lower a migration" \
  "${LIGHT_ARGS[@]}" --domain migration --require LIGHT
expect_profile RIGOROUS "--require STANDARD cannot lower a security change" \
  "${LIGHT_ARGS[@]}" --domain security --require STANDARD
expect_profile RIGOROUS "--require LIGHT cannot lower an irreversible change" \
  "${LIGHT_ARGS[@]}" --reversible no --require LIGHT

REFUSAL="$("$PYTHON3" "$PROFILE" "${LIGHT_ARGS[@]}" --domain migration --require LIGHT 2>&1)"
if contains "$REFUSAL" "was NOT applied"; then
  ok "a refused downgrade is stated, not silently ignored"
else
  bad "a refused downgrade is stated, not silently ignored" "$REFUSAL"
fi

# Requesting MORE rigour is always allowed. Nobody is stopped from being careful.
expect_profile RIGOROUS "--require RIGOROUS raises a lookup" "${LIGHT_ARGS[@]}" --require RIGOROUS
expect_profile STANDARD "--require STANDARD raises a lookup" "${LIGHT_ARGS[@]}" --require STANDARD

# ---------------------------------------------------------------------------
sec "LIGHT gives up ceremony, never safety"
# ---------------------------------------------------------------------------
# This is the section that decides whether the whole change was worth making. If
# LIGHT can skip verification, the speed came out of correctness.

ALWAYS="$(field_of always_required "${LIGHT_ARGS[@]}")"
for invariant in credential-safety authorization-checks bounded-reads \
                 explicit-verification evidence-retained safety-floor; do
  if contains "$ALWAYS" "$invariant"; then
    ok "LIGHT still requires $invariant"
  else
    bad "LIGHT still requires $invariant" "$ALWAYS"
  fi
done

# The same list, at every profile. A per-profile safety list would rot.
for prof in STANDARD RIGOROUS; do
  OTHER="$(field_of always_required --require "$prof")"
  if [ "$OTHER" = "$ALWAYS" ]; then
    ok "the invariant set is identical at $prof"
  else
    bad "the invariant set is identical at $prof" "$OTHER"
  fi
done

LIGHT_REQ="$(field_of requires "${LIGHT_ARGS[@]}")"
if contains "$LIGHT_REQ" '"delivery_plan": false' \
   && contains "$LIGHT_REQ" '"fresh_context_dispatch": false' \
   && contains "$LIGHT_REQ" '"independent_review": false'; then
  ok "LIGHT drops the delivery plan, the fresh-agent handoff, and the review agent"
else
  bad "LIGHT drops the delivery plan, the fresh-agent handoff, and the review agent" "$LIGHT_REQ"
fi

RIG_REQ="$(field_of requires --domain security)"
if contains "$RIG_REQ" '"independent_review": true' \
   && contains "$RIG_REQ" '"mutation_testing": true' \
   && contains "$RIG_REQ" '"evidence_depth": "full"'; then
  ok "RIGOROUS keeps independent review, mutation testing, and full evidence"
else
  bad "RIGOROUS keeps independent review, mutation testing, and full evidence" "$RIG_REQ"
fi

# ---------------------------------------------------------------------------
sec "The decision is deterministic"
# ---------------------------------------------------------------------------
# A profile that varies run to run cannot be tested, reproduced from a plan
# file, or argued with.

FIRST="$("$PYTHON3" "$PROFILE" --json "${LIGHT_ARGS[@]}" --domain security 2>/dev/null)"
STABLE=1
for _ in 1 2 3 4 5; do
  AGAIN="$("$PYTHON3" "$PROFILE" --json "${LIGHT_ARGS[@]}" --domain security 2>/dev/null)"
  [ "$AGAIN" = "$FIRST" ] || STABLE=0
done
if [ "$STABLE" -eq 1 ]; then
  ok "repeated invocations return byte-identical decisions"
else
  bad "repeated invocations return byte-identical decisions"
fi

# Signal order must not matter either.
A="$(profile_of --domain security --domain payments "${LIGHT_ARGS[@]}")"
B="$(profile_of --domain payments --domain security "${LIGHT_ARGS[@]}")"
if [ "$A" = "$B" ] && [ "$A" = "RIGOROUS" ]; then
  ok "the order signals are supplied in does not change the result"
else
  bad "the order signals are supplied in does not change the result" "$A vs $B"
fi

UNKNOWN_RC=0
"$PYTHON3" "$PROFILE" --domain nonsense-domain >/dev/null 2>&1 || UNKNOWN_RC=$?
if [ "$UNKNOWN_RC" -eq 0 ]; then
  ok "an unrecognised domain is reported but does not fail the call"
else
  bad "an unrecognised domain is reported but does not fail the call" "rc=$UNKNOWN_RC"
fi

# ---------------------------------------------------------------------------
sec "Concurrency requires proven independence"
# ---------------------------------------------------------------------------

PLANS="$BOX/plans"

# `make_plan NAME POINTER` starts an index; `add_phase` appends rows; phase
# files are written by `write_phase`.
make_plan() {
  local dir="$PLANS/$1"
  mkdir -p "$dir/phased-plan"
  cat > "$dir/phased-plan/README.md" <<EOF
---
work_key: PROJ-900
current_dispatch_pointer: $2
readiness_decision: READY_FOR_DISPATCH
state: active
---

## Phases

| ID | Title | Owner skill | Size | State | Prereqs | Profile | Parallel |
| -- | ----- | ----------- | ---- | ----- | ------- | ------- | -------- |
EOF
  printf '%s\n' "$dir"
}

add_phase() {
  # dir id title owner size state prereqs profile parallel
  printf '| %s | %s | %s | %s | %s | %s | %s | %s |\n' \
    "$2" "$3" "$4" "$5" "$6" "$7" "$8" "$9" >> "$1/phased-plan/README.md"
}

write_phase() {
  # dir id slug profile parallel_safe parallel_with mutation_targets [effort]
  cat > "$1/phased-plan/$2-$3.md" <<EOF
---
phase_id: ${2#phase-}
execution_profile: $4
parallel_safe: $5
parallel_with: $6
mutation_targets: $7
expected_effort_minutes: ${8:-10}
---
EOF
}

group_of() {
  "$PYTHON3" "$PLANNEXT" "$1" 2>/dev/null \
    | "$PYTHON3" -c 'import json,sys; print(",".join(json.load(sys.stdin)["concurrency"]["parallel_group"]))'
}

# Case 1: three independent read-only inspections. The safe example.
DIR="$(make_plan independent phase-02)"
add_phase "$DIR" phase-01 Groundwork software-engineer S done none LIGHT no
add_phase "$DIR" phase-02 CI issue-investigator S ready 01 LIGHT yes
add_phase "$DIR" phase-03 Sentry issue-investigator S ready 01 LIGHT yes
add_phase "$DIR" phase-04 Logs issue-investigator S ready 01 LIGHT yes
write_phase "$DIR" phase-02 ci LIGHT true "[02, 03, 04]" "[evidence/ci.md]"
write_phase "$DIR" phase-03 sentry LIGHT true "[02, 03, 04]" "[evidence/sentry.md]"
write_phase "$DIR" phase-04 logs LIGHT true "[02, 03, 04]" "[evidence/logs.md]"
GROUP="$(group_of "$DIR")"
if [ "$GROUP" = "phase-02,phase-03,phase-04" ]; then
  ok "independent read-only phases are grouped for concurrent dispatch"
else
  bad "independent read-only phases are grouped for concurrent dispatch" "got '$GROUP'"
fi

# Case 2: overlapping mutation targets. Two agents editing the same file is the
# canonical unsafe case, and `parallel_safe: true` on both does not make it safe.
DIR="$(make_plan overlap phase-02)"
add_phase "$DIR" phase-02 Rename software-engineer S ready none STANDARD yes
add_phase "$DIR" phase-03 Retype software-engineer S ready none STANDARD yes
write_phase "$DIR" phase-02 rename STANDARD true "[03]" "[src/api/handler.ts]"
write_phase "$DIR" phase-03 retype STANDARD true "[02]" "[src/api/handler.ts]"
GROUP="$(group_of "$DIR")"
if [ "$GROUP" = "" ]; then
  ok "phases writing the same file are not grouped, despite both claiming safety"
else
  bad "phases writing the same file are not grouped, despite both claiming safety" "got '$GROUP'"
fi

# Case 3: a one-sided claim. One phase was written without the other in mind.
DIR="$(make_plan onesided phase-02)"
add_phase "$DIR" phase-02 A issue-investigator S ready none LIGHT yes
add_phase "$DIR" phase-03 B issue-investigator S ready none LIGHT yes
write_phase "$DIR" phase-02 a LIGHT true "[03]" "[evidence/a.md]"
write_phase "$DIR" phase-03 b LIGHT true "[]" "[evidence/b.md]"
GROUP="$(group_of "$DIR")"
if [ "$GROUP" = "" ]; then
  ok "a one-sided parallel_with claim does not form a group"
else
  bad "a one-sided parallel_with claim does not form a group" "got '$GROUP'"
fi

# Case 4: undeclared mutation targets. Silence is not a safety claim.
DIR="$(make_plan undeclared phase-02)"
add_phase "$DIR" phase-02 A issue-investigator S ready none LIGHT yes
add_phase "$DIR" phase-03 B issue-investigator S ready none LIGHT yes
cat > "$DIR/phased-plan/phase-02-a.md" <<'EOF'
---
phase_id: 02
execution_profile: LIGHT
parallel_safe: true
parallel_with: [03]
---
EOF
write_phase "$DIR" phase-03 b LIGHT true "[02]" "[evidence/b.md]"
GROUP="$(group_of "$DIR")"
if [ "$GROUP" = "" ]; then
  ok "a phase that does not declare what it writes is never grouped"
else
  bad "a phase that does not declare what it writes is never grouped" "got '$GROUP'"
fi

# Case 5: a dependency edge beats a parallel_with claim.
DIR="$(make_plan depedge phase-02)"
add_phase "$DIR" phase-02 Schema software-engineer S ready none STANDARD yes
add_phase "$DIR" phase-03 Consumer software-engineer S ready 02 STANDARD yes
write_phase "$DIR" phase-02 schema STANDARD true "[03]" "[db/schema.sql]"
write_phase "$DIR" phase-03 consumer STANDARD true "[02]" "[src/consumer.ts]"
GROUP="$(group_of "$DIR")"
if [ "$GROUP" = "" ]; then
  ok "a dependent phase is not grouped even when both claim parallel safety"
else
  bad "a dependent phase is not grouped even when both claim parallel safety" "got '$GROUP'"
fi

# Case 6: the cap.
DIR="$(make_plan capped phase-02)"
add_phase "$DIR" phase-02 A issue-investigator S ready none LIGHT yes
add_phase "$DIR" phase-03 B issue-investigator S ready none LIGHT yes
add_phase "$DIR" phase-04 C issue-investigator S ready none LIGHT yes
add_phase "$DIR" phase-05 D issue-investigator S ready none LIGHT yes
add_phase "$DIR" phase-06 E issue-investigator S ready none LIGHT yes
for pair in 02:a 03:b 04:c 05:d 06:e; do
  write_phase "$DIR" "phase-${pair%%:*}" "${pair##*:}" LIGHT true \
    "[02, 03, 04, 05, 06]" "[evidence/${pair##*:}.md]"
done
GROUP="$(group_of "$DIR")"
COUNT="$(printf '%s' "$GROUP" | tr ',' '\n' | grep -c .)"
if [ "$COUNT" -le 3 ] && [ "$COUNT" -gt 1 ]; then
  ok "a group of five candidates is capped at 3, not fanned out"
else
  bad "a group of five candidates is capped at 3, not fanned out" "got $COUNT: $GROUP"
fi

COUNT_ENV="$(AGENT_SKILLS_MAX_PARALLEL=99 "$PYTHON3" "$PLANNEXT" "$DIR" 2>/dev/null \
  | "$PYTHON3" -c 'import json,sys; print(len(json.load(sys.stdin)["concurrency"]["parallel_group"]))')"
if [ "$COUNT_ENV" -le 3 ]; then
  ok "AGENT_SKILLS_MAX_PARALLEL is clamped, not trusted"
else
  bad "AGENT_SKILLS_MAX_PARALLEL is clamped, not trusted" "got $COUNT_ENV"
fi

COUNT_ONE="$(AGENT_SKILLS_MAX_PARALLEL=1 "$PYTHON3" "$PLANNEXT" "$DIR" 2>/dev/null \
  | "$PYTHON3" -c 'import json,sys; print(len(json.load(sys.stdin)["concurrency"]["parallel_group"]))')"
if [ "$COUNT_ONE" -eq 0 ]; then
  ok "a limit of 1 disables grouping entirely"
else
  bad "a limit of 1 disables grouping entirely" "got $COUNT_ONE"
fi

# Case 7: a parent and a child path. Set intersection on the raw strings called
# `src/api` and `src/api/handler.ts` disjoint; they are the same write.
DIR="$(make_plan parentchild phase-02)"
add_phase "$DIR" phase-02 Dir software-engineer S ready none STANDARD yes
add_phase "$DIR" phase-03 File software-engineer S ready none STANDARD yes
write_phase "$DIR" phase-02 dir STANDARD true "[03]" "[src/api]"
write_phase "$DIR" phase-03 file STANDARD true "[02]" "[src/api/handler.ts]"
GROUP="$(group_of "$DIR")"
if [ "$GROUP" = "" ]; then
  ok "a phase writing a directory is not grouped with one writing a file inside it"
else
  bad "a phase writing a directory is not grouped with one writing a file inside it" "got '$GROUP'"
fi

# Case 8: the same path spelled differently. Aliases are one path.
DIR="$(make_plan alias phase-02)"
add_phase "$DIR" phase-02 A software-engineer S ready none STANDARD yes
add_phase "$DIR" phase-03 B software-engineer S ready none STANDARD yes
write_phase "$DIR" phase-02 a STANDARD true "[03]" "[src/api/handler.ts]"
write_phase "$DIR" phase-03 b STANDARD true "[02]" "[./src/./api/../api/handler.ts]"
GROUP="$(group_of "$DIR")"
if [ "$GROUP" = "" ]; then
  ok "a dot-segment alias of a claimed path is not grouped"
else
  bad "a dot-segment alias of a claimed path is not grouped" "got '$GROUP'"
fi

# Case 9: a target that cannot be proven independent — absolute, or escaping
# the repository — disqualifies the phase rather than being compared as text.
DIR="$(make_plan escaping phase-02)"
add_phase "$DIR" phase-02 A software-engineer S ready none STANDARD yes
add_phase "$DIR" phase-03 B software-engineer S ready none STANDARD yes
write_phase "$DIR" phase-02 a STANDARD true "[03]" "[src/a.ts]"
write_phase "$DIR" phase-03 b STANDARD true "[02]" "[../elsewhere/b.ts]"
GROUP="$(group_of "$DIR")"
if [ "$GROUP" = "" ]; then
  ok "a target that escapes the repository is never proven independent"
else
  bad "a target that escapes the repository is never proven independent" "got '$GROUP'"
fi
write_phase "$DIR" phase-03 b STANDARD true "[02]" "[/tmp/b.ts]"
GROUP="$(group_of "$DIR")"
if [ "$GROUP" = "" ]; then
  ok "an absolute target is never proven independent"
else
  bad "an absolute target is never proven independent" "got '$GROUP'"
fi

# Case 10: genuinely disjoint paths and distinct named resources still group,
# so the overlap rule is not a blanket refusal.
DIR="$(make_plan disjoint phase-02)"
add_phase "$DIR" phase-02 A software-engineer S ready none STANDARD yes
add_phase "$DIR" phase-03 B software-engineer S ready none STANDARD yes
write_phase "$DIR" phase-02 a STANDARD true "[03]" "[src/api/handler.ts, db:orders]"
write_phase "$DIR" phase-03 b STANDARD true "[02]" "[src/api-client/index.ts, db:sessions]"
GROUP="$(group_of "$DIR")"
if [ "$GROUP" = "phase-02,phase-03" ]; then
  ok "sibling paths with a shared prefix and distinct resources are still grouped"
else
  bad "sibling paths with a shared prefix and distinct resources are still grouped" "got '$GROUP'"
fi
write_phase "$DIR" phase-03 b STANDARD true "[02]" "[src/api-client/index.ts, DB:orders]"
GROUP="$(group_of "$DIR")"
if [ "$GROUP" = "" ]; then
  ok "the same named resource in a different case is one resource"
else
  bad "the same named resource in a different case is one resource" "got '$GROUP'"
fi

# ---------------------------------------------------------------------------
sec "Phase profiles are read, and cannot be downgraded by a stale index"
# ---------------------------------------------------------------------------

DIR="$(make_plan profiles phase-02)"
add_phase "$DIR" phase-02 Interceptor software-engineer M ready none LIGHT no
write_phase "$DIR" phase-02 interceptor RIGOROUS false "[]" "[src/Interceptor.java]" 45
DECISION="$("$PYTHON3" "$PLANNEXT" "$DIR" 2>/dev/null)"
GOT="$(printf '%s' "$DECISION" | "$PYTHON3" -c 'import json,sys; print(json.load(sys.stdin)["phase"]["execution_profile"])')"
if [ "$GOT" = "RIGOROUS" ]; then
  ok "the phase file's RIGOROUS wins over a LIGHT column in the index"
else
  bad "the phase file's RIGOROUS wins over a LIGHT column in the index" "got $GOT"
fi
REVIEW="$(printf '%s' "$DECISION" | "$PYTHON3" -c 'import json,sys; print(json.load(sys.stdin)["phase"]["independent_review_required"])')"
if [ "$REVIEW" = "True" ]; then
  ok "a RIGOROUS phase still requires independent review"
else
  bad "a RIGOROUS phase still requires independent review" "got $REVIEW"
fi
EFFORT="$(printf '%s' "$DECISION" | "$PYTHON3" -c 'import json,sys; print(json.load(sys.stdin)["phase"]["expected_effort_minutes"])')"
if [ "$EFFORT" = "45" ]; then
  ok "the phase's effort budget reaches the runner for the watchdog"
else
  bad "the phase's effort budget reaches the runner for the watchdog" "got $EFFORT"
fi

DIR="$(make_plan lightphase phase-02)"
add_phase "$DIR" phase-02 Typo software-engineer S ready none LIGHT no
write_phase "$DIR" phase-02 typo LIGHT false "[]" "[docs/readme.md]" 5
FRESH="$("$PYTHON3" "$PLANNEXT" "$DIR" 2>/dev/null \
  | "$PYTHON3" -c 'import json,sys; print(json.load(sys.stdin)["phase"]["fresh_context_required"])')"
if [ "$FRESH" = "False" ]; then
  ok "a LIGHT phase does not require a fresh-context agent"
else
  bad "a LIGHT phase does not require a fresh-context agent" "got $FRESH"
fi

# ---------------------------------------------------------------------------
sec "Plans written before this release still parse"
# ---------------------------------------------------------------------------
# The two columns were appended rather than inserted precisely so this holds.

DIR="$PLANS/legacy"
mkdir -p "$DIR/phased-plan"
cat > "$DIR/phased-plan/README.md" <<'EOF'
---
work_key: PROJ-901
current_dispatch_pointer: phase-01
readiness_decision: READY_FOR_DISPATCH
state: active
---

## Phases

| ID       | Title    | Owner skill       | Size | State | Prereqs |
| -------- | -------- | ----------------- | ---- | ----- | ------- |
| phase-01 | Old plan | software-engineer | M    | ready | none    |
EOF
LEGACY="$("$PYTHON3" "$PLANNEXT" "$DIR" 2>/dev/null)"
LEGACY_ACTION="$(printf '%s' "$LEGACY" | "$PYTHON3" -c 'import json,sys; print(json.load(sys.stdin)["action"])')"
LEGACY_PROFILE="$(printf '%s' "$LEGACY" | "$PYTHON3" -c 'import json,sys; print(json.load(sys.stdin)["phase"]["execution_profile"])')"
if [ "$LEGACY_ACTION" = "dispatch" ] && [ "$LEGACY_PROFILE" = "STANDARD" ]; then
  ok "a six-column index still dispatches, defaulting to STANDARD"
else
  bad "a six-column index still dispatches, defaulting to STANDARD" \
      "action=$LEGACY_ACTION profile=$LEGACY_PROFILE"
fi

DIR="$(make_plan garbageprofile phase-02)"
add_phase "$DIR" phase-02 A software-engineer S ready none WHATEVER no
GOT="$("$PYTHON3" "$PLANNEXT" "$DIR" 2>/dev/null \
  | "$PYTHON3" -c 'import json,sys; print(json.load(sys.stdin)["phase"]["execution_profile"])')"
if [ "$GOT" = "STANDARD" ]; then
  ok "an unrecognised profile column falls back to STANDARD, not to LIGHT"
else
  bad "an unrecognised profile column falls back to STANDARD, not to LIGHT" "got $GOT"
fi

# ---------------------------------------------------------------------------
sec "What a prerequisite learned reaches the next phase's brief"
# ---------------------------------------------------------------------------
# Each executor writes `follow_up_context` into the evidence pack for the phases
# after it. Nothing read it back: a dispatcher carried the Tailwind scanner trap
# and the duplicate colour token into the next brief only because it remembered
# to. `plan-next` now returns it with the dispatch decision.

SECRET_LIKE="$("$PYTHON3" -c "import secrets; print('Tok' + secrets.token_hex(20))")"
DIR="$(make_plan continuity phase-03)"
add_phase "$DIR" phase-01 Tokens software-engineer S done none STANDARD no
add_phase "$DIR" phase-02 Scanner software-engineer S done 01 STANDARD no
add_phase "$DIR" phase-03 Screens software-engineer M ready "01, 02" STANDARD no
add_phase "$DIR" phase-04 Later software-engineer M ready 03 STANDARD no
write_phase "$DIR" phase-03 screens STANDARD false "[]" "[src/screens]"
cat > "$DIR/evidence-pack.yml" <<EOF
issue_key: PROJ-900
delivery_plan:
  current_dispatch_pointer: phase-03
  phases:
    - id: phase-01
      state: done
      completion_summary: "Tokens moved to CSS variables."
      artifacts:
        - "src/tokens.css"
      review:
        verdict: PASS
        state: nested-and-ignored
      follow_up_context:
        - "--tdx-text-muted is defined twice; the second definition wins"
        - "api key used during the spike was ${SECRET_LIKE}"
    - id: phase-02
      state: done
      completion_summary: "Scanner configured."
      follow_up_context: []
    - id: phase-04
      state: ready
review:
  round: 0
EOF
CONT="$("$PYTHON3" "$PLANNEXT" "$DIR" 2>/dev/null)"
cont_py() {
  printf '%s' "$CONT" | "$PYTHON3" -c "import json,sys; d=json.load(sys.stdin)['phase']['prerequisite_context']; $1"
}
if [ "$(cont_py 'print([p["id"] for p in d["phases"]])')" = "['phase-01', 'phase-02']" ]; then
  ok "the dispatch decision carries every prerequisite, in order"
else
  bad "the dispatch decision carries every prerequisite, in order" "$CONT"
fi
if contains "$(cont_py 'print(d["phases"][0]["follow_up_context"])')" "defined twice"; then
  ok "a prerequisite's follow_up_context is returned for the brief"
else
  bad "a prerequisite's follow_up_context is returned for the brief" "$CONT"
fi
if [ "$(cont_py 'print(d["phases"][0]["state"])')" = "done" ]; then
  ok "a nested mapping inside a phase does not overwrite the phase's own keys"
else
  bad "a nested mapping inside a phase does not overwrite the phase's own keys" "$CONT"
fi
if [ "$(cont_py 'print(d["missing"])')" = "['phase-02']" ]; then
  ok "a prerequisite that recorded nothing to carry forward is named, not silently empty"
else
  bad "a prerequisite that recorded nothing to carry forward is named, not silently empty" "$CONT"
fi
if contains "$CONT" "$SECRET_LIKE"; then
  bad "a credential-shaped value in the evidence pack never reaches the decision"
else
  ok "a credential-shaped value in the evidence pack never reaches the decision"
fi

DIR="$(make_plan continuity-nopack phase-02)"
add_phase "$DIR" phase-01 A software-engineer S done none STANDARD no
add_phase "$DIR" phase-02 B software-engineer S ready 01 STANDARD no
NOPACK="$("$PYTHON3" "$PLANNEXT" "$DIR" 2>/dev/null)"
NOPACK_ACTION="$(printf '%s' "$NOPACK" | "$PYTHON3" -c 'import json,sys; print(json.load(sys.stdin)["action"])')"
if [ "$NOPACK_ACTION" = "dispatch" ] && contains "$NOPACK" "No evidence pack on disk"; then
  ok "a missing evidence pack is reported and never blocks the decision"
else
  bad "a missing evidence pack is reported and never blocks the decision" "$NOPACK"
fi

# ---------------------------------------------------------------------------
sec "Stagnation is detected by absence of progress, not elapsed time"
# ---------------------------------------------------------------------------

CACHE="$BOX/wcache"
"$PYTHON3" "$BB" --cache-root "$CACHE" init --project demo proj-950 >/dev/null 2>&1

# Timestamps are pinned rather than taken from the clock. The blackboard CLI
# stamps entries with the real time, so against a simulated `--now` every
# milestone reads as ancient and every run looks stalled — the fixture would be
# testing the clock rather than the verdict. `--now` and these written times
# come from the same fixed origin instead.
START="2026-01-01T00:00:00Z"
"$PYTHON3" - "$CACHE/proj-950/blackboard.json" "$START" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
data["created_at"] = sys.argv[2]
path.write_text(json.dumps(data, indent=2), encoding="utf-8")
PY

# `at MINUTES` — a timestamp that many minutes after the task started.
at() {
  "$PYTHON3" -c "
import datetime, sys
t = datetime.datetime.strptime('$START', '%Y-%m-%dT%H:%M:%SZ')
print((t + datetime.timedelta(minutes=float(sys.argv[1]))).strftime('%Y-%m-%dT%H:%M:%SZ'))" "$1"
}

# `record_progress_at MINUTES` — one milestone, stamped at a known offset.
record_progress_at() {
  "$PYTHON3" - "$CACHE/proj-950/blackboard.json" "$(at "$1")" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
data.setdefault("progress", []).append(
    {"at": sys.argv[2], "by": "issue-investigator", "kind": "query", "note": "counted rows"}
)
path.write_text(json.dumps(data, indent=2), encoding="utf-8")
PY
}

# `verdict BUDGET WHEN` — the watchdog's verdict at that point.
verdict() {
  "$PYTHON3" "$WATCHDOG" proj-950 --cache-root "$CACHE" --budget-minutes "$1" \
    --now "$(at "$2")" --json 2>/dev/null \
    | "$PYTHON3" -c 'import json,sys; print(json.load(sys.stdin)["verdict"])'
}

# No milestones yet. This is the reported case: a dispatch that ran roughly an
# hour and wrote nothing.
GOT="$(verdict 15 8)"
if [ "$GOT" = "continue" ]; then
  ok "an early run with nothing written yet is left alone"
else
  bad "an early run with nothing written yet is left alone" "got $GOT"
fi

GOT="$(verdict 15 20)"
if [ "$GOT" = "restart" ]; then
  ok "past the stall window with no milestone at all, the brief is restarted"
else
  bad "past the stall window with no milestone at all, the brief is restarted" "got $GOT"
fi

GOT="$(verdict 15 60)"
if [ "$GOT" = "stop" ]; then
  ok "an hour against a fifteen-minute budget with nothing written stops"
else
  bad "an hour against a fifteen-minute budget with nothing written stops" "got $GOT"
fi

STOP_RC=0
"$PYTHON3" "$WATCHDOG" proj-950 --cache-root "$CACHE" --budget-minutes 15 \
  --now "$(at 60)" >/dev/null 2>&1 || STOP_RC=$?
if [ "$STOP_RC" -eq 20 ]; then
  ok "a stop verdict exits 20 so a caller can branch on it"
else
  bad "a stop verdict exits 20 so a caller can branch on it" "rc=$STOP_RC"
fi

# Now the same task, with milestones landing as it goes. Same elapsed times,
# different answers: that difference IS the feature.
record_progress_at 5
record_progress_at 12
record_progress_at 22
record_progress_at 38

GOT="$(verdict 15 10)"
if [ "$GOT" = "continue" ]; then
  ok "work inside its budget with recent milestones continues"
else
  bad "work inside its budget with recent milestones continues" "got $GOT"
fi

GOT="$(verdict 15 20)"
if [ "$GOT" = "narrow" ]; then
  ok "over budget but still producing, the remaining scope is narrowed"
else
  bad "over budget but still producing, the remaining scope is narrowed" "got $GOT"
fi

GOT="$(verdict 5 40)"
if [ "$GOT" = "split" ]; then
  ok "well over budget but still producing, the work is split rather than killed"
else
  bad "well over budget but still producing, the work is split rather than killed" "got $GOT"
fi

# The elapsed-time-alone check: a long run that is still writing is NOT stopped.
GOT="$(verdict 5 40)"
if [ "$GOT" != "stop" ]; then
  ok "elapsed time alone never produces a stop while milestones keep landing"
else
  bad "elapsed time alone never produces a stop while milestones keep landing"
fi

REASSESS_RC=0
"$PYTHON3" "$WATCHDOG" proj-950 --cache-root "$CACHE" --budget-minutes 5 \
  --now "$(at 40)" >/dev/null 2>&1 || REASSESS_RC=$?
if [ "$REASSESS_RC" -eq 10 ]; then
  ok "a reassessment verdict exits 10, distinct from continue and stop"
else
  bad "a reassessment verdict exits 10, distinct from continue and stop" "rc=$REASSESS_RC"
fi

MISSING_RC=0
"$PYTHON3" "$WATCHDOG" proj-does-not-exist --cache-root "$CACHE" >/dev/null 2>&1 || MISSING_RC=$?
if [ "$MISSING_RC" -eq 2 ]; then
  ok "an unreadable task reports a usage error rather than guessing a verdict"
else
  bad "an unreadable task reports a usage error rather than guessing a verdict" "rc=$MISSING_RC"
fi

# ---------------------------------------------------------------------------
sec "Mutation probes"
# ---------------------------------------------------------------------------

PROBE="$BOX/probe"
mkdir -p "$PROBE"
# plan-next redacts what it reads from the evidence pack, so its sandboxed copy
# needs the redactor beside it or every probe against it dies on import.
cp "$REPO/scripts/guard_audit.py" "$PROBE/guard_audit.py"
# The watchdog resolves its cache through the shared resolver.
cp "$REPO/scripts/cache_root.py" "$PROBE/cache_root.py"

# Probe 1: remove the escalating-domain table and confirm a migration is then
# allowed down to LIGHT. This is the check that matters most in this file.
cp "$PROFILE" "$PROBE/execution-profile.py"
"$PYTHON3" - "$PROBE/execution-profile.py" <<'PY'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
weakened, count = re.subn(
    r"ESCALATING_DOMAINS = \{[^}]*\}",
    "ESCALATING_DOMAINS = {}",
    text,
    count=1,
)
if count == 0:
    sys.exit(3)
path.write_text(weakened, encoding="utf-8")
PY
if [ $? -ne 0 ]; then
  bad "probe 1 could weaken the build" "ESCALATING_DOMAINS not found"
else
  GOT="$("$PYTHON3" "$PROBE/execution-profile.py" --json "${LIGHT_ARGS[@]}" \
    --domain migration --require LIGHT 2>/dev/null \
    | "$PYTHON3" -c 'import json,sys; print(json.load(sys.stdin)["profile"])')"
  if [ "$GOT" = "LIGHT" ]; then
    ok "probe 1: without the escalation table a migration drops to LIGHT"
  else
    bad "probe 1: without the escalation table a migration drops to LIGHT" \
        "got $GOT — the floor test proves nothing"
  fi
fi

# Probe 2: remove the mutation-target overlap check and confirm two phases
# writing the same file are then grouped.
cp "$PLANNEXT" "$PROBE/delivery-run-next.py"
"$PYTHON3" - "$PROBE/delivery-run-next.py" <<'PY'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
weakened, count = re.subn(
    r'    return left == right or left\.startswith\(right \+ "/"\) or right\.startswith\(left \+ "/"\)\n',
    "    return False\n",
    text,
    count=1,
)
if count == 0:
    sys.exit(3)
path.write_text(weakened, encoding="utf-8")
PY
if [ $? -ne 0 ]; then
  bad "probe 2 could weaken the build" "the overlap check was not found"
else
  GOT="$("$PYTHON3" "$PROBE/delivery-run-next.py" "$PLANS/overlap" 2>/dev/null \
    | "$PYTHON3" -c 'import json,sys; print(",".join(json.load(sys.stdin)["concurrency"]["parallel_group"]))')"
  if [ -n "$GOT" ]; then
    ok "probe 2: without the overlap check two writers to one file are grouped"
  else
    bad "probe 2: without the overlap check two writers to one file are grouped" \
        "the weakened build still refused, so the check is untested"
  fi
fi

# Probe 3: make the watchdog fire on elapsed time alone and confirm the
# still-producing case is then killed.
cp "$WATCHDOG" "$PROBE/execution-watchdog.py"
"$PYTHON3" - "$PROBE/execution-watchdog.py" <<'PY'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
weakened, count = re.subn(
    r"    stalled = since_progress > \(stall_window if progress_times else first_window\)\n",
    "    stalled = True\n",
    text,
    count=1,
)
if count == 0:
    sys.exit(3)
path.write_text(weakened, encoding="utf-8")
PY
if [ $? -ne 0 ]; then
  bad "probe 3 could weaken the build" "the stall computation was not found"
else
  GOT="$("$PYTHON3" "$PROBE/execution-watchdog.py" proj-950 --cache-root "$CACHE" \
    --budget-minutes 5 --now "$(at 40)" --json 2>/dev/null \
    | "$PYTHON3" -c 'import json,sys; print(json.load(sys.stdin)["verdict"])')"
  if [ "$GOT" = "stop" ]; then
    ok "probe 3: treating every run as stalled kills work that was still producing"
  else
    bad "probe 3: treating every run as stalled kills work that was still producing" \
        "got $GOT — the stagnation-not-elapsed property is untested"
  fi
fi

# Probe 4: stop redacting what plan-next reads from the evidence pack, and a
# credential-shaped value rides into the next agent's brief.
cp "$PLANNEXT" "$PROBE/delivery-run-next.py"
"$PYTHON3" - "$PROBE/delivery-run-next.py" <<'PY'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
anchor = "        return [redact(str(item)) for item in value]\n"
if anchor not in text:
    sys.exit(3)
path.write_text(text.replace(anchor, "        return [str(item) for item in value]\n", 1),
                encoding="utf-8")
PY
if [ $? -ne 0 ]; then
  bad "probe 4 could weaken the build" "the evidence-pack redaction was not found"
else
  LEAK="$("$PYTHON3" "$PROBE/delivery-run-next.py" "$PLANS/continuity" 2>/dev/null)"
  if contains "$LEAK" "$SECRET_LIKE"; then
    ok "probe 4: without redaction an evidence-pack credential reaches the brief"
  else
    bad "probe 4: without redaction an evidence-pack credential reaches the brief" \
        "the weakened build still hid it, so the redaction test proves nothing"
  fi
fi

# ---------------------------------------------------------------------------
printf '\n== summary ==\n'
printf '  passed: %d\n' "$PASS"
printf '  failed: %d\n' "$FAIL"
if [ "$FAIL" -ne 0 ]; then
  printf '\nADAPTIVE_EXECUTION: FAIL\n'
  exit 1
fi
printf '\nADAPTIVE_EXECUTION: PASS\n'
exit 0
