"""Agent Skills release and distribution engine.

This package is the single authoritative implementation of everything that
happens between "a release exists somewhere" and "a release is staged on this
machine, verified, and ready to activate".

It is deliberately free of GitHub-specific knowledge outside
``providers/git.py``. The installer talks to a ``ReleaseProvider``; whether the
payload arrives from a local checkout, an authenticated private git remote, or
a future subscription registry is the provider's problem and nobody else's.

The same modules are vendored verbatim into the npm bootstrap package, so a
machine with no Agent Skills installation runs exactly this code to fetch its
first release. ``scripts/build-npm-bootstrap.sh`` copies them and
``scripts/test-npm-bootstrap.sh`` asserts the copy is byte-identical.
"""

from .exits import Exit, ExitError
from .release import ReleaseRef, StagedRelease, PAYLOAD_ENTRIES
from .providers import build_provider, AuthState, ProviderError

__all__ = [
    "Exit",
    "ExitError",
    "ReleaseRef",
    "StagedRelease",
    "PAYLOAD_ENTRIES",
    "build_provider",
    "AuthState",
    "ProviderError",
]
