#!/usr/bin/env bash
# agent-skills global installer.
#
# Owns exactly four verbs: install, verify, uninstall, and the host
# registration underneath them. `lib/runtime.sh` must be sourced first.
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
# Host registration
# ------------------------------------------------------------------------------
# Register every skill into one host directory.
# Sets AS_REGISTER_CREATED / AS_REGISTER_KEPT / AS_REGISTER_CONFLICTS.
as_register_host_dir() {
  local source_dir="$1"
  local skills_dir="$2"
  AS_REGISTER_CREATED=0
  AS_REGISTER_KEPT=0
  AS_REGISTER_CONFLICTS=""

  mkdir -p "${skills_dir}" 2>/dev/null || return 1

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
# Manifest
# ------------------------------------------------------------------------------
as_write_manifest() {
  local source_dir="$1"
  local hosts="$2"
  local cli_link="$3"
  local version git_sha manifest
  version="$(as_read_version_file "${source_dir}/VERSION" || printf 'unknown')"
  git_sha=""
  if command -v git >/dev/null 2>&1 && [ -d "${source_dir}/.git" ]; then
    git_sha="$(cd "${source_dir}" && git rev-parse --short=12 HEAD 2>/dev/null || true)"
  fi
  manifest="$(as_manifest_path)"

  AS_MF_VERSION="${version}" \
  AS_MF_SHA="${git_sha}" \
  AS_MF_SOURCE="${source_dir}" \
  AS_MF_HOME="$(as_home)" \
  AS_MF_HOSTS="${hosts}" \
  AS_MF_CLI="${cli_link}" \
  AS_MF_PATH="${manifest}" \
  python3 -c '
import json
import os

hosts = [h for h in os.environ.get("AS_MF_HOSTS", "").split() if h]
home = os.environ["AS_MF_HOME"]
payload = {
    "schema": "agent-skills.install/v1",
    "version": os.environ.get("AS_MF_VERSION", ""),
    "git_sha": os.environ.get("AS_MF_SHA", ""),
    "source_dir": os.environ["AS_MF_SOURCE"],
    "home": home,
    "canonical_skills_dir": os.path.join(home, "skills"),
    "hosts": hosts,
    "cli_link": os.environ.get("AS_MF_CLI", ""),
    "installed_at": __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "installed_by": "agent-skills install " + os.environ.get("AS_MF_VERSION", ""),
}
target = os.environ["AS_MF_PATH"]
with open(target, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2)
    handle.write("\n")
os.chmod(target, 0o644)
'
}

# ------------------------------------------------------------------------------
# install
# ------------------------------------------------------------------------------
# Options are passed as environment variables so the CLI stays the only place
# that parses flags:
#   AS_OPT_HOSTS       comma-separated allow-list, empty means auto-detect
#   AS_OPT_ALL_HOSTS   "true" registers every linkable host
#   AS_OPT_NO_PATH     "true" skips the PATH link
as_install_global() {
  local source_dir home version
  source_dir="$(as_source_dir 2>/dev/null || true)"
  if [ -z "${source_dir}" ]; then
    as_die "cannot locate an agent-skills source tree. Run this from a clone, or set AGENT_SKILLS_SOURCE." 2
  fi
  home="$(as_home)"
  version="$(as_read_version_file "${source_dir}/VERSION" || printf 'unknown')"

  # Hard prerequisites, checked before anything is written. Both of these used to
  # fail silently mid-install and still print "installed globally": the host loop
  # and the manifest writer are both driven through `$(...)`, which discards the
  # exit status of whatever ran inside.
  command -v python3 >/dev/null 2>&1 \
    || as_die "python3 is required to install agent-skills (it writes the install manifest and resolves access)" 2
  as_registry_path >/dev/null 2>&1 \
    || as_die "host registry not found; this source tree is incomplete (expected lib/hosts.registry)" 2
  [ -n "$(as_registry_rows)" ] \
    || as_die "host registry is empty; this source tree is incomplete (expected lib/hosts.registry)" 2

  printf 'Installing agent-skills %s\n' "${version}"
  printf '  source: %s\n' "${source_dir}"
  printf '  home:   %s\n' "${home}"
  printf '\n'

  mkdir -p "${home}" || as_die "cannot create ${home}" 2
  mkdir -p "$(as_config_dir)" || as_die "cannot create $(as_config_dir)" 2
  chmod 700 "$(as_config_dir)" 2>/dev/null || true

  # One canonical realpath per tree. Everything downstream — host adapters, the
  # CLI, skill references — resolves through these five links.
  printf 'Canonical trees\n'
  local tree status conflicts=""
  for tree in ${AS_LINKED_TREES}; do
    [ -e "${source_dir}/${tree}" ] || continue
    status="$(as_link_path "${source_dir}/${tree}" "${home}/${tree}")"
    case "${status}" in
      conflict)
        as_fail "${home}/${tree} exists and is not managed by agent-skills"
        conflicts="${conflicts}${tree} "
        ;;
      *) as_ok "${tree} -> ${source_dir}/${tree} (${status})" ;;
    esac
  done
  if [ -n "${conflicts}" ]; then
    as_die "refusing to overwrite unmanaged paths in ${home}: ${conflicts}" 2
  fi
  printf '%s\n' "${version}" > "${home}/VERSION"

  # Host registration.
  printf '\nHost integrations\n'
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

  # CLI launcher.
  printf '\nCommand line\n'
  local cli_link=""
  if [ "${AS_OPT_NO_PATH:-false}" = "true" ]; then
    as_info "PATH link skipped (--no-path-link)"
  elif as_link_cli; then
    cli_link="${AS_CLI_LINK}"
    if [ "${AS_CLI_ON_PATH}" = "yes" ]; then
      as_ok "agent-skills -> ${cli_link}"
    else
      as_warn "linked ${cli_link} but its directory is not on PATH"
      printf '        Add this line to your shell profile:\n'
      printf '          export PATH="%s:$PATH"\n' "$(dirname "${cli_link}")"
    fi
  else
    as_warn "no writable PATH directory found; use ${home}/bin/agent-skills directly"
  fi

  # The manifest is what every later command reads to decide whether this machine
  # is installed at all, so a failed write must not reach the success banner.
  as_write_manifest "${source_dir}" "${registered}" "${cli_link}" \
    || as_die "could not write the install manifest at $(as_manifest_path)" 2
  [ -s "$(as_manifest_path)" ] \
    || as_die "install manifest missing or empty at $(as_manifest_path)" 2

  printf '\n'
  printf 'Agent Skills v%s installed globally.\n' "${version}"
  printf '\n'
  printf 'Skills are available to:\n'
  as_print_host_summary "${registered}"
  printf '\n'
  printf 'No credentials were requested or stored.\n'
  printf 'External-service access is configured only when a task requires it.\n'
  printf '\n'
  printf 'Next:\n'
  printf '  cd into any repository on this machine and invoke a skill.\n'
  printf '  agent-skills doctor    what this environment can actually do\n'
  printf '  agent-skills verify    re-check this installation\n'
  printf '  agent-skills update    apply a new release\n'
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
as_verify_install() {
  local errors=0
  local home source_dir manifest
  home="$(as_home)"
  manifest="$(as_manifest_path)"

  printf 'agent-skills verify\n'
  printf '  home: %s\n\n' "${home}"

  if [ ! -f "${manifest}" ]; then
    as_fail "no install manifest at ${manifest}"
    printf '        Run: ./setup.init   (or: agent-skills install)\n' >&2
    return 1
  fi

  local installed_version source_version
  installed_version="$(as_installed_version || printf 'unknown')"
  as_ok "install manifest present (v${installed_version})"

  source_dir="$(as_source_dir 2>/dev/null || true)"
  if [ -z "${source_dir}" ]; then
    as_fail "canonical source tree is unreachable; the clone may have been moved or deleted"
    errors=$((errors + 1))
  else
    as_ok "canonical source: ${source_dir}"
    source_version="$(as_read_version_file "${source_dir}/VERSION" || printf 'unknown')"
    if [ "${source_version}" != "${installed_version}" ]; then
      as_warn "version drift: manifest v${installed_version}, source v${source_version}"
      printf '        Run: agent-skills install   (re-links and refreshes the manifest)\n' >&2
    else
      as_ok "no version drift (source and manifest both v${source_version})"
    fi
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
  local row id label global_dir register skill_count linked stale foreign entry name
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
    return 1
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
  rm -f "${home}/VERSION" "$(as_manifest_path)"
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
  printf 'Removed %s host registration(s). The source clone was not touched.\n' "${removed}"
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
