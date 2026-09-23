#!/usr/bin/env python3
"""Read a launcher script to learn what it would do, without running it.

An MCP server entry often points at a script rather than at a known package:
a wrapper someone's employer wrote that fetches a token from the keychain,
sets a few variables, and execs the real server. To Agent Skills that script
is a black box, and the incident that motivated this module was exactly that
box: a wrapper that defaulted to read-only unless a variable of its own was
set, which nothing reported.

This module opens the box statically. It never executes the script, never
sources it, and never passes it to a shell. It reads at most `MAX_BYTES`,
skips binaries, strips comments, and then looks for four things:

* the **upstream** it launches (`uvx`, `npx`, `docker run`, `pipx`, `python -m`),
  matched against the registry;
* **mode settings**: assignments to an upstream's mode keys, the condition that
  guards them, and the wrapper's own switch variable with its default;
* **credential references**: keychain, secret-service, `pass`, `op`, keyring,
  `.netrc`, files and environment variables - as locators, never values;
* **base URLs**, so the route can be matched to a system and a target.

Every conclusion is `inferred` and carries the file and line it came from, so
Wamala can show the user the evidence and ask before relying on it. A heuristic
that is silently wrong is worse than one that says what it saw.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional

import access_registry as reg
from access_hosts import looks_mode_like, looks_secret

MAX_BYTES = 64 * 1024
LAUNCHERS = (
    ("uvx", re.compile(r"(?:^|[\s\"'\[,(])uvx\b")),
    ("pipx", re.compile(r"\bpipx\s+run\b")),
    ("npx", re.compile(r"(?:^|[\s\"'\[,(])npx\b")),
    ("docker", re.compile(r"\bdocker\b[\"',\s]+run\b")),
    ("podman", re.compile(r"\bpodman\b[\"',\s]+run\b")),
    ("python-module", re.compile(r"\bpython3?\b[\"',\s]+-m\b")),
    ("node", re.compile(r"(?:^|[\s\"'\[,(])node\s")),
)
_VAR_REF = re.compile(
    r"\$\{?([A-Za-z_][A-Za-z0-9_]*)(?::?-([^}\s\"']*))?\}?"
    r"|os\.environ\.get\(\s*[\"']([A-Za-z_][A-Za-z0-9_]*)[\"'](?:\s*,\s*[\"']([^\"']*)[\"'])?"
    r"|os\.getenv\(\s*[\"']([A-Za-z_][A-Za-z0-9_]*)[\"'](?:\s*,\s*[\"']([^\"']*)[\"'])?"
    r"|os\.environ\[\s*[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']\s*\]"
)
_URL = re.compile(r"https?://[^\s\"'`;)\]}>,]+")
_TRUTHY = {"1", "true", "yes", "on", "readonly", "read-only", "read_only"}
_FALSY = {"0", "false", "no", "off", ""}


def _strip_comment(line: str) -> str:
    """Drop a trailing `#` comment that is outside quotes."""
    quote = ""
    for i, ch in enumerate(line):
        if quote:
            if ch == quote and line[i - 1] != "\\":
                quote = ""
        elif ch in ("'", '"'):
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t;"):
            # `${#VAR}` and `$#` are not comments.
            if i > 0 and line[i - 1] == "$":
                continue
            return line[:i]
    return line


def resolve_command(command: str, path_env: Optional[str] = None) -> Optional[Path]:
    if not command:
        return None
    if "/" in command or command.startswith("~"):
        candidate = Path(os.path.expanduser(command))
        return candidate if candidate.exists() else None
    found = shutil.which(command, path=path_env)
    return Path(found) if found else None


def is_user_local(path: Path) -> bool:
    home = Path(os.environ.get("HOME") or str(Path.home()))
    try:
        path.resolve().relative_to(home.resolve())
        return True
    except ValueError:
        return False


def _mode_envs(systems: Dict[str, dict]) -> Dict[str, dict]:
    """Upstream mode keys -> the rule, e.g. READ_ONLY_MODE -> {truthy: read-only}."""
    envs: Dict[str, dict] = {}
    for system in systems.values():
        for upstream in system.get("mcp_upstreams", []):
            for rule in upstream.get("mode_rules", []):
                if rule.get("env"):
                    envs[rule["env"]] = rule
    return envs


def _rule_mode(rule: dict, value: str) -> str:
    value = (value or "").strip().strip("\"'").lower()
    if "values" in rule:
        return rule["values"].get(value, "unknown")
    if rule.get("truthy"):
        if value in _TRUTHY:
            return rule.get("mode", "read-only")
        if value in _FALSY:
            return "read-write"
    return "unknown"


def _condition(lines: List[tuple], index: int, python: bool) -> Optional[dict]:
    """The guard around line `index`: {var, op, value, line, inverted}."""
    number, text = lines[index]
    candidates = []
    if "&&" in text or "||" in text or re.search(r"\bif\b", text):
        candidates.append((index, text, False))
    indent = len(text) - len(text.lstrip())
    inverted = False
    depth = 0
    for back in range(index - 1, max(-1, index - 12), -1):
        _n, prev = lines[back]
        stripped = prev.strip()
        if not stripped:
            continue
        if python:
            prev_indent = len(prev) - len(prev.lstrip())
            if prev_indent >= indent:
                continue
            if stripped.startswith("else"):
                inverted = True
                indent = prev_indent
                continue
            if re.match(r"(el)?if\b", stripped):
                candidates.append((back, prev, inverted))
                break
            break
        if re.match(r"fi\b", stripped):
            depth += 1
            continue
        if stripped.startswith("else") and depth == 0:
            inverted = True
            continue
        if re.match(r"(el)?if\b", stripped):
            if depth == 0:
                candidates.append((back, prev, inverted))
                break
            depth -= 1
    for idx, cond_text, inv in candidates:
        parsed = _parse_condition(cond_text)
        if parsed:
            parsed["line"] = lines[idx][0]
            if idx == index and "||" in cond_text and "&&" not in cond_text:
                inv = not inv  # `[ test ] || export X=...` runs when the test fails
            parsed["inverted"] = inv
            return parsed
    return None


def _parse_condition(text: str) -> Optional[dict]:
    names = []
    for m in _VAR_REF.finditer(text):
        name = next(g for g in (m.group(1), m.group(3), m.group(5), m.group(7)) if g)
        default = m.group(2) or m.group(4) or m.group(6) or ""
        if not looks_secret(name):
            names.append((name, default))
    if not names:
        return None
    name, default = names[0]
    m = re.search(r"(!=|==|=|-ne|-eq)\s*[\"']?([A-Za-z0-9_.-]*)[\"']?", text.split(name, 1)[-1])
    if m:
        op = "!=" if m.group(1) in ("!=", "-ne") else "=="
        return {"var": name, "op": op, "value": m.group(2), "default": default}
    if re.search(r"-z\s", text) or re.search(r"\bnot\s+os\.", text):
        return {"var": name, "op": "empty", "value": "", "default": default}
    if re.search(r"-n\s", text) or re.search(r"\bif\s+os\.", text):
        return {"var": name, "op": "set", "value": "", "default": default}
    return {"var": name, "op": "?", "value": "", "default": default}


def inspect_launcher(command: str, systems: Optional[Dict[str, dict]] = None,
                     path_env: Optional[str] = None) -> dict:
    systems = systems if systems is not None else reg.load_systems()
    report = {
        "command": command, "path": "", "resolved": "", "kind": "missing", "strength": "inferred",
        "user_local": False, "sha256": "", "size": 0, "truncated": False, "language": "",
        "upstream": None, "launcher": "", "system_ids": [], "mode": None, "mode_variables": [],
        "credential_refs": [], "base_urls": [], "notes": [],
    }
    path = resolve_command(command, path_env)
    if path is None:
        report["notes"].append("command not found on PATH")
        return report
    report["path"] = str(path)
    resolved = path.resolve()
    report["resolved"] = str(resolved)
    report["user_local"] = is_user_local(path)
    if not os.access(str(resolved), os.X_OK) or not resolved.is_file():
        # A launcher is an executable file. Anything else is not read at all, so
        # a host config (which a repository can supply) cannot point the
        # inspector at a key or a credentials file.
        report["kind"] = "not-executable"
        report["notes"].append("not an executable file; not read")
        return report
    try:
        size = resolved.stat().st_size
        with resolved.open("rb") as handle:
            data = handle.read(MAX_BYTES)
    except OSError as exc:
        report["kind"] = "unreadable"
        report["notes"].append("cannot read: %s" % (exc.strerror or exc))
        return report
    report["size"] = size
    report["sha256"] = hashlib.sha256(data).hexdigest()
    report["executable"] = os.access(str(resolved), os.X_OK)
    if b"\x00" in data[:8192]:
        report["kind"] = "opaque-binary"
        report["notes"].append("binary executable: its mode cannot be read statically")
        return report
    if size > MAX_BYTES:
        report["truncated"] = True
        report["notes"].append("only the first %d KB were read" % (MAX_BYTES // 1024))
    text = data.decode("utf-8", errors="replace")
    first = text.splitlines()[0] if text else ""
    python = "python" in first or resolved.suffix == ".py"
    report["language"] = "python" if python else ("shell" if ("sh" in first or not first.startswith("#!")) else first[2:].strip())
    report["kind"] = "script"
    lines = [(n, _strip_comment(raw)) for n, raw in enumerate(text.splitlines(), start=1)]
    _find_upstream(report, lines, systems)
    _find_mode(report, lines, systems, python)
    _find_credentials(report, lines)
    _find_urls(report, lines, systems)
    return report


def _flat(text: str) -> str:
    """`["security", "-s", "x"]` -> ` security  -s  x ` for argv-list scripts."""
    return re.sub(r"[\"',\[\]()]", " ", text)


def _find_upstream(report: dict, lines: List[tuple], systems: Dict[str, dict]) -> None:
    for number, text in lines:
        if not text.strip():
            continue
        for sid, system in systems.items():
            for upstream in system.get("mcp_upstreams", []):
                needles = upstream.get("match", {}).get("args_contain", [])
                if any(n in text for n in needles):
                    if report["upstream"] is None:
                        report["upstream"] = {"id": upstream["id"], "label": upstream.get("label", upstream["id"]),
                                              "line": number, "evidence": text.strip()[:160]}
                    if sid not in report["system_ids"] and report["upstream"]["id"] == upstream["id"]:
                        report["system_ids"].append(sid)
        if not report["launcher"]:
            for name, pattern in LAUNCHERS:
                if pattern.search(text):
                    report["launcher"] = name
                    break


def _find_mode(report: dict, lines: List[tuple], systems: Dict[str, dict], python: bool) -> None:
    mode_envs = _mode_envs(systems)
    variables: Dict[str, dict] = {}
    for number, text in lines:
        for m in _VAR_REF.finditer(text):
            name = next(g for g in (m.group(1), m.group(3), m.group(5), m.group(7)) if g)
            if name in mode_envs or not looks_mode_like(name):
                continue
            default = m.group(2) if m.group(2) is not None else (m.group(4) or m.group(6))
            entry = variables.setdefault(name, {"name": name, "default": None, "lines": []})
            if default is not None and entry["default"] is None:
                entry["default"] = default
            if number not in entry["lines"]:
                entry["lines"].append(number)
    report["mode_variables"] = sorted(variables.values(), key=lambda v: v["lines"][0])

    settings = []
    for index, (number, text) in enumerate(lines):
        for env, rule in mode_envs.items():
            pattern = re.compile(
                r"(?:\b%s\b\s*=\s*|[\"']%s[\"']\s*\]\s*=\s*|setdefault\(\s*[\"']%s[\"']\s*,\s*|"
                r"[\"']%s=)([\"']?)(\$\{[^}]*\}|[^\"'\s;)]*)" % ((re.escape(env),) * 4))
            m = pattern.search(text)
            if not m:
                continue
            raw_value = m.group(2)
            ref = _VAR_REF.fullmatch(raw_value) if raw_value.startswith("$") else None
            setting = {"env": env, "line": number, "evidence": text.strip()[:160]}
            if ref and ref.group(1):
                setting.update(value=None, var=ref.group(1), var_default=ref.group(2) or "")
                setting["mode"] = _rule_mode(rule, ref.group(2) or "")
            else:
                setting["value"] = raw_value
                setting["mode"] = _rule_mode(rule, raw_value)
                setting["condition"] = _condition(lines, index, python)
            settings.append(setting)
        if re.search(r"(?:^|[\s\"'])--read-only(?:[\s\"']|$)", text):
            settings.append({"env": "--read-only", "line": number, "evidence": text.strip()[:160],
                             "value": "flag", "mode": "read-only", "condition": _condition(lines, index, python)})
    report["mode_settings"] = settings
    report["mode"] = _conclude_mode(settings, variables)


def _conclude_mode(settings: List[dict], variables: Dict[str, dict]) -> Optional[dict]:
    """Turn raw settings into {default, toggle, evidence, confidence}."""
    if not settings:
        if variables:
            names = ", ".join(sorted(variables))
            return {"default": "unknown", "toggle": None, "confidence": "low",
                    "summary": "mode-like variable(s) %s are read but no upstream mode setting was found" % names,
                    "lines": sorted({ln for v in variables.values() for ln in v["lines"]})}
        return None
    for s in settings:
        if s.get("var"):
            default_mode = s["mode"]
            write_when = "false" if default_mode == "read-only" else ""
            return {"default": default_mode, "confidence": "medium", "lines": [s["line"]],
                    "toggle": {"env": s["var"], "write_when": write_when or "(see line)", "line": s["line"]},
                    "summary": "%s takes its value from %s (default %r)" % (s["env"], s["var"], s["var_default"])}
    readonly = [s for s in settings if s["mode"] == "read-only"]
    writable = [s for s in settings if s["mode"] in ("read-write", "modify")]
    guarded = [s for s in readonly if s.get("condition")]
    if readonly and not guarded:
        s = readonly[0]
        return {"default": "read-only", "toggle": None, "confidence": "medium", "lines": [s["line"]],
                "summary": "%s is set unconditionally at line %d" % (s["env"], s["line"])}
    if guarded:
        s = guarded[0]
        cond = s["condition"]
        op = cond["op"]
        if cond.get("inverted"):
            op = {"!=": "==", "==": "!=", "empty": "set", "set": "empty"}.get(op, op)
        # `op` now states when the read-only assignment runs.
        if op == "!=":
            toggle = {"env": cond["var"], "write_when": cond["value"], "line": cond["line"]}
            default = "read-write" if (cond.get("default") or "") == cond["value"] else "read-only"
        elif op == "empty":
            toggle = {"env": cond["var"], "write_when": "(any non-empty value)", "line": cond["line"]}
            default = "read-write" if cond.get("default") else "read-only"
        elif op == "==":
            toggle = {"env": cond["var"], "readonly_when": cond["value"], "line": cond["line"]}
            default = "read-only" if (cond.get("default") or "") == cond["value"] else "read-write"
        elif op == "set":
            toggle = {"env": cond["var"], "readonly_when": "(any non-empty value)", "line": cond["line"]}
            default = "read-only" if cond.get("default") else "read-write"
        else:
            return {"default": "unknown", "toggle": {"env": cond["var"], "line": cond["line"]}, "confidence": "low",
                    "lines": [s["line"], cond["line"]],
                    "summary": "%s is set under a condition on %s that could not be read" % (s["env"], cond["var"])}
        return {"default": default, "toggle": toggle, "confidence": "medium",
                "lines": sorted({s["line"], cond["line"]}),
                "summary": "%s is set to read-only unless %s" % (
                    s["env"], _describe_toggle(toggle))}
    if writable:
        s = writable[0]
        cond = s.get("condition")
        if cond and cond["op"] == "==" and not cond.get("inverted"):
            return {"default": "unknown", "confidence": "low", "lines": [s["line"], cond["line"]],
                    "toggle": {"env": cond["var"], "write_when": cond["value"], "line": cond["line"]},
                    "summary": "%s enables writes when %s=%s; the default is the upstream default" % (
                        s["env"], cond["var"], cond["value"])}
        return {"default": "read-write", "toggle": None, "confidence": "medium", "lines": [s["line"]],
                "summary": "%s is set to a writable value at line %d" % (s["env"], s["line"])}
    return {"default": "unknown", "toggle": None, "confidence": "low", "lines": [settings[0]["line"]],
            "summary": "a mode setting was found but its value could not be read"}


def _describe_toggle(toggle: dict) -> str:
    if "write_when" in toggle:
        return "%s=%s" % (toggle["env"], toggle["write_when"])
    return "%s is not %s" % (toggle["env"], toggle.get("readonly_when", "?"))


_CRED_PATTERNS = (
    ("keychain-generic", re.compile(r"\bsecurity\s+find-generic-password\b[^\n]*?\s-s\s+([^\s-][^\s]*)")),
    ("keychain-internet", re.compile(r"\bsecurity\s+find-internet-password\b[^\n]*?\s-s\s+([^\s-][^\s]*)")),
    ("secret-service", re.compile(r"\bsecret-tool\s+lookup\s+((?:[^\s|;)&]+\s+[^\s|;)&]+\s*)+)")),
    ("pass", re.compile(r"\bpass\s+show\s+([^\s|;)&]+)")),
    ("pass", re.compile(r"\$\(\s*pass\s+(?!show\b)([^\s|;)&]+)")),
    ("1password", re.compile(r"\bop\s+read\s+(op://[^\s|;)&]+)")),
    ("keyring", re.compile(r"\bkeyring\.get_password\(\s*[\"']([^\"']+)[\"']")),
    ("netrc", re.compile(r"(\.netrc)\b")),
    ("file", re.compile(r"\b(?:cat|read_text|open)\s*\(?\s*[\"']?([~$\w/.{}-]*(?:token|secret|cred|pat)[\w/.-]*)", re.I)),
)


def _find_credentials(report: dict, lines: List[tuple]) -> None:
    refs = []
    seen = set()
    for number, text in lines:
        if not text.strip():
            continue
        for kind, pattern in _CRED_PATTERNS:
            for variant in (text, _flat(text)):
                for m in pattern.finditer(variant):
                    locator = m.group(1).strip().strip("\"'")
                    if kind == "secret-service":
                        locator = " ".join(locator.split())
                    key = (kind, locator)
                    if locator and key not in seen:
                        seen.add(key)
                        refs.append({"kind": kind, "locator": locator, "line": number})
        for m in _VAR_REF.finditer(text):
            name = next(g for g in (m.group(1), m.group(3), m.group(5), m.group(7)) if g)
            if looks_secret(name) and ("env", name) not in seen:
                seen.add(("env", name))
                refs.append({"kind": "env", "locator": name, "line": number})
    report["credential_refs"] = refs


def _find_urls(report: dict, lines: List[tuple], systems: Dict[str, dict]) -> None:
    urls = []
    for number, text in lines:
        for m in _URL.finditer(text):
            value = m.group(0).rstrip(".")
            key = ""
            km = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\s*[=:]\s*[\"']?$", text[:m.start()])
            if km:
                key = km.group(1)
            urls.append({"value": value, "key": key, "line": number})
    report["base_urls"] = urls
    if not report["system_ids"]:
        for url in urls:
            for sid in reg.systems_for_hint(systems, url["key"] + " " + url["value"]):
                if sid not in report["system_ids"]:
                    report["system_ids"].append(sid)


SELF_REPORT_FLAG = "--agent-skills-capabilities"


def self_report(command: str, timeout: float = 5.0) -> dict:
    """Ask a launcher to describe itself. Only for launchers the user trusts.

    The convention is documented in docs/access/for-launcher-authors.md. This
    is the one place a launcher is executed, and the caller runs it only when
    the user's local route knowledge marks it `trusted_self_report`: an
    unknown script is never run to find out what it is.
    """
    path = resolve_command(command)
    if path is None:
        return {"error": "command not found"}
    import json
    import subprocess
    try:
        out = subprocess.run([str(path), SELF_REPORT_FLAG], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"error": "self-report failed: %s" % exc}
    if out.returncode != 0:
        return {"error": "the launcher does not support %s (exit %d)" % (SELF_REPORT_FLAG, out.returncode)}
    try:
        data = json.loads(out.stdout[:MAX_BYTES].decode("utf-8", errors="replace"))
    except ValueError:
        return {"error": "self-report was not JSON"}
    if not isinstance(data, dict) or data.get("mode") not in ("read-only", "read-write", "modify"):
        return {"error": "self-report has no usable mode"}
    keep = ("mode", "mode_source", "systems", "enabled_tools", "toolsets", "scope_filters", "deployment",
            "credential_source")
    return {k: data[k] for k in keep if k in data}


def render(report: dict) -> str:
    out = ["Launcher inspection: %s" % report["command"]]
    if report["kind"] == "missing":
        out.append("  not found: %s" % "; ".join(report["notes"]))
        return "\n".join(out)
    out.append("  file      %s%s" % (report["resolved"], "  (user-local)" if report["user_local"] else ""))
    out.append("  kind      %s%s" % (report["kind"], " (%s)" % report["language"] if report["language"] else ""))
    if report["kind"] != "script":
        for note in report["notes"]:
            out.append("  note      %s" % note)
        return "\n".join(out)
    up = report["upstream"]
    out.append("  upstream  %s" % ("%s via %s (line %d)" % (up["label"], report["launcher"] or "?", up["line"])
                                   if up else "not recognised (launcher: %s)" % (report["launcher"] or "none")))
    if report["system_ids"]:
        out.append("  systems   %s" % ", ".join(report["system_ids"]))
    mode = report["mode"]
    if mode:
        out.append("  mode      default %s; %s  [inferred: lines %s]" % (
            mode["default"], mode["summary"], ", ".join(str(n) for n in mode["lines"])))
    else:
        out.append("  mode      no mode setting found  [unknown]")
    for var in report["mode_variables"]:
        out.append("  variable  %s (default %r, lines %s)" % (
            var["name"], var["default"] if var["default"] is not None else "unset",
            ", ".join(str(n) for n in var["lines"])))
    for ref in report["credential_refs"]:
        out.append("  credential %s %s (line %d) - locator only, never read" % (ref["kind"], ref["locator"], ref["line"]))
    for url in report["base_urls"][:5]:
        out.append("  url       %s%s (line %d)" % (url["value"], " as %s" % url["key"] if url["key"] else "", url["line"]))
    for note in report["notes"]:
        out.append("  note      %s" % note)
    out.append("  All of this is inferred from reading the file. The script was not run.")
    return "\n".join(out)
