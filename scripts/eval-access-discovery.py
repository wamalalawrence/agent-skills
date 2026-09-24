#!/usr/bin/env python3
"""Run the CLI side of the Wamala access evals and record exactly what Wamala would relay.

    python3 scripts/eval-access-discovery.py [--out eval-runs/<release>/access-discovery]

The evals in `evals/wamala-access-*.md` describe what Wamala must do with a check's
result: relay it, run the resolution dialogue, never improvise. That half needs a
model. This script covers the other half deterministically - for each of the ten
scenarios it builds the sandbox, runs the commands the eval names, writes their
exact output to `<out>/<scenario>.txt`, and scores the facts the dialogue depends
on (result, blocked rung, strength, fix options, exit code). It prints a markdown
table; exit 1 if any scenario's facts are wrong.

The sandboxes and fixtures are the test suite's (`test-access-discovery.py`), with
the same invented names.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("access_suite", str(HERE / "test-access-discovery.py"))
suite = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(suite)
Box, PAGE, rung = suite.Box, suite.PAGE, suite.rung


def _clean(box, text):
    import os
    text = text.replace("\r\n", "\n")
    for home in (os.path.realpath(str(box.home)), str(box.home)):
        text = text.replace(home, "~")
    for sandbox in (os.path.realpath(str(box.dir)), str(box.dir)):
        text = text.replace(sandbox, "<sandbox>")
    return text


def transcript(box, *args, env=None):
    rc, out, err = box.run(*args, env=env)
    return rc, _clean(box, "$ agent-skills access %s\n%s%s[exit %d]\n" % (" ".join(args), out, err, rc))


def s1_incident():
    box = suite.incident_box()
    try:
        rc, text = transcript(box, "check", "--system", "confluence", "--op", "update", "--target", PAGE,
                              "--host", "codex", "--user-authorised", "--own-target")
        _r, rep, _ = box.run_json("check", "--system", "confluence", "--op", "update", "--target", PAGE, "--host",
                                  "codex", "--user-authorised", "--own-target")
        ids = [f["id"] for f in rung(rep, "mode")["fix_options"]]
        ok = (rc == 11 and rep["blocked_at"] == "mode" and rung(rep, "mode")["strength"] == "inferred"
              and ids == ["confirm-inferred", "write-profile", "manual-handoff"])
        return ok, "blocked at mode [inferred], exit %d, options %s" % (rc, ",".join(ids)), text
    finally:
        box.close()


def s2_write_profile_present():
    box = suite.incident_box()
    try:
        texts = []
        rc, text = transcript(box, "setup", "confluence", "--write-profile", "--host", "codex", "--target", PAGE)
        texts.append(text)
        rc, out = box.run_tty(["yes"], "setup", "confluence", "--write-profile", "--host", "codex", "--target", PAGE)
        texts.append(_clean(box, "$ agent-skills access setup confluence --write-profile --host codex --target %s   "
                                 "(in a terminal)\n" % PAGE + out + "[exit %d]\n" % rc))
        rc, text = transcript(box, "remember", "--system", "confluence", "--server", "atlassian", "--host", "codex",
                              "--yes")
        texts.append(text)
        rc, text = transcript(box, "check", "--system", "confluence", "--op", "update", "--target", PAGE, "--host",
                              "codex", "--user-authorised", "--own-target")
        texts.append(text)
        _r, rep, _ = box.run_json("check", "--system", "confluence", "--op", "update", "--target", PAGE, "--host",
                                  "codex", "--user-authorised", "--own-target")
        ok = rc == 0 and rep["route"]["name"] == "atlassian-write" and "preview" in rep["confirmation"]
        return ok, "available via atlassian-write; %s" % rep["confirmation"], "\n".join(texts)
    finally:
        box.close()


def s3_no_route():
    box = Box()
    try:
        (box.home / ".cursor").mkdir()
        rc, text = transcript(box, "check", "--system", "jira", "--op", "comment", "--target", "ABC-12", "--host",
                              "cursor", "--user-authorised")
        _r, rep, _ = box.run_json("check", "--system", "jira", "--op", "comment", "--target", "ABC-12", "--host",
                                  "cursor", "--user-authorised")
        ids = [f["id"] for f in rung(rep, "route")["fix_options"]]
        ok = rc == 1 and rep["blocked_at"] == "route" and ids[0] == "setup-route" and ids[-1] == "manual-handoff"
        return ok, "blocked at route, exit %d, options %s" % (rc, ",".join(ids)), text
    finally:
        box.close()


def s4_no_credential():
    box = suite.incident_box(keychain="")
    try:
        rc, text = transcript(box, "check", "--system", "confluence", "--op", "update", "--target", PAGE, "--host",
                              "codex", "--user-authorised")
        _r, rep, _ = box.run_json("check", "--system", "confluence", "--op", "update", "--target", PAGE, "--host",
                                  "codex", "--user-authorised")
        ids = [f["id"] for f in rung(rep, "auth")["fix_options"]]
        ok = rc == 3 and rep["blocked_at"] == "auth" and ids[0] == "store-token"
        return ok, "blocked at auth, exit %d, options %s" % (rc, ",".join(ids)), text
    finally:
        box.close()


def s5_credential_found_no_route():
    box = Box()
    try:
        box.env["FAKE_KEYCHAIN_ITEMS"] = "confluence"
        (box.home / ".cursor").mkdir()
        rc, text = transcript(box, "check", "--system", "confluence", "--op", "update", "--target", PAGE, "--host",
                              "cursor", "--user-authorised")
        _r, rep, _ = box.run_json("check", "--system", "confluence", "--op", "update", "--target", PAGE, "--host",
                                  "cursor", "--user-authorised")
        opts = rung(rep, "route")["fix_options"]
        found = [o for o in opts if o["id"] == "use-found-credential-for-setup"]
        ok = (rc == 1 and found and found[0]["command"].startswith("agent-skills access setup")
              and rep["found_credentials"][0]["locator"] == "confluence")
        return ok, "blocked at route; found keychain item offered only as setup input", text
    finally:
        box.close()


def s6_target_out_of_scope():
    box = Box()
    try:
        suite._direct(box, {"CONFLUENCE_SPACES_FILTER": "DEV,OPS", "CONFLUENCE_URL": "https://acme.atlassian.net/wiki"})
        rc, text = transcript(box, "check", "--system", "confluence", "--op", "update", "--target", PAGE, "--host",
                              "cursor", "--user-authorised", "--own-target")
        _r, rep, _ = box.run_json("check", "--system", "confluence", "--op", "update", "--target", PAGE, "--host",
                                  "cursor", "--user-authorised", "--own-target")
        ev = rung(rep, "target")["evidence"]
        ok = rc == 11 and "missing, not forbidden" in ev and "personal space" in ev
        return ok, "blocked at target: personal space excluded by CONFLUENCE_SPACES_FILTER", text
    finally:
        box.close()


def s7_account_lacks_permission():
    import http.server
    import threading

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            body = {"accountId": "a"} if "user/current" in self.path else \
                {"id": "123456789", "operations": [{"operation": "read", "targetType": "page"}]}
            data = json.dumps(body).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(data)

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    box = Box()
    try:
        base = "http://127.0.0.1:%d/wiki" % server.server_address[1]
        suite._direct(box, {"CONFLUENCE_URL": base})
        env = {"AGENT_SKILLS_CONFLUENCE_HOST": base, "AGENT_SKILLS_CONFLUENCE_LOGIN": "me@example.com",
               "AGENT_SKILLS_CONFLUENCE_TOKEN": "not-a-real-token"}
        page = base + "/spaces/TEAM/pages/123456789/Runbook"
        rc, text = transcript(box, "check", "--system", "confluence", "--op", "update", "--target", page, "--host",
                              "cursor", "--user-authorised", "--probe", env=env)
        text = text.replace(str(server.server_address[1]), "<port>")
        ok = rc == 11 and "lacks the 'update' permission" in text and "[verified]" in text
        return ok, "blocked at target [verified]: no update permission; ask the space owner", text
    finally:
        server.shutdown()
        box.close()


def s8_host_divergence():
    box = Box()
    try:
        suite._direct(box, {"READ_ONLY_MODE": "true"}, host=".cursor/mcp.json")
        suite._direct(box, {}, host=".kiro/settings/mcp.json")
        rc1, t1 = transcript(box, "scan", "--all-hosts")
        rc, t2 = transcript(box, "check", "--system", "confluence", "--op", "update", "--target", PAGE,
                            "--user-authorised")
        ok = rc == 1 and "differs across hosts" in t1 and "Tell me which assistant" in t2
        return ok, "unknown at route: asks which host; scan warns about divergence", t1 + "\n" + t2
    finally:
        box.close()


def s9_unknown_wrapper_confirmed():
    box = Box()
    try:
        opaque = box.home / ".local" / "bin" / "work-bridge"
        opaque.write_bytes(b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 64)
        opaque.chmod(0o755)
        box.json_host(".cursor/mcp.json", "mcpServers", {"bridge": {"command": str(opaque),
                      "env": {"BRIDGE_RW": "1", "JIRA_API_TOKEN": "${env:JIRA_TOKEN}"}}})
        texts = []
        rc0, t = transcript(box, "check", "--system", "jira", "--op", "comment", "--target", "ABC-12", "--host",
                            "cursor", "--user-authorised")
        texts.append(t)
        rc, t = transcript(box, "inspect", str(opaque))
        texts.append(t)
        rc, t = transcript(box, "remember", "--systems", "jira", "--server", "bridge", "--host", "cursor",
                           "--mode-env", "BRIDGE_RW", "--write-when", "1", "--default-mode", "read-only", "--yes")
        texts.append(t)
        rc, t = transcript(box, "check", "--system", "jira", "--op", "comment", "--target", "ABC-12", "--host",
                           "cursor", "--user-authorised")
        texts.append(t)
        _r, rep, _ = box.run_json("check", "--system", "jira", "--op", "comment", "--target", "ABC-12", "--host",
                                  "cursor", "--user-authorised")
        ok = rc0 == 1 and rc == 0 and rung(rep, "mode")["strength"] == "declared"
        return ok, "no route until the user says what it is; then available [declared]", "\n".join(texts)
    finally:
        box.close()


def s10_mid_task_403():
    box = Box()
    try:
        rc, text = transcript(box, "classify-error", "--system", "confluence", "--op", "update", "--status", "403",
                              "--target", PAGE)
        ok = rc == 11 and "target rung" in text and "do not retry through another route" in text
        return ok, "403 -> target rung (permission / token scope), exit 11, no other route", text
    finally:
        box.close()


SCENARIOS = [
    ("01-incident", "incident: read-only launcher", s1_incident),
    ("02-write-profile", "write profile present", s2_write_profile_present),
    ("03-no-route", "no route", s3_no_route),
    ("04-no-credential", "no credential", s4_no_credential),
    ("05-credential-no-route", "credential found, no route", s5_credential_found_no_route),
    ("06-out-of-scope", "target out of scope", s6_target_out_of_scope),
    ("07-no-permission", "account lacks permission", s7_account_lacks_permission),
    ("08-host-divergence", "host divergence", s8_host_divergence),
    ("09-unknown-wrapper", "unknown wrapper confirmed by the user", s9_unknown_wrapper_confirmed),
    ("10-mid-task-403", "mid-task 403", s10_mid_task_403),
]


def main(argv) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    out = Path(args.out) if args.out else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
    rows = ["| Scenario | Facts correct | What the check told Wamala |", "| --- | --- | --- |"]
    failed = 0
    for slug, label, fn in SCENARIOS:
        try:
            ok, summary, text = fn()
        except Exception as exc:  # noqa: BLE001 - a crashed scenario is a failed one
            ok, summary, text = False, "crashed: %s" % exc, ""
        failed += 0 if ok else 1
        rows.append("| %s | %s | %s |" % (label, "yes" if ok else "no", summary))
        if out:
            (out / ("%s.txt" % slug)).write_text(text, encoding="utf-8")
    print("\n".join(rows))
    print("\n%d/%d scenarios correct" % (len(SCENARIOS) - failed, len(SCENARIOS)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
