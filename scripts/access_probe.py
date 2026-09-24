#!/usr/bin/env python3
"""Opt-in, non-mutating permission probes (`access check --probe`).

A probe asks the system whether the account may do the operation on the
target, without doing it: Confluence `content/{id}?expand=operations`, Jira
`mypermissions`. It never probes a write by attempting one.

The credential comes only from an identity the user created in the Access
Resolver (`agent-skills access set`), resolved in-process through
`resolve_access(values_out=...)`: it never crosses argv, stdout, a cache or a
log. A credential that was merely *found* - a keychain item a launcher reads,
a token in a host config - is never used here. That credential belongs to the
MCP route, and using it directly is exactly the move that defeats a read-only
setting.

What a probe proves is stated plainly: it speaks for the identity it used. When
that identity is not the MCP route's own account, the report says so.
"""
from __future__ import annotations

import base64
import json
import os
import socket
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

import access as resolver

TIMEOUT = 15
CACHE_TTL_SECONDS = 10 * 60


def _cache_path(key: list) -> Path:
    import hashlib
    import access_state
    digest = hashlib.sha256(json.dumps(key, sort_keys=True).encode("utf-8")).hexdigest()[:32]
    return access_state.cache_dir() / "probes" / ("%s.json" % digest)


def _cache_get(key: list) -> Optional[dict]:
    import time
    try:
        data = json.loads(_cache_path(key).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    age = time.time() - data.get("at", 0)
    if not 0 <= age < CACHE_TTL_SECONDS or data.get("key") != key:
        return None
    result = dict(data["result"])
    result["evidence"] += " (probed %d min ago)" % (age // 60)
    return result


def _cache_put(key: list, result: dict) -> None:
    """Keep a probe's answer briefly. It holds no secret: the key is the
    system, site, target, operation and identity name; the value is the
    verdict and its wording."""
    import time
    path = _cache_path(key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"key": key, "at": time.time(), "result": result}), encoding="utf-8")
        os.chmod(str(tmp), 0o600)
        tmp.replace(path)
    except OSError:
        pass


def _auth_header(values: dict) -> Optional[str]:
    token = values.get("token")
    if not token:
        return None
    login = values.get("login")
    if login:
        raw = ("%s:%s" % (login, token)).encode("utf-8")
        return "Basic " + base64.b64encode(raw).decode("ascii")
    return "Bearer " + token


def _get(url: str, header: str) -> tuple:
    request = urllib.request.Request(url, headers={"Authorization": header, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT, context=ssl.create_default_context()) as response:
            return response.status, json.loads(response.read(1_000_000).decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        return exc.code, {}
    except (urllib.error.URLError, socket.timeout, ConnectionError, OSError) as exc:
        return None, {"network": str(getattr(exc, "reason", exc))[:120]}
    except ValueError:
        return 0, {}


def _identity(service: str, base_url: str, cwd: Path):
    values: dict = {}
    resolution = resolver.resolve_access(service, base_url, ["host", "login", "token"], {"token"}, cwd,
                                         allow_capability=False, values_out=values)
    if resolution.status != "resolved" or not values.get("token"):
        values = {}
        resolution = resolver.resolve_access(service, base_url, ["host", "token"], {"token"}, cwd,
                                             allow_capability=False, values_out=values)
    if resolution.status != "resolved" or not values.get("token"):
        return None, None
    return values, resolution


def probe(system: dict, target: dict, base_url: str, cwd: Path, op_class: str, fresh: bool = False) -> Optional[dict]:
    """{status, rung, evidence}, cached for CACHE_TTL_SECONDS unless `fresh`.

    The cache key is the system, site, target, operation and the identity's
    name - never a value. A network failure is never cached: it is a reason to
    try again, not an answer about the account.
    """
    probes = system.get("probes") or {}
    service = probes.get("auth_service")
    if not service or not base_url or not target.get("id"):
        return None
    values, resolution = _identity(service, base_url, cwd)
    if values is None:
        return {"status": "unknown", "rung": "target",
                "evidence": "no Agent Skills identity for %s to probe with (`agent-skills access set`); the "
                            "route's own credential is never used for a probe" % service}
    key = [system.get("id"), resolver.resource_host(base_url), target.get("kind"), target.get("id"), op_class,
           resolution.profile or "environment:%s" % resolver.resource_host(values.get("host", ""))]
    if not fresh:
        cached = _cache_get(key)
        if cached is not None:
            return cached
    result = _probe(system, target, base_url, op_class, values, resolution)
    if result is not None and result.get("status") in ("pass", "fail"):
        _cache_put(key, result)
    return result


def _probe(system: dict, target: dict, base_url: str, op_class: str, values: dict, resolution) -> Optional[dict]:
    probes = system.get("probes") or {}
    # The base URL comes from the route, and a project-scoped route is read from
    # a file inside the repository - attacker-controlled for anyone who can open
    # a pull request. The credential is sent only to the site the identity
    # itself names (from the user's own config or environment), never to a site
    # a repository chose.
    identity_host = resolver.resource_host(values.get("host", ""))
    route_host = resolver.resource_host(base_url)
    if not identity_host or identity_host != route_host:
        return {"status": "unknown", "rung": "target",
                "evidence": "not probing: the route points at %s but the identity is for %s; a credential is only "
                            "sent to the site its identity names" % (route_host or "?", identity_host or "no site")}
    header = _auth_header(values)
    who = ("identity %r" % resolution.profile) if resolution.profile else "the identity in your environment"
    base = base_url.rstrip("/")
    identity_url = probes["identity"].replace("GET ", "").replace("{base}", base)
    status, _body = _get(identity_url, header)
    if status is None:
        return {"status": "network", "rung": "auth", "evidence": "identity probe could not reach %s" % base}
    if status in (401, 403):
        return {"status": "fail", "rung": "auth", "evidence": "%s was rejected by %s (HTTP %d)" % (who, base, status)}
    if status != 200:
        return {"status": "unknown", "rung": "auth", "evidence": "identity probe returned HTTP %s" % status}
    if system["id"] == "confluence" and target.get("kind") == "page":
        url = probes["target_permissions"].replace("GET ", "").replace("{base}", base).replace("{id}", target["id"])
        status, body = _get(url, header)
        if status is None:
            return {"status": "network", "rung": "target", "evidence": "permission probe could not reach %s" % base}
        if status == 404:
            return {"status": "fail", "rung": "target", "evidence": "page %s is not visible to %s (missing, or no view "
                    "permission)" % (target["id"], who)}
        if status != 200:
            return {"status": "unknown", "rung": "target", "evidence": "permission probe returned HTTP %s" % status}
        ops = {(o.get("operation"), o.get("targetType")) for o in body.get("operations", []) if isinstance(o, dict)}
        wanted = "delete" if op_class == "destructive" else "update"
        if op_class == "read" or (wanted, "page") in ops:
            return {"status": "pass", "rung": "target",
                    "evidence": "%s may %s page %s (expand=operations)" % (who, wanted if op_class != "read" else "read",
                                                                          target["id"])}
        return {"status": "fail", "rung": "target", "evidence": "%s lacks the '%s' permission on page %s; ask the "
                "space owner" % (who, wanted, target["id"])}
    if system["id"] == "jira" and target.get("kind") == "issue":
        url = probes["target_permissions"].replace("GET ", "").replace("{base}", base).replace("{id}", target["id"])
        status, body = _get(url, header)
        if status is None:
            return {"status": "network", "rung": "target", "evidence": "permission probe could not reach %s" % base}
        if status != 200:
            return {"status": "unknown", "rung": "target", "evidence": "permission probe returned HTTP %s" % status}
        perms = body.get("permissions") or {}
        wanted = "DELETE_ISSUES" if op_class == "destructive" else "EDIT_ISSUES"
        have = bool((perms.get(wanted) or {}).get("havePermission"))
        if op_class == "read" or have:
            return {"status": "pass", "rung": "target", "evidence": "%s has %s on %s" % (who, wanted, target["id"])}
        return {"status": "fail", "rung": "target", "evidence": "%s lacks %s on %s; ask a project admin"
                % (who, wanted, target["id"])}
    return None
