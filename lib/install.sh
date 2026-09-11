#!/usr/bin/env bash
# agent-skills host adapters, verification, and uninstall.
#
# Since v0.43.0 this file no longer owns installation. The install transaction
# lives in `lib/asrelease/transaction.py`, which stages, verifies, and activates
# a release, then calls `as_reconcile_hosts` here to point the machine's agent
# hosts at whatever `current` now resolves to. There is one installer, and this
# is its host-facing half. `lib/runtime.sh` must be sourced first.
#
# Safety rules, in force everywhere in this file:
#
#   * Only symlinks whose resolved target lives inside AGENT_SKILLS_HOME are
#     ever created, replaced, or removed. A real directory is never deleted,
#     and a link pointing somewhere else is never touched. That is what makes
#     the installer safe to run next to skills the user already had.
#   * Every operation is idempotent. Re-running install must not produce a
#     second registration or a second copy of anything.
#   * Nothing here asks for a credential. Installation and authentication are
#     separate concerns; see scripts/access.py.

# Directories inside the source tree that the install exposes globally. `hooks`
# is included so the optional hook templates have a stable absolute path too.
AS_LINKED_TREES="skills scripts lib bin docs hooks"
# Exit codes are a public contract, frozen in lib/asrelease/exits.py and in
# docs/one-point-oh.md. Named here so the shell half cannot drift from the
# Python half by returning whatever the last command happened to produce.
AS_EXIT_VERIFY_FAILED="${AS_EXIT_VERIFY_FAILED:-7}"

# ------------------------------------------------------------------------------
# Registry access
# ------------------------------------------------------------------------------
as_registry_path() {
  local source_dir
  source_dir="$(as_source_dir 2>/dev/null || true)"
  [ -n "${source_dir}" ] || return 1
  printf '%s/lib/hosts.registry' "${source_dir}"
}

# Emit registry rows with comments and blank lines stripped.
as_registry_rows() {
  local registry
  registry="$(as_registry_path)" || return 1
  [ -f "${registry}" ] || return 1
  grep -v '^[[:space:]]*#' "${registry}" | grep -v '^[[:space:]]*$'
}

as_row_field() {
  printf '%s' "$1" | cut -d'|' -f"$2"
}

# A host counts as present when its config directory or its skills directory
# already exists. Absent hosts are skipped, not failed: installing on a machine
# without Cursor is a normal case, not an error.
as_host_detected() {
  local global_dir="$1"
  [ "${global_dir}" = "-" ] && return 1
  local skills_dir="${HOME}/${global_dir}"
  [ -d "${skills_dir}" ] && return 0
  local parent
  parent="$(dirname "${skills_dir}")"
  [ -d "${parent}" ] && return 0
  return 1
}

# ------------------------------------------------------------------------------
# Ownership test — the single most important predicate in this file.
#
# True when `path` is a symlink whose resolved target is inside the install
# root. Anything else is somebody else's file and is left alone.
# ------------------------------------------------------------------------------
as_is_owned_link() {
  local path="$1"
  local home home_real target resolved dir
  [ -L "${path}" ] || return 1
  home="$(as_home)"
  home_real="$(as_realpath "${home}" 2>/dev/null || printf '%s' "${home}")"

  # Check the literal link target first. This is what makes ownership survive a
  # deleted or moved source tree: the far end of the chain no longer resolves,
  # but the link we wrote still points at our install root, so we can still
  # recognise and clean up our own registrations. Resolving all the way through
  # a broken chain would silently disown them.
  target="$(readlink "${path}" 2>/dev/null || true)"
  if [ -n "${target}" ]; then
    case "${target}" in
      /*) : ;;
      *)
        dir="$(cd -P "$(dirname "${path}")" >/dev/null 2>&1 && pwd)"
        target="${dir}/${target}"
        ;;
    esac
    case "${target}" in
      "${home}"|"${home}"/*) return 0 ;;
      "${home_real}"|"${home_real}"/*) return 0 ;;
    esac
  fi

  resolved="$(as_realpath "${path}" 2>/dev/null || true)"
  [ -n "${resolved}" ] || return 1
  case "${resolved}" in
    "${home_real}"|"${home_real}"/*) return 0 ;;
    "${home}"|"${home}"/*) return 0 ;;
  esac
  return 1
}

# True when `path` sits inside the install root.
#
# Location-based ownership, as opposed to the target-based test above. We create
# `~/.agent-skills` and everything in it, so an entry there is ours regardless of
# where it currently points. Entries in a host's own skills directory get no such
# presumption — that directory belongs to the user.
as_in_install_namespace() {
  local path="$1"
  local home home_real parent parent_real
  home="$(as_home)"
  home_real="$(as_realpath "${home}" 2>/dev/null || printf '%s' "${home}")"
  parent="$(dirname "${path}")"
  parent_real="$(cd -P "${parent}" >/dev/null 2>&1 && pwd)" || parent_real="${parent}"
  case "${parent}" in
    "${home}"|"${home}"/*) return 0 ;;
    "${home_real}"|"${home_real}"/*) return 0 ;;
  esac
  case "${parent_real}" in
    "${home}"|"${home}"/*) return 0 ;;
    "${home_real}"|"${home_real}"/*) return 0 ;;
  esac
  return 1
}

# Create or refresh a symlink at `link` pointing to `target`.
# Echoes one of: created | kept | relinked | conflict
as_link_path() {
  local target="$1"
  local link="$2"

  if [ -L "${link}" ]; then
    if [ -e "${link}" ] && as_same_path "${link}" "${target}"; then
      printf '%s' 'kept'
      return 0
    fi
    # Two ways a link may be replaced, and a dangling link needs one of them.
    #
    #   * It lives inside our own install root, a namespace we created. Anything
    #     at `~/.agent-skills/<tree>` is ours by location no matter what it now
    #     points at, so a canonical tree left dangling by a moved source clone is
    #     repaired here.
    #   * Or its literal target points into our install root, which is how a
    #     registration in a host's directory proves it is ours.
    #
    # Neither holds for a dangling link somebody else wrote into a host's skills
    # directory — an unmounted volume, a repo not yet cloned on this machine, a
    # directory synced from elsewhere. The link is itself the data, so that is a
    # conflict to preserve, not a free slot to claim.
    if as_in_install_namespace "${link}" || as_is_owned_link "${link}"; then
      rm -f "${link}"
      ln -s "${target}" "${link}"
      printf '%s' 'relinked'
      return 0
    fi
    printf '%s' 'conflict'
    return 0
  fi

  if [ -e "${link}" ]; then
    printf '%s' 'conflict'
    return 0
  fi

  ln -s "${target}" "${link}"
  printf '%s' 'created'
}

# ------------------------------------------------------------------------------
# Skill enumeration
#
# Only top-level skills are registered. Nested support skills travel inside
# their parent's directory, so a host that walks the skills root recursively
# finds them, and a host that does not still sees the parent. Registering them
# separately would put two names into one host directory for one skill tree.
# ------------------------------------------------------------------------------
as_top_level_skills() {
  local source_dir="$1"
  local entry name
  for entry in "${source_dir}"/skills/*; do
    [ -d "${entry}" ] || continue
    [ -f "${entry}/SKILL.md" ] || continue
    name="$(basename "${entry}")"
    printf '%s\n' "${name}"
  done
}

# ------------------------------------------------------------------------------
# Orphan registrations
#
# A registration is an orphan when it is one of ours — a symlink into
# `<home>/skills/<name>` — but `<name>` is no longer a skill in this release.
# That happens when a skill is renamed or dropped: `tech-lead` became `wamala`
# in v0.38.0, and without this the old name stays in every host directory as a
# dead front door pointing at a path the new release does not create.
#
# The predicate is deliberately narrow. It requires BOTH that the entry is a
# symlink we wrote (`as_is_owned_link`) AND that its literal target's parent is
# our canonical skills directory. A directory the user created, a link into
# their own tree, and anything else in the host directory all fail it, so a
# same-named skill of the user's own is never touched.
# ------------------------------------------------------------------------------
as_is_our_skill_registration() {
  local path="$1"
  as_is_owned_link "${path}" || return 1

  local home home_real target dir parent
  home="$(as_home)"
  home_real="$(as_realpath "${home}" 2>/dev/null || printf '%s' "${home}")"
  target="$(readlink "${path}" 2>/dev/null || true)"
  [ -n "${target}" ] || return 1
  case "${target}" in
    /*) : ;;
    *)
      dir="$(cd -P "$(dirname "${path}")" >/dev/null 2>&1 && pwd)"
      target="${dir}/${target}"
      ;;
  esac
  parent="$(dirname "${target}")"
  case "${parent}" in
    "${home}/skills"|"${home_real}/skills") return 0 ;;
  esac
  return 1
}

# Echo the names of our registrations in `skills_dir` that no longer exist as
# skills in `source_dir`. Read-only; the caller decides what to do with them.
as_orphan_registrations() {
  local source_dir="$1"
  local skills_dir="$2"
  [ -d "${skills_dir}" ] || return 0

  local current=""
  local name
  while IFS= read -r name; do
    [ -n "${name}" ] || continue
    current="${current}${name} "
  done <<EOF
$(as_top_level_skills "${source_dir}")
EOF
  # An empty skill list means we could not read the source tree. Removing every
  # registration on that basis would be the worst possible failure mode, so
  # report nothing instead.
  [ -n "${current}" ] || return 0

  local entry
  for entry in "${skills_dir}"/*; do
    [ -L "${entry}" ] || continue
    name="$(basename "${entry}")"
    case " ${current} " in
      *" ${name} "*) continue ;;
    esac
    as_is_our_skill_registration "${entry}" || continue
    printf '%s\n' "${name}"
  done
}

# ------------------------------------------------------------------------------
# Host registration
# ------------------------------------------------------------------------------
# Register every skill into one host directory.
# Sets AS_REGISTER_CREATED / AS_REGISTER_KEPT / AS_REGISTER_CONFLICTS /
# AS_REGISTER_PRUNED.
as_register_host_dir() {
  local source_dir="$1"
  local skills_dir="$2"
  AS_REGISTER_CREATED=0
  AS_REGISTER_KEPT=0
  AS_REGISTER_CONFLICTS=""
  AS_REGISTER_PRUNED=""

  mkdir -p "${skills_dir}" 2>/dev/null || return 1

  # Reconcile before registering, so a renamed skill leaves no second entry
  # behind. Idempotent: a second run finds nothing left to prune.
  local orphan
  while IFS= read -r orphan; do
    [ -n "${orphan}" ] || continue
    rm -f "${skills_dir}/${orphan}"
    AS_REGISTER_PRUNED="${AS_REGISTER_PRUNED}${orphan} "
  done <<EOF
$(as_orphan_registrations "${source_dir}" "${skills_dir}")
EOF

  local name status
  while IFS= read -r name; do
    [ -n "${name}" ] || continue
    status="$(as_link_path "$(as_home)/skills/${name}" "${skills_dir}/${name}")"
    case "${status}" in
      created|relinked) AS_REGISTER_CREATED=$((AS_REGISTER_CREATED + 1)) ;;
      kept) AS_REGISTER_KEPT=$((AS_REGISTER_KEPT + 1)) ;;
      conflict) AS_REGISTER_CONFLICTS="${AS_REGISTER_CONFLICTS}${name} " ;;
    esac
  done <<EOF
$(as_top_level_skills "${source_dir}")
EOF
  return 0
}

# Remove only this project's registrations from one host directory. A skill the
# user installed themselves is not a symlink into our home, so it survives.
as_unregister_host_dir() {
  local skills_dir="$1"
  AS_UNREGISTER_REMOVED=0
  [ -d "${skills_dir}" ] || return 0
  local entry
  for entry in "${skills_dir}"/*; do
    [ -e "${entry}" ] || [ -L "${entry}" ] || continue
    if as_is_owned_link "${entry}"; then
      rm -f "${entry}"
      AS_UNREGISTER_REMOVED=$((AS_UNREGISTER_REMOVED + 1))
    fi
  done
  # Remove the directory only when we created it and nothing else is in it.
  rmdir "${skills_dir}" 2>/dev/null || true
  return 0
}

# ------------------------------------------------------------------------------
# CLI on PATH
#
# The launcher is linked into the first writable candidate directory. Shell
# startup files are never edited: a silent rc-file write is a surprise, and the
# skills carry a documented fallback that works without PATH at all.
# ------------------------------------------------------------------------------
as_path_link_candidates() {
  printf '%s\n' "${HOME}/.local/bin"
  printf '%s\n' "${HOME}/bin"
}

as_dir_on_path() {
  local dir="$1"
  case ":${PATH}:" in
    *":${dir}:"*) return 0 ;;
  esac
  return 1
}

# Sets AS_CLI_LINK and AS_CLI_ON_PATH.
as_link_cli() {
  AS_CLI_LINK=""
  AS_CLI_ON_PATH="no"
  local target="$(as_home)/bin/agent-skills"
  local dir status
  while IFS= read -r dir; do
    [ -n "${dir}" ] || continue
    mkdir -p "${dir}" 2>/dev/null || continue
    [ -w "${dir}" ] || continue
    status="$(as_link_path "${target}" "${dir}/agent-skills")"
    case "${status}" in
      created|relinked|kept)
        AS_CLI_LINK="${dir}/agent-skills"
        as_dir_on_path "${dir}" && AS_CLI_ON_PATH="yes"
        return 0
        ;;
    esac
  done <<EOF
$(as_path_link_candidates)
EOF
  return 1
}

# ------------------------------------------------------------------------------
# Host reconciliation
#
# This is the only part of installation that writes outside AGENT_SKILLS_HOME,
# and it is the reason the host adapters stayed in shell: the ownership
# predicates above decide what may be touched inside a directory that belongs to
# the user, and they are the most safety-critical code in the project.
#
# The install transaction in lib/asrelease/transaction.py calls this through
# scripts/hosts-reconcile.sh after activating a release, and again after a
# rollback. It never registers a version: every registration points at
# `<home>/skills/<name>`, which resolves through `current`. Repointing `current`
# therefore moves every host at once, and there is no window in which two hosts
# disagree about which version they are on.
#
# Reads:  AS_OPT_HOSTS, AS_OPT_ALL_HOSTS, AS_OPT_NO_PATH
# Writes: AS_RESULT_HOSTS=<ids>, AS_RESULT_CLI_LINK=<path> on stdout
# ------------------------------------------------------------------------------
as_reconcile_hosts() {
  local source_dir home
  source_dir="$(as_source_dir 2>/dev/null || true)"
  [ -n "${source_dir}" ] || as_die "no active release to register; run: agent-skills install" 6
  home="$(as_home)"

  command -v python3 >/dev/null 2>&1 \
    || as_die "python3 is required to install agent-skills" 2
  as_registry_path >/dev/null 2>&1 \
    || as_die "host registry not found; this release is incomplete (expected lib/hosts.registry)" 5
  [ -n "$(as_registry_rows)" ] \
    || as_die "host registry is empty; this release is incomplete" 5

  local registered="" row id label global_dir register skipped=""
  while IFS= read -r row; do
    [ -n "${row}" ] || continue
    id="$(as_row_field "${row}" 1)"
    label="$(as_row_field "${row}" 2)"
    global_dir="$(as_row_field "${row}" 3)"
    register="$(as_row_field "${row}" 4)"

    if [ -n "${AS_OPT_HOSTS:-}" ]; then
      case ",${AS_OPT_HOSTS}," in
        *",${id},"*) : ;;
        *) continue ;;
      esac
    fi

    if [ "${register}" = "manual" ]; then
      as_info "${label}: one manual step required (see docs/assistants.md)"
      continue
    fi

    if [ "${register}" = "link" ] && [ "${AS_OPT_ALL_HOSTS:-false}" != "true" ] \
      && [ -z "${AS_OPT_HOSTS:-}" ] && ! as_host_detected "${global_dir}"; then
      skipped="${skipped}${label}, "
      continue
    fi

    if as_register_host_dir "${source_dir}" "${HOME}/${global_dir}"; then
      if [ -n "${AS_REGISTER_CONFLICTS}" ]; then
        as_warn "${label}: left existing non-agent-skills entries alone: ${AS_REGISTER_CONFLICTS}"
      fi
      if [ -n "${AS_REGISTER_PRUNED}" ]; then
        as_info "${label}: removed registration(s) for skills this release no longer ships: ${AS_REGISTER_PRUNED}"
      fi
      as_ok "${label}: ~/${global_dir} (${AS_REGISTER_CREATED} linked, ${AS_REGISTER_KEPT} already current)"
      registered="${registered}${id} "
    else
      as_warn "${label}: could not write ~/${global_dir}"
    fi
  done <<EOF
$(as_registry_rows)
EOF
  if [ -n "${skipped}" ]; then
    as_info "not detected on this machine, skipped: ${skipped%, }"
  fi

  local cli_link=""
  if [ "${AS_OPT_NO_PATH:-false}" = "true" ]; then
    as_info "PATH link skipped"
  elif as_link_cli; then
    cli_link="${AS_CLI_LINK}"
    if [ "${AS_CLI_ON_PATH}" = "yes" ]; then
      as_ok "agent-skills -> ${cli_link}"
    else
      as_warn "linked ${cli_link} but its directory is not on PATH"
      as_warn "add to your shell profile: export PATH=\"$(dirname "${cli_link}"):\$PATH\""
    fi
  else
    as_warn "no writable PATH directory found; use ${home}/bin/agent-skills directly"
  fi

  # Execution Guard hooks must follow the active release. `guard reconcile`
  # rewrites only hook entries this project owns, and is a no-op when the guard
  # was never installed, so an update or rollback can call it unconditionally.
  if [ -f "${source_dir}/scripts/guard.py" ]; then
    python3 "${source_dir}/scripts/guard.py" reconcile >/dev/null 2>&1 || true
  fi

  printf 'AS_RESULT_HOSTS=%s\n' "${registered% }"
  printf 'AS_RESULT_CLI_LINK=%s\n' "${cli_link}"
  return 0
}


as_recommend_guard() {
  local source_dir
  source_dir="$(as_source_dir 2>/dev/null || true)"
  [ -n "${source_dir}" ] || return 0
  [ -f "${source_dir}/scripts/guard.py" ] || return 0

  local registered=""
  registered="$(python3 "${source_dir}/scripts/guard.py" verify --format json 2>/dev/null \
    | python3 -c '
import json
import sys

try:
    hosts = json.load(sys.stdin)["hosts"]
except Exception:
    sys.exit(0)
names = [h["label"] for h in hosts if h["state"] == "registered"]
sys.stdout.write(", ".join(names))
' 2>/dev/null || true)"

  printf 'Execution Guard (not installed automatically)\n'
  if [ -n "${registered}" ]; then
    printf '  Already enforcing before execution for: %s\n' "${registered}"
    printf '  Re-check with: agent-skills guard verify\n'
  else
    printf '  A deterministic check that runs before every shell command and tool\n'
    printf '  call, and blocks the destructive ones. It edits your host hook\n'
    printf '  configuration, so it is opt-in:\n'
    printf '\n'
    printf '    agent-skills guard install --dry-run   show exactly what would change\n'
    printf '    agent-skills guard install             register the hooks\n'
    printf '    agent-skills guard doctor              per-host enforcement status\n'
  fi
  printf '\n'
}

as_print_host_summary() {
  local registered="$1"
  local row id label register global_dir
  while IFS= read -r row; do
    [ -n "${row}" ] || continue
    id="$(as_row_field "${row}" 1)"
    label="$(as_row_field "${row}" 2)"
    register="$(as_row_field "${row}" 4)"
    global_dir="$(as_row_field "${row}" 3)"
    case " ${registered} " in
      *" ${id} "*) printf '  [x] %s (~/%s)\n' "${label}" "${global_dir}" ;;
      *)
        if [ "${register}" = "manual" ]; then
          printf '  [ ] %s — one settings action, see docs/assistants.md\n' "${label}"
        fi
        ;;
    esac
  done <<EOF
$(as_registry_rows)
EOF
}

# ------------------------------------------------------------------------------
# verify
# ------------------------------------------------------------------------------
# Re-hash an installed release and compare it with its own manifest.
#
#   0  the payload matches
#   1  it does not
#   3  the check could not run (no python3, no release engine reachable) — a
#      missing tool is not evidence of tampering and must not read as one
as_verify_payload_integrity() {
  local root="$1"
  local engine="${root}/lib"
  [ -d "${engine}/asrelease" ] || return 3
  command -v python3 >/dev/null 2>&1 || return 3
  AS_VERIFY_ROOT="${root}" AS_VERIFY_ENGINE="${engine}" python3 - <<'PY'
import os
import sys

sys.path.insert(0, os.environ["AS_VERIFY_ENGINE"])
root = os.environ["AS_VERIFY_ROOT"]
try:
    from asrelease.release import verify_payload
except Exception as exc:  # the engine is unreachable, not the payload wrong
    sys.stderr.write("release engine unavailable: {}\n".format(exc))
    raise SystemExit(3)
try:
    verify_payload(root)
except SystemExit:
    raise
except Exception as exc:
    sys.stderr.write("{}\n".format(getattr(exc, "message", None) or exc))
    raise SystemExit(1)
raise SystemExit(0)
PY
}
# Print the frozen exit-code contract, read from its one definition.
as_explain_exit_codes() {
  local source_dir engine
  source_dir="$(as_source_dir 2>/dev/null || true)"
  engine="${source_dir:+${source_dir}/lib}"
  if [ -n "${engine}" ] && [ -d "${engine}/asrelease" ] && command -v python3 >/dev/null 2>&1; then
    AS_EXPLAIN_ENGINE="${engine}" python3 - <<'PY' && return 0
import os
import sys

sys.path.insert(0, os.environ["AS_EXPLAIN_ENGINE"])
from asrelease.exits import Exit

MEANINGS = {
    0: "the operation succeeded",
    2: "the command was wrong; fix the invocation",
    3: "the release source needs credentials; authenticate, then retry",
    4: "the release source was unreachable; retry later",
    5: "the payload was not what it claimed to be; do not retry blindly",
    6: "the machine could not be changed; the previous version is still active",
    7: "the machine is in a bad state; run: agent-skills doctor",
    10: "an update is available; informational, not a failure",
}
print("agent-skills exit codes (frozen at 1.0; see docs/one-point-oh.md)")
print("")
for code in sorted(Exit.NAMES):
    print("  {:<3} {:<26} {}".format(code, Exit.NAMES[code], MEANINGS.get(code, "")))
PY
  fi
  printf 'agent-skills exit codes\n\n'
  printf '  0   ok\n  2   usage-error\n  3   authentication-required\n'
  printf '  4   network-failure\n  5   integrity-failure\n  6   installation-failure\n'
  printf '  7   verification-failure\n  10  update-available\n'
}
as_verify_install() {
  local errors=0
  local home source_dir manifest
  home="$(as_home)"
  manifest="$(as_manifest_path)"

  printf 'agent-skills verify\n'
  printf '  home: %s\n\n' "${home}"

  if [ ! -f "${manifest}" ]; then
    as_fail "no install manifest at ${manifest}"
    printf '        Run: agent-skills install\n' >&2
    return 7
  fi

  local installed_version source_version active_version
  installed_version="$(as_installed_version || printf 'unknown')"
  as_ok "install manifest present (v${installed_version})"

  # The active release. `current` is the only pointer that decides which version
  # this machine runs, so it is checked before anything that depends on it.
  active_version="$(as_active_version || printf '')"
  if [ -z "${active_version}" ]; then
    as_fail "no active release: ${home}/current does not point at an installed version"
    printf '        Run: agent-skills install\n' >&2
    errors=$((errors + 1))
  elif [ ! -d "$(as_realpath "${home}/current" 2>/dev/null || printf '/nonexistent')" ]; then
    as_fail "${home}/current is a broken link (points at ${active_version})"
    printf '        Run: agent-skills rollback   (or: agent-skills install)\n' >&2
    errors=$((errors + 1))
  else
    as_ok "active release: v${active_version} at ${home}/versions/${active_version}"
  fi

  source_dir="$(as_source_dir 2>/dev/null || true)"
  if [ -z "${source_dir}" ]; then
    as_fail "the active release tree is unreachable"
    errors=$((errors + 1))
  else
    source_version="$(as_read_version_file "${source_dir}/VERSION" || printf 'unknown')"
    # Version coherence. Skills, runtime, manifest, and the release payload all
    # come from one directory, so a disagreement between any two of them means
    # the install is mixed and must not be reported as healthy.
    if [ "${source_version}" != "${installed_version}" ]; then
      as_fail "version drift: manifest v${installed_version}, active release v${source_version}"
      printf '        Run: agent-skills install   (re-activates and refreshes the manifest)\n' >&2
      errors=$((errors + 1))
    elif [ -n "${active_version}" ] && [ "${active_version}" != "${source_version}" ]; then
      as_fail "version drift: current -> ${active_version}, payload VERSION ${source_version}"
      errors=$((errors + 1))
    else
      as_ok "version coherence: manifest, current, and payload all v${source_version}"
    fi
    # Integrity, not just presence. Checking that release.json exists proved
    # nothing about the tree it describes: `verify` printed "Installation
    # verified" over a release whose files had been edited, because the payload
    # hash was only ever re-computed at stage and rollback time. This re-hashes
    # the active tree and compares it against the manifest that shipped with it,
    # which is the only check that can tell a tampered release from a good one.
    if [ -f "${source_dir}/release.json" ]; then
      local integrity_out integrity_rc
      integrity_out="$(as_verify_payload_integrity "${source_dir}" 2>&1)"
      integrity_rc=$?
      if [ "${integrity_rc}" -eq 0 ]; then
        as_ok "release payload matches its manifest hash"
      elif [ "${integrity_rc}" -eq 3 ]; then
        as_warn "could not re-check the payload hash: ${integrity_out}"
      else
        as_fail "release payload does not match its manifest"
        printf '        %s\n' "${integrity_out}" >&2
        printf '        Run: agent-skills install   (re-stages a verified payload)\n' >&2
        errors=$((errors + 1))
      fi
    else
      as_warn "active release has no release.json; integrity cannot be re-checked"
    fi
  fi

  # A recovery path is part of a working installation, so its absence is
  # reported rather than left to be discovered during an incident.
  local rollback_to
  rollback_to="$(as_rollback_candidate || printf '')"
  if [ -n "${rollback_to}" ]; then
    as_ok "previous release retained: v${rollback_to} (agent-skills rollback)"
  else
    as_info "no previous release retained; rollback has nothing to return to yet"
  fi

  local tree tree_errors=0
  for tree in ${AS_LINKED_TREES}; do
    if [ ! -e "${home}/${tree}" ]; then
      # docs and hooks are convenience trees; their absence is not a fault.
      case "${tree}" in docs|hooks) continue ;; esac
      as_fail "${home}/${tree} is missing"
      errors=$((errors + 1))
      tree_errors=$((tree_errors + 1))
    elif [ -L "${home}/${tree}" ] && [ ! -e "$(as_realpath "${home}/${tree}")" ]; then
      as_fail "${home}/${tree} is a broken symlink"
      errors=$((errors + 1))
      tree_errors=$((tree_errors + 1))
    fi
  done
  # Report on the trees only, not on `errors`, which earlier checks also feed —
  # otherwise an unrelated earlier failure silently suppresses this line and the
  # trees look unreported rather than fine.
  [ "${tree_errors}" -eq 0 ] && as_ok "canonical trees resolve"

  # Host integrations: every registration must resolve into the canonical tree.
  printf '\nHost integrations\n'
  local row id label global_dir register skill_count linked stale foreign entry name orphans
  local canonical="${home}/skills"
  while IFS= read -r row; do
    [ -n "${row}" ] || continue
    id="$(as_row_field "${row}" 1)"
    label="$(as_row_field "${row}" 2)"
    global_dir="$(as_row_field "${row}" 3)"
    register="$(as_row_field "${row}" 4)"

    if [ "${register}" = "manual" ]; then
      as_info "${label}: manual registration, cannot be verified from the filesystem"
      continue
    fi
    if [ ! -d "${HOME}/${global_dir}" ]; then
      as_info "${label}: not registered (host not detected)"
      continue
    fi

    skill_count=0
    linked=0
    stale=0
    foreign=0
    while IFS= read -r name; do
      [ -n "${name}" ] || continue
      skill_count=$((skill_count + 1))
      entry="${HOME}/${global_dir}/${name}"
      [ -e "${entry}" ] || [ -L "${entry}" ] || continue
      if as_is_owned_link "${entry}"; then
        # One of ours: registered only if it still resolves to the canonical
        # tree, otherwise the source moved and install needs rerunning.
        if [ -e "${entry}/SKILL.md" ] && as_same_path "${entry}" "${canonical}/${name}"; then
          linked=$((linked + 1))
        else
          stale=$((stale + 1))
        fi
      else
        # Not ours. Install deliberately leaves a same-named user skill alone, so
        # verify must not call that preserved state a failure — there would be no
        # way to get verify green short of deleting the user's own work.
        foreign=$((foreign + 1))
      fi
    done <<INNER
$(as_top_level_skills "${source_dir:-${home}}")
INNER

    orphans="$(as_orphan_registrations "${source_dir:-${home}}" "${HOME}/${global_dir}" | tr '\n' ' ')"
    if [ -n "${orphans}" ]; then
      as_fail "${label}: stale registration(s) for renamed or removed skills: ${orphans}"
      printf '        Run: agent-skills install   (removes them)\n' >&2
      errors=$((errors + 1))
    fi

    if [ "${linked}" -eq 0 ] && [ "${stale}" -eq 0 ]; then
      as_info "${label}: no agent-skills registrations in ~/${global_dir}"
    elif [ "${stale}" -gt 0 ]; then
      as_fail "${label}: ${stale} agent-skills registration(s) in ~/${global_dir} no longer resolve"
      printf '        Run: agent-skills install   (re-links them)\n' >&2
      errors=$((errors + 1))
    elif [ "${linked}" -lt $((skill_count - foreign)) ]; then
      as_warn "${label}: ${linked}/${skill_count} skills registered; rerun install"
    else
      as_ok "${label}: ${linked}/${skill_count} skills resolve to the canonical tree"
    fi
    if [ "${foreign}" -gt 0 ]; then
      as_info "${label}: ${foreign} name(s) in ~/${global_dir} are yours, not ours, and were left alone"
    fi
  done <<EOF
$(as_registry_rows)
EOF

  # Runtime reachability.
  printf '\nRuntime\n'
  if [ -x "${home}/bin/agent-skills" ]; then
    as_ok "launcher executable at ${home}/bin/agent-skills"
  else
    as_fail "launcher missing or not executable at ${home}/bin/agent-skills"
    errors=$((errors + 1))
  fi
  if command -v agent-skills >/dev/null 2>&1; then
    as_ok "agent-skills is on PATH"
  else
    as_warn "agent-skills is not on PATH; skills fall back to ${home}/bin/agent-skills"
  fi
  local helper
  for helper in start-task.sh finish-task.sh doctor.sh; do
    if [ -f "${home}/scripts/${helper}" ]; then
      as_ok "lifecycle helper reachable: ${helper}"
    else
      as_fail "lifecycle helper missing: ${home}/scripts/${helper}"
      errors=$((errors + 1))
    fi
  done

  # Credential backend and legacy remnants are reported by dedicated tools so
  # this stays a filesystem check. Both are surfaced, neither prints a secret.
  printf '\nCredential storage\n'
  if [ -f "${home}/scripts/access.py" ]; then
    python3 "${home}/scripts/access.py" backend || true
  else
    as_warn "scripts/access.py not reachable; cannot report the credential backend"
  fi

  printf '\nLegacy installation remnants\n'
  as_report_legacy_remnants

  printf '\nCloud and remote agents\n'
  as_info "a cloud agent cannot read this machine; use the in-repo mechanism there"
  as_info "see docs/execution-modes.md"

  printf '\n'
  if [ "${errors}" -gt 0 ]; then
    printf '%s failure(s). See the FAIL lines above.\n' "${errors}" >&2
    # 7, not 1. The exit-code contract in docs/one-point-oh.md freezes
    # "verify failed" as 7 and says 1 never appears, and a caller branching on
    # 7 to run doctor saw the drift case fall through as a generic failure. The
    # only reason it was 1 was that this function returned the shell's default.
    return "${AS_EXIT_VERIFY_FAILED}"
  fi
  printf 'Installation verified.\n'
  return 0
}

# Report pre-v0.37.0 workspace artifacts near the source clone. Read-only: it
# never deletes anything, because a `.env` may still be the user's only copy of
# a credential.
as_report_legacy_remnants() {
  local source_dir parent found=0
  source_dir="$(as_source_dir 2>/dev/null || true)"
  if [ -z "${source_dir}" ]; then
    as_info "source tree unknown; skipped the legacy scan"
    return 0
  fi
  parent="$(dirname "${source_dir}")"
  local candidate
  for candidate in .skills .agent-skills.lock; do
    if [ -e "${parent}/${candidate}" ]; then
      as_warn "legacy ${candidate} found beside the clone; obsolete under the global install"
      found=1
    fi
  done
  for candidate in .env .env.local .jira-config.yml; do
    if [ -f "${parent}/${candidate}" ]; then
      as_info "legacy ${candidate} beside the clone is still read by the access resolver"
      found=1
    fi
  done
  if [ "${found}" -eq 1 ]; then
    printf '        Migration guidance: agent-skills migrate\n'
  else
    as_ok "no legacy workspace remnants beside the clone"
  fi
  return 0
}

# ------------------------------------------------------------------------------
# uninstall
# ------------------------------------------------------------------------------
# AS_OPT_PURGE="true" also removes credential metadata and bindings. Secret
# values in an OS store are never removed implicitly: that needs
# `agent-skills access forget`, which is an explicit, per-identity action.
as_uninstall_global() {
  local home removed=0
  home="$(as_home)"

  printf 'Uninstalling agent-skills\n'
  printf '  home: %s\n\n' "${home}"

  # Execution Guard hooks first, while the release that owns them is still
  # reachable. `guard uninstall` removes only entries carrying this project's
  # signature; an unrelated hook the user wrote in the same file survives.
  local source_dir
  source_dir="$(as_source_dir 2>/dev/null || true)"
  if [ -n "${source_dir}" ] && [ -f "${source_dir}/scripts/guard.py" ]; then
    if python3 "${source_dir}/scripts/guard.py" uninstall >/dev/null 2>&1; then
      as_ok "removed agent-skills-owned Execution Guard hooks"
    fi
  fi

  local row id label global_dir register
  while IFS= read -r row; do
    [ -n "${row}" ] || continue
    id="$(as_row_field "${row}" 1)"
    label="$(as_row_field "${row}" 2)"
    global_dir="$(as_row_field "${row}" 3)"
    register="$(as_row_field "${row}" 4)"
    [ "${register}" = "manual" ] && continue
    [ -d "${HOME}/${global_dir}" ] || continue
    as_unregister_host_dir "${HOME}/${global_dir}"
    if [ "${AS_UNREGISTER_REMOVED}" -gt 0 ]; then
      as_ok "${label}: removed ${AS_UNREGISTER_REMOVED} registration(s) from ~/${global_dir}"
      removed=$((removed + AS_UNREGISTER_REMOVED))
    fi
  done <<EOF
$(as_registry_rows)
EOF

  local dir
  while IFS= read -r dir; do
    [ -n "${dir}" ] || continue
    if as_is_owned_link "${dir}/agent-skills"; then
      rm -f "${dir}/agent-skills"
      as_ok "removed launcher link ${dir}/agent-skills"
    fi
  done <<EOF
$(as_path_link_candidates)
EOF

  local tree
  for tree in ${AS_LINKED_TREES}; do
    if [ -L "${home}/${tree}" ]; then
      rm -f "${home}/${tree}"
    fi
  done
  [ -L "${home}/current" ] && rm -f "${home}/current"
  # Installed release payloads. Only ever inside our own versions/ directory,
  # which nothing but the installer writes to.
  if [ -d "${home}/versions" ]; then
    rm -rf "${home}/versions"
    as_ok "removed installed release payloads"
  fi
  rm -rf "${home}/cache"
  rm -f "${home}/VERSION" "$(as_manifest_path)"
  if [ "${AS_OPT_PURGE:-false}" = "true" ]; then
    rm -rf "${home}/state"
  else
    as_info "kept install history in ${home}/state"
  fi
  rmdir "${home}" 2>/dev/null || as_info "kept ${home} (not empty)"

  if [ "${AS_OPT_PURGE:-false}" = "true" ]; then
    local config_dir
    config_dir="$(as_config_dir)"
    rm -f "${config_dir}/credentials.json" "${config_dir}/bindings.json"
    rm -rf "${config_dir}/secrets"
    rmdir "${config_dir}" 2>/dev/null || true
    as_ok "removed credential metadata and project bindings (--purge)"
    as_info "secrets held in an OS keychain were NOT removed; use: agent-skills access forget"
  else
    as_info "kept credential metadata and project bindings in $(as_config_dir)"
    as_info "add --purge to remove them"
  fi

  printf '\n'
  printf 'Removed %s host registration(s).\n' "${removed}"
  as_info "user memory, repo knowledge, and unrelated skills and hooks were not touched"
  return 0
}

# ------------------------------------------------------------------------------
# hosts report
# ------------------------------------------------------------------------------
as_list_hosts() {
  local as_json="${1:-false}"
  local registered=""
  if as_is_installed; then
    registered="$(as_json_field "$(as_manifest_path)" hosts 2>/dev/null || true)"
  fi

  if [ "${as_json}" = "true" ]; then
    AS_HOSTS_REGISTERED="${registered}" python3 -c '
import json
import os
import sys

registered = set()
raw = os.environ.get("AS_HOSTS_REGISTERED", "")
if raw:
    try:
        registered = set(json.loads(raw))
    except Exception:
        registered = set(raw.split())

rows = []
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    parts = line.split("|")
    if len(parts) < 6:
        continue
    rows.append(
        {
            "id": parts[0],
            "label": parts[1],
            "global_dir": parts[2],
            "register": parts[3],
            "sync_to_cloud": parts[4],
            "notes": parts[5],
            "registered": parts[0] in registered,
        }
    )
json.dump(rows, sys.stdout, indent=2)
sys.stdout.write("\n")
' <<EOF
$(as_registry_rows)
EOF
    return 0
  fi

  printf 'Supported hosts (global discovery)\n\n'
  local row id label global_dir register sync notes state
  while IFS= read -r row; do
    [ -n "${row}" ] || continue
    id="$(as_row_field "${row}" 1)"
    label="$(as_row_field "${row}" 2)"
    global_dir="$(as_row_field "${row}" 3)"
    register="$(as_row_field "${row}" 4)"
    sync="$(as_row_field "${row}" 5)"
    notes="$(as_row_field "${row}" 6)"
    case "${registered}" in
      *"\"${id}\""*) state="registered" ;;
      *) state="not registered" ;;
    esac
    printf '%s (%s)\n' "${label}" "${id}"
    if [ "${global_dir}" = "-" ]; then
      printf '  global dir     : none (IDE settings)\n'
    else
      printf '  global dir     : ~/%s\n' "${global_dir}"
    fi
    printf '  registration   : %s (%s)\n' "${register}" "${state}"
    printf '  reaches cloud  : %s\n' "${sync}"
    printf '  notes          : %s\n\n' "${notes}"
  done <<EOF
$(as_registry_rows)
EOF
}
