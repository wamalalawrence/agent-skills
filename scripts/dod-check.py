#!/usr/bin/env python3
"""Validate a Definition of Done artifact as evidence, not as a claim.

`software-engineer` writes `definition-of-done.json` at the end of its Commit
phase and `code-reviewer` reads it before a verdict. Until this release the
file was a bag of booleans, and the rule "every `false` needs a waiver" applied
equally to a failed build and to `shared_library_changed: false`, which is a
classification, not a check. A lifecycle closeout could also record
`completed` with no artifact at all.

This validator separates the two questions the artifact answers:

  * **Checks** — build, tests, format, lint, security scan, regression RED and
    GREEN — each with a result of `pass | fail | not_run | not_applicable` and,
    for a pass, the execution record that produced it: the command, the working
    directory, the revision or tree it ran against, and the exit code.
  * **Classifications** — is this a bug fix, did a shared library change, does
    the safety acknowledgement apply. Never pass/fail. Never waived.

A required check that is `fail` or `not_run` blocks verified delivery unless a
waiver names it, gives a reason, and records an authority other than the agent
itself. A pass whose recorded revision differs from `head_sha` is stale
evidence and does not count.

Usage:
  python3 scripts/dod-check.py <definition-of-done.json> [--json]

Exit codes:
  0  verified — every required check passed on the reviewed revision, or was
     waived by a named authority
  1  not verified — the reasons are printed, one per line
  2  the file is missing, unreadable, or not this schema
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RESULTS = ("pass", "fail", "not_run", "not_applicable")
# Checks every engineering change must account for. A check can be
# `not_applicable` with a one-line reason, which is not a waiver.
ALWAYS_REQUIRED = ("build", "tests", "format", "lint_or_static_analysis", "security_scan")
BUG_FIX_REQUIRED = ("regression_red", "regression_green")
# A waiver signed by the agent that wrote the artifact is an excuse, not an
# authorization. These are the authorities a waiver may carry.
WAIVER_AUTHORITIES = ("user", "reviewer", "project-policy", "ticket")


def load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"FAIL {path}: not found")
    except (OSError, ValueError) as exc:
        raise SystemExit(f"FAIL {path}: unreadable ({str(exc).splitlines()[0][:80]})")
    if not isinstance(data, dict):
        raise SystemExit(f"FAIL {path}: top level is not an object")
    return data


def evaluate(data: dict) -> tuple[list[str], list[str]]:
    """Return (problems, notes). Empty problems means verified."""
    problems: list[str] = []
    notes: list[str] = []

    checks = data.get("checks")
    if not isinstance(checks, dict):
        problems.append(
            "no `checks` object: this artifact uses the pre-1.0 boolean schema, which "
            "records claims, not execution evidence — regenerate it"
        )
        return problems, notes

    classification = data.get("classification") or {}
    if not isinstance(classification, dict):
        classification = {}
    head_sha = str(data.get("head_sha") or "").strip()

    waivers = data.get("waivers") or []
    waived: dict[str, dict] = {}
    if isinstance(waivers, list):
        for entry in waivers:
            if not isinstance(entry, dict):
                problems.append("a waiver is not an object")
                continue
            name = str(entry.get("check") or "").strip()
            reason = str(entry.get("reason") or "").strip()
            authority = str(entry.get("authority") or "").strip().lower()
            if not name:
                problems.append("a waiver names no check")
                continue
            if not reason:
                problems.append(f"waiver for `{name}` has no reason")
            if authority not in WAIVER_AUTHORITIES:
                problems.append(
                    f"waiver for `{name}` has authority {authority or 'none'!r}; "
                    f"an agent cannot waive its own check — one of "
                    f"{', '.join(WAIVER_AUTHORITIES)} must be recorded"
                )
                continue
            waived[name] = entry

    required = list(ALWAYS_REQUIRED)
    if classification.get("is_bug_fix") is True:
        required.extend(BUG_FIX_REQUIRED)

    for name in required:
        check = checks.get(name)
        if not isinstance(check, dict):
            if name in waived:
                notes.append(f"{name}: absent, waived by {waived[name]['authority']}")
                continue
            problems.append(f"required check `{name}` is missing")
            continue
        result = str(check.get("result") or "").strip().lower()
        if result not in RESULTS:
            problems.append(f"check `{name}` has result {result or 'none'!r}; expected one of {', '.join(RESULTS)}")
            continue
        if result == "not_applicable":
            if not str(check.get("reason") or "").strip():
                problems.append(f"check `{name}` is not_applicable without a reason")
            else:
                notes.append(f"{name}: not applicable — {check['reason']}")
            continue
        if result in ("fail", "not_run"):
            if name in waived:
                notes.append(f"{name}: {result}, waived by {waived[name]['authority']}")
            else:
                problems.append(f"required check `{name}` is `{result}` and not waived")
            continue
        # result == pass: the execution record is what makes it evidence.
        missing = [
            field
            for field in ("command", "revision", "exit_code")
            if check.get(field) in (None, "")
        ]
        if missing:
            problems.append(
                f"check `{name}` claims pass without an execution record "
                f"(missing {', '.join(missing)})"
            )
            continue
        if str(check.get("exit_code")) != "0":
            problems.append(
                f"check `{name}` claims pass but records exit_code {check.get('exit_code')}"
            )
            continue
        revision = str(check.get("revision") or "").strip()
        if head_sha and revision and revision != head_sha and not head_sha.startswith(revision) and not revision.startswith(head_sha):
            problems.append(
                f"check `{name}` passed on revision {revision}, not the reviewed head {head_sha}: stale evidence"
            )
            continue
        if name == "regression_red" and not str(check.get("assertion") or "").strip():
            problems.append(
                "regression_red must record the behavioural assertion that failed; a "
                "missing test, zero collected tests, or a setup error is not RED"
            )
            continue

    for name, check in checks.items():
        if isinstance(check, dict) and isinstance(check.get("result"), bool):
            problems.append(f"check `{name}` uses a boolean; results are pass/fail/not_run/not_applicable")

    for name, value in classification.items():
        if name in waived:
            problems.append(
                f"`{name}` is a classification, not a check; a waiver for it is meaningless"
            )

    return problems, notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("path")
    parser.add_argument("--json", action="store_true", help="Machine-readable result.")
    args = parser.parse_args(argv)

    data = load(Path(args.path))
    problems, notes = evaluate(data)
    verified = not problems

    if args.json:
        print(
            json.dumps(
                {
                    "verified": verified,
                    "issue_key": data.get("issue_key"),
                    "head_sha": data.get("head_sha"),
                    "problems": problems,
                    "notes": notes,
                },
                indent=2,
            )
        )
    else:
        for note in notes:
            print(f"note  {note}")
        for problem in problems:
            print(f"FAIL  {problem}")
        state = "verified" if verified else "NOT verified"
        print(f"definition-of-done: {state} ({len(problems)} problem(s))")
    return 0 if verified else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print(exc.code, file=sys.stderr)
            sys.exit(2)
        raise
