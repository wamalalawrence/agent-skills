#!/usr/bin/env python3
"""Lightweight executable eval harness for agent-skills.

The full evals under `evals/` are prose scenarios meant for humans plus
agents. This harness adds a small, machine-checkable layer on top so a CI run
can answer: *does any eval file structurally regress between releases?*

It is intentionally minimal — it does not invoke a model. It checks that:

  1. Every eval file under `evals/` has a top-level `# ` heading.
  2. Every eval file declares some context (one of `CONTEXT_SECTIONS`) and
     some success criteria (one of `CRITERIA_SECTIONS`). The exact section
     names in the corpus vary by author and skill.
  3. Skill names referenced in `Expected Skills:` lines exist on disk under
     `skills/`.
  4. Every release-scoped run under `eval-runs/<version>/` ships a
     `summary.md`.

A future iteration can plug a real agent runner behind `--invoke` and compare
its output against an `Expected Behavior` block. The scaffold is here so the
contract exists from day one.

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

EXPECTED_SECTIONS = ()  # legacy: kept for --strict-sections compatibility
CONTEXT_SECTIONS = (
    "Input Context",
    "Scenario",
    "Setup",
    "Why This Scenario",
    "Why this eval exists",
    "Workspace fixture",
    "Skill Under Test",
)
CRITERIA_SECTIONS = (
    "Expected Behavior",
    "Expected agent behavior",
    "Pass/Fail Checklist",
    "Pass / Fail Checklist",
    "Pass criteria",
    "Scorecard Criteria",
    "Required Output Fields",
    "Required Output",
)
EXPECTED_SKILLS_RE = re.compile(r"^Expected Skills:\s*(.+)$", re.MULTILINE)


def discover_skills() -> set[str]:
    return {p.parent.name for p in SKILLS_DIR.glob("**/SKILL.md")}


def check_eval_file(path: Path, skills: set[str]) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    if not re.search(r"^#\s+\S", text, re.MULTILINE):
        errors.append(f"{path.relative_to(ROOT)}: missing top-level heading")
    headings = {
        re.sub(r"\s+", " ", m.group(1).strip().lower())
        for m in re.finditer(r"^##\s+(.+?)\s*$", text, re.MULTILINE)
    }
    if not any(s.lower() in headings or any(h.startswith(s.lower()) for h in headings) for s in CONTEXT_SECTIONS):
        errors.append(
            f"{path.relative_to(ROOT)}: missing a context section "
            f"(one of: {', '.join(CONTEXT_SECTIONS)})"
        )
    if not any(s.lower() in headings or any(h.startswith(s.lower()) for h in headings) for s in CRITERIA_SECTIONS):
        errors.append(
            f"{path.relative_to(ROOT)}: missing a success-criteria section "
            f"(one of: {', '.join(CRITERIA_SECTIONS)})"
        )
    for required in EXPECTED_SECTIONS:
        if required.lower() not in headings:
            errors.append(
                f"{path.relative_to(ROOT)}: missing required section '## {required}'"
            )
    for match in EXPECTED_SKILLS_RE.finditer(text):
        for raw in match.group(1).split(","):
            name = raw.strip().strip("`").lower()
            if name and name not in skills:
                errors.append(
                    f"{path.relative_to(ROOT)}: references unknown skill {name!r}"
                )
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
        help="Treat missing EXPECTED_SECTIONS as fatal (default: warn only).",
    )
    args = parser.parse_args(argv)

    skills = discover_skills()
    all_errors: list[str] = []
    warnings: list[str] = []

    for path in sorted(EVALS_DIR.glob("*.md")):
        errors = check_eval_file(path, skills)
        for err in errors:
            if ("missing a context section" in err
                    or "missing a success-criteria section" in err
                    or "missing required section" in err) and not args.strict_sections:
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
