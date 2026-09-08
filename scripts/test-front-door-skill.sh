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
if [ "${TOP_LEVEL}" = "8" ]; then
  ok "eight top-level skills are registerable (${TOP_LEVEL})"
else
  bad "eight top-level skills are registerable" "found ${TOP_LEVEL}"
fi

# The specialists keep their role-based names. A rename that swept them up too
# would break every direct invocation in the wild.
for specialist in product-owner software-engineer manual-tester \
  test-automation-engineer delivery-planner delivery-runner domain-modeler; do
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
# The rule is **superset, not equality**. Routing gains rows deliberately: a
# release that teaches the router a new class adds rows, and forbidding that
# would freeze the table rather than protect it. What must never happen is a row
# silently losing its owner or disappearing while something else is being
# edited, which is exactly what the rename release was written to catch. So each
# baseline row must still be present, verbatim, in the current table. An added
# row is reported, not failed.
routing_rows() {
  # Table rows only, name normalised, whitespace collapsed.
  sed -n 's/^|/|/p' \
    | grep -v '^| *---' \
    | sed -e 's/tech-lead/wamala/g' -e 's/[[:space:]]\{1,\}/ /g'
}

# Rows carry a leading index in references/routing-table.md, and renumbering on
# insert is not a contract change. Compare on the part that is the contract:
# the condition, the owner, and the reason.
routing_rows_unindexed() {
  routing_rows | sed -e 's/^| [0-9]\{1,\} |/|/'
}

compare_routing_artifact() {
  local tag="$1" baseline_skill="$2" artifact="$3" before after missing added
  before="$(git -C "${REPO_ROOT}" show "${tag}:${baseline_skill}/${artifact}" \
    2>/dev/null | routing_rows_unindexed)"
  after="$(routing_rows_unindexed < "${SKILL_DIR}/${artifact}")"
  if [ -z "${before}" ]; then
    bad "baseline ${artifact} at ${tag} has routing rows to compare"
    return
  fi
  missing="$(comm -23 <(printf '%s\n' "${before}" | sort -u) \
    <(printf '%s\n' "${after}" | sort -u))"
  added="$(comm -13 <(printf '%s\n' "${before}" | sort -u) \
    <(printf '%s\n' "${after}" | sort -u))"
  if [ -z "${missing}" ]; then
    if [ -n "${added}" ] && [ "${VERBOSE}" = "true" ]; then
      printf '       (%s rows added since %s)\n' \
        "$(printf '%s\n' "${added}" | grep -c .)" "${tag}"
    fi
    ok "${artifact}: every routing row from ${tag} is still present"
  else
    bad "${artifact}: routing rows lost since ${tag}" \
      "$(printf '%s\n' "${missing}" | head -8)"
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
section "deprecated alias tech-lead -> wamala"
# ------------------------------------------------------------------------------
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

ALIAS_OUT="$(run_alias start-task.sh demo demo-2 --no-org --skill tech-lead 2>&1)"
if printf '%s' "${ALIAS_OUT}" | grep -q 'tech-lead was renamed to wamala; using wamala'; then
  ok "start-task prints the migration notice for the deprecated name"
else
  bad "start-task prints the migration notice for the deprecated name" \
    "$(printf '%s' "${ALIAS_OUT}" | head -5)"
fi
ALIAS_BB="$(python3 "${REPO_ROOT}/scripts/blackboard.py" --cache-root "${ALIAS_CACHE}" \
  read demo-2 2>&1)"
if printf '%s' "${ALIAS_BB}" | grep -q 'wamala'; then
  ok "the deprecated name is recorded as wamala, not as itself"
else
  bad "the deprecated name is recorded as wamala, not as itself" \
    "$(printf '%s' "${ALIAS_BB}" | head -5)"
fi
if printf '%s' "${ALIAS_BB}" | grep -q 'tech-lead'; then
  bad "the deprecated name does not survive into the blackboard"
else
  ok "the deprecated name does not survive into the blackboard"
fi

ALIAS_FIN="$(run_alias finish-task.sh demo demo-2 --summary "alias smoke test" \
  --skill tech-lead --no-candidates 2>&1)"
if printf '%s' "${ALIAS_FIN}" | grep -q 'tech-lead was renamed to wamala; using wamala'; then
  ok "finish-task prints the migration notice for the deprecated name"
else
  bad "finish-task prints the migration notice for the deprecated name" \
    "$(printf '%s' "${ALIAS_FIN}" | head -5)"
fi
ALIAS_TEL="$(find "${ALIAS_CACHE}" -name telemetry.ndjson -exec cat {} + 2>/dev/null)"
if printf '%s' "${ALIAS_TEL}" | grep -q '"skill": *"wamala"'; then
  ok "telemetry from the deprecated name is attributed to wamala"
else
  bad "telemetry from the deprecated name is attributed to wamala" \
    "$(printf '%s' "${ALIAS_TEL}" | tail -2)"
fi

# A name that is neither current nor deprecated must pass through untouched, so
# the table cannot silently swallow a typo.
UNKNOWN="$( . "${REPO_ROOT}/scripts/task-context.sh"; \
  agent_skills_resolve_skill_name "not-a-skill" 2>/dev/null )"
if [ "${UNKNOWN}" = "not-a-skill" ]; then
  ok "an unknown skill name passes through the alias table unchanged"
else
  bad "an unknown skill name passes through the alias table unchanged" "got '${UNKNOWN}'"
fi

# The deprecation window is recorded, not open-ended.
if grep -q '| `tech-lead` | `wamala` |' "${REPO_ROOT}/docs/versioning.md"; then
  ok "the alias has a documented removal release"
else
  bad "the alias has a documented removal release" "no row in docs/versioning.md"
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
