"""Release providers: where a release payload comes from.

The installer knows four verbs and nothing else:

    resolve_latest(channel) -> ReleaseRef
    resolve_version(version) -> ReleaseRef
    fetch_release(ref, dest) -> StagedRelease
    verify_release(staged) -> dict

Everything GitHub-specific lives in ``git.py``. Everything filesystem-specific
lives in ``local.py``. A future ``PremiumRegistryProvider`` — subscription
entitlement, short-lived download authorisation, signed bundle — implements the
same four verbs and the installer does not change. The test suite proves that
by registering an in-process fake registry provider and running the real
install transaction through it.

Providers are registered by name, never loaded from a path. A repository or
project the user has merely opened must not be able to point the global
installer at code or credentials of its choosing, so there is deliberately no
"provider module" environment variable and no plugin directory.
"""

from __future__ import annotations

from ..exits import Exit, ExitError


class AuthState:
    """What a provider knows about its own ability to reach its source."""

    NOT_REQUIRED = "not-required"
    AVAILABLE = "available"
    REQUIRED = "required"
    UNKNOWN = "unknown"


class ProviderError(ExitError):
    """A provider could not do its job. Carries the right exit code."""


class ReleaseProvider:
    """Base class. Subclasses override the four verbs."""

    id = "abstract"
    #: Human-readable description of where releases come from, shown by doctor.
    description = ""

    def auth_state(self) -> str:
        """Report whether this provider can reach its source right now.

        Never returns a credential, never prints one, and must not block on an
        interactive prompt.
        """
        return AuthState.NOT_REQUIRED

    def resolve_latest(self, channel: str = "stable"):
        raise NotImplementedError

    def resolve_version(self, version: str):
        raise NotImplementedError

    def available_versions(self):
        """Every version this provider can offer, newest last. May be empty."""
        return []

    def fetch_release(self, ref, dest: str):
        raise NotImplementedError

    def verify_release(self, staged):
        from ..release import verify_payload

        return verify_payload(staged.root, staged.ref, staged.manifest)

    def describe(self) -> dict:
        return {"id": self.id, "description": self.description, "auth": self.auth_state()}


_REGISTRY = {}


def register_provider(name: str, factory) -> None:
    """Register a provider factory under a name.

    Used by the built-in providers below and by the test suite's fake registry
    provider. It is an in-process call on purpose: registration is a code-level
    decision, not configuration a hostile repository can influence.
    """
    _REGISTRY[name] = factory


def provider_names():
    return sorted(_REGISTRY)


def build_provider(name: str = "", **options):
    """Construct a provider by name.

    ``local`` and ``git`` are always available. ``name`` defaults to ``local``
    when a source directory was given and ``git`` otherwise, so the common
    cases need no flag.
    """
    if not name:
        name = "local" if options.get("source") else "git"
    factory = _REGISTRY.get(name)
    if factory is None:
        raise ProviderError(
            "unknown release provider {!r}; known providers: {}".format(
                name, ", ".join(provider_names()) or "none"
            ),
            Exit.USAGE,
        )
    return factory(**options)


def _install_builtins():
    from .local import LocalReleaseProvider
    from .git import GitReleaseProvider

    register_provider("local", lambda **kw: LocalReleaseProvider(**kw))
    register_provider("git", lambda **kw: GitReleaseProvider(**kw))


_install_builtins()
