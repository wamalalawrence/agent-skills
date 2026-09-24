#!/usr/bin/env python3
"""`agent-skills access setup`: propose a route, or a separate write profile.

A read-only route should stay read-only. When the user wants writes, the safe
change is a **second** server entry, `<name>-write`, that reuses the same
command and switches write mode with whatever that route's own mode rule says:
the upstream's setting (`READ_ONLY_MODE=false`), or a wrapper's own variable
learned by inspection or confirmed by the user. By default it is limited to the
target's space or project (the route's scope filter) and, when one server serves
several systems, to the target system's toolsets; `--all-scopes` lifts only the
first. The read-only entry is left exactly as it was.

Rules this module never bends:

* Nothing is written without an interactive "yes" typed at a terminal. Run by
  an agent (no TTY), it prints the change and the instructions and writes
  nothing. There is no flag or variable that skips the prompt.
* The diff is exact but masked: secret-shaped values appear as
  `<unchanged value of KEY>`. They are copied inside the file, never shown.
* The host file is backed up first and written atomically with its mode kept.
  `--undo` removes only the entry it added (after its own confirmation), so
  later edits to the file survive; the backup stays for anything else.
* A file with comments (JSONC) is never rewritten, because rewriting it would
  drop them; the snippet is printed for the user to paste.
"""
from __future__ import annotations

import copy
import difflib
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

import access_hosts as hosts_mod
import access_registry as reg
import access_state as state
import access_toml
from guard_audit import redact

HISTORY_SCHEMA = "agent-skills.access-setup-history/v1"


def _history_path() -> Path:
    return state.install_home() / "state" / "access" / "setup-history.json"


def _load_history() -> dict:
    try:
        data = json.loads(_history_path().read_text(encoding="utf-8"))
        if data.get("schema") == HISTORY_SCHEMA:
            return data
    except (OSError, ValueError):
        pass
    return {"schema": HISTORY_SCHEMA, "changes": []}


def _save_history(data: dict) -> None:
    path = _history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)


# Set by `--json`: a confirmation prompt hidden inside machine output would be
# answered by nobody, so a JSON run never writes.
FORCE_NONINTERACTIVE = False


def interactive() -> bool:
    return not FORCE_NONINTERACTIVE and sys.stdin.isatty() and sys.stdout.isatty()


def confirm(question: str) -> bool:
    if not interactive():
        return False
    sys.stdout.write(question + " Type 'yes' to apply: ")
    sys.stdout.flush()
    answer = sys.stdin.readline().strip().lower()
    return answer == "yes"


# ---------------------------------------------------------------------------
# Write-mode switch for a route
# ---------------------------------------------------------------------------
def write_switch(route: dict, system: dict) -> Tuple[Optional[dict], str]:
    """({"set_env": {K: V}, "drop_args": [...]}, explanation) or (None, why not)."""
    mode = route.get("mode") or {}
    toggle = mode.get("toggle") or {}
    if toggle.get("env"):
        value = toggle.get("write_when") or ""
        if value == "(any non-empty value)":
            value = "1"
        if value and not value.startswith("("):
            source = "confirmed local knowledge" if mode.get("strength") == "declared" else \
                "the launcher (%s)" % mode.get("source", "inferred")
            return {"set_env": {toggle["env"]: value}, "drop_args": []}, \
                "%s=%s switches write mode, per %s" % (toggle["env"], value, source)
    upstream = next((u for u in system.get("mcp_upstreams", []) if u.get("id") == route.get("upstream")), None)
    if upstream and route.get("via") == "direct":
        change = {"set_env": {}, "drop_args": []}
        for rule in upstream.get("mode_rules", []):
            if rule.get("arg"):
                change["drop_args"].append(rule["arg"])
            elif rule.get("truthy"):
                change["set_env"][rule["env"]] = "false"
            elif rule.get("values"):
                writable = [k for k, v in rule["values"].items() if v == "modify"] or \
                           [k for k, v in rule["values"].items() if v == "read-write"]
                if writable:
                    change["set_env"][rule["env"]] = writable[0]
        if change["set_env"] or change["drop_args"]:
            return change, "upstream %s: %s" % (upstream["id"], ", ".join(
                ["%s=%s" % kv for kv in change["set_env"].items()] + ["drop %s" % a for a in change["drop_args"]]))
    if upstream and route.get("via") == "launcher" and not toggle:
        return None, ("the launcher runs %s but no switch for write mode was found in it; tell me which variable "
                      "enables writes and confirm it with `agent-skills access remember`" % upstream["id"])
    return None, "cannot tell how this route switches to write mode"


# ---------------------------------------------------------------------------
# Building the change
# ---------------------------------------------------------------------------
def _raw_entry(data, fmt: str, route: dict, repo_root: Optional[Path]) -> Tuple[dict, dict]:
    """(container dict holding the server table, the entry) from parsed file data."""
    if fmt == "claude-json":
        if route["scope"] == "local" and repo_root:
            projects = data.get("projects", {})
            for key in (str(repo_root), str(repo_root.resolve())):
                if key in projects:
                    table = projects[key].setdefault("mcpServers", {})
                    return table, table[route["name"]]
        table = data.setdefault("mcpServers", {})
    elif fmt == "codex-toml":
        table = data.setdefault("mcp_servers", {})
    elif fmt == "vscode-servers":
        table = data.setdefault("servers", {})
    elif fmt == "vscode-settings":
        table = data.setdefault("mcp", {}).setdefault("servers", {})
    else:
        table = data.setdefault("mcpServers", {})
    return table, table[route["name"]]


def _secret_values(entry: dict) -> List[Tuple[str, str]]:
    env = entry.get("env") if isinstance(entry.get("env"), dict) else {}
    return [(str(k), str(v)) for k, v in env.items() if hosts_mod.looks_secret(str(k)) and str(v)]


def _mask(text: str, secrets: List[Tuple[str, str]]) -> str:
    for key, value in sorted(secrets, key=lambda kv: -len(kv[1])):
        if len(value) >= 4:
            text = text.replace(value, "<unchanged value of %s>" % key)
    return redact(text)


def _toml_block(name: str, entry: dict) -> str:
    lines = ["", "[mcp_servers.%s]" % access_toml.dump_key(name)]
    for key, value in entry.items():
        if key == "env" or isinstance(value, dict):
            continue
        lines.append("%s = %s" % (access_toml.dump_key(key), _toml_value(value)))
    env = entry.get("env")
    if isinstance(env, dict) and env:
        lines.append("")
        lines.append("[mcp_servers.%s.env]" % access_toml.dump_key(name))
        for key, value in env.items():
            lines.append("%s = %s" % (access_toml.dump_key(str(key)), _toml_value(value)))
    return "\n".join(lines) + "\n"


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    return access_toml.dump_string(str(value))


def scope_requirement(route: dict, system: dict) -> Optional[dict]:
    """The scope filter a write profile for this route is limited by, if any.

    {"key": CONFLUENCE_SPACES_FILTER, "kind": "space"} for an upstream that can
    filter by space or project; None when the route has no such setting (the
    profile then covers everything the account may write, and says so).
    """
    upstream = _upstream_of(route, system)
    for key, kind in (upstream or {}).get("scope_filters", {}).items():
        return {"key": key, "kind": kind}
    return None


def _upstream_of(route: dict, system: dict) -> Optional[dict]:
    return next((u for u in system.get("mcp_upstreams", []) if u.get("id") == route.get("upstream")), None)


def plan_write_profile(route: dict, system: dict, scope_value: str, repo_root: Optional[Path],
                       all_scopes: bool = False) -> dict:
    """Propose `<name>-write`, limited by default.

    Limits, in order: the target's space or project (the route's scope filter),
    and the target system's toolsets when the upstream serves several systems
    from one server (a Confluence write profile must not also write to Jira).
    `all_scopes` is the explicit opt-out of the first; there is none for the
    second, because a profile made for one system has no business in another.
    """
    path = Path(route["file"])
    fmt = hosts_mod.format_of(route["host"], path)
    text = path.read_text(encoding="utf-8")
    switch, why = write_switch(route, system)
    if switch is None:
        return {"ok": False, "reason": why}
    data = hosts_mod.load_raw(path, fmt)
    table, entry = _raw_entry(data, fmt, route, repo_root)
    new_name = "%s-write" % route["name"]
    if new_name in table:
        return {"ok": False, "reason": "a server named %r already exists in %s; check it with `agent-skills access check`"
                % (new_name, path)}
    new_entry = copy.deepcopy(entry)
    env = new_entry.get("env") if isinstance(new_entry.get("env"), dict) else {}
    env.update(switch["set_env"])
    upstream = _upstream_of(route, system)
    requirement = scope_requirement(route, system)
    limits = []
    if requirement and not all_scopes:
        if not scope_value:
            return {"ok": False, "needs_scope": True, "reason": (
                "a write profile is limited to one %s by default. Name the target (--target <url-or-key>) or the "
                "%s (--scope <key>); --all-scopes removes the limit" % (requirement["kind"], requirement["kind"]))}
        env[requirement["key"]] = scope_value
        limits.append("%s %s only (%s=%s)" % (requirement["kind"], scope_value, requirement["key"], scope_value))
    elif scope_value and not requirement:
        return {"ok": False, "reason": "this route has no scope filter setting to narrow"}
    elif requirement and all_scopes:
        limits.append("every %s the account can write (--all-scopes)" % requirement["kind"])
    else:
        limits.append("everything the account can write: this route has no scope filter")
    toolsets = (upstream or {}).get("toolset_filters", {})
    if toolsets.get("system_toolsets"):
        env[toolsets["env"][0]] = ",".join(toolsets["system_toolsets"])
        limits.append("%s tools only (%s)" % (system["id"], toolsets["env"][0]))
    if env:
        new_entry["env"] = env
    if isinstance(new_entry.get("args"), list):
        new_entry["args"] = _drop_flags(new_entry["args"], switch["drop_args"], toolsets.get("args", [])
                                        if toolsets.get("system_toolsets") else [])
    secrets = _secret_values(entry)
    if fmt == "codex-toml":
        new_text = text.rstrip("\n") + "\n" + _toml_block(new_name, new_entry)
        writable = True
    elif fmt.startswith("vscode") and hosts_mod._strip_jsonc(text) != text:
        new_text = None
        writable = False
    else:
        table[new_name] = new_entry
        new_text = json.dumps(data, indent=2) + "\n"
        writable = True
    snippet_obj = {new_name: new_entry}
    snippet = _toml_block(new_name, new_entry) if fmt == "codex-toml" else json.dumps(snippet_obj, indent=2)
    diff = ""
    if new_text is not None:
        diff = "".join(difflib.unified_diff(_mask(text, secrets).splitlines(True), _mask(new_text, secrets).splitlines(True),
                                            fromfile=str(path), tofile=str(path) + " (proposed)"))
    return {"ok": True, "why": why, "limits": limits, "file": str(path), "format": fmt, "new_name": new_name, "writable": writable,
            "new_text": new_text, "diff": diff, "snippet": _mask(snippet, secrets), "host": route["host"],
            "server": route["name"]}


def _drop_flags(args: List[str], bare: List[str], with_value: List[str]) -> List[str]:
    """Remove `--read-only`-style flags, and `--toolsets <v>` / `--toolsets=<v>` pairs."""
    out = []
    skip = False
    for arg in args:
        if skip:
            skip = False
            continue
        if arg in bare:
            continue
        if arg in with_value:
            skip = True
            continue
        if any(arg.startswith(flag + "=") for flag in with_value):
            continue
        out.append(arg)
    return out


def apply_change(plan: dict) -> Tuple[bool, str]:
    path = Path(plan["file"])
    stamp = time.strftime("%Y%m%dT%H%M%S")
    backup = path.with_name("%s.agent-skills-backup-%s" % (path.name, stamp))
    mode = path.stat().st_mode & 0o777
    shutil.copy2(str(path), str(backup))
    os.chmod(str(backup), mode & 0o700 if mode & 0o700 else 0o600)
    tmp = path.with_name(".%s.agent-skills-tmp" % path.name)
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode or 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(plan["new_text"])
    os.chmod(str(tmp), mode or 0o600)
    os.replace(str(tmp), str(path))
    history = _load_history()
    history["changes"].append({"file": str(path), "backup": str(backup), "host": plan["host"],
                               "server": plan["new_name"], "created": state.utc_now()})
    _save_history(history)
    return True, str(backup)


def _remove_entry(text: str, fmt: str, name: str) -> Optional[str]:
    """The file text without server `name`, or None if it is not there.

    Only the entry `setup` added is removed. Everything else in the file -
    including edits made after the write profile was added - stays as it is.
    """
    if fmt == "codex-toml":
        lines = text.splitlines(True)
        key = access_toml.dump_key(name)
        heads = ("[mcp_servers.%s]" % key, "[mcp_servers.%s." % key)
        out, dropping, found = [], False, False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("["):
                dropping = stripped == heads[0] or stripped.startswith(heads[1])
                found = found or dropping
            if not dropping:
                out.append(line)
        if not found:
            return None
        new = "".join(out).rstrip("\n") + "\n"
        before = access_toml.loads(text).get("mcp_servers", {})
        after = access_toml.loads(new).get("mcp_servers", {})
        before.pop(name, None)
        if before != after:
            raise ValueError("removing %r would change other servers; not touching the file" % name)
        return new
    data = json.loads(text)
    tables = [data.get("mcpServers"), (data.get("mcp") or {}).get("servers") if isinstance(data.get("mcp"), dict)
              else None, data.get("servers")]
    for project in (data.get("projects") or {}).values() if isinstance(data.get("projects"), dict) else []:
        if isinstance(project, dict):
            tables.append(project.get("mcpServers"))
    for table in tables:
        if isinstance(table, dict) and name in table:
            del table[name]
            return json.dumps(data, indent=2) + "\n"
    return None


def undo(host: Optional[str]) -> int:
    history = _load_history()
    candidates = [c for c in history["changes"] if not host or c["host"] == host]
    if not candidates:
        print("Nothing to undo%s: no change made by `access setup` is recorded." % (" for %s" % host if host else ""))
        return 0
    change = candidates[-1]
    path = Path(change["file"])
    fmt = hosts_mod.format_of(change["host"], path)
    try:
        text = path.read_text(encoding="utf-8")
        new_text = _remove_entry(text, fmt, change["server"])
    except (OSError, ValueError, access_toml.TomlSubsetError) as exc:
        print("Cannot undo automatically (%s). The backup from before the change is %s." % (exc, change["backup"]),
              file=sys.stderr)
        return 1
    if new_text is None:
        print("Server %r is no longer in %s; nothing to undo." % (change["server"], path))
        history["changes"].remove(change)
        _save_history(history)
        return 0
    entry_secrets = []
    try:
        entry_secrets = _secret_values(_find_entry(text, fmt, change["server"]) or {})
    except (ValueError, access_toml.TomlSubsetError):
        pass
    diff = "".join(difflib.unified_diff(_mask(text, entry_secrets).splitlines(True),
                                        _mask(new_text, entry_secrets).splitlines(True),
                                        fromfile=str(path), tofile=str(path) + " (after undo)"))
    print("This removes server %r from %s. Nothing else in the file changes." % (change["server"], path))
    print(redact(diff))
    if not interactive():
        print("Not a terminal: nothing was changed. Run this command yourself in a terminal to confirm it.")
        return 1
    if not confirm("Remove it?"):
        print("Nothing changed.")
        return 1
    mode = path.stat().st_mode & 0o777
    tmp = path.with_name(".%s.agent-skills-tmp" % path.name)
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode or 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(new_text)
    os.chmod(str(tmp), mode or 0o600)
    os.replace(str(tmp), str(path))
    history["changes"].remove(change)
    _save_history(history)
    print("Removed. %s" % hosts_mod.RELOAD_HINTS.get(change["host"], "Reload the host's MCP servers."))
    return 0


def _find_entry(text: str, fmt: str, name: str) -> Optional[dict]:
    data = access_toml.loads(text) if fmt == "codex-toml" else json.loads(text)
    for table in (data.get("mcp_servers"), data.get("mcpServers"), data.get("servers")):
        if isinstance(table, dict) and isinstance(table.get(name), dict):
            return table[name]
    return None


def approval_note(host: str, name: str) -> str:
    if host == "claude-code":
        return ("Claude Code asks before each MCP tool call unless the tool is on your permissions allow list; keep "
                "mcp__%s__* off that list so every write is asked." % name)
    return ("Agent Skills does not know a per-tool approval setting for %s; if it has one, keep the %s server's tools "
            "on ask." % (hosts_mod.HOST_LABELS.get(host, host), name))


def setup_steps(system: dict, host: str) -> str:
    """What to do when there is no route: printed only, never written."""
    lines = ["Setting up a route for %s in %s (nothing below is applied for you)" % (
        system["id"], hosts_mod.HOST_LABELS.get(host, host or "your assistant"))]
    upstreams = [u for u in system.get("mcp_upstreams", []) if u.get("default_mode") != "unknown"] or \
        system.get("mcp_upstreams", [])
    if upstreams:
        up = upstreams[0]
        lines.append("1. Add an MCP server for %s (%s). Start it read-only:" % (system["id"], up.get("label", up["id"])))
        for rule in up.get("mode_rules", []):
            if rule.get("env") and rule.get("truthy"):
                lines.append("     %s=true" % rule["env"])
                break
        for key in up.get("base_url_env", [])[:1]:
            lines.append("     %s=<your site's base URL>" % key)
        cred = up.get("credential_env", [])[:1]
        if cred:
            lines.append("   Supply %s from your OS credential store through a small launcher script, not as a "
                         "literal in the host config." % cred[0])
        files = hosts_mod.config_files(host, None) if host else []
        if files:
            lines.append("   Host config: %s" % files[0][1])
    for cli in system.get("cli_routes", []):
        lines.append("%s. Or log in to the %s: `%s auth login` (or its equivalent), then `%s`." % (
            len(lines), cli.get("label", cli["command"]), cli["command"], " ".join([cli["command"]] + cli["auth_probe"])))
    if host:
        lines.append("Then: %s" % hosts_mod.RELOAD_HINTS.get(host, "reload the host"))
    lines.append("Then run `agent-skills access check --system %s --op <op>` again." % system["id"])
    lines.append("Docs: %s" % system.get("docs", "docs/access/README.md"))
    return "\n".join(lines)
