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
sec "Mutation probes"
# ---------------------------------------------------------------------------
# Each probe removes one guarantee from a sandboxed copy and asserts the check
# that covers it then fails. A probe that passes against the weakened build is
# proving nothing.

PROBE_DIR="$BOX/probe"
mkdir -p "$PROBE_DIR"
cp "$PM" "$PROBE_DIR/project-memory.py"
# The sandbox needs the redaction module too. Without it the weakened build dies
# on import, refuses everything, and the probe reads as "the guard held" when in
# fact nothing ran.
cp "$REPO/scripts/guard_audit.py" "$PROBE_DIR/guard_audit.py"

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
# The sandbox needs the redaction module too. Without it the weakened build dies
# on import, refuses everything, and the probe reads as "the guard held" when in
# fact nothing ran.
cp "$REPO/scripts/guard_audit.py" "$PROBE_DIR/guard_audit.py"
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
