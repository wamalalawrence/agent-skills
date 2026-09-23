#!/usr/bin/env python3
"""Execution Guard: a write to a known system needs a passing `access check` first.

Where a host consults the guard before each tool call (Claude Code and Codex
`PreToolUse`), two kinds of call reach an external system's write path:

* an MCP tool the system registry lists as a write or destructive tool, and
* a shell `curl`/`wget`/`http` with a writing method aimed at a known system's
  host (a registry host hint, or a base URL the user confirmed in local route
  knowledge) - the "just use the token against the REST API" move.

Either is allowed when `agent-skills access check` passed for that system and
operation class within the grant window (`access_state.GRANT_TTL_SECONDS`);
otherwise the guard answers ASK and names the check to run. ASK, not DENY, is
the default so a user working without Wamala is asked rather than locked out;
a guard policy can raise it to deny like any other rule.

The grant says a check passed for (system, operation class, server). It does
not bind to one target: the host's tool arguments differ per server and are not
a reliable place to read a page id from. That limit is documented in
docs/access/README.md.

For hosts without a pre-execution hook, Wamala's contract is the only gate.
"""
from __future__ import annotations

import fnmatch
import json
import os
import shlex
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

_SYSTEMS: Optional[Dict[str, dict]] = None
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_FETCHERS = {"curl", "wget", "http", "https", "xh"}


def _systems() -> Dict[str, dict]:
    global _SYSTEMS
    if _SYSTEMS is None:
        try:
            import access_registry
            _SYSTEMS = access_registry.load_systems()
        except Exception:  # noqa: BLE001 - a broken registry must not break the guard
            _SYSTEMS = {}
    return _SYSTEMS


def split_tool(name: str) -> Tuple[str, str]:
    """(server, tool) from `mcp__server__tool` or `server/tool`."""
    if name.startswith("mcp__"):
        parts = name.split("__", 2)
        if len(parts) == 3:
            return parts[1], parts[2]
    if "/" in name:
        server, tool = name.split("/", 1)
        return server, tool
    return "", name


def mcp_write(name: str) -> Optional[Tuple[str, str, str, str]]:
    """(system, op class, server, tool) when the tool writes to a known system."""
    import access_registry
    server, tool = split_tool(name)
    for sid, system in _systems().items():
        cls = access_registry.tool_class(system, tool)
        if cls in ("write", "destructive"):
            return sid, cls, server, tool
    return None


def _known_hosts() -> List[Tuple[str, str]]:
    """(pattern, system) for registry host hints and confirmed base URLs."""
    pairs = []
    for sid, system in _systems().items():
        for pattern in system.get("host_hints", []):
            pairs.append((pattern.lower(), sid))
    try:
        import access_state
        for route in access_state.load_routes().get("routes", []):
            host = (urlparse(route.get("base_url", "")).hostname or "").lower()
            for sid in route.get("systems", []):
                if host:
                    pairs.append((host, sid))
    except Exception:  # noqa: BLE001
        pass
    return pairs


def http_write(command: str) -> Optional[Tuple[str, str, str]]:
    """(system, method, host) for a fetcher writing to a known system's host."""
    try:
        words = shlex.split(command)
    except ValueError:
        return None
    for start, word in enumerate(words):
        if os.path.basename(word) not in _FETCHERS:
            continue
        method = ""
        urls = []
        data = False
        rest = words[start + 1:]
        for i, arg in enumerate(rest):
            if arg in ("|", ";", "&&", "||"):
                break
            if arg in ("-X", "--request") and i + 1 < len(rest):
                method = rest[i + 1].upper()
            elif arg.startswith("-X") and len(arg) > 2:
                method = arg[2:].upper()
            elif arg.startswith("--request="):
                method = arg.split("=", 1)[1].upper()
            elif arg in ("-d", "--data", "--data-raw", "--data-binary", "--json", "-F", "--form", "-T",
                         "--upload-file") or arg.startswith(("--data=", "--json=", "--post-data")):
                data = True
            elif arg.upper() in _WRITE_METHODS and os.path.basename(word) in ("http", "https", "xh"):
                method = arg.upper()
            elif arg.startswith(("http://", "https://")):
                urls.append(arg)
        if not method and data:
            method = "POST"
        if method not in _WRITE_METHODS:
            continue
        for url in urls:
            host = (urlparse(url).hostname or "").lower()
            for pattern, sid in _known_hosts():
                if host and fnmatch.fnmatch(host, pattern):
                    return sid, method, host
    return None


def has_grant(system: str, op_class: str, server: str = "") -> bool:
    try:
        import access_state
        grants = access_state.valid_grants()
    except Exception:  # noqa: BLE001
        return False
    rank = {"read": 0, "write": 1, "destructive": 2}
    for grant in grants:
        if grant.get("system") != system:
            continue
        if rank.get(grant.get("operation"), -1) < rank.get(op_class, 9):
            continue
        if server and grant.get("server_name") and grant["server_name"] != server:
            continue
        return True
    return False


def advice(system: str, op_class: str) -> str:
    return ("Run `agent-skills access check --system %s --op %s --target <url-or-key> --user-authorised` and "
            "follow its result; a passing check allows this for %d minutes." % (
                system, op_class, 30))


def describe(arguments) -> str:
    try:
        return json.dumps(arguments)[:200]
    except (TypeError, ValueError):
        return ""
