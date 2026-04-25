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


def _hand_parse(block: str) -> dict[str, object]:
    result: dict[str, object] = {}
    current_key: str | None = None
    nested: dict[str, str] | None = None
    for raw in block.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.startswith("  ") and nested is not None and current_key is not None:
            k, _, v = raw.strip().partition(":")
            nested[k.strip()] = v.strip().strip('"').strip("'")
            continue
        key, _, value = raw.partition(":")
        key = key.strip()
        value = value.strip()
        if value == "" or value == ">-":
            # Could be a nested mapping or a folded scalar; treat as nested
            # mapping when followed by indented lines, otherwise empty string.
            nested = {}
            result[key] = nested
            current_key = key
        else:
            nested = None
            current_key = key
            # Strip surrounding quotes if any.
            if (value.startswith("'") and value.endswith("'")) or (
                value.startswith('"') and value.endswith('"')
            ):
                value = value[1:-1]
            result[key] = value
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
