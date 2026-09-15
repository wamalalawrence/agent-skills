#!/usr/bin/env bash
# Lifecycle filesystem safety.
#
# Task scratch lives at `<cache-root>/<issue-key>/`, and `finish-task` deletes
# that directory recursively once memory has been written. Recursive deletion
# driven by a user-supplied string is the most dangerous operation this project
# performs, and it went wrong in the field:
#
#   `finish-task` run with a lowercase issue key deleted the cache directory
#   belonging to the uppercase key, because macOS compares path components
#   case-insensitively and the cleanup step deleted whatever `exists()` matched.
#
# The reported incident used a real ticket key. These fixtures use the `PROJ`
# placeholder prefix the repository validator requires, which exercises the same
# property: `PROJ-805` on disk, `proj-805` from the caller.
#
# What is asserted here is not "cleanup works". It is that cleanup **fails
# closed** on every ambiguity: a key that only matches under the filesystem's
# equivalence rules removes nothing and says why. A cleanup that guesses is
# worse than one that refuses, because the thing it guesses away is the only
# copy of an investigation.
#
# The mutation probes exist because an assertion that would pass with the
# property removed is not evidence the property holds. Each probe weakens a
# sandboxed copy of the runtime and asserts the matching check then fails. See
# the probe-discipline section of docs/release-checklist.md.
#
# Usage:
#   bash scripts/test-lifecycle-fs.sh
#
# Exit 0 when every check passes, 1 otherwise.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 2
PYTHON3="${PYTHON3:-python3}"
PM="${REPO}/scripts/project-memory.py"
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

# `contains HAYSTACK NEEDLE` — matched with `case` so no pattern reaches a shell.
contains() {
  case "$1" in
    *"$2"*) return 0 ;;
    *) return 1 ;;
  esac
}

# A fresh cache root per case. Nothing here ever points at a real cache.
new_cache() {
  local dir="$BOX/cache-$1"
  rm -rf "$dir"
  mkdir -p "$dir"
  printf '%s\n' "$dir"
}

# Build a directory that looks like real task scratch.
make_task_dir() {
  local root="$1" key="$2"
  mkdir -p "$root/$key"
  printf '{"issue_key": "%s"}\n' "$key" > "$root/$key/blackboard.json"
  printf 'evidence\n' > "$root/$key/findings.md"
}

# `clean CACHE KEY` — run cleanup-task, capture stdout+stderr and the exit code.
clean() {
  local root="$1" key="$2"
  CLEAN_OUT="$("$PYTHON3" "$PM" --cache-root "$root" cleanup-task "$key" 2>&1)"
  CLEAN_RC=$?
  return 0
}

# Does this filesystem fold case? The answer changes which cases are meaningful,
# and hardcoding "macOS" would make the suite lie on a case-sensitive volume.
CASE_PROBE="$BOX/case-probe"
mkdir -p "$CASE_PROBE/AAA"
if [ -d "$CASE_PROBE/aaa" ]; then
  CASE_INSENSITIVE=1
else
  CASE_INSENSITIVE=0
fi

printf 'lifecycle filesystem safety\n'
printf '  filesystem folds case: %s\n' "$([ "$CASE_INSENSITIVE" -eq 1 ] && echo yes || echo no)"

# ---------------------------------------------------------------------------
sec "Exact-case cleanup still works"
# ---------------------------------------------------------------------------
# The fix must not turn cleanup off. If nothing is ever removed, scratch grows
# without bound and the next agent reads a stale blackboard.

CACHE="$(new_cache exact)"
make_task_dir "$CACHE" "proj-805"
clean "$CACHE" "proj-805"
if [ "$CLEAN_RC" -eq 0 ] && [ ! -d "$CACHE/proj-805" ]; then
  ok "lowercase key removes the lowercase directory"
else
  bad "lowercase key removes the lowercase directory" "rc=$CLEAN_RC out=$CLEAN_OUT"
fi

CACHE="$(new_cache exact-upper)"
make_task_dir "$CACHE" "PROJ-805"
clean "$CACHE" "PROJ-805"
if [ "$CLEAN_RC" -eq 0 ] && [ ! -d "$CACHE/PROJ-805" ]; then
  ok "uppercase key removes the uppercase directory it names exactly"
else
  bad "uppercase key removes the uppercase directory it names exactly" "rc=$CLEAN_RC out=$CLEAN_OUT"
fi

CACHE="$(new_cache absent)"
mkdir -p "$CACHE"
clean "$CACHE" "proj-999"
if [ "$CLEAN_RC" -eq 0 ]; then
  ok "a key with no directory at all is a no-op, not an error"
else
  bad "a key with no directory at all is a no-op, not an error" "rc=$CLEAN_RC out=$CLEAN_OUT"
fi

# ---------------------------------------------------------------------------
sec "Case-variant cleanup refuses (the reported data-loss defect)"
# ---------------------------------------------------------------------------
# Each of these had the whole cache directory deleted before the fix.

for variant in "proj-805" "Proj-805" "pRoJ-805"; do
  CACHE="$(new_cache "variant-$variant")"
  make_task_dir "$CACHE" "PROJ-805"
  clean "$CACHE" "$variant"
  if [ -d "$CACHE/PROJ-805" ] && [ -f "$CACHE/PROJ-805/blackboard.json" ]; then
    ok "key '$variant' does not delete directory 'PROJ-805'"
  else
    bad "key '$variant' does not delete directory 'PROJ-805'" \
        "the directory is gone — rc=$CLEAN_RC out=$CLEAN_OUT"
  fi
  if [ "$CLEAN_RC" -ne 0 ] && contains "$CLEAN_OUT" "PROJ-805"; then
    ok "key '$variant' refuses loudly and names the directory it would not touch"
  else
    bad "key '$variant' refuses loudly and names the directory it would not touch" \
        "rc=$CLEAN_RC out=$CLEAN_OUT"
  fi
done

# ---------------------------------------------------------------------------
sec "Reported paths are truthful"
# ---------------------------------------------------------------------------
# The pre-fix code printed `removed: <cache>/bpf-805` — a path that had never
# existed on disk. A cleanup log naming a path that was never there makes the
# incident unreconstructable afterwards.

CACHE="$(new_cache truthful)"
make_task_dir "$CACHE" "PROJ-806"
clean "$CACHE" "proj-806"
if ! contains "$CLEAN_OUT" "removed:"; then
  ok "a refused cleanup never reports a removal"
else
  bad "a refused cleanup never reports a removal" "out=$CLEAN_OUT"
fi

CACHE="$(new_cache truthful2)"
make_task_dir "$CACHE" "proj-807"
clean "$CACHE" "proj-807"
if contains "$CLEAN_OUT" "removed:" && contains "$CLEAN_OUT" "proj-807"; then
  ok "a real removal reports the path that actually existed"
else
  bad "a real removal reports the path that actually existed" "out=$CLEAN_OUT"
fi

# ---------------------------------------------------------------------------
sec "Reserved and malformed keys refuse"
# ---------------------------------------------------------------------------
# `_projects/` holds every project's durable memory and `_org/` holds org
# memory. Neither is task scratch, and a cleanup that reached either would
# destroy the Company Brain rather than a task.

for reserved in "_projects" "_org"; do
  CACHE="$(new_cache "reserved-$reserved")"
  mkdir -p "$CACHE/$reserved"
  printf 'durable\n' > "$CACHE/$reserved/memory.md"
  clean "$CACHE" "$reserved"
  if [ "$CLEAN_RC" -ne 0 ] && [ -f "$CACHE/$reserved/memory.md" ]; then
    ok "reserved key '$reserved' is refused and its contents survive"
  else
    bad "reserved key '$reserved' is refused and its contents survive" "rc=$CLEAN_RC out=$CLEAN_OUT"
  fi
done

for malformed in "../escape" "a/b" ".." "." ""; do
  CACHE="$(new_cache "malformed")"
  clean "$CACHE" "$malformed"
  if [ "$CLEAN_RC" -ne 0 ]; then
    ok "malformed key '$malformed' is refused"
  else
    bad "malformed key '$malformed' is refused" "rc=$CLEAN_RC out=$CLEAN_OUT"
  fi
done

# ---------------------------------------------------------------------------
sec "Cleanup cannot escape the cache root"
# ---------------------------------------------------------------------------

CACHE="$(new_cache symlink)"
VICTIM="$BOX/victim-tree"
mkdir -p "$VICTIM"
printf 'irreplaceable\n' > "$VICTIM/keep.txt"
ln -s "$VICTIM" "$CACHE/proj-808"
clean "$CACHE" "proj-808"
if [ -f "$VICTIM/keep.txt" ]; then
  ok "a symlinked task directory does not delete its target"
else
  bad "a symlinked task directory does not delete its target" "rc=$CLEAN_RC out=$CLEAN_OUT"
fi

CACHE="$(new_cache repo)"
mkdir -p "$CACHE/proj-809/.git"
printf 'ref\n' > "$CACHE/proj-809/.git/HEAD"
clean "$CACHE" "proj-809"
if [ "$CLEAN_RC" -ne 0 ] && [ -d "$CACHE/proj-809/.git" ]; then
  ok "a directory containing a git repository is never recursively deleted"
else
  bad "a directory containing a git repository is never recursively deleted" \
      "rc=$CLEAN_RC out=$CLEAN_OUT"
fi

# ---------------------------------------------------------------------------
sec "Phased-plan preservation is unchanged"
# ---------------------------------------------------------------------------
# Existing contract: when a plan is present, cleanup keeps `phased-plan/` and
# `destination.md` so the next phase can resume, and clears the rest.

CACHE="$(new_cache plan)"
mkdir -p "$CACHE/proj-810/phased-plan"
printf '# index\n' > "$CACHE/proj-810/phased-plan/README.md"
printf '# destination\n' > "$CACHE/proj-810/destination.md"
printf '{}\n' > "$CACHE/proj-810/blackboard.json"
mkdir -p "$CACHE/proj-810/scratch-dir"
clean "$CACHE" "proj-810"
if [ -f "$CACHE/proj-810/phased-plan/README.md" ] && [ -f "$CACHE/proj-810/destination.md" ]; then
  ok "plan index and destination brief survive cleanup"
else
  bad "plan index and destination brief survive cleanup" "rc=$CLEAN_RC out=$CLEAN_OUT"
fi
if [ ! -f "$CACHE/proj-810/blackboard.json" ] && [ ! -d "$CACHE/proj-810/scratch-dir" ]; then
  ok "per-phase scratch is still cleared around a preserved plan"
else
  bad "per-phase scratch is still cleared around a preserved plan" "rc=$CLEAN_RC out=$CLEAN_OUT"
fi

CACHE="$(new_cache plan-variant)"
mkdir -p "$CACHE/PROJ-811/phased-plan"
printf '# index\n' > "$CACHE/PROJ-811/phased-plan/README.md"
printf '{}\n' > "$CACHE/PROJ-811/blackboard.json"
clean "$CACHE" "proj-811"
if [ -f "$CACHE/PROJ-811/blackboard.json" ]; then
  ok "a case-variant key does not clear scratch around someone else's plan"
else
  bad "a case-variant key does not clear scratch around someone else's plan" \
      "rc=$CLEAN_RC out=$CLEAN_OUT"
fi

# ---------------------------------------------------------------------------
sec "A refused cleanup does not fail the closeout"
# ---------------------------------------------------------------------------
# Cleanup fails closed, which is right. But by the time it runs, memory and
# telemetry are already written — the durable work is done and only scratch is
# left. Failing the whole closeout over undeleted scratch would report a lost
# task when nothing was lost, and would do it on EVERY task for anyone holding a
# cache directory created before issue keys were normalised.

FT="$REPO/scripts/finish-task.sh"
CACHE="$(new_cache closeout)"
make_task_dir "$CACHE" "PROJ-901"
FT_OUT="$(AGENT_SKILLS_CACHE_DIR="$CACHE" bash "$FT" demo PROJ-901 \
  --summary "closeout against a legacy-cased directory" 2>&1)"
FT_RC=$?

if [ "$FT_RC" -eq 0 ]; then
  ok "a refused cleanup still reports a successful closeout"
else
  bad "a refused cleanup still reports a successful closeout" "rc=$FT_RC"
fi
if contains "$FT_OUT" "PROJ-901" && contains "$FT_OUT" "NOT removed"; then
  ok "the refusal is surfaced rather than swallowed"
else
  bad "the refusal is surfaced rather than swallowed" "$FT_OUT"
fi
if [ -f "$CACHE/PROJ-901/blackboard.json" ]; then
  ok "the scratch it declined to delete is still there"
else
  bad "the scratch it declined to delete is still there"
fi
if grep -rq "proj-901" "$CACHE/_projects" 2>/dev/null; then
  ok "durable memory was written before cleanup was attempted"
else
  bad "durable memory was written before cleanup was attempted"
fi

CACHE="$(new_cache closeout-ok)"
make_task_dir "$CACHE" "proj-902"
AGENT_SKILLS_CACHE_DIR="$CACHE" bash "$FT" demo proj-902 \
  --summary "ordinary closeout" >/dev/null 2>&1
FT_RC=$?
if [ "$FT_RC" -eq 0 ] && [ ! -d "$CACHE/proj-902" ]; then
  ok "an ordinary closeout still removes its scratch and exits zero"
else
  bad "an ordinary closeout still removes its scratch and exits zero" \
      "rc=$FT_RC, dir present=$([ -d "$CACHE/proj-902" ] && echo yes || echo no)"
fi

# ---------------------------------------------------------------------------
sec "Incremental progress survives an interrupted run"
# ---------------------------------------------------------------------------
# A long execution that is killed must leave behind what it had already learned.
# Before the progress ledger existed, an agent that ran for an hour and was then
# terminated left nothing at all, so the retry restarted from zero.

CACHE="$(new_cache progress)"
"$PYTHON3" "$BB" --cache-root "$CACHE" init --project demo proj-812 >/dev/null 2>&1
"$PYTHON3" "$BB" --cache-root "$CACHE" progress proj-812 --by issue-investigator \
  --kind hypothesis --note "connection pool exhaustion suspected" >/dev/null 2>&1
PROGRESS_RC=$?
"$PYTHON3" "$BB" --cache-root "$CACHE" progress proj-812 --by issue-investigator \
  --kind query --note "counted rows in the failed-payment table" >/dev/null 2>&1

if [ "$PROGRESS_RC" -eq 0 ]; then
  ok "progress milestones can be recorded"
else
  bad "progress milestones can be recorded" "rc=$PROGRESS_RC"
fi

# No finish-task runs: this is the crash case.
READBACK="$("$PYTHON3" "$BB" --cache-root "$CACHE" read proj-812 2>&1)"
if contains "$READBACK" "connection pool exhaustion" && contains "$READBACK" "failed-payment"; then
  ok "recorded milestones survive a run that never reached finish-task"
else
  bad "recorded milestones survive a run that never reached finish-task" "$READBACK"
fi

# A blocked closeout preserves scratch, so the milestones stay readable.
"$PYTHON3" "$PM" --cache-root "$CACHE" cleanup-task proj-812 >/dev/null 2>&1
if [ ! -f "$CACHE/proj-812/blackboard.json" ]; then
  ok "a clean closeout still clears the ledger with the rest of the scratch"
else
  bad "a clean closeout still clears the ledger with the rest of the scratch"
fi

# ---------------------------------------------------------------------------
sec "Cleanup keeps what someone still has to read"
# ---------------------------------------------------------------------------
# A dispatched agent wrote its report into the task directory, closed out as
# `complete`, and the closeout deleted the report before the agent that
# dispatched it could verify anything. And around a phased plan the evidence
# pack — the only place each phase's `follow_up_context` lives — was cleared
# between phases, so no later phase could be told what an earlier one learned.

CACHE="$(new_cache keep-artifacts)"
make_task_dir "$CACHE" "proj-820"
mkdir -p "$CACHE/proj-820/artifacts"
printf '# audit\n' > "$CACHE/proj-820/artifacts/ux-audit.md"
clean "$CACHE" "proj-820"
if [ -f "$CACHE/proj-820/artifacts/ux-audit.md" ]; then
  ok "artifacts/ survives a clean closeout"
else
  bad "artifacts/ survives a clean closeout" "rc=$CLEAN_RC out=$CLEAN_OUT"
fi
if [ ! -f "$CACHE/proj-820/blackboard.json" ] && [ ! -f "$CACHE/proj-820/findings.md" ]; then
  ok "the scratch around artifacts/ is still cleared"
else
  bad "the scratch around artifacts/ is still cleared" "rc=$CLEAN_RC out=$CLEAN_OUT"
fi
if contains "$CLEAN_OUT" "kept: artifacts"; then
  ok "cleanup says what it kept"
else
  bad "cleanup says what it kept" "$CLEAN_OUT"
fi

CACHE="$(new_cache keep-pack)"
mkdir -p "$CACHE/proj-821/phased-plan"
printf '# index\n' > "$CACHE/proj-821/phased-plan/README.md"
printf 'delivery_plan:\n  phases: []\n' > "$CACHE/proj-821/evidence-pack.yml"
printf '{}\n' > "$CACHE/proj-821/blackboard.json"
clean "$CACHE" "proj-821"
if [ -f "$CACHE/proj-821/evidence-pack.yml" ] && [ ! -f "$CACHE/proj-821/blackboard.json" ]; then
  ok "the evidence pack survives between phases of a plan; the blackboard does not"
else
  bad "the evidence pack survives between phases of a plan; the blackboard does not" \
      "rc=$CLEAN_RC out=$CLEAN_OUT"
fi

CACHE="$(new_cache no-plan-pack)"
make_task_dir "$CACHE" "proj-822"
printf 'x: 1\n' > "$CACHE/proj-822/evidence-pack.yml"
clean "$CACHE" "proj-822"
if [ ! -d "$CACHE/proj-822" ]; then
  ok "without a plan or artifacts the whole task directory still goes"
else
  bad "without a plan or artifacts the whole task directory still goes" "rc=$CLEAN_RC out=$CLEAN_OUT"
fi

# ---------------------------------------------------------------------------
sec "finish-task names the task the way start-task does"
# ---------------------------------------------------------------------------
# The ambiguity refusal told agents to pass `--issue-key`, and finish-task had no
# such option: the only form it accepted was positional. An agent that followed
# the error message got a second error.

FT="$REPO/scripts/finish-task.sh"
CACHE="$(new_cache flags)"
"$PYTHON3" "$BB" --cache-root "$CACHE" init --project demo proj-830 >/dev/null 2>&1
"$PYTHON3" "$BB" --cache-root "$CACHE" init --project demo proj-831 >/dev/null 2>&1
FT_OUT="$(AGENT_SKILLS_CACHE_DIR="$CACHE" bash "$FT" --project demo --no-candidates \
  --summary "implicit closeout with two tasks in flight" 2>&1)"
FT_RC=$?
if [ "$FT_RC" -eq 3 ] && contains "$FT_OUT" "--issue-key <key>"; then
  ok "the ambiguity refusal still refuses, and names a flag"
else
  bad "the ambiguity refusal still refuses, and names a flag" "rc=$FT_RC out=$FT_OUT"
fi
FT_OUT="$(AGENT_SKILLS_CACHE_DIR="$CACHE" bash "$FT" --project demo --issue-key proj-830 \
  --no-candidates --summary "explicit closeout" 2>&1)"
FT_RC=$?
if [ "$FT_RC" -eq 0 ] && contains "$FT_OUT" "issue-key: proj-830"; then
  ok "the flag the refusal names is accepted"
else
  bad "the flag the refusal names is accepted" "rc=$FT_RC out=$FT_OUT"
fi
FT_OUT="$(AGENT_SKILLS_CACHE_DIR="$CACHE" bash "$FT" --task=proj-831 --project=demo \
  --no-candidates --summary "equals form" 2>&1)"
FT_RC=$?
if [ "$FT_RC" -eq 0 ] && contains "$FT_OUT" "issue-key: proj-831"; then
  ok "--task and the = forms work too"
else
  bad "--task and the = forms work too" "rc=$FT_RC out=$FT_OUT"
fi

CACHE="$(new_cache leftovers)"
mkdir -p "$CACHE/proj-832/artifacts" "$CACHE/proj-833/phased-plan"
printf 'r\n' > "$CACHE/proj-832/artifacts/report.md"
printf '# i\n' > "$CACHE/proj-833/phased-plan/README.md"
"$PYTHON3" "$BB" --cache-root "$CACHE" init --project demo proj-834 >/dev/null 2>&1
printf 'project=demo\nissue_key=proj-834\n' > "$CACHE/.last-task-context"
FT_OUT="$(AGENT_SKILLS_CACHE_DIR="$CACHE" bash "$FT" --no-candidates \
  --summary "one task running beside kept artifacts" 2>&1)"
FT_RC=$?
if [ "$FT_RC" -eq 0 ] && contains "$FT_OUT" "issue-key: proj-834"; then
  ok "directories holding only kept artifacts are not counted as tasks in flight"
else
  bad "directories holding only kept artifacts are not counted as tasks in flight" "rc=$FT_RC out=$FT_OUT"
fi

# ---------------------------------------------------------------------------
sec "A step inside a coordinated run leaves scratch to the coordinator"
# ---------------------------------------------------------------------------

CACHE="$(new_cache coordinated)"
"$PYTHON3" "$BB" --cache-root "$CACHE" init --project demo proj-840 \
  --skill wamala=1.1.0 >/dev/null 2>&1
printf 'delivery_plan: {}\n' > "$CACHE/proj-840/evidence-pack.yml"
FT_OUT="$(AGENT_SKILLS_CACHE_DIR="$CACHE" bash "$FT" demo proj-840 --skill software-engineer \
  --no-candidates --summary "step one done" 2>&1)"
FT_RC=$?
if [ "$FT_RC" -eq 0 ] && [ -f "$CACHE/proj-840/evidence-pack.yml" ] && contains "$FT_OUT" "wamala run"; then
  ok "a step's complete closeout keeps the evidence the coordinator verifies"
else
  bad "a step's complete closeout keeps the evidence the coordinator verifies" "rc=$FT_RC out=$FT_OUT"
fi
AGENT_SKILLS_CACHE_DIR="$CACHE" bash "$FT" demo proj-840 --skill wamala \
  --no-candidates --summary "run finished" >/dev/null 2>&1
if [ ! -d "$CACHE/proj-840" ]; then
  ok "the coordinator's own closeout cleans the run's scratch"
else
  bad "the coordinator's own closeout cleans the run's scratch"
fi

CACHE="$(new_cache coordinated-force)"
"$PYTHON3" "$BB" --cache-root "$CACHE" init --project demo proj-841 \
  --skill delivery-runner=1.1.0 >/dev/null 2>&1
AGENT_SKILLS_CACHE_DIR="$CACHE" bash "$FT" demo proj-841 --skill product-owner --cleanup \
  --no-candidates --summary "forced" >/dev/null 2>&1
if [ ! -d "$CACHE/proj-841" ]; then
  ok "--cleanup still forces cleanup inside a coordinated run"
else
  bad "--cleanup still forces cleanup inside a coordinated run"
fi

CACHE="$(new_cache not-coordinated)"
"$PYTHON3" "$BB" --cache-root "$CACHE" init --project demo proj-842 \
  --skill software-engineer=1.1.0 >/dev/null 2>&1
printf '{"issue_key": "proj-842", "skill_versions": {"software-engineer": "1.1.0"}, "facts": [{"text": "wamala routed this"}]}\n' \
  > "$CACHE/proj-842/blackboard.json"
AGENT_SKILLS_CACHE_DIR="$CACHE" bash "$FT" demo proj-842 --skill software-engineer \
  --no-candidates --summary "ordinary" >/dev/null 2>&1
if [ ! -d "$CACHE/proj-842" ]; then
  ok "a note that mentions a coordinator does not make a run coordinated"
else
  bad "a note that mentions a coordinator does not make a run coordinated"
fi

# ---------------------------------------------------------------------------
sec "Every helper finds the same cache"
# ---------------------------------------------------------------------------
# The wrappers anchored the cache at the git root and most Python helpers at the
# current directory, so `agent-skills blackboard progress` run from `src/` could
# not find the blackboard start-task had just created.

WS="$BOX/ws-git"
mkdir -p "$WS/src/deep"
git -C "$WS" init -q >/dev/null 2>&1
( cd "$WS" && env -u AGENT_SKILLS_CACHE_DIR -u WORKSPACE_ROOT \
    "$PYTHON3" "$BB" init --project demo proj-850 >/dev/null 2>&1 )
NESTED="$( cd "$WS/src/deep" && env -u AGENT_SKILLS_CACHE_DIR -u WORKSPACE_ROOT \
    "$PYTHON3" "$BB" read proj-850 2>&1 )"
if contains "$NESTED" '"issue_key": "proj-850"'; then
  ok "a Python helper run from a nested directory reads the git-root cache"
else
  bad "a Python helper run from a nested directory reads the git-root cache" "$NESTED"
fi
SHELL_ROOT="$( cd "$WS/src/deep" && env -u AGENT_SKILLS_CACHE_DIR -u WORKSPACE_ROOT \
    bash -c 'source "$1/scripts/task-context.sh"; agent_skills_resolve_cache_root' _ "$REPO" )"
PY_ROOT="$( cd "$WS/src/deep" && env -u AGENT_SKILLS_CACHE_DIR -u WORKSPACE_ROOT \
    "$PYTHON3" "$REPO/scripts/cache_root.py" )"
SHELL_REAL="$(cd "$(dirname "$SHELL_ROOT")/.." 2>/dev/null && pwd -P)"
PY_REAL="$(cd "$(dirname "$PY_ROOT")/.." 2>/dev/null && pwd -P)"
if [ -n "$SHELL_REAL" ] && [ "$SHELL_REAL" = "$PY_REAL" ] \
   && [ "$SHELL_REAL" = "$(cd "$WS" && pwd -P)" ]; then
  ok "the shell and Python resolvers agree on the git root"
else
  bad "the shell and Python resolvers agree on the git root" "shell=$SHELL_ROOT python=$PY_ROOT"
fi

WS="$BOX/ws-plain"
mkdir -p "$WS/docs/old" "$WS/.cache/agent-skills"
printf 'project=ws-plain\nissue_key=proj-851\n' > "$WS/.cache/agent-skills/.last-task-context"
SH_SUB="$( cd "$WS/docs/old" && env -u AGENT_SKILLS_CACHE_DIR -u WORKSPACE_ROOT \
    bash -c 'source "$1/scripts/task-context.sh"; agent_skills_resolve_cache_root' _ "$REPO" )"
SH_PROJECT="$( cd "$WS/docs/old" && env -u AGENT_SKILLS_CACHE_DIR -u WORKSPACE_ROOT \
    -u AGENT_SKILLS_PROJECT -u PROJECTS_JSON \
    bash -c 'source "$1/scripts/task-context.sh"; agent_skills_detect_project' _ "$REPO" )"
if contains "$SH_SUB" "ws-plain/.cache/agent-skills" && [ "$SH_PROJECT" = "ws-plain" ]; then
  ok "outside git, a subdirectory resolves the workspace that already has a cache"
else
  bad "outside git, a subdirectory resolves the workspace that already has a cache" \
      "cache=$SH_SUB project=$SH_PROJECT"
fi
PY_SUB="$( cd "$WS/docs/old" && env -u AGENT_SKILLS_CACHE_DIR -u WORKSPACE_ROOT \
    "$PYTHON3" "$REPO/scripts/cache_root.py" )"
if contains "$PY_SUB" "ws-plain/.cache/agent-skills"; then
  ok "the Python resolver takes the same anchor"
else
  bad "the Python resolver takes the same anchor" "$PY_SUB"
fi

# ---------------------------------------------------------------------------
sec "Delete-shaped requests: reversibility is checked, not assumed"
# ---------------------------------------------------------------------------

REV="$REPO/scripts/reversibility.py"
RV="$BOX/rev"
mkdir -p "$RV/plain/old-docs" "$RV/repo/docs" "$RV/repo/notes"
printf 'old\n' > "$RV/plain/old-docs/a.md"
git -C "$RV/repo" init -q >/dev/null 2>&1
printf 'a\n' > "$RV/repo/docs/a.md"
printf 'n\n' > "$RV/repo/notes/n.md"
printf '*.log\n' > "$RV/repo/.gitignore"
git -C "$RV/repo" add . >/dev/null 2>&1
git -C "$RV/repo" -c user.name=t -c user.email=t@example.invalid commit -qm init >/dev/null 2>&1
printf 'fresh\n' > "$RV/repo/notes/untracked.md"
printf 'l\n' > "$RV/repo/docs/build.log"

rev_verdict() {
  "$PYTHON3" "$REV" --json "$1" 2>/dev/null \
    | "$PYTHON3" -c 'import json,sys; print(json.load(sys.stdin)["targets"][0]["verdict"])'
}
"$PYTHON3" "$REV" "$RV/plain/old-docs" >/dev/null 2>&1
REV_RC=$?
if [ "$REV_RC" -eq 1 ] && [ "$(rev_verdict "$RV/plain/old-docs")" = "NOT_RECOVERABLE" ]; then
  ok "a directory outside any repository is not recoverable (exit 1)"
else
  bad "a directory outside any repository is not recoverable (exit 1)" "rc=$REV_RC"
fi
if [ -f "$RV/plain/old-docs/a.md" ]; then
  ok "the check never touches the target"
else
  bad "the check never touches the target"
fi
if [ "$(rev_verdict "$RV/repo/notes")" = "NOT_RECOVERABLE" ]; then
  ok "an untracked file beneath a tracked directory makes it not recoverable"
else
  bad "an untracked file beneath a tracked directory makes it not recoverable"
fi
if [ "$(rev_verdict "$RV/repo/docs")" = "NOT_RECOVERABLE" ]; then
  ok "an ignored file beneath a tracked directory makes it not recoverable"
else
  bad "an ignored file beneath a tracked directory makes it not recoverable"
fi
"$PYTHON3" "$REV" "$RV/repo/docs/a.md" >/dev/null 2>&1
REV_RC=$?
if [ "$REV_RC" -eq 0 ] && [ "$(rev_verdict "$RV/repo/docs/a.md")" = "RECOVERABLE" ]; then
  ok "a tracked, committed, unmodified file is recoverable (exit 0)"
else
  bad "a tracked, committed, unmodified file is recoverable (exit 0)" "rc=$REV_RC"
fi
if [ "$(rev_verdict "$RV/repo")" = "NOT_RECOVERABLE" ]; then
  ok "a repository root is never recoverable from its own history"
else
  bad "a repository root is never recoverable from its own history"
fi
REV_TEXT="$("$PYTHON3" "$REV" "$RV/plain/old-docs" 2>&1)"
if contains "$REV_TEXT" "mv -n" && contains "$REV_TEXT" "rm -r" && contains "$REV_TEXT" "_archive"; then
  ok "a not-recoverable target comes with archive commands and the user's delete command"
else
  bad "a not-recoverable target comes with archive commands and the user's delete command" "$REV_TEXT"
fi
printf 'edit\n' >> "$RV/repo/docs/a.md"
if [ "$(rev_verdict "$RV/repo/docs/a.md")" = "NOT_RECOVERABLE" ]; then
  ok "an uncommitted edit makes a tracked file not recoverable"
else
  bad "an uncommitted edit makes a tracked file not recoverable"
fi

# ---------------------------------------------------------------------------
sec "Mutation probes"
# ---------------------------------------------------------------------------
# Each probe removes one guarantee from a sandboxed copy and asserts the check
# that covers it then fails. A probe that passes against the weakened build is
# proving nothing.

PROBE_DIR="$BOX/probe"
mkdir -p "$PROBE_DIR"
cp "$PM" "$PROBE_DIR/project-memory.py"
# The sandbox needs every module project-memory imports. Without them the
# weakened build dies on import, refuses everything, and the probe reads as "the
# guard held" when in fact nothing ran.
cp "$REPO/scripts/guard_audit.py" "$PROBE_DIR/guard_audit.py"
cp "$REPO/scripts/durable.py" "$PROBE_DIR/durable.py"
cp "$REPO/scripts/cache_root.py" "$PROBE_DIR/cache_root.py"

# Probe 1: restore the pre-fix `exists()`-driven deletion.
python3 - "$PROBE_DIR/project-memory.py" <<'PY'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
# Replace the resolved-entry lookup with the original permissive one.
weakened = re.sub(
    r"    target = _resolve_task_dir\(cache_root, issue_key\)\n",
    "    target = cache_root / issue_key\n    if not target.exists():\n        return None\n",
    text,
)
if weakened == text:
    sys.stderr.write("probe could not weaken the build\n")
    sys.exit(3)
path.write_text(weakened, encoding="utf-8")
PY
PROBE_PREP=$?

if [ "$PROBE_PREP" -ne 0 ]; then
  bad "probe 1 could weaken the build" "the anchor _resolve_task_dir( was not found"
else
  CACHE="$(new_cache probe1)"
  make_task_dir "$CACHE" "PROJ-805"
  "$PYTHON3" "$PROBE_DIR/project-memory.py" --cache-root "$CACHE" cleanup-task proj-805 \
    >/dev/null 2>&1
  if [ "$CASE_INSENSITIVE" -eq 1 ]; then
    if [ ! -d "$CACHE/PROJ-805" ]; then
      ok "probe 1: without the resolved-entry lookup the wrong directory is deleted"
    else
      bad "probe 1: without the resolved-entry lookup the wrong directory is deleted" \
          "the weakened build did not reproduce the defect, so the guard is untested"
    fi
  else
    ok "probe 1: skipped — this filesystem is case-sensitive, the defect needs folding"
  fi
fi

# Probe 2: remove the repository-ownership refusal and confirm a directory
# holding a git repository is then deleted.
#
# The symlink guard deliberately has no probe. `shutil.rmtree` refuses a symlink
# on its own, so removing the explicit check does not change what survives — the
# check earns its place by turning an unhandled OSError into a message that says
# which path was refused and why, not by being the only thing standing there.
cp "$PM" "$PROBE_DIR/project-memory.py"
# The sandbox needs every module project-memory imports. Without them the
# weakened build dies on import, refuses everything, and the probe reads as "the
# guard held" when in fact nothing ran.
cp "$REPO/scripts/guard_audit.py" "$PROBE_DIR/guard_audit.py"
cp "$REPO/scripts/durable.py" "$PROBE_DIR/durable.py"
cp "$REPO/scripts/cache_root.py" "$PROBE_DIR/cache_root.py"
python3 - "$PROBE_DIR/project-memory.py" <<'PY'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
weakened, count = re.subn(
    r'    if \(target / "\.git"\)\.exists\(\):\n(?:        .*\n)+?        \)\n',
    "",
    text,
    count=1,
)
if count == 0:
    sys.stderr.write("probe could not weaken the build\n")
    sys.exit(3)
path.write_text(weakened, encoding="utf-8")
PY
PROBE_PREP=$?

if [ "$PROBE_PREP" -ne 0 ]; then
  bad "probe 2 could weaken the build" "the repository-ownership guard was not found"
else
  CACHE="$(new_cache probe2)"
  mkdir -p "$CACHE/proj-813/.git"
  printf 'ref\n' > "$CACHE/proj-813/.git/HEAD"
  "$PYTHON3" "$PROBE_DIR/project-memory.py" --cache-root "$CACHE" cleanup-task proj-813 \
    >/dev/null 2>&1
  if [ ! -d "$CACHE/proj-813" ]; then
    ok "probe 2: without the ownership guard a repository directory is deleted"
  else
    bad "probe 2: without the ownership guard a repository directory is deleted" \
        "the weakened build still refused, so the guard is untested"
  fi
fi

# Probe 3: drop `artifacts` from what cleanup keeps, and a finished step's report
# is deleted again.
cp "$PM" "$PROBE_DIR/project-memory.py"
"$PYTHON3" - "$PROBE_DIR/project-memory.py" <<'PY'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
weakened = text.replace('ALWAYS_KEPT = ("artifacts",)', "ALWAYS_KEPT = ()", 1)
if weakened == text:
    sys.exit(3)
path.write_text(weakened, encoding="utf-8")
PY
if [ $? -ne 0 ]; then
  bad "probe 3 could weaken the build" "ALWAYS_KEPT was not found"
else
  CACHE="$(new_cache probe3)"
  make_task_dir "$CACHE" "proj-860"
  mkdir -p "$CACHE/proj-860/artifacts"
  printf 'r\n' > "$CACHE/proj-860/artifacts/report.md"
  "$PYTHON3" "$PROBE_DIR/project-memory.py" --cache-root "$CACHE" cleanup-task proj-860 \
    >/dev/null 2>&1
  if [ ! -f "$CACHE/proj-860/artifacts/report.md" ]; then
    ok "probe 3: without the keep rule a finished step's report is deleted"
  else
    bad "probe 3: without the keep rule a finished step's report is deleted" \
        "the weakened build kept it, so the keep test proves nothing"
  fi
fi

# Probe 4: remove the coordinated-run check, and a step deletes the evidence the
# coordinator was about to verify.
PROBE_SCRIPTS="$BOX/probe-scripts"
mkdir -p "$PROBE_SCRIPTS"
cp "$REPO"/scripts/*.sh "$REPO"/scripts/*.py "$PROBE_SCRIPTS/"
"$PYTHON3" - "$PROBE_SCRIPTS/finish-task.sh" <<'PY'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
anchor = '  if [[ -n "${COORDINATOR}" ]]; then\n    CLEANUP="false"\n  fi\n'
if anchor not in text:
    sys.exit(3)
path.write_text(text.replace(anchor, "", 1), encoding="utf-8")
PY
if [ $? -ne 0 ]; then
  bad "probe 4 could weaken the build" "the coordinated-run check was not found"
else
  CACHE="$(new_cache probe4)"
  "$PYTHON3" "$BB" --cache-root "$CACHE" init --project demo proj-861 \
    --skill wamala=1.1.0 >/dev/null 2>&1
  printf 'delivery_plan: {}\n' > "$CACHE/proj-861/evidence-pack.yml"
  AGENT_SKILLS_CACHE_DIR="$CACHE" bash "$PROBE_SCRIPTS/finish-task.sh" demo proj-861 \
    --skill software-engineer --no-candidates --summary "step" >/dev/null 2>&1
  if [ ! -f "$CACHE/proj-861/evidence-pack.yml" ]; then
    ok "probe 4: without the coordinated-run check a step deletes the coordinator's evidence"
  else
    bad "probe 4: without the coordinated-run check a step deletes the coordinator's evidence" \
        "the weakened build kept it, so the coordinated-run test proves nothing"
  fi
fi

# Probe 5: stop counting untracked content, and an untracked note reads as safe to
# delete.
cp "$REPO/scripts/reversibility.py" "$PROBE_DIR/reversibility.py"
"$PYTHON3" - "$PROBE_DIR/reversibility.py" <<'PY'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
anchor = "    elif untracked or ignored or changed:\n"
if anchor not in text:
    sys.exit(3)
path.write_text(text.replace(anchor, "    elif False:\n", 1), encoding="utf-8")
PY
if [ $? -ne 0 ]; then
  bad "probe 5 could weaken the build" "the untracked-content check was not found"
else
  GOT="$("$PYTHON3" "$PROBE_DIR/reversibility.py" --json "$RV/repo/notes" 2>/dev/null \
    | "$PYTHON3" -c 'import json,sys; print(json.load(sys.stdin)["targets"][0]["verdict"])')"
  if [ "$GOT" = "RECOVERABLE" ]; then
    ok "probe 5: without the untracked-content check an untracked note reads as recoverable"
  else
    bad "probe 5: without the untracked-content check an untracked note reads as recoverable" \
        "got $GOT, so the reversibility test proves nothing"
  fi
fi

# ---------------------------------------------------------------------------
printf '\n== summary ==\n'
printf '  passed: %d\n' "$PASS"
printf '  failed: %d\n' "$FAIL"
if [ "$FAIL" -ne 0 ]; then
  printf '\nLIFECYCLE_FS: FAIL\n'
  exit 1
fi
printf '\nLIFECYCLE_FS: PASS\n'
exit 0
