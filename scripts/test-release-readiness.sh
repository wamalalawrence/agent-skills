#!/usr/bin/env bash
# Release-readiness verification.
#
# Runs the mechanical half of docs/release-checklist.md in one command, so the
# evidence in eval-runs/<version>/summary.md is reproducible rather than
# asserted. Everything is sandboxed under `mktemp`; nothing touches the
# developer's real HOME, host skill directories, or credential store.
#
# Not wired into CI. It builds a worktree of the previous release tag and
# performs several full installs, which is minutes of work rather than seconds,
# and CI already covers the fast subset.
#
# Usage:
#   bash scripts/test-release-readiness.sh
#   AGENT_SKILLS_PREVIOUS_TAG=v0.36.0 bash scripts/test-release-readiness.sh
#
# AGENT_SKILLS_PREVIOUS_TAG floats to the latest tag and drives the generic
# upgrade in section 6. AGENT_SKILLS_RENAME_TAG (default v0.37.0) is pinned to
# the release the front-door rename came from and drives section 6b only.
#
# Exit 0 when every check passes, 1 otherwise.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 2
# The release being prepared is not tagged yet, so the highest existing tag is
# the version users are upgrading *from*. Override for a different baseline.
PREVIOUS_TAG="${AGENT_SKILLS_PREVIOUS_TAG:-}"
if [ -z "$PREVIOUS_TAG" ]; then
  PREVIOUS_TAG="$(git tag --list 'v*' --sort=-v:refname | sed -n 1p)"
fi
[ -n "$PREVIOUS_TAG" ] || PREVIOUS_TAG="HEAD"
# Section 6b upgrades across the front-door rename, which happened at one fixed
# point in history. Pinning it there keeps the check meaningful as releases move
# on; floating it to "the previous tag" quietly stopped testing the rename the
# moment v0.38.0 shipped.
RENAME_TAG="${AGENT_SKILLS_RENAME_TAG:-v0.37.0}"

PASS=0
FAIL=0
SANDBOXES=""
cleanup() {
  local box
  for box in $SANDBOXES; do
    [ -n "$box" ] && rm -rf "$box" 2>/dev/null
  done
  git worktree prune 2>/dev/null || true
}
trap cleanup EXIT

good() { PASS=$((PASS + 1)); printf '  PASS  %s\n' "$1"; }
bad() {
  FAIL=$((FAIL + 1))
  printf '  FAIL  %s\n' "$1" >&2
  [ -n "${2:-}" ] && printf '        %s\n' "$2" >&2
}
sec() { printf '\n== %s ==\n' "$1"; }
sandbox() {
  local box
  box="$(mktemp -d)"
  SANDBOXES="$SANDBOXES $box"
  printf '%s' "$box"
}

# ------------------------------------------------------------------------------
sec "1. structural validators"
# ------------------------------------------------------------------------------
if python3 scripts/validate-repo.py >/tmp/as-rr-validate.log 2>&1; then
  good "validate-repo.py passed ($(grep -c '^WARN' /tmp/as-rr-validate.log) warnings)"
else
  bad "validate-repo.py" "$(grep '^FAIL' /tmp/as-rr-validate.log | head -5)"
fi
python3 scripts/validate_skills.py >/dev/null 2>&1 \
  && good "validate_skills.py compatibility shim passed" || bad "validate_skills.py"
if python3 scripts/run-evals.py >/tmp/as-rr-evals.log 2>&1; then
  good "run-evals.py: $(tail -1 /tmp/as-rr-evals.log)"
else
  bad "run-evals.py" "$(cat /tmp/as-rr-evals.log)"
fi
python3 scripts/run-evals.py --strict-sections >/dev/null 2>&1 \
  && good "run-evals.py --strict-sections passed" || bad "run-evals.py --strict-sections"

# ------------------------------------------------------------------------------
sec "2. syntax across every shipped artifact"
# ------------------------------------------------------------------------------
syntax_failed=0
for file in setup.init lib/*.sh bin/agent-skills scripts/*.sh hooks/*.sh; do
  bash -n "$file" 2>/dev/null || { bad "bash -n $file"; syntax_failed=1; }
done
[ "$syntax_failed" -eq 0 ] && good "bash -n clean across setup.init, lib, bin, scripts, hooks"

if python3 - <<'PY'
import ast
import pathlib
import sys

broken = []
for path in sorted(pathlib.Path("scripts").glob("*.py")):
    try:
        ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as error:
        broken.append("%s: %s" % (path, error))
if broken:
    print("\n".join(broken))
    sys.exit(1)
PY
then good "ast.parse clean across every scripts/*.py"; else bad "python syntax"; fi

json_failed=0
for file in hooks/*.json .github/markdown-link-check.json; do
  python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$file" 2>/dev/null \
    || { bad "json.load $file"; json_failed=1; }
done
[ "$json_failed" -eq 0 ] && good "json.load clean across hook templates and CI config"

python3 -c 'import yaml; yaml.safe_load(open(".github/workflows/ci.yml"))' 2>/dev/null \
  && good "ci.yml parses as YAML" \
  || printf '  --    skipped ci.yml YAML parse (PyYAML unavailable)\n'

# ------------------------------------------------------------------------------
sec "3. test suites"
# ------------------------------------------------------------------------------
for suite in test-cli-install test-global-install test-access-resolution \
  test-front-door-skill test-context-optimizer test-guard \
  test-lifecycle-fs test-secret-boundary test-adaptive-execution test-knowledge; do
  if bash "scripts/$suite.sh" </dev/null >"/tmp/as-rr-$suite.log" 2>&1; then
    good "$suite.sh: $(tail -1 "/tmp/as-rr-$suite.log")"
  else
    bad "$suite.sh" "$(grep 'FAIL' "/tmp/as-rr-$suite.log" | head -5)"
  fi
done
if python3 scripts/test-release-engine.py >/tmp/as-rr-engine.log 2>&1; then
  good "release engine: $(tail -1 /tmp/as-rr-engine.log)"
else
  bad "release engine" "$(grep 'FAIL' /tmp/as-rr-engine.log | head -5)"
fi
if python3 scripts/test-meeting.py </dev/null >/tmp/as-rr-meeting.log 2>&1; then
  good "meeting intelligence: $(tail -1 /tmp/as-rr-meeting.log)"
else
  bad "meeting intelligence" "$(grep 'FAIL' /tmp/as-rr-meeting.log | head -5)"
fi

# ------------------------------------------------------------------------------
sec "4. CLI surface"
# ------------------------------------------------------------------------------
for command in help version hosts; do
  bash bin/agent-skills "$command" >/dev/null 2>&1 \
    && good "agent-skills $command" || bad "agent-skills $command"
done
bash bin/agent-skills hosts --json \
  | python3 -c 'import json,sys; assert len(json.load(sys.stdin)) >= 9' 2>/dev/null \
  && good "hosts --json lists at least nine hosts" || bad "hosts --json"
if bash bin/agent-skills definitely-not-a-command >/dev/null 2>&1; then
  bad "an unknown command should exit non-zero"
else
  good "an unknown command exits non-zero"
fi

# ------------------------------------------------------------------------------
sec "5. clean-HOME install, verify, drift, rollback, uninstall"
# ------------------------------------------------------------------------------
BOX="$(sandbox)"
HOME_DIR="$BOX/clean home"
mkdir -p "$HOME_DIR"
run_clean() {
  env -u AGENT_SKILLS_SOURCE HOME="$HOME_DIR" \
    AGENT_SKILLS_HOME="$HOME_DIR/.agent-skills" \
    AGENT_SKILLS_CONFIG_DIR="$HOME_DIR/.config/agent-skills" \
    PATH="$HOME_DIR/.local/bin:$PATH" "$@"
}
as_cli() { run_clean bash bin/agent-skills "$@"; }

if as_cli install --provider local --source "$PWD" --channel any >"$BOX/install.log" 2>&1; then
  good "install from a clean HOME exits 0"
else
  bad "clean install" "$(tail -5 "$BOX/install.log")"
fi
grep -q "No credentials were requested or stored" "$BOX/install.log" \
  && good "install states that no credentials were requested" || bad "install credential statement"
if grep -Eiq 'JIRA_|CONFLUENCE_|SONAR_|paste your|api token' "$BOX/install.log"; then
  bad "install output mentions a credential"
else
  good "install output mentions no credential prompt"
fi
for artifact in ".config/agent-skills/credentials.json" ".env" ".skills"; do
  [ -e "$HOME_DIR/$artifact" ] && bad "install created $artifact" || good "install created no $artifact"
done
[ -L "$HOME_DIR/.agent-skills/current" ] \
  && good "the install is versioned: current points at a release" || bad "no current symlink"
[ -f "$HOME_DIR/.agent-skills/current/release.json" ] \
  && good "the active release carries an integrity manifest" || bad "no release.json"

if as_cli verify >"$BOX/verify.log" 2>&1; then
  good "verify passes on a fresh install"
else
  bad "verify" "$(tail -8 "$BOX/verify.log")"
fi
for line in "install manifest present" "active release" "version coherence" \
  "Host integrations" "Runtime" "Credential storage" "Cloud and remote agents"; do
  grep -q "$line" "$BOX/verify.log" && good "verify reports: $line" || bad "verify missing: $line"
done
if grep -Eq 'ghp_|AKIA[0-9A-Z]{16}' "$BOX/verify.log"; then
  bad "verify leaked a secret-shaped string"
else
  good "verify prints no secret-shaped string"
fi

# Drift: the manifest and the active release must agree, and a reinstall must
# be the thing that repairs the disagreement.
MANIFEST_FILE="$HOME_DIR/.agent-skills/install.json"
python3 - "$MANIFEST_FILE" <<'DRIFTPY'
import json
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as handle:
    data = json.load(handle)
data["version"] = "0.0.1"
with open(path, "w", encoding="utf-8") as handle:
    json.dump(data, handle, indent=2)
DRIFTPY
# Captured rather than piped into `grep -q`: under `set -o pipefail` a matching
# `grep -q` exits early and SIGPIPEs the writer, inverting the assertion.
DRIFT="$(as_cli verify 2>&1 || true)"
case "$DRIFT" in
  *"version drift"*) good "verify detects version drift" ;;
  *) bad "drift detection" "$(printf '%s' "$DRIFT" | head -6)" ;;
esac
as_cli install --provider local --source "$PWD" --channel any >/dev/null 2>&1
DRIFT_AFTER="$(as_cli verify 2>&1 || true)"
case "$DRIFT_AFTER" in
  *"version drift"*) bad "reinstall did not clear drift" ;;
  *"version coherence"*) good "reinstall clears drift" ;;
  *) bad "drift state unclear after reinstall" "$(printf '%s' "$DRIFT_AFTER" | head -6)" ;;
esac

# A release candidate needs a recovery path that has actually been run, not one
# that exists on paper.
NEXTREL="$BOX/next"
mkdir -p "$NEXTREL"
for entry in VERSION bin lib scripts skills docs hooks README.md LICENSE; do
  [ -e "$entry" ] && cp -R "$entry" "$NEXTREL/$entry"
done
printf '99.0.0\n' > "$NEXTREL/VERSION"
as_cli update --provider local --source "$NEXTREL" >"$BOX/update.log" 2>&1 \
  && good "update to a newer release exits 0" || bad "update" "$(tail -5 "$BOX/update.log")"
[ "$(run_clean bash "$HOME_DIR/.agent-skills/bin/agent-skills" version)" = "99.0.0" ] \
  && good "the newer release is active" || bad "update did not activate the new release"
as_cli rollback >"$BOX/rollback.log" 2>&1 \
  && good "rollback exits 0" || bad "rollback" "$(tail -5 "$BOX/rollback.log")"
[ "$(run_clean bash "$HOME_DIR/.agent-skills/bin/agent-skills" version)" = "$(cat VERSION)" ] \
  && good "rollback restored the previous release" || bad "rollback did not restore"

as_cli uninstall --yes >/dev/null 2>&1 \
  && good "uninstall exits 0" || bad "uninstall"
[ -e "$HOME_DIR/.agents/skills/wamala" ] \
  && bad "a registration survived uninstall" || good "uninstall removed our registrations"
[ -d "$HOME_DIR/.agent-skills/versions" ] \
  && bad "release payloads survived uninstall" || good "uninstall removed the release payloads"


# ------------------------------------------------------------------------------
sec "6. upgrade from the $PREVIOUS_TAG installation"
# ------------------------------------------------------------------------------
# The migration every existing user actually performs: a pre-CLI global install
# produced by the previous release, upgraded by the v0.43.0 installer. What must
# survive is not the installation — that is replaced — but everything the user
# owns: credential identities, project bindings, and any legacy `.env` the
# access resolver still reads for them.
UP="$(sandbox)"
if git worktree add -q --detach "$UP/previous" "$PREVIOUS_TAG" 2>/dev/null; then
  UP_HOME="$UP/home"
  UP_OLD="$UP/previous-clone"
  mkdir -p "$UP_HOME" "$UP/work/repo-a"
  cp -R "$UP/previous" "$UP_OLD"
  rm -rf "$UP_OLD/.git"
  ( cd "$UP/work/repo-a" && git init -q )
  printf '[project]\nname = "repo-a"\n' > "$UP/work/repo-a/pyproject.toml"

  run_upgraded() {
    env -i HOME="$UP_HOME" \
      AGENT_SKILLS_HOME="$UP_HOME/.agent-skills" \
      AGENT_SKILLS_CONFIG_DIR="$UP_HOME/.config/agent-skills" \
      PATH="$UP_HOME/.local/bin:/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin" \
      TERM=dumb "$@"
  }

  # Install the previous release from its own on-disk tree, not by re-fetching
  # it. Since the repository went private (v0.43.1) an anonymous git-provider
  # fetch from a throwaway $HOME cannot authenticate, and this section is about
  # upgrade mechanics and state preservation, not distribution access — that is
  # scripts/test-private-source.sh. The tree is already at $UP_OLD.
  #
  # The channel has to be derived because the PREVIOUS tag can itself be a
  # pre-release — from v1.0.0-rc.2 onward it usually is. The local provider
  # correctly refuses to install an `rc` version under the default `stable`
  # channel, so a bare install of an rc predecessor fails on a guard that is
  # doing its job. `--channel any` is the existing "install exactly this tree"
  # hatch and is a no-op for a stable predecessor. Same reasoning as the
  # current-tree installs above; this path was simply not a pre-release until
  # now.
  UP_OLD_VERSION="$(head -n 1 "$UP_OLD/VERSION" 2>/dev/null | tr -d '[:space:]')"
  UP_OLD_CHANNEL_ARGS=()
  case "$UP_OLD_VERSION" in
    *-*) UP_OLD_CHANNEL_ARGS=(--channel any) ;;
  esac
  run_upgraded bash "$UP_OLD/bin/agent-skills" install \
    --provider local --source "$UP_OLD" "${UP_OLD_CHANNEL_ARGS[@]+"${UP_OLD_CHANNEL_ARGS[@]}"}" \
    >"$UP/old.log" 2>&1
  [ -f "$UP_HOME/.agent-skills/install.json" ] \
    && good "$PREVIOUS_TAG produced its own global install" \
    || bad "$PREVIOUS_TAG install" "$(tail -5 "$UP/old.log")"
  [ -L "$UP_HOME/.agents/skills/wamala" ] \
    && good "$PREVIOUS_TAG registered its skills" || bad "$PREVIOUS_TAG registration"

  # State the user owns, in both places it can live.
  run_upgraded python3 "$UP_OLD/scripts/access.py" set --profile work \
    --service demo-service --field host=demo.example.invalid >/dev/null 2>&1
  [ -f "$UP_HOME/.config/agent-skills/credentials.json" ] \
    && good "a credential identity exists before the upgrade" \
    || bad "could not seed a credential identity"
  cat > "$UP/work/.env" <<'LEGACYENV'
JIRA_HOST="https://legacy.example.com"
JIRA_LOGIN="me@example.com"
JIRA_API_TOKEN="legacy-token-value-1234"
LEGACYENV

  run_upgraded bash "$REPO/bin/agent-skills" install \
    --provider local --source "$REPO" --channel any >"$UP/new.log" 2>&1 \
    && good "the v0.43.0 installer upgrades a pre-CLI installation" \
    || bad "upgrade from $PREVIOUS_TAG" "$(tail -8 "$UP/new.log")"
  [ "$(run_upgraded bash "$UP_HOME/.agent-skills/bin/agent-skills" version)" = "$(cat VERSION)" ] \
    && good "the upgraded machine runs this release" || bad "upgrade did not activate this release"
  [ "$(readlink "$UP_HOME/.agent-skills/skills")" = "current/skills" ] \
    && good "the upgrade moved the install onto the versioned layout" \
    || bad "install trees still point outside current"
  run_upgraded bash "$UP_HOME/.agent-skills/bin/agent-skills" verify >"$UP/verify.log" 2>&1 \
    && good "verify passes after the upgrade" || bad "verify after upgrade" "$(tail -8 "$UP/verify.log")"

  [ -f "$UP_HOME/.config/agent-skills/credentials.json" ] \
    && good "the credential identity survived the upgrade" \
    || bad "the upgrade destroyed a credential identity"
  grep -q 'work' "$UP_HOME/.config/agent-skills/credentials.json" \
    && good "the identity itself is intact" || bad "the identity was rewritten"

  # A legacy `.env` is no longer written by anything, but it is still read on
  # behalf of users who have one. Dropping that quietly would take away a
  # credential the user believes is configured.
  LEGACY_RESOLVE="$(
    cd "$UP/work/repo-a" && env HOME="$UP_HOME" \
      AGENT_SKILLS_CONFIG_DIR="$UP_HOME/.config/agent-skills" \
      WORKSPACE_ROOT="$UP/work" \
      python3 "$REPO/scripts/access.py" resolve --service jira \
      --require host,token --secret token --no-capability 2>&1
  )"
  case "$LEGACY_RESOLVE" in
    *"status: resolved"*) good "a legacy .env credential still resolves after the upgrade" ;;
    *) bad "legacy credential lost after upgrade" "$(printf '%s' "$LEGACY_RESOLVE" | head -6)" ;;
  esac
  case "$LEGACY_RESOLVE" in
    *legacy-token-value-1234*) bad "the legacy token value was echoed" ;;
    *) good "the legacy token value was not echoed" ;;
  esac

  # The migration report still explains what a pre-v0.37 workspace leaves behind.
  run_upgraded bash "$UP_HOME/.agent-skills/bin/agent-skills" migrate \
    --workspace-root "$UP/work" >"$UP/migrate.log" 2>&1 || true
  grep -q '\.env' "$UP/migrate.log" \
    && good "migrate still explains an existing legacy .env" || bad "migrate .env report"

  # Meeting state written by this release must be ignored, not tripped over, by
  # the release a user rolls back to. Plant a real record, roll back to the
  # previous tag's own code, and run its verify and doctor against it.
  UP_MEETING="$UP_HOME/.agent-skills/state/meetings/m_0123456789ab/record.json"
  env HOME="$UP_HOME" AGENT_SKILLS_HOME="$UP_HOME/.agent-skills" python3 - "$REPO/scripts" <<'PLANT'
import sys
sys.path.insert(0, sys.argv[1])
import meeting_capture as mc
import meeting_store as store
record = store.new_record("m_0123456789ab", "zoom", "https://zoom.us/j/81234567890", "Planted",
                          {"kind": "unscoped"}, mc.CaptureHandle("recall", "7c1f0d52-3a4e-4b6f-9d21-0a1b2c3d4e5f"),
                          "captions", store.load_config())
store.save_record(record)
PLANT
  UP_MEETING_SUM="$(cksum < "$UP_MEETING" 2>/dev/null)"
  if run_upgraded bash "$UP_HOME/.agent-skills/bin/agent-skills" rollback >"$UP/rollback.log" 2>&1; then
    run_upgraded bash "$UP_HOME/.agent-skills/bin/agent-skills" verify >"$UP/old-verify.log" 2>&1 \
      && good "$PREVIOUS_TAG verify passes with meeting state present" \
      || bad "$PREVIOUS_TAG verify with meeting state" "$(tail -6 "$UP/old-verify.log")"
    run_upgraded bash "$UP_HOME/.agent-skills/bin/agent-skills" doctor --brief >"$UP/old-doctor.log" 2>&1 \
      && good "$PREVIOUS_TAG doctor runs with meeting state present" \
      || bad "$PREVIOUS_TAG doctor with meeting state" "$(tail -6 "$UP/old-doctor.log")"
    [ "$(cksum < "$UP_MEETING" 2>/dev/null)" = "$UP_MEETING_SUM" ] \
      && good "rolling back to $PREVIOUS_TAG leaves meeting state untouched" \
      || bad "rollback to $PREVIOUS_TAG changed meeting state"
  else
    bad "rollback to $PREVIOUS_TAG" "$(tail -6 "$UP/rollback.log")"
  fi

  git worktree remove --force "$UP/previous" 2>/dev/null || true
else
  bad "could not create a worktree for $PREVIOUS_TAG"
fi


# ------------------------------------------------------------------------------
sec "6b. global-install upgrade across the rename ($RENAME_TAG)"
# ------------------------------------------------------------------------------
# The path a pre-rename user actually takes: a global install, then
# `agent-skills update`, which replaces the contents of the same clone and
# re-runs install. Upgrading across the front-door rename is the migration most
# likely to leave a dead registration behind, so it stays pinned to the release
# the rename came from rather than to whatever tag happens to be latest.
GU="$(sandbox)"
if git worktree add -q --detach "$GU/previous" "$RENAME_TAG" 2>/dev/null; then
  GU_HOME="$GU/home"
  GU_SRC="$GU/clone"
  mkdir -p "$GU_HOME"
  cp -R "$GU/previous" "$GU_SRC"
  rm -rf "$GU_SRC/.git"

  run_gu() {
    env -i HOME="$GU_HOME" \
      AGENT_SKILLS_HOME="$GU_HOME/.agent-skills" \
      AGENT_SKILLS_CONFIG_DIR="$GU_HOME/.config/agent-skills" \
      PATH="$GU_HOME/.local/bin:/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin" \
      TERM=dumb "$@"
  }

  # A skill of the user's own, sharing the name that is about to be retired.
  mkdir -p "$GU_HOME/.claude/skills/tech-lead"
  printf -- '---\nname: tech-lead\ndescription: mine\n---\n# Mine\n' \
    > "$GU_HOME/.claude/skills/tech-lead/SKILL.md"

  run_gu bash "$GU_SRC/bin/agent-skills" install >"$GU/old.log" 2>&1
  OLD_FRONT_DOOR="$(sed -n 's/^name: //p' "$GU_SRC/skills/tech-lead/SKILL.md" 2>/dev/null | head -1)"
  if [ "$OLD_FRONT_DOOR" = "tech-lead" ]; then
    good "$RENAME_TAG really did ship the front door as tech-lead"
  else
    bad "$RENAME_TAG front-door name" "got '$OLD_FRONT_DOOR'"
  fi
  [ -L "$GU_HOME/.agents/skills/tech-lead" ] \
    && good "$RENAME_TAG registered tech-lead globally" \
    || bad "$RENAME_TAG registration" "$(tail -5 "$GU/old.log")"

  # Reproduce the upgrade without a network fetch: this release, installed over
  # the pre-rename one by the v0.43.0 installer.
  rm -rf "$GU_SRC"
  cp -R "$REPO" "$GU_SRC"
  rm -rf "$GU_SRC/.git" "$GU_SRC/.venv" "$GU_SRC/.cache"
  run_gu bash "$GU_SRC/bin/agent-skills" install \
    --provider local --source "$GU_SRC" --channel any >"$GU/new.log" 2>&1

  [ -L "$GU_HOME/.agents/skills/wamala" ] \
    && good "the upgrade registered wamala" || bad "wamala not registered" "$(tail -8 "$GU/new.log")"
  [ -f "$GU_HOME/.agents/skills/wamala/SKILL.md" ] \
    && good "the wamala registration resolves to a SKILL.md" || bad "wamala registration dangles"
  if [ -e "$GU_HOME/.agents/skills/tech-lead" ] || [ -L "$GU_HOME/.agents/skills/tech-lead" ]; then
    bad "our tech-lead registration survived the upgrade"
  else
    good "our tech-lead registration was removed by the upgrade"
  fi
  [ -f "$GU_HOME/.claude/skills/tech-lead/SKILL.md" ] \
    && good "the user's own tech-lead skill survived the upgrade" \
    || bad "the upgrade deleted a user skill named tech-lead"
  run_gu bash "$GU_SRC/bin/agent-skills" verify >"$GU/verify.log" 2>&1 \
    && good "verify passes after the upgrade" || bad "verify after upgrade" "$(tail -8 "$GU/verify.log")"
  run_gu bash "$GU_SRC/bin/agent-skills" install \
    --provider local --source "$GU_SRC" --channel any >/dev/null 2>&1
  GU_WAMALA="$(find "$GU_HOME/.agents/skills" -maxdepth 1 -name wamala | wc -l | tr -d ' ')"
  [ "$GU_WAMALA" = "1" ] \
    && good "a second upgrade run leaves exactly one wamala registration" \
    || bad "duplicate wamala registrations" "found $GU_WAMALA"

  # The deprecated lifecycle alias, exercised against the shipped CLI.
  mkdir -p "$GU/repo" && ( cd "$GU/repo" && git init -q )
  ALIAS_OUT="$(
    cd "$GU/repo" && env HOME="$GU_HOME" \
      AGENT_SKILLS_HOME="$GU_HOME/.agent-skills" \
      AGENT_SKILLS_CONFIG_DIR="$GU_HOME/.config/agent-skills" \
      AGENT_SKILLS_CACHE_DIR="$GU/cache" \
      bash "$GU_HOME/.agent-skills/bin/agent-skills" start-task demo demo-1 \
        --no-org --skill tech-lead 2>&1
  )"
  # The `tech-lead` alias was retired in v0.41.0 on the schedule docs/versioning.md
  # recorded. Before that release this asserted the migration notice was printed;
  # it now asserts the opposite, because after a scheduled removal the property
  # worth holding is that the old name is genuinely gone rather than quietly
  # remapped to something else.
  case "$ALIAS_OUT" in
    *"was renamed to"*)
      bad "the retired alias still prints a migration notice" \
        "$(printf '%s' "$ALIAS_OUT" | grep 'renamed' | head -3)" ;;
    *"tech-lead"*)
      good "the shipped CLI passes the retired name through unchanged" ;;
    *) bad "retired alias passthrough" "$(printf '%s' "$ALIAS_OUT" | head -5)" ;;
  esac

  git worktree remove --force "$GU/previous" 2>/dev/null || true
else
  bad "could not create a worktree for $RENAME_TAG (global-install upgrade)"
fi

# ------------------------------------------------------------------------------
sec "7. cloud / in-repo mode unaffected"
# ------------------------------------------------------------------------------
CLOUD="$(sandbox)"
mkdir -p "$CLOUD/repo/.agent-skills"
cp -R "$REPO/skills" "$CLOUD/repo/.agent-skills/skills"
cp "$REPO/.agent-skills.example.yml" "$CLOUD/repo/.agent-skills.yml"
[ -f "$CLOUD/repo/.agent-skills/skills/software-engineer/SKILL.md" ] \
  && good "vendored in-repo skills load with no global install" || bad "vendored skills"
grep -q '^mode: in-repo' "$CLOUD/repo/.agent-skills.yml" \
  && good "the example config still carries the in-repo marker" || bad "in-repo marker"
( cd "$CLOUD/repo" && git init -q ) >/dev/null 2>&1
IN_REPO_MODE="$(
  cd "$CLOUD/repo" && env -u AGENT_SKILLS_HOME HOME="$CLOUD/nohome" \
    python3 "$REPO/scripts/project-context.py" --field mode 2>/dev/null
)"
case "$IN_REPO_MODE" in
  in-repo) good "project context reports in-repo from a committed config" ;;
  *) bad "in-repo mode detection" "got '$IN_REPO_MODE'" ;;
esac

# ------------------------------------------------------------------------------
sec "8. public-safety review"
# ------------------------------------------------------------------------------
# Mirrors the repo validator's own rule: comment lines in non-Markdown files are
# skipped, and the line defining the pattern is allowlisted. A cruder grep flags
# a commented placeholder in a legacy template, which is not a private path.
if python3 - <<'PY'
import pathlib
import re
import subprocess
import sys

pattern = re.compile(r"(?:/Users/[^\s)\"']+|/home/[a-z][^\s)\"']*)")
skip_prefixes = ("eval-runs/", ".claude/")
# Both of these files define the pattern being searched for, so they match
# themselves. The repo validator allowlists itself for the same reason.
skip_files = {
    "CHANGELOG.md",
    "scripts/validate-repo.py",
    "scripts/test-release-readiness.sh",
}
placeholders = ("you/work", "/Users/you", "/home/you")
tracked = subprocess.run(
    ["git", "ls-files"], stdout=subprocess.PIPE, text=True, check=True
).stdout.split()

hits = []
for name in tracked:
    if name.startswith(skip_prefixes) or name in skip_files:
        continue
    path = pathlib.Path(name)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        continue
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#") and path.suffix != ".md":
            continue
        if any(token in line for token in placeholders):
            continue
        if pattern.search(line):
            hits.append("%s:%d: %s" % (name, number, stripped[:100]))
if hits:
    print("\n".join(hits[:10]))
    sys.exit(1)
PY
then good "no private absolute path in tracked files"; else bad "private absolute path found"; fi

if git grep -nE 'ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|BEGIN [A-Z ]*PRIVATE KEY' -- . \
  >/tmp/as-rr-secrets.log 2>&1; then
  bad "secret-shaped string in tracked files" "$(head -3 /tmp/as-rr-secrets.log)"
else
  good "no secret-shaped string in tracked files"
fi
tracked_private=0
for file in .env .env.local .jira-config.yml .skills; do
  git ls-files --error-unmatch "$file" >/dev/null 2>&1 \
    && { bad "$file is tracked"; tracked_private=1; }
done
[ "$tracked_private" -eq 0 ] && good "no private or generated config file is tracked"

# ------------------------------------------------------------------------------
sec "9. README and documentation integrity"
# ------------------------------------------------------------------------------
if python3 - <<'PY'
import re
import sys

text = open("README.md", encoding="utf-8").read()
problems = []
if text.count("```") % 2:
    problems.append("unbalanced code fences")
if "\t" in text:
    problems.append("tab character")
long_lines = [i + 1 for i, line in enumerate(text.splitlines()) if len(line) > 200]
if long_lines:
    problems.append("lines over 200 chars: %s" % long_lines[:3])
for pattern in (
    r"\*\*(\w+) top-level skills\*\*",
    r"\*\*(\w+) nested support skills\*\*",
    r"the (\w+) specialist skills",
):
    if not re.search(pattern, text):
        problems.append("missing count prose for %s" % pattern)
if problems:
    print("; ".join(problems))
    sys.exit(1)
PY
then good "README balanced, tab-free, within line limits, count prose present"; else bad "README"; fi

if python3 - <<'PY'
import pathlib
import re
import sys
from urllib.parse import unquote, urlparse

inline = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
skip = {".git", ".venv", ".cache", "node_modules"}
broken = []
for markdown in sorted(pathlib.Path(".").rglob("*.md")):
    if any(part in skip for part in markdown.parts):
        continue
    for match in inline.finditer(markdown.read_text(encoding="utf-8")):
        target = match.group(1).strip().strip("<>")
        parsed = urlparse(target)
        if parsed.scheme or parsed.netloc or target.startswith("#"):
            continue
        clean = target.split("#", 1)[0]
        if not clean:
            continue
        if not (markdown.parent / unquote(clean)).resolve().exists():
            broken.append("%s -> %s" % (markdown, target))
if broken:
    print("\n".join(broken[:10]))
    sys.exit(1)
PY
then good "every relative markdown link resolves"; else bad "broken relative markdown link"; fi

# ------------------------------------------------------------------------------
sec "10. telemetry review"
# ------------------------------------------------------------------------------
if python3 scripts/telemetry.py report --all >/tmp/as-rr-telemetry.json 2>&1 \
  && python3 -c 'import json; json.load(open("/tmp/as-rr-telemetry.json"))' 2>/dev/null; then
  good "telemetry report --all produced valid JSON"
  printf '        %s\n' "$(tr -d '\n' < /tmp/as-rr-telemetry.json | tr -s ' ')"
  printf '        Paste the verbatim report into eval-runs/<version>/summary.md.\n'
else
  bad "telemetry report" "$(cat /tmp/as-rr-telemetry.json)"
fi

KNOW="$(sandbox)"
( cd "$KNOW" && git init -q ) >/dev/null 2>&1
python3 scripts/knowledge.py --repo-root "$KNOW" init >/dev/null 2>&1
python3 scripts/knowledge.py --repo-root "$KNOW" doctor >/dev/null 2>&1 \
  && good "knowledge doctor passes on a fresh base" || bad "knowledge doctor"

# ------------------------------------------------------------------------------
sec "11. version consistency"
# ------------------------------------------------------------------------------
VERSION="$(head -n 1 VERSION | tr -d '[:space:]')"
printf '        VERSION: %s\n' "$VERSION"
mismatches=0
while IFS= read -r skill; do
  declared="$(grep -m1 '  version:' "$skill" | sed -E 's/.*"([^"]+)".*/\1/')"
  if [ "$declared" != "$VERSION" ]; then
    printf '        %s declares %s\n' "$skill" "$declared"
    mismatches=$((mismatches + 1))
  fi
done <<EOF
$(git ls-files | grep 'SKILL.md$')
EOF
[ "$mismatches" -eq 0 ] \
  && good "every SKILL.md metadata.version matches VERSION ($VERSION)" \
  || bad "$mismatches SKILL.md version mismatch(es)"

if grep -q "$VERSION" README.md; then
  good "README mentions the current VERSION"
else
  bad "README does not mention VERSION $VERSION"
fi
if [ -f "eval-runs/v$VERSION/summary.md" ]; then
  good "eval-runs/v$VERSION/summary.md exists"
else
  bad "eval-runs/v$VERSION/summary.md is missing"
fi

# ------------------------------------------------------------------------------
printf '\n'
if [ "$FAIL" -eq 0 ]; then
  printf 'ok: release readiness verified (%s checks)\n' "$PASS"
  exit 0
fi
printf 'FAIL: %s of %s release-readiness checks failed\n' "$FAIL" "$((PASS + FAIL))" >&2
exit 1
