#!/usr/bin/env python3
"""Ask whether a running task is still getting anywhere.

    agent-skills watchdog PROJ-123 --budget-minutes 20
    agent-skills watchdog PROJ-123 --budget-minutes 20 --json

A mechanism-selection dispatch ran for roughly an hour, was killed, and had
written nothing at all. The hour bought no artifact, no hypothesis, no partial
answer — the retry started from zero. Nothing was watching, and nothing could
have been, because the task left no trace to watch.

This is the other half of the progress ledger (`agent-skills blackboard
progress`). The ledger records milestones; this reads them and answers one
question: continue, narrow, split, restart, or stop.

**It measures stagnation, not elapsed time.** That distinction is the whole
design. A hard timeout kills the careful work along with the stuck work, and
teaches everyone to pad their estimates. A task that is still writing artifacts
at three times its budget is not stuck — it is bigger than someone thought, and
the useful response is to narrow or split it, not to shoot it. A task that has
written nothing for twenty minutes is stuck whether its budget was five minutes
or fifty.

There is no daemon and nothing polls. A supervisor process would bring orphaned
children, stale lock files, and signal handling into a release whose entire
purpose is stability, and it could not observe a sub-agent it did not spawn
anyway. This is a pure function of what is already on disk: the runner calls it
between phases, an executor calls it at its own checkpoints, and a human can
call it any time to ask what is going on.

Exit codes:
   0  continue — the work is moving
  10  reassess — narrow, split, or restart; the caller decides which
  20  stop — no useful progress and well past budget
   2  usage error, or the task has no readable blackboard
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cache_root import default_cache_root

CONTINUE = "continue"
NARROW = "narrow"
SPLIT = "split"
RESTART = "restart"
STOP = "stop"

EXIT_CONTINUE = 0
EXIT_REASSESS = 10
EXIT_STOP = 20
EXIT_USAGE = 2

REASSESS_VERDICTS = {NARROW, SPLIT, RESTART}

# Below this, a "stall" is just an agent thinking. Reading a file, forming a
# hypothesis, and running one query is several minutes of legitimate silence,
# and a watchdog that fires inside that window trains people to disable it.
MIN_STALL_MINUTES = 5.0

DEFAULT_BUDGET_MINUTES = 20.0


def parse_iso(value: str) -> datetime | None:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def resolve_cache_root(explicit: str | None) -> Path:
    # One resolution order for every helper and both wrappers; see cache_root.py.
    return default_cache_root(explicit)


def assess(
    started_at: datetime,
    progress_times: list[datetime],
    now: datetime,
    budget_minutes: float,
) -> dict:
    """Map a progress history to a verdict. Pure and total."""
    elapsed = (now - started_at).total_seconds() / 60.0
    stall_window = max(MIN_STALL_MINUTES, budget_minutes * 0.5)
    # The FIRST milestone is allowed longer than a mid-run gap. An agent has to
    # read the brief, orient in the repository, and form a hypothesis before it
    # has anything worth recording, and firing during that is how a watchdog
    # earns a reputation for interrupting people who were working.
    first_window = max(MIN_STALL_MINUTES, budget_minutes * 0.75)
    last = max(progress_times) if progress_times else None
    since_progress = (now - last).total_seconds() / 60.0 if last else elapsed
    stalled = since_progress > (stall_window if progress_times else first_window)

    reasons: list[str] = []

    if not progress_times:
        # The worst case, and the one that actually happened: a long run with
        # nothing persisted. The fix is not more time, it is a narrower brief.
        if elapsed > budget_minutes * 3:
            verdict = STOP
            reasons.append(
                f"{elapsed:.0f} min elapsed against a {budget_minutes:.0f} min budget with "
                f"no milestone ever recorded — stop and hand back rather than spend more"
            )
        elif elapsed >= first_window:
            verdict = RESTART
            reasons.append(
                f"{elapsed:.0f} min elapsed and not one milestone recorded — the brief is "
                f"most likely too broad to produce anything; restart it narrower"
            )
        else:
            verdict = CONTINUE
            reasons.append(
                f"{elapsed:.0f} min elapsed, still inside the {first_window:.0f} min "
                f"settling window before a first milestone is expected"
            )
        return _result(verdict, reasons, elapsed, since_progress, first_window,
                       budget_minutes, len(progress_times), stalled)

    if stalled:
        if elapsed > budget_minutes * 2:
            verdict = STOP
            reasons.append(
                f"nothing recorded for {since_progress:.0f} min and {elapsed:.0f} min "
                f"elapsed against a {budget_minutes:.0f} min budget — stop safely"
            )
        else:
            verdict = NARROW
            reasons.append(
                f"nothing recorded for {since_progress:.0f} min, past the "
                f"{stall_window:.0f} min stall window — narrow to the next single "
                f"checkable step"
            )
        return _result(verdict, reasons, elapsed, since_progress, stall_window,
                       budget_minutes, len(progress_times), stalled)

    # Progress is being made. Elapsed alone never stops the work.
    if elapsed > budget_minutes * 2:
        verdict = SPLIT
        reasons.append(
            f"still producing milestones ({len(progress_times)} so far) but "
            f"{elapsed:.0f} min against a {budget_minutes:.0f} min budget — this is "
            f"bigger than one unit of work; split it"
        )
    elif elapsed > budget_minutes:
        verdict = NARROW
        reasons.append(
            f"progress is current but {elapsed:.0f} min is over the "
            f"{budget_minutes:.0f} min budget — narrow the remaining scope"
        )
    else:
        verdict = CONTINUE
        reasons.append(
            f"{len(progress_times)} milestone(s), most recent {since_progress:.0f} min ago, "
            f"{elapsed:.0f} min of a {budget_minutes:.0f} min budget used"
        )
    return _result(verdict, reasons, elapsed, since_progress, stall_window,
                   budget_minutes, len(progress_times), stalled)


def _result(verdict, reasons, elapsed, since_progress, stall_window,
            budget_minutes, count, stalled) -> dict:
    return {
        "verdict": verdict,
        "reasons": reasons,
        "stalled": stalled,
        "elapsed_minutes": round(elapsed, 1),
        "minutes_since_progress": round(since_progress, 1),
        "stall_window_minutes": round(stall_window, 1),
        "budget_minutes": budget_minutes,
        "progress_events": count,
    }


def load_history(path: Path) -> tuple[datetime | None, list[datetime]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    started = parse_iso(str(data.get("created_at", "")))
    times: list[datetime] = []
    # Any durable write counts as motion, not only an explicit progress entry.
    # A skill that recorded three facts and an artifact is plainly working, and
    # requiring a separate ceremony to say so would just add ceremony.
    for section in ("progress", "facts", "decisions", "artifacts", "handoffs"):
        for entry in data.get(section, []) or []:
            if not isinstance(entry, dict):
                continue
            when = parse_iso(str(entry.get("at", "")))
            if when is not None:
                times.append(when)
    return started, times


def render_text(decision: dict) -> str:
    lines = [
        f"verdict: {decision['verdict']}",
        "",
        f"  elapsed              {decision['elapsed_minutes']} min "
        f"(budget {decision['budget_minutes']} min)",
        f"  since last milestone {decision['minutes_since_progress']} min "
        f"(stall window {decision['stall_window_minutes']} min)",
        f"  milestones recorded  {decision['progress_events']}",
        "",
    ]
    for reason in decision["reasons"]:
        lines.append(f"  - {reason}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Decide whether a task is still making progress.",
        epilog="Reads the task blackboard. Never writes, never kills anything.",
    )
    parser.add_argument("issue_key")
    parser.add_argument("--cache-root", default=None)
    parser.add_argument(
        "--budget-minutes",
        type=float,
        default=DEFAULT_BUDGET_MINUTES,
        help=f"expected effort for this task or phase (default {DEFAULT_BUDGET_MINUTES:.0f})",
    )
    parser.add_argument(
        "--now",
        default=None,
        help="evaluate as at this UTC time (RFC3339). For tests and replays",
    )
    parser.add_argument(
        "--started-at",
        default=None,
        help="override the start time instead of reading the blackboard's created_at",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    if args.budget_minutes <= 0:
        sys.stderr.write("watchdog: --budget-minutes must be positive\n")
        return EXIT_USAGE

    now = datetime.now(timezone.utc)
    if args.now:
        parsed_now = parse_iso(args.now)
        if parsed_now is None:
            sys.stderr.write(f"watchdog: cannot parse --now {args.now!r}\n")
            return EXIT_USAGE
        now = parsed_now

    path = resolve_cache_root(args.cache_root) / args.issue_key / "blackboard.json"
    try:
        started, times = load_history(path)
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"watchdog: no readable blackboard at {path}: {exc}\n")
        return EXIT_USAGE

    if args.started_at:
        started = parse_iso(args.started_at)
        if started is None:
            sys.stderr.write(f"watchdog: cannot parse --started-at {args.started_at!r}\n")
            return EXIT_USAGE
    if started is None:
        sys.stderr.write(f"watchdog: blackboard at {path} has no usable created_at\n")
        return EXIT_USAGE

    # A milestone outside the window under evaluation is not evidence about it.
    # One stamped before the start (clock skew, a restored blackboard) would
    # otherwise read as progress; one stamped after `now` would read as progress
    # that has not happened yet, which is worse — it makes a stalled task look
    # busy.
    times = [when for when in times if started <= when <= now]

    decision = assess(started, times, now, args.budget_minutes)
    if args.json:
        sys.stdout.write(json.dumps(decision, indent=2) + "\n")
    else:
        sys.stdout.write(render_text(decision) + "\n")

    if decision["verdict"] == CONTINUE:
        return EXIT_CONTINUE
    if decision["verdict"] in REASSESS_VERDICTS:
        return EXIT_REASSESS
    return EXIT_STOP


if __name__ == "__main__":
    raise SystemExit(main())
