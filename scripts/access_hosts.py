#!/usr/bin/env python3
"""Where each agent host keeps its MCP servers, read into one shape.

Every reader returns entries of the same form:

    {host, scope, file, server_name, transport, command, args, url,
     env_keys, env_values, plaintext_secret_keys, disabled}

`env_values` holds values **only** for keys the caller allows: mode, filter and
base-URL keys from the registry, a wrapper's own mode variable from local route
knowledge, and names that look like a mode switch and not like a secret. Every
other key is kept as a name. A secret value is never returned; the one thing a
reader learns about a secret-shaped key is whether its value is a literal
(which doctor warns about) or a reference such as `${env:VAR}`.

A file that exists but cannot be parsed is returned as an `error` for that
host, never as "no servers": a parse gap must not read as the absence of a
read-only flag.

Host ids follow `lib/hosts.registry` wherever the host is also a skills host.
`claude-desktop` is not a skills host but does launch MCP servers, so it is
read here too.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import access_toml

HOSTS = ("claude-code", "claude-desktop", "codex", "cursor", "copilot", "kiro")

HOST_LABELS = {
    "claude-code": "Claude Code",
    "claude-desktop": "Claude Desktop",
    "codex": "Codex",
    "cursor": "Cursor",
    "copilot": "VS Code / GitHub Copilot",
    "kiro": "Kiro",
}

RELOAD_HINTS = {
    "claude-code": "Restart the Claude Code session (or run /mcp to reconnect the server).",
    "claude-desktop": "Quit and reopen Claude Desktop.",
    "codex": "Start a new Codex session; Codex reads config.toml at startup.",
    "cursor": "Open Cursor Settings > MCP and toggle the server off and on, or reload the window.",
    "copilot": "Run 'MCP: List Servers' in VS Code and restart the server.",
    "kiro": "Reconnect the server from the Kiro MCP panel, or restart Kiro.",
}

_SECRET_NAME = re.compile(r"(?i)(TOKEN|SECRET|PASSWORD|PASSWD|API_?KEY|PRIVATE|CREDENTIAL|\bPAT\b|_PAT$|AUTH|COOKIE|SESSION)")
_MODE_NAME = re.compile(r"(?i)(READ_?ONLY|READ_?WRITE|(^|_)RW($|_)|WRITE|ENABLED_TOOLS|TOOLSETS|_FILTER$|PERMISSION_MODE|_MODE$|_TOOLS$)")
_REFERENCE = re.compile(r"^\s*(\$\{[^}]*\}|\$[A-Za-z_][A-Za-z0-9_]*|<[^>]*>|op://\S+)\s*$")


class HostReadError(Exception):
    pass


def looks_secret(key: str) -> bool:
    return bool(_SECRET_NAME.search(key))


def looks_mode_like(key: str) -> bool:
    return bool(_MODE_NAME.search(key)) and not looks_secret(key)


def default_value_policy(allowed: set) -> Callable[[str], bool]:
    def allowed_key(key: str) -> bool:
        if looks_secret(key):
            return False
        return key in allowed or looks_mode_like(key)
    return allowed_key


# ---------------------------------------------------------------------------
# Files per host
# ---------------------------------------------------------------------------
def _home() -> Path:
    return Path(os.environ.get("HOME") or str(Path.home()))


def _codex_home() -> Path:
    override = os.environ.get("CODEX_HOME")
    return Path(override) if override else _home() / ".codex"


def _vscode_user_dir() -> Path:
    if sys.platform == "darwin":
        return _home() / "Library" / "Application Support" / "Code" / "User"
    return Path(os.environ.get("XDG_CONFIG_HOME") or _home() / ".config") / "Code" / "User"


def _claude_desktop_file() -> Path:
    if sys.platform == "darwin":
        return _home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    return Path(os.environ.get("XDG_CONFIG_HOME") or _home() / ".config") / "Claude" / "claude_desktop_config.json"


def config_files(host: str, repo_root: Optional[Path]) -> List[Tuple[str, Path, str]]:
    """(scope, path, format) candidates for one host, most general first."""
    home = _home()
    out: List[Tuple[str, Path, str]] = []
    if host == "claude-code":
        out.append(("user", home / ".claude.json", "claude-json"))
        if repo_root:
            out.append(("project", repo_root / ".mcp.json", "mcpServers"))
    elif host == "claude-desktop":
        out.append(("user", _claude_desktop_file(), "mcpServers"))
    elif host == "codex":
        out.append(("user", _codex_home() / "config.toml", "codex-toml"))
        if repo_root:
            out.append(("project", repo_root / ".codex" / "config.toml", "codex-toml"))
    elif host == "cursor":
        out.append(("user", home / ".cursor" / "mcp.json", "mcpServers"))
        if repo_root:
            out.append(("project", repo_root / ".cursor" / "mcp.json", "mcpServers"))
    elif host == "copilot":
        out.append(("user", _vscode_user_dir() / "mcp.json", "vscode-servers"))
        out.append(("user", _vscode_user_dir() / "settings.json", "vscode-settings"))
        if repo_root:
            out.append(("project", repo_root / ".vscode" / "mcp.json", "vscode-servers"))
    elif host == "kiro":
        kiro_home = Path(os.environ.get("KIRO_HOME") or home / ".kiro")
        out.append(("user", kiro_home / "settings" / "mcp.json", "mcpServers"))
        if repo_root:
            out.append(("project", repo_root / ".kiro" / "settings" / "mcp.json", "mcpServers"))
    return out


def host_detected(host: str, repo_root: Optional[Path]) -> bool:
    home = _home()
    marker = {
        "claude-code": [home / ".claude.json", home / ".claude"],
        "claude-desktop": [_claude_desktop_file().parent],
        "codex": [_codex_home()],
        "cursor": [home / ".cursor"],
        "copilot": [_vscode_user_dir()],
        "kiro": [Path(os.environ.get("KIRO_HOME") or home / ".kiro")],
    }.get(host, [])
    if any(p.exists() for p in marker):
        return True
    return any(p.is_file() for _s, p, _f in config_files(host, repo_root))


# ---------------------------------------------------------------------------
# Current host
# ---------------------------------------------------------------------------
def resolve_current_host(explicit: str = "") -> Tuple[Optional[str], str]:
    """(host id, how it was established). None means "evaluate every host".

    Only signals that were verified to be set by the host itself are used.
    Anything else is not guessed: a wrong host answer would report another
    host's mode as this one's.
    """
    if explicit:
        if explicit not in HOSTS:
            raise HostReadError("unknown host %r; expected one of %s" % (explicit, ", ".join(HOSTS)))
        return explicit, "--host"
    env_host = os.environ.get("AGENT_SKILLS_HOST", "").strip()
    if env_host in HOSTS:
        return env_host, "AGENT_SKILLS_HOST"
    if os.environ.get("CLAUDECODE") == "1":
        return "claude-code", "CLAUDECODE=1 (set by Claude Code, including inside the desktop app)"
    return None, "no reliable host signal; every detected host is evaluated and labelled"


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def _strip_jsonc(text: str) -> str:
    """Remove // and /* */ comments and trailing commas outside strings."""
    out = []
    i = 0
    in_string = False
    while i < len(text):
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < len(text):
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
        elif text.startswith("//", i):
            while i < len(text) and text[i] != "\n":
                i += 1
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = len(text) if end < 0 else end + 2
        else:
            out.append(ch)
            i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def _load(path: Path, fmt: str):
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HostReadError("cannot read %s: %s" % (path, exc.strerror or exc))
    try:
        if fmt == "codex-toml":
            return access_toml.loads(text)
        if fmt.startswith("vscode"):
            return json.loads(_strip_jsonc(text))
        return json.loads(text)
    except (ValueError, access_toml.TomlSubsetError) as exc:
        raise HostReadError("cannot parse %s: %s" % (path, exc))


def _servers(data, fmt: str, repo_root: Optional[Path]) -> List[Tuple[str, str, dict]]:
    """(scope-suffix, name, raw entry) from one parsed file."""
    if not isinstance(data, dict):
        raise HostReadError("top level is not an object")
    found: List[Tuple[str, str, dict]] = []

    def take(block, scope=""):
        if block is None:
            return
        if not isinstance(block, dict):
            raise HostReadError("server table is not an object")
        for name, entry in block.items():
            if isinstance(entry, dict):
                found.append((scope, str(name), entry))

    if fmt == "claude-json":
        take(data.get("mcpServers"))
        projects = data.get("projects")
        if repo_root and isinstance(projects, dict):
            for key in (str(repo_root), str(repo_root.resolve())):
                project = projects.get(key)
                if isinstance(project, dict):
                    take(project.get("mcpServers"), "local")
                    break
    elif fmt == "codex-toml":
        take(data.get("mcp_servers"))
    elif fmt == "vscode-servers":
        take(data.get("servers"))
    elif fmt == "vscode-settings":
        mcp = data.get("mcp")
        if isinstance(mcp, dict):
            take(mcp.get("servers"))
    else:
        take(data.get("mcpServers"))
    return found


def _normalise(host: str, scope: str, path: Path, name: str, entry: dict,
               value_allowed: Callable[[str], bool]) -> dict:
    env = entry.get("env")
    env = env if isinstance(env, dict) else {}
    args = entry.get("args")
    args = [str(a) for a in args] if isinstance(args, list) else []
    url = str(entry.get("url") or entry.get("serverUrl") or "")
    command = str(entry.get("command") or "")
    headers = entry.get("headers") if isinstance(entry.get("headers"), dict) else {}
    env_values = {}
    plaintext = []
    for key, value in env.items():
        key = str(key)
        if looks_secret(key):
            if isinstance(value, str) and value.strip() and not _REFERENCE.match(value):
                plaintext.append(key)
            continue
        if value_allowed(key):
            env_values[key] = "" if value is None else str(value)
    for key, value in headers.items():
        if str(key).lower() != "authorization" or not isinstance(value, str) or not value.split():
            continue
        if not _REFERENCE.search(value.split()[-1]):
            plaintext.append("headers.Authorization")
    disabled = bool(entry.get("disabled")) or entry.get("enabled") is False
    return {
        "host": host,
        "scope": scope,
        "file": str(path),
        "server_name": name,
        "transport": "http" if url and not command else "stdio",
        "command": command,
        "args": args,
        "url": url,
        "env_keys": sorted(str(k) for k in env.keys()),
        "env_values": env_values,
        "plaintext_secret_keys": sorted(plaintext),
        "disabled": disabled,
    }


def read_host(host: str, repo_root: Optional[Path], value_allowed: Callable[[str], bool]) -> dict:
    """{host, detected, files: [{path, scope, status, error}], servers: [...]}"""
    report = {"host": host, "label": HOST_LABELS[host], "detected": host_detected(host, repo_root),
              "files": [], "servers": []}
    for scope, path, fmt in config_files(host, repo_root):
        if not path.is_file():
            report["files"].append({"path": str(path), "scope": scope, "status": "absent"})
            continue
        try:
            data = _load(path, fmt)
            entries = _servers(data, fmt, repo_root)
        except HostReadError as exc:
            report["files"].append({"path": str(path), "scope": scope, "status": "error", "error": str(exc)})
            continue
        try:
            mode = "%o" % (path.stat().st_mode & 0o777)
        except OSError:
            mode = ""
        report["files"].append({"path": str(path), "scope": scope, "status": "read", "mode": mode,
                                "group_or_world_readable": bool(mode) and (int(mode, 8) & 0o044) != 0})
        for suffix, name, entry in entries:
            report["servers"].append(_normalise(host, suffix or scope, path, name, entry, value_allowed))
    return report


def read_hosts(hosts: List[str], repo_root: Optional[Path], value_allowed: Callable[[str], bool]) -> List[dict]:
    return [read_host(h, repo_root, value_allowed) for h in hosts]


def load_raw(path: Path, fmt_hint: str = ""):
    """Parsed file content, for `access setup` only (never printed)."""
    fmt = fmt_hint or ("codex-toml" if path.suffix == ".toml" else "mcpServers")
    return _load(path, fmt)


def format_of(host: str, path: Path) -> str:
    for _scope, candidate, fmt in config_files(host, None) + config_files(host, path.parent.parent):
        if candidate == path:
            return fmt
    if path.suffix == ".toml":
        return "codex-toml"
    if path.name == ".claude.json":
        return "claude-json"
    return "mcpServers"
