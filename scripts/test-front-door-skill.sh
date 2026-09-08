#!/usr/bin/env bash
# Regression tests for the front-door skill's identity and contract.
#
# `wamala` is the single entry point to the skill catalogue. Two properties are
# easy to break by accident and expensive to notice late:
#
#   * There is exactly ONE discoverable front door. A rename that leaves the old
#     directory behind ships two entry points that drift apart silently.
#   * The rename did not quietly redesign the routing architecture underneath it.
#
# The second is checked by diffing the routing contract against the release the
# rename came from, not by grepping for words. When that tag is not fetched — a
# shallow CI clone — the comparison reports as skipped rather than passing.
#
# Usage: bash scripts/test-front-door-skill.sh [-v]
#
# Environment:
#   AGENT_SKILLS_RENAME_BASELINE_TAG   release the front door was renamed FROM (default v0.37.0)
#   AGENT_SKILLS_ROUTING_BASELINE_TAG  release the rename landed IN (default v0.38.0)
#
# Exit 0 when every case passes, 1 otherwise.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL_DIR="${REPO_ROOT}/skills/wamala"
SKILL_MD="${SKILL_DIR}/SKILL.md"
BASELINE_TAG="${AGENT_SKILLS_RENAME_BASELINE_TAG:-v0.37.0}"
BASELINE_SKILL="skills/tech-lead"
RENAMED_TAG="${AGENT_SKILLS_ROUTING_BASELINE_TAG:-v0.38.0}"
RENAMED_SKILL="skills/wamala"
VERBOSE="false"
[ "${1:-}" = "-v" ] && VERBOSE="true"

PASS=0
FAIL=0
SKIP=0
SANDBOXES=""

cleanup() {
  local box
  for box in ${SANDBOXES}; do
    [ -n "${box}" ] && rm -rf "${box}" 2>/dev/null
  done
}
trap cleanup EXIT

ok() { PASS=$((PASS + 1)); printf '  ok   %s\n' "$1"; }
bad() {
  FAIL=$((FAIL + 1))
  printf '  FAIL %s\n' "$1" >&2
  [ -n "${2:-}" ] && printf '       %s\n' "$2" >&2
}
skip() { SKIP=$((SKIP + 1)); printf '  skip %s (%s)\n' "$1" "$2"; }
section() { printf '\n== %s ==\n' "$1"; }

check() {
  local description="$1"
  shift
  if "$@" >/dev/null 2>&1; then ok "${description}"; else bad "${description}" "command failed: $*"; fi
}

sandbox() {
  local box
  box="$(mktemp -d)"
  SANDBOXES="${SANDBOXES} ${box}"
  printf '%s' "${box}"
}

# ------------------------------------------------------------------------------
section "identity"
# ------------------------------------------------------------------------------
check "skills/wamala/SKILL.md exists" test -f "${SKILL_MD}"

DECLARED_NAME="$(awk '/^name:[[:space:]]*/ { sub(/^name:[[:space:]]*/, ""); print; exit }' "${SKILL_MD}")"
if [ "${DECLARED_NAME}" = "wamala" ]; then
  ok "the declared name is exactly 'wamala'"
else
  bad "the declared name is exactly 'wamala'" "got '${DECLARED_NAME}'"
fi

HEADING="$(grep -m1 '^# ' "${SKILL_MD}")"
if [ "${HEADING}" = "# Wamala" ]; then
  ok "the human heading is 'Wamala'"
else
  bad "the human heading is 'Wamala'" "got '${HEADING}'"
fi

# The directory name and the declared name must agree: hosts register by
# directory, and the eval harness resolves by directory.
if [ "$(basename "${SKILL_DIR}")" = "${DECLARED_NAME}" ]; then
  ok "the directory name matches the declared name"
else
  bad "the directory name matches the declared name"
fi

# ------------------------------------------------------------------------------
section "exactly one front door"
# ------------------------------------------------------------------------------
if [ -e "${REPO_ROOT}/skills/tech-lead" ]; then
  bad "skills/tech-lead is not retained as a second skill directory"
else
  ok "skills/tech-lead is not retained as a second skill directory"
fi

DUPES="$(grep -rl '^name: tech-lead$' "${REPO_ROOT}/skills" 2>/dev/null || true)"
if [ -z "${DUPES}" ]; then
  ok "no SKILL.md anywhere declares the old name"
else
  bad "no SKILL.md anywhere declares the old name" "${DUPES}"
fi

TOP_LEVEL="$(find "${REPO_ROOT}/skills" -mindepth 2 -maxdepth 2 -name SKILL.md | wc -l | tr -d ' ')"
if [ "${TOP_LEVEL}" = "9" ]; then
  ok "nine top-level skills are registerable (${TOP_LEVEL})"
else
  bad "nine top-level skills are registerable" "found ${TOP_LEVEL}"
fi

# The specialists keep their role-based names. A rename that swept them up too
# would break every direct invocation in the wild.
for specialist in product-owner software-engineer manual-tester \
  test-automation-engineer delivery-planner delivery-runner domain-modeler \
  context-optimizer; do
  check "specialist '${specialist}' keeps its role-based name" \
    test -f "${REPO_ROOT}/skills/${specialist}/SKILL.md"
done
for nested in issue-investigator code-reviewer; do
  check "nested specialist '${nested}' keeps its role-based name" \
    test -f "${REPO_ROOT}/skills/software-engineer/skills/${nested}/SKILL.md"
done

# ------------------------------------------------------------------------------
section "routing contract survives later releases"
# ------------------------------------------------------------------------------
# Compare the machine-readable half of the contract — the routing rows and the
# chains — against every earlier release that shipped it, with the identity
# substituted.
#
# The rule is **ordered subsequence, not equality**. Routing gains rows
# deliberately: a release that teaches the router a new class adds rows, and
# forbidding that would freeze the table rather than protect it. What must never
# happen is a row silently losing its owner, disappearing, or MOVING, because
# the table is first-match-wins and its order is the semantics. So every
# baseline row must still be present, verbatim, and in the same relative order.
# An added row is reported, not failed.
#
# An earlier draft of this compared the two sets with `comm` on sorted input.
# That allowed additions, which was the point, but it also silently allowed
# reordering — and reordering the catch-all row above the boundary rows inverts
# exactly the ownership the boundary rows exist to protect. Set comparison is
# the wrong tool for an ordered contract.
routing_rows() {
  # Every table row in the file, name normalised, whitespace collapsed. Scanning
  # all tables rather than only the routing table is deliberate over-inclusion:
  # the class table and the chains table are contract too, and a check that
  # covers more than it must is the safe direction to err in.
  sed -n 's/^|/|/p' \
    | grep -v '^| *---' \
    | sed -e 's/tech-lead/wamala/g' -e 's/[[:space:]]\{1,\}/ /g'
}

# Rows carry a leading index in references/routing-table.md, and renumbering on
# insert is not a contract change. Compare on the part that is the contract:
# the condition, the owner, and the reason. Order is preserved by the caller.
routing_rows_unindexed() {
  routing_rows | sed -e 's/^| [0-9]\{1,\} |/|/'
}

# Print the baseline rows that are absent from the current table, or present but
# out of order. Exit non-zero when any is. Greedy single pass: for each baseline
# row in order, advance through the current rows until it is found. A row that
# moved earlier has already been passed by the time it is looked for, so it
# reports as missing — which is the intent.
ordered_subsequence_gaps() {
  awk 'NR==FNR { cur[++n] = $0; next }
       { base[++m] = $0 }
       END {
         i = 1; gaps = 0
         for (j = 1; j <= m; j++) {
           found = 0
           while (i <= n) {
             if (cur[i] == base[j]) { found = 1; i++; break }
             i++
           }
           if (!found) { print base[j]; gaps = 1 }
         }
         exit gaps
       }' "$2" "$1"
}

compare_routing_artifact() {
  local tag="$1" baseline_skill="$2" artifact="$3" before after missing added
  before="$(mktemp)"; after="$(mktemp)"
  git -C "${REPO_ROOT}" show "${tag}:${baseline_skill}/${artifact}" 2>/dev/null \
    | routing_rows_unindexed > "${before}"
  routing_rows_unindexed < "${SKILL_DIR}/${artifact}" > "${after}"
  if [ ! -s "${before}" ]; then
    bad "baseline ${artifact} at ${tag} has routing rows to compare"
    rm -f "${before}" "${after}"
    return
  fi
  missing="$(ordered_subsequence_gaps "${before}" "${after}")"
  added=$(( $(wc -l < "${after}") - $(wc -l < "${before}") ))
  if [ -z "${missing}" ]; then
    if [ "${added}" -gt 0 ] && [ "${VERBOSE}" = "true" ]; then
      printf '       (%s rows added since %s)\n' "${added}" "${tag}"
    fi
    ok "${artifact}: every routing row from ${tag} is still present, in order"
  else
    bad "${artifact}: routing rows lost or reordered since ${tag}" \
      "$(printf '%s\n' "${missing}" | head -8)"
  fi
  rm -f "${before}" "${after}"
}

# Ordered subsequence catches deletion, owner changes, and movement. It does not
# catch a row INSERTED ABOVE an existing one that shadows it — first-match-wins
# means the new row silently takes over while every baseline row is still
# present and in order. That is what these assertions are for: for each class,
# the owners of the rows mentioning it, in table order, must be exactly this.
# A shadowing insert changes the sequence; so does a reorder.
routing_table_rows() {
  # Numbered rows of references/routing-table.md only, so the owner is always
  # the third cell.
  sed -n 's/^| [0-9]\{1,\} |/|/p' "${SKILL_DIR}/references/routing-table.md" \
    | sed -e 's/[[:space:]]\{1,\}/ /g'
}

assert_class_owners() {
  local description="$1" token="$2" expected="$3" actual
  actual="$(routing_table_rows | grep -F -- "${token}" \
    | awk -F'|' '{ gsub(/^ +| +$/, "", $3); printf "%s ", $3 }' | sed -e 's/ $//')"
  if [ "${actual}" = "${expected}" ]; then
    ok "${description}"
  else
    bad "${description}" "expected: ${expected}
       got:      ${actual}"
  fi
}

if git -C "${REPO_ROOT}" rev-parse -q --verify "${BASELINE_TAG}^{commit}" >/dev/null 2>&1; then
  for artifact in SKILL.md references/routing-table.md; do
    compare_routing_artifact "${BASELINE_TAG}" "${BASELINE_SKILL}" "${artifact}"
  done

  # And the prose contract, minus the identity, must not have been rewritten
  # while the name was being changed.
  contract_body() {
    sed -e 's/tech-lead/wamala/g' -e 's/Tech Lead/Wamala/g' -e 's/[Tt]he lead/Wamala/g'
  }
  BEFORE_SECTIONS="$(git -C "${REPO_ROOT}" show "${BASELINE_TAG}:${BASELINE_SKILL}/SKILL.md" \
    2>/dev/null | grep '^## ')"
  AFTER_SECTIONS="$(grep '^## ' "${SKILL_MD}")"
  if [ "${BEFORE_SECTIONS}" = "${AFTER_SECTIONS}" ]; then
    ok "SKILL.md keeps exactly the section structure it had at ${BASELINE_TAG}"
  else
    bad "SKILL.md keeps exactly the section structure it had at ${BASELINE_TAG}" \
      "$(diff <(printf '%s\n' "${BEFORE_SECTIONS}") <(printf '%s\n' "${AFTER_SECTIONS}") | head -12)"
  fi
else
  skip "routing rows from ${BASELINE_TAG} are still present" "tag not fetched in this clone"
  skip "section structure is identical to ${BASELINE_TAG}" "tag not fetched in this clone"
fi

# The release that renamed the front door is a second baseline. Checking both
# means a row cannot be dropped in one release and its loss go unnoticed in the
# next, which comparing only against the immediately previous tag would allow.
if git -C "${REPO_ROOT}" rev-parse -q --verify "${RENAMED_TAG}^{commit}" >/dev/null 2>&1; then
  for artifact in SKILL.md references/routing-table.md; do
    compare_routing_artifact "${RENAMED_TAG}" "${RENAMED_SKILL}" "${artifact}"
  done
else
  skip "routing rows from ${RENAMED_TAG} are still present" "tag not fetched in this clone"
fi

# The bounds that make the router safe. Each is a distinct guarantee, so each is
# asserted separately rather than as one blob.
assert_contract() {
  local description="$1"
  local pattern="$2"
  if grep -qi -- "${pattern}" "${SKILL_MD}"; then
    ok "${description}"
  else
    bad "${description}" "no line matching: ${pattern}"
  fi
}
assert_contract "the requirement-understanding gate is still run before routing" \
  'Run the \[requirement-understanding workflow\]'
assert_contract "the gate's verdict still outranks the classification" \
  "confidence verdict outranks the classification"
assert_contract "dispatch is still fresh-context, not nested invocation" \
  'It opens a \*\*new agent whose context starts'
assert_contract "steps are still verified from artifacts, not chat" \
  "A chat summary is never proof"
assert_contract "a missing artifact is still retried exactly once" \
  "Retry \*\*once\*\*"
assert_contract "the depth cap of two is still preserved" \
  "depth cap of two"
assert_contract "one owner per dispatched step is still binding" \
  "One step per dispatch"
assert_contract "the dispatch cap still bounds a run" \
  "hard cap of \*\*six dispatches\*\*"
assert_contract "the safety floor is still inherited" \
  "destructive-action safety policy"
assert_contract "routing still never launders a forbidden request" \
  "Routing is not a laundering step"
assert_contract "direct specialist invocation is still first-class" \
  "Direct invocation of any skill stays"
assert_contract "an existing plan is still handed to delivery-runner" \
  "delivery-runner"
assert_contract "routing is still capability-aware" \
  "capability report"
assert_contract "stopping conditions are still enumerated" \
  "^## Stopping Conditions"

# Automation routing, added in v0.39.0. The ownership boundaries matter more than
# the destination row: a router that sends every red test to the automation
# engineer makes that skill absorb root-cause analysis and product decisions,
# which is the failure this class was added to avoid.
assert_contract "the automation class exists" \
  '^| `automation` | the automated test suite itself is the subject'
assert_contract "automation work routes to test-automation-engineer" \
  'runtime, backlog | `test-automation-engineer`'
assert_contract "an automation request with unagreed behaviour routes to product-owner" \
  'the behaviour to assert is not agreed | `product-owner`'
assert_contract "a failing test pointing at a product defect routes to issue-investigator" \
  'points at a product defect | `issue-investigator`'
assert_contract "an unstable scenario still routes to manual-tester" \
  'too unstable to assert | `manual-tester`'

# First-match-wins ordering, pinned per class. A row inserted above an existing
# one shadows it without removing it, so neither the subsequence check nor a
# substring grep can see it — only the ordered owner sequence can.
assert_class_owners "automation rows route boundaries first, catch-all last" \
  '`automation`' \
  '`product-owner` `issue-investigator` `manual-tester` `test-automation-engineer`'
assert_class_owners "no row shadows the review row" \
  '`review`' '`code-reviewer`'
assert_class_owners "defect rows still order investigation before implementation" \
  '`defect`' '`issue-investigator` `software-engineer`'
assert_class_owners "question rows still order behaviour before product intent" \
  '`question`' '`issue-investigator` `product-owner`'
assert_class_owners "validation rows still order manual before automated" \
  '`validation`' '`manual-tester` `test-automation-engineer`'

# Developer tests belong to the engineer who wrote the code. The row that says so
# names no class token, so none of the five sequences above can see it. Pin it
# directly: it must exist, be owned by software-engineer, and sit above the
# automation catch-all, because first-match-wins is what sends "write unit tests
# for the change I just made" to the engineer rather than to the suite owner.
DEV_TEST_ROW="$(routing_table_rows | grep -n -F -- 'Tests for a code change' || true)"
AUTOMATION_CATCHALL_ROW="$(routing_table_rows | grep -n -F -- 'runtime, or a backlog' || true)"
if [ -z "${DEV_TEST_ROW}" ]; then
  bad "a routing row owns the developer tests that ship with a change" "row not found"
elif ! printf '%s' "${DEV_TEST_ROW}" | grep -q -F -- '`software-engineer`'; then
  bad "developer tests route to software-engineer" "got: ${DEV_TEST_ROW}"
elif [ -z "${AUTOMATION_CATCHALL_ROW}" ]; then
  bad "the automation catch-all row is still present" "row not found"
elif [ "${DEV_TEST_ROW%%:*}" -ge "${AUTOMATION_CATCHALL_ROW%%:*}" ]; then
  bad "the developer-test row precedes the automation catch-all" \
    "developer-test row at ${DEV_TEST_ROW%%:*}, catch-all at ${AUTOMATION_CATCHALL_ROW%%:*}"
else
  ok "developer tests route to software-engineer, above the automation catch-all"
fi

# ------------------------------------------------------------------------------
section "lifecycle CLI accepts the skill"
# ------------------------------------------------------------------------------
LC="$(sandbox)"
mkdir -p "${LC}/repo" "${LC}/home"
( cd "${LC}/repo" && git init -q )
CACHE="${LC}/cache"

run_lifecycle() {
  local script="$1"
  shift
  ( cd "${LC}/repo" && env HOME="${LC}/home" \
      AGENT_SKILLS_CACHE_DIR="${CACHE}" \
      AGENT_SKILLS_CONFIG_DIR="${LC}/home/.config/agent-skills" \
      bash "${REPO_ROOT}/scripts/${script}" "$@" )
}

START_OUT="$(run_lifecycle start-task.sh demo demo-1 --no-org --skill wamala 2>&1)"
START_RC=$?
if [ "${START_RC}" -eq 0 ]; then
  ok "start-task --skill wamala exits 0"
else
  bad "start-task --skill wamala exits 0" "$(printf '%s' "${START_OUT}" | tail -5)"
fi
BB="$(python3 "${REPO_ROOT}/scripts/blackboard.py" --cache-root "${CACHE}" read demo-1 2>&1)"
if printf '%s' "${BB}" | grep -q 'wamala'; then
  ok "the blackboard records wamala as a participating skill"
else
  bad "the blackboard records wamala as a participating skill" "$(printf '%s' "${BB}" | head -5)"
fi

FINISH_OUT="$(run_lifecycle finish-task.sh demo demo-1 \
  --summary "front-door smoke test" --skill wamala --no-candidates 2>&1)"
FINISH_RC=$?
if [ "${FINISH_RC}" -eq 0 ]; then
  ok "finish-task --skill wamala exits 0"
else
  bad "finish-task --skill wamala exits 0" "$(printf '%s' "${FINISH_OUT}" | tail -5)"
fi
TELEMETRY="$(find "${CACHE}" -name telemetry.ndjson -exec cat {} + 2>/dev/null)"
if printf '%s' "${TELEMETRY}" | grep -q '"skill": *"wamala"'; then
  ok "telemetry attributes the run to wamala"
else
  bad "telemetry attributes the run to wamala" "$(printf '%s' "${TELEMETRY}" | tail -2)"
fi

# ------------------------------------------------------------------------------
section "retired alias tech-lead (removed in v0.41.0)"
# ------------------------------------------------------------------------------
# `tech-lead` was renamed to `wamala` in v0.38.0 and carried as a lifecycle alias
# for three minor releases. v0.41.0 is the release the deprecation table named,
# so this section now verifies the REMOVAL rather than the alias.
#
# Before v0.41.0 this section asserted the opposite. Inverting it rather than
# deleting it is deliberate: the interesting property after a scheduled removal
# is that the old name is genuinely gone and is not silently translated to
# something else, which is a different bug from simply not working.
ALIAS="$(sandbox)"
mkdir -p "${ALIAS}/repo" "${ALIAS}/home"
( cd "${ALIAS}/repo" && git init -q )
ALIAS_CACHE="${ALIAS}/cache"

run_alias() {
  local script="$1"
  shift
  ( cd "${ALIAS}/repo" && env HOME="${ALIAS}/home" \
      AGENT_SKILLS_CACHE_DIR="${ALIAS_CACHE}" \
      AGENT_SKILLS_CONFIG_DIR="${ALIAS}/home/.config/agent-skills" \
      bash "${REPO_ROOT}/scripts/${script}" "$@" )
}

# The alias table is empty, so the retired name resolves to itself.
RETIRED="$( . "${REPO_ROOT}/scripts/task-context.sh"; \
  agent_skills_resolve_skill_name "tech-lead" 2>/dev/null )"
if [ "${RETIRED}" = "tech-lead" ]; then
  ok "the retired name is no longer translated"
else
  bad "the retired name is no longer translated" "got '${RETIRED}'"
fi

ALIAS_OUT="$(run_alias start-task.sh demo demo-2 --no-org --skill tech-lead 2>&1)"
if printf '%s' "${ALIAS_OUT}" | grep -q 'was renamed to'; then
  bad "start-task no longer prints a migration notice for the retired name" \
    "$(printf '%s' "${ALIAS_OUT}" | grep 'renamed' | head -3)"
else
  ok "start-task prints no migration notice for the retired name"
fi

# The retired name must not be silently remapped to the current one either. It is
# recorded as given, so an operator sees the name they actually passed.
ALIAS_BB="$(python3 "${REPO_ROOT}/scripts/blackboard.py" --cache-root "${ALIAS_CACHE}" \
  read demo-2 2>&1)"
if printf '%s' "${ALIAS_BB}" | grep -q 'tech-lead'; then
  ok "the retired name is recorded as given, not remapped to wamala"
else
  bad "the retired name is recorded as given" "$(printf '%s' "${ALIAS_BB}" | head -5)"
fi

# A name that is neither current nor deprecated must still pass through
# untouched, so an empty table cannot start swallowing typos.
UNKNOWN="$( . "${REPO_ROOT}/scripts/task-context.sh"; \
  agent_skills_resolve_skill_name "not-a-skill" 2>/dev/null )"
if [ "${UNKNOWN}" = "not-a-skill" ]; then
  ok "an unknown skill name passes through the alias table unchanged"
else
  bad "an unknown skill name passes through the alias table unchanged" "got '${UNKNOWN}'"
fi

# The removal is recorded where the addition was, so the schedule stays auditable.
if grep -q '| _(none)_ | | | |' "${REPO_ROOT}/docs/versioning.md"; then
  ok "the deprecation table records that no alias is currently carried"
else
  bad "the deprecation table records that no alias is carried" \
    "expected an empty row in docs/versioning.md"
fi
if grep -q 'v0.41.0' "${REPO_ROOT}/docs/versioning.md"; then
  ok "docs/versioning.md still records when the alias was removed"
else
  bad "docs/versioning.md records when the alias was removed"
fi

# ------------------------------------------------------------------------------
section "active documentation names the front door correctly"
# ------------------------------------------------------------------------------
# Historical material may — and should — still say `tech-lead`: release plans,
# past security reviews, and the deprecation registry in docs/versioning.md,
# which exists precisely to name the old name and when it goes away. Active
# docs, skills, examples, and evals may not.
ACTIVE_HITS="$(cd "${REPO_ROOT}" && git ls-files -- \
  'README.md' 'ROADMAP.md' 'docs/*.md' 'docs/examples/*.md' 'skills/**/*.md' 'evals/*.md' \
  | grep -v '^docs/plans/' \
  | grep -v '^docs/security-review-' \
  | grep -v '^docs/versioning.md$' \
  | xargs grep -ln 'tech-lead' 2>/dev/null || true)"
if [ -z "${ACTIVE_HITS}" ]; then
  ok "no active doc, skill, example, or eval advertises the old name"
else
  bad "no active doc, skill, example, or eval advertises the old name" "${ACTIVE_HITS}"
fi

check "the starter prompts lead with Wamala" \
  grep -q 'Use Wamala' "${REPO_ROOT}/docs/starter-prompts.md"
check "the README states the front-door model" \
  grep -q 'Wamala is the front door to Agent Skills' "${REPO_ROOT}/README.md"
check "the routing example is named for the skill" \
  test -f "${REPO_ROOT}/docs/examples/wamala-routing.md"
check "the routing eval is named for the skill" \
  test -f "${REPO_ROOT}/evals/wamala-routing.md"

# The eval harness resolves the skill named in the eval against skills/ on disk,
# so a stale name there is a hard failure rather than a cosmetic one.
check "the eval corpus resolves every named skill" \
  python3 "${REPO_ROOT}/scripts/run-evals.py"

# ------------------------------------------------------------------------------
printf '\n'
if [ "${FAIL}" -gt 0 ]; then
  printf 'FAILED: %s of %s assertions failed.\n' "${FAIL}" "$((PASS + FAIL))" >&2
  exit 1
fi
printf 'ok: front-door skill tests passed (%s assertions' "${PASS}"
[ "${SKIP}" -gt 0 ] && printf ', %s skipped' "${SKIP}"
printf ')\n'
exit 0
