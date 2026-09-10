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
    python3 scripts/delivery-run-next.py <work-dir-or-index-path>

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
import os
import re
import sys
from pathlib import Path

DONE_STATES = {"done", "skipped"}
DISPATCHABLE_STATES = {"ready", "in-progress"}
HALT_READINESS = {"NEEDS_CLARIFICATION", "NEEDS_EVIDENCE", "BLOCKED"}

VALID_PROFILES = ("LIGHT", "STANDARD", "RIGOROUS")
DEFAULT_PROFILE = "STANDARD"

# Concurrency is an optimisation and never a correctness requirement, so the cap
# is small and deterministic. Unbounded fan-out turns a plan into a thundering
# herd against the same repository, the same test runner, and the same rate
# limits — and makes a failure impossible to attribute.
DEFAULT_MAX_PARALLEL = 3


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
    """Parse phase rows from the index table.

    Layout: ID | Title | Owner skill | Size | State | Prereqs [| Profile | Parallel]

    The two trailing columns were added after `1.0.0-rc.1` and are **appended**,
    never inserted. Cells are read positionally, so moving `State` to make room
    would silently mis-read every plan already sitting in a cache directory. An
    index written before they existed parses unchanged and gets the defaults.
    """
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 5 or not re.match(r"^phase-\d", cells[0], re.IGNORECASE):
            continue
        profile = cells[6].strip().upper() if len(cells) > 6 and cells[6].strip() else ""
        rows.append(
            {
                "id": cells[0].lower(),
                "title": cells[1],
                "owner": cells[2].lower(),
                "size": cells[3],
                "state": cells[4].lower(),
                "prereqs": cells[5] if len(cells) > 5 else "none",
                # An unrecognised value is not trusted into a weaker profile.
                "profile": profile if profile in VALID_PROFILES else DEFAULT_PROFILE,
                "parallel": (cells[7].strip().lower() if len(cells) > 7 else "no"),
            }
        )
    return rows


def phase_header(index_path: Path, phase_id: str) -> dict[str, object]:
    """Read the flat YAML header of a phase file.

    Only the fields concurrency depends on. The index carries a summary; the
    phase file is authoritative, and a claim of parallel-safety is only worth
    acting on from the file that also has to declare what it writes.
    """
    name = phase_file_for(index_path, phase_id)
    if not name:
        return {}
    path = index_path.parent / name
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    header: dict[str, object] = {}
    for raw in text[4:end].splitlines():
        if not raw.strip() or raw.startswith((" ", "\t")) or raw.lstrip().startswith("#"):
            continue
        key, sep, value = raw.partition(":")
        if not sep:
            continue
        key = key.strip()
        value = value.split("#", 1)[0].strip()
        if value.startswith("[") and value.endswith("]"):
            items = [
                item.strip().strip("'\"").lower()
                for item in value[1:-1].split(",")
                if item.strip()
            ]
            header[key] = items
        else:
            header[key] = value.strip("'\"")
    return header


def normalise_phase_id(token: str) -> str:
    token = str(token).strip().lower()
    if not token:
        return ""
    return token if token.startswith("phase-") else f"phase-{token.zfill(2)}"


def parallel_group(
    index_path: Path,
    pointer_row: dict[str, str],
    rows: list[dict[str, str]],
    limit: int,
) -> tuple[list[str], list[str]]:
    """Which phases may run alongside the pointer phase, and why not the rest.

    Every condition must hold. Concurrency here buys wall-clock time on work
    that was going to happen anyway; being wrong about independence costs a
    corrupted working tree and a debugging session that starts with "which
    agent wrote this?". So anything unproven is sequential, and a phase that
    does not say what it writes is treated as writing everything.
    """
    notes: list[str] = []
    if limit <= 1:
        return [], ["concurrency limit is 1"]

    head = phase_header(index_path, pointer_row["id"])
    if str(head.get("parallel_safe", "")).lower() != "true":
        return [], [f"{pointer_row['id']} is not marked parallel_safe"]
    if "mutation_targets" not in head:
        return [], [f"{pointer_row['id']} does not declare mutation_targets"]

    head_targets = set(head.get("mutation_targets") or [])
    head_with = {normalise_phase_id(x) for x in (head.get("parallel_with") or [])}

    by_id = {row["id"]: row for row in rows}
    chosen: list[str] = []
    claimed = set(head_targets)

    for row in rows:
        if len(chosen) + 1 >= limit:
            break
        if row["id"] == pointer_row["id"]:
            continue
        if row["state"] not in DISPATCHABLE_STATES:
            continue
        if unmet_prerequisites(row, rows):
            continue
        if row["id"] not in head_with:
            continue

        other = phase_header(index_path, row["id"])
        if str(other.get("parallel_safe", "")).lower() != "true":
            notes.append(f"{row['id']} is not marked parallel_safe")
            continue
        if "mutation_targets" not in other:
            notes.append(f"{row['id']} does not declare mutation_targets")
            continue
        # Mutual. A one-sided claim means one of the two phases was written
        # without the other in mind, and that is exactly when they collide.
        other_with = {normalise_phase_id(x) for x in (other.get("parallel_with") or [])}
        if pointer_row["id"] not in other_with:
            notes.append(f"{row['id']} does not list {pointer_row['id']} in parallel_with")
            continue
        # A dependency in either direction disqualifies, regardless of what the
        # parallel_with lists claim.
        row_prereqs = {
            normalise_phase_id(t)
            for t in re.split(r"[,\s]+", str(row.get("prereqs", "")).lower())
            if t and t not in {"none", "n/a", "-"}
        }
        head_prereqs = {
            normalise_phase_id(t)
            for t in re.split(r"[,\s]+", str(pointer_row.get("prereqs", "")).lower())
            if t and t not in {"none", "n/a", "-"}
        }
        if pointer_row["id"] in row_prereqs or row["id"] in head_prereqs:
            notes.append(f"{row['id']} and {pointer_row['id']} have a dependency edge")
            continue

        targets = set(other.get("mutation_targets") or [])
        overlap = targets & claimed
        if overlap:
            notes.append(
                f"{row['id']} writes {', '.join(sorted(overlap))}, already claimed by "
                f"another phase in the group"
            )
            continue

        chosen.append(row["id"])
        claimed |= targets

    if not chosen and not notes:
        notes.append("no other phase is both ready and declared parallel-safe with it")
    _ = by_id
    return chosen, notes


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


def decide(index_path: Path) -> dict[str, object]:
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

    phase_file = phase_file_for(index_path, pointer)
    head = phase_header(index_path, pointer)

    # The phase file is authoritative; the index column is a roll-up of it. When
    # they disagree, the stronger of the two wins rather than the more recent —
    # a downgrade should never come from a stale summary table.
    file_profile = str(head.get("execution_profile", "")).strip().upper()
    profile = target["profile"]
    if file_profile in VALID_PROFILES:
        profile = max(
            (profile, file_profile), key=lambda name: VALID_PROFILES.index(name)
        )

    limit = max_parallel()
    group, group_notes = parallel_group(index_path, target, rows, limit)

    decision = {
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
            "execution_profile": profile,
            # A LIGHT phase may be executed inline; anything else gets its own
            # empty-context agent. RIGOROUS additionally keeps independent
            # review, and no field here can turn that off.
            "fresh_context_required": profile != "LIGHT",
            "independent_review_required": profile == "RIGOROUS",
            "expected_effort_minutes": _int_or_none(head.get("expected_effort_minutes")),
        },
        "concurrency": {
            "limit": limit,
            "parallel_group": [target["id"], *group] if group else [],
            "notes": group_notes,
        },
        "message": f"Dispatch {target['id']} ('{target['title']}') to a fresh agent owned by "
                   f"'{target['owner']}'.",
    }
    if group:
        decision["message"] += (
            f" {len(group)} further phase(s) are provably independent and may run "
            f"alongside it: {', '.join(group)}."
        )
    return decision


def _int_or_none(value: object) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def max_parallel() -> int:
    raw = os.environ.get("AGENT_SKILLS_MAX_PARALLEL", "")
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_PARALLEL
    # Clamped rather than trusted. A caller that exports 400 gets the cap, not a
    # fork bomb aimed at their own test runner.
    return max(1, min(value, DEFAULT_MAX_PARALLEL))


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
    if len(argv) != 2:
        print("usage: delivery-run-next.py <work-dir-or-index-path>", file=sys.stderr)
        return 2
    index_path = find_index(argv[1])
    if index_path is None:
        print(json.dumps({"action": "error", "reason": "index-not-found",
                          "message": f"No phased-plan/README.md found for {argv[1]!r}."}))
        return 2
    try:
        decision = decide(index_path)
    except OSError as exc:
        print(json.dumps({"action": "error", "reason": "read-failed", "message": str(exc)}))
        return 2
    print(json.dumps(decision, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
