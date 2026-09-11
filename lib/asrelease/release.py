"""Release identity, payload shape, and integrity.

A "release" is a directory tree plus a manifest that says what that tree is
supposed to be. Everything downstream — activation, rollback, drift detection —
depends on being able to answer "is this tree still the release it claims to
be?" without trusting the thing that produced it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from datetime import datetime, timezone

from .exits import Exit, ExitError

RELEASE_SCHEMA = "agent-skills.release/v1"
RELEASE_MANIFEST_NAME = "release.json"

# What a release payload consists of. Anything not listed here never leaves the
# repository: evals, eval-runs, the npm bootstrap sources, CI config, and the
# git history are development assets, not product.
#
# Order matters only for readability. Missing optional entries are skipped;
# missing required ones fail the build.
PAYLOAD_ENTRIES = (
    ("VERSION", True),
    ("bin", True),
    ("lib", True),
    ("scripts", True),
    ("skills", True),
    ("docs", False),
    ("hooks", False),
    ("README.md", False),
    ("LICENSE", False),
)

# Paths never copied into a payload even when they sit inside an included tree.
PAYLOAD_EXCLUDE_NAMES = frozenset(
    {
        ".git",
        ".DS_Store",
        "__pycache__",
        ".pytest_cache",
        ".venv",
        "node_modules",
        ".env",
        ".env.local",
    }
)

SEMVER_RE = re.compile(
    r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?:-(?P<pre>[0-9A-Za-z.-]+))?(?:\+(?P<build>[0-9A-Za-z.-]+))?$"
)

CHANNELS = ("stable", "rc")

# The values a machine may be recorded as following. `any` is not a channel a
# release belongs to — `channel_of` never returns it — but it is a line a --dev
# install follows, so it is accepted here and nowhere else. Anything outside
# this set is not a channel: resolution falls back to `stable` rather than
# trusting whatever the manifest happened to contain.
FOLLOWABLE_CHANNELS = frozenset(CHANNELS) | {"any"}

# The first release whose payload can be installed by this engine.
#
# A release payload is not just data: the installer runs its launcher for the
# staged self-test, its `scripts/hosts-reconcile.sh` to register hosts, and its
# `verify` afterwards. Releases before v0.43.0 carry none of those, because
# before v0.43.0 the installer was `setup.init` inside a manual clone. Refusing
# them with one clear sentence is better than letting the self-test fail with a
# usage dump from a launcher that has never heard of it.
MIN_INSTALLABLE_VERSION = "0.43.0"


# ------------------------------------------------------------------------------
# Version handling
# ------------------------------------------------------------------------------
def normalise_version(raw: str) -> str:
    """Strip a leading ``v`` and surrounding whitespace. Does not validate."""
    return (raw or "").strip().lstrip("vV").strip()


def is_version(raw: str) -> bool:
    """Whether ``raw`` is a semantic version this engine will act on."""
    return parse_version(raw) is not None


def require_version(raw: str, what: str = "release version", code: int = Exit.USAGE) -> str:
    """Return the normalised version, or refuse to carry the value any further.

    Every version in this engine arrives from outside it: a ``--version``
    argument, a git tag, a ``VERSION`` file in a directory somebody handed us.
    Downstream, a version becomes a path — ``versions/<v>``,
    ``cache/staging/<v>`` — and one of those paths is passed to ``rmtree``. So a
    version that is not a version is not a cosmetic problem: ``../../x`` is a
    delete primitive aimed wherever the caller likes.

    Validation therefore happens at the boundary, before the value is used for
    anything at all, and ``Layout`` enforces the path-shape invariant again on
    its own account. Two independent checks, because the cost of the first one
    being bypassed is unrecoverable.
    """
    normalised = normalise_version(raw)
    if parse_version(normalised) is None:
        shown = (raw or "").strip()
        raise ExitError(
            "{} {!r} is not a semantic version".format(what, shown[:120]),
            code,
            hint=(
                "expected MAJOR.MINOR.PATCH with an optional -prerelease and +build,\n"
                "  for example 1.0.0, 1.0.0-rc.4, or v0.43.0"
            ),
        )
    return normalised


def parse_version(raw: str):
    """Return a sort key for a semver string, or ``None`` when it is not semver.

    Pre-release versions sort below their release, which is what makes
    ``1.0.0-rc.1`` an upgrade from ``0.43.0`` and a downgrade from ``1.0.0``.
    """
    match = SEMVER_RE.match(normalise_version(raw))
    if not match:
        return None
    major = int(match.group("major"))
    minor = int(match.group("minor"))
    patch = int(match.group("patch"))
    pre = match.group("pre")
    if pre is None:
        # No pre-release sorts above every pre-release of the same triple.
        return (major, minor, patch, 1, ())
    parts = []
    for chunk in pre.split("."):
        if chunk.isdigit():
            parts.append((0, int(chunk), ""))
        else:
            parts.append((1, 0, chunk))
    return (major, minor, patch, 0, tuple(parts))


def compare_versions(left: str, right: str) -> int:
    """-1 / 0 / 1, ordering two versions this engine already trusts.

    Unparseable input compares as equal, so that a machine carrying a version
    string this build does not understand is reported as "nothing to do" rather
    than as an upgrade or a downgrade it cannot reason about.

    That fallback makes this the wrong function for asking "is this the release
    the operator named". ``0`` here means "equal, or unknown", and an identity
    test that reads unknown as a match will happily select some other release.
    Use ``versions_equal`` for identity and ``require_version`` at the boundary
    where the string arrives.
    """
    a = parse_version(left)
    b = parse_version(right)
    if a is None or b is None:
        return 0
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


def versions_equal(left: str, right: str) -> bool:
    """Whether two strings name the same release. Unparseable is never equal."""
    a = parse_version(left)
    b = parse_version(right)
    if a is None or b is None:
        return False
    return a == b


def channel_of(version: str) -> str:
    """Which channel a version belongs to. A pre-release is never `stable`."""
    match = SEMVER_RE.match(normalise_version(version))
    if match and match.group("pre"):
        return "rc"
    return "stable"


# ------------------------------------------------------------------------------
# Release identity
# ------------------------------------------------------------------------------
class ReleaseRef:
    """One resolved release: which version, from which provider, at which ref.

    ``ref`` is provider-private (a git tag, a directory path, a registry id).
    Nothing outside the provider may parse it.
    """

    def __init__(self, version: str, provider: str, ref: str, channel: str = "", commit: str = ""):
        # A ReleaseRef is the point at which a version string stops being data
        # and starts being something the installer acts on, so it is also the
        # last place validation is cheap. Anything that reaches here unchecked —
        # a hand-edited VERSION file, a provider that grew a new resolve path —
        # is refused here rather than becoming a directory name.
        self.version = require_version(
            version, "release version from provider {}".format(provider or "?")
        )
        self.provider = provider
        self.ref = ref
        self.channel = channel or channel_of(self.version)
        self.commit = commit

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "provider": self.provider,
            "ref": self.ref,
            "channel": self.channel,
            "commit": self.commit,
        }

    def __repr__(self) -> str:
        return "ReleaseRef({} via {} @ {})".format(self.version, self.provider, self.ref)


class StagedRelease:
    """A payload that has been written to a staging directory but not activated."""

    def __init__(self, root: str, ref: ReleaseRef, manifest: dict):
        self.root = root
        self.ref = ref
        self.manifest = manifest

    @property
    def version(self) -> str:
        return self.manifest.get("version", self.ref.version)


# ------------------------------------------------------------------------------
# Payload hashing
#
# The tree hash is the whole basis of "this is the release it claims to be", so
# it has to be stable across machines and sensitive to the things that matter.
# It covers: relative path, whether the file is executable, and content. It
# deliberately does not cover mtime, owner, or the full mode, because a copy or
# a tar round-trip legitimately changes those and a hash that flags a normal
# copy is a hash everyone learns to ignore.
# ------------------------------------------------------------------------------
def _file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 256), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_payload_files(root: str):
    """Yield ``(relative_path, absolute_path)`` for every payload file, sorted.

    Symlinks inside a payload are followed only when they stay inside the
    payload; one pointing outside is a packaging bug and is reported rather
    than silently hashed as whatever it happens to reach today.
    """
    root = os.path.realpath(root)
    collected = []
    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in PAYLOAD_EXCLUDE_NAMES)
        for name in sorted(filenames):
            if name in PAYLOAD_EXCLUDE_NAMES:
                continue
            if name == RELEASE_MANIFEST_NAME and current == root:
                # The manifest carries the hash; it cannot also be inside it.
                continue
            absolute = os.path.join(current, name)
            relative = os.path.relpath(absolute, root)
            collected.append((relative, absolute))
    collected.sort(key=lambda item: item[0])
    return collected


def compute_tree_hash(root: str):
    """Return ``(tree_sha256, file_count)`` for a payload directory."""
    digest = hashlib.sha256()
    count = 0
    for relative, absolute in iter_payload_files(root):
        if os.path.islink(absolute):
            target = os.readlink(absolute)
            resolved = os.path.realpath(absolute)
            if not (resolved == root or resolved.startswith(root + os.sep)):
                raise ExitError(
                    "payload symlink escapes the release: {} -> {}".format(relative, target),
                    Exit.INTEGRITY,
                )
        try:
            mode = os.stat(absolute).st_mode
        except OSError as exc:
            raise ExitError(
                "unreadable payload file {}: {}".format(relative, exc), Exit.INTEGRITY
            )
        executable = "1" if mode & stat.S_IXUSR else "0"
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(executable.encode("ascii"))
        digest.update(b"\0")
        digest.update(_file_sha256(absolute).encode("ascii"))
        digest.update(b"\n")
        count += 1
    return digest.hexdigest(), count


# ------------------------------------------------------------------------------
# Release manifest
# ------------------------------------------------------------------------------
def read_version_file(root: str) -> str:
    path = os.path.join(root, "VERSION")
    try:
        with open(path, encoding="utf-8") as handle:
            return normalise_version(handle.readline())
    except OSError:
        return ""


def build_manifest(root: str, ref: ReleaseRef, extra: dict = None) -> dict:
    """Compute and return the manifest for a payload already written to ``root``."""
    tree_hash, file_count = compute_tree_hash(root)
    payload_version = read_version_file(root)
    manifest = {
        "schema": RELEASE_SCHEMA,
        "version": payload_version or ref.version,
        "channel": ref.channel,
        "provider": ref.provider,
        "source": {"ref": ref.ref, "commit": ref.commit},
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "payload": {
            "tree_sha256": tree_hash,
            "file_count": file_count,
            "algorithm": "sha256-tree/v1",
        },
        # Reserved so a future signed release adds a field rather than a schema.
        "signature": None,
    }
    if extra:
        manifest.update(extra)
    return manifest


def write_manifest(root: str, manifest: dict) -> str:
    path = os.path.join(root, RELEASE_MANIFEST_NAME)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.chmod(path, 0o644)
    return path


def read_manifest(root: str) -> dict:
    path = os.path.join(root, RELEASE_MANIFEST_NAME)
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        raise ExitError(
            "release manifest unreadable at {}: {}".format(path, exc), Exit.INTEGRITY
        )
    if data.get("schema") != RELEASE_SCHEMA:
        raise ExitError(
            "unknown release manifest schema {!r} at {}".format(data.get("schema"), path),
            Exit.INTEGRITY,
        )
    return data


def verify_payload(root: str, ref: ReleaseRef = None, manifest: dict = None) -> dict:
    """Assert that a staged payload is internally consistent and matches ``ref``.

    Four things must agree before a payload is allowed anywhere near activation:
    the version that was requested, the tag the provider resolved, the VERSION
    file inside the payload, and the manifest. A disagreement between any two of
    them means the payload is not the release it says it is.
    """
    manifest = manifest if manifest is not None else read_manifest(root)

    declared = normalise_version(manifest.get("version", ""))
    payload_version = read_version_file(root)
    if not payload_version:
        raise ExitError("staged payload has no readable VERSION file", Exit.INTEGRITY)
    require_version(payload_version, "payload VERSION", Exit.INTEGRITY)
    require_version(declared, "manifest version", Exit.INTEGRITY)
    if declared != payload_version:
        raise ExitError(
            "version disagreement: manifest says {}, payload VERSION says {}".format(
                declared, payload_version
            ),
            Exit.INTEGRITY,
        )
    if ref is not None and ref.version and ref.version != payload_version:
        raise ExitError(
            "version disagreement: resolved release {} delivered payload {}".format(
                ref.version, payload_version
            ),
            Exit.INTEGRITY,
        )

    recorded = manifest.get("payload", {})
    expected_hash = recorded.get("tree_sha256", "")
    if not expected_hash:
        raise ExitError("release manifest carries no payload hash", Exit.INTEGRITY)
    actual_hash, actual_count = compute_tree_hash(root)
    if actual_hash != expected_hash:
        raise ExitError(
            "payload hash mismatch at {}\n"
            "  expected {}\n"
            "  actual   {}".format(root, expected_hash, actual_hash),
            Exit.INTEGRITY,
            hint="the download is corrupt or has been tampered with; do not activate it",
        )
    expected_count = recorded.get("file_count")
    if isinstance(expected_count, int) and expected_count != actual_count:
        raise ExitError(
            "payload file count mismatch: expected {}, found {}".format(
                expected_count, actual_count
            ),
            Exit.INTEGRITY,
        )

    # Required trees must exist and be non-empty, or "installed" would mean a
    # directory with a VERSION file in it.
    for name, required in PAYLOAD_ENTRIES:
        path = os.path.join(root, name)
        if required and not os.path.exists(path):
            raise ExitError(
                "staged payload is missing required entry: {}".format(name), Exit.INTEGRITY
            )
    launcher = os.path.join(root, "bin", "agent-skills")
    if not os.path.isfile(launcher):
        raise ExitError("staged payload has no bin/agent-skills launcher", Exit.INTEGRITY)
    return manifest
