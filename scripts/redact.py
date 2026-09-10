#!/usr/bin/env python3
"""Strip credential-shaped values from text before it becomes context.

    agent-skills redact < noisy.log
    some-command 2>&1 | agent-skills redact
    agent-skills redact --check build.log

The problem this solves is one-directional. A credential that reaches a model's
context is in the transcript, in every summary of that transcript, and in
whatever the agent writes next. There is no recall. So the value has to be
removed *before* the text is read, which means at the pipe, not afterwards.

This is defence in depth and not the primary control. The primary control is
that skills resolve database and service access through the Access Resolver and
never put a credential on a command line. This filter is what stands between a
mistake and a permanent one.

Structure is preserved deliberately. `PGPASSWORD=[redacted] psql -h db.internal`
still tells an engineer which variable was set and which host was being reached;
an opaque hash would have moved the problem rather than solved it.

The patterns live in `guard_audit.py` and are shared with the Execution Guard's
decision log, which faces the same obligation from the other direction. One
implementation on purpose: a second pattern set drifts from the first, and the
weaker of the two ends up deciding.

Exit codes:
  0  text was processed (default mode), or `--check` found nothing
  1  `--check` found at least one value to redact
  2  usage or I/O error
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from guard_audit import redact

EXIT_OK = 0
EXIT_FOUND = 1
EXIT_USAGE = 2


def _read_sources(paths: list[str]) -> str | None:
    if not paths:
        return sys.stdin.read()
    chunks: list[str] = []
    for name in paths:
        try:
            chunks.append(Path(name).read_text(encoding="utf-8", errors="replace"))
        except OSError as exc:
            sys.stderr.write(f"redact: cannot read {name}: {exc}\n")
            return None
    return "".join(chunks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Remove credential-shaped values from text.",
        epilog="Reads stdin when no file is given.",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="files to read instead of stdin",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "report instead of transforming: exit 1 if anything would be "
            "redacted, 0 if not. Writes nothing to stdout."
        ),
    )
    args = parser.parse_args(argv)

    text = _read_sources(args.files)
    if text is None:
        return EXIT_USAGE

    cleaned = redact(text)

    if not args.check:
        sys.stdout.write(cleaned)
        return EXIT_OK

    # `--check` never prints the value, and never prints the line either: the
    # line is what contains the secret. It prints where to look.
    if cleaned == text:
        return EXIT_OK

    original_lines = text.splitlines()
    cleaned_lines = cleaned.splitlines()
    hits = [
        number
        for number, (before, after) in enumerate(zip(original_lines, cleaned_lines), start=1)
        if before != after
    ]
    located = ", ".join(str(number) for number in hits[:20])
    if len(hits) > 20:
        located += f", and {len(hits) - 20} more"
    sys.stderr.write(
        f"redact: {len(hits)} line(s) carry a credential-shaped value: {located}\n"
    )
    return EXIT_FOUND


if __name__ == "__main__":
    raise SystemExit(main())
