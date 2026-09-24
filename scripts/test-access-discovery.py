#!/usr/bin/env python3
"""Offline acceptance suite for Access Discovery (`agent-skills access scan|check|...`).

    python3 scripts/test-access-discovery.py            run everything
    python3 scripts/test-access-discovery.py -k incident only checks whose name contains "incident"
    python3 scripts/test-access-discovery.py --hash NAME print the digest to add to the no-coupling denylist

Every check runs in its own sandbox: a fake HOME with host configs, fake
`security` / `secret-tool` / `gh` / `uvx` / `docker` on PATH, and a canary that
the fake credential tools print only when asked for a secret. Nothing here
touches the network, the real keychain, or a real host configuration.

The incident regression (A1-A3) uses invented names on purpose - acme, globex,
initech, hooli, soylent, umbrella, vandelay - so that passing it proves the
design is not keyed to any one organisation.
"""
from __future__ import annotations

import hashlib
import json
import os
import pty
import re
import select
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FIX = HERE / "fixtures" / "access"
ACCESS = HERE / "access.py"
# Canaries stand in for secret values. The fake credential tools print one only
# when asked for a secret; finding one anywhere in output or on disk is a leak.
PLAINTEXT_CANARY = "-".join(["CANARY", "PLAINTEXT", "VALUE", "77aa"])
CANARIES = ("CANARY-SECRET-KEYCHAIN-4f1e", "CANARY-SECRET-SECRETTOOL-9c2d", PLAINTEXT_CANARY)
PAGE = "https://acme.atlassian.net/wiki/spaces/~jdoe/pages/123456789/Notes"
sys.path[:0] = [str(HERE), str(ROOT / "lib")]

CHECKS = []


def check(name):
    def wrap(fn):
        CHECKS.append((name, fn))
        return fn
    return wrap


class Box:
    """One sandbox: fake home, fake tools, a git work tree."""

    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="as-access-"))
        self.home = self.dir / "home"
        self.bin = self.dir / "bin"
        self.work = self.dir / "work"
        for d in (self.home / ".local" / "bin", self.bin, self.work):
            d.mkdir(parents=True)
        for tool in (FIX / "bin").iterdir():
            shutil.copy2(str(tool), str(self.bin / tool.name))
        self.marker = self.dir / "launcher-ran"
        self.seclog = self.dir / "security.log"
        subprocess.run(["git", "init", "-q", str(self.work)], check=True)
        self.env = {
            "HOME": str(self.home), "PATH": "%s:/usr/bin:/bin" % self.bin, "PYTHONIOENCODING": "utf-8",
            "AGENT_SKILLS_HOME": str(self.home / ".agent-skills"), "FAKE_SECURITY_LOG": str(self.seclog),
            "ACME_FIXTURE_RAN_MARKER": str(self.marker), "FAKE_KEYCHAIN_ITEMS": "",
        }
        py = shutil.which("python3")
        if py and os.path.dirname(py) not in ("/usr/bin", "/bin"):
            os.symlink(py, str(self.bin / "python3"))

    def launcher(self, name, as_name=None) -> Path:
        dest = self.home / ".local" / "bin" / (as_name or name)
        shutil.copy2(str(FIX / "launchers" / name), str(dest))
        return dest

    def codex(self, servers: str) -> Path:
        path = self.home / ".codex" / "config.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('model = "x"\n' + servers, encoding="utf-8")
        return path

    def json_host(self, rel: str, key: str, servers: dict) -> Path:
        path = self.home / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({key: servers}, indent=2), encoding="utf-8")
        return path

    def run(self, *args, env=None, cwd=None):
        full = dict(self.env)
        full.update(env or {})
        out = subprocess.run([sys.executable, str(ACCESS)] + list(args), cwd=str(cwd or self.work), env=full,
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             universal_newlines=True, timeout=90)
        return out.returncode, out.stdout, out.stderr

    def run_json(self, *args, env=None):
        rc, out, err = self.run(*(list(args) + ["--json"]), env=env)
        try:
            return rc, json.loads(out), err
        except ValueError:
            raise AssertionError("not JSON (rc %s): %s %s" % (rc, out[:400], err[:400]))

    def run_tty(self, answers, *args):
        """Run under a pseudo-terminal, typing `answers` at each "Type 'yes'" prompt."""
        pid, fd = pty.fork()
        if pid == 0:
            os.chdir(str(self.work))
            os.execve(sys.executable, [sys.executable, str(ACCESS)] + list(args), self.env)
        out = b""
        answers = list(answers)
        while True:
            ready, _w, _x = select.select([fd], [], [], 60)
            if not ready:
                break
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
            if answers and b"Type 'yes'" in out.rsplit(b"\n", 1)[-1]:
                os.write(fd, (answers.pop(0) + "\n").encode())
        _pid, status = os.waitpid(pid, 0)
        return os.WEXITSTATUS(status), out.decode("utf-8", "replace")

    def state_written(self) -> str:
        """Everything Agent Skills wrote: config, state, cache."""
        chunks = []
        for base in (self.home / ".agent-skills", self.home / ".config" / "agent-skills"):
            for path in base.rglob("*") if base.exists() else []:
                if path.is_file():
                    chunks.append(path.read_text(encoding="utf-8", errors="replace"))
        return "\n".join(chunks)

    def assert_never_ran(self):
        assert not self.marker.exists(), "a launcher script was executed during discovery"

    def assert_no_secret_requested(self):
        log = self.seclog.read_text() if self.seclog.exists() else ""
        for line in log.splitlines():
            assert " -w" not in " " + line and " -g" not in " " + line, "secret requested: %s" % line
            assert not line.startswith("secret-tool"), "secret-tool was called: %s" % line

    def close(self):
        shutil.rmtree(str(self.dir), ignore_errors=True)


def incident_box(launcher="acme-mcp-atlassian", keychain="acme-atlassian"):
    box = Box()
    path = box.launcher(launcher)
    box.env["FAKE_KEYCHAIN_ITEMS"] = keychain
    box.codex('[mcp_servers.atlassian]\ncommand = "%s"\nargs = []\nstartup_timeout_sec = 60\n' % path)
    return box


def no_canary(*texts):
    for text in texts:
        for canary in CANARIES:
            assert canary not in text, "secret canary leaked: %s" % canary


def rung(rep, rid):
    return next(r for r in rep["rungs"] if r["id"] == rid)


# ---------------------------------------------------------------------------
# A. The incident, and the same shape with other invented names
# ---------------------------------------------------------------------------
@check("A1 incident: blocked at mode, inferred, cites wrapper line, exit 11, locator only, browser never used")
def _():
    box = incident_box()
    try:
        rc, rep, err = box.run_json("check", "--system", "confluence", "--op", "update", "--target", PAGE,
                                    "--host", "codex", "--user-authorised", "--own-target")
        assert rc == 11, (rc, err)
        assert rep["result"] == "blocked" and rep["blocked_at"] == "mode", rep["result"]
        mode = rung(rep, "mode")
        assert mode["status"] == "fail" and mode["strength"] == "inferred", mode
        assert "acme-mcp-atlassian" in mode["evidence"] and "ACME_ATL_RW=1" in mode["evidence"], mode
        fixes = {f["id"]: f for f in mode["fix_options"]}
        assert {"write-profile", "manual-handoff", "confirm-inferred"} <= set(fixes), fixes
        assert "ACME_ATL_RW=1" in fixes["write-profile"]["label"], fixes["write-profile"]
        assert "line 14, 15" in fixes["confirm-inferred"]["label"], fixes["confirm-inferred"]
        creds = rep["found_credentials"]
        assert any(c["source"] == "keychain-generic" and c["locator"] == "acme-atlassian" and c["present"] == "present"
                   for c in creds), creds
        browser = [r for r in rep["routes"] if r["kind"] == "browser"]
        assert browser and browser[0]["usable"] is False, browser
        assert rep["route"]["name"] == "atlassian" and "grant" not in rep
        text_rc, text, _ = box.run("check", "--system", "confluence", "--op", "update", "--target", PAGE, "--host",
                                   "codex", "--user-authorised")
        assert text_rc == 11 and "Result: BLOCKED at mode." in text, text
        assert "(user-local launcher)" in text, text
        no_canary(json.dumps(rep), text, err, box.state_written())
        box.assert_no_secret_requested()
        box.assert_never_ran()
    finally:
        box.close()


@check("A2 incident: write profile via setup, confirmation, then the check passes and policy wants a preview")
def _():
    box = incident_box()
    try:
        config = box.home / ".codex" / "config.toml"
        before = config.read_bytes()
        rc, out, err = box.run("setup", "confluence", "--write-profile", "--host", "codex")
        assert rc == 1 and "limited to one space by default" in err, (out, err)
        rc, out, _ = box.run("setup", "confluence", "--write-profile", "--host", "codex", "--target", PAGE)
        assert rc == 0 and "Not a terminal, so nothing was written" in out, out
        assert 'ACME_ATL_RW = "1"' in out and 'CONFLUENCE_SPACES_FILTER = "~jdoe"' in out, out
        assert 'TOOLSETS = "confluence_pages,' in out and "Limited to: space ~jdoe only" in out, out
        assert config.read_bytes() == before, "non-interactive setup wrote the file"
        rc, out = box.run_tty(["yes"], "setup", "confluence", "--write-profile", "--host", "codex", "--target", PAGE)
        assert rc == 0 and "Written. Backup:" in out, out
        after = config.read_text()
        assert after.startswith(before.decode()), "the read-only entry was changed"
        assert "[mcp_servers.atlassian-write]" in after and 'ACME_ATL_RW = "1"' in after, after
        assert 'CONFLUENCE_SPACES_FILTER = "~jdoe"' in after and "jira_issues" not in after, after
        backups = list((box.home / ".codex").glob("config.toml.agent-skills-backup-*"))
        assert len(backups) == 1 and backups[0].read_bytes() == before
        rc, rep, _ = box.run_json("check", "--system", "confluence", "--op", "update", "--target", PAGE, "--host",
                                  "codex", "--user-authorised", "--own-target")
        assert rc == 1 and rep["result"] == "needs-confirmation" and rep["blocked_at"] == "mode", rep["result"]
        routes = box.home / ".config" / "agent-skills" / "access" / "routes.json"
        rc, out, err = box.run("remember", "--system", "confluence", "--server", "atlassian", "--host", "codex")
        assert rc == 1 and not routes.exists(), (out, err)
        rc, out, _ = box.run("remember", "--system", "confluence", "--server", "atlassian", "--host", "codex", "--yes")
        assert rc == 0, out
        assert stat.S_IMODE(routes.stat().st_mode) == 0o600
        saved = json.loads(routes.read_text())
        assert saved["routes"][0]["mode"] == {"env": "ACME_ATL_RW", "write_when": "1", "default": "read-only"}
        assert sorted(saved["routes"][0]["systems"]) == ["confluence", "jira"], saved
        rc, rep, _ = box.run_json("check", "--system", "confluence", "--op", "update", "--target", PAGE, "--host",
                                  "codex", "--user-authorised", "--own-target")
        assert rc == 0 and rep["result"] == "available", (rc, rep["result"], rep["blocked_at"])
        assert rep["route"]["name"] == "atlassian-write"
        statuses = {r["id"]: r["status"] for r in rep["rungs"]}
        assert statuses["intent"] == "pass" and statuses["policy"] == "pass", statuses
        assert "preview" in rep["confirmation"], rep["confirmation"]
        assert rep.get("grant"), "a passing write check leaves a short-lived grant"
        rc, out = box.run_tty(["yes"], "setup", "--undo", "--host", "codex")
        assert rc == 0 and "Restored" in out, out
        assert config.read_bytes() == before, "undo did not restore the original"
        no_canary(box.state_written())
        box.assert_no_secret_requested()
        box.assert_never_ran()
    finally:
        box.close()


@check("A3 incident with other invented names: docker upstream, pass credential, different switch")
def _():
    box = Box()
    try:
        path = box.launcher("globex-atlassian-mcp")
        store = box.home / ".password-store" / "work" / "globex"
        store.mkdir(parents=True)
        (store / "atlassian.gpg").write_bytes(b"\x85\x01binary")
        box.json_host(".cursor/mcp.json", "mcpServers", {"confluence": {"command": str(path)}})
        page = "https://globex.example.net/wiki/spaces/ENG/pages/42/Runbook"
        rc, rep, _ = box.run_json("check", "--system", "confluence", "--op", "edit", "--target", page, "--host", "cursor",
                                  "--user-authorised")
        assert rc == 11 and rep["blocked_at"] == "mode", (rc, rep["blocked_at"])
        mode = rung(rep, "mode")
        assert "GLOBEX_WRITE_ENABLED" in mode["evidence"] and mode["strength"] == "inferred", mode
        assert any(c["source"] == "pass" and c["locator"] == "work/globex/atlassian" and c["present"] == "present"
                   for c in rep["found_credentials"]), rep["found_credentials"]
        write = next(f for f in mode["fix_options"] if f["id"] == "write-profile")
        assert "--server confluence" in write["command"] and '--target "%s"' % page in write["command"], write
        assert "acme" not in json.dumps(rep).lower(), "an earlier fixture's name leaked into another check"
        box.json_host(".cursor/mcp.json", "mcpServers", {
            "confluence": {"command": str(path)},
            "confluence-write": {"command": str(path), "env": {"GLOBEX_WRITE_ENABLED": "1"}}})
        rc, rep, _ = box.run_json("check", "--system", "confluence", "--op", "edit", "--target", page, "--host",
                                  "cursor", "--user-authorised")
        assert rc == 1 and rep["result"] == "needs-confirmation", (rc, rep["result"])
        assert rep["route"]["name"] == "confluence-write"
        box.assert_never_ran()
    finally:
        box.close()


# ---------------------------------------------------------------------------
# H. Host readers and the TOML subset
# ---------------------------------------------------------------------------
@check("H1 host readers: every host, user and project scope, JSONC, malformed files are unknown not absent")
def _():
    import access_hosts as H
    box = Box()
    old = dict(os.environ)
    try:
        os.environ["HOME"] = str(box.home)
        for name in ("CODEX_HOME", "XDG_CONFIG_HOME", "KIRO_HOME"):
            os.environ.pop(name, None)
        up = {"command": "uvx", "args": ["mcp-atlassian"], "env": {"READ_ONLY_MODE": "true",
              "CONFLUENCE_API_TOKEN": PLAINTEXT_CANARY, "CONFLUENCE_URL": "https://x.example.com/wiki"}}
        data = {"mcpServers": {"u": up}, "projects": {str(box.work): {"mcpServers": {"l": up}}}}
        (box.home / ".claude.json").write_text(json.dumps(data))
        (box.work / ".mcp.json").write_text(json.dumps({"mcpServers": {"p": up}}))
        box.json_host(".cursor/mcp.json", "mcpServers", {"c": up})
        box.json_host(".kiro/settings/mcp.json", "mcpServers", {"k": up})
        desktop = H._claude_desktop_file()
        desktop.parent.mkdir(parents=True, exist_ok=True)
        desktop.write_text(json.dumps({"mcpServers": {"d": up}}))
        vs = box.work / ".vscode" / "mcp.json"
        vs.parent.mkdir()
        vs.write_text('{\n  // comment\n  "servers": {"v": %s,},\n}\n' % json.dumps(up))
        box.codex('[mcp_servers.x]\ncommand = "uvx"\nargs = ["mcp-atlassian"]\nenv = { READ_ONLY_MODE = "true" }\n')
        allowed = H.default_value_policy({"READ_ONLY_MODE", "CONFLUENCE_URL"})
        names = {}
        for host in H.HOSTS:
            rep = H.read_host(host, box.work, allowed)
            names[host] = sorted((s["scope"], s["server_name"]) for s in rep["servers"])
            for server in rep["servers"]:
                assert "CONFLUENCE_API_TOKEN" not in server["env_values"], server
                if server["server_name"] != "x":
                    assert server["plaintext_secret_keys"] == ["CONFLUENCE_API_TOKEN"], server
                assert server["env_values"].get("READ_ONLY_MODE") == "true", server
            no_canary(json.dumps(rep))
        assert names["claude-code"] == [("local", "l"), ("project", "p"), ("user", "u")], names
        assert names["cursor"] == [("user", "c")] and names["kiro"] == [("user", "k")], names
        assert names["claude-desktop"] == [("user", "d")] and names["copilot"] == [("project", "v")], names
        assert names["codex"] == [("user", "x")], names
        (box.home / ".cursor" / "mcp.json").write_text("{ not json")
        rep = H.read_host("cursor", box.work, allowed)
        assert rep["servers"] == [] and rep["files"][0]["status"] == "error", rep
        # Invalid for both parsers (a multi-line string is valid TOML to tomllib
        # on 3.11+, and only outside the 3.8 subset).
        box.codex('[mcp_servers.x]\ncommand = \n')
        rc, scan, _ = box.run_json("scan", "--host", "codex")
        assert rc == 0 and any("unknown, not absent" in w for w in scan["warnings"]), scan["warnings"]
    finally:
        os.environ.clear()
        os.environ.update(old)
        box.close()


@check("H2 TOML subset parser: supported shapes, and anything else fails instead of guessing")
def _():
    import access_toml as T
    text = ('top = 1\n[mcp_servers.a]\ncommand = "uvx" # c\nargs = [\n  "mcp-atlassian",\n  \'--x\',\n]\n'
            'env = { READ_ONLY_MODE = "true", "Q.K" = "v" }\n[mcp_servers."b.c"]\nurl = "https://e.example.com/x"\n'
            'enabled = false\nstartup_timeout_sec = 60\n[mcp_servers.a2.env]\nX = "\\u00e9\\n"\n')
    got = T.loads(text, force_subset=True)
    assert got["mcp_servers"]["a"]["args"] == ["mcp-atlassian", "--x"], got
    assert got["mcp_servers"]["a"]["env"] == {"READ_ONLY_MODE": "true", "Q.K": "v"}, got
    assert got["mcp_servers"]["b.c"]["enabled"] is False and got["mcp_servers"]["b.c"]["startup_timeout_sec"] == 60
    assert got["mcp_servers"]["a2"]["env"]["X"] == "\u00e9\n"
    if T._tomllib is not None:
        assert T.loads(text) == got, "subset parser disagrees with tomllib"
    for bad in ('a = """x"""', "[[t]]\na=1", "a = 1979-05-27", "a = 1\na = 2", 'a = "unterminated'):
        try:
            T.loads(bad, force_subset=True)
        except T.TomlSubsetError:
            continue
        raise AssertionError("accepted unsupported TOML: %r" % bad)
    block = __import__("access_setup")._toml_block("n-write", {"command": "c", "args": ["a"], "env": {"K": 'v"\\'}})
    assert T.loads(block, force_subset=True)["mcp_servers"]["n-write"]["env"]["K"] == 'v"\\', block


# ---------------------------------------------------------------------------
# R. Registry mode rules, filters, and scope
# ---------------------------------------------------------------------------
def _direct(box, env=None, args=None, host=".cursor/mcp.json", name="atlassian"):
    env = dict(env or {})
    env.setdefault("CONFLUENCE_API_TOKEN", "${env:CONFLUENCE_API_TOKEN}")
    entry = {"command": "uvx", "args": ["mcp-atlassian"] + (args or []), "env": env}
    box.json_host(host, "mcpServers", {name: entry})


@check("R1 registry: every system file validates, records its sources, and matches upstreams exactly")
def _():
    import access_registry as reg
    systems = reg.load_systems()
    assert {"confluence", "jira", "github", "gitlab"} <= set(systems), systems.keys()
    for sid, system in systems.items():
        for up in system["mcp_upstreams"]:
            assert up["verified_against"] and all(v.get("date") for v in up["verified_against"]), sid
    assert reg.tool_class(systems["confluence"], "confluence_update_page") == "write"
    assert reg.tool_class(systems["confluence"], "confluence_delete_page") == "destructive"
    assert reg.tool_class(systems["jira"], "jira_get_issue") == "read"
    assert reg.tool_class(systems["github"], "merge_pull_request") == "destructive"
    assert reg.operation_class("aktualisieren") == "write" and reg.operation_class("löschen") == "destructive"
    t = reg.parse_target(systems["confluence"], PAGE)
    assert (t["kind"], t["id"], t["space"]) == ("page", "123456789", "~jdoe"), t
    assert reg.parse_target(systems["jira"], "https://x.atlassian.net/browse/ABC-12")["project"] == "ABC"
    assert reg.parse_target(systems["github"], "https://github.com/o/r/pull/7")["kind"] == "pull-request"
    assert reg.match_upstream(systems["confluence"], "/opt/tools/bin/acme-mcp-atlassian", []) is None, \
        "a wrapper named after its upstream must not be mistaken for it"
    assert reg.match_upstream(systems["confluence"], "/usr/local/bin/mcp-atlassian", []) is not None


@check("R2 direct upstream: READ_ONLY_MODE, --read-only, ENABLED_TOOLS, TOOLSETS, and the upstream default")
def _():
    box = Box()
    try:
        cases = [
            ({"READ_ONLY_MODE": "true"}, [], 11, "mode"),
            ({}, ["--read-only"], 11, "mode"),
            ({"ENABLED_TOOLS": "confluence_search,confluence_get_page"}, [], 11, "mode"),
            ({"TOOLSETS": "jira_issues"}, [], 11, "mode"),
            ({"TOOLSETS": "default"}, [], 0, None),
            ({"READ_ONLY_MODE": "false"}, [], 0, None),
            ({}, [], 0, None),
        ]
        for env, args, want_rc, blocked in cases:
            _direct(box, env, args)
            rc, rep, _ = box.run_json("check", "--system", "confluence", "--op", "write", "--target",
                                      "https://x.atlassian.net/wiki/spaces/DEV/pages/1/P", "--host", "cursor",
                                      "--user-authorised")
            assert rc == want_rc and rep["blocked_at"] == blocked, (env, args, rc, rep["blocked_at"])
            if blocked:
                assert rung(rep, "mode")["strength"] == "declared", rung(rep, "mode")
        _direct(box, {"READ_ONLY_MODE": "true"})
        rc, rep, _ = box.run_json("check", "--system", "confluence", "--op", "read", "--host", "cursor")
        assert rc == 0 and rep["result"] == "available", "a read-only route must still serve reads"
    finally:
        box.close()


@check("R3 scope filter: a personal space outside CONFLUENCE_SPACES_FILTER is 'missing, not forbidden'")
def _():
    box = Box()
    try:
        _direct(box, {"CONFLUENCE_SPACES_FILTER": "DEV,OPS", "CONFLUENCE_URL": "https://acme.atlassian.net/wiki"})
        rc, rep, _ = box.run_json("check", "--system", "confluence", "--op", "update", "--target", PAGE, "--host",
                                  "cursor", "--user-authorised")
        assert rc == 11 and rep["blocked_at"] == "target", (rc, rep["blocked_at"])
        target = rung(rep, "target")
        assert "~jdoe" in target["evidence"] and "personal space" in target["evidence"], target
        assert "missing, not forbidden" in target["evidence"], target
        assert any(f["id"] == "write-profile-scoped" for f in target["fix_options"]), target["fix_options"]
        rc, rep, _ = box.run_json("check", "--system", "confluence", "--op", "update", "--target",
                                  "https://other.atlassian.net/wiki/spaces/DEV/pages/5/X", "--host", "cursor",
                                  "--user-authorised")
        assert rc == 11 and "the route serves acme.atlassian.net" in json.dumps(rep["rungs"]), rep["rungs"]
    finally:
        box.close()


@check("R4 github and gitlab: GITHUB_READ_ONLY, GITLAB_PERMISSION_MODE=modify allows writes, not destructive")
def _():
    box = Box()
    try:
        box.json_host(".cursor/mcp.json", "mcpServers", {"github": {"command": "docker", "args": [
            "run", "-i", "--rm", "-e", "GITHUB_PERSONAL_ACCESS_TOKEN", "ghcr.io/github/github-mcp-server"],
            "env": {"GITHUB_READ_ONLY": "1", "GITHUB_PERSONAL_ACCESS_TOKEN": "${env:GH}"}}})
        rc, rep, _ = box.run_json("check", "--system", "github", "--op", "write", "--target", "o/r", "--host", "cursor",
                                  "--user-authorised")
        assert rc == 11 and rep["blocked_at"] == "mode", (rc, rep["blocked_at"])
        box.json_host(".cursor/mcp.json", "mcpServers", {"gitlab": {"command": "npx", "args": ["-y",
            "@zereight/mcp-gitlab"], "env": {"GITLAB_PERMISSION_MODE": "modify", "GITLAB_PERSONAL_ACCESS_TOKEN": "${X}"}}})
        rc, rep, _ = box.run_json("check", "--system", "gitlab", "--op", "comment", "--target", "g/p", "--host",
                                  "cursor", "--user-authorised")
        assert rc == 0, (rc, rep["blocked_at"], rep["rungs"])
        rc, rep, _ = box.run_json("check", "--system", "gitlab", "--op", "delete", "--target", "g/p", "--host",
                                  "cursor", "--user-authorised")
        assert rc == 11 and rep["blocked_at"] == "mode", (rc, rep["blocked_at"])
    finally:
        box.close()


@check("R5 host divergence: the same server read-only in one host and read-write in another is a warning")
def _():
    box = Box()
    try:
        _direct(box, {"READ_ONLY_MODE": "true"}, host=".cursor/mcp.json")
        _direct(box, {}, host=".kiro/settings/mcp.json")
        rc, scan, _ = box.run_json("scan", "--all-hosts")
        assert rc == 0 and any("differs across hosts" in w and "cursor read-only" in w and "kiro read-write" in w
                               for w in scan["warnings"]), scan["warnings"]
        rc, rep, _ = box.run_json("check", "--system", "confluence", "--op", "write", "--target", PAGE,
                                  "--user-authorised")
        assert rc == 1 and rep["result"] == "unknown" and rep["blocked_at"] == "route", (rc, rep["result"])
        assert rep["rungs"][0]["fix_options"][0]["id"] == "ask-host", rep["rungs"][0]
    finally:
        box.close()


@check("R6 no route and no credential: setup and hand-off are offered; a found credential only feeds setup")
def _():
    box = Box()
    try:
        box.env["FAKE_KEYCHAIN_ITEMS"] = "confluence"
        (box.home / ".cursor").mkdir()
        rc, rep, _ = box.run_json("check", "--system", "confluence", "--op", "update", "--target", PAGE, "--host",
                                  "cursor", "--user-authorised")
        assert rc == 1 and rep["blocked_at"] == "route", (rc, rep["blocked_at"])
        ids = [f["id"] for f in rung(rep, "route")["fix_options"]]
        assert ids[0] == "setup-route" and "use-found-credential-for-setup" in ids and ids[-1] == "manual-handoff", ids
        found = next(f for f in rung(rep, "route")["fix_options"] if f["id"] == "use-found-credential-for-setup")
        assert found["command"].startswith("agent-skills access setup"), found
        rc, out, _ = box.run("setup", "confluence", "--host", "cursor")
        assert rc == 0 and "nothing below is applied for you" in out and "READ_ONLY_MODE=true" in out, out
        _direct(box, {"CONFLUENCE_URL": "https://acme.atlassian.net/wiki"})
        box.launcher("acme-mcp-atlassian")
        box.json_host(".cursor/mcp.json", "mcpServers", {"atl": {"command": str(
            box.home / ".local/bin/acme-mcp-atlassian"), "env": {"ACME_ATL_RW": "1"}}})
        box.env["FAKE_KEYCHAIN_ITEMS"] = ""
        rc, rep, _ = box.run_json("check", "--system", "confluence", "--op", "update", "--target", PAGE, "--host",
                                  "cursor", "--user-authorised")
        assert rc == 3 and rep["blocked_at"] == "auth", (rc, rep["blocked_at"], rung(rep, "auth"))
        assert "store-token" in [f["id"] for f in rung(rep, "auth")["fix_options"]]
        box.assert_no_secret_requested()
    finally:
        box.close()


@check("D1 one MCP detector: access resolve, tools and doctor read routes (with mode), not config text")
def _():
    box = Box()
    try:
        def tool(*args):
            out = subprocess.run([sys.executable, str(HERE / "tools.py")] + list(args), env=box.env,
                                 cwd=str(box.work), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 universal_newlines=True, timeout=60)
            return out.returncode, out.stdout
        _direct(box, {"READ_ONLY_MODE": "true", "JIRA_URL": "https://acme.atlassian.net",
                      "CONFLUENCE_URL": "https://acme.atlassian.net/wiki"})
        rc, out, _ = box.run("resolve", "--service", "jira", "--resource", "https://acme.atlassian.net",
                             "--require", "host,token", "--secret", "token")
        assert rc == 0 and "via: mcp" in out and "read-only [declared]" in out, out
        rc, out, _ = box.run("resolve", "--service", "jira", "--resource", "https://other.atlassian.net",
                             "--require", "host,token", "--secret", "token")
        assert "via: mcp" not in out, "a route for one site must not resolve a request for another: %s" % out
        rc, out = tool("resolve", "jira", "--capability", "tracker.issue.write", "--allow-write")
        assert "read-only, so it cannot provide tracker.issue.write" in out and "resolved via: mcp" not in out, out
        rc, out = tool("resolve", "jira", "--capability", "tracker.issue.read")
        assert "resolved via: mcp" in out, out
        rc, out = tool("status")
        assert re.search(r"jira\s+AVAILABLE\s+MCP \(read-only\)", out), out
        box.json_host(".cursor/mcp.json", "mcpServers", {"linear": {"command": "npx", "args": ["-y", "linear-mcp"]}})
        import importlib
        old = dict(os.environ)
        try:
            os.environ["HOME"] = str(box.home)
            os.environ.pop("CLAUDECODE", None)
            import access_ladder
            importlib.reload(access_ladder)
            found = access_ladder.mcp_servers_for("linear", box.work)
            assert [m["name"] for m in found["matches"]] == ["linear"] and found["matches"][0]["mode"] == "unknown"
            assert access_ladder.mcp_servers_for("gitlab", box.work)["matches"] == []
        finally:
            os.environ.clear()
            os.environ.update(old)
        box.codex('[mcp_servers.atl]\ncommand = "uvx"\nargs = ["mcp-atlassian"]\n')
        doctor = subprocess.run(["bash", str(HERE / "doctor.sh"), "--brief"], env=box.env, cwd=str(box.work),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, timeout=120)
        assert re.search(r"ok\s+mcp\s+\d+ server\(s\):.*codex: atl", doctor.stdout), doctor.stdout
    finally:
        box.close()


# ---------------------------------------------------------------------------
# W. Wrapper inspector
# ---------------------------------------------------------------------------
@check("W1 inspector reads every fixture shape statically and never runs one")
def _():
    import access_inspect as I
    expect = {
        "acme-mcp-atlassian": ("uvx", "read-only", ("ACME_ATL_RW", "1"), ("keychain-generic", "acme-atlassian")),
        "globex-atlassian-mcp": ("docker", "read-only", ("GLOBEX_WRITE_ENABLED", "(any non-empty value)"),
                                 ("pass", "work/globex/atlassian")),
        "python-wrapper": ("uvx", "read-only", ("INITECH_JIRA_READWRITE", "yes"), ("keyring", "initech-jira")),
        "always-readonly": ("uvx", "read-only", None, ("1password", "op://work/umbrella-confluence/token")),
        "default-from-var": ("uvx", "read-only", ("HOOLI_ATL_READONLY", "false"),
                             ("secret-service", "service hooli-jira user me")),
        "misleading-comments": ("uvx", "read-only", ("SOYLENT_RW", "1"), ("file", "~/.config/soylent/confluence-token")),
        "github-npx": ("docker", "read-only", ("VANDELAY_GH_WRITE", "1"), None),
    }
    marker = Path(tempfile.mkdtemp()) / "ran"
    os.environ["ACME_FIXTURE_RAN_MARKER"] = str(marker)
    for name, (launcher, default, toggle, cred) in expect.items():
        rep = I.inspect_launcher(str(FIX / "launchers" / name))
        assert rep["kind"] == "script" and rep["launcher"] == launcher, (name, rep["launcher"])
        assert rep["mode"]["default"] == default, (name, rep["mode"])
        got = rep["mode"].get("toggle")
        if toggle is None:
            assert not got, (name, got)
        else:
            assert (got["env"], got.get("write_when")) == toggle, (name, got)
        if cred:
            assert (cred[0], cred[1]) in [(c["kind"], c["locator"]) for c in rep["credential_refs"]], \
                (name, rep["credential_refs"])
        assert "decoy-item" not in json.dumps(rep), "a commented-out line was treated as code"
    assert not marker.exists(), "the inspector executed a script"
    binary = Path(tempfile.mkdtemp()) / "bin-launcher"
    binary.write_bytes(b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 64)
    binary.chmod(0o755)
    assert I.inspect_launcher(str(binary))["kind"] == "opaque-binary"
    secret = Path(tempfile.mkdtemp()) / "id_key"
    secret.write_text("export READ_ONLY_MODE=true\nurl=https://leak.example.com/k \n")
    rep = I.inspect_launcher(str(secret))
    assert rep["kind"] == "not-executable" and not rep["base_urls"], "a non-executable file was read"
    big = Path(tempfile.mkdtemp()) / "big-launcher"
    big.write_text("#!/bin/sh\n" + "# pad\n" * 20000 + "export READ_ONLY_MODE=true\nexec uvx mcp-atlassian\n")
    big.chmod(0o755)
    rep = I.inspect_launcher(str(big))
    assert rep["truncated"] and rep["upstream"] is None, "content past the read bound was inspected"


# ---------------------------------------------------------------------------
# C. Credential locator: presence only
# ---------------------------------------------------------------------------
@check("C1 credential locator never asks a tool for a secret, and no canary reaches any output or file")
def _():
    box = incident_box(launcher="default-from-var", keychain="jira atlassian")
    try:
        (box.home / ".netrc").write_text("machine hooli.example.com login me password %s\n" % PLAINTEXT_CANARY)
        outputs = []
        for args in (["scan", "--all-hosts"],
                     ["check", "--system", "jira", "--op", "comment", "--target",
                      "https://hooli.example.com/browse/ABC-1", "--host", "codex", "--user-authorised"],
                     ["explain", "jira"], ["inspect", str(box.home / ".local/bin/default-from-var")]):
            for extra in ([], ["--json"]):
                rc, out, err = box.run(*(args + extra))
                outputs += [out, err]
        joined = "\n".join(outputs)
        assert "service hooli-jira user me" in joined, joined[:2000]
        assert "machine hooli.example.com" in joined, "netrc presence not reported"
        no_canary(joined, box.state_written())
        box.assert_no_secret_requested()
        box.assert_never_ran()
    finally:
        box.close()


@check("C2 plaintext token in a host env block is a warning naming file, server and key only")
def _():
    box = Box()
    try:
        path = box.json_host(".cursor/mcp.json", "mcpServers", {"atl": {"command": "uvx", "args": ["mcp-atlassian"],
                             "env": {"CONFLUENCE_API_TOKEN": PLAINTEXT_CANARY}}})
        path.chmod(0o644)
        rc, out, err = box.run("scan", "--host", "cursor")
        assert rc == 0 and "plaintext secret in CONFLUENCE_API_TOKEN" in out and "readable by other users" in out, out
        no_canary(out, err)
        rc, rep, _ = box.run_json("check", "--system", "confluence", "--op", "read", "--host", "cursor")
        no_canary(json.dumps(rep))
    finally:
        box.close()


# ---------------------------------------------------------------------------
# K. Local route knowledge
# ---------------------------------------------------------------------------
@check("K1 local knowledge: confirmed facts go stale when the launcher changes; forget removes them")
def _():
    box = incident_box()
    try:
        rc, _o, _e = box.run("remember", "--system", "confluence", "--server", "atlassian", "--host", "codex", "--yes")
        assert rc == 0
        rc, scan, _ = box.run_json("scan", "--host", "codex")
        conf = [r for r in scan["routes"] if r["system"] == "confluence"][0]
        assert conf["mode"]["strength"] == "declared", conf["mode"]
        launcher = box.home / ".local" / "bin" / "acme-mcp-atlassian"
        launcher.write_text(launcher.read_text() + "\n# edited\nexport EXTRA=1\n")
        rc, scan, _ = box.run_json("scan", "--host", "codex")
        assert any("stale" in w for w in scan["warnings"]), scan["warnings"]
        conf = [r for r in scan["routes"] if r["system"] == "confluence"][0]
        assert conf["mode"]["strength"] == "inferred", "stale knowledge must not stay 'declared'"
        box.json_host(".cursor/mcp.json", "mcpServers", {"ro": {"command": "uvx", "args": ["mcp-atlassian"],
                      "env": {"READ_ONLY_MODE": "true", "CONFLUENCE_API_TOKEN": "${env:T}"}}})
        box.run("remember", "--systems", "confluence", "--server", "ro", "--host", "cursor", "--mode-value",
                "read-write", "--yes")
        rc, rep, _ = box.run_json("check", "--system", "confluence", "--op", "update", "--target", PAGE, "--host",
                                  "cursor", "--user-authorised")
        assert rc == 11 and "READ_ONLY_MODE=true" in rung(rep, "mode")["evidence"], \
            "remembered knowledge must not outrank the route's own read-only setting"
        rc, out, _ = box.run("forget", "jira")
        assert rc == 0 and "Forgot 1 route fact" in out, out
        rc, out, _ = box.run("forget", "--all")
        assert rc == 0 and "Forgot 1 route fact" in out, out
        rc, out, err = box.run("forget", "--all", "--profile", "work")
        assert rc == 2, (out, err)
        rc, out, _ = box.run("forget", "--profile", "nobody")
        assert rc == 0 and "No identity named" in out, "forget --profile must keep its 1.4.0 behaviour"
    finally:
        box.close()


@check("K2 self-report runs only for a launcher the user marked trusted, and only with the documented flag")
def _():
    box = Box()
    try:
        path = box.launcher("self-reporting")
        box.json_host(".cursor/mcp.json", "mcpServers", {"wiki": {"command": str(path),
                                                                   "env": {"CONFLUENCE_API_TOKEN": "${env:T}"}}})
        rc, scan, _ = box.run_json("scan", "--host", "cursor")
        assert not box.marker.exists() and "the launcher reports" not in json.dumps(scan), "ran an untrusted launcher"
        rc, _o, _e = box.run("remember", "--systems", "confluence", "--server", "wiki", "--host", "cursor",
                             "--trust-self-report", "--yes")
        assert rc == 0, (_o, _e)
        rc, rep, _ = box.run_json("check", "--system", "confluence", "--op", "update", "--target", PAGE, "--host",
                                  "cursor", "--user-authorised")
        mode = rung(rep, "mode")
        assert rc == 11 and "the launcher reports read-only" in mode["evidence"] and mode["strength"] == "declared", mode
        assert not box.marker.exists(), "the self-report ran the server instead of answering the flag"
    finally:
        box.close()


# ---------------------------------------------------------------------------
# L. Live introspection
# ---------------------------------------------------------------------------
@check("L1 --live: a fake stdio MCP server verifies read-write, read-only, and survives hang and crash")
def _():
    box = Box()
    try:
        server = str(box.bin / "fake-mcp-server")

        def live(mode):
            box.json_host(".cursor/mcp.json", "mcpServers", {"atl": {"command": server, "env": {"FAKE_MCP_MODE": mode}}})
            box.run("remember", "--systems", "confluence", "--server", "atl", "--host", "cursor",
                    "--mode-value", "read-write", "--yes")
            return box.run_json("check", "--system", "confluence", "--op", "update", "--target", PAGE, "--host",
                                "cursor", "--user-authorised", "--live")
        rc, rep, _ = live("rw")
        mode = rung(rep, "mode")
        assert mode["status"] == "pass" and mode["strength"] == "verified", mode
        rc, rep, _ = live("ro")
        mode = rung(rep, "mode")
        assert rc == 11 and mode["status"] == "fail" and mode["strength"] == "verified", mode
        started = time.time()
        rc, rep, _ = live("hang")
        assert "live introspection failed" in rung(rep, "mode")["evidence"] and time.time() - started < 45, rep
        rc, rep, _ = live("crash")
        assert "live introspection failed" in rung(rep, "mode")["evidence"], rep
        rc, rep, _ = box.run_json("check", "--system", "confluence", "--op", "update", "--target", PAGE, "--host",
                                  "cursor", "--user-authorised")
        assert "live:" not in json.dumps(rep), "a server was started without --live"
        (box.home / ".cursor" / "mcp.json").unlink()
        project = box.work / ".cursor" / "mcp.json"
        project.parent.mkdir()
        project.write_text(json.dumps({"mcpServers": {"atl": {"command": server, "env": {"FAKE_MCP_MODE": "rw"}}}}))
        rc, rep, _ = box.run_json("check", "--system", "confluence", "--op", "update", "--target", PAGE, "--host",
                                  "cursor", "--user-authorised", "--live")
        assert "defined in the repository" in rung(rep, "mode")["evidence"], rung(rep, "mode")
    finally:
        box.close()


# ---------------------------------------------------------------------------
# E. classify-error
# ---------------------------------------------------------------------------
@check("E1 classify-error maps mid-task failures onto rungs and exit codes")
def _():
    box = Box()
    try:
        cases = [(["--status", "401"], "auth", 3), (["--status", "403"], "target", 11),
                 (["--status", "404", "--filtered"], "target", 11), (["--status", "404"], "target", 1),
                 (["--status", "tool confluence_update_page not found"], "mode", 11),
                 (["--status", "409"], "policy", 1), (["--status", "503"], "network", 4),
                 (["--status", "weird"], "unknown", 1)]
        for extra, rid, code in cases:
            rc, rep, _ = box.run_json("classify-error", "--system", "confluence", "--op", "update", "--target", PAGE,
                                      *extra)
            assert (rep["rung"], rc) == (rid, code), (extra, rep["rung"], rc)
        rc, rep, _ = box.run_json("classify-error", "--system", "confluence", "--op", "update", "--status", "404",
                                  "--filtered")
        assert "filtered" in rep["reason"], rep
    finally:
        box.close()


# ---------------------------------------------------------------------------
# S. Setup on a JSON host, masking, and JSONC
# ---------------------------------------------------------------------------
@check("S1 setup on a JSON host: masked diff, atomic write keeps the mode, JSONC is never rewritten")
def _():
    box = Box()
    try:
        path = box.json_host(".cursor/mcp.json", "mcpServers", {"atl": {"command": "uvx", "args": ["mcp-atlassian"],
                             "env": {"READ_ONLY_MODE": "true", "CONFLUENCE_API_TOKEN": PLAINTEXT_CANARY}}})
        path.chmod(0o600)
        rc, out, err = box.run("setup", "confluence", "--write-profile", "--host", "cursor", "--scope", "~jdoe")
        assert rc == 0 and '"READ_ONLY_MODE": "false"' in out and '"CONFLUENCE_SPACES_FILTER": "~jdoe"' in out, out
        assert "<unchanged value of CONFLUENCE_API_TOKEN>" in out or '"CONFLUENCE_API_TOKEN": "[redacted]"' in out, out
        no_canary(out, err)
        rc, out = box.run_tty(["no"], "setup", "confluence", "--write-profile", "--host", "cursor", "--scope", "~jdoe")
        assert "Nothing changed" in out and "atl-write" not in path.read_text(), out
        rc, out = box.run_tty(["yes"], "setup", "confluence", "--write-profile", "--host", "cursor", "--all-scopes")
        no_canary(out)
        data = json.loads(path.read_text())
        assert data["mcpServers"]["atl"]["env"]["READ_ONLY_MODE"] == "true", "the original entry changed"
        assert data["mcpServers"]["atl-write"]["env"]["READ_ONLY_MODE"] == "false"
        assert "CONFLUENCE_SPACES_FILTER" not in data["mcpServers"]["atl-write"]["env"], "--all-scopes still scoped"
        assert data["mcpServers"]["atl-write"]["env"]["TOOLSETS"].split(",")[0] == "confluence_pages", \
            "a Confluence write profile must stay limited to Confluence tools"
        assert data["mcpServers"]["atl-write"]["env"]["CONFLUENCE_API_TOKEN"] == PLAINTEXT_CANARY, \
            "the write profile must carry the same credential reference"
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        rc, out, _ = box.run("setup", "confluence", "--write-profile", "--host", "cursor", "--all-scopes")
        assert rc == 1, "a second write profile must not be proposed over the first"
        vs = box.work / ".vscode" / "mcp.json"
        vs.parent.mkdir()
        vs.write_text('{\n  // keep me\n  "servers": {"atl": {"command": "uvx", "args": ["mcp-atlassian"], '
                      '"env": {"READ_ONLY_MODE": "true"}}}\n}\n')
        before = vs.read_bytes()
        rc, out = box.run_tty(["yes"], "setup", "confluence", "--write-profile", "--host", "copilot", "--all-scopes")
        assert "has comments" in out and vs.read_bytes() == before, out
    finally:
        box.close()


# ---------------------------------------------------------------------------
# P. Policy, audit, intent
# ---------------------------------------------------------------------------
@check("P1 policy tightens, cannot loosen, and fails closed on unknown keys; intent is required for writes")
def _():
    box = Box()
    try:
        _direct(box, {})
        policy = box.home / ".config" / "agent-skills" / "access-policy.json"
        policy.parent.mkdir(parents=True)
        base = ["check", "--system", "confluence", "--op", "update", "--target", PAGE, "--host", "cursor"]
        rc, rep, _ = box.run_json(*base)
        assert rc == 1 and rep["blocked_at"] == "intent", (rc, rep["blocked_at"])
        policy.write_text(json.dumps({"deny": [{"system": "confluence", "operation": "write"}]}))
        rc, rep, _ = box.run_json(*(base + ["--user-authorised"]))
        assert rc == 11 and rep["blocked_at"] == "policy", (rc, rep["blocked_at"])
        policy.write_text(json.dumps({"allow_found_credentials": True}))
        rc, out, err = box.run(*(base + ["--user-authorised"]))
        assert rc == 2 and "may only tighten" in err, err
        policy.write_text(json.dumps({"surprise": 1}))
        rc, out, err = box.run(*(base + ["--user-authorised"]))
        assert rc == 2 and "unknown keys" in err, err
        policy.write_text(json.dumps({"always_confirm": [{"system": "*", "operation": "write"}]}))
        rc, rep, _ = box.run_json(*(base + ["--user-authorised", "--own-target"]))
        assert rc == 0 and "explicit confirmation" in rep["confirmation"], rep["confirmation"]
        policy.unlink()
        rc, rep, _ = box.run_json("check", "--system", "confluence", "--op", "delete", "--target", PAGE, "--host",
                                  "cursor", "--user-authorised")
        assert rc == 0 and "naming each target and the count" in rep["confirmation"], rep["confirmation"]
        rc, out, _ = box.run("record", "--system", "confluence", "--op", "write", "--target", "123", "--route",
                             "mcp:atl", "--result", "ok", "--confirmation", "preview")
        audit = box.home / ".agent-skills" / "state" / "access" / "audit.jsonl"
        line = json.loads(audit.read_text().splitlines()[-1])
        assert line["schema"] == "agent-skills.access-audit/v1" and line["target"] == "123", line
        assert stat.S_IMODE(audit.stat().st_mode) == 0o600
    finally:
        box.close()


@check("P2 --probe: a non-mutating permission query, with the user's own identity, maps onto target and exit 4")
def _():
    import http.server
    import socket
    import threading
    seen = {"auth": [], "methods": set()}
    allow = {"update": True}

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            seen["methods"].add("GET")
            seen["auth"].append(self.headers.get("Authorization", ""))
            if self.path.startswith("/wiki/rest/api/user/current"):
                body = {"accountId": "a1"}
            elif self.path.startswith("/wiki/rest/api/content/123456789"):
                ops = [{"operation": "read", "targetType": "page"}]
                if allow["update"]:
                    ops.append({"operation": "update", "targetType": "page"})
                body = {"id": "123456789", "operations": ops}
            else:
                self.send_response(404)
                self.end_headers()
                return
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)

        def do_PUT(self):
            seen["methods"].add("PUT")
            self.send_response(500)
            self.end_headers()

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    box = Box()
    try:
        base = "http://127.0.0.1:%d/wiki" % port
        _direct(box, {"CONFLUENCE_URL": base})
        page = base + "/spaces/~jdoe/pages/123456789/Notes"
        env = {"AGENT_SKILLS_CONFLUENCE_HOST": base, "AGENT_SKILLS_CONFLUENCE_LOGIN": "me@example.com",
               "AGENT_SKILLS_CONFLUENCE_TOKEN": PLAINTEXT_CANARY}
        args = ["check", "--system", "confluence", "--op", "update", "--target", page, "--host", "cursor",
                "--user-authorised", "--probe"]
        rc, rep, err = box.run_json(*args, env=env)
        target = rung(rep, "target")
        assert rc == 0 and target["status"] == "pass" and target["strength"] == "verified", (rc, target, err)
        allow["update"] = False
        rc, rep, _ = box.run_json(*args, env=env)
        target = rung(rep, "target")
        assert rc == 11 and target["status"] == "fail" and "lacks the 'update' permission" in target["evidence"], target
        no_canary(json.dumps(rep), box.state_written())
        assert seen["methods"] == {"GET"}, "a probe must never write: %s" % seen["methods"]
        assert all(a.startswith("Basic ") for a in seen["auth"]), seen["auth"]
        rc, rep, _ = box.run_json("check", "--system", "confluence", "--op", "update", "--target", page, "--host",
                                  "cursor", "--user-authorised")
        assert rung(rep, "target")["strength"] != "verified", "no probe without --probe"
        seen["auth"].clear()
        (box.work / ".mcp.json").write_text(json.dumps({"mcpServers": {"atlassian": {"command": "uvx", "args": [
            "mcp-atlassian"], "env": {"CONFLUENCE_URL": "http://127.0.0.1:%d/wiki" % port,
                                      "CONFLUENCE_API_TOKEN": "${env:T}"}}}}))
        (box.home / ".cursor" / "mcp.json").unlink()
        box.env["CLAUDECODE"] = "1"
        rc, rep, _ = box.run_json("check", "--system", "confluence", "--op", "update", "--target", page, "--host",
                                  "claude-code", "--user-authorised", "--probe",
                                  env=dict(env, AGENT_SKILLS_CONFLUENCE_HOST="https://acme.atlassian.net/wiki"))
        assert not seen["auth"], "a repository-chosen site received the identity's credential"
        assert "not probing" in rung(rep, "target")["evidence"], rung(rep, "target")
        del box.env["CLAUDECODE"]
        _direct(box, {"CONFLUENCE_URL": base})
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            dead = sock.getsockname()[1]
        dead_base = "http://127.0.0.1:%d/wiki" % dead
        _direct(box, {"CONFLUENCE_URL": dead_base})
        env["AGENT_SKILLS_CONFLUENCE_HOST"] = dead_base
        rc, rep, _ = box.run_json("check", "--system", "confluence", "--op", "update", "--target",
                                  dead_base + "/spaces/~jdoe/pages/123456789/Notes", "--host", "cursor",
                                  "--user-authorised", "--probe", env=env)
        assert rc == 4, (rc, rep["result"], rep["rungs"])
    finally:
        server.shutdown()
        box.close()


# ---------------------------------------------------------------------------
# G. Execution Guard enforcement
# ---------------------------------------------------------------------------
@check("G1 guard asks before an MCP write or a direct REST write to a known system until a check passes")
def _():
    box = Box()
    try:
        _direct(box, {})

        def guard(*args, stdin=None):
            out = subprocess.run([sys.executable, str(HERE / "guard.py")] + list(args), input=stdin, env=box.env,
                                 cwd=str(box.work), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 universal_newlines=True, timeout=30)
            return out.returncode, out.stdout
        payload = json.dumps({"tool_name": "mcp__atlassian__confluence_update_page", "tool_input": {"page_id": "1"},
                              "cwd": str(box.work)})
        other = payload.replace("mcp__atlassian__", "mcp__other__")
        rc, out = guard("check-tool", "--host", "claude-code", stdin=payload)
        assert '"ask"' in out and "ACCESS_UNQUALIFIED_WRITE" in out, out
        rc, out = guard("check-tool", "--host", "claude-code", stdin=payload.replace("update_page", "get_page"))
        assert '"allow"' in out, out
        put = "curl -X PUT https://acme.atlassian.net/wiki/rest/api/content/1 -d @b"
        rc, out = guard("check-command", "--", put)
        assert rc == 10 and "ACCESS_UNQUALIFIED_WRITE" in out, out
        rc, out = guard("check-command", "--", "curl https://acme.atlassian.net/wiki/rest/api/content/1")
        assert rc == 0, out
        rc, _rep, _ = box.run_json("check", "--system", "confluence", "--op", "update", "--target", PAGE, "--host",
                                   "cursor", "--user-authorised")
        assert rc == 0
        rc, out = guard("check-tool", "--host", "claude-code", stdin=payload)
        assert '"allow"' in out, "a passing check should grant the write: %s" % out
        rc, out = guard("check-tool", "--host", "claude-code", stdin=other)
        assert '"ask"' in out, "a grant for one server must not cover another: %s" % out
        rc, out = guard("check-command", "--", put)
        assert rc == 0, out
    finally:
        box.close()


# ---------------------------------------------------------------------------
# X. Redaction, exit codes, no coupling
# ---------------------------------------------------------------------------
@check("X1 redaction: Atlassian tokens, auth headers, JWTs, *_API_TOKEN/_PERSONAL_TOKEN/_SECRET, in both redactors")
def _():
    from guard_audit import redact as runtime
    from asrelease.providers.git import redact as installer
    # Assembled at run time: obviously fake values, never a literal credential.
    atl = "ATA" + "TT" + "3xFfGF0x9YqLmN0pQ"
    jwt = ".".join(["eyJ" + "hbGciOiJub25lIn0", "eyJzdWIiOiJ0ZXN0LXVzZXIifQ", "not-a-real-signature-0000"])
    cases = [(atl, atl), ("Authorization: Basic dXNlcjpwYXNzd29yZA==", "dXNlcjpwYXNzd29yZA=="),
             ("authorization: Bearer abcdefghijklmnop1234", "abcdefghijklmnop1234"),
             ('{"Authorization": "Bearer abcdefghijklmnop1234"}', "abcdefghijklmnop1234"),
             (jwt, "not-a-real-signature-0000"),
             ("CONFLUENCE_API_" + "TOKEN=abc123def456", "abc123def456"),
             ("JIRA_PERSONAL_" + "TOKEN=abc123def456", "abc123def456"), ("CLIENT_" + "SECRET=hunter2x", "hunter2x")]
    for sample, secret in cases:
        assert secret not in runtime(sample), ("runtime", sample, runtime(sample))
        assert secret not in installer(sample), ("installer", sample, installer(sample))
    assert runtime("READ_ONLY_MODE=true") == "READ_ONLY_MODE=true"


@check("X2 exit codes: 11 capability-unavailable added, nothing renumbered")
def _():
    from asrelease.exits import Exit
    assert Exit.CAPABILITY_UNAVAILABLE == 11 and Exit.NAMES[11] == "capability-unavailable"
    assert {0: "ok", 2: "usage-error", 3: "authentication-required", 4: "network-failure",
            10: "update-available"}.items() <= Exit.NAMES.items()


@check("X3 rollback safety: new state files are versioned and unknown schemas are ignored, not trusted")
def _():
    import access_state as S
    box = Box()
    old = dict(os.environ)
    try:
        os.environ["HOME"] = str(box.home)
        os.environ.pop("AGENT_SKILLS_CONFIG_DIR", None)
        os.environ.pop("XDG_CONFIG_HOME", None)
        path = S.routes_path()
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"schema": "agent-skills.local-routes/v9", "routes": [{"match": {}}]}))
        assert S.load_routes()["routes"] == [], "a future schema must be ignored, not half-read"
    finally:
        os.environ.clear()
        os.environ.update(old)
        box.close()


# Digests of organisation names and internal domains that must never ship.
# Plain names would themselves put the names in the payload, because scripts/
# ships. Add one with: python3 scripts/test-access-discovery.py --hash <name>
# A plaintext list kept outside the payload can be named with
# AGENT_SKILLS_COUPLING_DENYLIST=<file> (one entry per line).
COUPLING_DENYLIST = {
    "ce371d3c6bedcfcabbfe11c748778817e8020f151ccc53f2831008ac6eff9ddb",
}
_PAYLOAD = ("bin", "lib", "scripts", "skills", "docs", "hooks", "README.md")


def _digest(token: str) -> str:
    return hashlib.sha256(token.strip().lower().encode("utf-8")).hexdigest()


@check("N1 no coupling: the shipped payload names no organisation from the denylist")
def _():
    deny = set(COUPLING_DENYLIST)
    extra = os.environ.get("AGENT_SKILLS_COUPLING_DENYLIST")
    if extra and Path(extra).is_file():
        deny |= {_digest(line) for line in Path(extra).read_text().splitlines() if line.strip()}
    hits = []
    for entry in _PAYLOAD:
        base = ROOT / entry
        files = [base] if base.is_file() else [p for p in base.rglob("*") if p.is_file()]
        for path in files:
            if "__pycache__" in path.parts or path.stat().st_size > 2_000_000:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            tokens = set(re.findall(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", text)) | set(re.findall(r"[a-z0-9]+", text))
            if any(_digest(token) in deny for token in tokens):
                hits.append(str(path.relative_to(ROOT)))
    assert not hits, "organisation-specific names in the payload: %s" % ", ".join(sorted(set(hits)))
    assert _digest("Example") == _digest("example"), "digests must be case-insensitive"


def main(argv):
    if argv[:1] == ["--hash"] and len(argv) == 2:
        print(_digest(argv[1]))
        return 0
    only = argv[argv.index("-k") + 1] if "-k" in argv else ""
    passed = failed = 0
    for name, fn in CHECKS:
        if only and only.lower() not in name.lower():
            continue
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - report every failure, keep going
            failed += 1
            print("  FAIL  %s\n        %s: %s" % (name, type(exc).__name__, str(exc)[:1500]))
        else:
            passed += 1
            print("  ok    %s" % name)
    print("\n%d passed, %d failed" % (passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
