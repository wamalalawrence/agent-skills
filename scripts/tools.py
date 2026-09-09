#!/usr/bin/env python3
"""Engineering Tool Capability Framework — the resolver runtime and its CLI.

This sits one layer above the Access Resolver. A skill decides *what* engineering
work it needs and names a capability (`ci.logs.read`, `database.query.read`,
`infrastructure.plan`). This runtime decides *how* that capability can be
provided on this machine, walking a fixed transport order that prefers a
capability the environment already has over any stored secret:

    host  ->  mcp  ->  authenticated CLI  ->  local/native client  ->
    connection profile  ->  API adapter  ->  unresolved (setup guidance)

It never authenticates anything itself. When a transport needs a credential it
shells out to `agent-skills access resolve` and reports that command's
secret-safe verdict. It never enforces a dangerous action either: it *classifies*
every capability as READ / WRITE / ELEVATED / DESTRUCTIVE so a skill knows the
blast radius before it proposes a command, and the Execution Guard remains the
authoritative gate on the command that actually runs.

Data lives in `lib/tools/`:
    capabilities.json      the provider-neutral vocabulary + action classes
    classes.json           the five tool classes + the transport order
    registry.d/<id>.json   one reference tool per file
    fixtures/<id>.json     extensibility fixtures — NOT claimed as supported

Adding a provider is one file in `registry.d/`. Nothing in Wamala, the
specialists, the Access Resolver core, or the Execution Guard core changes.

Exit codes:
    0   ok / resolved
    1   a resolve request could not be satisfied, or doctor found a problem
    2   usage error, unknown tool, unknown capability, or a blocked action class
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_UNRESOLVED = 1
EXIT_USAGE = 2

ACTION_ORDER = {"READ": 0, "WRITE": 1, "ELEVATED": 2, "DESTRUCTIVE": 3}

# Capability-name suffixes whose action class is structurally fixed. `doctor`
# and the test suite assert the vocabulary never contradicts these, so a new
# capability cannot be quietly filed one notch too low.
SUFFIX_ACTION_RULES = (
    (".destroy", "DESTRUCTIVE"),
    (".delete", "DESTRUCTIVE"),
    (".plan", "READ"),
    (".explain", "READ"),
    (".apply", "ELEVATED"),
    (".publish", "ELEVATED"),
    (".trigger", "ELEVATED"),
    (".deploy", "ELEVATED"),
)

# A capability whose name carries one of these reads a potentially large,
# potentially hostile external payload. Every tool that owns such a capability
# must list it under `bounded_capabilities`, and the consuming skill must route
# the read through `agent-skills context pack`.
BOUNDED_MARKERS = (
    "logs.read",
    "query.read",
    "message.sample",
    "thread.read",
    "document.read",
    "errors.read",
    "finding.read",
    "timeline.read",
    "traces.read",
)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def _lib_dir() -> Path:
    override = os.environ.get("AGENT_SKILLS_TOOLS_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "lib" / "tools"


def _load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"tools: missing data file: {path}")
    except (ValueError, OSError) as exc:
        raise SystemExit(f"tools: cannot read {path}: {exc}")


class Registry:
    def __init__(self, include_fixtures: bool = False) -> None:
        base = _lib_dir()
        self.base = base
        caps = _load_json(base / "capabilities.json")
        classes = _load_json(base / "classes.json")
        if not isinstance(caps, dict) or not isinstance(classes, dict):
            raise SystemExit("tools: capabilities.json / classes.json must be objects")
        self.action_classes: dict = caps.get("action_classes", {})
        self.capabilities: dict = caps.get("capabilities", {})
        self.classes: dict = classes.get("classes", {})
        self.resolution_order: list = classes.get("resolution_order", [])
        self.transport_needs_auth: dict = classes.get("transport_needs_auth", {})
        self.tools: dict = {}
        self.fixtures: dict = {}
        for path in sorted((base / "registry.d").glob("*.json")):
            d = _load_json(path)
            if isinstance(d, dict) and d.get("id"):
                self.tools[d["id"]] = d
        for path in sorted((base / "fixtures").glob("*.json")):
            d = _load_json(path)
            if isinstance(d, dict) and d.get("id"):
                self.fixtures[d["id"]] = d
        self.include_fixtures = include_fixtures

    def all_tools(self) -> dict:
        merged = dict(self.tools)
        if self.include_fixtures:
            merged.update(self.fixtures)
        return merged

    def get_tool(self, tool_id: str) -> dict:
        merged = dict(self.tools)
        merged.update(self.fixtures)
        if tool_id not in merged:
            raise SystemExit(
                f"tools: unknown tool {tool_id!r}. `agent-skills tools list` shows the set."
            )
        return merged[tool_id]

    def action_of(self, capability: str) -> str:
        entry = self.capabilities.get(capability)
        if not isinstance(entry, dict) or "action" not in entry:
            raise SystemExit(
                f"tools: unknown capability {capability!r}. "
                f"`agent-skills tools capabilities` lists the vocabulary."
            )
        return entry["action"]

    def resolution_ranks(self) -> list:
        return [row.get("transport") for row in self.resolution_order]


# ---------------------------------------------------------------------------
# Probes — read-only, fast, never mutate a session. Mirrors access.py.
# ---------------------------------------------------------------------------
def _probe_cli(command: str, args: list, timeout: int = 15) -> bool:
    if shutil.which(command) is None:
        return False
    try:
        result = subprocess.run(
            [command] + list(args),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


_MCP_CONFIG_CANDIDATES = (
    ".mcp.json",
    "mcp.json",
    ".cursor/mcp.json",
    ".vscode/mcp.json",
    ".kiro/settings/mcp.json",
)
_MCP_HOME_CANDIDATES = (
    ".kiro/settings/mcp.json",
    ".cursor/mcp.json",
    ".claude.json",
    ".codex/config.toml",
)


def _detect_mcp(hint: str, cwd: Path) -> str:
    """Return the path of an MCP config that mentions `hint`, or "" if none.

    This does not call a tool. It reports that an MCP path may exist, the same
    way access.py step 1 does, so a resolve can prefer it over a stored secret.
    """
    hint = (hint or "").lower()
    seen = []
    for name in _MCP_CONFIG_CANDIDATES:
        seen.append(cwd / name)
    home = Path(os.path.expanduser("~"))
    for name in _MCP_HOME_CANDIDATES:
        seen.append(home / name)
    for path in seen:
        try:
            if path.is_file() and hint and hint in path.read_text(encoding="utf-8", errors="ignore").lower():
                return str(path)
        except OSError:
            continue
    return ""


def _assumed_hosts() -> set:
    raw = os.environ.get("AGENT_SKILLS_TOOLS_ASSUME_HOST", "")
    return {piece.strip().lower() for piece in raw.split(",") if piece.strip()}


def _access_resolve(service: str, require: list, secret: list) -> dict:
    """Ask `agent-skills access resolve` whether auth can be constructed.

    Returns {"resolved": bool, "detail": str, "missing": [...]}. Never contains a
    secret value: `access resolve --json` is documented safe for agent context.
    """
    launcher = os.environ.get("AGENT_SKILLS_LAUNCHER")
    if launcher:
        cmd = [launcher, "access", "resolve"]
    else:
        cmd = [sys.executable, str(Path(__file__).resolve().parent / "access.py"), "resolve"]
    cmd += ["--service", service, "--json"]
    if require:
        cmd += ["--require", ",".join(require)]
    for field in secret or []:
        cmd += ["--secret", field]
    try:
        out = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"resolved": False, "detail": f"access resolve unavailable: {exc}", "missing": list(require)}
    payload = {}
    if out.stdout:
        try:
            payload = json.loads(out.stdout)
        except ValueError:
            payload = {}
    resolved = out.returncode == 0 or bool(payload.get("resolved"))
    missing = payload.get("missing") or payload.get("missing_fields") or []
    detail = payload.get("status") or payload.get("summary") or ("resolved" if resolved else "not resolved")
    return {"resolved": bool(resolved), "detail": str(detail), "missing": list(missing)}


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------
def resolve_capability(reg: Registry, tool: dict, capability: str, allow_write: bool):
    """Walk the transport order for one capability on one tool.

    Returns (result_dict, exit_code).
    """
    if capability not in tool.get("capabilities", []):
        return (
            {
                "tool": tool["id"],
                "capability": capability,
                "status": "unknown-capability-for-tool",
                "detail": f"{tool['id']} does not declare {capability}",
            },
            EXIT_USAGE,
        )

    action = reg.action_of(capability)
    bounded = capability in tool.get("bounded_capabilities", [])
    base = {
        "tool": tool["id"],
        "class": tool["class"],
        "capability": capability,
        "action_class": action,
        "bounded": bounded,
    }
    if bounded:
        base["bounded_note"] = (
            "This capability reads large, untrusted external output. Read it with an explicit "
            "bound (time range, row/line limit, message count, log budget) and pass it through "
            "`agent-skills context pack` before it enters model context. Never fetch everything."
        )

    if action == "DESTRUCTIVE":
        base.update(
            status="blocked",
            detail=(
                "DESTRUCTIVE capabilities are never resolved here. The Execution Guard "
                "hard-deny floor governs the command that would perform this action."
            ),
        )
        return base, EXIT_USAGE

    if action in ("WRITE", "ELEVATED") and not allow_write:
        base.update(
            status="blocked",
            detail=(
                f"{capability} is {'an' if action[0] in 'AEIOU' else 'a'} {action} capability. "
                f"Re-run with --allow-write to "
                f"resolve a transport. Resolution is not authorization: the Execution "
                f"Guard still gates the actual command."
            ),
        )
        return base, EXIT_USAGE

    cwd = Path.cwd()
    steps = []
    order = reg.resolution_ranks()
    transports = tool.get("transports", [])

    def step(transport, outcome, detail, **extra):
        row = {"transport": transport, "outcome": outcome, "detail": detail}
        row.update(extra)
        steps.append(row)

    for transport_kind in order:
        for t in transports:
            if t.get("kind") != transport_kind:
                continue
            kind = t["kind"]
            if kind == "host":
                if tool["id"] in _assumed_hosts():
                    step("host", "resolved", "host declared via AGENT_SKILLS_TOOLS_ASSUME_HOST")
                    base.update(status="resolved", via="host", needs_auth=False, steps=steps)
                    return base, EXIT_OK
                step("host", "skipped",
                     "host-native tools are not probeable from a script; check your agent host")
                continue
            if kind == "mcp":
                path = _detect_mcp(t.get("hint", tool["id"]), cwd)
                if path:
                    step("mcp", "resolved", f"MCP config mentions {t.get('hint', tool['id'])}: {path}")
                    base.update(status="resolved", via="mcp", needs_auth=False, steps=steps)
                    return base, EXIT_OK
                step("mcp", "skipped", "no host MCP config mentions this service")
                continue
            if kind in ("cli", "native-client"):
                command = t.get("command", "")
                probe = t.get("probe")
                if not command or shutil.which(command) is None:
                    step(kind, "skipped", f"{command or '(no command)'} not on PATH")
                    continue
                if probe is not None and not _probe_cli(command, probe):
                    step(kind, "skipped",
                         f"{command} present but probe `{command} {' '.join(probe)}` did not succeed")
                    continue
                label = "authenticated CLI" if kind == "cli" else "local tool"
                step(kind, "resolved", f"{command} available ({label})")
                base.update(status="resolved", via=kind, command=command, needs_auth=False, steps=steps)
                return base, EXIT_OK
            if kind in ("profile", "api"):
                service = t.get("auth_service") or tool.get("auth_service")
                if not service:
                    step(kind, "skipped", "no auth_service declared")
                    continue
                verdict = _access_resolve(service, t.get("require", []), t.get("secret", []))
                if verdict["resolved"]:
                    step(kind, "resolved", f"Access Resolver: {verdict['detail']}")
                    base.update(status="resolved", via=kind, auth_service=service, needs_auth=True, steps=steps)
                    return base, EXIT_OK
                step(kind, "needs-setup", f"Access Resolver: {verdict['detail']}",
                     missing_fields=verdict["missing"], auth_service=service)
                continue

    base.update(
        status="unresolved",
        steps=steps,
        detail=(
            f"No transport for {capability} on {tool['id']} resolved on this machine. "
            f"See {tool.get('docs', 'docs/engineering-tools.md')} for setup."
        ),
    )
    return base, EXIT_UNRESOLVED


def tool_status(reg: Registry, tool: dict) -> dict:
    """Cheap availability summary for `tools status`. Never resolves a capability
    and never touches a secret value — only reports field names."""
    cwd = Path.cwd()
    for transport_kind in reg.resolution_ranks():
        for t in tool.get("transports", []):
            if t.get("kind") != transport_kind:
                continue
            kind = t["kind"]
            if kind == "host" and tool["id"] in _assumed_hosts():
                return {"state": "AVAILABLE", "via": "host"}
            if kind == "mcp":
                path = _detect_mcp(t.get("hint", tool["id"]), cwd)
                if path:
                    return {"state": "AVAILABLE", "via": "MCP"}
            if kind in ("cli", "native-client"):
                command = t.get("command", "")
                if command and shutil.which(command) is not None:
                    if t.get("probe") is None or _probe_cli(command, t["probe"]):
                        return {"state": "AVAILABLE", "via": command}
            if kind in ("profile", "api"):
                service = t.get("auth_service") or tool.get("auth_service")
                if service:
                    verdict = _access_resolve(service, t.get("require", []), t.get("secret", []))
                    if verdict["resolved"]:
                        label = "profile" if kind == "profile" else "api"
                        return {"state": "AVAILABLE", "via": f"{label}: {service}"}
    # Nothing resolved. Distinguish "a credential would fix it" from "no path".
    for t in tool.get("transports", []):
        if t.get("kind") in ("profile", "api"):
            return {"state": "NEEDS SETUP", "via": tool.get("docs", "docs/engineering-tools.md")}
    return {"state": "UNAVAILABLE", "via": "no transport available on this machine"}


# ---------------------------------------------------------------------------
# Integrity — used by `doctor` and by scripts/test-tools.sh / validate-repo.py
# ---------------------------------------------------------------------------
def integrity_problems(reg: Registry) -> list:
    problems = []
    known_caps = set(reg.capabilities)
    known_classes = set(reg.classes)
    known_kinds = set(reg.transport_needs_auth)

    # vocabulary self-consistency
    for cap, entry in reg.capabilities.items():
        action = entry.get("action")
        if action not in ACTION_ORDER:
            problems.append(f"capability {cap}: action {action!r} is not one of {sorted(ACTION_ORDER)}")
            continue
        for suffix, required in SUFFIX_ACTION_RULES:
            if cap.endswith(suffix) and action != required:
                problems.append(
                    f"capability {cap}: name ends {suffix} so action must be {required}, not {action}"
                )

    for tool_id, tool in {**reg.tools, **reg.fixtures}.items():
        where = "fixtures" if tool_id in reg.fixtures else "registry.d"
        if tool.get("schema") != "agent-skills.tool-definition/v1":
            problems.append(f"{where}/{tool_id}: wrong or missing schema")
        if tool.get("id") != tool_id:
            problems.append(f"{where}/{tool_id}: id field {tool.get('id')!r} != filename")
        if tool.get("class") not in known_classes:
            problems.append(f"{where}/{tool_id}: class {tool.get('class')!r} not in classes.json")
        if not tool.get("capabilities"):
            problems.append(f"{where}/{tool_id}: no capabilities")
        for cap in tool.get("capabilities", []):
            if cap not in known_caps:
                problems.append(f"{where}/{tool_id}: capability {cap!r} not in the vocabulary")
        if not tool.get("transports"):
            problems.append(f"{where}/{tool_id}: no transports")
        for t in tool.get("transports", []):
            if t.get("kind") not in known_kinds:
                problems.append(f"{where}/{tool_id}: transport kind {t.get('kind')!r} unknown")
            if t.get("kind") in ("profile", "api"):
                if not (t.get("auth_service") or tool.get("auth_service")):
                    problems.append(f"{where}/{tool_id}: {t.get('kind')} transport needs an auth_service")
                if not t.get("require"):
                    problems.append(f"{where}/{tool_id}: {t.get('kind')} transport needs a require list")
        # bounded-read coherence
        bounded = set(tool.get("bounded_capabilities", []))
        for cap in tool.get("capabilities", []):
            if any(marker in cap for marker in BOUNDED_MARKERS) and cap not in bounded:
                problems.append(
                    f"{where}/{tool_id}: {cap} is a large external read and must be listed "
                    f"under bounded_capabilities (route it through Context Optimizer)"
                )
        for cap in bounded:
            if cap not in tool.get("capabilities", []):
                problems.append(f"{where}/{tool_id}: bounded_capabilities lists {cap!r} which the tool does not have")
        # destructive tools must name the Guard floor
        if any(reg.capabilities.get(c, {}).get("action") == "DESTRUCTIVE" for c in tool.get("capabilities", [])):
            note = (tool.get("notes") or "").lower()
            if "guard" not in note and "floor" not in note:
                problems.append(
                    f"{where}/{tool_id}: owns a DESTRUCTIVE capability but its notes do not "
                    f"reference the Execution Guard floor"
                )
        if tool.get("reference_status") not in ("validated", "fixture"):
            problems.append(f"{where}/{tool_id}: reference_status must be 'validated' or 'fixture'")
        if where == "fixtures" and tool.get("reference_status") != "fixture":
            problems.append(f"fixtures/{tool_id}: a fixture must declare reference_status 'fixture'")

    return problems


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _print_json(obj) -> None:
    json.dump(obj, sys.stdout, indent=2, sort_keys=False)
    sys.stdout.write("\n")


def cmd_list(reg: Registry, args) -> int:
    rows = []
    for tool_id, tool in sorted(reg.all_tools().items()):
        if args.tool_class and tool.get("class") != args.tool_class:
            continue
        if args.category and tool.get("category") != args.category:
            continue
        rows.append(tool)
    if args.json:
        _print_json([
            {
                "id": t["id"],
                "class": t["class"],
                "category": t.get("category"),
                "reference_status": t.get("reference_status"),
                "capabilities": t.get("capabilities", []),
            }
            for t in rows
        ])
        return EXIT_OK
    width = max((len(t["id"]) for t in rows), default=4)
    for t in rows:
        tag = "" if t.get("reference_status") == "validated" else "  (fixture)"
        print(f"  {t['id']:<{width}}  {t['class']:<16}  {t.get('category', ''):<20}{tag}")
    return EXIT_OK


def cmd_status(reg: Registry, args) -> int:
    results = {}
    for tool_id, tool in sorted(reg.all_tools().items()):
        results[tool_id] = tool_status(reg, tool)
    if args.json:
        _print_json(results)
        return EXIT_OK
    width = max((len(k) for k in results), default=4)
    for tool_id, info in results.items():
        print(f"  {tool_id:<{width}}  {info['state']:<12}  {info['via']}")
    print("\nNo secret value is shown. `NEEDS SETUP` means a credential identity would resolve it;")
    print("run `agent-skills tools inspect <id>` for the fields, or see the linked doc.")
    return EXIT_OK


def cmd_inspect(reg: Registry, args) -> int:
    tool = reg.get_tool(args.tool)
    caps = [
        {"capability": c, "action_class": reg.capabilities.get(c, {}).get("action", "?"),
         "bounded": c in tool.get("bounded_capabilities", [])}
        for c in tool.get("capabilities", [])
    ]
    status = tool_status(reg, tool)
    view = {
        "id": tool["id"],
        "class": tool["class"],
        "category": tool.get("category"),
        "summary": tool.get("summary"),
        "reference_status": tool.get("reference_status"),
        "delegates_to": tool.get("delegates_to"),
        "capabilities": caps,
        "transports": tool.get("transports", []),
        "auth_service": tool.get("auth_service"),
        "docs": tool.get("docs"),
        "status": status,
        "notes": tool.get("notes"),
    }
    if args.json:
        _print_json(view)
        return EXIT_OK
    print(f"{tool['id']}  —  {tool.get('summary', '')}")
    print(f"  class     : {tool['class']}  ({tool.get('category')})")
    print(f"  status    : {status['state']}  via {status['via']}")
    if tool.get("reference_status") != "validated":
        print("  note      : FIXTURE — not claimed as supported; present to prove extensibility")
    if tool.get("delegates_to"):
        print(f"  delegates : transport shared with `{tool['delegates_to']}`")
    print("  capabilities:")
    for c in caps:
        flag = "  [bounded read -> context pack]" if c["bounded"] else ""
        print(f"      {c['capability']:<28} {c['action_class']:<12}{flag}")
    print("  transports (in preference order):")
    for t in tool.get("transports", []):
        extra = ""
        if t.get("command"):
            extra = f" ({t['command']})"
        elif t.get("hint"):
            extra = f" (hint: {t['hint']})"
        elif t.get("kind") in ("profile", "api"):
            extra = f" (access: {t.get('auth_service') or tool.get('auth_service')}, fields: {','.join(t.get('require', []))})"
        print(f"      {t['kind']}{extra}")
    print(f"  docs      : {tool.get('docs')}")
    if tool.get("notes"):
        print(f"  notes     : {tool['notes']}")
    return EXIT_OK


def cmd_classify(reg: Registry, args) -> int:
    tool = reg.get_tool(args.tool)
    if args.capability not in tool.get("capabilities", []):
        print(f"tools: {tool['id']} does not declare {args.capability}", file=sys.stderr)
        return EXIT_USAGE
    action = reg.action_of(args.capability)
    if args.json:
        _print_json({"tool": tool["id"], "capability": args.capability, "action_class": action})
    else:
        print(action)
    return EXIT_OK


def cmd_resolve(reg: Registry, args) -> int:
    tool = reg.get_tool(args.tool)
    result, code = resolve_capability(reg, tool, args.capability, args.allow_write)
    if args.json:
        _print_json(result)
        return code
    print(f"tool        : {result.get('tool')}  ({result.get('class', '')})")
    print(f"capability  : {result.get('capability')}  [{result.get('action_class', '?')}]")
    print(f"status      : {result.get('status')}")
    if result.get("via"):
        auth = "  (auth via Access Resolver)" if result.get("needs_auth") else ""
        print(f"resolved via: {result['via']}{auth}")
    for step in result.get("steps", []):
        print(f"  - {step['transport']:<14} {step['outcome']:<12} {step.get('detail', '')}")
        if step.get("missing_fields"):
            print(f"      missing: {', '.join(step['missing_fields'])}  (service: {step.get('auth_service')})")
    if result.get("detail"):
        print(f"note        : {result['detail']}")
    if result.get("bounded_note"):
        print(f"bounded     : {result['bounded_note']}")
    if result.get("status") == "resolved":
        print("reminder    : resolution is not authorization. The Execution Guard gates the command that runs.")
    return code


def cmd_capabilities(reg: Registry, args) -> int:
    if args.json:
        _print_json({"action_classes": reg.action_classes, "capabilities": reg.capabilities})
        return EXIT_OK
    families: dict = {}
    for cap, entry in reg.capabilities.items():
        family = cap.split(".", 1)[0]
        families.setdefault(family, []).append((cap, entry.get("action", "?")))
    for family in sorted(families):
        print(f"{family}.*")
        for cap, action in families[family]:
            print(f"    {cap:<30} {action}")
    print("\nAction classes: READ < WRITE < ELEVATED < DESTRUCTIVE.")
    print("This vocabulary is a candidate for freezing at 1.0 — see docs/engineering-tool-capabilities.md.")
    return EXIT_OK


def cmd_classes(reg: Registry, args) -> int:
    if args.json:
        _print_json({"classes": reg.classes, "resolution_order": reg.resolution_order})
        return EXIT_OK
    for name, info in reg.classes.items():
        print(f"{name}")
        print(f"    {info.get('summary', '')}")
        if info.get("examples"):
            print(f"    e.g. {', '.join(info['examples'])}")
    print("\nTransport resolution order:")
    for row in reg.resolution_order:
        auth = "  (needs a credential)" if reg.transport_needs_auth.get(row.get("transport")) else ""
        print(f"  {row.get('rank')}. {row.get('transport'):<14} {row.get('summary', '')}{auth}")
    return EXIT_OK


def cmd_doctor(reg: Registry, args) -> int:
    problems = integrity_problems(reg)
    tools = reg.tools
    validated = [t for t in tools.values() if t.get("reference_status") == "validated"]
    payload = {
        "data_dir": str(reg.base),
        "reference_tools": len(validated),
        "fixture_tools": len(reg.fixtures),
        "capabilities": len(reg.capabilities),
        "classes": list(reg.classes),
        "problems": problems,
    }
    if args.json:
        _print_json(payload)
        return EXIT_OK if not problems else EXIT_UNRESOLVED
    print(f"engineering tool framework — data at {reg.base}")
    print(f"  reference tools : {len(validated)}")
    print(f"  fixtures        : {len(reg.fixtures)}  (not claimed as supported)")
    print(f"  capabilities    : {len(reg.capabilities)} across {len({c.split('.',1)[0] for c in reg.capabilities})} families")
    print(f"  tool classes    : {', '.join(reg.classes)}")
    if problems:
        print(f"\n  {len(problems)} integrity problem(s):")
        for p in problems:
            print(f"    - {p}")
        return EXIT_UNRESOLVED
    print("\n  integrity: OK")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agent-skills tools", description=__doc__.splitlines()[0])
    p.add_argument("--include-fixtures", action="store_true",
                   help="include the extensibility fixtures (gitlab, gcp, mysql, newrelic) in list/status")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("list", help="list defined engineering tools")
    sp.add_argument("--class", dest="tool_class", help="filter by tool class")
    sp.add_argument("--category", help="filter by category")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("status", help="per-tool availability on this machine (no secrets)")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("inspect", help="full detail for one tool")
    sp.add_argument("tool")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_inspect)

    sp = sub.add_parser("classify", help="print the action class of a capability")
    sp.add_argument("tool")
    sp.add_argument("capability")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_classify)

    sp = sub.add_parser("resolve", help="walk the transport order for one capability")
    sp.add_argument("tool")
    sp.add_argument("--capability", required=True)
    sp.add_argument("--allow-write", action="store_true",
                    help="permit resolving a WRITE/ELEVATED capability (still Guard-gated)")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_resolve)

    sp = sub.add_parser("capabilities", help="the provider-neutral capability vocabulary")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_capabilities)

    sp = sub.add_parser("classes", help="the tool classes and transport resolution order")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_classes)

    sp = sub.add_parser("doctor", help="registry integrity and coherence checks")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_doctor)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    reg = Registry(include_fixtures=getattr(args, "include_fixtures", False))
    return args.func(reg, args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print(exc.code, file=sys.stderr)
            sys.exit(EXIT_USAGE)
        raise
    except KeyboardInterrupt:
        sys.exit(130)
