#!/usr/bin/env python3
"""Read-only dispatch-decision helper for the delivery-runner skill.

The delivery-runner loop calls this once per iteration to answer one question
deterministically: *given the current phased plan on disk, what should the next
fresh agent do?* It never edits anything. The orchestrating agent uses the
JSON it prints to decide whether to dispatch the next phase, stop because the
plan is complete, or stop because a human/planner decision is required.

Source of truth is `phased-plan/README.md` (the plan index), not
`evidence-pack.yml`. The index is the artifact that the lifecycle cleanup
wrapper preserves across executor phase boundaries (see
`scripts/project-memory.py:cleanup_task`); the evidence pack is per-phase
scratch that a fresh phase may have to reconstruct. Reading the index keeps the
runner correct even after a phase has finished and its scratch was cleaned.

Usage:
    python3 scripts/delivery-run-next.py <work-dir-or-index-path> [--mode MODE]

`<work-dir-or-index-path>` may be:
  * the per-task cache dir            (.cache/agent-skills/PROJ-123)
  * the phased-plan dir               (.cache/agent-skills/PROJ-123/phased-plan)
  * the index file itself             (.cache/agent-skills/PROJ-123/phased-plan/README.md)

Exit codes:
  0  a decision was produced (see JSON `action`); this includes "stop" actions
  2  the index could not be found or parsed (caller must surface, not loop)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from boundary_safety import redact_boundary

DONE_STATES = {"done", "skipped"}
DISPATCHABLE_STATES = {"ready", "in-progress"}
HALT_READINESS = {"NEEDS_CLARIFICATION", "NEEDS_EVIDENCE", "BLOCKED"}
MODE_CONTRACTS = {
    "LIGHT": {"phase_budget": "S", "eligible_phase_sizes": ["S"], "mandatory_gates": True},
    "STANDARD": {
        "phase_budget": "M",
        "eligible_phase_sizes": ["S", "M"],
        "mandatory_gates": True,
    },
    "RIGOROUS": {
        "phase_budget": "L",
        "eligible_phase_sizes": ["S", "M", "L"],
        "mandatory_gates": True,
    },
}


def find_index(arg: str) -> Path | None:
    """Resolve the caller's argument to a phased-plan/README.md path."""
    path = Path(arg).expanduser()
    if path.is_file():
        return path
    candidates = [
        path / "README.md",
        path / "phased-plan" / "README.md",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def parse_header(text: str) -> dict[str, str]:
    """Parse the flat top-level scalar keys from the index YAML header."""
    header: dict[str, str] = {}
    if not text.startswith("---\n"):
        return header
    end = text.find("\n---", 4)
    if end == -1:
        return header
    for raw in text[4:end].splitlines():
        if not raw.strip() or raw.startswith((" ", "\t")) or raw.lstrip().startswith("#"):
            continue
        key, sep, value = raw.partition(":")
        if not sep:
            continue
        header[key.strip()] = value.split("#", 1)[0].strip().strip("'\"")
    return header


def phase_rows(text: str) -> list[dict[str, str]]:
    """Parse phase rows with the canonical 6-column layout.

    Layout: ID | Title | Owner skill | Size | State | Prereqs
    """
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 5 or not re.match(r"^phase-\d", cells[0], re.IGNORECASE):
            continue
        rows.append(
            {
                "id": cells[0].lower(),
                "title": cells[1],
                "owner": cells[2].lower(),
                "size": cells[3],
                "state": cells[4].lower(),
                "prereqs": cells[5] if len(cells) > 5 else "none",
            }
        )
    return rows


def phase_file_for(index_path: Path, phase_id: str) -> str | None:
    matches = sorted(index_path.parent.glob(f"{phase_id}-*.md"))
    if not matches:
        exact = index_path.parent / f"{phase_id}.md"
        return exact.name if exact.exists() else None
    return matches[0].name


def stop_for_pointer(base: dict, pointer: str, target: dict | None,
                     rows: list[dict[str, str]]) -> dict[str, object] | None:
    """Return a stop decision if the pointer target is not dispatchable, else None."""
    if target is None:
        return {**base, "action": "stop", "reason": "pointer-not-found",
                "message": f"current_dispatch_pointer '{pointer}' has no matching phase row in the index."}
    if target["state"] in DONE_STATES:
        return {**base, "action": "stop", "reason": "pointer-stale",
                "message": f"Pointer phase '{pointer}' is already '{target['state']}' but is still the "
                           "pointer. Index is stale; re-run delivery-planner to regenerate it."}
    if target["state"] not in DISPATCHABLE_STATES:
        return {**base, "action": "stop", "reason": "pointer-not-ready",
                "message": f"Pointer phase '{pointer}' state is '{target['state']}', not ready/in-progress. "
                           "It needs discovery or a planner decision before dispatch."}
    unmet = unmet_prerequisites(target, rows)
    if unmet:
        return {**base, "action": "stop", "reason": "prerequisites-unmet",
                "message": f"Pointer phase '{pointer}' has unmet prerequisites: {', '.join(unmet)}."}
    return None


def decide(index_path: Path, execution_mode: str = "STANDARD") -> dict[str, object]:
    text = index_path.read_text(encoding="utf-8")
    header = parse_header(text)
    rows = phase_rows(text)

    pointer = header.get("current_dispatch_pointer", "").lower()
    if pointer in {"", "null", "none", "~"}:
        pointer = ""
    readiness = header.get("readiness_decision", "").upper()
    plan_state = header.get("state", "active").lower()
    all_done = bool(rows) and all(r["state"] in DONE_STATES for r in rows)

    base = {
        "work_key": header.get("work_key", "unknown"),
        "plan_branch": header.get("plan_branch", None),
        "index_path": str(index_path),
        "destination_path": str(index_path.parent.parent / "destination.md"),
        "pointer": pointer or None,
        "readiness": readiness or None,
        "totals": {
            "total": len(rows),
            "done": sum(1 for r in rows if r["state"] in DONE_STATES),
            "remaining": sum(1 for r in rows if r["state"] not in DONE_STATES),
        },
        "execution_mode": execution_mode,
        "execution_contract": MODE_CONTRACTS[execution_mode],
    }

    if plan_state == "superseded":
        return {**base, "action": "stop", "reason": "plan-superseded",
                "message": "Index state is 'superseded'; a newer plan exists. Re-run delivery-planner."}
    if all_done:
        return {**base, "action": "stop", "reason": "complete",
                "message": "All phases are done or skipped. Delivery plan complete."}
    if readiness in HALT_READINESS or not pointer:
        return {**base, "action": "stop", "reason": "needs-human",
                "message": "No dispatchable phase: readiness requires a planner or user decision "
                           f"(readiness={readiness or 'unset'}, pointer={pointer or 'null'})."}

    target = next((r for r in rows if r["id"] == pointer), None)
    stop = stop_for_pointer(base, pointer, target, rows)
    if stop is not None:
        return stop
    assert target is not None  # stop_for_pointer returns non-None when target is None

    if target["size"].upper() not in MODE_CONTRACTS[execution_mode]["eligible_phase_sizes"]:
        return {
            **base,
            "action": "stop",
            "reason": "mode-phase-ineligible",
            "message": f"Phase '{pointer}' size '{target['size']}' exceeds the "
                       f"{execution_mode} phase budget "
                       f"'{MODE_CONTRACTS[execution_mode]['phase_budget']}'. Select a higher mode.",
        }

    phase_file = phase_file_for(index_path, pointer)
    return {
        **base,
        "action": "dispatch",
        "reason": "resume" if target["state"] == "in-progress" else "next",
        "phase": {
            "id": target["id"],
            "title": target["title"],
            "owner": target["owner"],
            "size": target["size"],
            "state": target["state"],
            "phase_file": f"phased-plan/{phase_file}" if phase_file else None,
        },
        "message": f"Dispatch {target['id']} ('{target['title']}') to a fresh agent owned by "
                   f"'{target['owner']}'.",
    }


def unmet_prerequisites(target: dict[str, str], rows: list[dict[str, str]]) -> list[str]:
    by_id = {r["id"]: r for r in rows}
    unmet: list[str] = []
    raw = target.get("prereqs", "none")
    for token in re.split(r"[,\s]+", raw.lower()):
        token = token.strip()
        if not token or token in {"none", "n/a", "-"}:
            continue
        prereq_id = token if token.startswith("phase-") else f"phase-{token.zfill(2)}"
        match = by_id.get(prereq_id) or by_id.get(token)
        if match is None:
            unmet.append(f"{token} (not in index)")
        elif match["state"] not in DONE_STATES:
            unmet.append(f"{prereq_id}={match['state']}")
    return unmet


def main(argv: list[str]) -> int:
    if len(argv) not in {2, 4} or (len(argv) == 4 and argv[2] != "--mode"):
        print("usage: delivery-run-next.py <work-dir-or-index-path> [--mode MODE]", file=sys.stderr)
        return 2
    requested_mode = argv[3] if len(argv) == 4 else "STANDARD"
    execution_mode = requested_mode.upper()
    if execution_mode not in MODE_CONTRACTS:
        payload = {
            "action": "error",
            "reason": "invalid-mode",
            "message": f"Invalid execution mode '{requested_mode}'. "
                       "Expected LIGHT, STANDARD, or RIGOROUS.",
        }
        print(json.dumps(redact_boundary(payload)))
        return 2
    index_path = find_index(argv[1])
    if index_path is None:
        payload = {"action": "error", "reason": "index-not-found",
                   "message": f"No phased-plan/README.md found for {argv[1]!r}."}
        print(json.dumps(redact_boundary(payload)))
        return 2
    try:
        decision = decide(index_path, execution_mode)
    except OSError as exc:
        payload = {"action": "error", "reason": "read-failed", "message": str(exc)}
        print(json.dumps(redact_boundary(payload)))
        return 2
    print(json.dumps(redact_boundary(decision), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
