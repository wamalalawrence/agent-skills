#!/usr/bin/env python3
"""The `agent-skills access` subcommands that discover and qualify routes.

    scan, check, classify-error, inspect, explain, setup, remember, forget
    (routes), systems, record

They sit beside the Access Resolver's own subcommands (`resolve`, `set`,
`bind`, ...) in `access.py`, which registers them through `register()`. The
resolver answers "can I authenticate?"; these answer "can this host do this
operation on this target, and via what?". Neither answers "may I?" - that is
the destructive-action policy, and a check's `policy` rung only reports it.

Every command accepts `--json`. Output passes through the shared redaction in
`guard_audit.py` before it is printed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import access_hosts as hosts_mod
import access_ladder as ladder
import access_registry as reg
import access_state as state
from guard_audit import redact


def _emit(payload, text: str, as_json: bool) -> None:
    if as_json:
        sys.stdout.write(redact(json.dumps(payload, indent=2, sort_keys=True)) + "\n")
    else:
        sys.stdout.write(redact(text) + "\n")


def json_capable(func, name: str):
    """Give a command that prints prose a `--json` form.

    The prose is still produced; with `--json` it is captured and returned as
    `messages` beside the exit code and whatever structured result the command
    attached to `args.result`. A JSON run is never interactive.
    """
    import contextlib
    import io

    def run(args) -> int:
        if not getattr(args, "json", False):
            return func(args)
        import access_setup
        access_setup.FORCE_NONINTERACTIVE = True
        out, err = io.StringIO(), io.StringIO()
        args.result = {}
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = func(args)
        payload = {"schema": "agent-skills.access-command/v1", "command": name, "exit_code": code,
                   "result": args.result, "messages": [l for l in out.getvalue().splitlines() if l.strip()],
                   "errors": [l for l in err.getvalue().splitlines() if l.strip()]}
        sys.stdout.write(redact(json.dumps(payload, indent=2, sort_keys=True)) + "\n")
        return code
    return run


def _result(args, **fields) -> None:
    if isinstance(getattr(args, "result", None), dict):
        args.result.update(fields)


def _systems():
    try:
        return reg.load_systems()
    except (reg.RegistryError, ValueError) as exc:
        print("FAIL the system registry is malformed: %s" % exc, file=sys.stderr)
        raise SystemExit(ladder.EXIT_USAGE)


def _system(systems, sid):
    if sid not in systems:
        print("FAIL unknown system %r. Known: %s (agent-skills access systems)" % (sid, ", ".join(sorted(systems))),
              file=sys.stderr)
        raise SystemExit(ladder.EXIT_USAGE)
    return systems[sid]


def _host(explicit):
    try:
        return hosts_mod.resolve_current_host(explicit or "")
    except hosts_mod.HostReadError as exc:
        print("FAIL %s" % exc, file=sys.stderr)
        raise SystemExit(ladder.EXIT_USAGE)


# ---------------------------------------------------------------------------
def cmd_scan(args) -> int:
    systems = _systems()
    scanner = ladder.Scanner(Path(args.cwd), systems)
    host, how = _host(args.host)
    host_ids = [host] if host and not args.all_hosts else ladder.detected_hosts(scanner.root)
    scan = scanner.scan(host_ids)
    scan["host"] = host if host and not args.all_hosts else ""
    scan["host_source"] = how
    scan["summary"] = ladder.summarise_scan(scan, systems)
    note = "%s (%s)" % (host, how) if host and not args.all_hosts else "all detected hosts (%s)" % how
    _emit(scan, ladder.render_scan(scan, systems, note), args.json)
    return 0


def cmd_check(args) -> int:
    systems = _systems()
    _system(systems, args.system)
    if reg.operation_class(args.op) is None:
        print("FAIL unknown operation %r. Use read, write, destructive, or a verb such as update, comment, "
              "transition, delete." % args.op, file=sys.stderr)
        return ladder.EXIT_USAGE
    try:
        args.policy = state.load_policy()
    except state.PolicyError as exc:
        print("FAIL %s" % exc, file=sys.stderr)
        return ladder.EXIT_USAGE
    host, how = _host(args.host)
    scanner = ladder.Scanner(Path(args.cwd), systems)
    report = ladder.check(scanner, args.system, args.op, args.target or "", host, how, args)
    _emit(report, ladder.render_check(report), args.json)
    return report["exit_code"]


def cmd_classify(args) -> int:
    systems = _systems()
    system = _system(systems, args.system)
    target = reg.parse_target(system, args.target or "")
    result = ladder.classify_error(system, args.op, args.status, target, args.filtered, args.known_existing)
    text = "Classified: %s %s failed with %r -> %s rung: %s.\nNext: %s." % (
        args.system, args.op, args.status, result["rung"], result["reason"], result["next"])
    _emit(result, text, args.json)
    return result["exit_code"]


def cmd_inspect(args) -> int:
    import access_inspect
    report = access_inspect.inspect_launcher(args.launcher, _systems())
    _emit(report, access_inspect.render(report), args.json)
    return 0 if report["kind"] != "missing" else 1


def cmd_explain(args) -> int:
    systems = _systems()
    system = _system(systems, args.system)
    scanner = ladder.Scanner(Path(args.cwd), systems)
    host, how = _host(args.host)
    scan = scanner.scan([host] if host else ladder.detected_hosts(scanner.root))
    routes = [r for r in scan["routes"] if r["system"] == args.system]
    try:
        policy = state.load_policy()
    except state.PolicyError as exc:
        policy = {"error": str(exc)}
    lines = ["%s - %s" % (system["id"], system.get("summary", ""))]
    lines.append("Known upstream MCP servers (public knowledge, with the source each was checked against):")
    for up in system.get("mcp_upstreams", []):
        modes = ", ".join(r.get("env") or r.get("arg") for r in up.get("mode_rules", [])) or "none known"
        lines.append("  %s: mode settings %s; default %s" % (up.get("label", up["id"]), modes, up.get("default_mode")))
        for key, kind in up.get("scope_filters", {}).items():
            lines.append("    scope filter %s limits by %s" % (key, kind))
        for v in up.get("verified_against", []):
            lines.append("    verified against %s on %s" % (v["source"], v["date"]))
    for cli in system.get("cli_routes", []):
        lines.append("  CLI %s: %s" % (cli["command"], cli.get("mode_note", "")))
    lines.append("Routes on this machine (%s):" % (host or "all detected hosts"))
    if not routes:
        lines.append("  none")
    for r in routes:
        lines.append("  %s %s [%s] mode %s (%s): %s" % (r["kind"], r["name"], r.get("host", "*"), r["mode"]["value"],
                                                        r["mode"]["strength"], r["mode"].get("evidence", "")))
    for note in system.get("notes", []):
        lines.append("Note: %s" % note)
    lines.append("Policy: reads need L1-L5; writes need L1-L6, one resolved target and a preview; destructive "
                 "operations need explicit confirmation naming targets and count.")
    if policy.get("error"):
        lines.append("Policy file problem: %s" % policy["error"])
    else:
        lines.append("Never: %s." % "; ".join(state.NEVER))
    lines.append("Docs: %s" % system.get("docs", "docs/access/README.md"))
    _emit({"system": system, "routes": routes, "policy": policy}, "\n".join(lines), args.json)
    return 0


def cmd_systems(args) -> int:
    systems = _systems()
    lines = ["%-11s %s" % (sid, s.get("summary", "")) for sid, s in sorted(systems.items())]
    _emit({"systems": sorted(systems)}, "\n".join(lines), args.json)
    return 0


def _find_route(scanner, systems, system_id, server, host):
    host_ids = [host] if host else ladder.detected_hosts(scanner.root)
    scan = scanner.scan(host_ids)
    routes = [r for r in scan["routes"] if r["kind"] == "mcp" and r["system"] == system_id
              and (not server or r["name"] == server)]
    return routes


def cmd_setup(args) -> int:
    import access_setup
    if args.undo:
        host, _how = _host(args.host) if args.host else (None, "")
        return access_setup.undo(host)
    systems = _systems()
    system = _system(systems, args.system)
    host, how = _host(args.host)
    scanner = ladder.Scanner(Path(args.cwd), systems)
    if not args.write_profile:
        print(access_setup.setup_steps(system, host or ""))
        return 0
    routes = _find_route(scanner, systems, args.system, args.server, host)
    if not host:
        hosts = sorted({r["host"] for r in routes})
        if len(hosts) != 1:
            print("Which host should get the write profile? Found %s in: %s. Re-run with --host <id>." % (
                args.system, ", ".join(hosts) or "no host"), file=sys.stderr)
            return ladder.EXIT_NEEDS_USER
        host = hosts[0]
        routes = [r for r in routes if r["host"] == host]
    if not routes:
        print("No %s route in %s to base a write profile on. `agent-skills access setup %s --host %s` prints the steps "
              "for a new one." % (args.system, host, args.system, host), file=sys.stderr)
        return ladder.EXIT_NEEDS_USER
    route = routes[0]
    scope = args.scope or ""
    if args.target and not scope:
        requirement = access_setup.scope_requirement(route, system)
        if requirement:
            target = reg.parse_target(system, args.target)
            scope = reg.target_scope_value(target, requirement["kind"])
            if not scope:
                print("Cannot tell the %s from %r (a short link does not name it). Pass --scope <key>." % (
                    requirement["kind"], args.target), file=sys.stderr)
                return ladder.EXIT_NEEDS_USER
    plan = access_setup.plan_write_profile(route, system, scope, scanner.root, all_scopes=args.all_scopes)
    if not plan["ok"]:
        print("Cannot propose a write profile: %s" % plan["reason"], file=sys.stderr)
        return ladder.EXIT_NEEDS_USER
    _result(args, host=host, file=plan["file"], server=plan["new_name"], based_on=route["name"],
            write_mode=plan["why"], limits=plan["limits"], diff=redact(plan["diff"]), written=False)
    print("Proposed: a second server %r in %s (%s). The existing %r entry is not changed." % (
        plan["new_name"], plan["file"], hosts_mod.HOST_LABELS.get(host, host), route["name"]))
    print("Write mode: %s." % plan["why"])
    print("Limited to: %s." % "; ".join(plan["limits"]))
    if plan["diff"]:
        print(redact(plan["diff"]))
    print(access_setup.approval_note(host, plan["new_name"]))
    if not plan["writable"]:
        print("This file has comments, which rewriting would lose. Paste this entry yourself:\n%s" % plan["snippet"])
        return 0
    if not access_setup.interactive():
        print("Not a terminal, so nothing was written. To apply it, run this yourself in a terminal:\n"
              "  agent-skills access setup %s --write-profile --host %s%s%s%s" % (
                  args.system, host, " --server %s" % route["name"] if args.server else "",
                  " --scope %s" % scope if scope else "", " --all-scopes" if args.all_scopes else ""))
        return 0
    if not access_setup.confirm("Add %r to %s?" % (plan["new_name"], plan["file"])):
        print("Nothing changed.")
        return 0
    _ok, backup = access_setup.apply_change(plan)
    _result(args, written=True, backup=backup)
    print("Written. Backup: %s (undo: agent-skills access setup --undo --host %s)" % (backup, host))
    print(hosts_mod.RELOAD_HINTS.get(host, "Reload the host's MCP servers."))
    print("Then: agent-skills access check --system %s --op write --target <target> --host %s" % (args.system, host))
    return 0


def cmd_remember(args) -> int:
    systems = _systems()
    host, _how = _host(args.host)
    if args.decision:
        _system(systems, args.system)
        decision = {"system": args.system, "operation": args.operation or "write", "scope": args.scope or "",
                    "choice": args.decision, "date": state.today()}
        if not _confirmed(args, "Remember this decision: %s" % json.dumps(decision)):
            return ladder.EXIT_NEEDS_USER
        state.remember_decision(decision)
        _result(args, decision=decision, saved=True)
        print("Remembered the decision for %s %s." % (args.system, decision["operation"]))
        return 0
    if not args.server:
        print("FAIL remember needs --server <name> (the MCP server entry the facts are about)", file=sys.stderr)
        return ladder.EXIT_USAGE
    scanner = ladder.Scanner(Path(args.cwd), systems)
    routes = _find_route(scanner, systems, args.system or "", args.server, host) if args.system else []
    if not routes:
        host_ids = [host] if host else ladder.detected_hosts(scanner.root)
        routes = [r for r in scanner.scan(host_ids)["routes"] if r["kind"] == "mcp" and r["name"] == args.server]
    if not routes:
        # A server nothing recognises: no known upstream, no telling name. This
        # is exactly where the user teaches us, so fall back to the raw entry.
        route = _raw_server_route(scanner, args.server, host)
        if route is None:
            print("FAIL no MCP server %r found in %s" % (args.server, host or "any detected host"), file=sys.stderr)
            return ladder.EXIT_NEEDS_USER
        if not args.systems:
            print("FAIL server %r serves no system I recognise; say which with --systems confluence,jira" % args.server,
                  file=sys.stderr)
            return ladder.EXIT_USAGE
        routes = [route]
    route = routes[0]
    if args.systems:
        system_ids = [s.strip() for s in args.systems.split(",") if s.strip()]
    else:
        # Every system this server serves, not only the one the check was about.
        host_ids = [route["host"]]
        system_ids = sorted({r["system"] for r in scanner.scan(host_ids)["routes"]
                             if r["kind"] == "mcp" and r["name"] == route["name"]}) or [args.system]
    mode = {}
    if args.mode_env:
        mode = {"env": args.mode_env, "write_when": args.write_when or "1", "default": args.default_mode or "read-only"}
    elif args.mode_value:
        mode = {"value": args.mode_value}
    else:
        toggle = (route["mode"] or {}).get("toggle") or {}
        if toggle.get("env") and toggle.get("write_when") and not toggle["write_when"].startswith("("):
            mode = {"env": toggle["env"], "write_when": toggle["write_when"], "default": "read-only"}
        elif route["mode"]["value"] in ("read-only", "read-write", "modify"):
            mode = {"value": route["mode"]["value"]}
    cred = next((c for c in route.get("credential_refs", []) if c["kind"] in
                 ("keychain-generic", "keychain-internet", "pass", "secret-service", "1password", "keyring")), None)
    entry = {
        # Knowledge describes the launcher, so it matches by command: a write
        # profile that reuses the same launcher inherits it. A server that is
        # not launched by a command (remote URL) matches by name instead.
        # A launcher script is matched by its path, so a write profile that runs
        # the same script inherits the facts. A server launched directly (`uvx
        # mcp-atlassian`) is matched by name as well: `uvx` alone would match
        # every uvx server.
        "match": ({"host": host or "*", "command": route.get("launcher_command") or route["command"]}
                  if route.get("launcher")
                  else {"host": host or "*", "server_name": route["name"], "command": route["command"]}
                  if route["command"] else {"host": host or "*", "server_name": route["name"]}),
        "learned_from": {"server_name": route["name"], "host": route["host"]},
        "systems": system_ids,
        "upstream": route.get("upstream") or "",
        "mode": mode,
        "base_url": (route.get("base_url") or {}).get("value", ""),
        "credential_locator": {"kind": cred["kind"], "name": cred["locator"]} if cred else {},
        "trusted_self_report": bool(args.trust_self_report),
        "confirmed_by_user": state.today(),
        "source": ("told by the user in dialogue" if (args.mode_env or args.mode_value or args.systems)
                   else "wrapper inspection, confirmed in dialogue" if route.get("via") == "launcher"
                   else "host config, confirmed in dialogue"),
        "fingerprint": ({"launcher_sha256": route["launcher"]["sha256"]} if route.get("launcher")
                        else {"entry_sha256": state.entry_fingerprint(route["command"], route.get("args", []))}),
    }
    shown = json.dumps({k: v for k, v in entry.items() if k != "fingerprint"}, indent=2)
    if not _confirmed(args, "Remember these facts (no secrets) in %s?\n%s" % (state.routes_path(), shown)):
        return ladder.EXIT_NEEDS_USER
    _entry, replaced = state.remember_route(entry)
    _result(args, route={k: v for k, v in entry.items() if k != "fingerprint"}, saved=True, replaced=replaced)
    print("%s local route knowledge for server %r in %s. Evidence for it is now 'declared'." % (
        "Updated" if replaced else "Saved", route["name"], state.routes_path()))
    return 0


def _raw_server_route(scanner, server_name, host):
    import access_inspect
    host_ids = [host] if host else ladder.detected_hosts(scanner.root)
    for report in scanner.read(host_ids):
        for server in report["servers"]:
            if server["server_name"] != server_name:
                continue
            inspection = access_inspect.inspect_launcher(ladder.launcher_path(server), scanner.systems) \
                if server["command"] else None
            launcher = None
            if inspection and inspection["kind"] != "missing":
                launcher = {"sha256": inspection["sha256"]}
            return {"kind": "mcp", "host": server["host"], "name": server_name, "command": server["command"],
                    "args": list(server["args"]),
                    "launcher_command": ladder.launcher_path(server),
                    "url": server["url"], "upstream": None, "via": "launcher" if launcher else "direct",
                    "mode": {"value": "unknown", "strength": "inferred"}, "launcher": launcher,
                    "credential_refs": (inspection or {}).get("credential_refs", []), "base_url": None}
    return None


def _confirmed(args, question: str) -> bool:
    print(question)
    if args.yes:
        print("Confirmed by the user in the conversation (--yes).")
        return True
    import access_setup
    if access_setup.interactive():
        return access_setup.confirm("")
    print("Not saved: confirm in a terminal, or pass --yes only after the user said yes.", file=sys.stderr)
    return False


def cmd_forget_routes(args) -> int:
    if not args.system and not args.all:
        print("FAIL forget needs --profile NAME, a system id, or --all", file=sys.stderr)
        return ladder.EXIT_USAGE
    routes, decisions = state.forget(args.system or "", everything=args.all)
    _result(args, routes_removed=routes, decisions_removed=decisions)
    print("Forgot %d route fact(s) and %d decision(s)%s. Credential profiles are untouched "
          "(use `access forget --profile NAME` for those)." % (routes, decisions,
                                                               "" if args.all else " for %s" % args.system))
    return 0


def cmd_record(args) -> int:
    path = state.append_audit({"host": args.host or "", "system": args.system, "operation": args.op,
                               "target": args.target, "route": args.route, "result": args.result,
                               "confirmation": args.confirmation})
    _result(args, audit=str(path))
    print("Recorded in %s (no content, no secrets)." % path)
    return 0


# ---------------------------------------------------------------------------
def register(subparsers) -> None:
    scan = subparsers.add_parser("scan", help="Static inventory of routes per host; no network.")
    scan.add_argument("--host", default="")
    scan.add_argument("--all-hosts", action="store_true")
    scan.add_argument("--json", action="store_true")
    scan.set_defaults(func=cmd_scan)

    check = subparsers.add_parser("check", help="Walk the access ladder for one (system, operation, target).")
    check.add_argument("--system", required=True)
    check.add_argument("--op", required=True, help="read | write | destructive | a verb such as update, comment")
    check.add_argument("--target", default="", help="URL or key of the page, issue, or repository")
    check.add_argument("--host", default="")
    check.add_argument("--probe", action="store_true", help="allow non-mutating identity/permission calls")
    check.add_argument("--live", action="store_true", help="also start configured MCP servers and list their tools")
    check.add_argument("--fresh", action="store_true", help="with --probe: ignore a cached probe answer")
    check.add_argument("--user-authorised", "--user-authorized", dest="user_authorised", action="store_true",
                       help="the user asked for this operation on this target in the current request")
    check.add_argument("--own-target", action="store_true",
                       help="the target is the user's own (personal space, own issue)")
    check.add_argument("--json", action="store_true")
    check.set_defaults(func=cmd_check)

    classify = subparsers.add_parser("classify-error", help="Map a mid-task failure onto a rung.")
    classify.add_argument("--system", required=True)
    classify.add_argument("--op", required=True)
    classify.add_argument("--status", required=True, help="HTTP status or tool error text")
    classify.add_argument("--target", default="")
    classify.add_argument("--filtered", action="store_true", help="a scope filter is known to exclude the target")
    classify.add_argument("--known-existing", action="store_true", help="the target is known to exist")
    classify.add_argument("--json", action="store_true")
    classify.set_defaults(func=cmd_classify)

    inspect = subparsers.add_parser("inspect", help="Statically inspect a launcher script (never runs it).")
    inspect.add_argument("launcher")
    inspect.add_argument("--json", action="store_true")
    inspect.set_defaults(func=cmd_inspect)

    explain = subparsers.add_parser("explain", help="Routes, modes, fixes, and policy for one system.")
    explain.add_argument("system")
    explain.add_argument("--host", default="")
    explain.add_argument("--json", action="store_true")
    explain.set_defaults(func=cmd_explain)

    setup = subparsers.add_parser("setup", help="Print setup steps, or propose a separate write profile.")
    setup.add_argument("system", nargs="?", default="")
    setup.add_argument("--write-profile", action="store_true")
    setup.add_argument("--host", default="")
    setup.add_argument("--server", default="", help="base the profile on this server entry")
    setup.add_argument("--target", default="", help="limit the write profile to this target's space/project")
    setup.add_argument("--scope", default="", help="limit the write profile to this space/project key")
    setup.add_argument("--all-scopes", action="store_true",
                       help="do not limit the write profile to one space/project (it stays limited to the system)")
    setup.add_argument("--undo", action="store_true")
    setup.add_argument("--json", action="store_true", help="machine-readable; never interactive, never writes")
    setup.set_defaults(func=json_capable(cmd_setup, "setup"))

    remember = subparsers.add_parser("remember", help="Record facts or a decision the user confirmed.")
    remember.add_argument("--system", default="")
    remember.add_argument("--systems", default="", help="comma-separated systems the route serves")
    remember.add_argument("--server", default="")
    remember.add_argument("--host", default="")
    remember.add_argument("--mode-env", default="", help="the variable that switches write mode")
    remember.add_argument("--write-when", default="", help="its value that enables writes")
    remember.add_argument("--default-mode", default="", choices=["", "read-only", "read-write"])
    remember.add_argument("--mode-value", default="", choices=["", "read-only", "read-write", "modify"])
    remember.add_argument("--decision", default="")
    remember.add_argument("--operation", default="")
    remember.add_argument("--scope", default="")
    remember.add_argument("--trust-self-report", action="store_true",
                          help="the launcher implements --agent-skills-capabilities and may be run to ask it")
    remember.add_argument("--yes", action="store_true",
                          help="the user confirmed in the conversation; pass it only after they said yes")
    remember.add_argument("--json", action="store_true")
    remember.set_defaults(func=json_capable(cmd_remember, "remember"))

    systems = subparsers.add_parser("systems", help="List the system registry.")
    systems.add_argument("--json", action="store_true")
    systems.set_defaults(func=cmd_systems)

    record = subparsers.add_parser("record", help="Append one write to the local audit log.")
    record.add_argument("--system", required=True)
    record.add_argument("--op", required=True)
    record.add_argument("--target", required=True)
    record.add_argument("--route", required=True)
    record.add_argument("--result", required=True)
    record.add_argument("--confirmation", default="")
    record.add_argument("--host", default="")
    record.add_argument("--json", action="store_true")
    record.set_defaults(func=json_capable(cmd_record, "record"))
