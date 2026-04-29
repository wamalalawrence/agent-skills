#!/usr/bin/env python3
"""Jira / Confluence auth preflight — safe discovery and validation, no secrets in output.

This script answers the question every agent should ask before declaring Jira or Confluence
inaccessible: "given the workspace's `.env`, `.env.local`, `.jira-config.yml`, and process
environment, can I construct a valid request?". It does not make a network call. It does not
prove credentials still work on the Jira side; it proves the local configuration is complete.

Exit codes:
  0  configuration is usable (Jira, plus Confluence when CONFLUENCE_HOST is set)
  1  configuration is incomplete (missing field, unresolved placeholder)
  2  setup error (workspace path missing, file unreadable, YAML malformed)

See docs/auth-discovery.md for the discovery order this script implements.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

PLACEHOLDER_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")
TOKEN_LIKE_RE = re.compile(r"^[A-Za-z0-9._\-/+=]{24,}$")
PROJECT_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,9}$")
HOST_RE = re.compile(r"^https?://[^\s/]+(/.*)?$")
SECRET_KEYS = {
    "JIRA_API_TOKEN",
    "CONFLUENCE_API_TOKEN",
    "SONAR_TOKEN",
    "GITHUB_TOKEN",
}


@dataclass
class Field:
    name: str
    value: str | None
    source: str
    secret: bool = False
    unresolved_placeholder: str | None = None


@dataclass
class Report:
    workspace_root: str
    env_file_loaded: str | None
    env_local_loaded: str | None
    jira_config_loaded: str | None
    jira: dict[str, Field] = field(default_factory=dict)
    confluence: dict[str, Field] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    jira_usable: bool = False
    confluence_usable: bool | None = None  # None = skipped


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse a `.env` file conservatively. No shell expansion, no command substitution."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SetupError(f"could not read {path}: {exc}") from exc

    multiline_key: str | None = None
    multiline_quote: str | None = None
    multiline_buffer: list[str] = []

    for raw_line in text.splitlines():
        if multiline_key is not None:
            assert multiline_quote is not None
            if multiline_quote in raw_line:
                end = raw_line.index(multiline_quote)
                multiline_buffer.append(raw_line[:end])
                values[multiline_key] = "\n".join(multiline_buffer)
                multiline_key = None
                multiline_quote = None
                multiline_buffer = []
            else:
                multiline_buffer.append(raw_line)
            continue

        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if not key.isidentifier():
            continue

        if value.startswith("'"):
            if value.endswith("'") and len(value) >= 2 and value.count("'") >= 2:
                values[key] = value[1:-1]
            else:
                multiline_key = key
                multiline_quote = "'"
                multiline_buffer = [value[1:]]
        elif value.startswith('"'):
            if value.endswith('"') and len(value) >= 2 and value.count('"') >= 2:
                values[key] = value[1:-1]
            else:
                multiline_key = key
                multiline_quote = '"'
                multiline_buffer = [value[1:]]
        else:
            comment = value.find(" #")
            if comment != -1:
                value = value[:comment].rstrip()
            values[key] = value

    if multiline_key is not None:
        # Unterminated quoted value — treat as the buffer joined.
        values[multiline_key] = "\n".join(multiline_buffer)

    return values


JIRA_CONFIG_KEY_MAP = {
    "server": "JIRA_HOST",
    "login": "JIRA_LOGIN",
    "auth_type": "JIRA_AUTH_TYPE",
}


def parse_jira_config(path: Path) -> dict[str, str]:
    """Pull a small set of keys from `.jira-config.yml` without PyYAML, mapping them to JIRA_*."""
    fields: dict[str, str] = {}
    if not path.exists():
        return fields
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SetupError(f"could not read {path}: {exc}") from exc

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("- "):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if key not in JIRA_CONFIG_KEY_MAP:
            continue
        if (value.startswith("'") and value.endswith("'")) or (
            value.startswith('"') and value.endswith('"')
        ):
            value = value[1:-1]
        comment = value.find(" #")
        if comment != -1:
            value = value[:comment].rstrip()
        fields[JIRA_CONFIG_KEY_MAP[key]] = value
    return fields


class SetupError(Exception):
    pass


def resolve_placeholder(value: str, sources: Iterable[dict[str, str]]) -> tuple[str, str | None]:
    """Resolve a `${VAR}` placeholder. Returns (resolved_value, unresolved_name_or_None)."""
    match = PLACEHOLDER_RE.fullmatch(value)
    if not match:
        return value, None
    name = match.group(1)
    for source in sources:
        if name in source and source[name]:
            return source[name], None
    return value, name


def lookup(
    name: str,
    sources: list[tuple[str, dict[str, str]]],
    secret: bool,
) -> Field:
    """Walk the discovery sources for `name`, recording where the value came from."""
    for source_name, source in sources:
        if name in source and source[name] != "":
            return Field(name=name, value=source[name], source=source_name, secret=secret)
    return Field(name=name, value=None, source="missing", secret=secret)


def redact(field_obj: Field, show_prefix: bool) -> str:
    """Render a field for human output without ever revealing a secret."""
    if field_obj.unresolved_placeholder:
        return f"unresolved placeholder ${{{field_obj.unresolved_placeholder}}}"
    if field_obj.value is None or field_obj.value == "":
        return "missing"
    if field_obj.secret:
        return "set (hidden)"
    if not show_prefix or len(field_obj.value) <= 4:
        return "set"
    return f"set: {field_obj.value[:2]}***{field_obj.value[-2:]}"


def evaluate_jira(report: Report, sources: list[tuple[str, dict[str, str]]]) -> None:
    field_specs = [
        ("JIRA_HOST", False, True),
        ("JIRA_LOGIN", False, False),
        ("JIRA_AUTH_TYPE", False, False),
        ("JIRA_API_TOKEN", True, True),
        ("JIRA_PROJECT_KEYS", False, False),
    ]
    placeholder_pool: dict[str, str] = {}
    for source_name, source in sources:
        if source_name == "jira-config":
            continue
        for key, value in source.items():
            if key not in placeholder_pool or placeholder_pool[key] == "":
                placeholder_pool[key] = value

    placeholder_sources = [placeholder_pool, dict(os.environ)]

    for name, secret, _required in field_specs:
        f = lookup(name, sources, secret)
        if f.value is not None and f.value.startswith("${"):
            new_value, unresolved = resolve_placeholder(f.value, placeholder_sources)
            if unresolved is not None:
                f.unresolved_placeholder = unresolved
                f.value = None
            else:
                f.value = new_value
        report.jira[name] = f

    host = report.jira["JIRA_HOST"]
    auth_type = report.jira["JIRA_AUTH_TYPE"]
    login = report.jira["JIRA_LOGIN"]
    token = report.jira["JIRA_API_TOKEN"]
    keys = report.jira["JIRA_PROJECT_KEYS"]

    missing: list[str] = []
    if not host.value:
        missing.append("JIRA_HOST")
    elif not HOST_RE.match(host.value):
        report.warnings.append(
            "JIRA_HOST does not look like a URL (expected `https://<host>` with no trailing slash)"
        )

    if not token.value:
        missing.append("JIRA_API_TOKEN")

    auth = (auth_type.value or "bearer").lower()
    if auth == "basic" and not login.value:
        missing.append("JIRA_LOGIN (required for basic auth)")
    if auth not in {"bearer", "basic"}:
        report.warnings.append(
            f"JIRA_AUTH_TYPE={auth_type.value!r} is not 'bearer' or 'basic'; defaulting to 'bearer'"
        )

    if keys.value:
        bad = [k for k in keys.value.split(",") if k.strip() and not PROJECT_KEY_RE.match(k.strip())]
        if bad:
            sample = bad[0].strip()
            looks_like_token = TOKEN_LIKE_RE.match(sample) is not None
            redacted_sample = (
                f"{sample[:2]}***{sample[-2:]}" if looks_like_token and len(sample) > 4 else "(redacted)"
            )
            if looks_like_token:
                report.errors.append(
                    "JIRA_PROJECT_KEYS contains a value that looks like an API token "
                    f"({redacted_sample}); rotate the leaked token and use uppercase short codes "
                    "like 'ABC,PROJ' instead"
                )
            else:
                report.warnings.append(
                    "JIRA_PROJECT_KEYS contains entries that are not Jira project key shape "
                    f"(uppercase short codes); first offender: {bad[0]!r}"
                )

    unresolved = [f.unresolved_placeholder for f in report.jira.values() if f.unresolved_placeholder]
    if unresolved:
        names = ", ".join(sorted(set(unresolved)))
        report.errors.append(
            f"unresolved placeholders in Jira config: {names} — add them to .env or process env"
        )

    if missing:
        report.errors.append(f"Jira config: missing required field(s): {', '.join(missing)}")

    report.jira_usable = not missing and not unresolved


def evaluate_confluence(report: Report, sources: list[tuple[str, dict[str, str]]]) -> None:
    field_specs = [
        ("CONFLUENCE_HOST", False),
        ("CONFLUENCE_LOGIN", False),
        ("CONFLUENCE_API_TOKEN", True),
        ("CONFLUENCE_SPACE_KEYS", False),
    ]
    for name, secret in field_specs:
        report.confluence[name] = lookup(name, sources, secret)

    host = report.confluence["CONFLUENCE_HOST"]
    if not host.value:
        report.confluence_usable = None  # explicitly skipped
        return

    if not HOST_RE.match(host.value):
        report.warnings.append(
            "CONFLUENCE_HOST does not look like a URL (expected `https://<host>` with optional `/wiki`)"
        )

    missing: list[str] = []
    token = report.confluence["CONFLUENCE_API_TOKEN"]
    if not token.value:
        missing.append("CONFLUENCE_API_TOKEN")

    if missing:
        report.errors.append(
            f"Confluence config: missing required field(s): {', '.join(missing)}"
        )
        report.confluence_usable = False
    else:
        report.confluence_usable = True


def render_text(report: Report, show_prefix: bool) -> str:
    lines: list[str] = []
    lines.append(f"workspace_root: {report.workspace_root}")
    lines.append(f".env loaded: {report.env_file_loaded or 'not found'}")
    lines.append(f".env.local loaded: {report.env_local_loaded or 'not found'}")
    lines.append(f".jira-config.yml loaded: {report.jira_config_loaded or 'not found'}")
    lines.append("")
    lines.append("Jira config:")
    for name, field_obj in report.jira.items():
        lines.append(f"  {name}: {redact(field_obj, show_prefix)} (source: {field_obj.source})")
    if report.jira_usable:
        lines.append("Result: Jira config appears usable.")
    else:
        lines.append("Result: Jira config is incomplete. See errors below.")

    lines.append("")
    lines.append("Confluence config:")
    if report.confluence_usable is None:
        lines.append("  CONFLUENCE_HOST: missing")
        lines.append("Result: Confluence skipped (host not configured).")
    else:
        for name, field_obj in report.confluence.items():
            lines.append(f"  {name}: {redact(field_obj, show_prefix)} (source: {field_obj.source})")
        if report.confluence_usable:
            lines.append("Result: Confluence config appears usable.")
        else:
            lines.append("Result: Confluence config is incomplete. See errors below.")

    if report.warnings:
        lines.append("")
        lines.append("Warnings:")
        for warning in report.warnings:
            lines.append(f"  - {warning}")
    if report.errors:
        lines.append("")
        lines.append("Errors:")
        for error in report.errors:
            lines.append(f"  - {error}")
    return "\n".join(lines)


def render_json(report: Report) -> str:
    def serialize(field_obj: Field) -> dict[str, str | None]:
        return {
            "value_present": field_obj.value not in (None, ""),
            "source": field_obj.source,
            "unresolved_placeholder": field_obj.unresolved_placeholder,
            "is_secret": field_obj.secret,
        }

    payload = {
        "workspace_root": report.workspace_root,
        "env_file_loaded": report.env_file_loaded,
        "env_local_loaded": report.env_local_loaded,
        "jira_config_loaded": report.jira_config_loaded,
        "jira": {name: serialize(f) for name, f in report.jira.items()},
        "confluence": {name: serialize(f) for name, f in report.confluence.items()},
        "jira_usable": report.jira_usable,
        "confluence_usable": report.confluence_usable,
        "warnings": report.warnings,
        "errors": report.errors,
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def build_sources(
    workspace_root: Path,
) -> tuple[list[tuple[str, dict[str, str]]], dict[str, str | None]]:
    env_file = workspace_root / ".env"
    env_local = workspace_root / ".env.local"
    jira_cfg = workspace_root / ".jira-config.yml"

    env_values = parse_env_file(env_file)
    env_local_values = parse_env_file(env_local)
    jira_cfg_values = parse_jira_config(jira_cfg)
    process_env = {k: v for k, v in os.environ.items() if k.startswith(("JIRA_", "CONFLUENCE_"))}

    sources = [
        ("env-process", process_env),
        ("env-local", env_local_values),
        ("env-file", env_values),
        ("jira-config", jira_cfg_values),
    ]
    paths = {
        "env": str(env_file) if env_file.exists() else None,
        "env_local": str(env_local) if env_local.exists() else None,
        "jira_config": str(jira_cfg) if jira_cfg.exists() else None,
    }
    return sources, paths


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Jira / Confluence auth preflight (no secrets in output, no network)."
    )
    parser.add_argument(
        "--workspace-root",
        default=os.environ.get("WORKSPACE_ROOT") or os.getcwd(),
        help="Workspace root containing .env / .jira-config.yml (default: WORKSPACE_ROOT or cwd)",
    )
    parser.add_argument(
        "--require-jira",
        action="store_true",
        help="Treat missing/incomplete Jira config as a failure (exit 1).",
    )
    parser.add_argument(
        "--require-confluence",
        action="store_true",
        help="Treat missing/incomplete Confluence config as a failure (exit 1).",
    )
    parser.add_argument("--json", action="store_true", help="Emit a JSON report.")
    parser.add_argument(
        "--show-prefix",
        action="store_true",
        help="Show 2-char prefix/suffix of non-secret values (never for tokens).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    workspace_root = Path(args.workspace_root).resolve()

    if not workspace_root.exists() or not workspace_root.is_dir():
        print(f"FAIL workspace root not found or not a directory: {workspace_root}", file=sys.stderr)
        return 2

    try:
        sources, paths = build_sources(workspace_root)
    except SetupError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 2

    report = Report(
        workspace_root=str(workspace_root),
        env_file_loaded=paths["env"],
        env_local_loaded=paths["env_local"],
        jira_config_loaded=paths["jira_config"],
    )

    evaluate_jira(report, sources)
    evaluate_confluence(report, sources)

    if args.json:
        print(render_json(report))
    else:
        print(render_text(report, show_prefix=args.show_prefix))

    incomplete = bool(report.errors)
    if args.require_jira and not report.jira_usable:
        incomplete = True
    if args.require_confluence and report.confluence_usable is not True:
        incomplete = True

    return 1 if incomplete else 0


if __name__ == "__main__":
    sys.exit(main())
