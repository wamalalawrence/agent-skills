#!/usr/bin/env python3
"""Durable writes for the memory tiers.

Everything under the cache root that survives a task — project memory, org
memory, the repository knowledge base, the blackboard — was written with
``Path.write_text``. That call truncates the file and then writes into it, with
no lock and no rename, which gives two failure modes that only appear when the
tool is doing its job:

  * **Lost updates.** Two agents in one repository read the same ``memory.md``,
    each append a bullet, each write the whole file back. The second write wins
    and the first bullet is gone. Nothing reports this; the memory is simply
    thinner than the work that went into it.
  * **Torn files.** A crash or a full disk between truncate and write leaves a
    file that is empty or half a JSON document. The next reader of
    ``memory.json`` gets a ``ValueError`` and the tier looks uninitialised.

Both are fixed by the same two moves, which is why they live in one place:

  ``write_text`` — write to a temporary file beside the target, flush it to the
  platter, then ``os.replace``. A reader sees either the old file or the new one.

  ``locked``     — hold an advisory exclusive lock for the whole
  read-modify-write, so appends serialise instead of racing. The lock file sits
  next to the target and is advisory, so a killed process releases it when its
  descriptor closes; there is nothing to clean up by hand.

``update_text`` and ``update_json`` combine the two, and are what callers should
reach for: passing a function that transforms the current content is the only
shape in which "read, change, write" is safe under concurrency.
"""
from __future__ import annotations

import contextlib
import json
import os
import time
from pathlib import Path
from typing import Callable

try:  # POSIX only, which is what the CLI supports.
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX
    fcntl = None

LOCK_TIMEOUT_SECONDS = 20.0


def write_text(path: Path | str, text: str, mode: int = 0o644) -> None:
    """Replace ``path`` with ``text`` atomically."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp.%d" % os.getpid())
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(temporary, mode)
        except OSError:
            pass
        os.replace(temporary, target)
    except BaseException:
        try:
            os.remove(temporary)
        except OSError:
            pass
        raise


def write_json(path: Path | str, payload, indent: int = 2) -> None:
    write_text(path, json.dumps(payload, indent=indent) + "\n")


@contextlib.contextmanager
def locked(path: Path | str, timeout: float = LOCK_TIMEOUT_SECONDS):
    """Hold an advisory exclusive lock covering ``path``.

    Best effort by design: if the lock cannot be taken within ``timeout`` the
    body still runs. A memory tier that refuses to record a fact because another
    agent is recording one is worse than an occasional lost bullet — this is a
    notebook, not a ledger — and the atomic write below still guarantees the file
    itself is never left torn.
    """
    target = Path(path)
    if fcntl is None:  # pragma: no cover - non-POSIX
        yield False
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.with_name(target.name + ".lock")
    handle = None
    held = False
    try:
        handle = open(lock_path, "a+", encoding="utf-8")
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                held = True
                break
            except OSError:
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.05)
        yield held
    except OSError:
        yield False
    finally:
        if handle is not None:
            if held:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
            handle.close()


def update_text(path: Path | str, transform: Callable[[str], str], default: str = "") -> str:
    """Read, transform, and atomically write ``path`` while holding its lock."""
    target = Path(path)
    with locked(target):
        try:
            current = target.read_text(encoding="utf-8")
        except OSError:
            current = default
        updated = transform(current)
        write_text(target, updated)
    return updated


def update_json(path: Path | str, transform: Callable[[dict], dict], default: dict = None) -> dict:
    """Read, transform, and atomically write a JSON file under its lock.

    Unreadable content is replaced by ``default`` rather than raising: a torn
    file written by an older build must not make the tier permanently unusable.
    """
    target = Path(path)
    with locked(target):
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("not an object")
        except (OSError, ValueError):
            data = dict(default or {})
        updated = transform(data)
        write_text(target, json.dumps(updated, indent=2) + "\n")
    return updated
