#!/usr/bin/env python3
"""What Access Discovery remembers, and where.

| What | Where | Why there |
| --- | --- | --- |
| Local route knowledge | `<config>/access/routes.json` (0600) | user facts; never shipped, never committed |
| Access policy overrides | `<config>/access-policy.json` (0600) | the user's own tightening |
| Write audit | `<install>/state/access/audit.jsonl` | survives update and rollback |
| Write grants | `<install>/cache/access/grants/` | safe to delete; expire after 30 minutes |

`<config>` is the Access Resolver's config directory (`access.config_dir()`),
so nothing new decides where user configuration lives. `<install>` is
`AGENT_SKILLS_HOME`, `~/.agent-skills` by default.

Local route knowledge is where organisation specifics live: a wrapper's name,
its mode switch, its keychain item name, the company's base URL. They are
learned on this machine, written only after the user confirms them, and never
contain a secret. Every file carries a versioned schema; a release that does
not know a file ignores it, which is what makes rollback to 1.4.0 safe.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple


SCHEMA_ROUTES = "agent-skills.local-routes/v1"
SCHEMA_POLICY = "agent-skills.access-policy/v1"
SCHEMA_AUDIT = "agent-skills.access-audit/v1"
SCHEMA_GRANT = "agent-skills.access-grant/v1"
GRANT_TTL_SECONDS = 30 * 60


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def config_dir() -> Path:
    # The Access Resolver owns where user configuration lives. Imported late so
    # the Execution Guard, which reads grants on every tool call, does not load
    # the resolver.
    import access as _resolver
    return _resolver.config_dir()


def install_home() -> Path:
    override = os.environ.get("AGENT_SKILLS_HOME")
    return Path(override) if override else Path(os.environ.get("HOME") or str(Path.home())) / ".agent-skills"


def routes_path() -> Path:
    return config_dir() / "access" / "routes.json"


def policy_path() -> Path:
    return config_dir() / "access-policy.json"


def audit_path() -> Path:
    return install_home() / "state" / "access" / "audit.jsonl"


def cache_dir() -> Path:
    return install_home() / "cache" / "access"


def grants_dir() -> Path:
    return cache_dir() / "grants"


def _write_private(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    for directory in (config_dir(), path.parent):
        try:
            if str(path).startswith(str(config_dir())):
                os.chmod(directory, 0o700)
        except OSError:
            pass
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.chmod(tmp, 0o600)
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Local route knowledge
# ---------------------------------------------------------------------------
def load_routes() -> dict:
    path = routes_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict) or data.get("schema") != SCHEMA_ROUTES:
        data = {"schema": SCHEMA_ROUTES, "routes": [], "decisions": []}
    data.setdefault("routes", [])
    data.setdefault("decisions", [])
    return data


def save_routes(data: dict) -> None:
    data["schema"] = SCHEMA_ROUTES
    _write_private(routes_path(), data)


def _norm_command(command: str) -> str:
    return os.path.normpath(os.path.expanduser(command or "")) if command else ""


def match_route(data: dict, host: str, server_name: str, command: str) -> Optional[dict]:
    for route in data.get("routes", []):
        match = route.get("match", {})
        if not fnmatch.fnmatch(host, match.get("host", "*")):
            continue
        if match.get("server_name") and match["server_name"] != server_name:
            continue
        if match.get("command") and _norm_command(match["command"]) != _norm_command(command):
            continue
        return route
    return None


def is_stale(route: dict, launcher_sha256: str) -> bool:
    recorded = (route.get("fingerprint") or {}).get("launcher_sha256")
    return bool(recorded and launcher_sha256 and recorded != launcher_sha256)


def remember_route(entry: dict) -> Tuple[dict, bool]:
    """Add or replace a route entry. Returns (entry, replaced).

    Callers build `entry` from inspection results and flags only; no code path
    that can see a secret value reaches this function.
    """
    data = load_routes()
    replaced = False
    kept = []
    for route in data["routes"]:
        if route.get("match") == entry.get("match"):
            replaced = True
            continue
        kept.append(route)
    kept.append(entry)
    data["routes"] = kept
    save_routes(data)
    return entry, replaced


def remember_decision(decision: dict) -> None:
    data = load_routes()
    data["decisions"] = [d for d in data["decisions"]
                         if (d.get("system"), d.get("operation"), d.get("scope"))
                         != (decision.get("system"), decision.get("operation"), decision.get("scope"))]
    data["decisions"].append(decision)
    save_routes(data)


def forget(system: str = "", everything: bool = False) -> Tuple[int, int]:
    data = load_routes()
    if everything:
        removed = (len(data["routes"]), len(data["decisions"]))
        data["routes"], data["decisions"] = [], []
    else:
        before_r, before_d = len(data["routes"]), len(data["decisions"])
        data["routes"] = [r for r in data["routes"] if system not in r.get("systems", [])]
        data["decisions"] = [d for d in data["decisions"] if d.get("system") != system]
        removed = (before_r - len(data["routes"]), before_d - len(data["decisions"]))
    save_routes(data)
    return removed


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------
# The floor. A user file may add to `deny` and `always_confirm`; it may not
# remove anything here, and a key that tries to is rejected rather than ignored.
NEVER = (
    "enable write mode globally",
    "edit a host MCP configuration without the user confirming the exact change",
    "use a found credential outside a configured, qualified route",
    "retry a blocked write through another route to get around a fail at mode, target or policy",
    "ask the user to paste a secret into the chat",
    "count a browser session as a write route for a system with an API",
)
_TIGHTEN_KEYS = {"schema", "deny", "always_confirm", "require_probe_for_write"}
_LOOSEN_KEYS = {"never", "allow", "allow_found_credentials", "allow_secret_in_chat", "allow_global_write",
                "allow_unqualified_retry", "allow_browser_writes", "skip_preview", "skip_confirmation",
                "allow_host_config_edit"}


class PolicyError(ValueError):
    pass


def load_policy() -> dict:
    policy = {"deny": [], "always_confirm": [], "require_probe_for_write": False, "source": "built-in",
              "never": list(NEVER)}
    path = policy_path()
    if not path.exists():
        return policy
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PolicyError("%s is not readable JSON (%s); fix or remove it - access checks fail closed "
                          "until then" % (path, exc))
    if not isinstance(data, dict):
        raise PolicyError("%s must be a JSON object" % path)
    loosening = sorted(set(data) & _LOOSEN_KEYS)
    if loosening:
        raise PolicyError("%s tries to loosen the policy floor (%s). A policy file may only tighten: "
                          "add to 'deny' or 'always_confirm'." % (path, ", ".join(loosening)))
    unknown = sorted(set(data) - _TIGHTEN_KEYS)
    if unknown:
        raise PolicyError("%s has unknown keys %s; refusing to guess what they mean" % (path, ", ".join(unknown)))
    for key in ("deny", "always_confirm"):
        rules = data.get(key, [])
        if not isinstance(rules, list) or not all(isinstance(r, dict) for r in rules):
            raise PolicyError("%s: '%s' must be a list of {system, operation} objects" % (path, key))
        policy[key] = rules
    policy["require_probe_for_write"] = bool(data.get("require_probe_for_write", False))
    policy["source"] = str(path)
    return policy


def policy_rule_matches(rule: dict, system: str, operation: str) -> bool:
    return (fnmatch.fnmatch(system, rule.get("system", "*"))
            and fnmatch.fnmatch(operation, rule.get("operation", "*")))


# ---------------------------------------------------------------------------
# Audit and grants
# ---------------------------------------------------------------------------
def append_audit(record: dict) -> Path:
    path = audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    allowed = ("host", "system", "operation", "target", "route", "result", "confirmation")
    line = {"schema": SCHEMA_AUDIT, "ts": utc_now()}
    for key in allowed:
        line[key] = str(record.get(key, ""))[:200]
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, sort_keys=True) + "\n")
    return path


def write_grant(system: str, operation: str, target: str, host: str, server_name: str, route: str) -> Path:
    directory = grants_dir()
    directory.mkdir(parents=True, exist_ok=True)
    now = time.time()
    payload = {"schema": SCHEMA_GRANT, "system": system, "operation": operation, "target": target,
               "host": host or "", "server_name": server_name or "", "route": route,
               "created": int(now), "expires": int(now + GRANT_TTL_SECONDS)}
    digest = hashlib.sha256(json.dumps([system, operation, target, host, server_name], sort_keys=True)
                            .encode("utf-8")).hexdigest()[:24]
    path = directory / ("%s.json" % digest)
    tmp = path.with_suffix(".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    tmp.replace(path)
    return path


def valid_grants() -> List[dict]:
    directory = grants_dir()
    if not directory.is_dir():
        return []
    now = time.time()
    grants = []
    for path in directory.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("schema") != SCHEMA_GRANT:
            continue
        if data.get("expires", 0) < now:
            try:
                path.unlink()
            except OSError:
                pass
            continue
        grants.append(data)
    return grants
