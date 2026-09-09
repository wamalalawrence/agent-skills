"""Local release provider: a source checkout or a fixture release directory.

This is the provider the maintainer uses to test an unreleased branch, the one
the test suite uses so acceptance runs need no network, and the one
``setup.init`` delegates to. It is also the proof that installation does not
depend on GitHub: everything downstream of ``fetch_release`` is identical.

Two shapes are accepted:

  * a source checkout — has ``VERSION``, ``skills/``, ``scripts/``. The payload
    is assembled by copying the payload entries and generating a manifest.
  * a prepared release directory — already carries ``release.json``. The
    manifest is taken as given and verified rather than regenerated, which is
    what makes a fixture able to represent a corrupt or hostile release.
"""

from __future__ import annotations

import os

from ..exits import Exit
from ..archive import copy_payload
from ..release import (
    PAYLOAD_ENTRIES,
    RELEASE_MANIFEST_NAME,
    ReleaseRef,
    StagedRelease,
    build_manifest,
    channel_of,
    read_manifest,
    read_version_file,
    write_manifest,
)
from . import AuthState, ProviderError, ReleaseProvider


class LocalReleaseProvider(ReleaseProvider):
    id = "local"

    def __init__(self, source: str = "", **_ignored):
        if not source:
            raise ProviderError("the local provider needs --source DIR", Exit.USAGE)
        self.source = os.path.realpath(os.path.expanduser(source))
        if not os.path.isdir(self.source):
            raise ProviderError(
                "source directory does not exist: {}".format(self.source), Exit.USAGE
            )
        self.description = "local directory {}".format(self.source)

    # A local directory is readable or it is not; there is no credential.
    def auth_state(self) -> str:
        return AuthState.NOT_REQUIRED

    def _is_prepared_release(self) -> bool:
        return os.path.isfile(os.path.join(self.source, RELEASE_MANIFEST_NAME))

    def _version(self) -> str:
        version = read_version_file(self.source)
        if not version:
            raise ProviderError(
                "no readable VERSION file in {}".format(self.source), Exit.USAGE
            )
        return version

    def resolve_latest(self, channel: str = "stable") -> ReleaseRef:
        version = self._version()
        found = channel_of(version)
        # A local directory holds exactly one release. Asking for a channel it
        # is not on is a usage error rather than a silent mismatch: installing
        # an rc while asking for stable is precisely the surprise channels exist
        # to prevent.
        if channel and channel != "any" and found != channel:
            raise ProviderError(
                "source {} holds a {} release ({}), not a {} one".format(
                    self.source, found, version, channel
                ),
                Exit.USAGE,
                hint="pass --channel {} to install it".format(found),
            )
        return ReleaseRef(version, self.id, self.source, channel=found)

    def resolve_version(self, version: str) -> ReleaseRef:
        actual = self._version()
        wanted = (version or "").lstrip("vV")
        if wanted and wanted != actual:
            raise ProviderError(
                "source {} holds version {}, not {}".format(self.source, actual, wanted),
                Exit.USAGE,
            )
        return ReleaseRef(actual, self.id, self.source)

    def available_versions(self):
        try:
            return [self._version()]
        except ProviderError:
            return []

    def fetch_release(self, ref: ReleaseRef, dest: str) -> StagedRelease:
        os.makedirs(dest, exist_ok=True)
        if self._is_prepared_release():
            # A prepared release is copied byte-for-byte, manifest included, so
            # a deliberately corrupt fixture stays corrupt and the verify step
            # is the thing being tested rather than a regenerated manifest.
            entries = PAYLOAD_ENTRIES + ((RELEASE_MANIFEST_NAME, True),)
            copy_payload(self.source, dest, entries)
            manifest = read_manifest(dest)
            return StagedRelease(dest, ref, manifest)

        copy_payload(self.source, dest, PAYLOAD_ENTRIES)
        manifest = build_manifest(dest, ref, extra={"source": {"ref": self.source, "commit": ""}})
        write_manifest(dest, manifest)
        return StagedRelease(dest, ref, manifest)
