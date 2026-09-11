"""The on-disk shape of an Agent Skills installation.

    ~/.agent-skills/
        current -> versions/<active>     the only thing activation changes
        versions/
            0.42.0/                      a complete, self-contained release
            0.43.0/
        state/                           survives every upgrade and rollback
            history.json
        cache/                           downloads; safe to delete
        install.json                     the machine-global install manifest
        VERSION                          the active version, as plain text
        bin  -> current/bin              stable paths that never need rewriting
        lib  -> current/lib
        docs -> current/docs
        hooks -> current/hooks
        scripts -> current/scripts
        skills -> current/skills

Two properties make the rest of the system simple.

First, every stable path in the installation goes through ``current``. A host
registration written to ``~/.claude/skills/wamala`` points at
``~/.agent-skills/skills/wamala``, which resolves through ``current`` to the
active release. Activating a new version repoints one symlink and every host,
every hook, and every skill follows in the same instant. Nothing has to be
rewritten per host, so there is no window in which some hosts are on the new
version and some on the old.

Second, a version directory is complete. Skills, scripts, lib, and docs from
one release live together and are never mixed, because ``current`` can only
point at one of them.

Credentials are deliberately not here. They live under
``~/.config/agent-skills`` so that removing an installation cannot destroy a
user's identities.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import time
from datetime import datetime, timezone

try:  # POSIX only; the installer supports macOS and Linux.
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX
    fcntl = None

from .exits import Exit, ExitError
from .release import normalise_version

# Directories linked from the install root into the active release. These names
# are a compatibility surface: skills and docs reference `~/.agent-skills/scripts`
# and `~/.agent-skills/docs` by absolute path.
LINKED_TREES = ("skills", "scripts", "lib", "bin", "docs", "hooks")

MANIFEST_SCHEMA = "agent-skills.install/v2"

# What a release directory may be named. Deliberately wider than semver — a
# directory that predates this check, or a fixture name a test chose, still has
# to be addressable — and deliberately narrower than "any string": exactly one
# path component, no separators, no leading dot, nothing that traverses.
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")


def default_home() -> str:
    home = os.environ.get("AGENT_SKILLS_HOME")
    if home:
        return os.path.abspath(os.path.expanduser(home.rstrip("/")))
    return os.path.join(os.path.expanduser("~"), ".agent-skills")


def default_config_dir() -> str:
    configured = os.environ.get("AGENT_SKILLS_CONFIG_DIR")
    if configured:
        return os.path.abspath(os.path.expanduser(configured.rstrip("/")))
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return os.path.join(os.path.abspath(os.path.expanduser(xdg.rstrip("/"))), "agent-skills")
    return os.path.join(os.path.expanduser("~"), ".config", "agent-skills")


class Layout:
    """Paths and the small number of operations that change them."""

    def __init__(self, home: str = "", config_dir: str = ""):
        self.home = os.path.abspath(os.path.expanduser(home)) if home else default_home()
        self.config_dir = (
            os.path.abspath(os.path.expanduser(config_dir)) if config_dir else default_config_dir()
        )

    # ---- paths ---------------------------------------------------------------
    @property
    def current(self) -> str:
        return os.path.join(self.home, "current")

    @property
    def versions_dir(self) -> str:
        return os.path.join(self.home, "versions")

    @property
    def state_dir(self) -> str:
        return os.path.join(self.home, "state")

    @property
    def cache_dir(self) -> str:
        return os.path.join(self.home, "cache")

    @property
    def staging_dir(self) -> str:
        return os.path.join(self.home, "cache", "staging")

    @property
    def manifest_path(self) -> str:
        return os.path.join(self.home, "install.json")

    @property
    def history_path(self) -> str:
        return os.path.join(self.state_dir, "history.json")

    @property
    def version_file(self) -> str:
        return os.path.join(self.home, "VERSION")

    @property
    def launcher(self) -> str:
        return os.path.join(self.home, "bin", "agent-skills")

    def version_path(self, version: str) -> str:
        return os.path.join(self.versions_dir, self.safe_component(version))

    def staging_path(self, version: str) -> str:
        return os.path.join(self.staging_dir, self.safe_component(version))

    @staticmethod
    def safe_component(version: str) -> str:
        """The one directory name a version may become, or an error.

        This is enforced here, independently of whether the caller validated the
        version, because every path this class builds is eventually passed to
        ``rmtree``, ``rename``, or ``symlink``. A version of ``../../x`` would
        turn ``version_path`` into a delete primitive aimed anywhere on the
        filesystem, and no amount of care at the call sites is worth relying on
        for that. The check is about path shape only: whether the value is a
        *release* version is ``release.require_version``'s question, asked at the
        boundary where the string arrives.
        """
        name = normalise_version(version)
        if not name or not _SAFE_COMPONENT.match(name) or name in (".", ".."):
            raise ExitError(
                "{!r} is not a usable release directory name".format((version or "")[:120]),
                Exit.USAGE,
                hint=(
                    "a release version becomes one directory under versions/, so it may not\n"
                    "  contain a path separator, start with a dot, or traverse upwards"
                ),
            )
        return name

    # ---- state ---------------------------------------------------------------
    def ensure_dirs(self) -> None:
        for path in (self.home, self.versions_dir, self.state_dir, self.cache_dir):
            os.makedirs(path, exist_ok=True)
        os.makedirs(self.config_dir, exist_ok=True)
        try:
            os.chmod(self.config_dir, 0o700)
        except OSError:
            pass

    def installed_versions(self):
        if not os.path.isdir(self.versions_dir):
            return []
        found = []
        for name in os.listdir(self.versions_dir):
            path = os.path.join(self.versions_dir, name)
            if os.path.isdir(path) or os.path.islink(path):
                found.append(name)
        return sorted(found)

    def active_version(self) -> str:
        """The version ``current`` points at, read from the link, not the manifest."""
        try:
            target = os.readlink(self.current)
        except OSError:
            return ""
        return os.path.basename(target.rstrip("/"))

    def active_root(self) -> str:
        if not os.path.exists(self.current):
            return ""
        return os.path.realpath(self.current)

    def read_manifest(self) -> dict:
        try:
            with open(self.manifest_path, encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            return {}

    def write_manifest(self, payload: dict) -> None:
        os.makedirs(self.home, exist_ok=True)
        temporary = self.manifest_path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(temporary, 0o644)
        os.replace(temporary, self.manifest_path)

    def read_history(self) -> list:
        try:
            with open(self.history_path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return []
        return data if isinstance(data, list) else []

    def append_history(self, entry: dict) -> None:
        os.makedirs(self.state_dir, exist_ok=True)
        history = self.read_history()
        history.append(entry)
        # Bounded: this is an audit trail for the last few operations, not a log.
        history = history[-50:]
        temporary = self.history_path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(history, handle, indent=2)
            handle.write("\n")
        os.replace(temporary, self.history_path)

    def rollback_candidate(self) -> str:
        """The release ``agent-skills rollback`` would return to, or empty.

        This is "the version that was active before this one", read from
        history rather than from a static pointer. After an update it is the
        release you came from; after a rollback it is the release you rolled
        back from, so a second rollback undoes the first rather than walking
        further into the past. Rollback is an undo, not a time machine.
        """
        active = self.active_version()
        for entry in reversed(self.read_history()):
            previous = entry.get("from", "")
            if not previous or previous == active:
                continue
            # History is data on disk and may name something that is not a
            # usable directory. A malformed entry makes that entry unusable as a
            # rollback target, not this whole lookup.
            path = self.installed_path(previous)
            if path and os.path.isdir(path):
                return previous
        return ""

    def installed_path(self, version: str) -> str:
        """``version_path`` for a name that may be junk. Empty when unusable."""
        try:
            return self.version_path(version)
        except ExitError:
            return ""

    # ---- mutation ------------------------------------------------------------
    def link(self, target: str, link_path: str) -> str:
        """Create or repoint a symlink inside the install root.

        Only ever called for paths under ``home``, which this installation
        created and therefore owns. Returns created | kept | relinked.
        """
        if os.path.islink(link_path):
            if os.readlink(link_path) == target:
                return "kept"
            os.remove(link_path)
            os.symlink(target, link_path)
            return "relinked"
        if os.path.exists(link_path):
            # A real directory where a link belongs is either a pre-v0.43
            # installation or somebody else's data. Both are the caller's
            # problem to resolve explicitly; never delete a real directory.
            raise ExitError(
                "{} exists and is not a symlink managed by agent-skills".format(link_path),
                Exit.INSTALL_FAILED,
                hint="move it aside and rerun, or run: agent-skills uninstall",
            )
        os.makedirs(os.path.dirname(link_path), exist_ok=True)
        os.symlink(target, link_path)
        return "created"

    def activate(self, version: str) -> None:
        """Point ``current`` at ``version`` atomically, then refresh the trees.

        The swap uses a temporary link and ``os.replace``, so no observer ever
        sees ``current`` missing. That matters because a host may be reading a
        skill through it at the moment of the swap.
        """
        version = normalise_version(version)
        target_dir = self.version_path(version)
        if not os.path.isdir(target_dir):
            raise ExitError(
                "cannot activate {}: {} is not an installed release".format(version, target_dir),
                Exit.INSTALL_FAILED,
            )
        self.ensure_dirs()
        relative = os.path.join("versions", version)
        temporary = self.current + ".activating"
        if os.path.lexists(temporary):
            os.remove(temporary)
        os.symlink(relative, temporary)
        os.replace(temporary, self.current)

        for tree in LINKED_TREES:
            source = os.path.join(target_dir, tree)
            if not os.path.exists(source):
                continue
            self._replace_managed_link(os.path.join("current", tree), os.path.join(self.home, tree))

        with open(self.version_file, "w", encoding="utf-8") as handle:
            handle.write(version + "\n")

    def _replace_managed_link(self, target: str, link_path: str) -> None:
        """Repoint a top-level install link, replacing a pre-v0.43 absolute one.

        Before v0.43 these pointed straight at a source checkout. They are
        inside the install root, which this installation owns, so replacing
        them is safe — but a real directory there is still never removed.
        """
        if os.path.islink(link_path):
            if os.readlink(link_path) == target:
                return
            os.remove(link_path)
        elif os.path.exists(link_path):
            raise ExitError(
                "{} is a real directory; agent-skills will not delete it".format(link_path),
                Exit.INSTALL_FAILED,
                hint="move it aside and rerun the install",
            )
        os.symlink(target, link_path)

    def prune_versions(self, keep: int = 2) -> list:
        """Remove old release directories, always keeping the active one and
        the rollback candidate. Returns the versions removed."""
        from .release import parse_version

        active = self.active_version()
        candidate = self.rollback_candidate()
        protected = {v for v in (active, candidate) if v}
        versions = [
            v for v in self.installed_versions()
            if v not in protected and _SAFE_COMPONENT.match(v)
        ]
        versions.sort(key=lambda v: parse_version(v) or (0, 0, 0, 0, ()))
        removed = []
        surplus = len(versions) + len(protected) - keep
        for version in versions:
            if surplus <= 0:
                break
            path = self.version_path(version)
            if os.path.islink(path):
                os.remove(path)
            else:
                shutil.rmtree(path, ignore_errors=True)
            removed.append(version)
            surplus -= 1
        return removed

    def clear_manifest(self) -> None:
        """Remove the install manifest. Used when a first install is undone."""
        for path in (self.manifest_path, self.manifest_path + ".tmp"):
            try:
                os.remove(path)
            except OSError:
                pass

    @contextlib.contextmanager
    def exclusive(self, action: str = "install", timeout: float = 120.0):
        """Hold the install lock for the duration of a state-changing operation.

        Everything in this class is careful about crash-safety and says nothing
        about concurrency, which made "atomic, no mixed state" true of one
        process and untrue of two. Two updates racing share
        ``cache/staging/<v>`` and ``versions/<v>.incoming``, and the moment one
        of them moves the running release aside is a moment the other can
        activate into the gap.

        One advisory lock per install root closes that. It is advisory on
        purpose: a stale lock from a killed process is released by the kernel
        when the file descriptor goes, so there is no lock file to clean up by
        hand and no state in which the installer is permanently wedged.
        """
        if fcntl is None:  # pragma: no cover - non-POSIX
            yield
            return
        os.makedirs(self.state_dir, exist_ok=True)
        path = os.path.join(self.state_dir, "install.lock")
        handle = open(path, "a+", encoding="utf-8")
        deadline = time.monotonic() + max(0.0, timeout)
        held = False
        try:
            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    held = True
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        try:
                            handle.seek(0)
                            holder = handle.read(200).strip()
                        except OSError:
                            holder = ""
                        raise ExitError(
                            "another agent-skills operation is already running against {}".format(
                                self.home
                            ),
                            Exit.INSTALL_FAILED,
                            hint=(
                                "waited {:.0f}s for the install lock{}\n"
                                "  nothing was changed; retry when it finishes".format(
                                    timeout, " (held by {})".format(holder) if holder else ""
                                )
                            ),
                        )
                    time.sleep(0.2)
            try:
                handle.seek(0)
                handle.truncate()
                handle.write("pid {} {} at {}\n".format(os.getpid(), action, self.now()))
                handle.flush()
            except OSError:
                pass
            yield
        finally:
            if held:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
            handle.close()

    def now(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
