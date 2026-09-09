#!/usr/bin/env python3
"""Host adapters for Execution Guard: install, verify, uninstall, doctor.

Every adapter here does the same three things — register a pre-execution hook,
prove it is registered, remove it again — against a host that spells all three
differently. None of them contains a rule. The decision comes from
`scripts/guard.py`, so Cursor and Claude Code cannot drift into disagreeing
about what `rm -rf /` means.

The hard constraint on this file is that it edits configuration files the user
owns and did not create. Four things follow, and each is enforced rather than
intended:

  * **Never overwrite.** A host's config is read, merged, and written back. An
    unrelated hook that was already there survives, and a first modification
    leaves a `.agent-skills-guard.bak` beside the file.
  * **Own only what we wrote.** Ownership is decided by the command signature
    `guard check-tool --host`, which nothing else produces. Uninstall removes
    exactly those entries and nothing else, even entries that look similar.
  * **Idempotent.** Installing twice produces one registration. A hook that
    fires twice is not twice as safe; it is twice as slow and prints the denial
    twice.
  * **Visible.** Security-relevant IDE configuration is never changed silently:
    install prints the file, the event, and the exact command it wrote, and
    `--dry-run` shows all of that without writing.

Enforcement levels come from `lib/guard.registry`, which is data. `enforced` is
only ever claimed for a host with a documented blocking contract.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# The substring that marks a hook entry as ours. Nothing else writes it, which
# is what makes removal safe without a manifest to consult.
SIGNATURE = "guard check-tool --host"

MANIFEST_SCHEMA = "agent-skills.guard-install/v1"

ENFORCED = "enforced"
PARTIAL = "partial"
ADVISORY = "advisory"
UNAVAILABLE = "unavailable"


@dataclass
class HostRow:
    identifier: str
    label: str
    enforcement: str
    mechanism: str
    config_path: str
    detect_path: str
    notes: str

    @property
    def absolute_config(self) -> Path | None:
        if self.config_path == "-":
            return None
        return Path.home() / self.config_path

    @property
    def detected(self) -> bool:
        if self.detect_path == "-":
            return False
        return (Path.home() / self.detect_path).exists()


@dataclass
class InstallResult:
    host: str
    status: str
    detail: str
    path: str | None = None
    entries: list[str] = field(default_factory=list)


def registry_path() -> Path:
    here = Path(__file__).resolve().parent
    return here.parent / "lib" / "guard.registry"


def read_registry() -> list[HostRow]:
    path = registry_path()
    rows: list[HostRow] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return rows
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|")
        if len(parts) < 7:
            continue
        rows.append(HostRow(*[part.strip() for part in parts[:7]]))
    return rows


def launcher_command(host: str) -> str:
    """The exact command a hook runs.

    An absolute path is written rather than the bare `agent-skills` name: a
    host may spawn hooks with a PATH that does not include the user's
    `~/.local/bin`, and a hook that cannot start is a hook that does not
    protect anything.
    """
    home = os.environ.get("AGENT_SKILLS_HOME") or str(Path.home() / ".agent-skills")
    launcher = Path(home) / "bin" / "agent-skills"
    if not launcher.exists():
        fallback = shutil.which("agent-skills")
        if fallback:
            launcher = Path(fallback)
    return '"%s" guard check-tool --host %s' % (launcher, host)


def config_dir() -> str:
    explicit = os.environ.get("AGENT_SKILLS_CONFIG_DIR")
    if explicit:
        return explicit
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return os.path.join(xdg, "agent-skills")
    return os.path.join(os.path.expanduser("~"), ".config", "agent-skills")


def manifest_path() -> Path:
    return Path(config_dir()) / "guard" / "hosts.json"


def read_manifest() -> dict:
    path = manifest_path()
    if not path.is_file():
        return {"schema": MANIFEST_SCHEMA, "hosts": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema": MANIFEST_SCHEMA, "hosts": {}}
    if not isinstance(data, dict) or "hosts" not in data:
        return {"schema": MANIFEST_SCHEMA, "hosts": {}}
    return data


def write_manifest(data: dict) -> None:
    path = manifest_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(path.parent, 0o700)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.chmod(path, 0o600)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------
def _read_json_file(path: Path) -> tuple[dict, str | None]:
    if not path.exists():
        return {}, None
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {}, "could not read %s: %s" % (path, exc)
    if not raw.strip():
        return {}, None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {}, (
            "%s is not valid JSON (%s); refusing to modify it. Fix the file and "
            "re-run." % (path, exc)
        )
    if not isinstance(data, dict):
        return {}, "%s does not contain a JSON object; refusing to modify it" % path
    return data, None


def _write_json_file(path: Path, data: dict, backup: bool) -> str | None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if backup and path.exists():
            backup_path = path.with_name(path.name + ".agent-skills-guard.bak")
            if not backup_path.exists():
                shutil.copy2(path, backup_path)
        tmp = path.with_name(path.name + ".agent-skills-guard.tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        return "could not write %s: %s" % (path, exc)
    return None


def _is_ours(entry: object) -> bool:
    """True only for an entry this project wrote."""
    return SIGNATURE in json.dumps(entry)


# ---------------------------------------------------------------------------
# Claude Code and Codex — the same hook shape
# ---------------------------------------------------------------------------
CLAUDE_MATCHERS = ("Bash|Edit|Write|MultiEdit|NotebookEdit", "mcp__.*")
CODEX_MATCHERS = ("Bash|apply_patch|local_shell", "mcp__.*")


def _claude_entries(host: str, matchers: tuple[str, ...]) -> list[dict]:
    command = launcher_command(host)
    return [
        {
            "matcher": matcher,
            "hooks": [
                {
                    "type": "command",
                    "command": command,
                    "timeout": 15,
                }
            ],
        }
        for matcher in matchers
    ]


def install_claude_shape(row: HostRow, dry_run: bool) -> InstallResult:
    path = row.absolute_config
    if path is None:
        return InstallResult(row.identifier, "skipped", "no config path for this host")
    data, error = _read_json_file(path)
    if error:
        return InstallResult(row.identifier, "failed", error, str(path))

    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        return InstallResult(
            row.identifier, "failed",
            "%s has a 'hooks' key that is not an object; refusing to modify it" % path,
            str(path),
        )
    events = hooks.setdefault("PreToolUse", [])
    if not isinstance(events, list):
        return InstallResult(
            row.identifier, "failed",
            "%s has a 'hooks.PreToolUse' key that is not a list; refusing to modify it"
            % path,
            str(path),
        )

    matchers = CODEX_MATCHERS if row.identifier == "codex" else CLAUDE_MATCHERS
    wanted = _claude_entries(row.identifier, matchers)
    existing_ours = [entry for entry in events if _is_ours(entry)]
    foreign = len(events) - len(existing_ours)

    if existing_ours == wanted:
        return InstallResult(
            row.identifier, "current",
            "already registered (%d unrelated PreToolUse entr%s preserved)"
            % (foreign, "y" if foreign == 1 else "ies"),
            str(path),
            [entry["matcher"] for entry in wanted],
        )

    if dry_run:
        return InstallResult(
            row.identifier, "would-install",
            "would add %d PreToolUse entr%s to %s, preserving %d existing"
            % (len(wanted), "y" if len(wanted) == 1 else "ies", path, foreign),
            str(path),
            [entry["matcher"] for entry in wanted],
        )

    hooks["PreToolUse"] = [entry for entry in events if not _is_ours(entry)] + wanted
    error = _write_json_file(path, data, backup=True)
    if error:
        return InstallResult(row.identifier, "failed", error, str(path))
    return InstallResult(
        row.identifier, "installed",
        "registered %d PreToolUse entr%s (%d unrelated entr%s preserved)"
        % (len(wanted), "y" if len(wanted) == 1 else "ies",
           foreign, "y" if foreign == 1 else "ies"),
        str(path),
        [entry["matcher"] for entry in wanted],
    )


def uninstall_claude_shape(row: HostRow, dry_run: bool) -> InstallResult:
    path = row.absolute_config
    if path is None or not path.exists():
        return InstallResult(row.identifier, "absent", "nothing registered")
    data, error = _read_json_file(path)
    if error:
        return InstallResult(row.identifier, "failed", error, str(path))
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return InstallResult(row.identifier, "absent", "nothing registered", str(path))
    events = hooks.get("PreToolUse")
    if not isinstance(events, list):
        return InstallResult(row.identifier, "absent", "nothing registered", str(path))
    kept = [entry for entry in events if not _is_ours(entry)]
    removed = len(events) - len(kept)
    if removed == 0:
        return InstallResult(row.identifier, "absent", "nothing of ours to remove", str(path))
    if dry_run:
        return InstallResult(
            row.identifier, "would-remove",
            "would remove %d entr%s and keep %d"
            % (removed, "y" if removed == 1 else "ies", len(kept)),
            str(path),
        )
    if kept:
        hooks["PreToolUse"] = kept
    else:
        hooks.pop("PreToolUse", None)
        if not hooks:
            data.pop("hooks", None)
    error = _write_json_file(path, data, backup=False)
    if error:
        return InstallResult(row.identifier, "failed", error, str(path))
    return InstallResult(
        row.identifier, "removed",
        "removed %d entr%s, kept %d unrelated"
        % (removed, "y" if removed == 1 else "ies", len(kept)),
        str(path),
    )


# ---------------------------------------------------------------------------
# Cursor
# ---------------------------------------------------------------------------
CURSOR_EVENTS = ("beforeShellExecution", "beforeMCPExecution")


def _cursor_entry() -> dict:
    return {
        "command": launcher_command("cursor"),
        # A hook that crashes or times out must block, not wave the command
        # through. This is the host's own switch for that; it is the reason
        # Cursor is listed as `enforced` rather than best-effort.
        "failClosed": True,
    }


def install_cursor(row: HostRow, dry_run: bool) -> InstallResult:
    path = row.absolute_config
    if path is None:
        return InstallResult(row.identifier, "skipped", "no config path for this host")
    data, error = _read_json_file(path)
    if error:
        return InstallResult(row.identifier, "failed", error, str(path))

    data.setdefault("version", 1)
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        return InstallResult(
            row.identifier, "failed",
            "%s has a 'hooks' key that is not an object; refusing to modify it" % path,
            str(path),
        )

    entry = _cursor_entry()
    changed = False
    preserved = 0
    for event in CURSOR_EVENTS:
        listeners = hooks.setdefault(event, [])
        if not isinstance(listeners, list):
            return InstallResult(
                row.identifier, "failed",
                "%s has a '%s' key that is not a list; refusing to modify it"
                % (path, event),
                str(path),
            )
        ours = [item for item in listeners if _is_ours(item)]
        preserved += len(listeners) - len(ours)
        if ours != [entry]:
            changed = True
            if not dry_run:
                hooks[event] = [item for item in listeners if not _is_ours(item)] + [entry]

    if not changed:
        return InstallResult(
            row.identifier, "current",
            "already registered on %s (%d unrelated hook(s) preserved)"
            % (" and ".join(CURSOR_EVENTS), preserved),
            str(path),
            list(CURSOR_EVENTS),
        )
    if dry_run:
        return InstallResult(
            row.identifier, "would-install",
            "would register on %s in %s, preserving %d unrelated hook(s)"
            % (" and ".join(CURSOR_EVENTS), path, preserved),
            str(path),
            list(CURSOR_EVENTS),
        )
    error = _write_json_file(path, data, backup=True)
    if error:
        return InstallResult(row.identifier, "failed", error, str(path))
    return InstallResult(
        row.identifier, "installed",
        "registered on %s with failClosed (%d unrelated hook(s) preserved)"
        % (" and ".join(CURSOR_EVENTS), preserved),
        str(path),
        list(CURSOR_EVENTS),
    )


def uninstall_cursor(row: HostRow, dry_run: bool) -> InstallResult:
    path = row.absolute_config
    if path is None or not path.exists():
        return InstallResult(row.identifier, "absent", "nothing registered")
    data, error = _read_json_file(path)
    if error:
        return InstallResult(row.identifier, "failed", error, str(path))
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return InstallResult(row.identifier, "absent", "nothing registered", str(path))
    removed = 0
    kept_total = 0
    for event in CURSOR_EVENTS:
        listeners = hooks.get(event)
        if not isinstance(listeners, list):
            continue
        kept = [item for item in listeners if not _is_ours(item)]
        removed += len(listeners) - len(kept)
        kept_total += len(kept)
        if not dry_run:
            if kept:
                hooks[event] = kept
            else:
                hooks.pop(event, None)
    if removed == 0:
        return InstallResult(row.identifier, "absent", "nothing of ours to remove", str(path))
    if dry_run:
        return InstallResult(
            row.identifier, "would-remove", "would remove %d hook(s)" % removed, str(path)
        )
    if not hooks:
        data.pop("hooks", None)
    error = _write_json_file(path, data, backup=False)
    if error:
        return InstallResult(row.identifier, "failed", error, str(path))
    return InstallResult(
        row.identifier, "removed",
        "removed %d hook(s), kept %d unrelated" % (removed, kept_total),
        str(path),
    )


# ---------------------------------------------------------------------------
# Kiro — its own file, so nothing of the user's is ever in the same document
# ---------------------------------------------------------------------------
def _kiro_document() -> dict:
    return {
        "version": "v1",
        "hooks": [
            {
                "name": "agent-skills: execution guard",
                "description": (
                    "Deterministic pre-execution check. Blocks destructive commands "
                    "before they run. See docs/execution-guard.md."
                ),
                "trigger": "preToolUse",
                "enabled": True,
                "timeout": 15,
                "action": {
                    "type": "command",
                    "command": launcher_command("kiro"),
                },
            }
        ],
    }


def install_kiro(row: HostRow, dry_run: bool) -> InstallResult:
    path = row.absolute_config
    if path is None:
        return InstallResult(row.identifier, "skipped", "no config path for this host")
    wanted = _kiro_document()
    if path.exists():
        data, error = _read_json_file(path)
        if error:
            return InstallResult(row.identifier, "failed", error, str(path))
        if data and not _is_ours(data):
            return InstallResult(
                row.identifier, "conflict",
                "%s exists and was not written by agent-skills; left alone" % path,
                str(path),
            )
        if data == wanted:
            return InstallResult(
                row.identifier, "current", "already registered", str(path), ["preToolUse"]
            )
    if dry_run:
        return InstallResult(
            row.identifier, "would-install",
            "would write a preToolUse hook to %s" % path, str(path), ["preToolUse"],
        )
    error = _write_json_file(path, wanted, backup=True)
    if error:
        return InstallResult(row.identifier, "failed", error, str(path))
    return InstallResult(
        row.identifier, "installed", "registered a preToolUse hook", str(path), ["preToolUse"]
    )


def uninstall_kiro(row: HostRow, dry_run: bool) -> InstallResult:
    path = row.absolute_config
    if path is None or not path.exists():
        return InstallResult(row.identifier, "absent", "nothing registered")
    data, error = _read_json_file(path)
    if error:
        return InstallResult(row.identifier, "failed", error, str(path))
    if not _is_ours(data):
        return InstallResult(
            row.identifier, "absent",
            "%s was not written by agent-skills; left alone" % path, str(path),
        )
    if dry_run:
        return InstallResult(
            row.identifier, "would-remove", "would remove %s" % path, str(path)
        )
    try:
        path.unlink()
    except OSError as exc:
        return InstallResult(row.identifier, "failed", str(exc), str(path))
    return InstallResult(row.identifier, "removed", "removed %s" % path, str(path))


ADAPTERS = {
    "claude-code": (install_claude_shape, uninstall_claude_shape),
    "codex": (install_claude_shape, uninstall_claude_shape),
    "cursor": (install_cursor, uninstall_cursor),
    "kiro": (install_kiro, uninstall_kiro),
}


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
def registration_state(row: HostRow) -> str:
    """`registered`, `not-registered`, or `not-applicable` for one host."""
    if row.identifier not in ADAPTERS:
        return "not-applicable"
    path = row.absolute_config
    if path is None or not path.exists():
        return "not-registered"
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return "not-registered"
    return "registered" if SIGNATURE in raw else "not-registered"


def status_rows() -> list[dict]:
    out: list[dict] = []
    for row in read_registry():
        state = registration_state(row)
        if row.enforcement == ENFORCED:
            effective = ENFORCED if state == "registered" else "available"
        else:
            effective = row.enforcement
        out.append({
            "host": row.identifier,
            "label": row.label,
            "capability": row.enforcement,
            "state": state,
            "effective": effective,
            "mechanism": row.mechanism,
            "config_path": str(row.absolute_config) if row.absolute_config else None,
            "detected": row.detected,
            "notes": row.notes,
        })
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _selected(rows: list[HostRow], names: str | None) -> list[HostRow]:
    if not names:
        return rows
    wanted = {name.strip() for name in names.split(",") if name.strip()}
    return [row for row in rows if row.identifier in wanted]


def _record_install(results: list[InstallResult]) -> None:
    manifest = read_manifest()
    hosts = manifest.setdefault("hosts", {})
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for result in results:
        if result.status in ("installed", "current"):
            hosts[result.host] = {
                "path": result.path,
                "entries": result.entries,
                "signature": SIGNATURE,
                "installed_at": stamp,
            }
        elif result.status == "removed":
            hosts.pop(result.host, None)
    manifest["schema"] = MANIFEST_SCHEMA
    write_manifest(manifest)


def cmd_install(args: argparse.Namespace) -> int:
    rows = _selected(read_registry(), args.hosts)
    results: list[InstallResult] = []
    sys.stdout.write("Execution Guard: host integration\n\n")
    for row in rows:
        if row.identifier not in ADAPTERS:
            sys.stdout.write(
                "  --    %-28s %s (%s); wrapper mode only\n"
                % (row.label, row.enforcement, row.mechanism)
            )
            continue
        if not args.all_hosts and not args.hosts and not row.detected:
            sys.stdout.write("  --    %-28s not detected on this machine\n" % row.label)
            continue
        install, _ = ADAPTERS[row.identifier]
        result = install(row, args.dry_run)
        results.append(result)
        marker = {
            "installed": "ok   ", "current": "ok   ", "would-install": "plan ",
            "failed": "FAIL ", "conflict": "WARN ", "skipped": "--   ",
        }.get(result.status, "--   ")
        sys.stdout.write("  %s %-28s %s\n" % (marker, row.label, result.detail))
        if result.path and result.status in ("installed", "would-install"):
            sys.stdout.write("        file:    %s\n" % result.path)
            sys.stdout.write("        command: %s\n" % launcher_command(row.identifier))

    if not args.dry_run:
        _record_install(results)

    failed = [result for result in results if result.status == "failed"]
    sys.stdout.write("\n")
    if args.dry_run:
        sys.stdout.write("Dry run: nothing was written.\n")
    else:
        sys.stdout.write(
            "Verify with: agent-skills guard verify\n"
            "Remove with: agent-skills guard uninstall\n"
        )
    sys.stdout.write(
        "Unrelated hooks in these files were preserved. A backup of each modified "
        "file is beside it as <name>.agent-skills-guard.bak.\n"
    )
    return 1 if failed else 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    rows = _selected(read_registry(), args.hosts)
    results: list[InstallResult] = []
    sys.stdout.write("Execution Guard: removing agent-skills-owned hooks\n\n")
    for row in rows:
        if row.identifier not in ADAPTERS:
            continue
        _, uninstall = ADAPTERS[row.identifier]
        result = uninstall(row, args.dry_run)
        results.append(result)
        marker = {
            "removed": "ok   ", "absent": "--   ", "would-remove": "plan ",
            "failed": "FAIL ",
        }.get(result.status, "--   ")
        sys.stdout.write("  %s %-28s %s\n" % (marker, row.label, result.detail))
    if not args.dry_run:
        _record_install(results)
    sys.stdout.write("\nOnly entries carrying the agent-skills signature were touched.\n")
    return 1 if any(r.status == "failed" for r in results) else 0


def cmd_verify(args: argparse.Namespace) -> int:
    rows = status_rows()
    if args.format == "json":
        sys.stdout.write(json.dumps({"hosts": rows}, indent=2) + "\n")
        return 0
    problems = 0
    sys.stdout.write("Execution Guard: registration check\n\n")
    for row in rows:
        if row["capability"] != ENFORCED:
            sys.stdout.write(
                "  --    %-28s %s (%s)\n" % (row["label"], row["capability"], row["mechanism"])
            )
            continue
        if row["state"] == "registered":
            sys.stdout.write(
                "  ok    %-28s enforced via %s\n" % (row["label"], row["mechanism"])
            )
        elif row["detected"]:
            sys.stdout.write(
                "  WARN  %-28s detected but not registered; run: "
                "agent-skills guard install\n" % row["label"]
            )
            problems += 1
        else:
            sys.stdout.write("  --    %-28s not installed on this machine\n" % row["label"])
    manifest = read_manifest()
    sys.stdout.write("\nOwnership manifest: %s\n" % manifest_path())
    sys.stdout.write("Recorded hosts: %s\n" % (", ".join(sorted(manifest.get("hosts", {}))) or "none"))
    return 1 if problems else 0


def cmd_doctor(args: argparse.Namespace) -> int:
    rows = status_rows()
    if args.format == "json":
        sys.stdout.write(json.dumps({"hosts": rows}, indent=2) + "\n")
        return 0
    sys.stdout.write("Execution Guard\n\n")
    for row in rows:
        sys.stdout.write(
            "  %-28s %-12s %s\n" % (row["label"], row["effective"].upper(), row["mechanism"])
        )
    sys.stdout.write("\n")
    sys.stdout.write(
        "  ENFORCED   the host asks the guard before the tool call and honours the answer\n"
        "  AVAILABLE  the host can enforce, but the hook is not registered here yet\n"
        "  PARTIAL    static deny rules only; the host cannot consult the guard\n"
        "  ADVISORY   no pre-execution interception point; use `agent-skills guard run`\n"
    )
    if args.verbose:
        sys.stdout.write("\nDetail\n")
        for row in rows:
            sys.stdout.write("  %s\n" % row["label"])
            sys.stdout.write("    state    : %s\n" % row["state"])
            sys.stdout.write("    config   : %s\n" % (row["config_path"] or "n/a"))
            sys.stdout.write("    notes    : %s\n" % row["notes"])
    return 0


def register_cli(subparsers) -> None:
    """Attach the host-facing subcommands to `agent-skills guard`."""
    install = subparsers.add_parser("install", help="register the pre-execution hook")
    install.add_argument("--hosts", default=None, help="comma-separated host ids")
    install.add_argument("--all-hosts", action="store_true")
    install.add_argument("--dry-run", action="store_true")
    install.add_argument("--yes", action="store_true")
    install.set_defaults(func=cmd_install)

    uninstall = subparsers.add_parser("uninstall", help="remove agent-skills-owned hooks")
    uninstall.add_argument("--hosts", default=None)
    uninstall.add_argument("--dry-run", action="store_true")
    uninstall.set_defaults(func=cmd_uninstall)

    verify = subparsers.add_parser("verify", help="check hook registration")
    verify.add_argument("--format", choices=("text", "json"), default="text")
    verify.set_defaults(func=cmd_verify)

    doctor = subparsers.add_parser("doctor", help="per-host enforcement status")
    doctor.add_argument("--format", choices=("text", "json"), default="text")
    doctor.add_argument("--verbose", action="store_true")
    doctor.set_defaults(func=cmd_doctor)
