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
import socket
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

import access as resolver

TIMEOUT = 15


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


def probe(system: dict, target: dict, base_url: str, cwd: Path, op_class: str) -> Optional[dict]:
    """{status: pass|fail|unknown|network, rung: auth|target, evidence} or None if not probeable."""
    probes = system.get("probes") or {}
    service = probes.get("auth_service")
    if not service or not base_url or not target.get("id"):
        return None
    values: dict = {}
    resolution = resolver.resolve_access(service, base_url, ["host", "login", "token"], {"token"}, cwd,
                                         allow_capability=False, values_out=values)
    if resolution.status != "resolved" or not values.get("token"):
        values = {}
        resolution = resolver.resolve_access(service, base_url, ["host", "token"], {"token"}, cwd,
                                             allow_capability=False, values_out=values)
    if resolution.status != "resolved" or not values.get("token"):
        return {"status": "unknown", "rung": "target",
                "evidence": "no Agent Skills identity for %s to probe with (`agent-skills access set`); the "
                            "route's own credential is never used for a probe" % service}
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
