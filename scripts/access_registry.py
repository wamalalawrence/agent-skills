#!/usr/bin/env python3
"""The shipped system registry: public, upstream knowledge about external systems.

One JSON file per system under `lib/access/systems/`. A file says which MCP
server packages are known for the system, which of their settings decide the
mode (read-only flags, tool allow-lists, toolsets, scope filters), which tools
write, how to read a target out of a URL, and which non-mutating probes exist.
Adding a system is adding a file; nothing here branches on a system id.

Nothing organisation-specific belongs in these files. A company's own launcher
script is understood by the wrapper inspector (`access_inspect.py`) and by the
user's local route knowledge (`access_state.py`), never by the product.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import unquote, urlparse

SCHEMA = "agent-skills.access-system/v1"
SYSTEMS_DIR = Path(__file__).resolve().parent.parent / "lib" / "access" / "systems"

OPERATIONS = ("read", "write", "destructive")

# Operation words a caller may pass as `--op`, mapped to the class that governs
# them. Closing, resolving, merging, moving and deleting are grouped with
# destructive on purpose: policy wants explicit confirmation naming the targets
# for all of them. German spellings are here because users ask in German.
VERB_CLASS = {
    "read": "read", "get": "read", "view": "read", "search": "read", "list": "read", "fetch": "read",
    "lesen": "read", "anzeigen": "read", "suchen": "read",
    "write": "write", "update": "write", "edit": "write", "create": "write", "comment": "write",
    "transition": "write", "assign": "write", "link": "write", "label": "write", "approve": "write",
    "publish": "write", "deploy": "write", "restart": "write", "rerun": "write", "upload": "write",
    "aktualisieren": "write", "ändern": "write", "bearbeiten": "write", "anlegen": "write",
    "erstellen": "write", "kommentieren": "write", "zuweisen": "write", "verknüpfen": "write",
    "destructive": "destructive", "delete": "destructive", "move": "destructive", "close": "destructive",
    "resolve": "destructive", "merge": "destructive", "bulk": "destructive",
    "löschen": "destructive", "verschieben": "destructive", "schließen": "destructive",
    "erledigen": "destructive",
}

# Tool names that look like a mutation when the registry does not list the tool.
_MUTATING_TOOL = re.compile(
    r"(?:^|_)(create|update|edit|add|set|write|push|upload|assign|transition|link|remove|"
    r"copy|reply|move|delete|merge|close|resolve|erase|cancel|stop|unprotect)(?:_|$)")
_DESTRUCTIVE_TOOL = re.compile(r"(?:^|_)(delete|move|merge|erase|unprotect)(?:_|$)")


class RegistryError(ValueError):
    pass


def operation_class(op: str) -> Optional[str]:
    return VERB_CLASS.get((op or "").strip().lower())


def load_systems(directory: Optional[Path] = None) -> Dict[str, dict]:
    directory = directory or SYSTEMS_DIR
    systems: Dict[str, dict] = {}
    if not directory.is_dir():
        return systems
    for path in sorted(directory.glob("*.json")):
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        problems = validate_system(data)
        if problems:
            raise RegistryError("%s: %s" % (path.name, "; ".join(problems)))
        systems[data["id"]] = data
    return systems


def validate_system(data: dict) -> List[str]:
    problems = []
    if not isinstance(data, dict):
        return ["not an object"]
    if data.get("schema") != SCHEMA:
        problems.append("schema must be %s" % SCHEMA)
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,40}", str(data.get("id", ""))):
        problems.append("id is missing or malformed")
    for upstream in data.get("mcp_upstreams", []):
        if not upstream.get("id"):
            problems.append("an mcp upstream has no id")
        if not upstream.get("verified_against"):
            problems.append("upstream %s records no verified_against source" % upstream.get("id"))
        if upstream.get("default_mode") not in ("read-only", "read-write", "modify", "unknown"):
            problems.append("upstream %s has an unknown default_mode" % upstream.get("id"))
        tools = upstream.get("tools", {})
        if not isinstance(tools.get("write", []), list) or not isinstance(tools.get("destructive", []), list):
            problems.append("upstream %s tools must be lists" % upstream.get("id"))
    return problems


def token_is(arg: str, needle: str) -> bool:
    """Does one argument name this package or image?

    Exactly, or followed by a version or tag (`mcp-atlassian@1.2`,
    `mcp-atlassian==0.11`, `ghcr.io/x/y:latest`), or as the last path segment
    of an npm scope. Never as a substring: a company wrapper is routinely named
    after what it wraps (`acme-mcp-atlassian`, `acme_mcp_atlassian.sh`), and
    calling it the upstream would report the upstream's default mode for a
    script whose own mode is the whole question.
    """
    arg = str(arg).strip("\"'")
    if arg == needle:
        return True
    return any(arg.startswith(needle + sep) for sep in ("@", "==", ":", "[", ">=", "~="))


def match_upstream(system: dict, command: str, args: List[str], url: str = "") -> Optional[dict]:
    """Which known upstream a launch line or URL runs, if any."""
    # Arguments are matched token by token (`uvx mcp-atlassian`, `docker run
    # ... <image>`); the command by exact basename. Never by substring.
    for upstream in system.get("mcp_upstreams", []):
        match = upstream.get("match", {})
        if any(token_is(a, n) for a in args or [] for n in match.get("args_contain", [])):
            return upstream
        # Exact basename only. A company wrapper is routinely *named* after the
        # server it wraps (`<org>-mcp-atlassian`); a substring match would call
        # that wrapper the upstream and report the upstream's default mode.
        if command and os.path.basename(command) in match.get("command_names", []):
            return upstream
        if url and any(n in url for n in match.get("url_contains", [])):
            return upstream
    return None


def all_mode_keys(systems: Dict[str, dict]) -> set:
    """Env names whose values may be read: mode, filter and base-URL keys only."""
    keys = set()
    for system in systems.values():
        for upstream in system.get("mcp_upstreams", []):
            for rule in upstream.get("mode_rules", []):
                if rule.get("env"):
                    keys.add(rule["env"])
            keys.update(upstream.get("tool_filters", {}).get("env", []))
            keys.update(upstream.get("toolset_filters", {}).get("env", []))
            keys.update(upstream.get("scope_filters", {}).keys())
            keys.update(upstream.get("base_url_env", []))
    return keys


def all_credential_keys(systems: Dict[str, dict]) -> set:
    keys = set()
    for system in systems.values():
        for upstream in system.get("mcp_upstreams", []):
            keys.update(upstream.get("credential_env", []))
    return keys


def tool_class(system: dict, tool: str, upstream: Optional[dict] = None) -> Optional[str]:
    """read | write | destructive for an MCP tool name, or None if not this system's.

    The registry lists are authoritative. For an unlisted tool carrying the
    system's prefix, the verb decides, which is a heuristic and is reported
    as such by the caller.
    """
    ups = [upstream] if upstream else system.get("mcp_upstreams", [])
    for up in ups:
        tools = up.get("tools", {})
        if tool in tools.get("destructive", []):
            return "destructive"
        if tool in tools.get("write", []):
            return "write"
    for up in ups:
        prefix = up.get("tool_prefix")
        if prefix and tool.startswith(prefix):
            if _DESTRUCTIVE_TOOL.search(tool):
                return "destructive"
            return "write" if _MUTATING_TOOL.search(tool) else "read"
    return None


def host_matches(system: dict, host: str) -> bool:
    host = (host or "").lower()
    return any(fnmatch.fnmatch(host, pattern) for pattern in system.get("host_hints", []))


def systems_for_hint(systems: Dict[str, dict], text: str) -> List[str]:
    """System ids a server name, command or URL plausibly refers to."""
    lowered = (text or "").lower()
    found = []
    for sid, system in systems.items():
        if any(h in lowered for h in system.get("name_hints", [])):
            found.append(sid)
    return found


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------
def parse_target(system: dict, raw: str) -> dict:
    """Read what a target is from a URL or key. Never contacts the network."""
    raw = (raw or "").strip()
    if not raw:
        return {"kind": "none", "raw": ""}
    parser = _PARSERS.get(system.get("target_parser", ""), _parse_generic)
    result = parser(raw)
    result["raw"] = raw
    return result


def _host_of(raw: str) -> str:
    try:
        return (urlparse(raw).hostname or "").lower()
    except ValueError:
        return ""


def _parse_confluence(raw: str) -> dict:
    if raw.startswith(("http://", "https://")):
        parsed = urlparse(raw)
        path = unquote(parsed.path)
        base = "%s://%s" % (parsed.scheme, parsed.netloc) + ("/wiki" if path.startswith("/wiki/") else "")
        m = re.search(r"/spaces/([^/]+)/pages/(\d+)", path)
        if m:
            return {"kind": "page", "id": m.group(2), "space": m.group(1), "host": _host_of(raw), "base": base}
        m = re.search(r"[?&]pageId=(\d+)", parsed.query and "?" + parsed.query or "")
        if m:
            return {"kind": "page", "id": m.group(1), "space": "", "host": _host_of(raw), "base": base}
        m = re.search(r"/wiki/x/([A-Za-z0-9_-]+)", path)
        if m:
            return {"kind": "tiny-link", "id": m.group(1), "space": "", "host": _host_of(raw), "base": base,
                    "note": "a short link does not name its space; the space is known only after a read"}
        m = re.search(r"/spaces/([^/]+)", path)
        if m:
            return {"kind": "space", "id": m.group(1), "space": m.group(1), "host": _host_of(raw), "base": base}
        return {"kind": "unknown", "host": _host_of(raw), "base": base}
    m = re.fullmatch(r"(~?[A-Za-z0-9_-]+):(.+)", raw)
    if m:
        return {"kind": "page-title", "id": m.group(2), "space": m.group(1)}
    if re.fullmatch(r"\d+", raw):
        return {"kind": "page", "id": raw, "space": ""}
    if re.fullmatch(r"~?[A-Za-z0-9_-]+", raw):
        return {"kind": "space", "id": raw, "space": raw}
    return {"kind": "unknown"}


def _parse_jira(raw: str) -> dict:
    key_re = r"([A-Z][A-Z0-9_]+)-(\d+)"
    if raw.startswith(("http://", "https://")):
        parsed = urlparse(raw)
        m = re.search(r"/browse/" + key_re, parsed.path) or re.search(r"selectedIssue=" + key_re, parsed.query)
        base = "%s://%s" % (parsed.scheme, parsed.netloc)
        if m:
            return {"kind": "issue", "id": "%s-%s" % (m.group(1), m.group(2)), "project": m.group(1),
                    "host": _host_of(raw), "base": base}
        m = re.search(r"/projects/([A-Z][A-Z0-9_]+)", parsed.path)
        if m:
            return {"kind": "project", "id": m.group(1), "project": m.group(1), "host": _host_of(raw), "base": base}
        return {"kind": "unknown", "host": _host_of(raw), "base": base}
    m = re.fullmatch(key_re, raw)
    if m:
        return {"kind": "issue", "id": raw, "project": m.group(1)}
    if re.fullmatch(r"[A-Z][A-Z0-9_]+", raw):
        return {"kind": "project", "id": raw, "project": raw}
    return {"kind": "unknown"}


def _parse_repo_host(raw: str, mr_word: str) -> dict:
    if raw.startswith(("http://", "https://")):
        parsed = urlparse(raw)
        parts = [p for p in parsed.path.split("/") if p and p != "-"]
        if len(parts) >= 2:
            owner, repo = parts[0], parts[1].replace(".git", "")
            result = {"kind": "repository", "id": "%s/%s" % (owner, repo), "owner": owner, "repo": repo,
                      "host": _host_of(raw)}
            if len(parts) >= 4 and parts[2] in ("pull", "issues", mr_word) and parts[3].isdigit():
                result.update(kind={"pull": "pull-request", "issues": "issue"}.get(parts[2], "merge-request"),
                              number=parts[3])
            return result
        return {"kind": "unknown", "host": _host_of(raw)}
    m = re.fullmatch(r"([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)(?:#(\d+))?", raw)
    if m:
        result = {"kind": "repository", "id": "%s/%s" % (m.group(1), m.group(2)), "owner": m.group(1), "repo": m.group(2)}
        if m.group(3):
            result.update(kind="issue-or-pull", number=m.group(3))
        return result
    return {"kind": "unknown"}


def _parse_generic(raw: str) -> dict:
    if raw.startswith(("http://", "https://")):
        return {"kind": "url", "id": raw, "host": _host_of(raw)}
    return {"kind": "key", "id": raw}


_PARSERS = {
    "confluence": _parse_confluence,
    "jira": _parse_jira,
    "github": lambda raw: _parse_repo_host(raw, "pull"),
    "gitlab": lambda raw: _parse_repo_host(raw, "merge_requests"),
}


def target_scope_value(target: dict, scope_kind: str) -> str:
    """The value a scope filter compares against (space key, project key)."""
    return str(target.get(scope_kind) or "")


def is_personal_space(space: str) -> bool:
    return space.startswith("~")
