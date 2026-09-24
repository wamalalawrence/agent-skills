#!/usr/bin/env python3
"""Access Discovery: can this host do *this* operation on *this* target, and via what?

"MCP configured" used to be the whole answer. It collapsed seven questions into
one bit, and any "no" among them surfaced late, after work had been done. This
module asks them one at a time, for one (system, operation, target) triple:

    L1 route    is there a route for this system in the current host?
    L2 launch   can it start?
    L3 auth     is a credential present (and, with --probe, accepted)?
    L4 mode     does the route's mode allow this operation?
    L5 target   is the target inside the route's scope, and permitted?
    L6 intent   did the user ask for this operation on this target?
    L7 policy   does policy allow it, and what confirmation does it need?

Each rung reports pass | fail | unknown | skipped, the evidence, and how strong
that evidence is: `verified` (probe or live introspection), `declared`
(explicit configuration or user-confirmed local knowledge), or `inferred`
(wrapper inspection or naming heuristics). `unknown` is never shown as `pass`,
and a write that leans on an inferred mode or scope needs the user to confirm
it before anyone relies on it.

A found credential never becomes a route here. A browser is never a write
route for a system that has an API. The CLI supplies the facts and the fix
options; Wamala presents them and follows the user's choice.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import access_creds as creds
import access_hosts as hosts_mod
import access_inspect as inspect_mod
import access_registry as reg
import access_state as state
from guard_audit import redact

SCHEMA_CHECK = "agent-skills.access-check/v1"
SCHEMA_SCAN = "agent-skills.access-scan/v1"

RUNGS = ("route", "launch", "auth", "mode", "target", "intent", "policy")

# Exit codes. 0/2/3/4 keep their CLI-wide meanings (lib/asrelease/exits.py);
# 11 is the one code this release adds; 1 keeps the Access Resolver's meaning,
# "not resolved - the report says what the user needs to decide or do".
EXIT_OK = 0
EXIT_NEEDS_USER = 1
EXIT_USAGE = 2
EXIT_AUTH = 3
EXIT_NETWORK = 4
EXIT_CAPABILITY = 11

# A launcher run through its interpreter (`bash ~/bin/w.sh`, `python3 w.py`):
# the script is the first argument that is not an option.
INTERPRETERS = {"bash", "sh", "zsh", "dash", "python", "python3", "node"}

RUNTIMES = {"uvx": "uvx", "npx": "npx", "docker": "docker", "podman": "podman", "pipx": "pipx",
            "python-module": "python3", "node": "node"}


def repo_root(cwd: Path) -> Optional[Path]:
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=str(cwd), capture_output=True,
                             text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    top = out.stdout.strip()
    return Path(top) if out.returncode == 0 and top else None


def _r(text: str) -> str:
    return redact(str(text)) if text else ""


def _tilde(path: str) -> str:
    home = os.environ.get("HOME") or ""
    # Resolved paths (a launcher's real location) carry the resolved home, which
    # differs from $HOME wherever a parent is a symlink (/var on macOS).
    for base in (home, os.path.realpath(home) if home else ""):
        if base and path.startswith(base + "/"):
            return "~" + path[len(base):]
    return path


# ---------------------------------------------------------------------------
# Scan: every route this machine has, statically
# ---------------------------------------------------------------------------
class Scanner:
    def __init__(self, cwd: Path, systems: Optional[Dict[str, dict]] = None):
        self.cwd = cwd
        self.root = repo_root(cwd) or cwd
        self.systems = systems if systems is not None else reg.load_systems()
        self.knowledge = state.load_routes()
        self._inspections: Dict[str, dict] = {}

    def inspect(self, command: str) -> dict:
        if command not in self._inspections:
            self._inspections[command] = inspect_mod.inspect_launcher(command, self.systems)
        return self._inspections[command]

    def _value_policy(self, extra: set):
        allowed = reg.all_mode_keys(self.systems) | extra
        for route in self.knowledge.get("routes", []):
            mode = route.get("mode") or {}
            if mode.get("env"):
                allowed.add(mode["env"])
        return hosts_mod.default_value_policy(allowed)

    def read(self, host_ids: List[str]) -> List[dict]:
        first = hosts_mod.read_hosts(host_ids, self.root, self._value_policy(set()))
        extra = set()
        for report in first:
            for server in report["servers"]:
                if server["command"] and not self._known_upstream(server):
                    toggle = ((self.inspect(launcher_path(server)).get("mode") or {}).get("toggle") or {})
                    if toggle.get("env") and not hosts_mod.looks_secret(toggle["env"]):
                        extra.add(toggle["env"])
        if not extra:
            return first
        return hosts_mod.read_hosts(host_ids, self.root, self._value_policy(extra))

    def _known_upstream(self, server: dict) -> Optional[Tuple[str, dict]]:
        for sid, system in self.systems.items():
            upstream = reg.match_upstream(system, server["command"], server["args"], server["url"])
            if upstream:
                return sid, upstream
        return None

    # -- one MCP server -> one route per system it serves ----------------------
    def qualify(self, server: dict) -> List[dict]:
        host = server["host"]
        known = self._known_upstream(server)
        local = state.match_route(self.knowledge, host, server["server_name"], launcher_path(server))
        inspection = None
        via = "direct"
        upstream = None
        system_ids: List[str] = []
        if known:
            upstream = known[1]
            system_ids = [sid for sid, s in self.systems.items()
                          if reg.match_upstream(s, server["command"], server["args"], server["url"]) is upstream
                          or any(u.get("id") == upstream["id"] for u in s.get("mcp_upstreams", []))]
        elif server["command"]:
            inspection = self.inspect(launcher_path(server))
            if inspection["kind"] != "missing":
                via = "launcher"
            if inspection.get("upstream"):
                upstream = self._upstream_by_id(inspection["upstream"]["id"])
            system_ids = list(inspection.get("system_ids") or [])
        if local and local.get("systems"):
            system_ids = list(local["systems"])
            if local.get("upstream") and upstream is None:
                upstream = self._upstream_by_id(local["upstream"])
        if not system_ids:
            system_ids = reg.systems_for_hint(self.systems, " ".join(
                [server["server_name"], server["command"], server["url"]] + server["args"]))
        stale = bool(local and state.is_stale(local, (inspection or {}).get("sha256", ""),
                                              state.entry_fingerprint(server["command"], server["args"])))
        routes = []
        for sid in system_ids:
            system = self.systems.get(sid)
            if not system:
                continue
            routes.append(self._route(server, system, upstream, via, inspection, local, stale))
        return routes

    def _upstream_by_id(self, upstream_id: str) -> Optional[dict]:
        for system in self.systems.values():
            for upstream in system.get("mcp_upstreams", []):
                if upstream.get("id") == upstream_id:
                    return upstream
        return None

    def _route(self, server, system, upstream, via, inspection, local, stale) -> dict:
        env = server["env_values"]
        args = server["args"]
        route = {
            "kind": "mcp", "host": server["host"], "scope": server["scope"], "file": server["file"],
            "name": server["server_name"], "system": system["id"], "transport": server["transport"],
            "command": server["command"], "args": list(server["args"]),
            "launcher_command": launcher_path(server), "url": server["url"],
            "via": via,
            "upstream": upstream["id"] if upstream else None,
            "upstream_label": upstream.get("label", upstream["id"]) if upstream else None,
            "disabled": server["disabled"],
            "launcher": None, "knowledge": None, "plaintext_secret_keys": server["plaintext_secret_keys"],
            "env_keys": server["env_keys"],
        }
        if inspection and inspection["kind"] != "missing":
            route["launcher"] = {"path": inspection["resolved"], "user_local": inspection["user_local"],
                                 "kind": inspection["kind"], "sha256": inspection["sha256"],
                                 "launcher": inspection["launcher"], "executable": inspection.get("executable", False)}
        if local:
            route["knowledge"] = {"confirmed_by_user": local.get("confirmed_by_user", ""), "stale": stale,
                                  "source": local.get("source", "")}
        route["mode"] = self._mode(server, upstream, inspection, local, stale)
        route["tool_filter"] = self._list_setting(env, args, upstream, "tool_filters")
        route["toolsets"] = self._list_setting(env, args, upstream, "toolset_filters")
        route["scope_filters"] = {}
        for key, kind in (upstream or {}).get("scope_filters", {}).items():
            if env.get(key, "").strip():
                route["scope_filters"][key] = {"kind": kind, "values": _split(env[key]), "strength": "declared"}
        route["base_url"] = self._base_url(server, upstream, inspection, local)
        route["credential_refs"] = list((inspection or {}).get("credential_refs") or [])
        if local and local.get("credential_locator"):
            loc = local["credential_locator"]
            route["credential_refs"].insert(0, {"kind": loc.get("kind", ""), "locator": loc.get("name", ""),
                                                "line": "local knowledge"})
        cred_keys = [k for k in server["env_keys"] if k in (upstream or {}).get("credential_env", [])
                     or hosts_mod.looks_secret(k)]
        route["host_credential_keys"] = cred_keys
        route["runtime"] = self._runtime(server, inspection)
        return route

    def _mode(self, server, upstream, inspection, local, stale) -> dict:
        env = server["env_values"]
        args = server["args"]
        explicit = self._explicit_upstream_mode(server, upstream)
        if explicit and explicit["value"] == "read-only":
            # A read-only setting the route itself declares outranks anything
            # remembered or self-reported: it is what the server will do.
            return explicit
        if local and local.get("trusted_self_report") and server["command"] and not stale:
            reported = inspect_mod.self_report(server["command"])
            if not reported.get("error"):
                return {"value": reported["mode"], "strength": "declared",
                        "evidence": "the launcher reports %s (%s); you marked it trusted to self-report" % (
                            reported["mode"], reported.get("mode_source", "no source given"))}
        if local and local.get("mode") and not stale:
            rule = local["mode"]
            if rule.get("value"):
                return {"value": rule["value"], "strength": "declared",
                        "evidence": "confirmed local knowledge (%s)" % local.get("confirmed_by_user", "")}
            if rule.get("env"):
                current = env.get(rule["env"])
                if current is not None and current == str(rule.get("write_when", "")):
                    value = "read-write"
                else:
                    value = rule.get("default", "unknown")
                shown = "%s=%s" % (rule["env"], current) if current is not None else "%s unset" % rule["env"]
                return {"value": value, "strength": "declared", "toggle": {"env": rule["env"],
                        "write_when": rule.get("write_when", "")},
                        "evidence": "confirmed local knowledge: %s unless %s=%s; host config has %s" % (
                            rule.get("default", "?"), rule["env"], rule.get("write_when", "?"), shown)}
        if upstream and server["command"] and inspection is None:
            for rule in upstream.get("mode_rules", []):
                if rule.get("arg") and rule["arg"] in args:
                    return {"value": rule["mode"], "strength": "declared",
                            "evidence": "%s in the server's args (%s)" % (rule["arg"], _tilde(server["file"]))}
                if rule.get("env") and rule["env"] in env:
                    value = inspect_mod._rule_mode(rule, env[rule["env"]])
                    return {"value": value, "strength": "declared",
                            "evidence": "%s=%s in %s" % (rule["env"], env[rule["env"]], _tilde(server["file"]))}
            default = upstream.get("default_mode", "unknown")
            return {"value": default, "strength": "declared" if default != "unknown" else "inferred",
                    "evidence": "no mode setting in the host config; upstream default is %s%s" % (
                        default, (" (%s)" % upstream["mode_note"]) if upstream.get("mode_note") else "")}
        if upstream and server["url"] and not server["command"]:
            return {"value": upstream.get("default_mode", "unknown"), "strength": "inferred",
                    "evidence": upstream.get("mode_note", "remote server; its mode is not visible locally")}
        if inspection and inspection["kind"] == "script":
            mode = inspection.get("mode")
            path = _tilde(inspection["resolved"])
            if not mode:
                return {"value": "unknown", "strength": "inferred",
                        "evidence": "launcher %s sets no mode that could be read" % path}
            toggle = mode.get("toggle") or {}
            value = mode["default"]
            shown = ""
            if toggle.get("env"):
                current = env.get(toggle["env"])
                shown = "; host config %s" % ("sets %s=%s" % (toggle["env"], current) if current is not None
                                              else "does not set %s" % toggle["env"])
                if current is not None:
                    if "write_when" in toggle and toggle["write_when"] == "(any non-empty value)":
                        value = "read-write" if current.strip() else mode["default"]
                    elif "write_when" in toggle:
                        value = "read-write" if current == toggle["write_when"] else mode["default"]
                    elif "readonly_when" in toggle:
                        hit = current.strip() if toggle["readonly_when"] == "(any non-empty value)" \
                            else current == toggle["readonly_when"]
                        value = "read-only" if hit else "read-write"
            lines = ", ".join(str(n) for n in mode.get("lines", []))
            result = {"value": value, "strength": "inferred",
                      "evidence": "launcher %s: %s%s" % (path, mode["summary"], shown),
                      "source": "%s line %s" % (path, lines)}
            if toggle.get("env"):
                result["toggle"] = {"env": toggle["env"], "write_when": toggle.get("write_when", ""),
                                    "readonly_when": toggle.get("readonly_when", "")}
            return result
        if inspection and inspection["kind"] == "opaque-binary":
            return {"value": "unknown", "strength": "inferred",
                    "evidence": "launcher %s is a binary; its mode cannot be read" % _tilde(inspection["resolved"])}
        return {"value": "unknown", "strength": "inferred", "evidence": "the server is not a known upstream"}

    @staticmethod
    def _explicit_upstream_mode(server, upstream) -> Optional[dict]:
        if not upstream:
            return None
        for rule in upstream.get("mode_rules", []):
            if rule.get("arg") and rule["arg"] in server["args"]:
                return {"value": rule["mode"], "strength": "declared",
                        "evidence": "%s in the server's args (%s)" % (rule["arg"], _tilde(server["file"]))}
            if rule.get("env") and rule["env"] in server["env_values"]:
                value = inspect_mod._rule_mode(rule, server["env_values"][rule["env"]])
                return {"value": value, "strength": "declared", "evidence": "%s=%s in %s" % (
                    rule["env"], server["env_values"][rule["env"]], _tilde(server["file"]))}
        return None

    @staticmethod
    def _list_setting(env: dict, args: List[str], upstream: Optional[dict], key: str) -> Optional[dict]:
        spec = (upstream or {}).get(key) or {}
        for name in spec.get("env", []):
            if env.get(name, "").strip():
                return {"source": name, "values": _split(env[name]), "strength": "declared"}
        for flag in spec.get("args", []):
            for i, arg in enumerate(args):
                if arg == flag and i + 1 < len(args):
                    return {"source": flag, "values": _split(args[i + 1]), "strength": "declared"}
                if arg.startswith(flag + "="):
                    return {"source": flag, "values": _split(arg.split("=", 1)[1]), "strength": "declared"}
        return None

    @staticmethod
    def _base_url(server, upstream, inspection, local) -> Optional[dict]:
        for key in (upstream or {}).get("base_url_env", []):
            if server["env_values"].get(key):
                return {"value": server["env_values"][key], "strength": "declared", "source": key}
        if local and local.get("base_url"):
            return {"value": local["base_url"], "strength": "declared", "source": "local knowledge"}
        for url in (inspection or {}).get("base_urls", []):
            if url["key"] in (upstream or {}).get("base_url_env", []) or not upstream:
                return {"value": url["value"], "strength": "inferred",
                        "source": "launcher line %d" % url["line"]}
        if (inspection or {}).get("base_urls"):
            url = inspection["base_urls"][0]
            return {"value": url["value"], "strength": "inferred", "source": "launcher line %d" % url["line"]}
        if server["url"]:
            return {"value": server["url"], "strength": "declared", "source": "server url"}
        return None

    @staticmethod
    def _runtime(server, inspection) -> dict:
        command = server["command"]
        if not command:
            return {"status": "remote", "evidence": "remote server; nothing starts locally"}
        path = inspect_mod.resolve_command(command)
        if path is None:
            return {"status": "fail", "evidence": "command %s not found" % command}
        if not os.access(str(path), os.X_OK):
            return {"status": "fail", "evidence": "%s is not executable" % _tilde(str(path))}
        needed = ""
        base = os.path.basename(command)
        if base in RUNTIMES.values():
            needed = ""
        elif inspection and inspection.get("launcher"):
            needed = RUNTIMES.get(inspection["launcher"], "")
        if needed and shutil.which(needed) is None:
            return {"status": "fail", "evidence": "the launcher runs %s, which is not installed" % needed}
        what = "launcher executable" if inspection else "%s found" % base
        return {"status": "pass", "evidence": what + ("; %s available" % needed if needed else "")}

    # -- all routes -------------------------------------------------------------
    def scan(self, host_ids: List[str]) -> dict:
        reports = self.read(host_ids)
        routes = []
        warnings = []
        for report in reports:
            for f in report["files"]:
                if f["status"] == "error":
                    warnings.append("%s: %s is unreadable (%s); its servers are unknown, not absent"
                                    % (report["host"], _tilde(f["path"]), f.get("error", "")))
                if f.get("group_or_world_readable"):
                    warnings.append("%s: %s is readable by other users (mode %s)"
                                    % (report["host"], _tilde(f["path"]), f.get("mode")))
            for server in report["servers"]:
                if server["plaintext_secret_keys"]:
                    warnings.append("%s: server %r in %s holds a plaintext secret in %s; prefer a launcher that "
                                    "reads it from a secret store" % (report["host"], server["server_name"],
                                                                     _tilde(server["file"]),
                                                                     ", ".join(server["plaintext_secret_keys"])))
                routes.extend(self.qualify(server))
        for sid, system in self.systems.items():
            for cli in system.get("cli_routes", []):
                if shutil.which(cli["command"]):
                    routes.append({"kind": "cli", "host": "*", "name": cli["command"], "system": sid,
                                   "label": cli.get("label", cli["command"]),
                                   "mode": {"value": "account", "strength": "declared",
                                            "evidence": cli.get("mode_note", "")}})
        for route in routes:
            kn = route.get("knowledge") or {}
            if kn.get("stale"):
                warnings.append("%s: confirmed knowledge for server %r is stale: the launcher changed since %s; "
                                "confirm it again" % (route["host"], route["name"], kn.get("confirmed_by_user", "?")))
        warnings.extend(_divergence(routes))
        servers = [{"host": s["host"], "name": s["server_name"], "file": s["file"], "scope": s["scope"],
                    "command": s["command"], "url": s["url"], "args": s["args"], "disabled": s["disabled"]}
                   for report in reports for s in report["servers"]]
        return {"schema": SCHEMA_SCAN, "servers": servers, "hosts": [{"host": r["host"], "label": r["label"], "detected": r["detected"],
                                                  "files": [{k: v for k, v in f.items()} for f in r["files"]]}
                                                 for r in reports],
                "routes": routes, "warnings": warnings}


def launcher_path(server: dict) -> str:
    """The file to inspect: the command, or the script an interpreter runs."""
    command = server["command"]
    if os.path.basename(command) in INTERPRETERS:
        for arg in server["args"]:
            if arg.startswith("-"):
                if arg in ("-m", "-c", "-e"):
                    return command  # a module or an inline program, not a file
                continue
            return os.path.expanduser(arg)
    return command


def _split(value: str) -> List[str]:
    return [v.strip() for v in str(value).split(",") if v.strip()]


def _divergence(routes: List[dict]) -> List[str]:
    by_key: Dict[tuple, Dict[str, str]] = {}
    for route in routes:
        if route["kind"] != "mcp":
            continue
        key = (route["system"], route["name"])
        by_key.setdefault(key, {})[route["host"]] = route["mode"]["value"]
    out = []
    for (system, name), modes in sorted(by_key.items()):
        if len(set(modes.values())) > 1:
            out.append("%s via server %r differs across hosts: %s" % (
                system, name, ", ".join("%s %s" % (h, m) for h, m in sorted(modes.items()))))
    return out


def detected_hosts(root: Path) -> List[str]:
    return [h for h in hosts_mod.HOSTS if hosts_mod.host_detected(h, root)]


_MATCH_CACHE: Dict[tuple, dict] = {}


def mcp_servers_for(hint: str, cwd: Path) -> dict:
    """MCP servers in the current host (or every detected host) that serve `hint`.

    The one MCP detector. `access resolve` (step 1), `tools resolve`, `tools
    status` and doctor all ask this instead of searching config text for a
    substring. `hint` is a system id (`confluence`), a family or name hint
    (`atlassian`), or a name the registry has never heard of (`linear`): a known
    system matches by its qualified routes, anything else by server name,
    command, URL or arguments.

    Returns {"host", "matches": [{host, name, file, system, mode, strength,
    base_url}], "servers": <count of every configured server>}.
    """
    host, _how = hosts_mod.resolve_current_host()
    key = (str(cwd), host, os.environ.get("HOME", ""))
    if key not in _MATCH_CACHE:
        scanner = Scanner(cwd)
        host_ids = [host] if host else detected_hosts(scanner.root)
        _MATCH_CACHE[key] = {"scan": scanner.scan(host_ids), "systems": scanner.systems}
    scan = _MATCH_CACHE[key]["scan"]
    systems = _MATCH_CACHE[key]["systems"]
    needle = (hint or "").strip().lower()
    wanted = {needle} if needle in systems else set(reg.systems_for_hint(systems, needle))
    matches = []
    seen = set()
    for route in scan["routes"]:
        if route["kind"] != "mcp" or route.get("disabled") or route["system"] not in wanted:
            continue
        seen.add((route["host"], route["name"]))
        matches.append({"host": route["host"], "name": route["name"], "file": route["file"],
                        "system": route["system"], "mode": route["mode"]["value"],
                        "strength": route["mode"]["strength"],
                        "base_url": (route.get("base_url") or {}).get("value", "")})
    if needle:
        for server in scan["servers"]:
            if server["disabled"] or (server["host"], server["name"]) in seen:
                continue
            text = " ".join([server["name"], server["command"], server["url"]] + server["args"]).lower()
            if needle in text:
                seen.add((server["host"], server["name"]))
                matches.append({"host": server["host"], "name": server["name"], "file": server["file"],
                                "system": "", "mode": "unknown", "strength": "inferred", "base_url": ""})
    return {"host": host or "", "matches": matches, "servers": len(scan["servers"])}


def describe_match(match: dict) -> str:
    what = 'MCP server "%s" in %s (%s)' % (match["name"], hosts_mod.HOST_LABELS.get(match["host"], match["host"]),
                                          _tilde(match["file"]))
    if match["mode"] in ("read-only", "read-write", "modify"):
        what += ", %s [%s]" % (match["mode"], match["strength"])
    else:
        what += ", mode unknown"
    return what


# ---------------------------------------------------------------------------
# Check: walk the ladder for one triple
# ---------------------------------------------------------------------------
def _rung(rid, status, evidence="", strength="", fix=None):
    return {"id": rid, "status": status, "strength": strength, "evidence": _r(evidence), "fix_options": fix or []}


def _allowed_ops(mode: str) -> set:
    return {"read-only": {"read"}, "modify": {"read", "write"}, "read-write": {"read", "write", "destructive"},
            "account": {"read", "write", "destructive"}}.get(mode, set())


def evaluate_route(route: dict, system: dict, op_class: str, target: dict, args, found: List[dict]) -> List[dict]:
    rungs = []
    host = route.get("host", "*")
    # L1 route
    if route["kind"] == "browser":
        rungs.append(_rung("route", "fail", "browser: no authenticated session can be detected, so it is never "
                                            "attempted; it is never a write route for a system with an API",
                           "declared"))
        return rungs
    if route["kind"] == "mcp":
        where = route["command"] and ("%s%s" % (_tilde(route["command"]),
                                                " (user-local launcher)" if (route.get("launcher") or {}).get("user_local")
                                                else "")) or route["url"]
        if route.get("disabled"):
            rungs.append(_rung("route", "fail", 'MCP server "%s" is disabled in %s' % (route["name"], _tilde(route["file"])),
                               "declared"))
            return rungs
        rungs.append(_rung("route", "pass", 'MCP server "%s" -> %s' % (route["name"], where), "declared"))
    else:
        rungs.append(_rung("route", "pass", "%s on PATH" % route["name"], "declared"))

    # L2 launch
    if route["kind"] == "mcp":
        rt = route["runtime"]
        if rt["status"] == "fail":
            rungs.append(_rung("launch", "fail", rt["evidence"], "declared"))
            return rungs
        rungs.append(_rung("launch", "pass", rt["evidence"], "declared"))
    else:
        rungs.append(_rung("launch", "pass", "%s installed" % route["name"], "declared"))

    # L3 auth
    auth = _auth(route, system, args, found, target)
    rungs.append(auth)
    if auth["status"] == "fail":
        return rungs

    # L4 mode
    mode_rung = _mode_rung(route, system, op_class, args)
    rungs.append(mode_rung)
    if mode_rung["status"] == "fail":
        return rungs

    # L5 target
    target_rung = _target_rung(route, system, op_class, target, args)
    rungs.append(target_rung)
    if target_rung["status"] == "fail":
        return rungs

    # L6 intent
    if op_class == "read":
        rungs.append(_rung("intent", "pass", "a read needs no separate authorisation", "declared"))
    elif args.user_authorised:
        rungs.append(_rung("intent", "pass", "you asked for this %s%s" % (
            args.op, " on this target" if target.get("kind") != "none" else ""), "declared"))
    else:
        rungs.append(_rung("intent", "fail", "the request does not state that you want this %s" % args.op, "declared"))
        return rungs

    # L7 policy
    rungs.append(_policy_rung(route, system, op_class, target, args))
    return rungs


def _auth(route, system, args, found, target=None) -> dict:
    if route["kind"] == "cli":
        cli = next((c for c in system.get("cli_routes", []) if c["command"] == route["name"]), None)
        if args.probe and cli:
            try:
                result = subprocess.run([cli["command"]] + cli["auth_probe"], stdin=subprocess.DEVNULL,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
            except subprocess.TimeoutExpired:
                return _rung("auth", "unknown", "%s %s timed out" % (cli["command"], " ".join(cli["auth_probe"])),
                             "verified")
            except OSError as exc:
                return _rung("auth", "unknown", str(exc), "verified")
            if result.returncode == 0:
                return _rung("auth", "pass", "%s %s succeeded" % (cli["command"], " ".join(cli["auth_probe"])), "verified")
            return _rung("auth", "fail", "%s %s failed: not logged in" % (cli["command"], " ".join(cli["auth_probe"])),
                         "verified")
        target_host = (target or {}).get("host", "")
        declared = creds.cli_login_declared(route["name"], target_host)
        if declared is False and target_host:
            return _rung("auth", "fail", "%s has no stored login for %s" % (route["name"], target_host), "declared")
        if declared:
            return _rung("auth", "pass", "%s has a stored login (not verified; --probe checks it)" % route["name"], "declared")
        if declared is False:
            return _rung("auth", "fail", "%s has no stored login" % route["name"], "declared")
        return _rung("auth", "unknown", "cannot tell whether %s is logged in" % route["name"], "inferred")
    if route["transport"] == "http" and not route["command"]:
        return _rung("auth", "unknown", "remote server: sign-in happens in the host", "inferred")
    present = [f for f in found if f["present"] == "present" and f["origin"] in ("host config",)
               or (f["present"] == "present" and str(f["origin"]).startswith(("launcher", "local knowledge")))]
    absent = [f for f in found if f["present"] == "absent" and str(f["origin"]).startswith(("launcher", "local"))]
    if route["host_credential_keys"]:
        return _rung("auth", "pass", "credential set in the host config (%s)" % ", ".join(route["host_credential_keys"]),
                     "declared")
    if present:
        f = present[0]
        return _rung("auth", "pass", "credential present (%s %s, referenced by the %s)" % (
            f["source"], f["locator"], "launcher" if "launcher" in f["origin"] else "confirmed route"), "inferred")
    if absent:
        f = absent[0]
        return _rung("auth", "fail", "the launcher reads %s %s, which does not exist" % (f["source"], f["locator"]),
                     "inferred")
    unknown = [f for f in found if f["present"] == "unknown" and str(f["origin"]).startswith("launcher")]
    if unknown:
        f = unknown[0]
        return _rung("auth", "unknown", "the launcher reads %s %s; its presence cannot be checked without reading it"
                     % (f["source"], f["locator"]), "inferred")
    return _rung("auth", "unknown", "no credential reference found for this route", "inferred")


def _mode_rung(route, system, op_class, args) -> dict:
    mode = route["mode"]
    value = mode["value"]
    evidence = mode["evidence"]
    strength = mode["strength"]
    if args.live_result is not None and route["kind"] == "mcp":
        live = args.live_result
        if live.get("error"):
            evidence += "; live introspection failed: %s" % live["error"]
        else:
            tools = set(live.get("tools", []))
            upstreams = [u for u in system.get("mcp_upstreams", []) if u.get("id") == route.get("upstream")]
            wanted = []
            for up in upstreams or system.get("mcp_upstreams", []):
                wanted += up.get("tools", {}).get(op_class, []) if op_class != "read" else []
            if op_class != "read":
                has = sorted(tools & set(wanted)) or sorted(t for t in tools
                                                              if reg.tool_class(system, t) == op_class)
                if not has:
                    return _rung("mode", "fail", "live: the server lists %d tools and none of them %s %s" % (
                        len(tools), "writes to" if op_class == "write" else "deletes or moves in", system["id"]),
                        "verified")
                if value == "read-only" and strength == "declared":
                    return _rung("mode", "fail", evidence + "; an explicit read-only setting outranks the tool list",
                                 "declared")
                return _rung("mode", "pass", "live: %s offers %s" % (route["name"], ", ".join(has[:4])), "verified")
    if op_class == "read":
        if value == "unknown" and route["kind"] == "mcp" and not route.get("upstream"):
            return _rung("mode", "unknown", evidence, strength)
        return _rung("mode", "pass", ("%s: " % value if value != "unknown" else "") + evidence, strength)
    if value == "unknown":
        return _rung("mode", "unknown", evidence, strength)
    if op_class not in _allowed_ops(value):
        label = {"read-only": "read-only", "modify": "writes allowed but not destructive operations"}.get(value, value)
        return _rung("mode", "fail", "%s: %s" % (label, evidence), strength)
    tf = route.get("tool_filter")
    if tf and route["kind"] == "mcp":
        cls = [t for t in tf["values"] if reg.tool_class(system, t) == op_class]
        if not cls:
            return _rung("mode", "fail", "%s allows only %s; no %s tool for %s is enabled" % (
                tf["source"], ", ".join(tf["values"][:6]), op_class, system["id"]), tf["strength"])
    ts = route.get("toolsets")
    if ts and route["kind"] == "mcp":
        spec = next((u.get("toolset_filters", {}) for u in system.get("mcp_upstreams", [])
                     if u.get("id") == route.get("upstream")), {})
        values = [v.lower() for v in ts["values"]]
        if not set(values) & set(spec.get("all_values", [])):
            ok = False
            if spec.get("system_prefix"):
                ok = any(v.startswith(spec["system_prefix"]) for v in values)
            if spec.get("write_toolsets"):
                ok = bool(set(values) & set(spec["write_toolsets"]))
            if not ok:
                return _rung("mode", "fail", "%s=%s enables no %s toolset for %s" % (
                    ts["source"], ",".join(ts["values"]), op_class, system["id"]), ts["strength"])
    return _rung("mode", "pass", "%s: %s" % (value, evidence), strength)


def _target_rung(route, system, op_class, target, args) -> dict:
    if target.get("kind") == "none":
        if op_class == "read":
            return _rung("target", "skipped", "no target named")
        return _rung("target", "fail", "a %s needs one specific target; none was named" % op_class, "declared")
    if target.get("kind") == "unknown":
        return _rung("target", "unknown", "could not read a %s target from %r" % (system["id"], target["raw"]), "inferred")
    base = route.get("base_url") or {}
    target_host = target.get("host", "")
    if base.get("value") and target_host:
        route_host = (urlparse(base["value"]).hostname or "").lower()
        if route_host and route_host != target_host:
            return _rung("target", "fail", "the route serves %s; the target is on %s" % (route_host, target_host),
                         base.get("strength", "inferred"))
    for key, spec in (route.get("scope_filters") or {}).items():
        value = reg.target_scope_value(target, spec["kind"])
        if not value:
            return _rung("target", "unknown", "%s limits this route to %s, and the target's %s is not known until "
                         "it is read" % (key, ",".join(spec["values"]), spec["kind"]), spec["strength"])
        if value not in spec["values"]:
            personal = " - a personal space" if reg.is_personal_space(value) else ""
            return _rung("target", "fail", "%s %s is excluded by %s=%s%s; pages there look missing, not forbidden" % (
                spec["kind"], value, key, ",".join(spec["values"]), personal), spec["strength"])
    if args.probe_result is not None:
        probe = args.probe_result
        if probe.get("status") == "pass":
            return _rung("target", "pass", probe["evidence"], "verified")
        if probe.get("status") == "fail":
            return _rung("target", "fail", probe["evidence"], "verified")
        if probe.get("status") == "unknown":
            return _rung("target", "unknown", probe["evidence"], "inferred")
    what = "%s %s" % (target.get("kind"), target.get("id", ""))
    if target.get("space"):
        what += " (space %s)" % target["space"]
    if target.get("project"):
        what += " (project %s)" % target["project"]
    strength = "declared" if route["kind"] == "cli" or route.get("via") == "direct" or \
        (route.get("knowledge") and not route["knowledge"].get("stale")) else "inferred"
    note = getattr(args, "probe_note", "")
    return _rung("target", "pass", "%s: no scope filter excludes it; the account's permission on it is not verified%s"
                 % (what, (" (probe: %s)" % note) if note else ("" if args.probe else " (--probe checks it)")), strength)


def _policy_rung(route, system, op_class, target, args) -> dict:
    policy = args.policy
    for rule in policy["deny"]:
        if state.policy_rule_matches(rule, system["id"], op_class):
            return _rung("policy", "fail", "your policy (%s) denies %s %s" % (policy["source"], system["id"], op_class),
                         "declared")
    if op_class == "read":
        return _rung("policy", "pass", "reads are allowed once the route qualifies", "declared")
    if route["kind"] == "browser":
        return _rung("policy", "fail", "a browser is never a write route for a system with an API", "declared")
    if policy.get("require_probe_for_write") and not args.probe:
        return _rung("policy", "fail", "your policy requires a verified permission probe before a write (--probe)",
                     "declared")
    confirm = "preview, then explicit confirmation"
    if op_class == "destructive":
        confirm = "explicit confirmation naming each target and the count"
    elif args.own_target:
        confirm = "preview, then proceed on your go-ahead"
    for rule in policy["always_confirm"]:
        if state.policy_rule_matches(rule, system["id"], op_class):
            confirm = "explicit confirmation (your policy)"
    rung = _rung("policy", "pass", "allowed: %s" % confirm, "declared")
    rung["confirmation"] = confirm
    return rung


def _fix_options(system: dict, route: Optional[dict], blocked: dict, op: str, host: Optional[str],
                 found: List[dict], target: dict) -> List[dict]:
    sid = system["id"]
    host_flag = " --host %s" % host if host else ""
    rid = blocked["id"]
    options = []
    inferred = blocked.get("strength") == "inferred" and route and route.get("kind") == "mcp"
    if rid == "route":
        options.append({"id": "setup-route", "label": "Set up an MCP server for %s" % sid,
                        "command": "agent-skills access setup %s%s" % (sid, host_flag)})
        options.append({"id": "tell-tool", "label": "Tell me which tool you normally use for %s, and I will inspect it"
                        % sid, "command": "agent-skills access inspect <command>"})
        present = [f for f in found if f["present"] == "present"]
        if present:
            f = present[0]
            options.append({"id": "use-found-credential-for-setup",
                            "label": "I found a credential at %s %s - use it for a new route? (setup only; it is never "
                                     "used directly)" % (f["source"], f["locator"]),
                            "command": "agent-skills access setup %s%s" % (sid, host_flag)})
    elif rid == "launch":
        options.append({"id": "fix-launch", "label": "Install the missing runtime or fix the command path: %s"
                        % blocked["evidence"], "command": ""})
    elif rid == "auth":
        options.append({"id": "store-token", "label": "Store a token in your OS credential store yourself (the value is "
                        "never typed into this chat)",
                        "command": "agent-skills access set --profile <name> --service %s --secret-field token" % sid})
        present = [f for f in found if f["present"] == "present"]
        if present:
            f = present[0]
            options.append({"id": "use-found-credential-for-setup",
                            "label": "I found a credential at %s %s - use it for a new route? (setup only)" % (
                                f["source"], f["locator"]), "command": "agent-skills access setup %s%s" % (sid, host_flag)})
    elif rid == "mode":
        if inferred:
            options.append({"id": "confirm-inferred", "label": "Confirm what I inferred from %s" % (
                route.get("mode", {}).get("source") or "the launcher"),
                "command": "agent-skills access remember --system %s --server %s%s --yes" % (sid, route["name"], host_flag)})
        options.append({"id": "write-profile", "label": "Add a separate write profile for this host, limited to this "
                        "target's space or project (the read-only entry stays as it is)%s" % _toggle_note(route),
                        "command": "agent-skills access setup %s --write-profile%s%s%s" % (
                            sid, host_flag, " --server %s" % route["name"] if route else "",
                            _target_flag(target))})
    elif rid == "target":
        text = blocked["evidence"]
        if "excluded by" in text:
            options.append({"id": "write-profile-scoped", "label": "Add a write profile limited to this target's "
                            "space or project", "command": "agent-skills access setup %s --write-profile%s%s%s" % (
                                sid, host_flag, " --server %s" % route["name"] if route else "",
                                _target_flag(target))})
        elif "serves" in text:
            options.append({"id": "other-route", "label": "Set up a route for the target's site", "command":
                            "agent-skills access setup %s%s" % (sid, host_flag)})
        elif "needs one specific target" in text:
            options.append({"id": "name-target", "label": "Name the exact page, issue or repository", "command": ""})
        else:
            options.append({"id": "ask-owner", "label": "Ask the owner of this %s for the permission the operation needs"
                            % target.get("kind", "target"), "command": ""})
    elif rid == "intent":
        options.append({"id": "ask-user", "label": "Ask you whether you want this %s" % op, "command": ""})
    elif rid == "policy":
        options.append({"id": "policy", "label": "Your policy blocks this; change it only if you mean to",
                        "command": "agent-skills access explain %s" % sid})
    elif rid == "host":
        options.append({"id": "ask-host", "label": "Tell me which assistant you are using right now", "command":
                        "agent-skills access check --host <id> ..."})
    options.append({"id": "manual-handoff", "label": "Do it once yourself: I prepare the exact change and the link, and "
                    "finish the rest of the task", "command": ""})
    return options


def _target_flag(target: dict) -> str:
    raw = (target or {}).get("raw", "")
    if not raw:
        return ""
    return ' --target "%s"' % raw.replace('"', "")


def _toggle_note(route: Optional[dict]) -> str:
    toggle = ((route or {}).get("mode") or {}).get("toggle") or {}
    if toggle.get("env") and toggle.get("write_when") and not toggle["write_when"].startswith("("):
        return ", using %s=%s" % (toggle["env"], toggle["write_when"])
    return ""


def _result_of(rungs: List[dict], op_class: str) -> Tuple[str, Optional[str], int]:
    for rung in rungs:
        if rung["status"] == "fail":
            code = {"route": EXIT_NEEDS_USER, "launch": EXIT_NEEDS_USER, "auth": EXIT_AUTH, "mode": EXIT_CAPABILITY,
                    "target": EXIT_CAPABILITY, "intent": EXIT_NEEDS_USER, "policy": EXIT_CAPABILITY}[rung["id"]]
            return "blocked", rung["id"], code
    for rung in rungs:
        if rung["status"] == "unknown":
            return "unknown", rung["id"], EXIT_NEEDS_USER
    if op_class != "read":
        for rung in rungs:
            if rung["id"] in ("mode", "target") and rung["strength"] == "inferred":
                return "needs-confirmation", rung["id"], EXIT_NEEDS_USER
    return "available", None, EXIT_OK


def _progress(rungs: List[dict]) -> tuple:
    passed = sum(1 for r in rungs if r["status"] in ("pass", "skipped"))
    strong = sum(1 for r in rungs if r.get("strength") in ("declared", "verified"))
    return (passed, strong)


def check(scanner: Scanner, system_id: str, op: str, target_raw: str, host: Optional[str], host_how: str,
          args) -> dict:
    system = scanner.systems[system_id]
    op_class = reg.operation_class(op) or ""
    host_ids = [host] if host else detected_hosts(scanner.root)
    scan = scanner.scan(host_ids)
    target = reg.parse_target(system, target_raw)
    routes = [r for r in scan["routes"] if r["system"] == system_id and (r["kind"] != "mcp" or r["host"] in host_ids)]
    mcp_routes = [r for r in routes if r["kind"] == "mcp"]
    cli_routes = [r for r in routes if r["kind"] == "cli"]
    base_hosts = sorted({(urlparse(r["base_url"]["value"]).hostname or "") for r in mcp_routes if r.get("base_url")}
                        | ({target["host"]} if target.get("host") else set()))
    base_hosts = [h for h in base_hosts if h]
    found_all: List[dict] = []
    per_route_found: Dict[int, List[dict]] = {}
    for idx, route in enumerate(mcp_routes):
        host_env = [{"key": k, "file": _tilde(route["file"]), "server": route["name"]}
                    for k in route["host_credential_keys"]]
        per_route_found[idx] = creds.locate(system, route["credential_refs"], base_hosts, host_env)
        found_all.extend(per_route_found[idx])
    if not mcp_routes:
        found_all = creds.locate(system, [], base_hosts)
    live_by_route = {}
    if args.live:
        import access_live
        for idx, route in enumerate(mcp_routes):
            if route["transport"] != "stdio" or route.get("disabled"):
                continue
            if route["scope"] == "project":
                # A project-scoped server is defined by a file in the repository.
                # Starting it would run a command the repository chose; the user
                # never approved it here, so --live does not.
                live_by_route[idx] = {"error": "not started: it is defined in the repository (%s), not by you"
                                               % _tilde(route["file"])}
                continue
            live_by_route[idx] = access_live.introspect_route(route, scanner.root)

    probes: Dict[str, Optional[dict]] = {}
    network_failure = False
    evaluations = []
    for idx, route in enumerate(mcp_routes):
        args.live_result = live_by_route.get(idx)
        args.probe_result = None
        args.probe_note = ""
        if args.probe and target.get("kind") not in ("none", "unknown", None):
            base = (route.get("base_url") or {}).get("value") or target.get("base", "")
            if base not in probes:
                import access_probe
                probes[base] = access_probe.probe(system, target, base, scanner.cwd, op_class,
                                                  fresh=getattr(args, "fresh", False))
            result = probes[base]
            if result and result["status"] == "network":
                # Verification was asked for and could not happen: the target
                # rung is unknown, not the unverified pass it would be without
                # --probe.
                network_failure = True
                args.probe_result = {"status": "unknown", "evidence": result["evidence"]}
            elif result and result["status"] in ("pass", "fail") and result["rung"] == "target":
                args.probe_result = result
            elif result:
                args.probe_note = result["evidence"]
        rungs = evaluate_route(route, system, op_class, target, args, per_route_found.get(idx, []))
        evaluations.append((route, rungs))
    for route in cli_routes:
        args.live_result = None
        args.probe_note = ""
        args.probe_result = _cli_permission_probe(route, system, target, op_class) if args.probe else None
        evaluations.append((route, evaluate_route(route, system, op_class, target, args, found_all)))
    args.live_result = None
    args.probe_result = None
    args.probe_note = ""

    browser = {"kind": "browser", "name": "browser", "host": host or "*", "system": system_id,
               "usable": False, "reason": "no authenticated session can be detected; never attempted"}

    per_host: Dict[str, Tuple[dict, List[dict]]] = {}
    for route, rungs in evaluations:
        keys = [route["host"]] if route["kind"] == "mcp" else list(host_ids)
        for key in keys:
            best = per_host.get(key)
            if best is None or _rank(rungs, op_class) > _rank(best[1], op_class):
                per_host[key] = (route, rungs)

    chosen_host = host
    if host:
        chosen = per_host.get(host)
    else:
        outcomes = {h: _result_of(v[1], op_class)[0] for h, v in per_host.items()}
        if len(set(outcomes.values())) == 1 and outcomes:
            chosen_host = sorted(per_host)[0]
            chosen = per_host[chosen_host]
        else:
            chosen = None

    if chosen is None and per_host and not host:
        rungs = [_rung("route", "unknown", "routes differ by host and the current host is not known (%s): %s" % (
            host_how, "; ".join("%s %s" % (h, _result_of(v[1], op_class)[0]) for h, v in sorted(per_host.items()))),
            "inferred")]
        route = None
    elif chosen is None:
        rungs = [_rung("route", "fail", "no MCP server or CLI for %s in %s" % (
            system_id, host or ", ".join(host_ids) or "any detected host"), "declared")]
        route = None
    else:
        route, rungs = chosen

    result, blocked_at, code = _result_of(rungs, op_class)
    if network_failure and result != "available" and code != EXIT_CAPABILITY:
        code = EXIT_NETWORK
    present_ids = {r["id"] for r in rungs}
    full = []
    for rid in RUNGS:
        match = next((r for r in rungs if r["id"] == rid), None)
        full.append(match or _rung(rid, "skipped"))
    switched_from = None
    if route is not None and op_class != "read" and result in ("available", "needs-confirmation"):
        # Another route in this host was blocked by a setting - read-only, a
        # scope filter, policy. Using a different route instead is exactly the
        # "retry a blocked write via another route" the floor forbids unless
        # the user chooses it, so the check stops and says so.
        for other, other_rungs in evaluations:
            if other is route or (other["kind"] == "mcp" and other["host"] != (chosen_host or other["host"])):
                continue
            if _same_server(other, route):
                # A write profile the user added for this server (same launcher,
                # its own mode) is their fix for the block, not a way round it.
                continue
            o_result, o_blocked, _o_code = _result_of(other_rungs, op_class)
            if o_result == "blocked" and o_blocked in ("mode", "target", "policy"):
                switched_from = (other, next(r for r in other_rungs if r["id"] == o_blocked))
                break
    if switched_from:
        other, why = switched_from
        result, blocked_at, code = "needs-confirmation", "route", EXIT_NEEDS_USER
        full[0]["evidence"] += "; but %s %r is blocked at %s by its own setting (%s)" % (
            other["kind"], other["name"], why["id"], why["evidence"])
        options = [{"id": "use-other-route", "label": "Use %s %r for this, knowing your %r %s is set that way on "
                    "purpose? (Only if you say so.)" % (route["kind"], route["name"], other["name"], other["kind"]),
                    "command": ""}]
        options += [o for o in _fix_options(system, other, dict(why), op, host, found_all, target)
                    if o["id"] != "manual-handoff"]
        options += [o for o in _fix_options(system, route, {"id": "intent"}, op, host, found_all, target)
                    if o["id"] == "manual-handoff"]
        full[0]["fix_options"] = options
    elif blocked_at:
        blocked = next(r for r in full if r["id"] == blocked_at)
        fix_id = "host" if (blocked_at == "route" and blocked["status"] == "unknown") else blocked_at
        blocked["fix_options"] = _fix_options(system, route, dict(blocked, id=fix_id), op, host, found_all, target)
    for r in full:
        if r["id"] not in present_ids and r["status"] == "skipped":
            r["evidence"] = ""
    confirmation = next((r.get("confirmation") for r in full if r["id"] == "policy" and r.get("confirmation")), "")
    report = {
        "schema": SCHEMA_CHECK, "system": system_id, "operation": op, "operation_class": op_class,
        "target": {k: v for k, v in target.items()}, "host": chosen_host or "", "host_source": host_how,
        "rungs": full, "result": result, "blocked_at": blocked_at, "exit_code": code,
        "confirmation": confirmation,
        "route": _route_summary(route) if route else None,
        "routes": [_route_summary(r, rungs_) for r, rungs_ in evaluations] + [browser],
        "found_credentials": [{"source": f["source"], "locator": _r(f["locator"]), "system_guess": f["system_guess"],
                               "present": f["present"]} for f in _dedupe(found_all)],
        "warnings": scan["warnings"],
    }
    if result == "available" and op_class in ("write", "destructive") and route:
        grant = state.write_grant(system_id, op_class, target.get("id", ""), chosen_host or "",
                                  route.get("name", ""), route.get("kind", ""))
        report["grant"] = {"path": _tilde(str(grant)), "ttl_minutes": state.GRANT_TTL_SECONDS // 60}
    return report


def _same_server(a: dict, b: dict) -> bool:
    if a.get("kind") != "mcp" or b.get("kind") != "mcp" or a.get("host") != b.get("host"):
        return False
    same_launcher = bool(a.get("launcher_command")) and a.get("launcher_command") == b.get("launcher_command") \
        and a.get("upstream") == b.get("upstream")
    profile_name = b.get("name") == "%s-write" % a.get("name") or a.get("name") == "%s-write" % b.get("name")
    return same_launcher or profile_name


def _rank(rungs, op_class):
    result = _result_of(rungs, op_class)[0]
    order = {"available": 3, "needs-confirmation": 2, "unknown": 1, "blocked": 0}[result]
    return (order,) + _progress(rungs)


def _dedupe(found):
    seen = set()
    out = []
    for f in found:
        key = (f["source"], f["locator"])
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


def _route_summary(route: dict, rungs: Optional[List[dict]] = None) -> dict:
    if route["kind"] == "browser":
        return route
    summary = {"kind": route["kind"], "name": route["name"], "host": route.get("host", "*"),
               "mode": (route.get("mode") or {}).get("value", "unknown"),
               "strength": (route.get("mode") or {}).get("strength", "")}
    if route["kind"] == "mcp":
        summary.update(file=_tilde(route["file"]), command=_tilde(route["command"]) if route["command"] else "",
                       upstream=route.get("upstream"), via=route.get("via"))
    if rungs is not None:
        failing = next((r for r in rungs if r["status"] in ("fail", "unknown")), None)
        summary["usable"] = failing is None
        summary["reason"] = ("%s %s: %s" % (failing["id"], failing["status"], failing["evidence"])) if failing else "qualifies"
    return summary


def _cli_permission_probe(route, system, target, op_class) -> Optional[dict]:
    cli = next((c for c in system.get("cli_routes", []) if c["command"] == route["name"]), None)
    if not cli or not cli.get("permission_probe") or op_class == "read" or not target.get("owner"):
        return None
    argv = [cli["command"]] + [a.replace("{owner}", target["owner"]).replace("{repo}", target["repo"])
                               for a in cli["permission_probe"]]
    try:
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"status": "unknown", "evidence": "permission probe failed: %s" % exc}
    value = result.stdout.strip().lower()
    if result.returncode != 0:
        return {"status": "unknown", "evidence": "permission probe could not read %s" % target["id"]}
    if value == "true":
        return {"status": "pass", "evidence": "%s: the account can push (%s)" % (target["id"], " ".join(argv[:3]))}
    return {"status": "fail", "evidence": "%s: the account cannot push; ask a maintainer for write access" % target["id"]}


# ---------------------------------------------------------------------------
# classify-error: a mid-task failure mapped back onto the ladder
# ---------------------------------------------------------------------------
def classify_error(system: dict, op: str, status: str, target: dict, filtered: bool, known_existing: bool) -> dict:
    s = (status or "").strip().lower()
    code = int(s) if s.isdigit() else None
    if code == 401 or "unauthorized" in s or "unauthorised" in s:
        rung, exit_code = "auth", EXIT_AUTH
        why = ("the credential was rejected: expired, rotated, or (for a scoped Atlassian token) missing the scope "
               "for this operation")
    elif code == 403 or "forbidden" in s or "permission" in s:
        rung, exit_code = "target", EXIT_CAPABILITY
        why = "the account or token scope lacks permission on this target"
    elif code == 404 or "not found" in s and "tool" not in s:
        rung, exit_code = "target", EXIT_CAPABILITY
        if filtered:
            why = "the target is outside the route's scope filter, so it looks missing (filtered)"
        elif known_existing:
            why = "the target exists but is hidden from this account or route (filtered or no view permission)"
        else:
            why = "the target does not exist, or is hidden from this account or route"
            exit_code = EXIT_NEEDS_USER
    elif "tool" in s and ("not found" in s or "unknown" in s or "not available" in s or "disabled" in s):
        rung, exit_code = "mode", EXIT_CAPABILITY
        why = "the server does not offer this tool: read-only mode or a tool filter removed it"
    elif code == 409 or "conflict" in s or "version" in s:
        rung, exit_code = "policy", EXIT_NEEDS_USER
        why = "version conflict: someone changed the target; re-read it, show the difference, and ask before retrying"
    elif code == 429 or (code and code >= 500) or "timeout" in s or "timed out" in s or "network" in s \
            or "connection" in s:
        rung, exit_code = "network", EXIT_NETWORK
        why = "a network or server fault, not a permission problem; retry later"
    else:
        rung, exit_code = "unknown", EXIT_NEEDS_USER
        why = "not a recognised failure; show it to the user rather than trying another route"
    return {"schema": "agent-skills.access-classify/v1", "system": system["id"], "operation": op,
            "status": status, "rung": rung, "reason": why, "exit_code": exit_code,
            "target": target, "next": "re-enter the resolution dialogue at the %s rung; do not retry through another "
                                      "route" % rung if rung not in ("network", "unknown") else
                                      ("retry later" if rung == "network" else "show the user the error")}


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def render_check(report: dict) -> str:
    target = report["target"]
    tdesc = ""
    if target.get("kind") not in ("none", None):
        tdesc = " · %s %s" % (target.get("kind"), target.get("id", target.get("raw", "")))
        if target.get("space"):
            tdesc += " (space %s)" % target["space"]
        if target.get("project"):
            tdesc += " (project %s)" % target["project"]
    host = report["host"] or "unknown"
    out = ["Access check: %s · %s%s · host %s" % (report["system"], report["operation"], tdesc, host)]
    for rung in report["rungs"]:
        status = rung["status"].upper() if rung["status"] in ("fail", "unknown") else rung["status"]
        line = "  %-8s %-8s %s" % (rung["id"], status, rung["evidence"])
        if rung.get("strength") and rung["status"] != "skipped":
            line += "   [%s]" % rung["strength"]
        out.append(line.rstrip())
    label = {"available": "AVAILABLE", "blocked": "BLOCKED at %s" % report["blocked_at"],
             "unknown": "UNKNOWN at %s" % report["blocked_at"],
             "needs-confirmation": ("NEEDS CONFIRMATION: another route is blocked by its own setting"
                                    if report["blocked_at"] == "route"
                                    else "NEEDS CONFIRMATION of the inferred %s" % report["blocked_at"])}[report["result"]]
    out.append("Result: %s." % label)
    if report.get("confirmation"):
        out.append("Before applying: %s." % report["confirmation"])
    others = [r for r in report["routes"] if r is not report.get("route")]
    if others:
        out.append("Routes considered:")
        for r in others:
            if r["kind"] == "browser":
                out.append("  browser  not usable (%s)" % r["reason"])
            else:
                out.append("  %-7s %s [%s] %s" % (r["kind"], r["name"], r.get("host", "*"),
                                                 ("usable" if r.get("usable") else "not usable: %s" % r.get("reason", ""))))
    if report["found_credentials"]:
        out.append("Credentials found (locators only; a found credential is not a route):")
        for f in report["found_credentials"]:
            out.append("  %s %s (%s)" % (f["source"], f["locator"], f["present"]))
    blocked = next((r for r in report["rungs"] if r["fix_options"]), None)
    if blocked:
        out.append("Options:")
        for i, option in enumerate(blocked["fix_options"], start=1):
            out.append("  %d. %s%s" % (i, option["label"], ("\n     %s" % option["command"]) if option["command"] else ""))
    for warning in report.get("warnings", []):
        out.append("warning: %s" % _r(warning))
    return "\n".join(out)


def summarise_scan(scan: dict, systems: Dict[str, dict]) -> List[dict]:
    rows = []
    hosts_seen = [h["host"] for h in scan["hosts"] if h["detected"]]
    for host in hosts_seen:
        for sid in systems:
            mcp = [r for r in scan["routes"] if r["kind"] == "mcp" and r["host"] == host and r["system"] == sid]
            cli = [r for r in scan["routes"] if r["kind"] == "cli" and r["system"] == sid]
            if not mcp and not cli:
                rows.append({"host": host, "system": sid, "state": "not configured", "route": "", "mode": "",
                             "strength": "", "auth_evidence": ""})
                continue
            for r in mcp or cli:
                mode = r["mode"]["value"]
                state_ = "ready (%s)" % mode if mode in ("read-only", "read-write", "modify") else \
                    ("ready (account permissions)" if mode == "account" else "ready (mode unknown)")
                if r.get("disabled"):
                    state_ = "broken: disabled in %s" % _tilde(r["file"])
                elif r["kind"] == "mcp" and r["runtime"]["status"] == "fail":
                    state_ = "broken: %s" % r["runtime"]["evidence"]
                cred = ""
                if r["kind"] == "mcp":
                    if r["host_credential_keys"]:
                        cred = "credential in host config"
                    elif r["credential_refs"]:
                        ref = r["credential_refs"][0]
                        cred = "launcher reads %s %s" % (ref["kind"], ref["locator"])
                    else:
                        cred = "no credential reference"
                where = ""
                if r["kind"] == "mcp":
                    where = 'MCP "%s"%s' % (r["name"], " via user-local launcher" if
                                            (r.get("launcher") or {}).get("user_local") else "")
                else:
                    where = "CLI %s" % r["name"]
                rows.append({"host": host, "system": sid, "state": state_, "route": where, "mode": mode,
                             "strength": r["mode"]["strength"], "auth_evidence": cred,
                             "stale": bool((r.get("knowledge") or {}).get("stale"))})
    return rows


def render_scan(scan: dict, systems: Dict[str, dict], host_note: str) -> str:
    out = ["Access scan (static; no network, no secret values)  host: %s" % host_note]
    rows = summarise_scan(scan, systems)
    current = None
    for row in rows:
        if row["host"] != current:
            current = row["host"]
            out.append("%s" % hosts_mod.HOST_LABELS.get(current, current))
        if row["state"] == "not configured":
            out.append("  %-11s not configured" % row["system"])
            continue
        out.append("  %-11s %s · %s · %s%s" % (row["system"], row["state"], row["route"], row["strength"],
                                                 (" · %s" % row["auth_evidence"]) if row["auth_evidence"] else ""))
    mcp_count = len({(r["host"], r["name"]) for r in scan["routes"] if r["kind"] == "mcp"})
    out.append("MCP configured: %s" % ("yes (%d server entr%s)" % (mcp_count, "y" if mcp_count == 1 else "ies")
                                       if mcp_count else "no"))
    for warning in scan["warnings"]:
        out.append("warning: %s" % _r(warning))
    out.append("Presence is not capability: before a write, run `agent-skills access check`.")
    return "\n".join(out)
