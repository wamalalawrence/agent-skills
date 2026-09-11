"""Hardened archive extraction and directory copying.

An installer that extracts an archive is a file-write primitive pointed at the
user's home directory by whoever produced the archive. Python's
``TarFile.extractall`` was that primitive until 3.12, and the compatibility
shims for older interpreters are exactly the machines this has to run on. So
extraction here is explicit and refuses anything it does not positively
recognise as safe.

Rejected outright:

  * absolute member paths (``/etc/cron.d/x``)
  * any ``..`` component, before or after normalisation
  * a member whose resolved destination leaves the extraction root
  * symlinks and hardlinks whose target leaves the extraction root
  * device nodes, FIFOs, sockets, and anything else that is not a regular
    file, directory, or in-root link
  * setuid / setgid bits

Nothing is written until every member has passed, so a hostile archive cannot
half-extract and leave a partial payload behind.
"""

from __future__ import annotations

import os
import shutil
import stat
import tarfile

from .exits import Exit, ExitError
from .release import PAYLOAD_EXCLUDE_NAMES

# Modes are normalised rather than trusted. The payload only ever needs
# "readable" and "executable"; nothing in a release legitimately needs setuid.
FILE_MODE = 0o644
EXEC_MODE = 0o755
DIR_MODE = 0o755


class ArchiveError(ExitError):
    def __init__(self, message: str, hint: str = ""):
        super().__init__(message, Exit.INTEGRITY, hint)


def _inside(root: str, candidate: str) -> bool:
    """True when ``candidate`` is ``root`` itself or lives beneath it.

    Compares on normalised absolute paths without resolving symlinks, because
    the question is about the path we are *about* to create.
    """
    root = os.path.normpath(root)
    candidate = os.path.normpath(candidate)
    return candidate == root or candidate.startswith(root + os.sep)


def _check_member_name(name: str) -> str:
    if not name or name in (".", "./"):
        return ""
    if name.startswith("/") or name.startswith("\\"):
        raise ArchiveError("archive member has an absolute path: {!r}".format(name))
    if os.path.isabs(name):
        raise ArchiveError("archive member has an absolute path: {!r}".format(name))
    # Windows drive letters and UNC paths, which normpath will not neutralise
    # on a POSIX host but a cross-platform consumer would honour.
    if len(name) > 1 and name[1] == ":":
        raise ArchiveError("archive member has a drive-qualified path: {!r}".format(name))
    parts = name.replace("\\", "/").split("/")
    if any(part == ".." for part in parts):
        raise ArchiveError("archive member escapes the root with '..': {!r}".format(name))
    normalised = os.path.normpath(name)
    if normalised.startswith(".."):
        raise ArchiveError("archive member escapes the root: {!r}".format(name))
    return normalised


def safe_extract_tar(archive_path: str, dest: str, strip_components: int = 0) -> int:
    """Extract ``archive_path`` into ``dest``. Returns the file count written.

    ``strip_components`` mirrors ``tar --strip-components``: ``git archive``
    prefixes every member with a directory, and dropping it here avoids a
    second copy pass.
    """
    dest = os.path.abspath(dest)
    os.makedirs(dest, exist_ok=True)

    approved = []
    with tarfile.open(archive_path, "r:*") as tar:
        for member in tar.getmembers():
            name = _check_member_name(member.name)
            if not name:
                continue
            if strip_components:
                parts = name.split(os.sep)
                if len(parts) <= strip_components:
                    continue
                name = os.sep.join(parts[strip_components:])
            if os.path.basename(name) in PAYLOAD_EXCLUDE_NAMES:
                continue
            target = os.path.join(dest, name)
            if not _inside(dest, target):
                raise ArchiveError("archive member resolves outside the root: {!r}".format(member.name))

            if member.issym() or member.islnk():
                link_target = member.linkname or ""
                if os.path.isabs(link_target):
                    raise ArchiveError(
                        "archive link {!r} points at an absolute path {!r}".format(
                            member.name, link_target
                        )
                    )
                resolved = os.path.normpath(os.path.join(os.path.dirname(target), link_target))
                if not _inside(dest, resolved):
                    raise ArchiveError(
                        "archive link {!r} escapes the root: {!r}".format(member.name, link_target)
                    )
            elif not (member.isfile() or member.isdir()):
                raise ArchiveError(
                    "archive member {!r} is not a file, directory, or in-root link".format(
                        member.name
                    )
                )

            if member.mode & (stat.S_ISUID | stat.S_ISGID):
                raise ArchiveError("archive member {!r} carries a setuid/setgid bit".format(member.name))
            approved.append((member, name, target))

        # Second pass: nothing was written above, so a rejection leaves no trace.
        written = 0
        for member, name, target in approved:
            if member.isdir():
                os.makedirs(target, exist_ok=True)
                os.chmod(target, DIR_MODE)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if member.issym():
                if os.path.lexists(target):
                    os.remove(target)
                os.symlink(member.linkname, target)
                continue
            if member.islnk():
                source = os.path.join(dest, _check_member_name(member.linkname))
                if os.path.lexists(target):
                    os.remove(target)
                shutil.copyfile(source, target)
                written += 1
                continue
            extracted = tar.extractfile(member)
            if extracted is None:
                raise ArchiveError("archive member {!r} has no readable content".format(member.name))
            with open(target, "wb") as handle:
                shutil.copyfileobj(extracted, handle)
            os.chmod(target, EXEC_MODE if member.mode & stat.S_IXUSR else FILE_MODE)
            written += 1
    return written


def copy_payload(source: str, dest: str, entries) -> int:
    """Copy the payload entries of a source tree into ``dest``.

    Used by the local provider. Symlinks are resolved rather than copied: a
    release must be self-contained, and a link into a developer's checkout
    would make the installed release depend on that checkout continuing to
    exist. Returns the number of files written.
    """
    source = os.path.realpath(source)
    dest = os.path.abspath(dest)
    os.makedirs(dest, exist_ok=True)
    written = 0

    for name, required in entries:
        origin = os.path.join(source, name)
        if not os.path.exists(origin):
            if required:
                raise ExitError(
                    "source tree {} is missing required entry {}".format(source, name),
                    Exit.INTEGRITY,
                )
            continue
        # The escape check inside `_copy_tree` only sees links on files it walks
        # past, so a payload entry that is *itself* a link — `skills -> ~/.ssh` —
        # was resolved by `isdir` and then walked as if it were part of the
        # checkout. Every entry is checked before it is read, at the top too.
        resolved_origin = os.path.realpath(origin)
        if not _inside(source, resolved_origin):
            raise ExitError(
                "source tree entry {} resolves outside the checkout: {} -> {}".format(
                    name, origin, resolved_origin
                ),
                Exit.INTEGRITY,
                hint="a release payload must be self-contained; move the real content in-tree",
            )
        target = os.path.join(dest, name)
        if os.path.isdir(origin):
            written += _copy_tree(origin, target, source)
        else:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(origin, target)
            _mirror_exec_bit(origin, target)
            written += 1
    return written


def _copy_tree(origin: str, target: str, source_root: str) -> int:
    written = 0
    os.makedirs(target, exist_ok=True)
    for current, dirnames, filenames in os.walk(origin):
        dirnames[:] = sorted(d for d in dirnames if d not in PAYLOAD_EXCLUDE_NAMES)
        # `os.walk` does not descend into a symlinked directory, so one pointing
        # outside the checkout would be dropped from the payload without a word.
        # Silence is the wrong answer: either the release is missing content it
        # expects, or the checkout is trying to reach outside itself.
        for name in list(dirnames):
            candidate = os.path.join(current, name)
            if os.path.islink(candidate) and not _inside(source_root, os.path.realpath(candidate)):
                raise ExitError(
                    "source tree link escapes the checkout: {} -> {}".format(
                        candidate, os.path.realpath(candidate)
                    ),
                    Exit.INTEGRITY,
                )
        relative = os.path.relpath(current, origin)
        here = target if relative == "." else os.path.join(target, relative)
        os.makedirs(here, exist_ok=True)
        for name in sorted(filenames):
            if name in PAYLOAD_EXCLUDE_NAMES:
                continue
            src = os.path.join(current, name)
            dst = os.path.join(here, name)
            if os.path.islink(src):
                resolved = os.path.realpath(src)
                if not _inside(source_root, resolved):
                    raise ExitError(
                        "source tree link escapes the checkout: {} -> {}".format(src, resolved),
                        Exit.INTEGRITY,
                    )
                src = resolved
            if not os.path.isfile(src):
                continue
            shutil.copyfile(src, dst)
            _mirror_exec_bit(src, dst)
            written += 1
    return written


def _mirror_exec_bit(source: str, target: str) -> None:
    mode = os.stat(source).st_mode
    os.chmod(target, EXEC_MODE if mode & stat.S_IXUSR else FILE_MODE)
