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

Three properties the first version of this module did not have, and which the
pre-1.0 review found by reading it:

  * A lock that cannot be taken within the timeout **raises** ``LockTimeout``
    instead of silently running the body unlocked. Callers that swallowed the
    ``False`` this used to yield were getting exactly the lost update the lock
    exists to prevent, with nothing in the output to say so. A filesystem that
    does not support locking at all (some network mounts) is a different case:
    that is reported once on stderr and the body runs, because there is no
    lock to wait for.
  * An error raised by the caller's body propagates. The old ``except OSError``
    wrapped the ``yield``, so a body failure re-entered the generator and
    surfaced as ``RuntimeError: generator didn't stop after throw()`` — the
    original cause gone.
  * ``update_json`` distinguishes a **missing** file from a **corrupt** one. A
    missing file starts from ``default``; a file that exists but is not a JSON
    object is moved aside to ``<name>.corrupt-<timestamp>`` and reported, then
    the tier continues from ``default``. Replacing it in place erased the only
    evidence of what went wrong.
"""
from __future__ import annotations

import contextlib
import errno
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

try:  # POSIX only, which is what the CLI supports.
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX
    fcntl = None

def _lock_timeout_default() -> float:
    """Seconds to wait for a contended lock. Operator-tunable, never negative."""
    raw = os.environ.get("AGENT_SKILLS_LOCK_TIMEOUT_SECONDS", "")
    try:
        return max(0.0, float(raw)) if raw.strip() else 20.0
    except ValueError:
        return 20.0


LOCK_TIMEOUT_SECONDS = _lock_timeout_default()

# errno values that mean "somebody else holds it" as opposed to "this
# filesystem cannot lock". Only the former is worth waiting on.
_CONTENDED = {errno.EAGAIN, errno.EWOULDBLOCK, errno.EACCES}

_unsupported_reported: set[str] = set()


class LockTimeout(OSError):
    """The advisory lock on a durable file could not be taken in time.

    Nothing was written. The operation is safe to retry; the holder is another
    agent-skills process updating the same file.
    """


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


def _acquire(handle, lock_path: Path, timeout: float) -> bool:
    """Take the exclusive lock, waiting up to ``timeout``.

    Returns True when held. Returns False only when the filesystem reports that
    it cannot lock at all. Raises ``LockTimeout`` on contention past the deadline.
    """
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError as exc:
            if exc.errno not in _CONTENDED:
                key = str(lock_path.parent)
                if key not in _unsupported_reported:
                    _unsupported_reported.add(key)
                    print(
                        f"WARN durable: this filesystem does not support locking "
                        f"({lock_path.parent}); proceeding without serialisation",
                        file=sys.stderr,
                    )
                return False
            if time.monotonic() >= deadline:
                raise LockTimeout(
                    f"could not lock {lock_path.name[:-5]} within {timeout:.0f}s; "
                    f"another agent-skills process holds it — nothing was written, retry"
                ) from None
            time.sleep(0.05)


@contextlib.contextmanager
def locked(path: Path | str, timeout: float = LOCK_TIMEOUT_SECONDS):
    """Hold an advisory exclusive lock covering ``path``.

    Yields ``True`` when the lock is held and ``False`` only when the
    filesystem cannot lock. Contention past ``timeout`` raises ``LockTimeout``
    before the body runs, so a caller never modifies the file unserialised
    without being told. Exceptions raised inside the body propagate unchanged.
    """
    target = Path(path)
    if fcntl is None:  # pragma: no cover - non-POSIX
        yield False
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.with_name(target.name + ".lock")
    handle = open(lock_path, "a+", encoding="utf-8")
    held = False
    try:
        # Only acquisition is guarded. A failure inside the ``with`` body is the
        # caller's error and must reach the caller intact.
        held = _acquire(handle, lock_path, timeout)
        yield held
    finally:
        if held:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        handle.close()


def _quarantine(target: Path, reason: str) -> Path:
    """Move an unreadable durable file aside so it can be inspected later."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    aside = target.with_name(f"{target.name}.corrupt-{stamp}")
    counter = 0
    while aside.exists():
        counter += 1
        aside = target.with_name(f"{target.name}.corrupt-{stamp}-{counter}")
    os.replace(target, aside)
    print(
        f"WARN durable: {target.name} was not readable ({reason}); "
        f"moved to {aside.name} and starting from an empty store",
        file=sys.stderr,
    )
    return aside


def update_text(path: Path | str, transform: Callable[[str], str], default: str = "") -> str:
    """Read, transform, and atomically write ``path`` while holding its lock.

    A missing file starts from ``default``. Any other read error propagates:
    a permission problem is not an empty file.
    """
    target = Path(path)
    with locked(target):
        try:
            current = target.read_text(encoding="utf-8")
        except FileNotFoundError:
            current = default
        updated = transform(current)
        write_text(target, updated)
    return updated


def update_json(path: Path | str, transform: Callable[[dict], dict], default: dict = None) -> dict:
    """Read, transform, and atomically write a JSON file under its lock.

    A missing file starts from ``default``. A file that exists but does not
    hold a JSON object is quarantined beside itself and reported, and the
    update then starts from ``default`` — the tier keeps working and the
    evidence of the corruption is kept, rather than overwritten.
    """
    target = Path(path)
    with locked(target):
        try:
            raw = target.read_text(encoding="utf-8")
        except FileNotFoundError:
            data = dict(default or {})
        else:
            try:
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise ValueError("top level is not an object")
            except ValueError as exc:
                _quarantine(target, str(exc).splitlines()[0][:80])
                data = dict(default or {})
        updated = transform(data)
        write_text(target, json.dumps(updated, indent=2) + "\n")
    return updated
