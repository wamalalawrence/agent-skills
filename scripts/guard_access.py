#!/usr/bin/env python3
"""Execution Guard: a write to a known system needs a passing `access check` first.

Where a host consults the guard before each tool call (Claude Code and Codex
`PreToolUse`), two kinds of call reach an external system's write path:

* an MCP tool the system registry lists as a write or destructive tool, and
* a shell fetcher (`curl`, `wget`, `http`, `xh`) sending a write to a known
  system's host - a registry host hint, or a base URL the user confirmed in
  local route knowledge. This is the "just use the token against the REST API"
  move that routes around a read-only MCP server.

An MCP write is allowed when `agent-skills access check` passed for that
system, operation class and server within the grant window
(`access_state.GRANT_TTL_SECONDS`). A fetcher write is never pre-allowed: the
check qualifies MCP and CLI routes, and a raw HTTP call with a token is not one
of them, so a passing check for the system does not cover it. Both otherwise
answer ASK and say why. ASK, not DENY, is
the default so a user working without Wamala is asked rather than locked out;
a guard policy can raise it to deny like any other rule.

It fails closed. A registry that cannot be read makes every mutating-looking
MCP tool and every fetcher write ASK. A shell line that cannot be tokenised but
names a fetcher and a known host is treated as a write. A fetcher reached
through `sh -c`, `bash -c` or `eval` is followed into its string.

Mapping a call to a system:

* MCP: the tool name, narrowed by the server's name when two systems share a
  tool name (`create_branch` is both GitHub's and GitLab's); a grant for any
  remaining candidate on that server allows it.
* HTTP: the host, narrowed by the URL path when two systems share a host
  (`/wiki` is Confluence on `*.atlassian.net`, `/rest/api/3` is Jira), so the
  message names the right system.

A grant says a check passed for (system, operation class, server) and covers
MCP tool calls only. It does not bind to one target: tool arguments differ per
server and are not a reliable place to read a page id from. That limit is
documented in docs/access/README.md.

For hosts without a pre-execution hook, Wamala's contract is the only gate.
"""
from __future__ import annotations

import fnmatch
import os
import re
import shlex
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

_UNREADABLE = object()
_SYSTEMS = None
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_FETCHERS = {"curl", "wget", "http", "https", "xh", "xhs", "httpie"}
_SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
_SEPARATORS = {"|", "||", "&&", ";", "&"}
# Options that send a body (curl, wget, httpie), bare or with an attached value.
_CURL_DATA = ("-d", "--data", "--data-raw", "--data-binary", "--data-ascii", "--data-urlencode", "--json",
              "-F", "--form", "--form-string", "-T", "--upload-file")
_WGET_DATA = ("--post-data", "--post-file", "--body-data", "--body-file")
_MUTATING_TOOL = re.compile(
    r"(?:^|[_.\-])(create|update|edit|add|set|write|push|upload|assign|transition|link|remove|copy|reply|"
    r"move|delete|merge|close|resolve|erase|cancel|stop|unprotect|put|patch|post)(?:$|[_.\-])", re.I)
_BARE_HOST = re.compile(r"^(?:[a-z0-9-]+\.)+[a-z]{2,}(?::\d+)?(?:/\S*)?$", re.I)
UNKNOWN_SYSTEM = "unknown"


def grant_minutes() -> int:
    try:
        import access_state
        return access_state.GRANT_TTL_SECONDS // 60
    except Exception:  # noqa: BLE001
        return 30


def _systems():
    """The registry, or `_UNREADABLE` when it cannot be loaded (fail closed)."""
    global _SYSTEMS
    if _SYSTEMS is None:
        try:
            import access_registry
            _SYSTEMS = access_registry.load_systems()
        except Exception:  # noqa: BLE001 - reported as ASK below, never as "no system"
            _SYSTEMS = _UNREADABLE
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


def mcp_write(name: str) -> Optional[Tuple[List[str], str, str, str]]:
    """([candidate systems], op class, server, tool) when the tool writes to a known system."""
    server, tool = split_tool(name)
    systems = _systems()
    if systems is _UNREADABLE:
        if _MUTATING_TOOL.search(tool):
            return [UNKNOWN_SYSTEM], "write", server, tool
        return None
    import access_registry
    classes: Dict[str, str] = {}
    for sid, system in systems.items():
        cls = access_registry.tool_class(system, tool)
        if cls in ("write", "destructive"):
            classes[sid] = cls
    named = access_registry.systems_for_hint(systems, server) if server else []
    if named and not set(named) & set(classes):
        # The server's name says which system it is (`github`), and the tool is
        # not in that system's list - an older or newer tool name. Its verb
        # decides, and it is filed under the system the server names, never
        # under another system that happens to share the tool name.
        if not _MUTATING_TOOL.search(tool):
            return None
        destructive = re.search(r"(?:^|_)(delete|merge|erase|unprotect|move)(?:_|$)", tool)
        return sorted(named), "destructive" if destructive else "write", server, tool
    if not classes:
        return None
    candidates = sorted(classes)
    if len(candidates) > 1 and named:
        candidates = [sid for sid in candidates if sid in named] or candidates
    op_class = "destructive" if any(classes[s] == "destructive" for s in candidates) else "write"
    return candidates, op_class, server, tool


def _known_hosts() -> List[Tuple[str, str]]:
    """(host pattern, system) for registry host hints and confirmed base URLs."""
    pairs = []
    systems = _systems()
    if systems is not _UNREADABLE:
        for sid, system in systems.items():
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


def systems_for_url(url: str) -> List[str]:
    """Systems a URL's host belongs to, narrowed by path when a host is shared."""
    if "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host:
        return []
    candidates = sorted({sid for pattern, sid in _known_hosts() if fnmatch.fnmatch(host, pattern)})
    if len(candidates) > 1:
        systems = _systems()
        if systems is not _UNREADABLE:
            path = parsed.path or "/"
            by_path = [sid for sid in candidates
                       if any(path.startswith(h) for h in systems.get(sid, {}).get("path_hints", []))]
            if by_path:
                candidates = by_path
    return candidates


def _looks_like_url(arg: str) -> bool:
    return arg.startswith(("http://", "https://")) or bool(_BARE_HOST.match(arg))


def _segments(words: List[str]) -> List[List[str]]:
    out, current = [], []
    for word in words:
        if word in _SEPARATORS:
            if current:
                out.append(current)
            current = []
        else:
            current.append(word)
    if current:
        out.append(current)
    return out


def _fetch_write(segment: List[str]) -> Optional[Tuple[str, List[str]]]:
    """(method, urls) when this command segment is a fetcher sending a write."""
    idx = next((i for i, w in enumerate(segment) if os.path.basename(w) in _FETCHERS), None)
    if idx is None:
        return None
    tool = os.path.basename(segment[idx])
    rest = segment[idx + 1:]
    method, data, urls = "", False, []
    i = 0
    while i < len(rest):
        arg = rest[i]
        nxt = rest[i + 1] if i + 1 < len(rest) else ""
        if tool == "curl":
            if arg in ("-X", "--request"):
                method, i = nxt.upper(), i + 1
            elif arg.startswith("--request="):
                method = arg.split("=", 1)[1].upper()
            elif arg.startswith("-X") and len(arg) > 2:
                method = arg[2:].upper()
            elif arg in _CURL_DATA:
                data, i = True, i + 1
            elif any(arg.startswith(opt + "=") for opt in _CURL_DATA if opt.startswith("--")):
                data = True
            elif arg[:2] in ("-d", "-F", "-T") and len(arg) > 2:
                data = True
            elif arg == "--url":
                urls.append(nxt)
                i += 1
            elif arg.startswith("--url="):
                urls.append(arg.split("=", 1)[1])
            elif not arg.startswith("-") and _looks_like_url(arg):
                urls.append(arg)
        elif tool == "wget":
            if arg == "--method":
                method, i = nxt.upper(), i + 1
            elif arg.startswith("--method="):
                method = arg.split("=", 1)[1].upper()
            elif arg in _WGET_DATA:
                data, i = True, i + 1
            elif any(arg.startswith(opt + "=") for opt in _WGET_DATA):
                data = True
            elif not arg.startswith("-") and _looks_like_url(arg):
                urls.append(arg)
        else:  # httpie / xh: `http [METHOD] URL [items]`
            if arg.upper() in _WRITE_METHODS | {"GET", "HEAD", "OPTIONS"} and not method:
                method = arg.upper()
            elif not arg.startswith("-") and _looks_like_url(arg):
                urls.append(arg)
            elif re.match(r"^[^=:\s]+(:=|=|@)", arg) and urls:
                data = True
        i += 1
    if not method and data:
        method = "POST"
    if method in _WRITE_METHODS and urls:
        return method, urls
    return None


def _nested(segment: List[str]) -> List[str]:
    """Command strings a segment runs in a nested shell (`sh -c '...'`, `eval '...'`)."""
    out = []
    for i, word in enumerate(segment):
        base = os.path.basename(word)
        if base in _SHELLS:
            for j in range(i + 1, len(segment) - 1):
                if segment[j] == "-c" or (segment[j].startswith("-") and segment[j].endswith("c")
                                          and len(segment[j]) <= 4):
                    out.append(segment[j + 1])
                    break
        elif base == "eval":
            out.append(" ".join(segment[i + 1:]))
    return out


def http_write(command: str, _depth: int = 0) -> Optional[Tuple[List[str], str, str]]:
    """([systems], method, host) for a fetcher writing to a known system's host."""
    if _depth > 3:
        return None
    try:
        words = shlex.split(command, posix=True)
    except ValueError:
        # Unbalanced quotes. A fetcher and a known host in the same line is
        # treated as a write rather than trusted as "not a write".
        if any(re.search(r"(?<![\w-])%s(?![\w-])" % f, command) for f in _FETCHERS):
            for token in re.findall(r"(?:https?://)?[\w.-]+\.[a-z]{2,}[^\s'\"]*", command, re.I):
                systems = systems_for_url(token)
                if systems:
                    return systems, "UNPARSED", (urlparse(token if "://" in token else "https://" + token)
                                                  .hostname or "")
        return None
    systems_all = _systems()
    for segment in _segments(words):
        for inner in _nested(segment):
            hit = http_write(inner, _depth + 1)
            if hit:
                return hit
        found = _fetch_write(segment)
        if not found:
            continue
        method, urls = found
        for url in urls:
            systems = systems_for_url(url)
            host = (urlparse(url if "://" in url else "https://" + url).hostname or "").lower()
            if systems:
                return systems, method, host
            if systems_all is _UNREADABLE:
                return [UNKNOWN_SYSTEM], method, host
    return None


def has_grant(system: str, op_class: str, server: str = "") -> bool:
    if system == UNKNOWN_SYSTEM:
        return False
    try:
        import access_state
        grants = access_state.valid_grants()
    except Exception:  # noqa: BLE001 - no grants readable means no grant
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


def advice(systems: List[str], op_class: str) -> str:
    if systems == [UNKNOWN_SYSTEM]:
        return ("The access registry could not be read (`agent-skills access systems` shows why), so this "
                "write cannot be matched to a system; the guard asks rather than assumes.")
    system = systems[0] if len(systems) == 1 else "<%s>" % "|".join(systems)
    return ("Run `agent-skills access check --system %s --op %s --target <url-or-key> --user-authorised` and "
            "follow its result; a passing check allows this for %d minutes." % (system, op_class, grant_minutes()))
