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
for suite in test-global-install test-access-resolution test-front-door-skill; do
  if bash "scripts/$suite.sh" </dev/null >"/tmp/as-rr-$suite.log" 2>&1; then
    good "$suite.sh: $(tail -1 "/tmp/as-rr-$suite.log")"
  else
    bad "$suite.sh" "$(grep '  FAIL' "/tmp/as-rr-$suite.log" | head -5)"
  fi
done
if bash scripts/test-setup-update-preserves-credentials.sh >/tmp/as-rr-cred.log 2>&1; then
  good "credential preservation across --update"
else
  bad "credential preservation" "$(tail -5 /tmp/as-rr-cred.log)"
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
sec "5. clean-HOME install, verify, drift, uninstall"
# ------------------------------------------------------------------------------
BOX="$(sandbox)"
HOME_DIR="$BOX/clean home"
mkdir -p "$HOME_DIR"
run_clean() {
  env HOME="$HOME_DIR" \
    AGENT_SKILLS_HOME="$HOME_DIR/.agent-skills" \
    AGENT_SKILLS_CONFIG_DIR="$HOME_DIR/.config/agent-skills" \
    PATH="$HOME_DIR/.local/bin:$PATH" "$@"
}
if run_clean ./setup.init --yes >"$BOX/install.log" 2>&1; then
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

if run_clean ./setup.init --verify >"$BOX/verify.log" 2>&1; then
  good "--verify passes on a fresh install"
else
  bad "--verify" "$(tail -8 "$BOX/verify.log")"
fi
for line in "install manifest present" "canonical source" "Host integrations" \
  "Runtime" "Credential storage" "Legacy installation remnants" "Cloud and remote agents"; do
  grep -q "$line" "$BOX/verify.log" && good "verify reports: $line" || bad "verify missing: $line"
done
if grep -Eq 'ghp_|AKIA[0-9A-Z]{16}' "$BOX/verify.log"; then
  bad "verify leaked a secret-shaped string"
else
  good "verify prints no secret-shaped string"
fi

python3 - "$HOME_DIR/.agent-skills/install.json" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as handle:
    data = json.load(handle)
data["version"] = "0.0.1"
with open(path, "w", encoding="utf-8") as handle:
    json.dump(data, handle, indent=2)
PY
# Captured rather than piped into `grep -q`: under `set -o pipefail` a matching
# `grep -q` exits early and SIGPIPEs the writer, inverting the assertion. And the
# healthy line reads "no version drift", so match the WARN prefix specifically.
DRIFT="$(run_clean ./setup.init --verify 2>&1)"
case "$DRIFT" in
  *"WARN  version drift"*) good "verify detects version drift" ;;
  *) bad "drift detection" "$(printf '%s' "$DRIFT" | head -6)" ;;
esac
run_clean ./setup.init --yes >/dev/null 2>&1
DRIFT_AFTER="$(run_clean ./setup.init --verify 2>&1)"
case "$DRIFT_AFTER" in
  *"WARN  version drift"*) bad "reinstall did not clear drift" ;;
  *"no version drift"*) good "reinstall clears drift" ;;
  *) bad "drift state unclear after reinstall" "$(printf '%s' "$DRIFT_AFTER" | head -6)" ;;
esac

run_clean bash bin/agent-skills uninstall --yes >/dev/null 2>&1 \
  && good "uninstall exits 0" || bad "uninstall"
[ -e "$HOME_DIR/.agents/skills/wamala" ] \
  && bad "a registration survived uninstall" || good "uninstall removed our registrations"

# ------------------------------------------------------------------------------
sec "6. upgrade from $PREVIOUS_TAG"
# ------------------------------------------------------------------------------
UP="$(sandbox)"
if git worktree add -q --detach "$UP/previous" "$PREVIOUS_TAG" 2>/dev/null; then
  mkdir -p "$UP/work/repo-a/.git"
  cp -R "$UP/previous" "$UP/work/agent-skills"
  printf '[project]\nname = "repo-a"\n' > "$UP/work/repo-a/pyproject.toml"
  ( cd "$UP/work/agent-skills" \
      && ./setup.init --yes --no-jira --workspace-root "$UP/work" ) >"$UP/old.log" 2>&1
  if [ -f "$UP/work/.env" ] && [ -L "$UP/work/.skills" ]; then
    good "$PREVIOUS_TAG produced its workspace layout (.env + .skills)"
  else
    bad "$PREVIOUS_TAG layout" "$(tail -5 "$UP/old.log")"
  fi
  # Put the credentials where setup.init itself writes them: inside the managed
  # block. Appending them after the block instead tests a shape setup.init
  # deliberately normalises away, which made this section pass for the wrong
  # reason. In-block is what a real v0.36 user has.
  python3 - "$UP/work/.env" <<'PY'
import sys
path = sys.argv[1]
with open(path, encoding="utf-8") as handle:
    text = handle.read()
text = text.replace('JIRA_HOST=""', 'JIRA_HOST="https://legacy.example.com"')
text = text.replace('JIRA_LOGIN=""', 'JIRA_LOGIN="me@example.com"')
text = text.replace('JIRA_API_TOKEN=""', 'JIRA_API_TOKEN="legacy-token-value-1234"')
with open(path, "w", encoding="utf-8") as handle:
    handle.write(text)
PY
  grep -q 'JIRA_HOST="https://legacy.example.com"' "$UP/work/.env" \
    && good "fixture seeded a credential inside the managed block" \
    || bad "fixture could not seed the managed block"

  rm -rf "$UP/work/agent-skills"
  cp -R "$REPO" "$UP/work/agent-skills"
  UP_HOME="$UP/newhome"
  mkdir -p "$UP_HOME"
  run_upgraded() {
    env HOME="$UP_HOME" \
      AGENT_SKILLS_HOME="$UP_HOME/.agent-skills" \
      AGENT_SKILLS_CONFIG_DIR="$UP_HOME/.config/agent-skills" \
      PATH="$UP_HOME/.local/bin:$PATH" "$@"
  }
  # A bare run on an existing legacy workspace must KEEP the legacy model. Before
  # v0.37.0 this silently converted the user to a global install, which is a
  # different layout, registrations in every detected host, and a launcher on
  # PATH — none of it asked for. Migrating is opt-in via --global.
  ( cd "$UP/work/agent-skills" && run_upgraded ./setup.init --yes ) >"$UP/new.log" 2>&1 \
    && good "a bare run on a legacy workspace exits 0" \
    || bad "bare run on a legacy workspace" "$(tail -5 "$UP/new.log")"
  grep -q 'legacy workspace model' "$UP/new.log" \
    && good "a bare run keeps the legacy workspace model" \
    || bad "bare run did not report the legacy model" "$(tail -5 "$UP/new.log")"
  [ -f "$UP_HOME/.agent-skills/install.json" ] \
    && bad "a bare run silently migrated the user to a global install" \
    || good "a bare run created no global install"
  [ -f "$UP/work/.env" ] && good "upgrade did not delete the legacy .env" || bad "legacy .env deleted"
  [ -L "$UP/work/.skills" ] \
    && good "upgrade left the legacy .skills alone" || bad ".skills removed by upgrade"
  # The managed-block writer emits empty strings for any service whose mode
  # resolves to "no", so a rerun that does not opt populated services back in
  # erases credentials it was never asked to touch.
  grep -q 'JIRA_HOST="https://legacy.example.com"' "$UP/work/.env" \
    && good "a bare rerun preserved the in-block Jira credential" \
    || bad "a bare rerun cleared the in-block Jira credential" \
         "$(grep -E '^JIRA_(HOST|LOGIN|API_TOKEN)=' "$UP/work/.env")"
  grep -q 'JIRA_API_TOKEN="legacy-token-value-1234"' "$UP/work/.env" \
    && good "a bare rerun preserved the in-block Jira token" \
    || bad "a bare rerun cleared the in-block Jira token"

  # Opting in explicitly is what produces the new model.
  ( cd "$UP/work/agent-skills" && run_upgraded ./setup.init --global --yes ) \
    >"$UP/optin.log" 2>&1 \
    && good "--global exits 0 on a legacy workspace" \
    || bad "--global on a legacy workspace" "$(tail -5 "$UP/optin.log")"
  [ -f "$UP_HOME/.agent-skills/install.json" ] \
    && good "--global produced the global install" || bad "no global install after --global"
  [ -f "$UP/work/.env" ] \
    && good "opting in still did not delete the legacy .env" || bad "--global deleted the legacy .env"

  ( cd "$UP/work/agent-skills" \
      && run_upgraded bash lib/migrate.sh --workspace-root "$UP/work" ) >"$UP/migrate.log" 2>&1
  grep -q '\.skills is obsolete' "$UP/migrate.log" \
    && good "migrate reports .skills as obsolete" || bad "migrate .skills report"
  grep -q '\.env is still discovered' "$UP/migrate.log" \
    && good "migrate reports .env as still read" || bad "migrate .env report"
  ( cd "$UP/work/agent-skills" && run_upgraded bash lib/migrate.sh \
      --workspace-root "$UP/work" --remove-obsolete ) >/dev/null 2>&1
  [ -e "$UP/work/.skills" ] \
    && bad "--remove-obsolete left .skills" || good "--remove-obsolete removed .skills"
  [ -f "$UP/work/.env" ] \
    && good "--remove-obsolete kept .env" || bad "--remove-obsolete deleted .env"

  LEGACY_RESOLVE="$(
    cd "$UP/work/repo-a" && env HOME="$UP_HOME" \
      AGENT_SKILLS_CONFIG_DIR="$UP_HOME/.config/agent-skills" \
      WORKSPACE_ROOT="$UP/work" \
      python3 "$REPO/scripts/access.py" resolve --service jira \
      --require host,token --secret token --no-capability 2>&1
  )"
  case "$LEGACY_RESOLVE" in
    *"status: resolved"*) good "a legacy .env credential still resolves after upgrade" ;;
    *) bad "legacy credential lost after upgrade" "$(printf '%s' "$LEGACY_RESOLVE" | head -6)" ;;
  esac
  case "$LEGACY_RESOLVE" in
    *legacy-token-value-1234*) bad "the legacy token value was echoed" ;;
    *) good "the legacy token value was not echoed" ;;
  esac
  git worktree remove --force "$UP/previous" 2>/dev/null || true
else
  bad "could not create a worktree for $PREVIOUS_TAG"
fi

# ------------------------------------------------------------------------------
sec "6b. global-install upgrade from $PREVIOUS_TAG"
# ------------------------------------------------------------------------------
# The path a v0.37.0 user actually takes: a global install, then `agent-skills
# update`, which replaces the contents of the same clone and re-runs install.
# The front-door rename makes this the release's highest-risk migration.
GU="$(sandbox)"
if git worktree add -q --detach "$GU/previous" "$PREVIOUS_TAG" 2>/dev/null; then
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

  run_gu bash "$GU_SRC/bin/agent-skills" install --yes >"$GU/old.log" 2>&1
  OLD_FRONT_DOOR="$(sed -n 's/^name: //p' "$GU_SRC/skills/tech-lead/SKILL.md" 2>/dev/null | head -1)"
  if [ "$OLD_FRONT_DOOR" = "tech-lead" ]; then
    good "$PREVIOUS_TAG really did ship the front door as tech-lead"
  else
    bad "$PREVIOUS_TAG front-door name" "got '$OLD_FRONT_DOOR'"
  fi
  [ -L "$GU_HOME/.agents/skills/tech-lead" ] \
    && good "$PREVIOUS_TAG registered tech-lead globally" \
    || bad "$PREVIOUS_TAG registration" "$(tail -5 "$GU/old.log")"

  # `agent-skills update` swaps the clone's contents in place. Reproduce that
  # without a network fetch by copying this release over the same directory.
  rm -rf "$GU_SRC"
  cp -R "$REPO" "$GU_SRC"
  rm -rf "$GU_SRC/.git" "$GU_SRC/.venv" "$GU_SRC/.cache"
  run_gu bash "$GU_SRC/bin/agent-skills" install --yes >"$GU/new.log" 2>&1

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
  run_gu bash "$GU_SRC/bin/agent-skills" install --yes >/dev/null 2>&1
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
  case "$ALIAS_OUT" in
    *"tech-lead was renamed to wamala; using wamala"*)
      good "the shipped CLI resolves the deprecated skill name with a notice" ;;
    *) bad "deprecated alias notice" "$(printf '%s' "$ALIAS_OUT" | head -5)" ;;
  esac

  git worktree remove --force "$GU/previous" 2>/dev/null || true
else
  bad "could not create a worktree for $PREVIOUS_TAG (global-install upgrade)"
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
