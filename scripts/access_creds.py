#!/usr/bin/env python3
"""Find where a credential for a system might live. Report the place, never the value.

A found credential is **evidence that a route could be set up**, never a route
in itself. A stored token carries its account's full permissions; a read-only
MCP server is read-only because of the process that holds the token, not the
token. Using a found token directly would route around the user's own safety
setting, which is what an agent proposed in the incident this exists for.

So this module only answers "is there something at this locator?", and only
in ways that cannot return a secret:

* macOS Keychain: `security find-generic-password -s <name>` and
  `find-internet-password -s <host>` **without** `-w` or `-g`. The exit status
  says whether the item exists; output is discarded unread.
* Linux Secret Service: `secret-tool` has no lookup that proves presence
  without printing the secret, so the answer is `unknown` and the user is asked.
* `pass`: whether `<store>/<path>.gpg` exists. Nothing is decrypted.
* 1Password `op`, Python keyring: `unknown`; asking would read the secret.
* `~/.netrc`: whether a `machine <host>` entry exists. Passwords are skipped
  by the tokenizer, never kept.
* Environment variables: whether the name is set. The value is not looked at.
* CLI logins: whether the CLI's own config names the host. `--probe` upgrades
  this to the CLI's own status command.

Candidate keychain names come from the route (the launcher's own locator), the
system's base-URL host, and the registry's `name_keywords`. The keychain is
never listed or dumped.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional


def _home() -> Path:
    return Path(os.environ.get("HOME") or str(Path.home()))


def _run_presence(argv: List[str], timeout: int = 5) -> Optional[bool]:
    """True/False from an exit status; None when the tool is missing or hangs.

    stdout and stderr go to DEVNULL: they are never read, so nothing a tool
    prints can reach a report even if a tool misbehaves.
    """
    if shutil.which(argv[0]) is None:
        return None
    try:
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.returncode == 0


def keychain_generic(name: str) -> Optional[bool]:
    return _run_presence(["security", "find-generic-password", "-s", name])


def keychain_internet(host: str) -> Optional[bool]:
    return _run_presence(["security", "find-internet-password", "-s", host])


def pass_entry(path: str) -> Optional[bool]:
    store = Path(os.environ.get("PASSWORD_STORE_DIR") or _home() / ".password-store")
    if not store.is_dir():
        return None
    return (store / (path + ".gpg")).is_file()


def netrc_hosts() -> List[str]:
    path = Path(os.environ.get("NETRC") or _home() / ".netrc")
    try:
        tokens = path.read_text(encoding="utf-8", errors="replace").split()
    except OSError:
        return []
    hosts = []
    skip_next = False
    for i, token in enumerate(tokens):
        if skip_next:
            skip_next = False
            continue
        if token in ("password", "account", "login"):
            skip_next = True
            continue
        if token == "machine" and i + 1 < len(tokens):
            hosts.append(tokens[i + 1].lower())
    return hosts


def cli_login_declared(command: str, host: str = "") -> Optional[bool]:
    """Static: does the CLI's own config name a login (for this host)?"""
    home = _home()
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    files = {
        "gh": [Path(os.environ.get("GH_CONFIG_DIR") or config_home / "gh") / "hosts.yml"],
        "glab": [config_home / "glab-cli" / "config.yml"],
        "jira": [config_home / ".jira" / ".config.yml"],
    }.get(command, [])
    if shutil.which(command) is None:
        return None
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        return (host.lower() in text.lower()) if host else bool(text.strip())
    if command == "gh" and (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")):
        return True
    return False


def locate(system: dict, route_refs: List[dict], hosts: List[str],
           host_env_keys: Optional[List[dict]] = None) -> List[dict]:
    """Candidate credentials for one system, as locators with presence.

    `route_refs` are the launcher's own references (from the inspector),
    `host_env_keys` the credential-shaped keys a host config sets for a
    server. Returns [{source, locator, system_guess, present, how, origin}].
    """
    found: List[dict] = []
    seen = set()

    def add(source, locator, present, how, origin):
        key = (source, locator)
        if key in seen:
            return
        seen.add(key)
        found.append({"source": source, "locator": locator, "system_guess": system["id"],
                      "present": present, "how": how, "origin": origin})

    # 1. What the route itself references.
    for ref in route_refs:
        kind, locator = ref["kind"], ref["locator"]
        origin = "launcher line %s" % ref.get("line", "?")
        if kind == "keychain-generic":
            add("keychain-generic", locator, _presence(keychain_generic(locator)), "security find-generic-password -s (no -w)", origin)
        elif kind == "keychain-internet":
            add("keychain-internet", locator, _presence(keychain_internet(locator)), "security find-internet-password -s (no -w)", origin)
        elif kind == "pass":
            add("pass", locator, _presence(pass_entry(locator)), "entry file exists; not decrypted", origin)
        elif kind in ("secret-service", "1password", "keyring"):
            add(kind, locator, "unknown", "cannot check presence without reading the secret", origin)
        elif kind == "netrc":
            add("netrc", "~/.netrc", "unknown", "referenced by the launcher", origin)
        elif kind == "file":
            path = Path(os.path.expanduser(os.path.expandvars(locator)))
            add("file", locator, "present" if path.is_file() else ("unknown" if "$" in locator else "absent"),
                "file exists; not read", origin)
    for entry in host_env_keys or []:
        add("host-config-env", "%s (%s, server %s)" % (entry["key"], entry["file"], entry["server"]),
            "present", "set in the host's MCP env block", "host config")

    # 2. Environment variables the registry names.
    for upstream in system.get("mcp_upstreams", []):
        for name in upstream.get("credential_env", []):
            if os.environ.get(name):
                add("env", name, "present", "set in this process environment (value not read)", "registry")

    # 3. CLI logins (static; `--probe` runs the CLI's status command instead).
    for cli in system.get("cli_routes", []):
        declared = cli_login_declared(cli["command"], hosts[0] if hosts else "")
        if declared is not None:
            add("cli-login", cli["command"], "present" if declared else "absent", "CLI config names a login", "registry")

    # 4. OS secret stores by exact name, never by listing.
    names = []
    for keyword in system.get("credential_hints", {}).get("name_keywords", []):
        names.append(keyword)
    for name in names:
        present = keychain_generic(name)
        if present:
            add("keychain-generic", name, "present", "security find-generic-password -s (no -w)", "registry keyword")
    for host in hosts:
        present = keychain_internet(host)
        if present:
            add("keychain-internet", host, "present", "security find-internet-password -s (no -w)", "base URL host")
    if shutil.which("secret-tool") and not shutil.which("security"):
        add("secret-service", "(ask the user for the item's attributes)", "unknown",
            "secret-tool cannot prove presence without returning the secret", "platform")

    # 5. ~/.netrc
    netrc = netrc_hosts()
    for host in hosts:
        if host.lower() in netrc:
            add("netrc", "machine %s" % host, "present", "~/.netrc has an entry (password not read)", "base URL host")
    return found


def _presence(value: Optional[bool]) -> str:
    if value is None:
        return "unknown"
    return "present" if value else "absent"
