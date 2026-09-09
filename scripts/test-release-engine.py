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

from asrelease.archive import ArchiveError, safe_extract_tar  # noqa: E402
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
    parse_version,
    verify_payload,
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
    assert set(Exit.NAMES) == {0, 2, 3, 4, 5, 6, 7, 10}


@check("payload: the entry list does not carry development-only trees")
def _(box):
    names = {name for name, _required in PAYLOAD_ENTRIES}
    for forbidden in ("evals", "eval-runs", "npm", ".github", "setup.init", "CHANGELOG.md"):
        assert forbidden not in names, forbidden
    for required in ("VERSION", "bin", "lib", "scripts", "skills"):
        assert required in names, required


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
