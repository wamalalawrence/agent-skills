#!/usr/bin/env python3
"""Ask a configured MCP server which tools it offers. Opt-in (`access check --live`).

Static reading infers a mode; asking the server verifies part of it. This does
the MCP stdio handshake - `initialize`, `notifications/initialized`,
`tools/list` - with a short timeout, then terminates the process.

It only ever starts a server the user has already configured in a host, with
that host's configured command, arguments and environment: the user already
chose to run it. It is never run by `doctor`, and never against a command that
is not in a host configuration.

"A write tool is present" is necessary, not sufficient: an explicit read-only
setting is authoritative over the tool list, and the caller applies that rule.
Tool names are returned; nothing the server prints on stderr is kept.
"""
from __future__ import annotations

import json
import os
import select
import subprocess
import time
from pathlib import Path
from typing import Optional

import access_hosts as hosts_mod

PROTOCOL_VERSION = "2025-06-18"
DEFAULT_TIMEOUT = 10.0


def _host_env(route: dict, repo_root: Optional[Path]) -> dict:
    """The server's configured env block, read fresh and kept in memory only."""
    env = dict(os.environ)
    try:
        data = hosts_mod.load_raw(Path(route["file"]), hosts_mod.format_of(route["host"], Path(route["file"])))
    except hosts_mod.HostReadError:
        return env
    for scope, name, entry in hosts_mod._servers(data, hosts_mod.format_of(route["host"], Path(route["file"])), repo_root):
        if name == route["name"] and isinstance(entry.get("env"), dict):
            for key, value in entry["env"].items():
                env[str(key)] = str(value)
            break
    return env


def introspect_route(route: dict, repo_root: Optional[Path], timeout: float = DEFAULT_TIMEOUT) -> dict:
    if route.get("transport") != "stdio" or not route.get("command"):
        return {"error": "only stdio servers can be introspected"}
    argv = [os.path.expanduser(route["command"])] + list(_args_of(route, repo_root))
    return introspect(argv, _host_env(route, repo_root), timeout)


def _args_of(route: dict, repo_root: Optional[Path]):
    try:
        fmt = hosts_mod.format_of(route["host"], Path(route["file"]))
        data = hosts_mod.load_raw(Path(route["file"]), fmt)
        for _scope, name, entry in hosts_mod._servers(data, fmt, repo_root):
            if name == route["name"]:
                return [str(a) for a in entry.get("args") or []]
    except hosts_mod.HostReadError:
        pass
    return []


def introspect(argv, env: dict, timeout: float = DEFAULT_TIMEOUT) -> dict:
    started = time.monotonic()
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                env=env, start_new_session=True)
    except OSError as exc:
        return {"error": "could not start: %s" % (exc.strerror or exc)}
    buffer = b""

    def send(message: dict) -> None:
        proc.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
        proc.stdin.flush()

    def receive(want_id: int) -> Optional[dict]:
        nonlocal buffer
        while True:
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                try:
                    message = json.loads(line.decode("utf-8", errors="replace"))
                except ValueError:
                    continue
                if isinstance(message, dict) and message.get("id") == want_id:
                    return message
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                return None
            ready, _w, _x = select.select([proc.stdout], [], [], remaining)
            if not ready:
                return None
            chunk = os.read(proc.stdout.fileno(), 65536)
            if not chunk:
                return None
            buffer += chunk

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                         "clientInfo": {"name": "agent-skills-access", "version": "1"}}})
        init = receive(1)
        if init is None:
            return {"error": "no initialize response within %.0fs (timeout or crash)" % timeout}
        if "error" in init:
            return {"error": "initialize failed: %s" % str(init["error"].get("message", ""))[:200]}
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        tools = []
        cursor = None
        for page in range(20):
            params = {"cursor": cursor} if cursor else {}
            send({"jsonrpc": "2.0", "id": 2 + page, "method": "tools/list", "params": params})
            listing = receive(2 + page)
            if listing is None:
                return {"error": "no tools/list response within %.0fs" % timeout}
            if "error" in listing:
                return {"error": "tools/list failed: %s" % str(listing["error"].get("message", ""))[:200]}
            result = listing.get("result") or {}
            tools.extend(str(t.get("name", "")) for t in result.get("tools", []) if isinstance(t, dict))
            cursor = result.get("nextCursor")
            if not cursor:
                break
        server = (init.get("result") or {}).get("serverInfo") or {}
        return {"tools": sorted(t for t in tools if t), "server": {"name": str(server.get("name", ""))[:80],
                                                                    "version": str(server.get("version", ""))[:40]}}
    except (BrokenPipeError, OSError) as exc:
        return {"error": "the server exited during the handshake (%s)" % exc}
    finally:
        _terminate(proc)


def _terminate(proc: subprocess.Popen) -> None:
    try:
        proc.stdin.close()
    except OSError:
        pass
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        try:
            proc.kill()
            proc.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            pass
