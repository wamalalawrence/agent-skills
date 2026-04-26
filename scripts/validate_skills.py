#!/usr/bin/env python3
"""Validate every SKILL.md in this repo against the Agent Skills spec.

Spec reference: https://agentskills.io/specification

Required frontmatter fields:
  - name: 1-64 chars, lowercase a-z + digits + hyphens, no leading/trailing/consecutive hyphen,
          must equal the parent directory name.
  - description: 1-1024 chars, non-empty.

Optional fields validated when present:
  - license: non-empty string.
  - compatibility: <= 500 chars.
  - metadata: mapping of string keys -> string/number/bool values.

Exit code 0 on success, 1 on any failure (errors printed to stderr).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def parse_frontmatter(text: str) -> dict[str, object] | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    block = text[4:end]
    # Minimal YAML parser sufficient for our SKILL.md style: top-level scalar
    # values (possibly quoted) and a single nested `metadata:` mapping. For
    # anything fancier we fall back to PyYAML if available.
    try:
        import yaml  # type: ignore

        return yaml.safe_load(block) or {}
    except Exception:
        return _hand_parse(block)


def _strip_quotes(value: str) -> str:
    if (value.startswith("'") and value.endswith("'")) or (
        value.startswith('"') and value.endswith('"')
    ):
        return value[1:-1]
    return value


def _hand_parse(block: str) -> dict[str, object]:
    result: dict[str, object] = {}
    lines = block.splitlines()
    i = 0

    while i < len(lines):
        raw = lines[i]
        if not raw.strip() or raw.lstrip().startswith("#"):
            i += 1
            continue
        if raw.startswith(" "):
            # Stray continuation line; valid frontmatter should have been
            # consumed while handling the parent key.
            i += 1
            continue

        key, _, value = raw.partition(":")
        key = key.strip()
        value = value.strip()

        if value in {">", ">-", "|", "|-"}:
            i += 1
            scalar_lines: list[str] = []
            while i < len(lines) and (not lines[i].strip() or lines[i].startswith(" ")):
                if lines[i].strip() and not lines[i].lstrip().startswith("#"):
                    scalar_lines.append(lines[i].strip())
                i += 1
            result[key] = (
                " ".join(scalar_lines).strip()
                if value.startswith(">")
                else "\n".join(scalar_lines).strip()
            )
            continue

        if value == "":
            i += 1
            block_lines: list[str] = []
            while i < len(lines) and (not lines[i].strip() or lines[i].startswith(" ")):
                if lines[i].strip() and not lines[i].lstrip().startswith("#"):
                    block_lines.append(lines[i].strip())
                i += 1

            if not block_lines:
                result[key] = ""
                continue

            # Our SKILL.md frontmatter uses `metadata:` as a nested mapping.
            # Other blank-valued keys may be valid multi-line scalars emitted
            # by Markdown/YAML formatters.
            if all(":" in line and not line.startswith(("'", '"')) for line in block_lines):
                nested: dict[str, str] = {}
                for line in block_lines:
                    nested_key, _, nested_value = line.partition(":")
                    nested[nested_key.strip()] = _strip_quotes(nested_value.strip())
                result[key] = nested
            else:
                result[key] = _strip_quotes(" ".join(block_lines).strip())
            continue

        result[key] = _strip_quotes(value)
        i += 1

    return result


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)
    if fm is None:
        return [f"{path}: missing or malformed YAML frontmatter"]

    name = fm.get("name")
    if not isinstance(name, str) or not name:
        errors.append(f"{path}: 'name' is required and must be a non-empty string")
    else:
        if len(name) > 64:
            errors.append(f"{path}: 'name' exceeds 64 characters")
        if not NAME_RE.match(name):
            errors.append(
                f"{path}: 'name' must be lowercase a-z/0-9/hyphens, no leading/trailing/consecutive hyphens"
            )
        if name != path.parent.name:
            errors.append(
                f"{path}: 'name' ({name!r}) must match parent directory ({path.parent.name!r})"
            )

    description = fm.get("description")
    if not isinstance(description, str) or not description.strip():
        errors.append(f"{path}: 'description' is required and must be a non-empty string")
    elif len(description) > 1024:
        errors.append(f"{path}: 'description' exceeds 1024 characters ({len(description)})")

    if "license" in fm:
        license_value = fm["license"]
        if not isinstance(license_value, str) or not license_value.strip():
            errors.append(f"{path}: 'license' must be a non-empty string when present")

    if "compatibility" in fm:
        compat = fm["compatibility"]
        if not isinstance(compat, str) or not compat.strip():
            errors.append(f"{path}: 'compatibility' must be a non-empty string when present")
        elif len(compat) > 500:
            errors.append(f"{path}: 'compatibility' exceeds 500 characters ({len(compat)})")

    if "metadata" in fm:
        meta = fm["metadata"]
        if not isinstance(meta, dict):
            errors.append(f"{path}: 'metadata' must be a mapping")
        else:
            for k, v in meta.items():
                if not isinstance(k, str) or not k:
                    errors.append(f"{path}: metadata key {k!r} must be a non-empty string")
                if not isinstance(v, (str, int, float, bool)):
                    errors.append(f"{path}: metadata['{k}'] must be a scalar string/number/bool")

    return errors


def main() -> int:
    skill_files = sorted(ROOT.glob("skills/**/SKILL.md"))
    if not skill_files:
        print("error: no SKILL.md files found under skills/", file=sys.stderr)
        return 1

    all_errors: list[str] = []
    for path in skill_files:
        rel = path.relative_to(ROOT)
        errs = validate(path)
        if errs:
            all_errors.extend(errs)
        else:
            print(f"ok   {rel}")

    if all_errors:
        print("", file=sys.stderr)
        for e in all_errors:
            print(f"FAIL {e}", file=sys.stderr)
        print(f"\n{len(all_errors)} validation error(s) across {len(skill_files)} skill file(s)", file=sys.stderr)
        return 1

    print(f"\nAll {len(skill_files)} SKILL.md files are spec-compliant.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
