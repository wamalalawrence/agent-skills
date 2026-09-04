#!/usr/bin/env python3
"""Lightweight executable eval harness for agent-skills.

The full evals under `evals/` are prose scenarios meant for humans plus
agents. This harness adds a small, machine-checkable layer on top so a CI run
can answer: *does any eval file structurally regress between releases?*

It is intentionally minimal — it does not invoke a model. It checks that:

  1. Every eval file under `evals/` has a top-level `# ` heading.
  2. Every eval file declares some context (one of `CONTEXT_SECTIONS`) and
     some success criteria (one of `CRITERIA_SECTIONS`).
  3. Every eval file names the skill(s) it exercises in a `## Skill Under Test`
     or `## Expected Skills` section, and every name resolves to a real skill
     directory under `skills/`.
  4. Every release-scoped run under `eval-runs/<version>/` ships a
     `summary.md`.

Section names are matched exactly. An earlier version matched prefixes and kept
growing its alias lists to absorb heading drift, which hid the drift instead of
surfacing it.

A future iteration can plug a real agent runner behind `--invoke` and compare
its output against an `Expected Behavior` block. The 12 evals that carry a
`## Required Output Fields` section are the cheapest starting point: field
presence is checkable without a model judging prose.

Exit codes: 0 = pass, 1 = at least one failure.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVALS_DIR = ROOT / "evals"
EVAL_RUNS_DIR = ROOT / "eval-runs"
SKILLS_DIR = ROOT / "skills"

CONTEXT_SECTIONS = (
    "Input Context",
    "Scenario",
    "Setup",
    "Workspace fixture",
)
CRITERIA_SECTIONS = (
    "Expected Behavior",
    "Expected agent behavior",
    "Pass/Fail Checklist",
    "Pass criteria",
    "Scorecard Criteria",
    "Required Output Fields",
)
# Sections in which an eval declares which skill(s) it exercises. Names are
# written as inline code spans, e.g. "`software-engineer`, `code-reviewer`".
SKILL_DECLARATION_SECTIONS = ("Skill Under Test", "Expected Skills")
CODE_SPAN_RE = re.compile(r"`([a-z0-9-]+)`")


def discover_skills() -> set[str]:
    return {p.parent.name for p in SKILLS_DIR.glob("**/SKILL.md")}


def section_body(text: str, heading: str) -> str | None:
    """Return the body of an exact `## <heading>` section, or None if absent."""
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    return match.group(1) if match else None


def check_eval_file(path: Path, skills: set[str]) -> list[str]:
    errors: list[str] = []
    rel_path = path.relative_to(ROOT)
    text = path.read_text(encoding="utf-8")

    if not re.search(r"^#\s+\S", text, re.MULTILINE):
        errors.append(f"{rel_path}: missing top-level heading")

    headings = {
        re.sub(r"\s+", " ", m.group(1).strip())
        for m in re.finditer(r"^##\s+(.+?)\s*$", text, re.MULTILINE)
    }

    if not any(s in headings for s in CONTEXT_SECTIONS):
        errors.append(
            f"{rel_path}: missing a context section "
            f"(one of: {', '.join(CONTEXT_SECTIONS)})"
        )
    if not any(s in headings for s in CRITERIA_SECTIONS):
        errors.append(
            f"{rel_path}: missing a success-criteria section "
            f"(one of: {', '.join(CRITERIA_SECTIONS)})"
        )

    declared: set[str] = set()
    found_declaration = False
    for heading in SKILL_DECLARATION_SECTIONS:
        body = section_body(text, heading)
        if body is None:
            continue
        found_declaration = True
        declared.update(CODE_SPAN_RE.findall(body))

    if not found_declaration:
        errors.append(
            f"{rel_path}: missing a skill-declaration section (one of: "
            f"{', '.join('## ' + s for s in SKILL_DECLARATION_SECTIONS)})"
        )
    elif not declared:
        errors.append(
            f"{rel_path}: skill-declaration section names no skill in backticks"
        )
    else:
        for name in sorted(declared):
            if name not in skills:
                errors.append(f"{rel_path}: references unknown skill {name!r}")

    return errors


def check_eval_runs() -> list[str]:
    errors: list[str] = []
    if not EVAL_RUNS_DIR.exists():
        return errors
    for child in sorted(EVAL_RUNS_DIR.iterdir()):
        if not child.is_dir():
            continue
        summary = child / "summary.md"
        if not summary.exists():
            errors.append(
                f"eval-runs/{child.name}/: missing summary.md"
            )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict-sections",
        action="store_true",
        help="Treat a missing context/criteria section as fatal (default: warn).",
    )
    args = parser.parse_args(argv)

    skills = discover_skills()
    all_errors: list[str] = []
    warnings: list[str] = []

    for path in sorted(EVALS_DIR.glob("*.md")):
        errors = check_eval_file(path, skills)
        for err in errors:
            soft = (
                "missing a context section" in err
                or "missing a success-criteria section" in err
            )
            if soft and not args.strict_sections:
                warnings.append(err)
            else:
                all_errors.append(err)

    all_errors.extend(check_eval_runs())

    for w in warnings:
        print(f"WARN {w}")
    for e in all_errors:
        print(f"FAIL {e}")

    print(
        f"-- evals: {len(list(EVALS_DIR.glob('*.md')))} files, "
        f"{len(skills)} skills known, "
        f"{len(all_errors)} failures, {len(warnings)} warnings"
    )
    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main())
